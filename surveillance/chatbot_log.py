"""Chatbot Query Log: one record per question to the Knowledge Base or the Response Support Chatbot.

Why: SDS B.4.2.3 (Chatbot Query Log), SRS R57 (AI audit) and the acceptance metrics in SRS Table 18 / Table 25
(match rate, escalation rate, content outside the approved set, restricted content to public users) are all
measured from these records.

Two levels, linked by correlation_id:
    Conversation  what the person asked and what they were shown (web assistant, WhatsApp, mobile, gateway)
    Retrieval     each Knowledge Base search / passage fetch behind it (often made by the chatbot service)
Metrics are computed on Conversation records; Retrieval records are the evidence trail.

Every record is committed straight away, so a denied request (which raises and rolls back) is still logged.
Records hold personal data (Kenya Data Protection Act 2019): read access needs capability view_chatbot_logs and
old records are purged after `chatbot_log_retention_days` (site config; 0 or unset = keep until KRCS decides, D3).
"""
import json
import uuid

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, today

from surveillance.capabilities import has_capability, require_capability
from surveillance.kb_access import POLICY_VERSION

DOCTYPE = "Chatbot Query Log"
VIEW = "view_chatbot_logs"
HANDLE = "handle_chatbot_escalations"
CHANNELS = ("Web", "Mobile", "WhatsApp", "SMS", "USSD", "API")
OUTCOMES = ("Matched", "No Match", "Restricted", "Escalated", "Conflict", "Clarify", "Routed", "Info", "Error")
ESCALATION_STATUSES = ("Open", "In Progress", "Answered", "Closed")
# Outcomes that count as "answered from approved content" for the match rate.
MATCHED = {"Matched"}
# Conversation outcomes that are about the app or reporting, not guidance; left out of match / escalation rates.
NOT_GUIDANCE = {"Routed", "Info"}
_JSON_FIELDS = ("passages", "trace")
_TEXT_LIMITS = {"query_text": 2000, "answer": 20000, "error": 1000, "reason": 140, "audience_roles": 1000,
	"scope": 1000, "user_ref": 140, "deny_reason_code": 140, "escalated_to": 140}


def _safe_log_error(title):
	try:
		frappe.log_error(title=title)
	except Exception:
		pass


def new_correlation_id():
	return str(uuid.uuid4())


def log(**fields):
	"""Insert one record and commit it. Never raises: logging must not break answering. Returns the name or None."""
	try:
		row = {"doctype": DOCTYPE}
		for k, v in fields.items():
			if v is None:
				continue
			if k in _JSON_FIELDS and not isinstance(v, str):
				v = json.dumps(v, default=str, ensure_ascii=False)
			elif isinstance(v, (list, tuple, set)):
				v = ", ".join(str(x) for x in v)
			if k in _TEXT_LIMITS and isinstance(v, str):
				v = v[: _TEXT_LIMITS[k]]
			row[k] = v
		row.setdefault("correlation_id", new_correlation_id())
		if row.get("channel") not in CHANNELS:
			row["channel"] = "API"
		if row.get("outcome") not in OUTCOMES:
			row["outcome"] = "Error"
		if row.get("escalated_to_human") and not row.get("escalation_status"):
			row["escalation_status"] = "Open"
		doc = frappe.get_doc(row)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name
	except Exception:
		_safe_log_error("Chatbot Query Log: could not write")
		return None


def log_denied(rollback=True, **fields):
	"""Record a denied request. The caller raises afterwards, which rolls the request back, so this commits on its
	own after discarding any partial work."""
	if rollback:
		frappe.db.rollback()
	return log(access_decision="DENY", outcome="Restricted", **fields)


def update(name, **fields):
	"""Change a few fields on an existing record (e.g. escalation from a later step). Never raises."""
	if not name:
		return
	try:
		for k, v in list(fields.items()):
			if k in _JSON_FIELDS and v is not None and not isinstance(v, str):
				fields[k] = json.dumps(v, default=str, ensure_ascii=False)
		if fields.get("escalated_to_human") and not fields.get("escalation_status"):
			if not frappe.db.get_value(DOCTYPE, name, "escalation_status"):
				fields["escalation_status"] = "Open"
		frappe.db.set_value(DOCTYPE, name, fields, update_modified=False)
		frappe.db.commit()
	except Exception:
		_safe_log_error("Chatbot Query Log: could not update")


def find_by_correlation(correlation_id, level="Conversation"):
	if not correlation_id:
		return None
	return frappe.db.get_value(DOCTYPE, {"correlation_id": correlation_id, "level": level}, "name")


# ---------- API ----------

def _row(d):
	return {
		"id": d.name, "createdAt": str(d.creation), "level": d.level, "channel": d.channel, "route": d.route,
		"user": d.user, "userName": frappe.utils.get_fullname(d.user) if d.user else None, "userRef": d.user_ref,
		"actorClass": d.actor_class, "audience": d.audience_roles, "scope": d.scope, "language": d.language,
		"question": d.query_text, "answer": d.answer, "answerMode": d.answer_mode, "outcome": d.outcome,
		"reason": d.reason, "confidence": d.match_confidence, "band": d.confidence_band,
		"matchedDocument": d.matched_document, "matchedProtocol": d.matched_protocol,
		"contentVersion": d.matched_content_version, "accessDecision": d.access_decision,
		"policyVersion": d.access_policy_version, "denyReason": d.deny_reason_code, "preview": cint(d.preview),
		"retrievalConfig": d.retrieval_config, "latencyMs": d.latency_ms, "error": d.error,
		"escalated": cint(d.escalated_to_human), "escalatedTo": d.escalated_to, "escalationStatus": d.escalation_status,
		"handledBy": frappe.utils.get_fullname(d.handled_by) if d.handled_by else None,
		"handledOn": str(d.handled_on) if d.handled_on else None, "responseNote": d.response_note,
		"helpful": d.feedback_helpful, "feedbackComment": d.feedback_comment, "correlationId": d.correlation_id,
	}


def _filters(from_date=None, to_date=None, channel=None, level=None, outcome=None, escalation_status=None):
	f = {}
	if from_date and to_date:
		f["creation"] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
	elif from_date:
		f["creation"] = [">=", f"{from_date} 00:00:00"]
	if channel:
		f["channel"] = channel
	if level:
		f["level"] = level
	if outcome:
		f["outcome"] = outcome
	if escalation_status:
		f["escalation_status"] = escalation_status
	return f


@frappe.whitelist()
def list_logs(from_date=None, to_date=None, channel=None, level="Conversation", outcome=None,
		escalation_status=None, limit=200):
	require_capability(VIEW)
	rows = frappe.get_all(DOCTYPE, fields=["*"], order_by="creation desc", limit=max(1, min(cint(limit) or 200, 1000)),
		filters=_filters(from_date, to_date, channel, level, outcome, escalation_status))
	return [_row(d) for d in rows]


@frappe.whitelist()
def get_log(name):
	require_capability(VIEW)
	d = frappe.get_doc(DOCTYPE, name)
	out = _row(d)
	out["passages"] = frappe.parse_json(d.passages) if d.passages else []
	out["trace"] = frappe.parse_json(d.trace) if d.trace else None
	out["related"] = [_row(r) for r in frappe.get_all(DOCTYPE, fields=["*"], order_by="creation asc",
		filters={"correlation_id": d.correlation_id, "name": ["!=", d.name]})] if d.correlation_id else []
	return out


def _pct(n, d):
	return round(100.0 * n / d, 1) if d else None


def _served_class(row):
	"""Audience class of the matched passage as recorded at serve time (None for older rows)."""
	try:
		passages = json.loads(row.passages) if isinstance(row.passages, str) else (row.passages or [])
	except Exception:
		return None
	for p in passages or []:
		if isinstance(p, dict) and p.get("doc") == row.matched_document and p.get("audience_class"):
			return p["audience_class"]
	return None


@frappe.whitelist()
def get_metrics(from_date=None, to_date=None, channel=None):
	"""Acceptance metrics (SRS Table 18 / Table 25) over Conversation records.

	match_rate      share of guidance questions answered from approved content (target >= 75%)
	escalation_rate share of guidance questions escalated or not matched (target <= 25%)
	restricted      denied requests (access decision DENY)
	public_restricted_leaks  replies to Public actors whose matched content was not Public (target 0)
	"""
	require_capability(VIEW)
	from_date = from_date or add_days(today(), -30)
	to_date = to_date or today()
	rows = frappe.get_all(DOCTYPE, filters=_filters(from_date, to_date, channel, "Conversation"),
		fields=["outcome", "escalated_to_human", "latency_ms", "channel", "access_decision", "actor_class",
			"matched_document", "feedback_helpful", "answer_mode", "passages"])
	guidance = [r for r in rows if r.outcome not in NOT_GUIDANCE and r.access_decision != "DENY"]
	matched = [r for r in guidance if r.outcome in MATCHED]
	escalated = [r for r in guidance if cint(r.escalated_to_human) or r.outcome in ("No Match", "Escalated", "Conflict")]
	lat = sorted(cint(r.latency_ms) for r in rows if r.latency_ms)
	leaks = 0
	public_docs = None
	for r in guidance:
		if r.actor_class == "Public" and r.matched_document:
			# the class recorded when the passage was served wins; the document may since be edited or deleted
			served = _served_class(r)
			if served is None:
				if public_docs is None:
					public_docs = set(frappe.get_all("Knowledge Document", filters={"audience_class": "Public"},
						pluck="name")) if frappe.get_meta("Knowledge Document").has_field("audience_class") else set()
				served = "Public" if r.matched_document in public_docs else "unknown"
			if served != "Public":
				leaks += 1
	by_channel = {}
	for r in rows:
		c = by_channel.setdefault(r.channel, {"questions": 0, "matched": 0, "escalated": 0})
		c["questions"] += 1
		c["matched"] += r.outcome in MATCHED
		c["escalated"] += bool(cint(r.escalated_to_human))
	helpful = [r for r in rows if r.feedback_helpful]
	return {
		"from_date": str(from_date), "to_date": str(to_date), "channel": channel,
		"questions": len(rows), "guidance_questions": len(guidance),
		"match_rate": _pct(len(matched), len(guidance)), "match_target": 75,
		"escalation_rate": _pct(len(escalated), len(guidance)), "escalation_target": 25,
		"denied": sum(1 for r in rows if r.access_decision == "DENY"),
		"generated_answers": sum(1 for r in rows if r.answer_mode in ("answer", "summary")),
		"public_restricted_leaks": leaks,
		"open_escalations": frappe.db.count(DOCTYPE, {"escalation_status": ["in", ["Open", "In Progress"]]}),
		"p50_latency_ms": lat[len(lat) // 2] if lat else None,
		"p95_latency_ms": lat[max(0, int(len(lat) * 0.95) - 1)] if lat else None,
		"helpful_rate": _pct(sum(1 for r in helpful if r.feedback_helpful == "Yes"), len(helpful)),
		"by_channel": by_channel,
		"outcomes": {o: sum(1 for r in rows if r.outcome == o) for o in OUTCOMES},
	}


@frappe.whitelist(methods=["POST"])
def update_escalation(name, status, note=None):
	"""Move an escalated question through Open -> In Progress -> Answered -> Closed."""
	require_capability(HANDLE)
	if status not in ESCALATION_STATUSES:
		frappe.throw(_("Status must be one of: {0}").format(", ".join(ESCALATION_STATUSES)))
	d = frappe.get_doc(DOCTYPE, name)
	if not cint(d.escalated_to_human):
		frappe.throw(_("This question was not escalated."))
	d.escalation_status = status
	if note is not None:
		d.response_note = note
	d.handled_by = frappe.session.user
	d.handled_on = now_datetime()
	d.save(ignore_permissions=True)
	return _row(d)


@frappe.whitelist(methods=["POST"])
def submit_feedback(name, helpful, comment=None, on_behalf_of=None):
	"""Helpful yes/no and a comment, by the person who asked (or the chatbot service for them)."""
	d = frappe.get_doc(DOCTYPE, name)
	user = frappe.session.user
	if on_behalf_of and has_capability("kb_service"):
		allowed = on_behalf_of in (d.user, d.user_ref)
	else:
		allowed = user != "Guest" and user == d.user
	if not allowed:
		frappe.throw(_("You can only give feedback on your own questions."), frappe.PermissionError)
	value = "Yes" if str(helpful).strip().lower() in ("1", "yes", "true", "y") else "No"
	frappe.db.set_value(DOCTYPE, name, {"feedback_helpful": value, "feedback_comment": (comment or "")[:1000],
		"feedback_on": now_datetime()}, update_modified=False)
	return {"id": name, "helpful": value}


def purge_old_logs():
	"""Daily: delete records older than chatbot_log_retention_days (0 / unset = keep, pending KRCS decision D3)."""
	days = cint(frappe.conf.get("chatbot_log_retention_days"))
	if days <= 0:
		return 0
	cutoff = add_days(getdate(today()), -days)
	names = frappe.get_all(DOCTYPE, filters={"creation": ["<", f"{cutoff} 00:00:00"],
		"escalation_status": ["not in", ["Open", "In Progress"]]}, pluck="name", limit=50000)
	for n in names:
		frappe.delete_doc(DOCTYPE, n, ignore_permissions=True, force=True)
	frappe.db.commit()
	return len(names)


# ---------- Response Support Chatbot exchanges (docs/frappe_interface.md §3) ----------

SERVICE_OUTCOMES = {"answer": "Matched", "reference": "Matched", "clarify": "Clarify", "escalate": "Escalated",
	"routed": "Routed", "greeting": "Info", "count": "Info", "info": "Info"}


def log_conversation(request, response=None, channel="API", user=None, error=None, latency_ms=None,
		actor_class=None, escalated_to=None):
	"""One Conversation record for a /chat exchange with the chatbot service. `request` is the /chat body."""
	response = response or {}
	protocol = response.get("protocol") or {}
	doc0 = (response.get("documents") or [{}])[0]
	if error:
		outcome, reason = "Error", "service_unavailable"
	else:
		outcome, reason = SERVICE_OUTCOMES.get(response.get("outcome"), "Error"), response.get("reason")
	if response.get("reason") == "conflict":
		outcome = "Conflict"
	escalated = bool(error or response.get("escalate") or response.get("outcome") == "escalate")
	matched_document = doc0.get("doc") if doc0.get("doc") and frappe.db.exists("Knowledge Document", doc0.get("doc")) else None
	roles = [r for r in (request.get("roles") or []) if r != "Guest"]
	return log(
		level="Conversation", route="chat", channel=channel, correlation_id=request.get("request_id"),
		user=user, user_ref=request.get("user_ref"), caller=frappe.session.user,
		actor_class=actor_class or ("Public" if not roles else "Staff"), access_policy_version=POLICY_VERSION,
		audience_roles=", ".join(roles) or "Guest", scope=request.get("location"),
		language=request.get("language") or response.get("language"), query_text=request.get("message"),
		answer=response.get("message"), answer_mode=response.get("outcome"), outcome=outcome, reason=reason,
		match_confidence=response.get("confidence"), confidence_band=doc0.get("confidence"),
		matched_document=matched_document,
		matched_protocol=protocol.get("protocol_id"),
		matched_content_version=protocol.get("source_version") or doc0.get("version"),
		passages=response.get("documents") or None, trace=response.get("trace"),
		access_decision="ALLOW", latency_ms=latency_ms or response.get("latency_ms"),
		error=str(error)[:1000] if error else (response.get("trace") or {}).get("knowledge_base_error"),
		escalated_to_human=1 if escalated else 0, escalated_to=escalated_to if escalated else None,
	)
