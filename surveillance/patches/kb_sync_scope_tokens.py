"""KB-4: copy scope tokens onto every Knowledge Base chunk. No re-embedding."""
import frappe


def execute():
	frappe.reload_doc("surveillance", "doctype", "knowledge_document")
	from surveillance.knowledge_base import sync_all_payloads
	sync_all_payloads()
