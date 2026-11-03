"""KB-3 / KB-14 / KB-T2: audience classes, sensitivity and the public guidance boundary (SRS R62, R73-R77)."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from surveillance import kb_safety
from surveillance import knowledge_base as kb
from surveillance.tests import kb_helpers as h

CHP = "kbt-aud-chp@example.com"
OFFICER = "kbt-aud-officer@example.com"
OFFICER_SENS = "kbt-aud-officer-sens@example.com"
LEAD = "kbt-aud-lead@example.com"
EDITOR = "kbt-aud-editor@example.com"
SERVICE = "kbt-aud-service@example.com"
PUBLIC = "whatsapp:+254799000222"
WORDS = "diarrhoea watery stool drink water clean hands"


class TestKBAudience(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("Surveillance Officer", ["use_knowledge_base"])
		h.ensure_role("KBT Sensitive Officer", ["use_knowledge_base", "view_sensitive_kb"])
		h.ensure_role("KBT Lead", ["use_knowledge_base", "view_restricted_kb"])
		h.ensure_role("KBT Editor", ["manage_knowledge_base"])
		h.ensure_role("KBT Service", ["use_knowledge_base", "kb_service"])
		h.user(CHP, "CHP")
		h.user(OFFICER, "Surveillance Officer")
		h.user(OFFICER_SENS, "KBT Sensitive Officer")
		h.user(LEAD, "KBT Lead")
		h.user(EDITOR, "KBT Editor")
		h.user(SERVICE, "KBT Service")
		# earlier runs' public rows point at documents the sandbox has since deleted
		frappe.db.delete("Chatbot Query Log", {"user_ref": PUBLIC})
		frappe.db.commit()
		cls.sandbox = h.kb_sandbox(kb_public_enabled=1)
		cls.sandbox.__enter__()
		all_ = "All roles"
		cls.docs = {
			"public": h.add_document("Public diarrhoea", f"# Home care\n{WORDS} public keep drinking ORS",
				applied_to=all_, audience_class="Public"),
			"public_unsafe": h.add_document("Public unsafe", f"# Treatment\n{WORDS} unsafe take 500 mg amoxicillin",
				applied_to=all_, audience_class="Public"),
			"chw": h.add_document("CHW diarrhoea", f"# CHW\n{WORDS} chw", applied_to=all_),
			"professional": h.add_document("Professional diarrhoea", f"# Officer\n{WORDS} professional",
				applied_to=all_, audience_class="Professional"),
			"restricted": h.add_document("Restricted diarrhoea", f"# Line list\n{WORDS} restricted",
				applied_to=all_, audience_class="Restricted"),
			"sensitive": h.add_document("Sensitive diarrhoea", f"# Sensitive\n{WORDS} sensitive",
				applied_to=all_, audience_class="Professional", sensitivity="Sensitive"),
		}

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.sandbox.__exit__(None, None, None)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _search(self, user, **kw):
		h.as_user(user)
		try:
			return kb.search(WORDS, limit=20, **kw)
		finally:
			frappe.set_user("Administrator")

	def _docs(self, user, **kw):
		names = {v: k for k, v in self.docs.items()}
		return {names[x["doc"]] for x in self._search(user, **kw)["results"] if x["doc"] in names}

	# ---- audience classes ----
	def test_public_actor_gets_public_documents_only(self):
		# "All roles" never includes the public; the unsafe public passage is withheld
		r = self._search(SERVICE, on_behalf_of=PUBLIC)
		self.assertEqual({x["doc"] for x in r["results"]}, {self.docs["public"]})
		self.assertEqual(r["actor_class"], "Public")
		self.assertEqual(r["public"]["withheld"], 1)
		self.assertIn("not a diagnosis", r["public"]["reply"])
		self.assertIn("1199", r["public"]["reply"])

	def test_staff_read_up_to_their_class(self):
		self.assertEqual(self._docs(CHP), {"public", "public_unsafe", "chw"})
		self.assertEqual(self._docs(OFFICER), {"public", "public_unsafe", "chw", "professional"})
		self.assertEqual(self._docs(OFFICER_SENS), {"public", "public_unsafe", "chw", "professional", "sensitive"})
		self.assertEqual(self._docs(LEAD), {"public", "public_unsafe", "chw", "professional", "restricted"})

	def test_chw_roles_are_configurable(self):
		frappe.conf["kb_chw_roles"] = "CHP, Surveillance Officer"
		try:
			self.assertNotIn("professional", self._docs(OFFICER))
		finally:
			frappe.conf.pop("kb_chw_roles", None)

	def test_editor_can_preview_the_public_view(self):
		self.assertEqual(self._docs(EDITOR, audience="Public"), {"public"})
		self.assertTrue({"professional", "restricted", "sensitive"} <= self._docs(EDITOR, preview=1))

	def test_passage_by_id_respects_class(self):
		r = self._search(OFFICER)
		prof = next(x for x in r["results"] if x["doc"] == self.docs["professional"])
		h.as_user(CHP)
		with self.assertRaises(frappe.DoesNotExistError):
			kb.get_passage(prof["id"])

	def test_public_document_cannot_be_sensitive(self):
		with self.assertRaises(frappe.ValidationError):
			kb.update_document(self.docs["public"], sensitivity="Sensitive")
		with self.assertRaises(frappe.ValidationError):
			kb.update_document(self.docs["chw"], audience_class="Everyone")

	def test_reclassifying_moves_the_document(self):
		def approve():
			doc = frappe.get_doc(kb.DOCTYPE, self.docs["chw"])
			doc.approval_status = "Approved"
			doc.save(ignore_permissions=True)
			kb._sync_access(doc)
		kb.update_document(self.docs["chw"], audience_class="Professional")
		approve()   # (a reclassified Approved document returns to Draft until approved again: test_kb_governance)
		try:
			self.assertNotIn("chw", self._docs(CHP))
			self.assertIn("chw", self._docs(OFFICER))
		finally:
			kb.update_document(self.docs["chw"], audience_class="Community Health Worker")
			approve()
		self.assertIn("chw", self._docs(CHP))

	# ---- public answers: verbatim template, never generated ----
	def test_public_ask_is_verbatim_and_never_calls_the_llm(self):
		h.as_user(SERVICE)
		with patch.object(kb, "_llm_chat", side_effect=AssertionError("LLM must not run for the public")):
			r = kb.ask(WORDS, on_behalf_of=PUBLIC)
		frappe.set_user("Administrator")
		self.assertEqual(r["mode"], "public")
		self.assertEqual([s["doc"] for s in r["sources"]], [self.docs["public"]])
		self.assertIn("keep drinking ORS", r["answer"])
		self.assertTrue(kb_safety.is_safe(r["answer"]))

	def test_public_only_unsafe_content_escalates(self):
		h.as_user(SERVICE)
		r = kb.search("amoxicillin treatment unsafe", limit=20, on_behalf_of=PUBLIC, category=None)
		frappe.set_user("Administrator")
		self.assertNotIn(self.docs["public_unsafe"], {x["doc"] for x in r["results"]})
		row = frappe.get_doc("Chatbot Query Log", r["log_id"])
		self.assertEqual(row.actor_class, "Public")

	def test_no_restricted_leaks_to_public_in_metrics(self):
		from surveillance.chatbot_log import get_metrics
		self._search(SERVICE, on_behalf_of=PUBLIC)
		self.assertEqual(get_metrics()["public_restricted_leaks"], 0)


class TestKBSafety(FrappeTestCase):
	def test_diagnosis_and_prescription_phrases(self):
		unsafe = [
			"You have cholera.", "This is probably malaria", "Your child has measles",
			"Take 2 tablets of paracetamol", "Give her amoxicillin syrup", "500 mg twice a day",
			"Una kipindupindu", "Umeambukizwa", "Meza vidonge viwili", "vidonge 2 kila siku",
		]
		for text in unsafe:
			self.assertFalse(kb_safety.is_safe(text), text)

	def test_safe_public_guidance(self):
		safe = [
			"Keep drinking ORS and clean water.", "Go to the nearest health facility if the person cannot drink.",
			"Osha mikono kwa sabuni na maji safi.", "Wash hands with soap after using the toilet.",
			"Cholera spreads through dirty water.",
		]
		for text in safe:
			self.assertTrue(kb_safety.is_safe(text), text)

	def test_template_in_kiswahili(self):
		reply = kb_safety.public_reply(["Osha mikono."], "Kiswahili")
		self.assertIn("si utambuzi", reply)
		self.assertIn("Sikupata", kb_safety.public_reply([], "Kiswahili"))
