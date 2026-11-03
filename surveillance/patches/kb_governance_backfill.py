"""KB-7 / KB-8: give existing documents a family and a content hash; approved ones get their approved hash."""
import frappe


def execute():
	frappe.reload_doc("surveillance", "doctype", "knowledge_document")
	from surveillance.knowledge_base import DOCTYPE, file_hash
	for d in frappe.get_all(DOCTYPE, fields=["name", "file", "approval_status", "document_family", "content_hash"]):
		values = {}
		if not d.document_family:
			values["document_family"] = d.name
		if not d.content_hash and d.file:
			try:
				values["content_hash"] = file_hash(d.file)
				if d.approval_status == "Approved":
					values["approved_hash"] = values["content_hash"]
			except Exception:
				frappe.log_error(title=f"Knowledge Base: could not hash {d.name}")
		if values:
			frappe.db.set_value(DOCTYPE, d.name, values, update_modified=False)
