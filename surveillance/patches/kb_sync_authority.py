"""KB-13: default authority on existing documents and copy authority / conflicts onto every chunk."""
import frappe


def execute():
	frappe.reload_doc("surveillance", "doctype", "knowledge_document")
	frappe.db.sql("""update `tabKnowledge Document` set authority='KRCS protocol' where ifnull(authority, '') = ''""")
	from surveillance.knowledge_base import sync_all_payloads
	sync_all_payloads()
