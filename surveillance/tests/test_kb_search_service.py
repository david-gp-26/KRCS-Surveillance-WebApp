"""The boundary with the krcs_search service: Frappe alone decides access, and a fault there is never a leak or a
silent answer. The engine itself is tested in the krcs_search repo."""
import json
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from surveillance import kb_ops
from surveillance import knowledge_base as kb
from surveillance.tests import kb_helpers as h

CHP = "kbt-svc-chp@example.com"
EDITOR = "kbt-svc-editor@example.com"
QUESTION = "cholera rehydration salts at home"
REAL_SERVICE = kb._search_service   # kb_sandbox replaces it while the tests run


def reply(status=200, body=None):
	r = MagicMock(status_code=status, text=json.dumps(body or {}))
	r.json.return_value = body or {}
	return r


class TestSearchServiceBoundary(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("KBT Svc Editor", ["manage_knowledge_base", "approve_knowledge_base"])
		h.user(CHP, "CHP")
		h.user(EDITOR, "KBT Svc Editor")
		cls.sandbox = h.kb_sandbox()
		cls.sandbox.__enter__()
		cls.visible = h.add_document("Cholera home care", f"# Home care\n\n{QUESTION}, give after each loose stool.\n")

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.sandbox.__exit__(None, None, None)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def _point(self, rank_score=0.9, dense_score=0.8, **changes):
		"""A passage as really indexed for the visible document, with only the named fields changed."""
		found, _next = kb._qdrant().scroll(kb._collection(), scroll_filter=kb._doc_filter(self.visible).filter, limit=1, with_payload=True)
		return {"id": str(found[0].id), "rank_score": rank_score, "dense_score": dense_score,
			"payload": {**found[0].payload, **changes}}

	def _sent(self, user=CHP, **args):
		h.as_user(user)
		with patch.object(kb, "_search_service", wraps=h.fake_search_service) as call:
			out = kb.search(query=QUESTION, **args)
		return out, call.call_args.args[0]

	def test_search_returns_results_through_the_service(self):
		out, _sent = self._sent()
		self.assertEqual(out["results"][0]["doc"], self.visible)
		self.assertTrue(out["results"][0]["confidence"])

	def test_the_service_gets_a_filter_but_no_identity(self):
		_out, sent = self._sent()
		self.assertEqual(set(sent), {"query", "expanded_query", "collection", "filter", "language", "limit", "today", "models"})
		text = json.dumps(sent)
		self.assertIn("approval_status", text)
		self.assertNotIn(CHP, text)

	def test_the_filter_comes_from_the_server_not_the_caller(self):
		"""A CHP claiming to be someone else gets their own filter, or a refusal."""
		_out, own = self._sent()
		h.as_user(CHP)
		with patch.object(kb, "_search_service", wraps=h.fake_search_service) as call:
			try:
				kb.search(query=QUESTION, audience="Administrator", region="Everywhere", include_drafts=1)
			except frappe.PermissionError:
				return
		self.assertEqual(call.call_args.args[0]["filter"], own["filter"])

	def test_a_passage_outside_the_askers_access_is_dropped(self):
		"""If the service ignored the filter, nothing it returned could reach the asker."""
		h.as_user(CHP)

		def docs(point):
			with patch.object(kb, "_search_service", return_value={"points": [point], "reranked": False}):
				return [r["doc"] for r in kb.search(query=QUESTION)["results"]]

		self.assertEqual(docs(self._point()), [self.visible])   # the control: unchanged, it is shown
		for changes in ({"approval_status": "Draft"}, {"valid_to": 20000101}, {"valid_from": 99990101},
				{"audience_level": 99}, {"scope_tokens": ["region:somewhere-else"]}, {"applied_to": ["Some Other Role"]}):
			self.assertEqual(docs(self._point(**changes)), [], changes)

	def test_an_unreachable_service_is_a_503_and_is_logged(self):
		h.as_user(CHP)
		for failure in ({"side_effect": requests.ConnectionError()}, {"side_effect": requests.Timeout()},
				{"return_value": reply(503)}, {"return_value": reply(401)}, {"return_value": reply(409, {"detail": "models"})}):
			with patch.object(kb, "_search_service", REAL_SERVICE), \
					patch("requests.post", **failure), self.assertRaises(kb.KBUnavailable):
				kb.search(query=QUESTION)
		frappe.set_user("Administrator")
		row = frappe.get_all("Chatbot Query Log", filters={"user": CHP, "outcome": "Error"}, fields=["name"], limit=1)
		self.assertTrue(row)

	def test_the_request_carries_the_key_and_the_sites_models(self):
		h.as_user(CHP)
		frappe.conf["kb_search_api_key"] = "the-key"
		frappe.conf["kb_search_url"] = "http://search.example:8900/"
		try:
			with patch("requests.post", return_value=reply(200, {"points": [], "reranked": False})) as post:
				REAL_SERVICE({"models": kb._search_models()})
		finally:
			frappe.conf.pop("kb_search_api_key")
			frappe.conf.pop("kb_search_url")
		self.assertEqual(post.call_args.args[0], "http://search.example:8900/v1/search")
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer the-key")

	def test_the_reranker_flag_decides_which_floor_applies(self):
		"""Rank scores below the floor are no match only if the re-ranker produced them."""
		weak = self._point(rank_score=0.01, dense_score=0.9)
		h.as_user(CHP)
		with patch.object(kb, "_search_service", return_value={"points": [weak], "reranked": True}):
			self.assertEqual(kb.ask(QUESTION, mode="verbatim")["mode"], "not_found")
		with patch.object(kb, "_search_service", return_value={"points": [weak], "reranked": False}):
			self.assertEqual(kb.ask(QUESTION, mode="verbatim")["mode"], "verbatim")

	def test_health_warns_when_the_service_is_down_or_mismatched(self):
		h.as_user(EDITOR)
		with patch.object(kb, "search_service_status", return_value={"reachable": False, "url": "u", "error": "ConnectionError"}):
			self.assertTrue(any("not reachable" in w for w in kb_ops.health()["warnings"]))
		with patch.object(kb, "search_service_status", return_value={"reachable": True, "url": "u", "ready": True,
				"reranker_loaded": False, "models_match": False}):
			self.assertTrue(any("different models" in w for w in kb_ops.health()["warnings"]))
