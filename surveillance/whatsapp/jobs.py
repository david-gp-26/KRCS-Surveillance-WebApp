"""Background jobs: answering messages, attaching media to reports, desk alerts and escalations.

Messages from one number are answered one at a time and in order: the webhook appends each message
to that number's inbox (a Redis list) and enqueues process_inbox; whichever worker holds the number's
lock empties the inbox, so two quick taps never race on the same session.
Needs the background workers (bench worker) and Redis to be running.
"""

import json
import time
from types import SimpleNamespace

import frappe
from frappe.utils import cint

from surveillance.whatsapp import data, sessions
from surveillance.whatsapp.chatbot import ChatbotClient
from surveillance.whatsapp.client import WhatsAppClient
from surveillance.whatsapp.conversation import AttrDict, format_phone, handle
from surveillance.whatsapp.extract import ExtractionClient
from surveillance.whatsapp.messages import text, validate

INBOX = "whatsapp:inbox:{}"
LOCK = "whatsapp:lock:{}"
LOCK_SECONDS = 120  # longer than one message can take (chatbot: 2 tries x timeout)
DAY = 24 * 3600

ATTACHMENT_TYPES = {"image": "Photo", "audio": "Voice Note"}
EXT = {
	"image/jpeg": "jpg",
	"image/png": "png",
	"image/webp": "webp",
	"audio/ogg": "ogg",
	"audio/mpeg": "mp3",
	"audio/mp4": "m4a",
	"video/mp4": "mp4",
	"application/pdf": "pdf",
}


def logger():
	return frappe.logger("whatsapp", allow_site=True)


def whatsapp_client(st=None):
	st = st or data.settings()
	return WhatsAppClient(
		st.get_password("access_token"), st.phone_number_id, st.graph_api_version or "v23.0"
	)


def chatbot_client(st):
	if not st.chatbot_url:
		return None
	return ChatbotClient(
		st.chatbot_url,
		st.get_password("chatbot_token", raise_exception=False),
		timeout=cint(st.chatbot_timeout) or 10,
	)


def extraction_client(st):
	"""POST /extract for free-text reports: its own URL (the NLP service, W-16) or the chatbot service.
	None: the conversation uses its keyword fallback."""
	url = st.extraction_url or st.chatbot_url
	if not url:
		return None
	token_field = "extraction_token" if st.extraction_url else "chatbot_token"
	return ExtractionClient(url, st.get_password(token_field, raise_exception=False), timeout=8)


def numbers(value):
	"""One number per line (or comma-separated), digits only."""
	return [
		n
		for n in (
			"".join(ch for ch in part if ch.isdigit())
			for part in (value or "").replace(",", "\n").split("\n")
		)
		if n
	]


def queue_message(ev):
	"""Called by the webhook for each new message."""
	inbox = INBOX.format(ev["from"])
	frappe.cache.rpush(inbox, json.dumps(ev))
	frappe.cache.expire(frappe.cache.make_key(inbox), DAY)
	frappe.enqueue("surveillance.whatsapp.jobs.process_inbox", queue="short", phone=ev["from"])


def process_inbox(phone):
	inbox, lock = INBOX.format(phone), frappe.cache.make_key(LOCK.format(phone))
	while frappe.cache.llen(inbox):
		# SET NX EX is the atomic lock; `lock` is site-prefixed by make_key, so sites don't share it.
		if not frappe.cache.set(lock, 1, nx=True, ex=LOCK_SECONDS):  # nosemgrep
			return  # another worker is answering this number and will take these messages too
		try:
			while raw := frappe.cache.lpop(inbox):
				frappe.cache.expire(lock, LOCK_SECONDS)
				try:
					process_event(json.loads(raw))
				except Exception:
					frappe.db.rollback()
					frappe.log_error(title="WhatsApp message failed")
		finally:
			frappe.cache.delete(lock)


def process_event(ev):
	st = data.settings()
	wa = whatsapp_client(st)
	try:
		wa.mark_read(ev["id"])  # before the reply, so the typing indicator can't linger after it
	except Exception:
		pass
	session = sessions.load(ev["from"])
	if ev.get("name"):
		session.profile_name = ev["name"]
	ctx = make_context(st)
	ctx.message_id = ev.get("id")   # becomes the report's client_ref, so a redelivered message never creates a second report
	replies = handle(session, ev["input"], ctx)
	sessions.save(session)
	for msg in replies:
		problems = validate(msg)
		if problems:
			logger().warning(f"message over WhatsApp limits: {'; '.join(problems)}")
		try:
			wa.send(ev["from"], msg)
		except Exception:
			frappe.log_error(title="WhatsApp reply could not be sent")
			break


def make_context(st):
	return SimpleNamespace(
		data=data,
		settings=AttrDict(
			idle_minutes=cint(st.idle_minutes) or 15, welcome_image_url=st.welcome_image_url or None
		),
		now=time.time,
		chatbot=chatbot_client(st),
		extractor=extraction_client(st),
		on_submit=on_submit,
		on_extract=log_extraction,
		on_report_stats=log_report_stats,
		on_chatbot=log_chatbot,
		on_escalate=on_escalate,
		log_error=lambda title: frappe.log_error(title=title),
	)


def on_submit(report, session, media, extraction=None):
	frappe.enqueue(
		"surveillance.whatsapp.jobs.after_submit",
		queue="default",
		report=report["name"],
		media=[dict(m) for m in media],
		phone=session.phone,
		reporter_role=(session.staff or {}).get("role"),
		danger_signs=list((extraction or {}).get("danger_signs") or []),
	)


def after_submit(report, media, phone, reporter_role=None, danger_signs=None):
	if media:
		attach_media(report, media)
	notify_desk(report, phone, reporter_role, danger_signs)


def log_extraction(report, session, draft):
	"""One line per free-text report in logs/whatsapp.log: what was extracted and what the reporter kept. The
	share changed by reporters is the correction rate the AI/ML spec tracks per extractor version (§7.1)."""
	x = draft.extraction

	def final(k):
		return draft.symptoms if k == "symptoms" else draft.get(k)

	fields = {
		k: {"extracted": v, "kept": final(k) == v, "confidence": x.confidence.get(k)}
		for k, v in x.filled.items()
	}
	logger().info(
		"[extract] "
		+ json.dumps(
			{
				"report": report["name"],
				"extractor": x.extractor,
				"threat": x.threat,
				"danger_signs": x.danger_signs,
				"fields": fields,
				"asked": draft.followups,
			}
		)
	)


def log_report_stats(report, session, draft, seconds):
	"""One line per report in logs/whatsapp.log: how long it took and how many messages the reporter sent,
	to measure the time to submit a report (community and staff, free text and step by step)."""
	logger().info(
		"[report] "
		+ json.dumps(
			{
				"report": report["name"],
				"mode": session.mode,
				"free_text": bool(draft.free),
				"messages": draft.messages or 0,
				"seconds": seconds,
				"asked": draft.followups if draft.free else None,
			}
		)
	)


def attach_media(report, media):
	"""Photos, voice notes and documents become private Files on the report, plus an Attachments row each.
	A file that fails is logged and skipped; the report stays."""
	wa = whatsapp_client()
	rows = []
	for i, m in enumerate(media, 1):
		try:
			content, mime = wa.download_media(m["media_id"])
			mime = (mime or m.get("mime_type") or "").split(";")[0]
			ext = EXT.get(mime) or mime.split("/")[-1] or "bin"
			f = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": m.get("filename") or f"whatsapp-{report}-{i}.{ext}",
					"content": content,
					"is_private": 1,
					"attached_to_doctype": "Case Report",
					"attached_to_name": report,
				}
			).insert(ignore_permissions=True)
			kind = ATTACHMENT_TYPES.get(m.get("kind"), "Attachment")
			row = {"attachment_type": kind, "file": f.file_url, "text_content": m.get("caption")}
			if kind in ("Photo", "Voice Note") and m.get("consent"):   # answered in the bot (RConsent)
				row.update({"people_shown": m.get("people_shown") or 0, "consent": m["consent"],
					"consent_recorded_on": frappe.utils.now_datetime()})
			rows.append(row)
		except Exception:
			frappe.log_error(title=f"WhatsApp media could not be attached to {report}")
	if rows:
		doc = frappe.get_doc("Case Report", report)
		for row in rows:
			doc.append("attachments", row)
		doc.save(ignore_permissions=True)
		# Keep the attachments even if the desk alert that follows fails.
		frappe.db.commit()  # nosemgrep


def notify_desk(report, phone, reporter_role=None, danger_signs=None):
	"""One alert per new report to the desk numbers in WhatsApp Settings.
	A number that hasn't written to the bot in the last 24 hours can only receive an approved template."""
	st = data.settings()
	to_numbers = numbers(st.notify_numbers)
	if not to_numbers:
		return
	r = frappe.db.get_value(
		"Case Report",
		report,
		[
			"name",
			"symptom_tags",
			"location_name",
			"region",
			"latitude",
			"longitude",
			"affected_count",
			"reporter_name",
		],
		as_dict=True,
	)
	region = frappe.db.get_value("Region", r.region, "region_name") or r.region
	where = ", ".join(x for x in (r.location_name, region) if x)
	pin = f" https://maps.google.com/?q={r.latitude},{r.longitude}" if r.latitude is not None else ""
	who = f"{r.reporter_name}{f' ({reporter_role})' if reporter_role else ''} {format_phone(phone)}"
	params = [
		r.name,
		(r.symptom_tags or "—")[:200],
		f"{where or '—'}{pin}",
		str(r.affected_count or "—"),
		who,
	]
	if st.notify_template:
		msg = {
			"kind": "template",
			"name": st.notify_template,
			"lang": st.notify_template_language or "en",
			"params": params,
		}
	else:
		msg = text(
			f"*New surveillance report {params[0]}*\n\n• What: {params[1]}\n• Where: {params[2]}\n"
			f"• Affected: {params[3]}\n• Reporter: {params[4]}"
			+ (f"\n• *Danger signs:* {', '.join(danger_signs)}" if danger_signs else "")
		)
	_send_all(to_numbers, msg, "WhatsApp desk alert failed")


def log_chatbot(request, response, session):
	"""One Chatbot Query Log record (level Conversation, channel WhatsApp) per question.
	Contains personal data: read access needs view_chatbot_logs; retention per chatbot_log_retention_days."""
	from surveillance import chatbot_log

	staff = session.staff or {}
	chatbot_log.log_conversation(request, response, channel="WhatsApp", user=staff.get("user"),
		escalated_to=_escalation_target())


def _escalation_target():
	st = data.settings()
	nums = numbers(st.escalation_numbers) or numbers(st.notify_numbers)
	return ", ".join(nums) if nums else "WhatsApp escalation desk (no number set)"


def on_escalate(question, session, request, reason, error=None, response=None):
	from surveillance import chatbot_log

	staff = session.staff or {}
	if error:
		# the service never answered, so no record was written by log_chatbot: write one now
		chatbot_log.log_conversation(request, None, channel="WhatsApp", user=staff.get("user"), error=error,
			escalated_to=_escalation_target())
	else:
		chatbot_log.update(chatbot_log.find_by_correlation(request.get("request_id")), escalated_to_human=1,
			escalated_to=_escalation_target())
	if staff:
		who = staff.get("full_name") + (f" ({staff['role']})" if staff.get("role") else "")
	else:
		who = session.profile_name or "Community member"
	logger().info(
		"[escalate] "
		+ json.dumps(
			{
				"request_id": request["request_id"],
				"user": request["user_ref"],
				"reason": reason,
				"error": error,
				"question": question,
			}
		)
	)
	frappe.enqueue(
		"surveillance.whatsapp.jobs.send_escalation",
		queue="short",
		question=question,
		who=who,
		phone=session.phone,
		region=staff.get("region_label") or staff.get("region"),
		reason=reason,
	)


def send_escalation(question, who, phone, region, reason):
	"""Plain text, so it only reaches numbers that messaged the bot in the last 24 hours."""
	st = data.settings()
	to_numbers = numbers(st.escalation_numbers) or numbers(st.notify_numbers)
	if not to_numbers:
		return
	body = (
		f"*Question needs a reply*\n\n• From: {who} {format_phone(phone)}\n• Region: {region or '—'}\n"
		f"• Why: {reason}\n\n{question[:1000]}"
	)
	_send_all(to_numbers, text(body), "WhatsApp escalation failed")


def _send_all(to_numbers, msg, error_title):
	wa = whatsapp_client()
	for to in to_numbers:
		try:
			wa.send(to, msg)
		except Exception:
			frappe.log_error(title=f"{error_title}: {to}")
