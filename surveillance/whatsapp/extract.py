"""Free-text report -> Case Report fields (AI/ML spec §3.1, SRS H.12).

The extraction service (agents/chatbot POST /extract, later the NLP service W-16) does the work. When it is not
configured or can't be reached, a small keyword fallback here finds symptoms, a count, today/yesterday and
region / sub-county names; the conversation asks for everything else.
Only values at or above AUTOFILL confidence are filled in (AI/ML §7.1: 70%), and every value is checked against
Frappe's own lists before it is used.

Does not import frappe, like the conversation package: the client is built in jobs.make_context.
"""

import re
from datetime import date, timedelta

import requests

from surveillance.whatsapp import content as C
from surveillance.whatsapp.redact import redact

AUTOFILL = 0.7
FIELDS = [
	"symptoms", "affected_count", "deaths_count", "category", "age_group", "animal_exposure",
	"onset_date", "region", "sub_county", "location_name",
]  # fmt: skip


class ExtractionError(Exception):
	pass


class ExtractionClient:
	def __init__(self, url, token=None, timeout=8):
		self.url = url.rstrip("/") + "/extract"
		self.headers = {
			"Accept": "application/json",
			**({"Authorization": f"Bearer {token}"} if token else {}),
		}
		self.timeout = timeout

	def post(self, body):
		r = requests.post(self.url, json=body, headers=self.headers, timeout=self.timeout)
		if not r.ok:
			raise ExtractionError(f"POST /extract -> {r.status_code}", r.status_code)
		return r.json()

	def extract(self, body):
		"""Retries once on a timeout, connection error or 5xx."""
		try:
			return self.post(body)
		except ExtractionError as e:
			if e.args[1] < 500:
				raise
		except requests.RequestException:
			pass
		try:
			return self.post(body)
		except requests.RequestException as e:
			raise ExtractionError(str(e)) from e


def normalize(value):
	return re.sub(r"\s+", " ", re.sub(r"[^\w' ]+|_", " ", str(value or "").lower())).strip()


def symptom_key(label):
	"""'Fever (hot body)' -> 'fever', the form used in content.py."""
	return normalize(re.sub(r"\([^)]*\)", "", label))


def find_symptoms(value, symptoms):
	"""Symptom names and their everyday words found anywhere in free text ("my child has homa and is vomiting"),
	longest first so "maumivu ya tumbo" isn't also read as something shorter; "no fever" is skipped."""
	phrases = [
		(normalize(p), x["name"])
		for x in symptoms
		for p in [x["label"], symptom_key(x["label"]), *C.SYMPTOM_WORDS.get(symptom_key(x["label"]), [])]
	]
	phrases.sort(key=lambda p: -len(p[0]))
	rest = f" {normalize(value)} "
	found = []
	for phrase, name in phrases:
		if not phrase:
			continue
		i = rest.find(f" {phrase} ")
		while i != -1:
			before = rest[:i].strip().split(" ")[-1]
			rest = rest[: i + 1] + "#" * len(phrase) + rest[i + 1 + len(phrase) :]
			if before not in C.NEGATIONS:
				found.append((i, name))
			i = rest.find(f" {phrase} ")
	return list(dict.fromkeys(name for _, name in sorted(found, key=lambda f: f[0])))


NUMBER_WORDS = {
	"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
	"moja": 1, "mmoja": 1, "mbili": 2, "wawili": 2, "tatu": 3, "watatu": 3, "nne": 4, "wanne": 4, "tano": 5,
	"watano": 5, "sita": 6, "saba": 7, "nane": 8, "wanane": 8, "tisa": 9, "kumi": 10,
}  # fmt: skip
PEOPLE = {
	"people", "persons", "children", "kids", "patients", "cases", "adults", "men", "women", "boys", "girls",
	"students", "pupils", "babies", "watu", "watoto", "wagonjwa", "wanaume", "wanawake", "wanafunzi", "kesi",
}  # fmt: skip
ONE_PERSON = {"person", "child", "baby", "man", "woman", "boy", "girl", "mtu", "mtoto"}  # counted ("1 person"), not a category
# A bite or scratch is a report even with no symptoms yet (rabies); the service also names the animal.
BITES = {
	"bitten", "bite", "bites", "scratched", "aliumwa", "ameumwa", "waliumwa", "wameumwa", "aling'atwa",
	"ameng'atwa", "alikwaruzwa", "amekwaruzwa",
}  # fmt: skip
ANIMALS = {
	"animals", "cows", "cattle", "goats", "sheep", "camels", "chickens", "donkeys", "livestock", "wanyama",
	"ng'ombe", "ngombe", "mbuzi", "kondoo", "ngamia", "kuku", "punda", "mifugo",
}  # fmt: skip
SW_MARKERS = {
	"na", "ya", "wa", "kwa", "ni", "kuna", "watu", "watoto", "mtoto", "homa", "kuhara", "kutapika", "tangu",
	"jana", "leo", "wana", "ana", "wagonjwa", "mgonjwa", "sana", "hapa", "huko",
}  # fmt: skip


def _shift(iso, days):
	return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _find_places(words, regions, sub_counties):
	def has(label):
		p = normalize(label).split(" ")
		return any(words[i : i + len(p)] == p for i in range(len(words)))

	subs = [x for x in sub_counties if has(x["label"])]
	regs = [r for r in regions if has(r["label"])]
	out = {}
	if len(regs) == 1:
		out["region"] = {"value": regs[0]["name"], "confidence": 0.9}
	if len(subs) == 1:
		sub = subs[0]
		region_name = next((r["label"] for r in regions if r["name"] == sub["region"]), "")
		same_name = normalize(region_name) == normalize(sub["label"])
		out["sub_county"] = {"value": sub["name"], "confidence": 0.6 if same_name else 0.9}
		out.setdefault("region", {"value": sub["region"], "confidence": 0.9})
	return out


def local_extract(value, catalog, sub_counties, today):
	words = [w for w in normalize(value).split(" ") if w]
	fields = {}
	symptoms = find_symptoms(value, catalog["symptoms"])
	if symptoms:
		fields["symptoms"] = {"value": symptoms, "confidence": 0.9}
	for i, w in enumerate(words):
		n = int(w) if re.fullmatch(r"\d{1,5}", w) else NUMBER_WORDS.get(w)
		near = [words[k] for k in (i - 1, i + 1) if 0 <= k < len(words)]
		if n and any(x in PEOPLE or x in ONE_PERSON or x in ANIMALS for x in near):
			fields["affected_count"] = {"value": n, "confidence": 0.9}
			break
	onset = next((w for w in words if w in ("today", "leo", "yesterday", "jana")), None)
	if onset:
		fields["onset_date"] = {
			"value": today if onset in ("today", "leo") else _shift(today, -1),
			"confidence": 0.9,
		}
	people = any(w in PEOPLE for w in words)
	animals = any(w in ANIMALS for w in words)
	if people or animals:
		category = "Human Disease" if people else "Animal Disease"   # the "All Disease" category was retired; animal contact is kept in animal_exposure
		fields["category"] = {"value": category, "confidence": 0.8}
	if any(w in BITES for w in words):
		fields["animal_exposure"] = {"value": "Bite or scratch", "confidence": 0.8}
		fields.setdefault("category", {"value": "Human Disease", "confidence": 0.8})
	fields.update(_find_places(words, catalog["regions"], sub_counties))
	return {
		"extractor": "keywords-fallback",
		"language": "sw" if sum(w in SW_MARKERS for w in words) >= 2 else "en",
		"is_report": bool(fields.get("symptoms") or fields.get("affected_count") or fields.get("animal_exposure")),
		"fields": {
			k: {**f, "autofill": f["confidence"] >= AUTOFILL, "evidence": []} for k, f in fields.items()
		},
		"danger_signs": [],
		"threat": "routine",
		"mentioned_diseases": [],
		"notes": ["extraction service not used: keyword fallback"],
	}


def _vocabulary(ctx):
	catalog = ctx.data.catalog()
	sub_counties = [
		{**x, "region": r["name"]} for r in catalog["regions"] for x in ctx.data.sub_counties(r["name"])
	]
	return catalog, sub_counties


def extract_report(value, ctx, today, language=None):
	"""Extract, then keep only values Frappe knows: {fill, offered, evidence, confidence, is_report, ...}."""
	catalog, sub_counties = _vocabulary(ctx)
	raw = None
	if getattr(ctx, "extractor", None):
		try:
			raw = ctx.extractor.extract(
				{
					"text": redact(value)[:2000],
					"language": language,
					"today": today,
					"vocabulary": {
						"symptoms": [
							{"id": s["name"], "label": s["label"], "category": s.get("category")}
							for s in catalog["symptoms"]
						],
						"regions": [{"id": r["name"], "label": r["label"]} for r in catalog["regions"]],
						"sub_counties": [
							{"id": x["name"], "label": x["label"], "region": x["region"]}
							for x in sub_counties
						],
					},
				}
			)
		except Exception:
			if getattr(ctx, "log_error", None):
				ctx.log_error("WhatsApp extraction service failed; keyword fallback used")
	if raw is None:
		raw = local_extract(value, catalog, sub_counties, today)
	return _clean(raw, catalog, sub_counties, today)


def _valid(field, value, catalog, sub_counties, fields, today):
	if field == "symptoms":
		ids = {s["name"] for s in catalog["symptoms"]}
		return isinstance(value, list) and bool(value) and all(v in ids for v in value)
	if field == "affected_count":
		return isinstance(value, int) and 1 <= value <= 100_000
	if field == "deaths_count":
		return isinstance(value, int) and 0 <= value <= 100_000
	if field == "region":
		return any(r["name"] == value for r in catalog["regions"])
	if field == "sub_county":
		region = (fields.get("region") or {}).get("value")
		return any(x["name"] == value and x["region"] == region for x in sub_counties)
	if field == "onset_date":
		return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value))) and _shift(today, -365) <= value <= today
	if field == "location_name":
		return isinstance(value, str) and len(value.strip()) >= 2
	return value in (catalog["options"].get(field) or [])  # Select fields: only options this Case Report has


def _clean(raw, catalog, sub_counties, today):
	fields = raw.get("fields") or {}
	out = {"fill": {}, "offered": {}, "evidence": {}, "confidence": {}}
	for field in FIELDS:
		f = fields.get(field)
		if not f or not _valid(field, f.get("value"), catalog, sub_counties, fields, today):
			continue
		target = out["fill"] if f.get("autofill") and f.get("confidence", 0) >= AUTOFILL else out["offered"]
		target[field] = f["value"].strip()[:140] if field == "location_name" else f["value"]
		out["confidence"][field] = f.get("confidence")
		out["evidence"][field] = [e.get("text") for e in f.get("evidence") or [] if e.get("text")]
	return {
		**out,
		"extractor": raw.get("extractor") or "unknown",
		"language": "sw" if raw.get("language") == "sw" else "en",
		"is_report": bool(raw.get("is_report")),
		"threat": raw.get("threat") or "routine",
		"safety": raw.get("safety"),
		"danger_signs": raw.get("danger_signs") or [],
		"diseases": [d.get("label") or d.get("key") for d in raw.get("mentioned_diseases") or []],
		"notes": raw.get("notes") or [],
	}
