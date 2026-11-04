"""Knowledge Base hardening and operations (plan KB-12, KB-16, KB-19, KB-20, D2; SRS R82, R86, R89, R90).

rate limits      per user per minute on search / ask / get_passage / the chat gateway (kb_rate_per_minute,
                 default 30; the chatbot service account kb_service_rate_per_minute, default 600)
upload checks    the bytes must match the extension: PDF magic, DOCX zip with word/document.xml and a capped
                 uncompressed size (zip bombs), TXT/MD valid UTF-8 without NUL bytes
health()         Qdrant, models with their licences, LLM, chatbot reload, index reconciliation, retrieval config
reconcile()      daily: every Approved/Indexed document has its chunks in Qdrant; orphan vectors are removed;
                 missing ones are re-queued
language tags    per chunk (English / Kiswahili), so a mixed-language document ranks the right passages
"""
import re
import zipfile

import frappe
from frappe import _
from frappe.utils import cint

from surveillance.capabilities import has_capability, require_capability

DOCX_MAX_UNCOMPRESSED = 100 * 1024 * 1024
# licences of the default models (D2: the re-ranker is non-commercial; KRCS governance must accept or replace it)
LICENCES = {
	"paraphrase-multilingual-MiniLM-L12-v2": ("Apache-2.0", True),
	"bm25": ("Apache-2.0", True),
	"jina-reranker-v2-base-multilingual": ("CC-BY-NC-4.0", False),
	"bge-reranker-v2-m3": ("Apache-2.0", True),
	"qwen3": ("Apache-2.0", True),
	"off": ("-", True),
}


class TooManyRequests(frappe.ValidationError):
	http_status_code = 429
	code = "RATE_LIMITED"


# ---------- rate limits ----------

def throttle(bucket):
	"""Count one call for this user in the current minute; refuse with 429 above the limit."""
	user = frappe.session.user
	if user == "Administrator" or frappe.flags.in_test and not frappe.flags.kb_test_rate_limit:
		return
	limit = cint(frappe.conf.get("kb_service_rate_per_minute") or 600) if has_capability("kb_service") \
		else cint(frappe.conf.get("kb_rate_per_minute") or 30)
	if limit <= 0:
		return
	import time
	key = f"kb_rate:{bucket}:{user}:{int(time.time() // 60)}"
	cache = frappe.cache()
	count = cache.incrby(key, 1)
	if count == 1:
		cache.expire(key, 120)
	if count > limit:
		raise TooManyRequests(_("Too many questions in a short time. Please wait a minute and try again."))


# ---------- upload checks ----------

def check_upload(path, ext):
	"""Raise ValidationError unless the file content matches its extension."""
	with open(path, "rb") as f:
		head = f.read(8)
	if ext == "pdf":
		if not head.startswith(b"%PDF-"):
			frappe.throw(_("This file is not a valid PDF."))
	elif ext == "docx":
		if not head.startswith(b"PK\x03\x04"):
			frappe.throw(_("This file is not a valid Word (.docx) document."))
		try:
			with zipfile.ZipFile(path) as z:
				names = z.namelist()
				if "word/document.xml" not in names:
					frappe.throw(_("This file is not a valid Word (.docx) document."))
				if sum(i.file_size for i in z.infolist()) > DOCX_MAX_UNCOMPRESSED:
					frappe.throw(_("This Word document is too large once uncompressed."))
		except zipfile.BadZipFile:
			frappe.throw(_("This file is not a valid Word (.docx) document."))
	elif ext in ("txt", "md"):
		with open(path, "rb") as f:
			data = f.read()
		if b"\x00" in data:
			frappe.throw(_("This text file contains binary data."))
		try:
			data.decode("utf-8")
		except UnicodeDecodeError:
			frappe.throw(_("Text files must be UTF-8."))


# ---------- language per chunk ----------

_SW = set("na ya wa kwa ni la za katika kama au hii huu hiyo pia lakini kuwa ana wana mtoto watoto mgonjwa "
	"ugonjwa dalili afya maji safi homa kuhara tafadhali nini gani wapi lini sana bila baada kabla hadi".split())
_EN = set("the and of to in is for with on that are be as by this or if a an from at not should".split())
_WORD = re.compile(r"[a-zA-Z']+")


def chunk_language(text, default="English"):
	words = [w.lower() for w in _WORD.findall(text or "")]
	if len(words) < 6:
		return default
	sw = sum(w in _SW for w in words)
	en = sum(w in _EN for w in words)
	if sw > en * 1.2 and sw >= 3:
		return "Kiswahili"
	if en > sw * 1.2 and en >= 3:
		return "English"
	return default


# ---------- health and reconciliation ----------

def _licence(model):
	name = (model or "").split("/")[-1].lower()
	for key, (lic, ok) in LICENCES.items():
		if key.lower() in name:
			return {"model": model, "licence": lic, "approved_for_use": ok}
	return {"model": model, "licence": "unknown", "approved_for_use": False}


INDEX_JOB_TIMEOUT = 1800  # seconds; matches knowledge_base._enqueue


def reconcile(fix=True):
	"""Compare chunk counts in Qdrant with the database. Missing -> re-index; orphans -> delete."""
	from surveillance import knowledge_base as kb
	client = kb._qdrant()
	result = {"checked": 0, "missing": [], "mismatch": [], "orphans": [], "requeued": [], "deleted": []}
	if not client.collection_exists(kb._collection()):
		result["error"] = "collection does not exist"
		return result
	docs = {d.name: d for d in frappe.get_all(kb.DOCTYPE, fields=["name", "status", "chunks", "approval_status", "modified"])}
	# A worker that dies mid-job leaves a document on Processing for good. Well past the job timeout, queue it again.
	stuck_before = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-2 * INDEX_JOB_TIMEOUT)
	result["stuck"] = sorted(n for n, d in docs.items() if d.status == "Processing"
		and frappe.utils.get_datetime(d.modified) < stuck_before)
	counts = {}
	offset = None
	while True:
		points, offset = client.scroll(kb._collection(), limit=1000, offset=offset, with_payload=["doc"],
			with_vectors=False)
		for p in points:
			counts[p.payload.get("doc")] = counts.get(p.payload.get("doc"), 0) + 1
		if offset is None:
			break
	for name, d in docs.items():
		if d.status != "Indexed":
			continue
		result["checked"] += 1
		have = counts.get(name, 0)
		if have == 0:
			result["missing"].append(name)
		elif have != cint(d.chunks):
			result["mismatch"].append({"doc": name, "db": cint(d.chunks), "qdrant": have})
	result["orphans"] = sorted(n for n in counts if n not in docs)
	if fix:
		for name in result["missing"] + [m["doc"] for m in result["mismatch"]] + result["stuck"]:
			frappe.db.set_value(kb.DOCTYPE, name, {"status": "Processing"})
			kb._enqueue(name)
			result["requeued"].append(name)
		for name in result["orphans"]:
			kb._delete_vectors(client, name)
			result["deleted"].append(name)
		frappe.db.commit()
	frappe.cache().set_value("kb_last_reconcile", {**result, "at": str(frappe.utils.now_datetime())})
	if result["missing"] or result["mismatch"] or result["orphans"] or result["stuck"]:
		frappe.log_error(title="Knowledge Base: index reconciliation found differences", message=frappe.as_json(result))
	return result


def daily_reconcile():
	try:
		reconcile(fix=True)
	except Exception:
		frappe.log_error(title="Knowledge Base: reconciliation failed")


@frappe.whitelist()
def health():
	"""One view of everything the Knowledge Base depends on (KB-12). Editors and approvers only."""
	from surveillance import knowledge_base as kb
	if not (has_capability(kb.CAPABILITY) or has_capability(kb.APPROVE_CAPABILITY)):
		require_capability(kb.CAPABILITY)
	out = {"retrieval_config": kb.retrieval_config(), "access_policy": kb.ACCESS_POLICY_VERSION}
	try:
		client = kb._qdrant()
		exists = client.collection_exists(kb._collection())
		info = client.get_collection(kb._collection()) if exists else None
		out["qdrant"] = {"reachable": True, "collection": kb._collection(), "exists": exists,
			"points": getattr(info, "points_count", None) if info else 0,
			"api_key": bool(frappe.conf.get("qdrant_api_key")),
			"tls": str(frappe.conf.get("qdrant_url") or "").startswith("https")}
	except Exception as e:
		out["qdrant"] = {"reachable": False, "error": str(e)[:200]}
	models = {
		"embedding": kb._conf("kb_embedding_model", kb.DEFAULT_MODEL),
		"sparse": kb._conf("kb_sparse_model", kb.DEFAULT_SPARSE),
		"reranker": kb._conf("kb_reranker_model", kb.DEFAULT_RERANKER),
		"llm": kb._conf("kb_llm_model", kb.DEFAULT_LLM),
	}
	out["models"] = {k: _licence(v) for k, v in models.items()}
	out["search_service"] = kb.search_service_status()
	try:
		out["llm"] = kb.llm_status()
	except Exception as e:
		out["llm"] = {"reachable": False, "error": str(e)[:200]}
	out["documents"] = {s: frappe.db.count(kb.DOCTYPE, {"approval_status": s}) for s in kb.APPROVAL_STATUSES}
	out["documents"]["failed"] = frappe.db.count(kb.DOCTYPE, {"status": "Failed"})
	out["last_reconcile"] = frappe.cache().get_value("kb_last_reconcile")
	out["chatbot_last_reload"] = frappe.cache().get_value("chatbot_last_reload")
	out["warnings"] = [f"{k}: {v['model']} is {v['licence']}; needs KRCS open-source governance approval (D2)"
		for k, v in out["models"].items() if not v["approved_for_use"]]
	if not out.get("qdrant", {}).get("api_key"):
		out["warnings"].append("Qdrant has no API key configured (use a key and TLS or a private network in production)")
	service = out["search_service"]
	if not service["reachable"]:
		out["warnings"].append(f"The search service at {service['url']} is not reachable ({service['error']}): searches will fail")
	else:
		if not service["models_match"]:
			out["warnings"].append("The search service runs different models from this site: searches will fail until they match")
		if not service["ready"]:
			out["warnings"].append("The search service is still loading its models")
		elif models["reranker"] != "off" and not service["reranker_loaded"]:
			out["warnings"].append("The search service could not load its re-ranker: results are not re-ranked")
	return out


@frappe.whitelist(methods=["POST"])
def run_reconcile():
	from surveillance import knowledge_base as kb
	require_capability(kb.CAPABILITY)
	return reconcile(fix=True)
