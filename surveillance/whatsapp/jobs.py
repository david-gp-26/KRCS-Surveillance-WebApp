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
from frappe.utils import cint, now_datetime
from frappe.utils.password import get_encryption_key

from surveillance import chatbot_log
from surveillance.whatsapp import data, sessions
from surveillance.whatsapp.chatbot import ChatbotClient
from surveillance.whatsapp.client import MediaTooLarge, WhatsAppClient
from surveillance.whatsapp.content import T
from surveillance.whatsapp.conversation import MEDIA_TYPES, AttrDict, format_phone, handle
from surveillance.whatsapp.extract import ExtractionClient
from surveillance.whatsapp.messages import text, validate
from surveillance.whatsapp.redact import redact
from surveillance.whatsapp.transcribe import TranscriptionClient

INBOX = "whatsapp:inbox:{}"
LOCK = "whatsapp:lock:{}"
LOCK_SECONDS = 120  # longer than one message can take (chatbot: 2 tries x timeout)
DAY = 24 * 3600

ATTACHMENT_TYPES = {"image": "Photo", "audio": "Voice Note"}

# Meta limits a template to 1024 characters once its values are filled in, so the question leaves room for the rest.
TEMPLATE_QUESTION_CHARS = 650
ESCALATION_REASONS = {
	"not_a_report": "Message was not a health report",
	"service_unavailable": "Assistant was unavailable",
	"no_match": "No approved answer found",
	"low_confidence": "No confident answer found",
	"ambiguous": "Question could mean several things",
	"missing_capability": "Asker lacks access to this answer",
	"count_disease_unknown": "Disease in the question not recognised",
	"privacy_request": "Privacy request: pass to the Data Protection Officer",
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


def voice_transcriber(st):
	"""ctx.transcribe when Transcribe Voice Notes is on: POST /transcribe on the speech service in the site config
	(`stt_url`, `stt_token`), the one surveillance.transcription uses. The note stays on the report, attached as
	usual, with this text on its row, so the background job doesn't transcribe it again."""
	url = frappe.conf.get("stt_url")
	if not st.voice_transcription or not url:
		return None
	client = TranscriptionClient(url, frappe.conf.get("stt_token"), timeout=cint(st.transcription_timeout) or 45)

	def transcribe(inp):
		content, mime = whatsapp_client(st).download_media(inp["media_id"])
		return client.transcribe(content, mime or inp.get("mime_type"), inp.get("filename"))

	return transcribe


def record_privacy(phone, event, version, language=None, message_id=None):
	"""Committed at once: the person is treated as having agreed, or having withdrawn, right after this."""
	frappe.get_doc(
		{
			"doctype": "WhatsApp Consent Log",
			"phone": phone,
			"event": event,
			"notice_version": version,
			"language": language,
			"message_id": message_id,
			"recorded_on": now_datetime(),
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep


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
		transcribe=voice_transcriber(st),
		pseudonym_key=get_encryption_key(),
		on_privacy=record_privacy,
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
		lang=session.lang,
	)


def after_submit(report, media, phone, reporter_role=None, danger_signs=None, lang=None):
	failed = attach_media(report, media) if media else 0
	if failed:
		tell_reporter_media_failed(report, phone, failed, lang)
	notify_desk(report, phone, reporter_role, danger_signs)


def tell_reporter_media_failed(report, phone, failed, lang=None):
	"""They were told the report was received, and they wrote moments ago, so a plain message reaches them."""
	strings = T.get(lang) or T["en"]
	try:
		whatsapp_client().send(phone, text(strings["mediaNotSaved"](report, failed)))
	except Exception:
		frappe.log_error(title=f"WhatsApp reporter not told about media on {report}")


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
	"""Photos, voice notes, videos and documents become private Files on the report, plus an Attachments row
	each. A file that fails is skipped, logged and noted on the report; the report stays.
	Returns how many failed."""
	wa = whatsapp_client()
	rows = []
	failed = 0
	for i, m in enumerate(media, 1):
		try:
			content, mime = wa.download_media(m["media_id"])
			mime = (mime or m.get("mime_type") or "").split(";")[0].strip().lower()
			if mime not in MEDIA_TYPES:  # the conversation checked what WhatsApp declared; this is what arrived
				raise ValueError(f"File type not accepted: {mime}")
			ext = MEDIA_TYPES[mime]
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
			if m.get("transcript"):  # read in the conversation: surveillance.transcription skips rows with a status
				row.update({"transcript": m["transcript"], "transcript_status": "Done",
					"transcript_language": m.get("transcript_language"), "transcribed_on": frappe.utils.now_datetime()})
			if m.get("consent"):  # answered in the bot (RConsent)
				row.update({"people_shown": m.get("people_shown") or 0, "consent": m["consent"],
					"consent_recorded_on": frappe.utils.now_datetime()})
			rows.append(row)
		except MediaTooLarge as e:
			failed += 1
			logger().warning(f"media over the size limit on {report}: {e}")
		except Exception:
			failed += 1
			frappe.log_error(title=f"WhatsApp media could not be attached to {report}")
	if failed:
		rows.append(
			{
				"attachment_type": "Text Note",
				"text_content": f"{failed} of {len(media)} WhatsApp attachment(s) could not be saved.",
			}
		)
	if rows:
		doc = frappe.get_doc("Case Report", report)
		for row in rows:
			doc.append("attachments", row)
		doc.save(ignore_permissions=True)
		# Keep the attachments even if the desk alert that follows fails.
		frappe.db.commit()  # nosemgrep
	return failed


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
		", ".join(danger_signs or [])[:200] or "None noted",
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
	_send_all(to_numbers, msg, "WhatsApp desk alert failed", purpose="desk_alert", ref=r.name)


def log_chatbot(request, response, session):
	"""One Chatbot Query Log record per question, the source of the SRS acceptance metrics. The question is redacted
	and a community member's number is a pseudonym. Read access needs view_chatbot_logs."""
	chatbot_log.log_conversation(
		request,
		response,
		channel="WhatsApp",
		user=(session.staff or {}).get("user"),
		escalated_to=_escalation_target(),
	)


def _escalation_target():
	st = data.settings()
	to = numbers(st.escalation_numbers) or numbers(st.notify_numbers)
	return ", ".join(to) if to else "WhatsApp escalation desk (no number set)"


def on_escalate(question, session, request, reason, error=None, response=None):
	staff = session.staff or {}
	if error:  # the service never answered, so log_chatbot wrote nothing
		chatbot_log.log_conversation(
			request, None, channel="WhatsApp", user=staff.get("user"), error=error, escalated_to=_escalation_target()
		)
	else:
		chatbot_log.update(
			chatbot_log.find_by_correlation(request.get("request_id")),
			escalated_to_human=1,
			escalated_to=_escalation_target(),
		)
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
				"question": redact(question),
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
		asked_at=format_time(now_datetime()),
	)


def format_time(when):
	return when.strftime("%d %b %Y %H:%M")


def reason_label(reason):
	"""Unknown reasons still read as words: the chatbot service can add new ones."""
	return ESCALATION_REASONS.get(reason) or (reason or "—").replace("_", " ")


def send_escalation(question, who, phone, region, reason, asked_at=None):
	"""With an approved template it reaches anyone (AI/ML §6.2). Without one it is plain text, which only
	reaches numbers that messaged the bot in the last 24 hours.
	asked_at is when the person asked, because a late delivery would otherwise look like a new question."""
	st = data.settings()
	to_numbers = numbers(st.escalation_numbers) or numbers(st.notify_numbers)
	if not to_numbers:
		return
	sender = f"{who} {format_phone(phone)}"
	why = reason_label(reason)
	asked_at = asked_at or format_time(now_datetime())
	if st.escalation_template:
		msg = {
			"kind": "template",
			"name": st.escalation_template,
			"lang": st.notify_template_language or "en",
			"params": [sender, region or "—", why, (question or "—")[:TEMPLATE_QUESTION_CHARS], asked_at],
		}
	else:
		msg = text(
			f"*Question needs a reply*\n\n• From: {sender}\n• Region: {region or '—'}\n"
			f"• Why: {why}\n• Asked: {asked_at}\n\n{question[:1000]}"
		)
	_send_all(to_numbers, msg, "WhatsApp escalation failed", purpose="escalation")


def _send_all(to_numbers, msg, error_title, purpose=None, ref=None):
	"""The [sent] line gives the message ID that record_statuses later reports on."""
	wa = whatsapp_client()
	for to in to_numbers:
		try:
			sent = wa.send(to, msg) or {}
			message_id = ((sent.get("messages") or [{}])[0]).get("id")
			logger().info(
				"[sent] " + json.dumps({"id": message_id, "to": to, "purpose": purpose, "ref": ref})
			)
		except Exception:
			frappe.log_error(title=f"{error_title}: {to}")


def record_statuses(statuses):
	"""One line per delivery update in logs/whatsapp.log (SRS R71). A failed message also goes to the Error Log:
	131047 means the number has not written in 24 hours and needs a template."""
	for st in statuses:
		logger().info("[delivery] " + json.dumps(st))
		if st["status"] == "failed":
			codes = ", ".join(str(e["code"]) for e in st["errors"]) or "no code"
			frappe.log_error(
				title=f"WhatsApp message not delivered ({codes})", message=json.dumps(st, indent=1)
			)
