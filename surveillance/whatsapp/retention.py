"""Removing WhatsApp personal data: media past its retention period, and a reporter's details on request.

Periods are KRCS's to set (AI/ML §10, DPIA Action 9). With none set, daily() removes nothing.
"""

import frappe
from frappe.utils import add_days, cint, now_datetime
from frappe.utils.password import get_encryption_key

from surveillance.whatsapp import data, sessions
from surveillance.whatsapp.conversation import normalize_phone
from surveillance.whatsapp.redact import pseudonym

REMOVED = "Removed"
# Reporter and place details. Region, sub-county, symptoms, counts and dates remain for surveillance totals.
IDENTIFYING = {
	"reporter_name": REMOVED,
	"phone_number": REMOVED,
	"location_name": REMOVED,
	"additional_notes": None,
}


def _coarse_place(report):
	"""Coordinates are required on a Case Report, so the exact point becomes its sub-county's centre."""
	sub_county = frappe.db.get_value("Case Report", report, "sub_county")
	lat, lng = frappe.db.get_value("Sub County", sub_county, ["latitude", "longitude"]) or (0, 0)
	return {"latitude": lat or 0, "longitude": lng or 0}


def _clear_questions(phone):
	"""A community member's questions in the Chatbot Query Log and the searches behind them. The outcomes stay, as the
	SRS metrics count them."""
	log = "Chatbot Query Log"
	asked = frappe.get_all(
		log, filters={"user_ref": pseudonym(phone, get_encryption_key())}, fields=["name", "correlation_id"]
	)
	linked = {r.correlation_id for r in asked if r.correlation_id}
	rows = {r.name for r in asked}
	if linked:
		rows.update(frappe.get_all(log, filters={"correlation_id": ["in", list(linked)]}, pluck="name"))
	for name in rows:
		frappe.db.set_value(
			log,
			name,
			{"query_text": REMOVED, "user_ref": None, "trace": None, "feedback_comment": None, "response_note": None},
			update_modified=False,
		)


def daily():
	"""Scheduler (hooks.py)."""
	days = cint(data.settings().media_retention_days)
	if days > 0:
		purge_media(days)


def _remove_attachments(rows, note):
	"""Deletes each private file and leaves a note on its row, so the report shows something was there. A voice note's
	transcript (surveillance.transcription) is the reporter's own words, so it goes too."""
	for row in rows:
		for name in frappe.get_all("File", filters={"file_url": row.file}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)
		frappe.db.set_value(
			"Case Report Attachment",
			row.name,
			{"file": None, "text_content": note, "transcript": None, "transcript_language": None},
			update_modified=False,
		)


def purge_media(days):
	"""Photos, voice notes and files on WhatsApp reports older than `days`. Returns how many were removed."""
	rows = frappe.get_all(
		"Case Report Attachment",
		filters=[
			["parenttype", "=", "Case Report"],
			["file", "is", "set"],
			["creation", "<", add_days(now_datetime(), -days)],
		],
		fields=["name", "file", "parent"],
	)
	whatsapp = set(
		frappe.get_all(
			"Case Report",
			filters={"name": ["in", list({r.parent for r in rows})], "channel": "WhatsApp"},
			pluck="name",
		)
	)
	rows = [r for r in rows if r.parent in whatsapp]
	_remove_attachments(rows, f"Removed after {days} days (retention period).")
	frappe.db.commit()  # nosemgrep
	return len(rows)


@frappe.whitelist(methods=["POST"])
def anonymise_reporter(phone):
	"""Run by the Data Protection Officer on a person's request (DPA data subject rights). Removes the name, number,
	their own words, exact place and media from their WhatsApp reports, the versions that record those values, their
	questions in the Chatbot Query Log, and the conversation. Returns the reports changed."""
	frappe.only_for("System Manager")
	normalised = normalize_phone(phone, data.country_code())
	reports = frappe.get_all(
		"Case Report", filters={"phone_number": f"+{normalised}", "channel": "WhatsApp"}, pluck="name"
	)
	for name in reports:
		rows = frappe.get_all(
			"Case Report Attachment",
			filters={"parent": name, "parenttype": "Case Report", "file": ["is", "set"]},
			fields=["name", "file"],
		)
		_remove_attachments(rows, "Removed at the reporter's request.")
		frappe.db.set_value("Case Report", name, {**IDENTIFYING, **_coarse_place(name)}, update_modified=False)
		frappe.db.delete("Version", {"ref_doctype": "Case Report", "docname": name})
	_clear_questions(normalised)
	sessions.clear(normalised)
	frappe.get_doc(
		{
			"doctype": "WhatsApp Consent Log",
			"phone": normalised,
			"event": "Data Removed",
			"notice_version": ", ".join(reports)[:140] or "no reports",
			"recorded_on": now_datetime(),
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep
	return reports
