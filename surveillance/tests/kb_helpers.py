"""Shared fixtures for Knowledge Base tests.

Real Qdrant (site config qdrant_url), but a throw-away collection and small deterministic embeddings, so tests are
fast, repeatable and never touch the live index or download models:
    dense  = hashed bag of words (64 dims, L2-normalised): texts sharing words score higher
    sparse = hashed term counts
    re-ranker off
The krcs_search service is replaced by fake_search_service; it has its own tests in that repo.
"""
import hashlib
import json
import math
import re
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import frappe

from surveillance import knowledge_base as kb

DIM = 64
_created = []
_WORD = re.compile(r"\w+", re.U)


def _h(token, mod):
	return int(hashlib.md5(token.encode()).hexdigest(), 16) % mod


def fake_embed(texts):
	out = []
	for t in texts:
		v = [0.0] * DIM
		for w in _WORD.findall((t or "").lower()):
			v[_h(w, DIM)] += 1.0
		n = math.sqrt(sum(x * x for x in v)) or 1.0
		out.append([x / n for x in v])
	return out


def fake_sparse(texts):
	from qdrant_client.models import SparseVector
	out = []
	for t in texts:
		counts = {}
		for w in _WORD.findall((t or "").lower()):
			i = _h(w, 100000)
			counts[i] = counts.get(i, 0) + 1.0
		out.append(SparseVector(indices=list(counts), values=list(counts.values())))
	return out


def fake_search_service(body):
	"""Same contract and ranking rules as krcs_search, without its models. The JSON round trip is what the real
	request goes through, so the filter is applied exactly as the service would receive it."""
	from qdrant_client.models import Filter, Fusion, FusionQuery, Prefetch
	body = json.loads(json.dumps(body))
	client = kb._qdrant()
	if not client.collection_exists(body["collection"]):
		return {"points": [], "reranked": False}
	flt = Filter.model_validate(body["filter"]) if body["filter"] else None
	text = body["expanded_query"]
	hits = client.query_points(body["collection"],
		prefetch=[
			Prefetch(query=fake_embed([text])[0], using=kb.DENSE, filter=flt, limit=30),
			Prefetch(query=fake_sparse([text])[0], using=kb.SPARSE, filter=flt, limit=30),
		],
		query=FusionQuery(fusion=Fusion.RRF), limit=30, with_payload=True).points
	ranked = []
	for h in hits:
		if kb._expired(h.payload):
			continue
		lang = h.payload.get("chunk_language") or h.payload.get("language")
		ranked.append((h.score + (0.05 if body["language"] and lang == body["language"] else 0), h))
	ranked.sort(key=lambda x: -x[0])
	question = fake_embed([body["query"]])[0]
	points, per_section = [], {}
	for score, h in ranked:
		key = (h.payload.get("doc"), h.payload.get("section"))
		if per_section.get(key, 0) >= 2:
			continue
		per_section[key] = per_section.get(key, 0) + 1
		vector = fake_embed([h.payload.get("text") or ""])[0]
		points.append({"id": str(h.id), "rank_score": score, "payload": h.payload,
			"dense_score": sum(a * b for a, b in zip(question, vector))})
		if len(points) >= body["limit"]:
			break
	return {"points": points, "reranked": False}


@contextmanager
def kb_sandbox(**conf):
	"""Patch models and point the Knowledge Base at a fresh collection; drop it afterwards."""
	collection = f"kb_test_{uuid.uuid4().hex[:8]}"
	saved = {k: frappe.conf.get(k) for k in ["kb_collection", "kb_reranker_model", *conf]}
	frappe.conf["kb_collection"] = collection
	frappe.conf["kb_reranker_model"] = "off"
	for k, v in conf.items():
		frappe.conf[k] = v
	try:
		# patch the functions too: frappe.conf can be reloaded mid-test, and the live collection must never be touched
		with patch.object(kb, "embed", fake_embed), patch.object(kb, "sparse_embed", fake_sparse), \
				patch.object(kb, "_enqueue", lambda name: None), patch.object(kb, "_collection", lambda: collection), \
				patch.object(kb, "_search_service", fake_search_service):
			yield collection
	finally:
		try:
			kb._qdrant().delete_collection(collection)
		except Exception:
			pass
		# documents are committed by logging during tests; remove this sandbox's ones so runs don't pile up
		for name in _created:
			frappe.db.delete(kb.DOCTYPE, {"name": name})
		_created.clear()
		frappe.db.commit()
		for k, v in saved.items():
			if v is None:
				frappe.conf.pop(k, None)
			else:
				frappe.conf[k] = v


def region(name):
	existing = frappe.db.get_value("Region", {"region_name": name}, "name")
	if existing:
		return existing
	return frappe.get_doc({"doctype": "Region", "region_name": name}).insert(ignore_permissions=True).name


def ensure_role(role, capabilities):
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(ignore_permissions=True)
	if not frappe.db.exists("Surveillance Role", role) and frappe.db.exists("DocType", "Surveillance Role"):
		try:
			frappe.get_doc({"doctype": "Surveillance Role", "role": role}).insert(ignore_permissions=True)
		except Exception:
			pass
	for c in capabilities:
		if not frappe.db.exists("Role Capability", {"role": role, "capability": c}):
			frappe.get_doc({"doctype": "Role Capability", "role": role, "capability": c}).insert(ignore_permissions=True)
	frappe.clear_cache()


def user(email, role, region_name=None, status="Active", enabled=1, sub_county=None, **extra):
	if frappe.db.exists("User", email):
		u = frappe.get_doc("User", email)
	else:
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "user_type": "System User"})
		u.insert(ignore_permissions=True)
	u.set("roles", [])
	if role:
		u.append("roles", {"role": role})
	u.primary_role = role
	u.account_status = status
	u.enabled = enabled
	u.assigned_region = region(region_name) if region_name else None
	if sub_county is not None and u.meta.has_field("assigned_sub_county"):
		u.assigned_sub_county = sub_county
	for k, v in extra.items():
		setattr(u, k, v)
	u.save(ignore_permissions=True)
	frappe.clear_cache(user=email)
	return email


def add_document(title, text, approve=True, **meta):
	"""Create, index and (optionally) approve a Knowledge Document from text. Runs as the current user."""
	fname = f"{re.sub(r'[^a-z0-9]+', '_', title.lower())}_{uuid.uuid4().hex[:6]}.md"
	f = frappe.get_doc({"doctype": "File", "file_name": fname, "content": text.encode(), "is_private": 1})
	f.insert(ignore_permissions=True)
	row = kb.create_document(f.file_url, meta.pop("category", "Guideline"), **meta)
	_created.append(row["id"])
	kb.index_document(row["id"])
	doc = frappe.get_doc(kb.DOCTYPE, row["id"])
	assert doc.status == "Indexed", doc.error
	if approve:
		doc.approval_status = "Approved"
		doc.approved_by = "Administrator"
		doc.approved_on = frappe.utils.now_datetime()
		doc.save(ignore_permissions=True)
		kb._sync_access(doc)
	return doc.name


def as_user(email):
	frappe.set_user(email)
	frappe.local.response = frappe._dict()


def logs(**filters):
	return frappe.get_all("Chatbot Query Log", filters=filters, fields=["*"], order_by="creation desc")
