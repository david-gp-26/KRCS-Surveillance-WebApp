"""Response Support Chatbot gateway: the one Frappe path between users and the chatbot service.

Contract: agents/chatbot/docs/frappe_interface.md
    §2  get_retrieval_corpus  Frappe -> service: Active Response Protocol records + aliases (service user only)
    §3  ask / ask_mobile      user -> Frappe -> service /chat. Identity, roles, region and capabilities come from
                              Frappe, never from the client (R63). Inactive accounts are refused and logged.
                              Only outcome, message, options, protocol and the log id go back to the client.
    §3a counts                the service returns a structured Case Report query; Frappe validates it and counts
                              as the asking user, with their permissions
    §4  reload                after a protocol enters or leaves Active, or synonyms change, Frappe calls
                              POST /admin/reload so the service never serves withdrawn content for 5 minutes

WhatsApp runs the same rules from surveillance.whatsapp (sender looked up by phone, roles from Frappe, Query Log).
"""
import json
import os
import re
import time
import uuid

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from surveillance import chatbot_log, kb_access
from surveillance.capabilities import get_user_capabilities, has_capability

EXCLUDED_ROLES = {"All", "Guest", "Desk User"}
STAGES = {
	"case_definition": "Case definition", "immediate_action": "Immediate action", "notification": "Notification",
	"isolation": "Isolation", "referral": "Referral", "ipc": "Infection prevention and control",
	"specimen_collection": "Specimen collection", "community_action": "Community action", "follow_up": "Follow-up",
}
UNAVAILABLE = {
	"en": "The guidance service is not available right now, so I have not answered. Your question has been passed "
		"to {contact}. If this is an emergency, follow your usual emergency reporting procedure.",
	"sw": "Huduma ya miongozo haipatikani kwa sasa, kwa hivyo sijajibu. Swali lako limetumwa kwa {contact}. "
		"Ikiwa ni dharura, fuata utaratibu wako wa kawaida wa kuripoti dharura.",
}
COUNT_FAILED = {
	"en": "I could not count the reports just now. Please try again later or use the Reports page.",
	"sw": "Sikuweza kuhesabu ripoti kwa sasa. Tafadhali jaribu tena baadaye au tumia ukurasa wa Ripoti.",
}
COUNT_FIELDS = ("suspected_disease", "region", "sub_county", "channel", "status", "severity", "signal_type")
CLIENT_FIELDS = ("outcome", "message", "options", "protocol", "route", "services", "escalate")


# ---------- asking ----------

def _settings():
	return frappe.get_cached_doc("WhatsApp Settings")


def _client():
	from surveillance.whatsapp.jobs import chatbot_client
	return chatbot_client(_settings())


def escalation_contact():
	from surveillance.knowledge_base import escalation_contact as kb_contact
	return kb_contact()


def _language(user, language):
	lang = (language or "").lower()[:2]
	if lang in ("en", "sw"):
		return lang
	if lang == "ki":   # "Kiswahili"
		return "sw"
	ul = (frappe.db.get_value("User", user, "language") or "").lower()[:2]
	return ul if ul in ("en", "sw") else None


def build_request(user, message, language=None, selected_protocol_id=None):
	"""The /chat body, built from Frappe records only (contract §3 step 2)."""
	roles = sorted(set(frappe.get_roles(user)) - EXCLUDED_ROLES) or ["Guest"]
	return {
		"message": str(message or "")[:2000],
		"roles": roles,
		"language": _language(user, language),
		"location": frappe.db.get_value("User", user, "assigned_region"),
		"selected_protocol_id": selected_protocol_id or None,
		"user_ref": user,
		"request_id": str(uuid.uuid4()),
		"capabilities": sorted(get_user_capabilities(user)),
	}


def _deny(code, message, user, channel, query):
	chatbot_log.log_denied(level="Conversation", route="chat", channel=channel, user=None if user == "Guest" else user,
		user_ref=user, caller=frappe.session.user, query_text=query, deny_reason_code=code,
		access_policy_version=kb_access.POLICY_VERSION, error=message)
	raise kb_access.KBAccessDenied(message, code)


def chat(user, message, channel, language=None, selected_protocol_id=None):
	"""Ask the service as `user` and return what the client may see. Used by every channel entry point."""
	if user == "Guest":
		_deny("NOT_LOGGED_IN", _("Please sign in to ask a question."), user, channel, message)
	from surveillance.kb_ops import throttle
	throttle("chat")
	row = kb_access._user_row(user)
	if user != "Administrator" and not kb_access.account_active(row):
		_deny("ACCOUNT_INACTIVE", _("Your account is not active."), user, channel, message)
	if not str(message or "").strip():
		frappe.throw(_("Please type a question."))
	req = build_request(user, message, language, selected_protocol_id)
	actor_class = kb_access._staff_context(user, row)["actor_class"]
	lang = req["language"] or "en"
	started = time.monotonic()
	client = _client()
	response, error = None, None
	if not client:
		error = "chatbot service URL is not configured (WhatsApp Settings)"
	else:
		try:
			response = client.ask(req)
		except Exception as e:   # timeouts, connection errors and 5xx were already retried once
			error = str(e)[:500]
	latency = int((time.monotonic() - started) * 1000)
	contact = escalation_contact()
	if error:
		frappe.log_error(title="Chatbot gateway: service unavailable", message=error)
		reply = {"outcome": "escalate", "message": UNAVAILABLE[lang].format(contact=contact), "escalate": True}
		log_id = chatbot_log.log_conversation(req, None, channel=channel, user=user, error=error, latency_ms=latency,
			actor_class=actor_class, escalated_to=contact)
		return {**reply, "options": [], "protocol": None, "log_id": log_id}

	if response.get("outcome") == "count":
		response = {**response, "message": _count_message(response, user, lang)}
	log_id = chatbot_log.log_conversation(req, response, channel=channel, user=user, latency_ms=latency,
		actor_class=actor_class, escalated_to=contact)
	if log_id and (response.get("escalate") or response.get("outcome") == "escalate"):
		chatbot_log.update(log_id, escalation_status="Open")
	out = {k: response.get(k) for k in CLIENT_FIELDS}
	out["options"] = out.get("options") or []
	out["log_id"] = log_id
	return out


@frappe.whitelist(methods=["POST"])
def ask(message, language=None, selected_protocol_id=None):
	"""Web entry point (AI Data Assistant). The channel is set here, never by the client."""
	return chat(frappe.session.user, message, "Web", language, selected_protocol_id)


@frappe.whitelist(methods=["POST"])
def ask_mobile(message, language=None, selected_protocol_id=None):
	"""Mobile app entry point (same rules, channel Mobile)."""
	return chat(frappe.session.user, message, "Mobile", language, selected_protocol_id)


# ---------- report counts (§3a) ----------

def validate_query(query):
	"""Raise ValueError unless the query is exactly the shape the contract allows."""
	if not isinstance(query, dict) or query.get("doctype") != "Case Report":
		raise ValueError("doctype must be Case Report")
	filters = query.get("filters") or []
	if not isinstance(filters, list):
		raise ValueError("filters must be a list")
	for f in filters:
		if not (isinstance(f, list) and len(f) == 3):
			raise ValueError(f"bad filter {f!r}")
		field, op, value = f
		if field in COUNT_FIELDS:
			if op == "=" and isinstance(value, str):
				continue
			if op == "in" and isinstance(value, list) and all(isinstance(v, str) for v in value):
				continue
		elif field == "creation" and op == "between" and isinstance(value, list) and len(value) == 2 \
				and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)) for v in value):
			continue
		raise ValueError(f"filter not allowed: {f!r}")
	group_by = query.get("group_by")
	if group_by is not None and group_by not in COUNT_FIELDS:
		raise ValueError(f"group_by not allowed: {group_by!r}")
	return filters, group_by


def _label(field, value):
	if value in (None, ""):
		return "-"
	if field == "suspected_disease":
		return frappe.db.get_value("Alert Threshold Config", value, "disease_name") or value
	if field == "region":
		return frappe.db.get_value("Region", value, "region_name") or value
	return str(value)


def _count_message(response, user, lang):
	"""Count as the asking user (their permissions decide what is counted) and fill the message."""
	try:
		if "view_reports" not in get_user_capabilities(user):
			raise ValueError("missing view_reports")
		filters, group_by = validate_query(response.get("query"))
		message = response.get("message") or ""
		if group_by:
			rows = frappe.get_list("Case Report", filters=filters, fields=[group_by, "count(name) as count"],
				group_by=group_by, order_by="count desc")
			total = sum(cint(r["count"]) for r in rows)
			lines = "\n".join(f"{_label(group_by, r[group_by])}: {cint(r['count'])}" for r in rows)
			message = message.replace("{rows}", lines)
		else:
			# get_list applies the user's permissions; frappe.db.count would not
			total = cint(frappe.get_list("Case Report", filters=filters, fields=["count(name) as count"])[0]["count"])
		return message.replace("{count}", str(total))
	except Exception as e:
		frappe.log_error(title="Chatbot gateway: report count failed", message=str(e))
		return COUNT_FAILED[lang]


# ---------- corpus (§2) ----------

def _stage_keywords():
	path = os.path.join(os.path.dirname(__file__), "stage_keywords.json")
	with open(path, encoding="utf-8") as f:
		return json.load(f)["stage_keywords"]


def _aliases():
	meta = frappe.get_meta("Alert Threshold Config")
	fields = ["name", "disease_name", "is_active"] + (["synonyms"] if meta.has_field("synonyms") else [])
	diseases, unsupported = {}, {}
	for d in frappe.get_all("Alert Threshold Config", fields=fields):
		names = [d.name, d.disease_name, *kb_access._split(d.get("synonyms"))]
		names = sorted({n.strip() for n in names if n and n.strip()})
		if cint(d.is_active):
			diseases[d.name] = {"label": d.disease_name or d.name, "aliases": names}
		else:
			unsupported[d.name] = names
	return {"diseases": diseases, "unsupported_diseases": unsupported, "stage_keywords": _stage_keywords()}


def _regions(value):
	vals = kb_access._split(value)
	if not vals:
		return ["national"]
	by_name = {r.region_name: r.name for r in frappe.get_all("Region", fields=["name", "region_name"])}
	return [by_name.get(v, v) for v in vals]


def _serving(p):
	"""Approved, approved by someone, within its dates."""
	if p.status != "Approved" or not p.approved_by or not p.approved_on:
		return False
	start = getdate(p.get("effective_date") or p.approved_on)
	if start > getdate(today()):
		return False
	return not (p.review_date and getdate(p.review_date) < getdate(today()))


def protocol_records(p, aliases=None):
	"""One contract record per protocol x action stage. The text is the approved steps, verbatim."""
	if not _serving(p):
		return []
	aliases = aliases if aliases is not None else _aliases()
	groups = {}
	case_def = [q.question for q in p.verification_questions if q.kind == "Case definition" and q.question]
	if case_def:
		groups["case_definition"] = [f"- {q.strip()}" for q in case_def]
	for s in p.steps:
		if not s.step:
			continue
		stage = s.get("action_stage") or ("immediate_action" if s.phase == "Investigation" else "community_action")
		extra = ", ".join(x for x in (s.timeframe, s.responsible) if x)
		groups.setdefault(stage, []).append(f"- {s.step.strip()}" + (f" ({extra})" if extra else ""))
	audience = kb_access._split(p.get("audience")) or sorted(kb_access.surveillance_roles())
	disease_aliases = (aliases["diseases"].get(p.disease) or {}).get("aliases", [])
	icd = [{"code": c.code, "title": c.title, "uri": c.uri} for c in (p.get("icd11") or []) if c.code and c.uri]
	out = []
	for stage, lines in groups.items():
		body = "\n".join(lines)
		if stage == "immediate_action" and p.summary:
			body = f"{p.summary.strip()}\n\n{body}"
		out.append({
			"protocol_id": f"{p.name}:{stage}",
			"title": f"{p.title} — {STAGES[stage]}",
			"disease": p.disease,
			"disease_aliases": disease_aliases,
			"symptom_keywords": [],
			"audience": audience,
			"situation": f"{STAGES[stage]} for {p.title}",
			"action_stage": stage,
			"location_applicability": _regions(p.get("location_applicability")),
			"language": p.get("language") or "en",
			"approved_content": body,
			"source_document": p.source or "KRCS Response Protocol",
			"source_section": STAGES[stage],
			"source_page": None,
			"source_version": p.version or "v1",
			"effective_date": str(getdate(p.get("effective_date") or p.approved_on)),
			"review_date": str(p.review_date) if p.review_date else None,
			"approved_by": p.approved_by,
			"approval_date": str(getdate(p.approved_on)),
			"status": "active",
			"placeholder": bool(cint(p.get("placeholder"))),
			"icd11": icd,
		})
	return out


@frappe.whitelist(methods=["GET"])
def get_retrieval_corpus():
	"""Active protocol records for the chatbot service. Only the service account (kb_service) may call it."""
	if not has_capability("kb_service"):
		raise kb_access.KBAccessDenied(_("Only the chatbot service may read the corpus."), "NOT_SERVICE")
	aliases = _aliases()
	records = []
	for name in frappe.get_all("Response Protocol", filters={"status": "Approved"}, pluck="name"):
		records += protocol_records(frappe.get_doc("Response Protocol", name), aliases)
	return {"protocols": records, "aliases": aliases, "settings": {"escalation_contact": escalation_contact()}}


# ---------- reload (§4) ----------

def _reload():
	st = _settings()
	if not st.chatbot_url:
		return None
	import requests
	token = st.get_password("chatbot_token", raise_exception=False)
	try:
		r = requests.post(st.chatbot_url.rstrip("/") + "/admin/reload",
			headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=30)
		result = {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300]}
	except Exception as e:
		result = {"status": None, "error": str(e)[:300]}
	result["at"] = str(frappe.utils.now_datetime())
	frappe.cache().set_value("chatbot_last_reload", result)
	if result.get("status") != 200:
		frappe.log_error(title="Chatbot gateway: reload failed", message=json.dumps(result, default=str))
	return result


def request_reload():
	"""Reload the service after this transaction commits (never for content that was rolled back)."""
	if frappe.flags.in_test or frappe.flags.in_migrate or frappe.flags.in_install:
		frappe.flags.chatbot_reload_requested = True
		return
	frappe.db.after_commit.add(lambda: frappe.enqueue("surveillance.chatbot.api._reload", queue="short"))


def on_protocol_change(doc, method=None):
	"""Response Protocol hook: reload when a protocol enters or leaves Active, or Active content changes."""
	before = doc.get_doc_before_save()
	was = bool(before) and _serving(before)
	if method == "on_trash":
		if _serving(doc):
			request_reload()
		return
	if was or _serving(doc):
		request_reload()


def on_vocabulary_change(doc, method=None):
	"""Alert Threshold Config hook: synonyms, names and active diseases feed the service's aliases."""
	before = doc.get_doc_before_save()
	fields = ("disease_name", "is_active", "synonyms")
	if method == "on_trash" or not before or any(before.get(f) != doc.get(f) for f in fields):
		request_reload()


@frappe.whitelist()
def last_reload():
	if not has_capability("manage_response_protocols"):
		raise kb_access.KBAccessDenied(_("Not permitted"), "NO_CAPABILITY")
	return frappe.cache().get_value("chatbot_last_reload")
