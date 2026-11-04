"""KB-6: every Knowledge Base request, allowed or denied, leaves one Chatbot Query Log record (SDS B.4.2.3, R57)."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from surveillance import chatbot_log
from surveillance import knowledge_base as kb
from surveillance.tests import kb_helpers as h

CHP = "kbt-log-chp@example.com"
OFFICER = "kbt-log-officer@example.com"
NOBODY = "kbt-log-nobody@example.com"
SERVICE = "kbt-log-service@example.com"


class TestChatbotQueryLog(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("Surveillance Officer", ["use_knowledge_base", "view_chatbot_logs", "handle_chatbot_escalations"])
		h.ensure_role("KBT No KB", [])
		h.ensure_role("KBT Service", ["use_knowledge_base", "kb_service"])
		h.user(CHP, "CHP", "KBT Region A")
		h.user(OFFICER, "Surveillance Officer", "KBT Region A")
		h.user(NOBODY, "KBT No KB", "KBT Region A")
		h.user(SERVICE, "KBT Service")

	def setUp(self):
		# records commit on their own (so denials survive a rollback): clear this suite's records first
		frappe.set_user("Administrator")
		for f in ({"user": ["in", [CHP, OFFICER, NOBODY]]}, {"caller": ["in", [CHP, OFFICER, NOBODY, SERVICE]]},
				{"user_ref": ["like", "whatsapp:+254711%"]}):
			frappe.db.delete("Chatbot Query Log", f)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_denied_search_is_logged_with_reason(self):
		h.as_user(NOBODY)
		with self.assertRaises(frappe.PermissionError):
			kb.search("cholera", correlation_id="cid-denied-1")
		frappe.set_user("Administrator")
		rows = h.logs(correlation_id="cid-denied-1")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].access_decision, "DENY")
		self.assertEqual(rows[0].outcome, "Restricted")
		self.assertEqual(rows[0].deny_reason_code, "NO_CAPABILITY")
		self.assertEqual(rows[0].access_policy_version, kb.ACCESS_POLICY_VERSION)
		self.assertEqual(rows[0].level, "Retrieval")

	def test_proxy_attempt_by_normal_user_is_logged(self):
		h.as_user(CHP)
		with self.assertRaises(frappe.PermissionError):
			kb.search("cholera", audience="Surveillance Officer", correlation_id="cid-proxy-1")
		frappe.set_user("Administrator")
		self.assertEqual(h.logs(correlation_id="cid-proxy-1")[0].deny_reason_code, "PREVIEW_NOT_ALLOWED")

	def test_allowed_search_logs_passages_and_config(self):
		with h.kb_sandbox():
			h.add_document("Cholera guide", "# Cholera\nGive oral rehydration solution and refer to the facility.",
				applied_to="CHP")
			h.as_user(CHP)
			r = kb.search("cholera oral rehydration", correlation_id="cid-ok-1")
			frappe.set_user("Administrator")
		self.assertTrue(r["results"])
		self.assertEqual(r["correlation_id"], "cid-ok-1")
		row = frappe.get_doc("Chatbot Query Log", r["log_id"])
		self.assertEqual(row.access_decision, "ALLOW")
		self.assertEqual(row.outcome, "Matched")
		self.assertEqual(row.matched_document, r["results"][0]["doc"])
		self.assertIn("CHP", row.audience_roles)
		self.assertTrue(row.retrieval_config)
		self.assertTrue(frappe.parse_json(row.passages))

	def test_ask_without_llm_logs_conversation(self):
		with h.kb_sandbox(kb_llm_url="http://127.0.0.1:9"):
			h.add_document("Measles guide", "# Measles\nIsolate the child and notify the surveillance officer.",
				applied_to="CHP")
			h.as_user(CHP)
			r = kb.ask("measles isolate child", channel="Web")
			frappe.set_user("Administrator")
		row = frappe.get_doc("Chatbot Query Log", r["log_id"])
		self.assertEqual(row.level, "Conversation")
		self.assertEqual(row.user, CHP)
		self.assertIn(row.outcome, ("Matched", "No Match"))
		self.assertEqual(row.answer, r["answer"])

	def test_feedback_only_by_asker(self):
		name = chatbot_log.log(level="Conversation", user=CHP, query_text="q", outcome="Matched", channel="Web")
		h.as_user(OFFICER)
		with self.assertRaises(frappe.PermissionError):
			chatbot_log.submit_feedback(name, 1)
		h.as_user(CHP)
		chatbot_log.submit_feedback(name, 0, "not what I needed")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Chatbot Query Log", name, "feedback_helpful"), "No")

	def test_escalation_workflow_needs_capability(self):
		name = chatbot_log.log(level="Conversation", user=CHP, query_text="q", outcome="Escalated",
			escalated_to_human=1, channel="WhatsApp")
		self.assertEqual(frappe.db.get_value("Chatbot Query Log", name, "escalation_status"), "Open")
		h.as_user(CHP)
		with self.assertRaises(frappe.PermissionError):
			chatbot_log.update_escalation(name, "Answered", "x")
		h.as_user(OFFICER)
		r = chatbot_log.update_escalation(name, "Answered", "Called the CHP back")
		self.assertEqual(r["escalationStatus"], "Answered")

	def test_metrics_targets(self):
		for outcome in ["Matched", "Matched", "Matched", "No Match"]:
			chatbot_log.log(level="Conversation", user=CHP, query_text="metric q", outcome=outcome, channel="USSD",
				escalated_to_human=1 if outcome == "No Match" else 0)
		chatbot_log.log(level="Conversation", user=CHP, query_text="report", outcome="Routed", channel="USSD")
		h.as_user(OFFICER)
		m = chatbot_log.get_metrics(channel="USSD")
		self.assertEqual(m["guidance_questions"], 4)
		self.assertEqual(m["match_rate"], 75.0)
		self.assertEqual(m["escalation_rate"], 25.0)
		h.as_user(CHP)
		with self.assertRaises(frappe.PermissionError):
			chatbot_log.get_metrics()

	def test_service_exchange_logging(self):
		req = {"message": "cholera?", "roles": ["Guest"], "language": "en", "user_ref": "whatsapp:+254711",
			"request_id": "cid-wa-1"}
		resp = {"outcome": "escalate", "reason": "no_match", "message": "Passed to the team", "escalate": True}
		name = chatbot_log.log_conversation(req, resp, channel="WhatsApp", escalated_to="+254700")
		row = frappe.get_doc("Chatbot Query Log", name)
		self.assertEqual((row.outcome, row.actor_class, row.escalation_status), ("Escalated", "Public", "Open"))
		self.assertEqual(chatbot_log.find_by_correlation("cid-wa-1"), name)

	def test_service_exchange_records_actor_class_and_policy(self):
		"""SDS B.4.2.3: a Conversation row says who asked and which access policy applied."""
		req = {"message": "cholera?", "roles": ["Community Health Promoter"], "user_ref": "someone@example.org"}
		resp = {"outcome": "clarify", "message": "Did you mean?"}
		row = frappe.get_doc("Chatbot Query Log", chatbot_log.log_conversation(req, resp, channel="Web"))
		self.assertEqual(row.actor_class, "Staff")
		self.assertEqual(row.access_policy_version, kb.ACCESS_POLICY_VERSION)
		named = chatbot_log.log_conversation(req, resp, channel="Web", actor_class="Community Health Worker")
		self.assertEqual(frappe.db.get_value("Chatbot Query Log", named, "actor_class"), "Community Health Worker")

	def test_logging_never_breaks_answering(self):
		with patch.object(frappe, "get_doc", side_effect=Exception("db down")):
			self.assertIsNone(chatbot_log.log(level="Conversation", query_text="x", outcome="Matched"))

	def test_retention_purge(self):
		name = chatbot_log.log(level="Conversation", query_text="old", outcome="Matched", channel="SMS")
		frappe.db.set_value("Chatbot Query Log", name, "creation", "2020-01-01 00:00:00", update_modified=False)
		frappe.conf["chatbot_log_retention_days"] = 30
		try:
			self.assertGreaterEqual(chatbot_log.purge_old_logs(), 1)
		finally:
			frappe.conf.pop("chatbot_log_retention_days", None)
		self.assertFalse(frappe.db.exists("Chatbot Query Log", name))
