"""Starting a report, the review, the duplicate check, editing, saving it and what the reporter sees afterwards."""

import re

from surveillance.whatsapp import content as C
from surveillance.whatsapp.conversation.core import (
	AttrDict,
	L,
	State,
	_call,
	go,
	home,
	nairobi_date,
	nav,
	normalize,
	normalize_phone,
	paging,
	quiet,
	ref_from,
	region_label,
	show_date,
	split_text,
	stay,
	sub_county_label,
	symptom_labels,
	t,
	to_media,
)
from surveillance.whatsapp.conversation.free_text import _clip, advice_for, describe, extraction_note
from surveillance.whatsapp.conversation.status import one_report
from surveillance.whatsapp.conversation.steps import (
	active_steps,
	area_locked,
	ask,
	choose,
	first_step,
	missing_steps,
	new_draft,
	set_place,
	step_name,
)
from surveillance.whatsapp.extract import extract_report
from surveillance.whatsapp.messages import text


def transcribed(s, inp, ctx):
	"""The words of a voice note (AI/ML §6.3), which then go the way typed words do. None: the reporter is asked to type.
	The menu language is not sent: someone reading Kiswahili menus may speak English or a mix, and the service picks
	its model by the language it hears. The words are kept on the note in the draft, so they are saved on its row and
	the background transcription for officers skips it."""
	transcribe = getattr(ctx, "transcribe", None)
	if inp.get("kind") != "audio" or not transcribe:
		return None
	try:
		heard = transcribe(inp) or ""
	except Exception:
		if getattr(ctx, "log_error", None):
			ctx.log_error("WhatsApp voice note could not be transcribed")
		return None
	words, language = (heard.get("text") or "", heard.get("language")) if isinstance(heard, dict) else (heard, None)
	words = words.strip()
	if len(normalize(words)) < 3:
		return None
	for m in s.draft.media or []:
		if m.get("media_id") == inp.get("media_id"):
			m["transcript"], m["transcript_language"] = words, language
	return words


class RDescribe(State):
	"""Community members first describe what is happening in their own words (AI/ML §1.4, SRS H.12)."""

	def options(self, s, ctx):
		return [
			{
				"id": "guided",
				"title": t(s)["describeGuided"],
				"aliases": ["step by step", "steps", "hatua kwa hatua", "hatua"],
			}
		]

	def prompt(self, s, ctx):
		return [choose(s, t(s)["describe"], self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "guided":
			s.draft.free = False
			return go(first_step(s, ctx))
		if inp["type"] == "media":
			s.draft.media.append(to_media(inp))
			if len(normalize(inp.get("caption"))) >= 3:
				return describe(s, inp["caption"], ctx)
			words = transcribed(s, inp, ctx)
			if words:
				s.draft.transcribed = True
				res = describe(s, words, ctx)
				res["say"].insert(0, text(t(s)["heard"](_clip(words, 800))))
				return res
			body = t(s)["describeVoice"] if inp.get("kind") == "audio" else t(s)["describeMedia"]
			return quiet(choose(s, body, self.options(s, ctx)))
		if inp["type"] == "location":
			set_place(s, inp, ctx)
			return quiet(choose(s, t(s)["describeLocation"], self.options(s, ctx)))
		if inp["type"] == "text" and len(normalize(inp.get("text"))) >= 3:
			return describe(s, inp["text"], ctx)
		return None


class RReview(State):
	def options(self, s, ctx):
		return [
			{
				"id": "submit",
				"title": t(s)["submit"],
				"aliases": ["submit", "confirm", "send", "yes", "tuma", "thibitisha", "ndiyo"],
			},
			{"id": "edit", "title": t(s)["edit"], "aliases": ["edit", "back", "change", "badilisha"]},
			{"id": "cancel", "title": t(s)["cancel"], "aliases": ["discard", "futa"]},
		]

	def prompt(self, s, ctx):
		s.editing = False
		return [choose(s, t(s)["review"](summary(s, ctx)), self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "edit":
			return go("r_edit")
		if choice == "cancel":
			s.draft = None
			return go("r_done", text(t(s)["cancelled"]))
		if choice != "submit":
			return None
		missing = missing_steps(s, ctx)
		if missing:
			s.editing = True
			return go(missing[0], text(t(s)["incomplete"](", ".join(step_name(s, m) for m in missing))))
		if needs_consent(s):
			return go("r_consent")
		if not s.draft.skip_duplicate_check:
			dup = ctx.data.find_duplicate(s.draft.region, s.draft.symptoms)
			if dup:
				s.draft.duplicate_of = dup
				return go("r_duplicate")
		return submit(s, ctx)


CONSENT_CHOICES = {
	"none": (0, "No one"),
	"person": (1, "Person agreed"),
	"guardian": (1, "Parent or guardian agreed"),
}


def needs_consent(s):
	"""Anything attached that has no consent answer yet (Kenya Data Protection Act 2019). Videos and files can
	show a person as much as photos can."""
	return any(not m.get("consent") for m in (s.draft.media or []))


class RConsent(State):
	"""Asked before sending, when the report has attachments without an answer."""

	def options(self, s, ctx):
		return [
			{
				"id": "none",
				"title": t(s)["consentNone"],
				"aliases": ["no", "none", "no one", "hapana", "hakuna"],
			},
			{
				"id": "person",
				"title": t(s)["consentPerson"],
				"aliases": ["yes", "agreed", "ndiyo", "alikubali"],
			},
			{
				"id": "guardian",
				"title": t(s)["consentGuardian"],
				"aliases": ["parent", "guardian", "mzazi", "mlezi"],
			},
			{
				"id": "remove",
				"title": t(s)["consentRemove"],
				"aliases": ["remove", "delete", "ondoa", "futa"],
			},
		]

	def prompt(self, s, ctx):
		return [choose(s, t(s)["consentAsk"], self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "remove":
			s.draft.media = []
			note = [text(t(s)["consentRemoved"])]
		elif choice in CONSENT_CHOICES:
			shown, consent = CONSENT_CHOICES[choice]
			for m in s.draft.media:
				m["people_shown"], m["consent"] = shown, consent
			note = []
		else:
			return None
		if not s.draft.skip_duplicate_check:
			dup = ctx.data.find_duplicate(s.draft.region, s.draft.symptoms)
			if dup:
				s.draft.duplicate_of = dup
				return go("r_duplicate", *note)
		return submit(s, ctx)


class RDuplicate(State):
	def options(self, s, ctx):
		return [
			{
				"id": "submit",
				"title": t(s)["submitAnyway"],
				"aliases": ["submit", "yes", "new", "tuma", "ndiyo"],
			},
			{"id": "cancel", "title": t(s)["cancel"], "aliases": ["no", "discard", "hapana"]},
		]

	def prompt(self, s, ctx):
		return [choose(s, t(s)["duplicate"](s.draft.duplicate_of), self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "cancel":
			s.draft = None
			return go("r_done", text(t(s)["cancelled"]))
		if choice != "submit":
			return None
		s.draft.skip_duplicate_check = True
		# Something may have been attached while this question was showing.
		return go("r_consent") if needs_consent(s) else submit(s, ctx)


class REdit(State):
	def options(self, s, ctx):
		return [
			*({"id": sid, "title": step_name(s, sid)} for sid in active_steps(s, ctx, editable=True)),
			{"id": "back", "title": t(s)["editBack"]},
			*nav(s),
		]

	def prompt(self, s, ctx):
		opts = self.options(s, ctx)
		sections = [o for o in opts if o["id"].startswith("r_")]
		return [ask(s, t(s)["editPrompt"], sections, extra=[next(o for o in opts if o["id"] == "back")])]

	def on(self, s, inp, choice, ctx):
		moved = paging(s, choice)
		if moved:
			return moved
		if not choice:
			return None
		if choice == "back":
			return go("r_review")
		s.editing = True
		if choice == "r_symptoms":
			s.draft.symptoms = []
			s.symptom_group = None
		return go(choice)


class RDone(State):
	def options(self, s, ctx):
		return [
			{"id": "another", "title": t(s)["another"]},
			*([] if s.mode == "staff" else [{"id": "advice", "title": t(s)["advice"]}]),
			{
				"id": "menu",
				"title": t(s)["finish"] if s.mode == "staff" else t(s)["backToMenu"],
				"aliases": ["done", "maliza"],
			},
		]

	def prompt(self, s, ctx):
		return [choose(s, t(s)["next"], self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "another":
			return start_report(s, ctx)
		if choice == "advice":
			return stay(text(C.HEALTH_TIPS))
		if choice == "menu":
			return go(home(s))
		ref = ref_from(inp)
		if ref:
			return stay(text(one_report(s, ctx, ref)))
		return None


def verify_staff(s, ctx):
	s.staff = AttrDict.wrap(ctx.data.find_staff(s.phone))
	if not s.staff:
		s.mode = None
		return go("not_staff")
	s.mode = "staff"
	s.lang = s.lang or "en"
	s.greet = True
	return go("menu")


def begin_report(s, ctx):
	"""From a "Submit a report" button outside the staff portal: community members pick a language first."""
	if not s.mode:
		s.mode = "community"
	if s.mode == "community" and not s.lang:
		return go("lang")
	return start_report(s, ctx)


def start_report(s, ctx):
	if s.mode == "staff":
		s.staff = AttrDict.wrap(ctx.data.find_staff(s.phone))
		if not s.staff:
			s.mode = None
			return go("not_staff")
		if area_locked(s) and not assigned_area_ok(s, ctx):
			return go("menu", text(t(s)["areaMissing"]))
	else:
		s.staff = None
	s.draft = new_draft(s)
	s.draft.started = ctx.now()
	s.editing = False
	s.symptom_group = None
	if not s.staff:
		# Community members describe it in their own words; trained staff keep the guided steps (AI/ML §1.4).
		s.draft.free = True
		seed, s.seed = s.seed, None
		return describe(s, seed["text"], ctx, seed["extraction"]) if seed else go("r_describe")
	return go(first_step(s, ctx))


def assigned_area_ok(s, ctx):
	"""Case Report refuses a field-staff report when the account has no region and sub-county, or the
	sub-county is not in the region, so the reporter is told before filling in the steps."""
	region, sub_county = s.staff.region, s.staff.sub_county
	return bool(region and sub_county) and any(x["name"] == sub_county for x in ctx.data.sub_counties(region))


def summary(s, ctx):
	d = s.draft
	f = t(s)["f"]
	symptoms = ctx.data.catalog()["symptoms"]
	place = d.location_name or (f"{d.latitude:.5f}, {d.longitude:.5f}" if d.latitude is not None else None)
	lines = [
		d.description and (f["description"], "_" + _clip(re.sub(r"[_*~]", "", d.description), 160) + "_"),
		(f["region"], region_label(d.region, ctx)),
		d.sub_county and (f["sub_county"], sub_county_label(d.region, d.sub_county, ctx)),
		place and (f["place"], place),
		not s.staff and (f["reporter_name"], d.reporter_name),
		(f["category"], d.category and L(s, "category", d.category)),
		s.staff and (f["signal_type"], d.signal_type),
		(f["symptoms"], symptom_labels(d.symptoms, symptoms)),
		(f["affected_count"], d.affected_count),
		d.age_group and (f["age_group"], L(s, "age_group", d.age_group)),
		d.animal_exposure and (f["animal_exposure"], L(s, "animal_exposure", d.animal_exposure)),
		(f["deaths_count"], d.deaths_count),
		(f["onset_date"], show_date(d.onset_date)),
		(d.media or d.notes) and (f["extra"], t(s)["attached"](len(d.media), len(d.notes))),
	]
	body = "\n".join(
		f"*{k}:* {'—' if v is None or v == '' else v}" for k, v in (line for line in lines if line)
	)
	filled = d.free and d.extraction and d.extraction.get("filled")
	return f"{body}\n\n_{t(s)['reviewFilled']}_" if filled else body


def build_doc(s, ctx):
	"""The Case Report exactly as the web form would create it, with channel = WhatsApp.
	Photos and voice notes are attached afterwards by a background job (jobs.attach_media)."""
	d = s.draft
	return {
		"doctype": "Case Report",
		"reported_by": s.staff.user if s.staff else ctx.data.community_user(),
		"reporter_name": d.reporter_name,
		"phone_number": f"+{normalize_phone(s.phone)}",
		"signal_type": d.signal_type,
		"category": d.category,
		"region": d.region,
		"sub_county": d.sub_county,
		"location_name": d.location_name,
		"latitude": d.latitude,
		"longitude": d.longitude,
		"affected_count": d.affected_count,
		"symptoms": [{"symptom": sid} for sid in d.symptoms],
		"onset_date": d.onset_date,
		"age_group": d.age_group,
		"animal_exposure": d.animal_exposure,
		# An Int column is never blank; extraction_note says when deaths were not asked.
		"deaths_count": d.deaths_count or 0,
		"additional_notes": "\n\n".join(x for x in [*d.notes, extraction_note(s)] if x) or None,
		"channel": "WhatsApp",
		"status": "Submitted",
		"client_ref": _client_ref(ctx),
	}


def _client_ref(ctx):
	mid = getattr(ctx, "message_id", None)
	if not mid:
		return None
	import hashlib

	return "wa:" + hashlib.sha1(str(mid).encode()).hexdigest()  # WhatsApp IDs can exceed 64 characters


def submit(s, ctx):
	try:
		report = ctx.data.create_report(build_doc(s, ctx))
	except Exception:
		if getattr(ctx, "log_error", None):
			ctx.log_error("WhatsApp report could not be saved")
		return quiet(text(t(s)["saveFailed"]))
	# SRS R10: community reporters get advice for what they reported; staff get the mobile app's next steps.
	advice = next_steps(s, report, ctx) if s.mode == "staff" else [text(advice_for(s, ctx))]
	draft = s.draft
	s.draft = None
	if draft.description:
		_call(ctx, "on_extract", report=report, session=s, draft=draft)
	seconds = round(ctx.now() - draft.started) if draft.started else None
	_call(ctx, "on_report_stats", report=report, session=s, draft=draft, seconds=seconds)
	_call(ctx, "on_submit", report=report, session=s, media=list(draft.media), extraction=draft.extraction)
	return go("r_done", text(t(s)["done"](report["name"])), *advice)


def next_steps(s, report, ctx):
	"""The protocol's steps for reporters and the general lines, as in the mobile app. Without the protocol
	(none approved, no permission, Frappe unreachable) the general lines still apply."""
	N = C.NEXT_STEPS.get(s.lang) or C.NEXT_STEPS["en"]
	try:
		a = ctx.data.reporter_advice(report.get("suspected_disease"), s.staff.user) or {}
	except Exception:
		if getattr(ctx, "log_error", None):
			ctx.log_error("WhatsApp next steps could not be loaded")
		a = {}
	disease, steps = a.get("disease"), a.get("steps") or []
	general = a.get("general") or N["general"]  # Reporter Advice Settings, else the app's default lines
	parts = [N["title"]]
	if disease:
		parts.append(N["disease"](disease))
	if steps:
		numbered = (
			f"{i}. {x['step']}" + (f" _({x['timeframe']})_" if x.get("timeframe") else "")
			for i, x in enumerate(steps, 1)
		)
		parts.append("\n".join([N["steps"](disease), *numbered]))
	parts.append("\n".join([N["also"] if steps else N["next"], *(f"• {g}" for g in general)]))
	return [text(p) for p in split_text("\n\n".join(parts))]


def seed_report(s, value, ctx):
	"""A report typed outside the report flow (the welcome screen, a question the chatbot routes as a report)
	starts a free-text report from it. A staff number keeps the staff portal, unless it chose Community member."""
	x = extract_report(value, ctx, nairobi_date(ctx.now()), s.lang)
	if not x["is_report"] or (s.mode != "community" and ctx.data.find_staff(s.phone)):
		return None
	return start_seeded(s, value, x, ctx)


def report_from_question(s, value, ctx):
	"""The report button under a message the chatbot took for a report: that message is the report, so it is not
	asked for again. Staff in the portal keep the guided steps."""
	if s.mode == "staff":
		return begin_report(s, ctx)
	return start_seeded(s, value, extract_report(value, ctx, nairobi_date(ctx.now()), s.lang), ctx)


def start_seeded(s, value, extraction, ctx):
	s.mode = "community"
	s.staff = None
	s.lang = s.lang or extraction["language"]
	s.seed = {"text": value, "extraction": extraction}
	return start_report(s, ctx)
