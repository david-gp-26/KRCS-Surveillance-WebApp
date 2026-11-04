"""KB-12, KB-19, KB-20, D2: rate limits, upload content checks, gap-free re-indexing, reconciliation, health and
per-chunk language (SRS R82, R84, R86, R89, R90)."""
import os
import tempfile
import uuid
import zipfile

import frappe
from frappe.tests.utils import FrappeTestCase

from surveillance import kb_ops
from surveillance import knowledge_base as kb
from surveillance.tests import kb_helpers as h

CHP = "kbt-ops-chp@example.com"
EDITOR = "kbt-ops-editor@example.com"


def _tmp(data, suffix):
	fd, path = tempfile.mkstemp(suffix=suffix)
	with os.fdopen(fd, "wb") as f:
		f.write(data)
	return path


class TestKBOps(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		h.ensure_role("CHP", ["use_knowledge_base"])
		h.ensure_role("KBT Ops Editor", ["manage_knowledge_base", "approve_knowledge_base"])
		h.user(CHP, "CHP")
		h.user(EDITOR, "KBT Ops Editor")
		cls.sandbox = h.kb_sandbox()
		cls.sandbox.__enter__()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.sandbox.__exit__(None, None, None)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.kb_test_rate_limit = False
		frappe.conf.pop("kb_rate_per_minute", None)

	# ---- uploads ----
	def test_upload_bytes_must_match_extension(self):
		good_pdf = _tmp(b"%PDF-1.7\n...", ".pdf")
		kb_ops.check_upload(good_pdf, "pdf")
		bad = [
			(_tmp(b"just text pretending", ".pdf"), "pdf"),
			(_tmp(b"not a zip", ".docx"), "docx"),
			(_tmp(b"text\x00binary", ".txt"), "txt"),
			(_tmp("café".encode("latin-1"), ".md"), "md"),
		]
		zpath = tempfile.mktemp(suffix=".docx")
		with zipfile.ZipFile(zpath, "w") as z:
			z.writestr("hello.txt", "no word document inside")
		bad.append((zpath, "docx"))
		for path, ext in bad:
			with self.assertRaises(frappe.ValidationError, msg=path):
				kb_ops.check_upload(path, ext)

	def test_docx_zip_bomb_is_refused(self):
		zpath = tempfile.mktemp(suffix=".docx")
		with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
			z.writestr("word/document.xml", "<w/>")
			z.writestr("word/big.bin", b"\0" * (kb_ops.DOCX_MAX_UNCOMPRESSED + 1))
		with self.assertRaises(frappe.ValidationError):
			kb_ops.check_upload(zpath, "docx")

	def test_create_document_rejects_a_renamed_file(self):
		# (Frappe itself already refuses a broken .pdf at upload; it does not inspect .docx)
		f = frappe.get_doc({"doctype": "File", "file_name": f"fake_{uuid.uuid4().hex[:6]}.docx",
			"content": b"plain text, not a word document", "is_private": 1}).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			kb.create_document(f.file_url, "Guideline")

	# ---- rate limits ----
	def test_rate_limit_per_user(self):
		frappe.flags.kb_test_rate_limit = True
		frappe.conf["kb_rate_per_minute"] = 2
		from unittest.mock import patch
		minute = 1_800_000_000.0 + uuid.uuid4().int % 10_000 * 60   # a fixed minute no earlier run used
		h.as_user(CHP)
		with patch("time.time", lambda: minute):
			kb.search("cholera", correlation_id="rl-1")
			kb.search("cholera", correlation_id="rl-2")
			with self.assertRaises(kb_ops.TooManyRequests):
				kb.search("cholera", correlation_id="rl-3")
		frappe.set_user("Administrator")
		row = h.logs(correlation_id="rl-3")[0]
		self.assertEqual((row.access_decision, row.deny_reason_code), ("DENY", "RATE_LIMITED"))

	# ---- indexing ----
	def _points(self, name):
		client = kb._qdrant()
		pts, _ = client.scroll(kb._collection(), scroll_filter=kb._doc_filter(name).filter, limit=100,
			with_payload=True)
		return {str(p.id): p.payload for p in pts}

	def test_reindex_is_gap_free_and_removes_stale_chunks(self):
		tag = uuid.uuid4().hex   # unique: Frappe shares one stored file between identical uploads
		long_text = "\n\n".join(f"# Part {i} {tag}\n" + ("measles rash fever " * 80) for i in range(4))
		name = h.add_document("Reindex doc", long_text, approve=False)
		before = self._points(name)
		self.assertGreater(len(before), 2)
		path = frappe.get_doc("File", {"file_url": frappe.db.get_value(kb.DOCTYPE, name, "file")}).get_full_path()
		with open(path, "w") as f:
			f.write(f"# Part 0\nmeasles short {uuid.uuid4().hex}")
		deleted = []
		real_delete = kb._delete_vectors
		kb._delete_vectors = lambda client, doc: deleted.append(doc) or real_delete(client, doc)
		try:
			kb.index_document(name)
		finally:
			kb._delete_vectors = real_delete
		after = self._points(name)
		self.assertEqual(deleted, [])   # the document was never emptied while re-indexing
		self.assertEqual(len(after), 1)
		self.assertIn(next(iter(after)), before)   # chunk 0 kept its id and was overwritten in place
		self.assertEqual(frappe.db.get_value(kb.DOCTYPE, name, "chunks"), 1)

	def test_reconcile_requeues_missing_and_removes_orphans(self):
		name = h.add_document("Reconcile doc", "# R\nmalaria reconcile text")
		kb._delete_vectors(kb._qdrant(), name)
		from qdrant_client.models import PointStruct
		kb._qdrant().upsert(kb._collection(), points=[PointStruct(id=str(uuid.uuid4()),
			vector={kb.DENSE: h.fake_embed(["orphan"])[0], kb.SPARSE: h.fake_sparse(["orphan"])[0]},
			payload={"doc": "KB-ORPHAN-TEST", "chunk": 0})])
		r = kb_ops.reconcile(fix=True)
		self.assertIn(name, r["missing"])
		self.assertIn(name, r["requeued"])
		self.assertIn("KB-ORPHAN-TEST", r["deleted"])
		self.assertEqual(self._points("KB-ORPHAN-TEST"), {})

	def test_reconcile_requeues_only_documents_stuck_past_the_job_timeout(self):
		stuck = h.add_document("Stuck doc", "# S\nmalaria stuck text")
		recent = h.add_document("Recent doc", "# R\nmalaria recent text")
		old = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-3 * kb_ops.INDEX_JOB_TIMEOUT)
		frappe.db.set_value(kb.DOCTYPE, stuck, {"status": "Processing", "modified": old}, update_modified=False)
		frappe.db.set_value(kb.DOCTYPE, recent, "status", "Processing")
		r = kb_ops.reconcile(fix=True)
		self.assertIn(stuck, r["stuck"])
		self.assertIn(stuck, r["requeued"])
		self.assertNotIn(recent, r["stuck"])
		self.assertNotIn(recent, r["requeued"])

	# ---- language and health ----
	def test_chunk_language(self):
		self.assertEqual(kb_ops.chunk_language("Mtoto ana homa na kuhara, tafadhali mpeleke kwa kituo cha afya na maji safi"),
			"Kiswahili")
		self.assertEqual(kb_ops.chunk_language("The child has a fever and should be taken to the facility for testing"),
			"English")
		name = h.add_document("Mixed doc", "# EN\nThe patient should drink clean water and be referred to the facility.\n\n"
			"# SW\nMgonjwa anapaswa kunywa maji safi na apelekwe kwa kituo cha afya kama dalili ni mbaya sana.")
		langs = {p["section"]: p["chunk_language"] for p in self._points(name).values()}
		self.assertEqual(langs, {"EN": "English", "SW": "Kiswahili"})

	def test_health_reports_licences(self):
		self.assertFalse(kb_ops._licence("jinaai/jina-reranker-v2-base-multilingual")["approved_for_use"])
		self.assertTrue(kb_ops._licence("BAAI/bge-reranker-v2-m3")["approved_for_use"])
		h.as_user(EDITOR)
		out = kb_ops.health()
		self.assertTrue(out["qdrant"]["reachable"])
		self.assertIn("models", out)
		self.assertIn("retrieval_config", out)
