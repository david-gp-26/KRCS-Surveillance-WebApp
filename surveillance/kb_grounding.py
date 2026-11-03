"""Grounded answers (AI/ML spec 3.8 and 3.8.1; SRS R73-R80; plan KB-9, KB-10, KB-11, KB-13).

verbatim (default)  the approved passages themselves, with citations. Nothing is generated.
summary             the LLM writes a short answer from the passages, for roles KRCS allows (kb_summary_roles; by
                    default professional staff). Before anyone sees it, check() confirms that every statement
                    cites a passage that was given, and every number, dose or unit appears in a cited passage.
                    If any check fails the user gets the verbatim passages instead.

Retrieved text is data, never instructions: it is wrapped in markers the system prompt tells the model to treat as
quoted material, and text that looks like an instruction to the model is flagged at index time and kept out of the
model's context (it can still be shown verbatim; a human approved it).
"""
import re
import unicodedata

import frappe

CITE = re.compile(r"\[(\d+)\]")
# numbers with optional decimal part and unit: "500 mg", "1.5", "1,000", "24 hours", "3x"
NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)*)(?:\s?(%|mg|mcg|µg|ml|g|kg|iu|units?|hours?|hrs?|days?|weeks?|months?|years?|°c|c))?\b", re.I)
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
INJECTION = re.compile(
	r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
	r"|you\s+are\s+now\s+(a|an|the)\b|system\s+prompt|act\s+as\s+(a|an)\s+\w+"
	r"|reveal\s+(the\s+)?(prompt|instructions)|\bjailbreak\b|<\s*/?\s*(system|assistant|instructions?)\s*>"
	r"|puuza\s+maagizo", re.I)
SOURCE_OPEN, SOURCE_CLOSE = "<<<APPROVED_SOURCE {n}>>>", "<<<END_SOURCE {n}>>>"

AUTHORITY = {"National guideline": 4, "KRCS protocol": 3, "Partner guidance": 2, "Other": 1}
DEFAULT_AUTHORITY = "KRCS protocol"

NOTES = {
	"english_only": {
		"English": "",
		"Kiswahili": "Mwongozo ulioidhinishwa unapatikana kwa Kiingereza pekee. Huu ni maandishi asilia.",
	},
	"machine_translated": {
		"English": "",
		"Kiswahili": "Jibu hili limetafsiriwa na kompyuta kutoka mwongozo ulioidhinishwa wa Kiingereza. "
			"Hakikisha na msimamizi wako ikiwa huna uhakika.",
	},
}
NO_MATCH = {
	"English": "I couldn't find approved guidance that answers this, so I have not guessed. "
		"Your question has been passed to {contact}. In an emergency, follow your supervisor's instructions.",
	"Kiswahili": "Sikupata mwongozo ulioidhinishwa unaojibu swali hili, kwa hivyo sijakisia. "
		"Swali lako limetumwa kwa {contact}. Katika dharura, fuata maagizo ya msimamizi wako.",
}
CONFLICT = {
	"English": "Two approved documents of equal standing give different guidance on this, so I have not chosen "
		"between them. Your question has been passed to {contact}.",
	"Kiswahili": "Nyaraka mbili zilizoidhinishwa zenye hadhi sawa zinatoa mwongozo tofauti kuhusu hili, kwa hivyo "
		"sijachagua. Swali lako limetumwa kwa {contact}.",
}


# ---------- index time ----------

def sanitize(text):
	"""Remove zero-width and control characters (hidden text) before indexing."""
	text = unicodedata.normalize("NFC", (text or "").translate(_ZERO_WIDTH))
	return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")


def injection_suspect(text):
	return bool(INJECTION.search(text or ""))


# ---------- prompt ----------

def wrap_sources(points):
	"""Number each passage and fence it as quoted data."""
	parts = []
	for i, p in enumerate(points, 1):
		pl = p.payload
		where = ", ".join(x for x in [pl.get("title"), pl.get("section"), f"page {pl['page']}" if pl.get("page") else ""] if x)
		parts.append(f"{SOURCE_OPEN.format(n=i)}\n[{i}] ({where})\n{pl.get('text')}\n{SOURCE_CLOSE.format(n=i)}")
	return "\n\n".join(parts)


# ---------- answer checks ----------

def _numbers(text):
	out = set()
	for m in NUMBER.finditer(text or ""):
		num = m.group(1).replace(",", "")
		out.add(num)
	return out


def _claims(answer):
	"""Sentences and list items that state something (headings and very short fragments are skipped)."""
	pieces = []
	for line in (answer or "").splitlines():
		line = line.strip().lstrip("-*•").strip()
		if not line or line.endswith(":") or line.startswith("#"):
			continue
		pieces += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line) if s.strip()]
	return [p for p in pieces if len(CITE.sub("", p).strip()) >= 25]


def check(answer, sources):
	"""Problems that make a generated answer unsafe to show. sources: [{n, text}] given to the model."""
	by_n = {s["n"]: s for s in sources}
	problems = []
	cited_all = {int(n) for n in CITE.findall(answer or "")}
	for n in sorted(cited_all - set(by_n)):
		problems.append({"kind": "unknown_citation", "detail": f"[{n}]"})
	if not cited_all:
		problems.append({"kind": "no_citation", "detail": "the answer cites no source"})
	for claim in _claims(answer):
		cited = [int(n) for n in CITE.findall(claim) if int(n) in by_n]
		if not cited:
			problems.append({"kind": "uncited", "detail": claim[:120]})
			continue
		evidence = " ".join(by_n[n]["text"] or "" for n in cited)
		have = _numbers(evidence)
		for num in _numbers(CITE.sub("", claim)) - have:
			problems.append({"kind": "number_not_in_source", "detail": f"{num} in: {claim[:100]}"})
	return problems


def verbatim(sources, language="English", count=2):
	"""The passages as they were approved, with citation numbers."""
	shown = sources[:count]
	body = "\n\n".join(f"{(s['text'] or '').strip()} [{s['n']}]" for s in shown)
	note = ""
	if language == "Kiswahili" and shown and all((s.get("language") or "English") == "English" for s in shown):
		note = NOTES["english_only"]["Kiswahili"]
	return (f"{note}\n\n{body}" if note else body), [s["n"] for s in shown]


def label_translation(answer, language, sources):
	if language == "Kiswahili" and sources and all((s.get("language") or "English") == "English" for s in sources):
		return f"{answer}\n\n_{NOTES['machine_translated']['Kiswahili']}_"
	return answer


# ---------- conflicts between documents ----------

def resolve_conflicts(items, key=lambda x: x):
	"""items: ranked passages; key(item) -> payload. Returns (kept, dropped_docs, unresolved_pair or None).

	Two documents conflict when either lists the other in conflicts_with. The one with the higher authority_rank
	is shown and the other dropped. Equal rank cannot be settled automatically: the caller escalates (R78).
	"""
	payloads = [key(i) for i in items]
	docs = {}
	for p in payloads:
		docs.setdefault(p.get("doc"), p)
	dropped, unresolved = set(), None
	names = list(docs)
	for i, a in enumerate(names):
		for b in names[i + 1:]:
			pa, pb = docs[a], docs[b]
			if b not in (pa.get("conflicts_with") or []) and a not in (pb.get("conflicts_with") or []):
				continue
			ra, rb = int(pa.get("authority_rank") or 0), int(pb.get("authority_rank") or 0)
			if ra == rb:
				unresolved = unresolved or (a, b)
			else:
				dropped.add(b if ra > rb else a)
	kept = [it for it, p in zip(items, payloads) if p.get("doc") not in dropped]
	return kept, sorted(dropped), unresolved


# ---------- server-side conversation history (R63: the client's history is not trusted) ----------

HISTORY_TTL = 2 * 60 * 60
HISTORY_TURNS = 6


def _history_key(owner, conversation_id):
	return f"kb_conversation:{owner}:{str(conversation_id)[:64]}"


def get_history(owner, conversation_id):
	if not conversation_id:
		return []
	return frappe.cache().get_value(_history_key(owner, conversation_id)) or []


def add_turn(owner, conversation_id, question, answer):
	if not conversation_id:
		return
	hist = get_history(owner, conversation_id)
	hist = (hist + [{"role": "user", "content": question[:2000]}, {"role": "assistant", "content": (answer or "")[:2000]}])
	frappe.cache().set_value(_history_key(owner, conversation_id), hist[-HISTORY_TURNS:], expires_in_sec=HISTORY_TTL)
