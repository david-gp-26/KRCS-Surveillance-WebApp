"""KB-4: scope hierarchy with inheritance (SRS R62: National -> County -> operational area -> Sub-county/Camp)."""
import frappe
from frappe.tests.utils import FrappeTestCase

from surveillance import kb_access
from surveillance import knowledge_base as kb
from surveillance.tests import kb_helpers as h

SUB_USER = "kbt-sc-sub@example.com"
REGION_USER = "kbt-sc-region@example.com"
NO_UNIT = "kbt-sc-nounit@example.com"
NATIONAL = "kbt-sc-national@example.com"
EDITOR = "kbt-sc-editor@example.com"
WORDS = "mpox lesions isolation contact tracing"


def _sub_county(name, county, region):
	existing = frappe.db.get_value("Sub County", {"sub_county_name": name, "region": region}, "name")
	if existing:
		return existing
	return frappe.get_doc({"doctype": "Sub County", "sub_county_name": name, "county": county, "region": region,
		"is_active": 1}).insert(ignore_permissions=True).name


class TestKBScope(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.r1, cls.r2 = h.region("KBT Scope R1"), h.region("KBT Scope R2")
		cls.s1a = _sub_county("KBT S1a", "KBT County", cls.r1)
		cls.s1b = _sub_county("KBT S1b", "KBT County", cls.r1)
		h.ensure_role("Surveillance Officer", ["use_knowledge_base"])
		h.ensure_role("KBT National Officer", ["use_knowledge_base", "kb_national_scope"])
		h.ensure_role("KBT Scope Editor", ["manage_knowledge_base"])
		h.user(SUB_USER, "Surveillance Officer", "KBT Scope R1", sub_county=cls.s1a)
		h.user(REGION_USER, "Surveillance Officer", "KBT Scope R1", sub_county="")
		h.user(NO_UNIT, "Surveillance Officer", sub_county="")
		h.user(NATIONAL, "KBT National Officer", sub_county="")
		h.user(EDITOR, "KBT Scope Editor")
		cls.sandbox = h.kb_sandbox()
		cls.sandbox.__enter__()
		all_ = "All roles"
		cls.docs = {
			"national": h.add_document("Nat", f"# N\n{WORDS} national", applied_to=all_),
			"r1": h.add_document("R1", f"# R1\n{WORDS} regional one", applied_to=all_, regions=cls.r1),
			"s1a": h.add_document("S1a", f"# S1a\n{WORDS} camp a", applied_to=all_, regions=cls.r1, sub_counties=cls.s1a),
			"s1b": h.add_document("S1b", f"# S1b\n{WORDS} camp b", applied_to=all_, regions=cls.r1, sub_counties=cls.s1b),
			"r2": h.add_document("R2", f"# R2\n{WORDS} regional two", applied_to=all_, regions=cls.r2),
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

	def test_sub_county_user_inherits_upwards_only(self):
		self.assertEqual(self._docs(SUB_USER), {"national", "r1", "s1a"})

	def test_region_user_sees_their_sub_counties(self):
		self.assertEqual(self._docs(REGION_USER), {"national", "r1", "s1a", "s1b"})

	def test_no_unit_is_not_national(self):
		# before KB-4 a user without a region saw every region
		self.assertEqual(self._docs(NO_UNIT), {"national"})
		self.assertEqual(self._docs(NATIONAL), set(self.docs))

	def test_editor_region_preview_uses_the_hierarchy(self):
		self.assertEqual(self._docs(EDITOR, region=self.r1), {"national", "r1", "s1a", "s1b"})

	def test_unit_scopes(self):
		tokens = kb_access.unit_scopes(sub_county=self.s1a)
		self.assertIn(f"region:{self.r1}", tokens)
		self.assertIn("county:KBT County", tokens)
		self.assertNotIn(f"subcounty:{self.s1b}", tokens)

	def test_sub_county_must_be_inside_the_regions(self):
		with self.assertRaises(frappe.ValidationError):
			kb.update_document(self.docs["r2"], sub_counties=self.s1a)

	def test_passage_by_id_respects_scope(self):
		h.as_user(REGION_USER)
		hit = next(x for x in kb.search(WORDS, limit=20)["results"] if x["doc"] == self.docs["s1b"])
		h.as_user(SUB_USER)
		with self.assertRaises(frappe.DoesNotExistError):
			kb.get_passage(hit["id"])
