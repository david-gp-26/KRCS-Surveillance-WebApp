"""AI Knowledge Base: upload KRCS documents, index them in Qdrant, and answer questions from them.

Flow: upload file -> Knowledge Document (status Processing, approval Draft) -> background job:
      extract sections -> split into chunks -> embed locally (fastembed, nothing leaves the server)
      -> upsert into Qdrant (one point per chunk) -> status Indexed with chunk count.
An approver then sets approval to Approved; only Approved documents are searchable by non-editors,
filtered by audience role (applied_to). Approval, audience and diseases are copied onto every
chunk's payload and kept in sync without re-indexing.

Answering (retrieval-augmented generation, all open source, nothing leaves the server):
    1. question  -> disease detection and synonym expansion (Alert Threshold Config synonyms)
    2. hybrid search in Qdrant: dense vectors (meaning) + BM25 sparse vectors (exact words such as
       "AWD", "505", drug names), merged with reciprocal rank fusion
    3. re-rank the top candidates with a multilingual cross-encoder and keep the best few
    4. a local LLM (Qwen via Ollama) writes ONE answer using only those passages, citing them [1] [2];
       if the passages do not cover the question it says so instead of guessing
    5. the answer can stream to the browser word by word (Frappe realtime)
If the LLM is unreachable, ask() still returns the best passages (mode "passages").

APIs: ask() for the assistant page; search() and get_passage() for the chatbot (David).

Site config (bench --site <site> set-config <key> <value>):
    qdrant_url            default http://localhost:6333
    qdrant_api_key        optional
    kb_collection         default krcs_kb_v2 (hybrid collection; run reindex_all after first install)
    kb_embedding_model    default sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    kb_sparse_model       default Qdrant/bm25
    kb_reranker_model     default jinaai/jina-reranker-v2-base-multilingual ("off" to disable)
    kb_llm_url            default http://localhost:11434 (Ollama)
    kb_llm_model          default qwen3:4b
    kb_llm_timeout        default 120 (seconds)
    kb_min_rerank_score   default 0.15 (below this the question is treated as not covered)
    kb_score_high         default 0.60  (dense score at or above = confidence "high")
    kb_score_low          default 0.45  (dense score below = confidence "low")
"""
import json
import os
import re
import time
import uuid

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, today

from surveillance import kb_access
from surveillance.capabilities import has_capability, require_capability
from surveillance.kb_access import KBAccessDenied  # noqa: F401  (re-exported for callers and tests)

DOCTYPE = "Knowledge Document"
CAPABILITY = "manage_knowledge_base"
APPROVE_CAPABILITY = "approve_knowledge_base"
SEARCH_CAPABILITY = "use_knowledge_base"
SERVICE_CAPABILITY = "kb_service"
APPROVAL_STATUSES = ("Draft", "Approved", "Retired")
ALL_ROLES = "All roles"
ALL_REGIONS = "All regions"
LANGUAGES = ("English", "Kiswahili")
LANGUAGE_BOOST = 0.05   # added to the score of passages in the asker's language when ranking
MAX_LIMIT = 20
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md"}
MAX_BYTES = 25 * 1024 * 1024
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 150
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # English + Kiswahili
DEFAULT_SPARSE = "Qdrant/bm25"
DEFAULT_RERANKER = "jinaai/jina-reranker-v2-base-multilingual"
DEFAULT_LLM = "qwen3:4b"
DENSE, SPARSE = "dense", "bm25"   # named vectors in the hybrid collection
CANDIDATES = 30                   # passages fetched before re-ranking
CONTEXT_PASSAGES = 5              # passages given to the LLM
NOT_FOUND = {
	"English": "I couldn't find this in the approved KRCS documents. Please check with your supervisor or the relevant guideline.",
	"Kiswahili": "Sikupata jibu la swali hili katika nyaraka zilizoidhinishwa za KRCS. Tafadhali wasiliana na msimamizi wako au mwongozo husika.",
}
INDEXED_FIELDS = ("doc", "category", "approval_status", "applied_to", "diseases", "regions", "language")
INTEGER_FIELDS = ("valid_from", "valid_to")   # effective dates as YYYYMMDD, filtered inside Qdrant (R62)
OPEN_START, OPEN_END = 0, 99991231

_model = None
_sparse_model = None
_reranker = None


class KBUnavailable(frappe.ValidationError):
	"""Qdrant or the embedding model is not reachable. Returned as HTTP 503."""
	http_status_code = 503


ACCESS_POLICY_VERSION = kb_access.POLICY_VERSION


def retrieval_config():
	"""Short id of everything that shapes an answer, stamped on every Query Log record (AI/ML spec 7.9)."""
	parts = [
		_collection(),
		_conf("kb_embedding_model", DEFAULT_MODEL).split("/")[-1],
		_conf("kb_sparse_model", DEFAULT_SPARSE).split("/")[-1],
		_conf("kb_reranker_model", DEFAULT_RERANKER).split("/")[-1],
		_conf("kb_llm_model", DEFAULT_LLM),
		"t%s-%s" % (_conf("kb_score_high", 0.60), _conf("kb_score_low", 0.45)),
		"m%s" % _conf("kb_min_rerank_score", 0.15),
	]
	return "|".join(str(p) for p in parts)[:140]


# ---------- clients ----------

def _conf(key, default=None):
	return frappe.conf.get(key) or default


def _collection():
	return _conf("kb_collection", "krcs_kb_v2")


def _qdrant():
	from qdrant_client import QdrantClient
	return QdrantClient(url=_conf("qdrant_url", "http://localhost:6333"), api_key=_conf("qdrant_api_key"), timeout=60)


def _embedder():
	global _model
	if _model is None:
		from fastembed import TextEmbedding
		cache = os.path.join(frappe.get_site_path(), "private", "fastembed_cache")
		_model = TextEmbedding(model_name=_conf("kb_embedding_model", DEFAULT_MODEL), cache_dir=cache)
	return _model


def _cache_dir():
	return os.path.join(frappe.get_site_path(), "private", "fastembed_cache")


def embed(texts):
	return [list(map(float, v)) for v in _embedder().embed(texts)]


def _sparse():
	global _sparse_model
	if _sparse_model is None:
		from fastembed import SparseTextEmbedding
		_sparse_model = SparseTextEmbedding(model_name=_conf("kb_sparse_model", DEFAULT_SPARSE), cache_dir=_cache_dir())
	return _sparse_model


def sparse_embed(texts, query=False):
	from qdrant_client.models import SparseVector
	model = _sparse()
	vecs = model.query_embed(texts) if query else model.embed(texts)
	return [SparseVector(indices=v.indices.tolist(), values=v.values.tolist()) for v in vecs]


def _rerank_model():
	"""Cross-encoder re-ranker, or None if disabled or not loadable (search still works without it)."""
	global _reranker
	name = _conf("kb_reranker_model", DEFAULT_RERANKER)
	if name == "off":
		return None
	if _reranker is None:
		try:
			from fastembed.rerank.cross_encoder import TextCrossEncoder
			_reranker = TextCrossEncoder(model_name=name, cache_dir=_cache_dir())
		except Exception:
			frappe.log_error(title="Knowledge Base: re-ranker could not load")
			_reranker = False
	return _reranker or None


def _ensure_collection(client, size):
	from qdrant_client.models import (Distance, Modifier, PayloadSchemaType, SparseVectorParams,
		VectorParams)
	name = _collection()
	if not client.collection_exists(name):
		client.create_collection(name,
			vectors_config={DENSE: VectorParams(size=size, distance=Distance.COSINE)},
			sparse_vectors_config={SPARSE: SparseVectorParams(modifier=Modifier.IDF)})
	for field in INDEXED_FIELDS:  # also adds new indexes to an existing collection
		try:
			client.create_payload_index(name, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
		except Exception:
			pass
	for field in INTEGER_FIELDS:
		try:
			client.create_payload_index(name, field_name=field, field_schema=PayloadSchemaType.INTEGER)
		except Exception:
			pass
	return name


def _doc_filter(docname):
	from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
	return FilterSelector(filter=Filter(must=[FieldCondition(key="doc", match=MatchValue(value=docname))]))


def _delete_vectors(client, docname):
	if client.collection_exists(_collection()):
		client.delete(_collection(), points_selector=_doc_filter(docname))


# ---------- access fields ----------

def _split(value):
	if isinstance(value, str) and value.strip().startswith("["):
		value = frappe.parse_json(value)
	if isinstance(value, (list, tuple)):
		return [str(v).strip() for v in value if str(v).strip()]
	return [v.strip() for v in (value or "").split(",") if v.strip()]


def _clean_diseases(value):
	from surveillance.case_definitions import get_disease_options
	keys = _split(value)
	valid = {d["key"] for d in get_disease_options()}
	unknown = [k for k in keys if k not in valid]
	if unknown:
		frappe.throw(_("Unknown disease key(s): {0}").format(", ".join(unknown)))
	return ", ".join(keys)


def _day(value):
	return int(str(getdate(value)).replace("-", "")) if value else None


def hide_after_review():
	"""D6: a document past its review date stops being served (default on, as the chatbot service assumes)."""
	return cint(frappe.conf.get("kb_hide_after_review_date", 1)) == 1


def valid_window(doc):
	"""(valid_from, valid_to) as YYYYMMDD. Content is served only when valid_from <= today <= valid_to."""
	ends = [d for d in (doc.get("expiry_date"), doc.get("review_date") if hide_after_review() else None) if d]
	return (_day(doc.get("effective_from")) or OPEN_START, min(_day(d) for d in ends) if ends else OPEN_END)


def _access_payload(doc):
	"""Fields used for filtering and citation; updated on every chunk without re-indexing."""
	valid_from, valid_to = valid_window(doc)
	return {
		"valid_from": valid_from,
		"valid_to": valid_to,
		"effective_from": str(doc.effective_from) if doc.get("effective_from") else None,
		"approval_status": doc.get("approval_status") or "Draft",
		"applied_to": _split(doc.applied_to) or [ALL_ROLES],
		"diseases": _split(doc.get("diseases")),
		"regions": _split(doc.get("regions")) or [ALL_REGIONS],
		"language": doc.get("language") or "English",
		"review_date": str(doc.review_date) if doc.get("review_date") else None,
		"expiry_date": str(doc.expiry_date) if doc.get("expiry_date") else None,
		"version": doc.version,
		"category": doc.category,
	}


def _clean_regions(value):
	regions = [r for r in _split(value) if r != ALL_REGIONS]
	valid = set(frappe.get_all("Region", pluck="name"))
	unknown = [r for r in regions if r not in valid]
	if unknown:
		frappe.throw(_("Unknown region(s): {0}").format(", ".join(unknown)))
	return ", ".join(regions) or ALL_REGIONS


def _check_dates(doc):
	if doc.get("language") and doc.language not in LANGUAGES:
		frappe.throw(_("Language must be one of: {0}").format(", ".join(LANGUAGES)))
	if doc.get("review_date") and doc.get("expiry_date") and getdate(doc.review_date) > getdate(doc.expiry_date):
		frappe.throw(_("Review date must be on or before the expiry date."))
	for end in ("review_date", "expiry_date"):
		if doc.get("effective_from") and doc.get(end) and getdate(doc.effective_from) > getdate(doc.get(end)):
			frappe.throw(_("The effective-from date must be on or before the {0}.").format(
				_("review date") if end == "review_date" else _("expiry date")))


def _sync_access(doc):
	"""Copy approval, audience and diseases onto every chunk of this document. No re-embedding."""
	try:
		client = _qdrant()
		if client.collection_exists(_collection()):
			client.set_payload(_collection(), payload=_access_payload(doc), points=_doc_filter(doc.name))
	except Exception:
		frappe.log_error(title=f"Knowledge Base: access sync failed for {doc.name}")


# ---------- text extraction and chunking ----------

def extract_units(path, ext):
	"""return [{section, page, text}] so every chunk can be cited.
	PDF: one unit per page. DOCX: one per heading section, one per table row (named by its first cell).
	TXT/MD: one per # heading."""
	units = []
	if ext == "pdf":
		from pypdf import PdfReader
		for i, page in enumerate(PdfReader(path).pages, 1):
			t = (page.extract_text() or "").strip()
			if t:
				units.append({"section": f"Page {i}", "page": i, "text": t})
		return units

	if ext == "docx":
		import docx
		from docx.table import Table
		from docx.text.paragraph import Paragraph
		d = docx.Document(path)
		state = {"heading": "", "buf": []}

		def flush():
			if state["buf"]:
				units.append({"section": state["heading"] or "Introduction", "page": None, "text": "\n".join(state["buf"])})
				state["buf"] = []

		for el in d.element.body.iterchildren():
			tag = el.tag.split("}")[-1]
			if tag == "p":
				p = Paragraph(el, d)
				t = p.text.strip()
				if not t:
					continue
				style = (p.style.name if p.style is not None else "").lower()
				if style.startswith(("heading", "title")):
					flush()
					state["heading"] = t
				else:
					state["buf"].append(t)
			elif tag == "tbl":
				flush()
				rows = Table(el, d).rows
				if not rows:
					continue
				header = [c.text.strip() for c in rows[0].cells]
				for r in rows[1:]:
					lines, seen = [], set()
					for h, c in zip(header, r.cells):
						t = c.text.strip()
						if t and t not in seen:  # merged cells repeat their text
							seen.add(t)
							lines.append(f"{h}: {t}" if h and h != t else t)
					if lines:
						first = r.cells[0].text.strip()
						units.append({"section": (first or state["heading"] or "Table")[:140], "page": None, "text": "\n".join(lines)})
		flush()
		return units

	with open(path, encoding="utf-8", errors="ignore") as f:
		heading, buf = "", []
		for line in f:
			if line.startswith("#"):
				if "".join(buf).strip():
					units.append({"section": heading or "Introduction", "page": None, "text": "".join(buf).strip()})
				buf, heading = [], line.lstrip("#").strip()
			else:
				buf.append(line)
		if "".join(buf).strip():
			units.append({"section": heading or "Introduction", "page": None, "text": "".join(buf).strip()})
	return units


def chunk_text(text, size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
	"""Split on paragraphs, pack paragraphs into ~size character chunks with a small overlap."""
	paras = [p.strip() for p in text.replace("\r", "").split("\n") if p.strip()]
	chunks, current = [], ""
	for p in paras:
		while len(p) > size:  # very long paragraph: hard split
			if current:
				chunks.append(current)
				current = ""
			chunks.append(p[:size])
			p = p[size - overlap:]
		if len(current) + len(p) + 1 > size and current:
			chunks.append(current)
			current = current[-overlap:] + "\n" + p
		else:
			current = f"{current}\n{p}" if current else p
	if current.strip():
		chunks.append(current)
	return chunks


# ---------- background job ----------

def index_document(docname):
	"""Background job: (re)build all vectors for one Knowledge Document."""
	from qdrant_client.models import PointStruct
	doc = frappe.get_doc(DOCTYPE, docname)
	try:
		path = frappe.get_doc("File", {"file_url": doc.file}).get_full_path()
		chunks = [{**u, "text": piece} for u in extract_units(path, doc.extension) for piece in chunk_text(u["text"])]
		if not chunks:
			raise ValueError("No readable text found. Scanned PDFs need OCR before upload.")
		client = _qdrant()
		_delete_vectors(client, docname)
		access = _access_payload(doc)
		batch = 64
		for start in range(0, len(chunks), batch):
			part = chunks[start:start + batch]
			# the title and section are embedded with each chunk so a passage keeps its context
			texts = [f"{doc.title} | {c['section']}\n{c['text']}" for c in part]
			vectors, sparse = embed(texts), sparse_embed(texts)
			collection = _ensure_collection(client, len(vectors[0]))
			client.upsert(collection, points=[
				PointStruct(
					id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{docname}:{start + i}")),
					vector={DENSE: v, SPARSE: sv},
					payload={"doc": docname, "title": doc.title, "category": doc.category, "version": doc.version,
						"chunk": start + i, "section": c["section"], "page": c["page"], "text": c["text"], **access},
				) for i, (c, v, sv) in enumerate(zip(part, vectors, sparse))
			])
		doc.db_set({"status": "Indexed", "chunks": len(chunks), "error": ""})
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Knowledge Base indexing failed: {docname}")
		frappe.db.set_value(DOCTYPE, docname, {"status": "Failed", "chunks": 0, "error": str(e)[:500]})
	frappe.db.commit()
	frappe.publish_realtime("kb_document_updated", {"name": docname}, after_commit=True)


def _enqueue(docname):
	frappe.enqueue("surveillance.knowledge_base.index_document", queue="long", timeout=1800,
		docname=docname, enqueue_after_commit=True, job_id=f"kb-index-{docname}", deduplicate=True)


# ---------- API ----------

def _row(d):
	return {
		"id": d.name, "name": d.title, "extension": (d.extension or "").upper(), "version": d.version,
		"category": d.category, "appliedTo": _split(d.applied_to),
		"diseases": _split(d.get("diseases")),
		"regions": _split(d.get("regions")) or [ALL_REGIONS],
		"language": d.get("language") or "English",
		"reviewDate": str(d.review_date) if d.get("review_date") else None,
		"expiryDate": str(d.expiry_date) if d.get("expiry_date") else None,
		"effectiveFrom": str(d.effective_from) if d.get("effective_from") else None,
		"approvalStatus": (d.get("approval_status") or "Draft").lower(),
		"approvedBy": frappe.utils.get_fullname(d.approved_by) if d.get("approved_by") else None,
		"approvedAt": str(d.approved_on) if d.get("approved_on") else None,
		"sizeBytes": cint(d.size_bytes), "status": (d.status or "").lower(), "chunks": cint(d.chunks),
		"error": d.error, "uploadedBy": frappe.utils.get_fullname(d.owner), "uploadedAt": str(d.creation),
	}


@frappe.whitelist()
def list_documents():
	if not (has_capability(CAPABILITY) or has_capability(APPROVE_CAPABILITY)):
		require_capability(CAPABILITY)
	return [_row(d) for d in frappe.get_all(DOCTYPE, fields=["*"], order_by="creation desc")]


@frappe.whitelist(methods=["POST"])
def create_document(file_url, category, applied_to=None, version="v1.0", diseases=None,
		regions=None, language="English", review_date=None, expiry_date=None, effective_from=None):
	"""Register an already uploaded file (via /api/method/upload_file) and queue indexing. Starts as Draft."""
	require_capability(CAPABILITY)
	f = frappe.get_doc("File", {"file_url": file_url})
	ext = (f.file_name.rsplit(".", 1)[-1] if "." in f.file_name else "").lower()
	if ext not in ALLOWED_EXTENSIONS:
		frappe.throw(_("Only PDF, DOCX, TXT and MD files are supported."))
	if cint(f.file_size) > MAX_BYTES:
		frappe.throw(_("File is larger than 25 MB."))
	doc = frappe.get_doc({
		"doctype": DOCTYPE, "title": f.file_name, "file": file_url, "extension": ext,
		"version": version or "v1.0", "category": category, "applied_to": ", ".join(_split(applied_to)) or ALL_ROLES,
		"diseases": _clean_diseases(diseases), "approval_status": "Draft",
		"regions": _clean_regions(regions), "language": language or "English",
		"review_date": review_date or None, "expiry_date": expiry_date or None,
		"effective_from": effective_from or None,
		"size_bytes": cint(f.file_size), "status": "Processing",
	})
	_check_dates(doc)
	doc.insert(ignore_permissions=True)
	f.db_set({"attached_to_doctype": DOCTYPE, "attached_to_name": doc.name})
	_enqueue(doc.name)
	return _row(doc)


@frappe.whitelist(methods=["POST"])
def update_document(name, category=None, applied_to=None, diseases=None, version=None,
		regions=None, language=None, review_date=None, expiry_date=None, effective_from=None):
	"""Edit document details. Everything is copied to Qdrant without re-embedding."""
	require_capability(CAPABILITY)
	doc = frappe.get_doc(DOCTYPE, name)
	if category is not None:
		doc.category = category
	if version is not None:
		doc.version = version
	if applied_to is not None:
		doc.applied_to = ", ".join(_split(applied_to)) or ALL_ROLES
	if diseases is not None:
		doc.diseases = _clean_diseases(diseases)
	if regions is not None:
		doc.regions = _clean_regions(regions)
	if language is not None:
		doc.language = language or "English"
	if review_date is not None:
		doc.review_date = review_date or None
	if expiry_date is not None:
		doc.expiry_date = expiry_date or None
	if effective_from is not None:
		doc.effective_from = effective_from or None
	_check_dates(doc)
	doc.save(ignore_permissions=True)
	_sync_access(doc)
	return _row(doc)


@frappe.whitelist(methods=["POST"])
def set_approval(name, status):
	"""approve, retire or send back to draft. Only Approved documents are searchable."""
	require_capability(APPROVE_CAPABILITY)
	if status not in APPROVAL_STATUSES:
		frappe.throw(_("Status must be one of: {0}").format(", ".join(APPROVAL_STATUSES)))
	doc = frappe.get_doc(DOCTYPE, name)
	if status == "Approved" and doc.status != "Indexed":
		frappe.throw(_("Only an indexed document can be approved. Wait for indexing to finish."))
	doc.approval_status = status
	if status == "Approved":
		doc.approved_by = frappe.session.user
		doc.approved_on = now_datetime()
	doc.save(ignore_permissions=True)
	_sync_access(doc)
	return _row(doc)


@frappe.whitelist(methods=["POST"])
def reindex_document(name):
	require_capability(CAPABILITY)
	frappe.db.set_value(DOCTYPE, name, {"status": "Processing", "chunks": 0, "error": ""})
	_enqueue(name)
	return _row(frappe.get_doc(DOCTYPE, name))

def reindex_all():
	"""Queue indexing for every Knowledge Document. Use after Qdrant data is lost or the model changes.

	bench --site <site> execute surveillance.knowledge_base.reindex_all
	"""
	names = frappe.get_all(DOCTYPE, pluck="name")
	for name in names:
		frappe.db.set_value(DOCTYPE, name, {"status": "Processing", "chunks": 0, "error": ""})
		_enqueue(name)
	frappe.db.commit()
	print(f"Queued {len(names)} documents for indexing")
	return len(names)


@frappe.whitelist(methods=["POST"])
def delete_document(name):
	require_capability(CAPABILITY)
	doc = frappe.get_doc(DOCTYPE, name)
	try:
		_delete_vectors(_qdrant(), name)
	except Exception:
		frappe.log_error(title=f"Knowledge Base: could not delete vectors for {name}")
	file_name = frappe.db.get_value("File", {"file_url": doc.file})
	doc.delete(ignore_permissions=True)
	if file_name:
		frappe.delete_doc("File", file_name, ignore_permissions=True)
	return {"deleted": name}


# ---------- search contract ----------
#
# GET /api/method/surveillance.knowledge_base.search
#     query     required, the question (English or Kiswahili)
#     audience  role or comma-separated roles of the person asking (chatbot service / editors only)
#     region    region or comma-separated regions (chatbot service / editors only); others use their assigned region
#     language  "English" or "Kiswahili": passages in that language are ranked first when relevant
#     disease   disease key filter (see get_disease_vocabulary); category; limit (1-20, default 5)
#     include_drafts=1  editors only
# Returns {"query", "count", "results": [...], "detected_disease", "score_range", "confidence_thresholds", "took_ms"}
# Each result: id, score (cosine similarity 0-1, higher = closer), confidence (high|medium|low), text (verbatim),
#     title, doc, version, category, section, page, chunk, diseases (always a list), regions (list), language,
#     review_date, expiry_date, approval_status.
# Errors: empty query or unknown audience/region -> 417; no permission -> 403; passage not found -> 404;
#     knowledge base unavailable -> 503. Zero matches -> 200 with "results": [].

def _thresholds():
	return {"high": float(_conf("kb_score_high", 0.60)), "low": float(_conf("kb_score_low", 0.45))}


def _confidence(score, t):
	return "high" if score >= t["high"] else ("medium" if score >= t["low"] else "low")


def _access_context(audience=None, region=None, include_drafts=0, on_behalf_of=None, preview=0):
	"""Who is asking and what they may see (surveillance.kb_access). Raises 403/417 on bad requests."""
	return kb_access.resolve(on_behalf_of=on_behalf_of, audience=audience, region=region,
		include_drafts=include_drafts, preview=preview)


class _Audit:
	"""Collects what one request did and writes it to the Chatbot Query Log (surveillance.chatbot_log)."""

	def __init__(self, route, level, query, language=None, correlation_id=None, channel=None):
		from surveillance import chatbot_log
		self.log = chatbot_log
		self.started = time.monotonic()
		# a correlation id from the caller links this record to the conversation (e.g. a WhatsApp request id)
		self.correlation_id = (str(correlation_id)[:64] if correlation_id else None) or chatbot_log.new_correlation_id()
		self.name = None
		self.fields = {
			"route": route, "level": level, "query_text": (query or "").strip(), "language": language,
			"correlation_id": self.correlation_id, "channel": channel if channel in chatbot_log.CHANNELS else "Web",
			"caller": frappe.session.user, "user": frappe.session.user if frappe.session.user != "Guest" else None,
			"access_policy_version": ACCESS_POLICY_VERSION, "retrieval_config": retrieval_config(),
		}

	def context(self, ctx):
		self.fields.update({
			"user": ctx.get("user"), "user_ref": ctx.get("user_ref"), "actor_class": ctx.get("actor_class"),
			"access_policy_version": ctx.get("policy_version") or ACCESS_POLICY_VERSION,
			"access_decision": "ALLOW",
			"audience_roles": "ALL (editor)" if ctx["roles"] is None else ", ".join(ctx["roles"]) or "-",
			"scope": "ALL" if ctx["regions"] is None else ", ".join(ctx["regions"]),
			"preview": 1 if ctx.get("preview") else 0,
		})

	def _ms(self):
		return int((time.monotonic() - self.started) * 1000)

	def claimed(self, on_behalf_of):
		"""Before the decision: record who the caller said the asker was."""
		if on_behalf_of:
			self.fields["user_ref"] = str(on_behalf_of)[:140]
			self.fields["user"] = on_behalf_of if frappe.db.exists("User", on_behalf_of) else None

	def denied(self, exc):
		code = getattr(exc, "code", None) or ("INVALID_REQUEST" if isinstance(exc, frappe.ValidationError) else "DENIED")
		self.name = self.log.log_denied(**self.fields, deny_reason_code=code, error=str(exc), latency_ms=self._ms())

	def failed(self, exc):
		self.name = self.log.log(**self.fields, outcome="Error", error=str(exc), latency_ms=self._ms())

	def done(self, **fields):
		self.fields.update(fields)
		self.fields.setdefault("access_decision", "ALLOW")
		self.name = self.log.log(**self.fields, latency_ms=self._ms())
		return self.name


def _passage_trace(scored):
	"""[(rank_score, dense_score, point)] -> compact list for the log."""
	out = []
	for rs, dense, p, shown in scored:
		pl = p.payload
		out.append({"id": str(p.id), "doc": pl.get("doc"), "version": pl.get("version"), "section": pl.get("section"),
			"rank_score": round(float(rs), 3) if rs is not None else None,
			"score": round(float(dense), 3) if dense is not None else None, "shown": bool(shown)})
	return out


def _filter(ctx, category=None, disease=None):
	from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
	from qdrant_client.models import Range
	must = []
	if ctx["approved_only"]:
		must.append(FieldCondition(key="approval_status", match=MatchValue(value="Approved")))
		# effective dates before retrieval: out-of-date content never reaches scoring (R62)
		now = _day(today())
		must.append(FieldCondition(key="valid_from", range=Range(lte=now)))
		must.append(FieldCondition(key="valid_to", range=Range(gte=now)))
	if ctx["roles"] is not None:
		must.append(FieldCondition(key="applied_to", match=MatchAny(any=[ALL_ROLES] + ctx["roles"])))
	if ctx["regions"] is not None:
		must.append(FieldCondition(key="regions", match=MatchAny(any=[ALL_REGIONS] + ctx["regions"])))
	if category:
		must.append(FieldCondition(key="category", match=MatchValue(value=category)))
	if disease:
		must.append(FieldCondition(key="diseases", match=MatchValue(value=disease)))
	return Filter(must=must) if must else None


def _visible(payload, ctx):
	"""Same rules as _filter, for a single passage fetched by id."""
	if ctx["approved_only"] and payload.get("approval_status") != "Approved":
		return False
	if ctx["approved_only"] and _expired(payload):
		return False
	if ctx["roles"] is not None and not ({ALL_ROLES, *ctx["roles"]} & set(payload.get("applied_to") or [ALL_ROLES])):
		return False
	if ctx["regions"] is not None and not ({ALL_REGIONS, *ctx["regions"]} & set(payload.get("regions") or [ALL_REGIONS])):
		return False
	return not _expired(payload)


def _expired(payload):
	"""Second check after retrieval (the Qdrant filter already excludes these)."""
	now = _day(today())
	if payload.get("valid_to") is not None or payload.get("valid_from") is not None:
		return not (cint(payload.get("valid_from")) <= now <= cint(payload.get("valid_to") or OPEN_END))
	return bool(payload.get("expiry_date")) and payload["expiry_date"] < today()


def _result(point_id, score, p, t):
	return {
		"id": str(point_id),
		"score": round(float(score), 3),
		"confidence": _confidence(float(score), t),
		"text": p.get("text"),
		"title": p.get("title"),
		"doc": p.get("doc"),
		"version": p.get("version"),
		"category": p.get("category"),
		"section": p.get("section"),
		"page": p.get("page"),
		"chunk": p.get("chunk"),
		"diseases": list(p.get("diseases") or []),
		"regions": list(p.get("regions") or [ALL_REGIONS]),
		"language": p.get("language") or "English",
		"review_date": p.get("review_date"),
		"expiry_date": p.get("expiry_date"),
		"approval_status": p.get("approval_status"),
	}


def _vocabulary():
	meta = frappe.get_meta("Alert Threshold Config")
	fields = ["name", "disease_name"] + (["synonyms"] if meta.has_field("synonyms") else [])
	out = []
	for d in frappe.get_all("Alert Threshold Config", filters={"is_active": 1}, fields=fields):
		out.append({"key": d.name, "name": d.disease_name, "synonyms": _split(d.get("synonyms"))})
	return out


def _detect_disease(query):
	"""Find a disease named in the question by key, name or synonym (e.g. 'kipindupindu' -> awd-cholera)."""
	text = query.lower()
	for d in _vocabulary():
		for term in [d["key"], d["name"], *d["synonyms"]]:
			term = (term or "").strip().lower()
			if len(term) >= 3 and re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
				return d
	return None


def _client():
	try:
		client = _qdrant()
		client.get_collections()
		return client
	except Exception:
		frappe.log_error(title="Knowledge Base: Qdrant unreachable")
		frappe.throw(_("The knowledge base is temporarily unavailable. Please try again shortly."), KBUnavailable)


def _retrieve(query, ctx, category=None, disease=None, language=None, limit=CONTEXT_PASSAGES):
	"""Hybrid search + re-rank. Returns (detected_disease, [(rank_score, point)]) best first."""
	from qdrant_client.models import Fusion, FusionQuery, Prefetch
	detected = _detect_disease(query)
	expanded = f"{query} ({detected['name']})" if detected else query  # e.g. "kipindupindu" -> cholera
	client = _client()
	if not client.collection_exists(_collection()):
		return detected, []
	flt = _filter(ctx, category, disease)
	try:
		hits = client.query_points(_collection(),
			prefetch=[
				Prefetch(query=embed([expanded])[0], using=DENSE, filter=flt, limit=CANDIDATES),
				Prefetch(query=sparse_embed([expanded], query=True)[0], using=SPARSE, filter=flt, limit=CANDIDATES),
			],
			query=FusionQuery(fusion=Fusion.RRF), limit=CANDIDATES, with_payload=True).points
	except Exception:
		frappe.log_error(title="Knowledge Base: search failed")
		frappe.throw(_("The knowledge base is temporarily unavailable. Please try again shortly."), KBUnavailable)

	hits = [h for h in hits if not _expired(h.payload)]
	if not hits:
		return detected, []
	reranker = _rerank_model()
	if reranker:
		import math
		# cross-encoder logits -> 0-1 relevance
		scores = [1 / (1 + math.exp(-float(x))) for x in reranker.rerank(query, [h.payload.get("text") or "" for h in hits])]
	else:
		scores = [h.score for h in hits]
	ranked = []
	for h, sc in zip(hits, scores):
		boost = LANGUAGE_BOOST if language and h.payload.get("language") == language else 0
		ranked.append((float(sc) + boost, h))
	ranked.sort(key=lambda x: -x[0])

	# keep the best passages, at most 2 per document section so one long section can't crowd out the rest
	out, per_section = [], {}
	for sc, h in ranked:
		key = (h.payload.get("doc"), h.payload.get("section"))
		if per_section.get(key, 0) >= 2:
			continue
		per_section[key] = per_section.get(key, 0) + 1
		out.append((sc, h))
		if len(out) >= limit:
			break
	return detected, out


def _dense_scores(query, points):
	"""Cosine similarity (0-1) of each passage to the question, for the confidence label."""
	import numpy as np
	q = np.array(embed([query])[0])
	vecs = np.array(embed([p.payload.get("text") or "" for p in points]))
	sims = vecs @ q / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(q) + 1e-9)
	return [float(x) for x in sims]


@frappe.whitelist()
def search(query, limit=5, category=None, disease=None, audience=None, region=None, language=None, include_drafts=0,
		correlation_id=None, channel=None, on_behalf_of=None, preview=0):
	"""Best passages for a question (hybrid search + re-rank), returned verbatim. Used by the chatbot.
	Every call, allowed or denied, is written to the Chatbot Query Log (level Retrieval)."""
	started = time.monotonic()
	audit = _Audit("kb_search", "Retrieval", query, language, correlation_id, channel or "API")
	audit.claimed(on_behalf_of)
	try:
		ctx = _access_context(audience, region, include_drafts, on_behalf_of, preview)
		query = (query or "").strip()
		if not query:
			frappe.throw(_("Query is empty."))
		if language and language not in LANGUAGES:
			frappe.throw(_("Language must be one of: {0}").format(", ".join(LANGUAGES)))
	except (frappe.PermissionError, frappe.ValidationError) as e:
		audit.denied(e)
		raise
	audit.context(ctx)
	limit = max(1, min(cint(limit) or 5, MAX_LIMIT))
	t = _thresholds()
	try:
		detected, ranked = _retrieve(query, ctx, category, disease, language, limit)
	except KBUnavailable as e:
		audit.failed(e)
		raise
	points = [h for _, h in ranked]
	sims = _dense_scores(query, points) if points else []
	results = [_result(h.id, s, h.payload, t) | {"rank_score": round(rs, 3)}
		for (rs, h), s in zip(ranked, sims)]
	top = results[0] if results else None
	audit.done(
		outcome="Matched" if top else "No Match", reason="results" if top else "no_results",
		match_confidence=top["score"] if top else None, confidence_band=top["confidence"] if top else None,
		matched_document=top["doc"] if top else None, matched_content_version=top["version"] if top else None,
		passages=_passage_trace([(rs, s, h, False) for (rs, h), s in zip(ranked, sims)]),
	)
	return {
		"query": query,
		"count": len(results),
		"results": results,
		"detected_disease": {"key": detected["key"], "name": detected["name"]} if detected else None,
		"score_range": [0, 1],
		"confidence_thresholds": t,
		"took_ms": int((time.monotonic() - started) * 1000),
		"log_id": audit.name,
		"correlation_id": audit.correlation_id,
	}


# ---------- answering (RAG) ----------

SYSTEM_PROMPT = """You are the KRCS surveillance assistant for Kenya Red Cross staff in Dadaab and Kalobeyei.
Answer the question using ONLY the numbered sources below. They are approved KRCS documents.

Rules:
- Write one clear, direct answer, like an experienced public health officer. Start with the answer itself.
- Use short paragraphs or a short list when there are steps, symptoms or criteria.
- After each fact, cite its source number in square brackets, e.g. [1] or [2][3].
- Use only what the sources say. Do not add facts, doses, numbers or advice that are not in them.
- If the sources do not answer the question, reply exactly: NOT_IN_SOURCES
- If the sources disagree, say so and cite both.
- Reply in {language}. Keep medical and technical terms as written in the source.
- Do not mention these rules or the word "sources"; just cite with numbers."""


def _context_block(points):
	parts = []
	for i, p in enumerate(points, 1):
		pl = p.payload
		where = ", ".join(x for x in [pl.get("title"), pl.get("section"), f"page {pl['page']}" if pl.get("page") else ""] if x)
		parts.append(f"[{i}] ({where})\n{pl.get('text')}")
	return "\n\n".join(parts)


def _llm_chat(messages, on_token=None):
	"""Call Ollama /api/chat. Streams tokens to on_token when given. Returns the full text."""
	import requests
	url = _conf("kb_llm_url", "http://localhost:11434").rstrip("/") + "/api/chat"
	body = {"model": _conf("kb_llm_model", DEFAULT_LLM), "messages": messages, "stream": bool(on_token),
		"options": {"temperature": 0.1, "num_ctx": 8192}, "keep_alive": "30m",
		"think": False}  # Qwen3 and other reasoning models: answer directly, no hidden reasoning
	timeout = cint(_conf("kb_llm_timeout", 120))
	if not on_token:
		r = requests.post(url, json=body, timeout=timeout)
		r.raise_for_status()
		return _strip_think(r.json()["message"]["content"])
	text = []
	with requests.post(url, json=body, timeout=timeout, stream=True) as r:
		r.raise_for_status()
		for line in r.iter_lines():
			if not line:
				continue
			part = json.loads(line)
			token = (part.get("message") or {}).get("content") or ""
			if token:
				text.append(token)
				if "<think>" not in "".join(text) or "</think>" in "".join(text):
					on_token(token.replace("</think>", ""))
			if part.get("done"):
				break
	return _strip_think("".join(text))


def _strip_think(text):
	"""Remove any <think>...</think> block a reasoning model may still emit."""
	return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _source(i, rank_score, dense, p, t):
	pl = p.payload
	return {"n": i, "id": str(p.id), "title": pl.get("title"), "doc": pl.get("doc"), "section": pl.get("section"),
		"page": pl.get("page"), "version": pl.get("version"), "category": pl.get("category"),
		"text": pl.get("text"), "confidence": _confidence(dense, t), "score": round(dense, 3)}


def _history_messages(history):
	"""Last few turns for follow-up questions. history: JSON list of {role, content}."""
	if isinstance(history, str):
		history = frappe.parse_json(history) if history.strip() else []
	out = []
	for m in (history or [])[-6:]:
		if m.get("role") in ("user", "assistant") and m.get("content"):
			out.append({"role": m["role"], "content": str(m["content"])[:2000]})
	return out


@frappe.whitelist(methods=["POST"])
def ask(query, language=None, history=None, stream_id=None, category=None, disease=None,
		audience=None, region=None, include_drafts=0, correlation_id=None, channel=None, on_behalf_of=None, preview=0):
	"""One grounded answer to a question, with the sources it used.

	stream_id: when given, tokens are pushed live to this user over realtime event "kb_answer"
	           as {stream_id, delta} and finally {stream_id, done: true}.
	Returns {query, answer, mode, sources, used_sources, detected_disease, language, took_ms}
	mode: "answer" (LLM answer) | "not_found" | "passages" (LLM unavailable: best passages only)
	"""
	started = time.monotonic()
	audit = _Audit("kb_ask", "Conversation", query, language, correlation_id, channel or "Web")
	audit.claimed(on_behalf_of)
	try:
		ctx = _access_context(audience, region, include_drafts, on_behalf_of, preview)
		query = (query or "").strip()
		if not query:
			frappe.throw(_("Query is empty."))
	except (frappe.PermissionError, frappe.ValidationError) as e:
		audit.denied(e)
		raise
	audit.context(ctx)
	language = language if language in LANGUAGES else "English"
	t = _thresholds()
	hist = _history_messages(history)

	# short follow-ups ("what about children?") are searched together with the previous question
	last_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
	search_q = f"{last_user} {query}" if last_user and len(query.split()) <= 6 else query
	try:
		detected, ranked = _retrieve(search_q, ctx, category, disease, language, CONTEXT_PASSAGES)
	except KBUnavailable as e:
		audit.failed(e)
		raise

	def push(payload):
		if stream_id:
			frappe.publish_realtime("kb_answer", {"stream_id": stream_id, **payload}, user=frappe.session.user)

	def finish(answer, mode, sources, used, trace=None, **log_fields):
		top = next((s for s in sources if s["n"] in used), None) if used else None
		outcome = {"answer": "Matched", "passages": "Matched", "not_found": "No Match"}.get(mode, "Matched")
		audit.done(outcome=outcome, reason=mode, answer=answer, answer_mode=mode,
			match_confidence=top["score"] if top else None, confidence_band=top["confidence"] if top else None,
			matched_document=top["doc"] if top else None, matched_content_version=top["version"] if top else None,
			passages=trace, **log_fields)
		push({"done": True, "mode": mode, "log_id": audit.name})
		return {"query": query, "answer": answer, "mode": mode, "sources": sources, "used_sources": used,
			"detected_disease": {"key": detected["key"], "name": detected["name"]} if detected else None,
			"language": language, "took_ms": int((time.monotonic() - started) * 1000),
			"log_id": audit.name, "correlation_id": audit.correlation_id}

	min_score = float(_conf("kb_min_rerank_score", 0.15))
	if not ranked or (_rerank_model() and ranked[0][0] < min_score):
		answer = NOT_FOUND[language]
		push({"delta": answer})
		return finish(answer, "not_found", [], [], _passage_trace([(rs, None, h, False) for rs, h in ranked]))

	points = [h for _, h in ranked]
	dense = _dense_scores(query, points)
	sources = [_source(i, rs, d, p, t) for i, ((rs, p), d) in enumerate(zip(ranked, dense), 1)]
	trace = _passage_trace([(rs, d, p, True) for (rs, p), d in zip(ranked, dense)])

	messages = [{"role": "system", "content": SYSTEM_PROMPT.format(language=language)}, *hist,
		{"role": "user", "content": f"Sources:\n\n{_context_block(points)}\n\nQuestion: {query}"}]

	buffer = {"text": "", "held": True}

	def on_token(tok):
		# hold the first few characters so a NOT_IN_SOURCES reply is never streamed to the user
		buffer["text"] += tok
		if buffer["held"]:
			if len(buffer["text"]) < 16 and "NOT_IN_SOURCES".startswith(buffer["text"].strip()[:14]):
				return
			buffer["held"] = False
			push({"delta": buffer["text"]})
		else:
			push({"delta": tok})

	try:
		answer = _llm_chat(messages, on_token if stream_id else None).strip()
	except Exception as e:
		frappe.log_error(title="Knowledge Base: LLM unavailable, returned passages only")
		answer = "\n\n".join(f"{s['text']} [{s['n']}]" for s in sources[:2])
		push({"delta": answer})
		return finish(answer, "passages", sources, [s["n"] for s in sources[:2]], trace, error=f"LLM: {e}"[:300])

	if "NOT_IN_SOURCES" in answer:
		answer = NOT_FOUND[language]
		push({"delta": answer})
		return finish(answer, "not_found", [], [], trace)
	if buffer["held"] and stream_id:
		push({"delta": answer})

	used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 0 < int(n) <= len(sources)})
	return finish(answer, "answer", sources, used or [s["n"] for s in sources[:1]], trace)


@frappe.whitelist()
def llm_status():
	"""Health check for the answer model: is Ollama reachable and is the model pulled?"""
	require_capability(CAPABILITY)
	import requests
	url = _conf("kb_llm_url", "http://localhost:11434").rstrip("/")
	model = _conf("kb_llm_model", DEFAULT_LLM)
	try:
		tags = requests.get(f"{url}/api/tags", timeout=5).json().get("models", [])
		names = [m.get("name") for m in tags]
		return {"reachable": True, "model": model, "pulled": model in names, "available": names}
	except Exception as e:
		return {"reachable": False, "model": model, "error": str(e)[:200]}


@frappe.whitelist()
def get_passage(id, audience=None, region=None, correlation_id=None, channel=None, on_behalf_of=None):
	"""Fetch one passage by the id returned from search, with the same access rules. Logged (level Retrieval)."""
	audit = _Audit("kb_passage", "Retrieval", f"passage:{id}", None, correlation_id, channel or "API")
	audit.claimed(on_behalf_of)
	try:
		ctx = _access_context(audience, region, on_behalf_of=on_behalf_of)
	except (frappe.PermissionError, frappe.ValidationError) as e:
		audit.denied(e)
		raise
	audit.context(ctx)
	client = _client()
	points = []
	if client.collection_exists(_collection()):
		try:
			points = client.retrieve(_collection(), ids=[id], with_payload=True)
		except Exception:
			points = []  # malformed id
	if not points or not _visible(points[0].payload, ctx):
		audit.done(outcome="Restricted" if points else "No Match", reason="not_visible" if points else "not_found",
			access_decision="DENY" if points else "ALLOW", deny_reason_code="NOT_VISIBLE" if points else None)
		frappe.throw(_("Passage not found or not available for this audience."), frappe.DoesNotExistError)
	pl = points[0].payload
	audit.done(outcome="Matched", reason="passage", matched_document=pl.get("doc"),
		matched_content_version=pl.get("version"), passages=_passage_trace([(None, None, points[0], True)]))
	return _result(points[0].id, 1.0, pl, _thresholds()) | {"score": None, "confidence": None, "log_id": audit.name}


@frappe.whitelist()
def get_disease_vocabulary():
	"""Disease keys, display names and synonyms (editable in Alert Threshold Config) for the chatbot."""
	if not (has_capability(CAPABILITY) or has_capability(SEARCH_CAPABILITY)):
		require_capability(SEARCH_CAPABILITY)
	return _vocabulary()


def retire_expired():
	"""Daily: move Approved documents past their expiry date (or review date, when kb_hide_after_review_date) to
	Retired. Search already hides them from the day after, through the valid_to filter."""
	# "is set" matters: Frappe compiles `date < today` to ifnull(date, '0001-01-01') < today, so without it every
	# document with no expiry / review date would be retired (the pre-November code had this bug for expiry_date).
	ends = ["expiry_date"] + (["review_date"] if hide_after_review() else [])
	names = set()
	for field in ends:
		names |= set(frappe.get_all(DOCTYPE, pluck="name", filters=[["approval_status", "=", "Approved"],
			[field, "is", "set"], [field, "<", today()]]))
	for name in sorted(names):
		doc = frappe.get_doc(DOCTYPE, name)
		why = "expiry date" if doc.expiry_date and getdate(doc.expiry_date) < getdate(today()) else "review date"
		doc.approval_status = "Retired"
		doc.save(ignore_permissions=True)
		doc.add_comment("Comment", f"Retired automatically: {why} passed.")
		_sync_access(doc)
	frappe.db.commit()
	return len(names)


REVIEW_NOTICE_DAYS = (30, 7)


def notify_upcoming_reviews():
	"""Daily: remind the uploader and approver 30 and 7 days before a document's review or expiry date (H.9)."""
	from frappe.utils import add_days
	sent = 0
	for days in REVIEW_NOTICE_DAYS:
		day = add_days(today(), days)
		for field in ("review_date", "expiry_date"):
			for d in frappe.get_all(DOCTYPE, filters={"approval_status": "Approved", field: day},
					fields=["name", "title", "owner", "approved_by"]):
				what = _("review") if field == "review_date" else _("expiry")
				for u in {d.owner, d.approved_by} - {None, "Administrator"}:
					frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert",
						"document_type": DOCTYPE, "document_name": d.name,
						"subject": _("Knowledge document {0}: {1} due in {2} days").format(d.title, what, days),
					}).insert(ignore_permissions=True)
					sent += 1
	frappe.db.commit()
	return sent


def sync_all_payloads():
	"""Copy current access fields (incl. effective dates) onto every chunk. Patch after upgrade; also safe any time.
	bench --site <site> execute surveillance.knowledge_base.sync_all_payloads"""
	names = frappe.get_all(DOCTYPE, pluck="name")
	try:
		client = _qdrant()
		if client.collection_exists(_collection()):
			_ensure_collection(client, 0)
	except Exception:
		frappe.log_error(title="Knowledge Base: payload sync could not reach Qdrant")
		return 0
	for name in names:
		_sync_access(frappe.get_doc(DOCTYPE, name))
	return len(names)
