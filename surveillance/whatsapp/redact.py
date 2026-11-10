"""Personal details taken out before text leaves Frappe for the AI services, and logs (DPA Clause 9.6).

The desk and the Case Report keep the reporter's own words. Reporters' words are unpredictable, so this lowers the
risk and does not remove it: a name with no cue around it ("Amina and Ali are sick") passes through.
Does not import frappe, like the conversation package.
"""

import hashlib
import hmac
import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# 9 to 15 digits, however they are spaced. "10 20 30" stays: too few digits to be a phone number.
PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?!\w)")
ID_NUMBER = re.compile(
	r"\b(?:national id|id|kitambulisho|alien id|refugee id|ration card|manifest|passport|pasipoti)"
	r"(?:\s+(?:no|number|namba|nambari))?\.?\s*[:#]?\s*[A-Za-z0-9-]*\d[A-Za-z0-9-]*",
	re.I,
)
# Case counts stop at 100,000 (extract._valid), so a run of 7 or 8 digits is an ID.
LONG_NUMBER = re.compile(r"(?<![\w.])\d{7,8}(?!\w)")
NAME_CUE = re.compile(
	r"\b(my name is|his name is|her name is|their name is|name is|i am called|i'm called|called|"
	r"jina langu ni|jina lake ni|jina lao ni|naitwa|ninaitwa|anaitwa)\s+((?:[\w'-]+\s*){1,3})",
	re.I,
)
TITLE = re.compile(r"\b(Mr|Mrs|Ms|Dr|Bw|Bi|Mzee|Mama|Baba|Daktari)\.?\s+[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?")
# Words that end a name after a cue: "my name is Ali and 3 kids are sick".
NOT_NAME = {
	"and", "from", "in", "at", "of", "the", "with", "i", "my", "we", "our", "people", "there", "is", "are", "am",
	"na", "kutoka", "wa", "ya", "kwa", "katika", "hapa", "huko", "kuna", "watu", "watoto", "mimi", "sisi", "ni",
}  # fmt: skip


def _phone(match):
	digits = sum(ch.isdigit() for ch in match.group())
	return "[PHONE]" if 9 <= digits <= 15 else match.group()


def _name(match):
	found = match.group(2)
	words = found.split()
	kept = []
	for word in words:
		if word.lower() in NOT_NAME or word[0].isdigit():
			break
		kept.append(word)
	if not kept:
		return match.group()
	rest = " ".join(words[len(kept) :])
	space_after = found[len(found.rstrip()) :]
	return f"{match.group(1)} [NAME]" + (f" {rest}" if rest else "") + space_after


def redact(value):
	"""The text with phone numbers, emails, ID numbers and cued names replaced by markers."""
	text = EMAIL.sub("[EMAIL]", str(value or ""))
	text = ID_NUMBER.sub("[ID]", text)
	text = PHONE.sub(_phone, text)
	text = LONG_NUMBER.sub("[ID]", text)
	text = NAME_CUE.sub(_name, text)
	text = TITLE.sub("[NAME]", text)
	return text.strip()


def pseudonym(phone, key):
	"""A stable reference for a community reporter: traceable in Frappe with the key, not by the AI services."""
	digest = hmac.new(str(key or "").encode(), str(phone).encode(), hashlib.sha256).hexdigest()
	return f"whatsapp:{digest[:24]}"
