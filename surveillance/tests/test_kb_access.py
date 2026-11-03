"""KB-1, KB-2, KB-5: server-side access decision before retrieval (SRS R62, R63, R72).

Each case asks a real Qdrant collection (fake embeddings) and checks exactly which documents come back.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from surveillance import knowledge_base as kb
from surveillance.kb_access import KBAccessDenied
from surveillance.tests import kb_helpers as h

CHP_A = "kbt-acc-chp-a@example.com"
CHP_B = "kbt-acc-chp-b@example.com"
OFFICER_A = "kbt-acc-officer-a@example.com"
SUSPENDED = "kbt-acc-suspended@example.com"
DISABLED = "kbt-acc-disabled@example.com"
EDITOR = "kbt-acc-editor@example.com"
SERVICE = "kbt-acc-service@example.com"
NO_CAP = "kbt-acc-nocap@example.com"
WORDS = "cholera oral rehydration refer facility"


class TestKBAccess(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("Surveillance Officer", ["use_knowledge_base"])
		h.ensure_role("KBT Editor", ["manage_knowledge_base"])
		h.ensure_role("KBT Service", ["use_knowledge_base", "kb_service"])
		h.ensure_role("KBT Plain", [])
		h.user(CHP_A, "CHP", "KBT Region A")
		h.user(CHP_B, "CHP", "KBT Region B")
		h.user(OFFICER_A, "Surveillance Officer", "KBT Region A")
		h.user(SUSPENDED, "CHP", "KBT Region A", status="Suspended")
		h.user(DISABLED, "CHP", "KBT Region A", enabled=0)
		h.user(EDITOR, "KBT Editor")
		h.user(SERVICE, "KBT Service")
		h.user(NO_CAP, "KBT Plain", "KBT Region A")
		cls.region_a = h.region("KBT Region A")
		cls.region_b = h.region("KBT Region B")
		cls.sandbox = h.kb_sandbox()
		cls.sandbox.__enter__()
		yesterday, tomorrow = add_days(today(), -1), add_days(today(), 1)
		cls.docs = {
			"chp": h.add_document("CHP cholera", f"# CHP\n{WORDS} chp", applied_to="CHP"),
			"officer": h.add_document("Officer cholera", f"# Officer\n{WORDS} officer", applied_to="Surveillance Officer"),
			"all": h.add_document("All cholera", f"# All\n{WORDS} everyone", applied_to="All roles"),
			"region_a": h.add_document("Region A cholera", f"# A\n{WORDS} region a", applied_to="CHP",
				regions=cls.region_a),
			"region_b": h.add_document("Region B cholera", f"# B\n{WORDS} region b", applied_to="CHP",
				regions=cls.region_b),
			"draft": h.add_document("Draft cholera", f"# Draft\n{WORDS} draft", applied_to="All roles", approve=False),
			"future": h.add_document("Future cholera", f"# Future\n{WORDS} future", applied_to="All roles",
				effective_from=tomorrow),
			"expired": h.add_document("Expired cholera", f"# Expired\n{WORDS} expired", applied_to="All roles",
				expiry_date=yesterday),
			"review_past": h.add_document("Review past cholera", f"# Review\n{WORDS} review", applied_to="All roles",
				review_date=yesterday),
		}

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.sandbox.__exit__(None, None, None)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")


	def _docs(self, user, **kw):
		h.as_user(user)
		try:
			r = kb.search(WORDS, limit=20, **kw)
		finally:
			frappe.set_user("Administrator")
		names = {v: k for k, v in self.docs.items()}
		return {names[x["doc"]] for x in r["results"] if x["doc"] in names}

	def _denied(self, user, code, **kw):
		h.as_user(user)
		try:
			with self.assertRaises(KBAccessDenied) as e:
				kb.search(WORDS, **kw)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(e.exception.code, code)

	# ---- direct users ----
	def test_chp_sees_own_audience_region_and_all(self):
		self.assertEqual(self._docs(CHP_A), {"chp", "all", "region_a"})

	def test_other_region_and_role(self):
		self.assertEqual(self._docs(CHP_B), {"chp", "all", "region_b"})
		self.assertEqual(self._docs(OFFICER_A), {"officer", "all"})

	def test_drafts_and_out_of_date_never_served(self):
		for user in (CHP_A, OFFICER_A):
			self.assertFalse({"draft", "future", "expired", "review_past"} & self._docs(user))

	def test_inactive_and_capability(self):
		self._denied(SUSPENDED, "ACCOUNT_INACTIVE")
		self._denied(NO_CAP, "NO_CAPABILITY")

	def test_normal_user_cannot_proxy(self):
		self._denied(CHP_A, "PREVIEW_NOT_ALLOWED", audience="Surveillance Officer")
		self._denied(CHP_A, "PROXY_NOT_ALLOWED", on_behalf_of=OFFICER_A)

	# ---- chatbot service ----
	def test_service_resolves_named_user(self):
		self.assertEqual(self._docs(SERVICE, on_behalf_of=CHP_A), {"chp", "all", "region_a"})
		self.assertEqual(self._docs(SERVICE, on_behalf_of=OFFICER_A), {"officer", "all"})

	def test_service_claims_are_ignored(self):
		# the service says "officer, every region" but names a CHP: the CHP's scope wins (R63)
		got = self._docs(SERVICE, on_behalf_of=CHP_A, audience="Surveillance Officer", region=self.region_b)
		self.assertEqual(got, {"chp", "all", "region_a"})

	def test_service_named_user_must_be_active(self):
		self._denied(SERVICE, "ACCOUNT_INACTIVE", on_behalf_of=SUSPENDED)
		self._denied(SERVICE, "ACCOUNT_INACTIVE", on_behalf_of=DISABLED)
		self._denied(SERVICE, "USER_UNKNOWN", on_behalf_of="nobody-here@example.com")
		self._denied(SERVICE, "NO_CAPABILITY", on_behalf_of=NO_CAP)

	def test_public_actor_needs_public_guidance(self):
		saved = frappe.conf.get("kb_public_enabled")
		frappe.conf["kb_public_enabled"] = 0
		try:
			self._denied(SERVICE, "PUBLIC_NOT_ENABLED", on_behalf_of="whatsapp:+254799000111")
		finally:
			frappe.conf["kb_public_enabled"] = saved

	def test_legacy_audience_contract_refused(self):
		h.as_user(SERVICE)
		try:
			with self.assertRaises(frappe.ValidationError):
				kb.search(WORDS, audience="CHP")
		finally:
			frappe.set_user("Administrator")

	def test_unknown_audience_role_does_not_fail_preview(self):
		got = self._docs(EDITOR, audience="CHP,System Manager,Not A Role")
		self.assertIn("chp", got)

	# ---- editors (administrative separation, KB-5) ----
	def test_editor_without_preview_searches_as_themselves(self):
		self.assertEqual(self._docs(EDITOR), {"all"})

	def test_editor_preview_is_explicit_and_logged(self):
		got = self._docs(EDITOR, preview=1)
		self.assertTrue({"chp", "officer", "all", "region_a", "region_b"} <= got)
		self.assertNotIn("draft", got)
		self.assertIn("draft", self._docs(EDITOR, include_drafts=1))
		row = h.logs(caller=EDITOR)[0]
		self.assertEqual((row.preview, row.actor_class), (1, "Editor preview"))

	# ---- dates ----
	def test_review_date_rule_is_configurable(self):
		frappe.db.set_value(kb.DOCTYPE, self.docs["review_past"], "approval_status", "Approved")
		frappe.conf["kb_hide_after_review_date"] = 0
		try:
			kb._sync_access(frappe.get_doc(kb.DOCTYPE, self.docs["review_past"]))
			self.assertIn("review_past", self._docs(OFFICER_A))
		finally:
			frappe.conf.pop("kb_hide_after_review_date", None)
		kb._sync_access(frappe.get_doc(kb.DOCTYPE, self.docs["review_past"]))
		self.assertNotIn("review_past", self._docs(OFFICER_A))

	def test_effective_from_after_expiry_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			kb.update_document(self.docs["all"], effective_from=add_days(today(), 10), expiry_date=add_days(today(), 5))

	def test_retire_expired_includes_review_date(self):
		kb.retire_expired()
		# regression: documents with no expiry / review date are never retired (ifnull(date, 0001-01-01) < today)
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, self.docs["all"], "approval_status"), "Approved")
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, self.docs["chp"], "approval_status"), "Approved")
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, self.docs["review_past"], "approval_status"), "Retired")
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, self.docs["expired"], "approval_status"), "Retired")

	# ---- passages ----
	def test_passage_by_id_rechecks_access(self):
		h.as_user(OFFICER_A)
		r = kb.search(WORDS, limit=20)
		officer_hit = next(x for x in r["results"] if x["doc"] == self.docs["officer"])
		h.as_user(CHP_A)
		with self.assertRaises(frappe.DoesNotExistError):
			kb.get_passage(officer_hit["id"], correlation_id="cid-pass-1")
		frappe.set_user("Administrator")
		row = h.logs(correlation_id="cid-pass-1")[0]
		self.assertEqual((row.access_decision, row.deny_reason_code), ("DENY", "NOT_VISIBLE"))

	def test_proxied_log_names_end_user(self):
		h.as_user(SERVICE)
		r = kb.search(WORDS, on_behalf_of=CHP_A, correlation_id="cid-obo-1")
		frappe.set_user("Administrator")
		row = frappe.get_doc("Chatbot Query Log", r["log_id"])
		self.assertEqual((row.user, row.caller, row.access_policy_version), (CHP_A, SERVICE, kb.ACCESS_POLICY_VERSION))
