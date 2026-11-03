"""Copy audience class, level and sensitivity onto every Knowledge Base chunk (KB-3). No re-embedding."""
import frappe


def execute():
	frappe.reload_doc("surveillance", "doctype", "knowledge_document")
	frappe.db.sql("""update `tabKnowledge Document` set audience_class='Community Health Worker'
		where ifnull(audience_class, '') = ''""")
	frappe.db.sql("""update `tabKnowledge Document` set sensitivity='Standard' where ifnull(sensitivity, '') = ''""")
	from surveillance.knowledge_base import sync_all_payloads
	sync_all_payloads()
