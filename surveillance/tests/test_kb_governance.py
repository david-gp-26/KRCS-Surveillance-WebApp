"""KB-7 / KB-8: approved content is frozen, bound to its file, versioned, approved by someone else, and retired
rather than deleted once served (SRS R60, R62; SDS ContentVersion / ApprovedBy)."""
import frappe
from frappe.tests.utils import FrappeTestCase

from surveillance import knowledge_base as kb
from surveillance.kb_access import KBAccessDenied
from surveillance.tests import kb_helpers as h

EDITOR = "kbt-gov-editor@example.com"
APPROVER = "kbt-gov-approver@example.com"
OFFICER = "kbt-gov-officer@example.com"
CHP = "kbt-gov-chp@example.com"
WORDS = "measles rash fever cough vaccination"


class TestKBGovernance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("KBT Gov Editor", ["manage_knowledge_base", "approve_knowledge_base"])
		h.ensure_role("KBT Gov Approver", ["approve_knowledge_base", "manage_knowledge_base"])
		h.ensure_role("Surveillance Officer", ["use_knowledge_base"])
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.user(EDITOR, "KBT Gov Editor")
		h.user(APPROVER, "KBT Gov Approver")
		h.user(OFFICER, "Surveillance Officer")
		h.user(CHP, "CHP")
		cls.sandbox = h.kb_sandbox()
		cls.sandbox.__enter__()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.sandbox.__exit__(None, None, None)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.conf.pop("kb_allow_self_approval", None)

	# helpers
	def _upload(self, title, text, **meta):
		h.as_user(EDITOR)
		try:
			return h.add_document(title, text, approve=False, **meta)
		finally:
			frappe.set_user("Administrator")

	def _approve(self, name, user=APPROVER):
		h.as_user(user)
		try:
			return kb.set_approval(name, "Approved")
		finally:
			frappe.set_user("Administrator")

	def _visible_to(self, user, name):
		h.as_user(user)
		try:
			return name in {r["doc"] for r in kb.search(WORDS, limit=20)["results"]}
		finally:
			frappe.set_user("Administrator")

	# ---- hash binding ----
	def test_upload_records_hash_and_family(self):
		name = self._upload("Hash doc", f"# H\n{WORDS} hash")
		doc = frappe.get_doc(kb.DOCTYPE, name)
		self.assertEqual(len(doc.content_hash), 64)
		self.assertEqual(doc.document_family, name)
		self._approve(name)
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, name, "approved_hash"), doc.content_hash)

	def test_swapped_file_cannot_be_reindexed_under_old_approval(self):
		# unique text: Frappe shares one stored file between uploads with identical content
		name = self._upload("Swap doc", f"# S\n{WORDS} original swap {frappe.generate_hash(length=8)}")
		self._approve(name)
		path = frappe.get_doc("File", {"file_url": frappe.db.get_value(kb.DOCTYPE, name, "file")}).get_full_path()
		with open(path, "w") as f:
			f.write(f"# S\n{WORDS} swapped text nobody approved")
		h.as_user(EDITOR)
		with self.assertRaises(frappe.ValidationError):
			kb.reindex_document(name)
		frappe.set_user("Administrator")
		kb.index_document(name)   # a queued job hitting the same check
		doc = frappe.get_doc(kb.DOCTYPE, name)
		self.assertEqual(doc.status, "Failed")
		self.assertIn("changed after approval", doc.error)
		# what is served is still the approved text
		h.as_user(OFFICER)
		texts = [r["text"] for r in kb.search(WORDS, limit=20)["results"] if r["doc"] == name]
		frappe.set_user("Administrator")
		self.assertTrue(texts and all("swapped" not in t for t in texts))

	# ---- frozen approved metadata ----
	def test_widening_access_returns_to_draft_until_reapproved(self):
		name = self._upload("Widen doc", f"# W\n{WORDS} widen", applied_to="Surveillance Officer")
		self._approve(name)
		self.assertTrue(self._visible_to(OFFICER, name))
		self.assertFalse(self._visible_to(CHP, name))
		h.as_user(EDITOR)
		row = kb.update_document(name, applied_to="Surveillance Officer, CHP")
		frappe.set_user("Administrator")
		self.assertEqual(row["approvalStatus"], "draft")
		self.assertIn("applied_to", row["governanceNote"])
		self.assertFalse(self._visible_to(CHP, name))
		self.assertFalse(self._visible_to(OFFICER, name))
		self._approve(name)
		self.assertTrue(self._visible_to(CHP, name))

	def test_dates_and_same_values_do_not_unapprove(self):
		name = self._upload("Dates doc", f"# D\n{WORDS} dates", applied_to="CHP, Surveillance Officer")
		self._approve(name)
		h.as_user(EDITOR)
		row = kb.update_document(name, applied_to=["Surveillance Officer", "CHP"], review_date=frappe.utils.add_days(
			frappe.utils.today(), 90))
		frappe.set_user("Administrator")
		self.assertEqual(row["approvalStatus"], "approved")

	# ---- separation of duties ----
	def test_uploader_cannot_approve_own_document(self):
		name = self._upload("Self doc", f"# Self\n{WORDS} self")
		with self.assertRaises(KBAccessDenied) as e:
			self._approve(name, EDITOR)
		self.assertEqual(e.exception.code, "SELF_APPROVAL")
		frappe.conf["kb_allow_self_approval"] = 1
		self.assertEqual(self._approve(name, EDITOR)["approvalStatus"], "approved")

	# ---- versions ----
	def test_version_format(self):
		with self.assertRaises(frappe.ValidationError):
			self._upload("Bad version", f"# V\n{WORDS} version", version="final-2")

	def test_new_version_supersedes_the_old_one(self):
		v1 = self._upload("Family v1", f"# F\n{WORDS} family one", version="v1.0")
		self._approve(v1)
		v2 = self._upload("Family v2", f"# F\n{WORDS} family two", version="v2.0", supersedes=v1)
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, v2, "document_family"), v1)
		with self.assertRaises(frappe.ValidationError):
			self._upload("Family dup", f"# F\n{WORDS} family dup", version="v2.0", supersedes=v1)
		self.assertTrue(self._visible_to(OFFICER, v1))
		row = self._approve(v2)
		self.assertEqual(row["retiredVersions"], [v1])
		old = frappe.get_doc(kb.DOCTYPE, v1)
		self.assertEqual((old.approval_status, old.superseded_by), ("Retired", v2))
		self.assertFalse(self._visible_to(OFFICER, v1))
		self.assertTrue(self._visible_to(OFFICER, v2))

	# ---- retire, don't delete ----
	def test_served_documents_are_retired_not_deleted(self):
		served = self._upload("Served doc", f"# Sv\n{WORDS} served")
		self._approve(served)
		h.as_user(EDITOR)
		r = kb.delete_document(served)
		frappe.set_user("Administrator")
		self.assertEqual(r["retired"], served)
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, served, "approval_status"), "Retired")
		self.assertFalse(self._visible_to(OFFICER, served))

	def test_never_approved_draft_is_deleted(self):
		draft = self._upload("Draft doc", f"# Dr\n{WORDS} draft")
		h.as_user(EDITOR)
		r = kb.delete_document(draft)
		frappe.set_user("Administrator")
		self.assertEqual(r, {"deleted": draft})
		self.assertFalse(frappe.db.exists(kb.DOCTYPE, draft))
