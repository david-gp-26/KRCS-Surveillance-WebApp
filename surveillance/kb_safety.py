"""Public guidance safety (SRS R74-R77, KB-3 / KB-14).

Public actors (community WhatsApp senders, anyone without a staff role) only ever receive approved
`Public` documents, verbatim, wrapped in a fixed template:
    plain-language guidance -> warning signs -> "seek care in person" -> emergency contact.
The public path never diagnoses or prescribes. check() looks for diagnosis and prescription phrasing in
English and Kiswahili; a passage that trips it is withheld from public users and the request is escalated.

The phrase lists are deliberately conservative (false positives escalate to a human, which is safe).
They are a backstop: the primary control is that only KRCS-approved Public documents are searchable.
"""
import re

import frappe

# "you have cholera", "this is malaria", "una kipindupindu", "umeambukizwa ..."
_DIAGNOSIS = [
	r"\byou (?:have|probably have|likely have|may have|are suffering from|are infected with)\b",
	r"\b(?:your|the) diagnosis is\b",
	r"\b(?:he|she|they|the child|your child) (?:has|have) (?:got )?(?:cholera|malaria|measles|mpox|polio|covid|ebola|tb|tuberculosis)\b",
	r"\bthis is (?:definitely |probably |likely )?(?:cholera|malaria|measles|mpox|polio|covid|ebola|tb|tuberculosis)\b",
	r"\bun(?:a|augua|augua ugonjwa wa) (?:kipindupindu|malaria|surua|ukambi|homa ya)\b",
	r"\bumeambukizwa\b",
	r"\bana(?:ugua)? (?:kipindupindu|malaria|surua|ukambi)\b",
]
# doses and instructions to take or give medicine
_PRESCRIPTION = [
	r"\b\d+(?:[.,]\d+)?\s?(?:mg|mcg|µg|ml|g|iu|units?)\b(?!\s*/\s*(?:dl|l)\b)",
	r"\b(?:take|give|swallow|administer|inject)\b[^.\n]{0,40}\b(?:tablets?|capsules?|pills?|syrup|antibiotics?|doxycycline|amoxicillin|artemether|coartem|paracetamol|ciprofloxacin|azithromycin)\b",
	r"\b(?:tablets?|capsules?|pills?)\s+(?:twice|three times|once|every)\b",
	r"\b(?:meza|kunywa|chukua|mpe)\b[^.\n]{0,40}\b(?:vidonge|kidonge|dawa ya|sindano)\b",
	r"\bvidonge\s+\d+\b",
]
_DIAG_RE = [re.compile(p, re.I | re.U) for p in _DIAGNOSIS]
_RX_RE = [re.compile(p, re.I | re.U) for p in _PRESCRIPTION]
# Safe, generic advice that must not trip the checks (ORS is not a prescription)
_ALLOWED = re.compile(r"\b(?:ors|oral rehydration|zinc as advised by a health worker)\b", re.I)

TEMPLATE = {
	"English": {
		"intro": "Here is approved health guidance from Kenya Red Cross:",
		"warning": "Go to the nearest health facility straight away if the person is very weak, cannot drink, "
			"is very sleepy or confused, has blood in the stool, or is getting worse.",
		"care": "This is general guidance, not a diagnosis. Only a health worker can examine you and decide on treatment.",
		"contact": "For help, contact {contact}.",
		"none": "I could not find approved public guidance for this question, so I have not guessed. "
			"A health worker will follow up. If someone is very unwell, go to the nearest health facility now.",
	},
	"Kiswahili": {
		"intro": "Huu ni ushauri wa afya ulioidhinishwa na Shirika la Msalaba Mwekundu Kenya:",
		"warning": "Nenda kwenye kituo cha afya kilicho karibu mara moja ikiwa mgonjwa ni dhaifu sana, hawezi kunywa, "
			"ana usingizi mwingi au amechanganyikiwa, ana damu kwenye choo, au hali inazidi kuwa mbaya.",
		"care": "Huu ni ushauri wa jumla, si utambuzi wa ugonjwa. Mhudumu wa afya pekee ndiye anaweza kukuchunguza na kuamua matibabu.",
		"contact": "Kwa msaada, wasiliana na {contact}.",
		"none": "Sikupata ushauri wa umma ulioidhinishwa kwa swali hili, kwa hivyo sijakisia. "
			"Mhudumu wa afya atafuatilia. Ikiwa mtu ni mgonjwa sana, nenda kwenye kituo cha afya kilicho karibu sasa.",
	},
}


def check(text):
	"""Return a list of {kind, phrase} found in text. Empty list = safe for the public path."""
	text = text or ""
	found = []
	for kind, patterns in (("diagnosis", _DIAG_RE), ("prescription", _RX_RE)):
		for p in patterns:
			for m in p.finditer(text):
				if not _ALLOWED.search(m.group(0)):
					found.append({"kind": kind, "phrase": m.group(0)})
	return found


def is_safe(text):
	return not check(text)


def emergency_contact():
	return frappe.conf.get("kb_public_emergency_contact") or "the Kenya Red Cross toll-free line 1199"


def public_reply(passages, language="English"):
	"""Fixed public template around verbatim approved text. passages: list of strings (already checked)."""
	t = TEMPLATE.get(language) or TEMPLATE["English"]
	if not passages:
		return t["none"]
	body = "\n\n".join(p.strip() for p in passages if p and p.strip())
	return "\n\n".join([t["intro"], body, t["warning"], t["care"], t["contact"].format(contact=emergency_contact())])


def public_notice(language="English"):
	"""The parts of the template a channel must append after the guidance text (for the chatbot service)."""
	t = TEMPLATE.get(language) or TEMPLATE["English"]
	return {"intro": t["intro"], "warning_signs": t["warning"], "care": t["care"],
		"contact": t["contact"].format(contact=emergency_contact()), "no_match": t["none"]}
