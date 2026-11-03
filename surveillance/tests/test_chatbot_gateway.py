"""KB-17 / KB-18 / KB-T4: one Frappe chat path, the protocol corpus and reload (chatbot contract §2-§4)."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from surveillance.chatbot import api
from surveillance.kb_access import KBAccessDenied
from surveillance.tests import kb_helpers as h

CHP = "kbt-gw-chp@example.com"
SUSPENDED = "kbt-gw-suspended@example.com"
SERVICE = "kbt-gw-service@example.com"
OFFICER = "kbt-gw-officer@example.com"


class _Client:
	def __init__(self, response=None, error=None):
		self.response, self.error, self.req = response, error, None

	def ask(self, req):
		self.req = req
		if self.error:
			raise self.error
		return self.response


class TestChatbotGateway(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("Surveillance Officer", ["use_knowledge_base", "view_reports"])
		h.ensure_role("KBT Service", ["use_knowledge_base", "kb_service"])
		h.user(CHP, "CHP", "KBT Region A")
		h.user(SUSPENDED, "CHP", "KBT Region A", status="Suspended")
		h.user(SERVICE, "KBT Service")
		h.user(OFFICER, "Surveillance Officer", "KBT Region A")
		cls.region = h.region("KBT Region A")
		cls.disease = frappe.get_all("Alert Threshold Config", filters={"is_active": 1}, pluck="name", limit=1)[0]
		frappe.db.commit()   # tearDown rolls back each test; the fixtures must survive that

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		# log writes commit, so test protocols may have been committed with them: never leave them in the corpus
		for name in frappe.get_all("Response Protocol", filters={"title": "KBT Protocol"}, pluck="name"):
			frappe.delete_doc("Response Protocol", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def _protocol(self, status="Approved", **kw):
		p = frappe.get_doc({
			"doctype": "Response Protocol", "title": "KBT Protocol", "disease": self.disease, "status": status,
			"version": "v1", "source": "IDSR Technical Guidelines", "summary": "Act fast.",
			"approved_by": "Administrator" if status == "Approved" else None,
			"approved_on": now_datetime() if status == "Approved" else None,
			"verification_questions": [{"question": "Three or more loose stools in 24 hours", "kind": "Case definition"}],
			"steps": [
				{"step": "Isolate the patient", "phase": "Investigation", "timeframe": "Immediately"},
				{"step": "Refer to the health facility", "phase": "Investigation", "action_stage": "referral"},
				{"step": "Hold a community meeting", "phase": "Response"},
			],
			**kw,
		})
		p.insert(ignore_permissions=True)
		return p

	# ---- corpus (§2) ----
	def test_corpus_records_follow_the_contract(self):
		p = self._protocol(audience="CHP, Surveillance Officer", location_applicability="KBT Region A",
			icd11=[{"code": "1A00", "title": "Cholera", "uri": "http://id.who.int/icd/entity/257068234"}])
		recs = {r["action_stage"]: r for r in api.protocol_records(p)}
		self.assertEqual(set(recs), {"case_definition", "immediate_action", "referral", "community_action"})
		r = recs["immediate_action"]
		self.assertEqual((r["status"], r["language"], r["audience"]), ("active", "en", ["CHP", "Surveillance Officer"]))
		self.assertEqual(r["location_applicability"], [self.region])
		self.assertIn("Isolate the patient (Immediately)", r["approved_content"])
		self.assertTrue(r["approved_by"] and r["approval_date"] and r["source_section"] and r["source_version"])
		self.assertEqual(r["icd11"][0]["code"], "1A00")
		keys = [(x["protocol_id"], x["language"], x["source_version"]) for x in recs.values()]
		self.assertEqual(len(keys), len(set(keys)))

	def test_only_serving_protocols_leave_frappe(self):
		self.assertEqual(api.protocol_records(self._protocol(status="Draft")), [])
		self.assertEqual(api.protocol_records(self._protocol(effective_date=add_days(today(), 3))), [])
		self.assertEqual(api.protocol_records(self._protocol(review_date=add_days(today(), -1))), [])

	def test_corpus_is_for_the_service_only(self):
		h.as_user(OFFICER)
		with self.assertRaises(KBAccessDenied):
			api.get_retrieval_corpus()
		h.as_user(SERVICE)
		body = api.get_retrieval_corpus()
		self.assertIn("stage_keywords", body["aliases"])
		self.assertIn(self.disease, body["aliases"]["diseases"])
		self.assertIn("escalation_contact", body["settings"])

	def test_protocol_changes_request_a_reload(self):
		frappe.flags.chatbot_reload_requested = False
		p = self._protocol(status="Draft")
		self.assertFalse(frappe.flags.chatbot_reload_requested)
		p.status, p.approved_by, p.approved_on = "Approved", "Administrator", now_datetime()
		p.save(ignore_permissions=True)
		self.assertTrue(frappe.flags.chatbot_reload_requested)
		frappe.flags.chatbot_reload_requested = False
		p.status = "Retired"
		p.save(ignore_permissions=True)
		self.assertTrue(frappe.flags.chatbot_reload_requested)

	# ---- asking (§3) ----
	def test_request_is_built_from_frappe_records(self):
		client = _Client({"outcome": "answer", "message": "Do this.", "protocol": {"protocol_id": "x"},
			"trace": {"secret": 1}, "confidence": 0.9, "documents": []})
		with patch.object(api, "_client", lambda: client):
			h.as_user(CHP)
			out = api.ask("what do I do for cholera?", language="Kiswahili")
		self.assertEqual(client.req["roles"], ["CHP"])
		self.assertEqual((client.req["location"], client.req["language"], client.req["user_ref"]),
			(self.region, "sw", CHP))
		self.assertNotIn("trace", out)
		self.assertNotIn("confidence", out)
		row = frappe.get_doc("Chatbot Query Log", out["log_id"])
		self.assertEqual((row.channel, row.user, row.outcome), ("Web", CHP, "Matched"))

	def test_inactive_and_guest_are_refused_and_logged(self):
		with patch.object(api, "_client", lambda: _Client({"outcome": "answer"})):
			h.as_user(SUSPENDED)
			with self.assertRaises(KBAccessDenied) as e:
				api.ask("hello")
		self.assertEqual(e.exception.code, "ACCOUNT_INACTIVE")
		frappe.set_user("Administrator")
		row = h.logs(user=SUSPENDED, route="chat")[0]
		self.assertEqual((row.access_decision, row.deny_reason_code), ("DENY", "ACCOUNT_INACTIVE"))

	def test_service_outage_gives_fixed_reply_and_escalates(self):
		with patch.object(api, "_client", lambda: _Client(error=TimeoutError("timed out"))):
			h.as_user(CHP)
			out = api.ask_mobile("what do I do?")
		self.assertEqual((out["outcome"], out["escalate"]), ("escalate", True))
		self.assertIn("not available right now", out["message"])
		row = frappe.get_doc("Chatbot Query Log", out["log_id"])
		self.assertEqual((row.channel, row.outcome, row.escalated_to_human), ("Mobile", "Error", 1))

	def test_escalation_opens_a_record(self):
		with patch.object(api, "_client", lambda: _Client({"outcome": "escalate", "reason": "no_match",
				"message": "Passed on.", "escalate": True})):
			h.as_user(CHP)
			out = api.ask("something unknown")
		self.assertEqual(frappe.db.get_value("Chatbot Query Log", out["log_id"], "escalation_status"), "Open")

	# ---- counts (§3a) ----
	def test_count_query_validation(self):
		ok = {"doctype": "Case Report", "filters": [["region", "in", ["A"]], ["creation", "between",
			["2026-10-01", "2026-10-07"]]], "group_by": "region"}
		self.assertEqual(api.validate_query(ok)[1], "region")
		for bad in ({"doctype": "User", "filters": []},
				{"doctype": "Case Report", "filters": [["owner", "=", "x"]]},
				{"doctype": "Case Report", "filters": [["region", "like", "%"]]},
				{"doctype": "Case Report", "filters": [], "group_by": "owner"},
				{"doctype": "Case Report", "filters": [["creation", "between", ["yesterday", "today"]]]}):
			with self.assertRaises(ValueError):
				api.validate_query(bad)

	def test_count_runs_as_the_user(self):
		resp = {"outcome": "count", "route": "report_count", "message": "There are {count} reports.",
			"query": {"doctype": "Case Report", "filters": [], "group_by": None}}
		with patch.object(api, "_client", lambda: _Client(dict(resp))):
			h.as_user(OFFICER)
			out = api.ask("how many reports?")
			expected = frappe.get_list("Case Report", fields=["count(name) as count"])[0]["count"]
		self.assertEqual(out["message"], f"There are {expected} reports.")
		with patch.object(api, "_client", lambda: _Client(dict(resp))):
			h.as_user(CHP)   # no view_reports
			out = api.ask("how many reports?")
		self.assertIn("could not count", out["message"])
