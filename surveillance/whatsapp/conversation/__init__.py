"""The WhatsApp conversation: welcome, staff portal, the report steps, review, questions to the chatbot.

A state machine over one session per phone number. Each state has
        options(s, ctx) -> choices, prompt(s, ctx) -> messages, on(s, input, choice, ctx) -> result or None.
The report steps follow the web "Record Health Signal" form and end in an ordinary Case Report
(channel = WhatsApp).

	core.py       session, results (go / stay / quiet), choices, phone numbers, dates, labels
	steps.py      which report steps apply, their order, "back", what is still missing, shared step prompts
	fields.py     one state per report field
	free_text.py  community reports in their own words: what was understood, advice afterwards
	report.py     starting a report, review, duplicate check, edit, saving, what the reporter sees afterwards
	status.py     report status, recent reports, lookup by reference
	ask.py        questions to the Response Support Chatbot
	privacy.py    the privacy notice, consent and the PRIVACY keyword
	portal.py     welcome, language, staff portal, help, resume
	__init__.py   handle(): global keywords (menu, cancel, back...) and the state table

This package does not import frappe: everything it needs comes in through `ctx`
(see jobs.make_context), so the whole flow is tested without a site (tests/test_conversation.py).
        ctx.data      catalog(), sub_counties(region), find_staff(phone), roles_of(user), community_user(),
                      create_report(doc), find_duplicate(region, symptoms), my_reports(user, phone, limit), get_report(name),
                      reporter_advice(disease, user)
        ctx.settings  idle_minutes, welcome_image_url
        ctx.now()     epoch seconds
        ctx.chatbot   Response Support Chatbot client, or None
        ctx.extractor free-text extraction client (extract.ExtractionClient), or None for the keyword fallback
        ctx.transcribe(input) -> {"text", "language"} (or the text) of a voice note, or None (optional); the service
                                 detects the spoken language
        ctx.pseudonym_key  secret for the reference that stands in for a community member's number
        ctx.on_privacy(phone, event, version, language, message_id)   saves an answer to the privacy notice
        ctx.on_submit(report, session, media, extraction), ctx.on_extract(report, session, draft),
        ctx.on_chatbot(request, response, session),
        ctx.on_escalate(question=, session=, request=, reason=, ...), ctx.log_error(title)   (all optional)
"""

from surveillance.whatsapp import content as C
from surveillance.whatsapp.conversation.ask import Ask, RNotReport
from surveillance.whatsapp.conversation.core import (
	MEDIA_TYPES,
	MIN,
	STATES,
	AttrDict,
	enter,
	format_phone,
	go,
	home,
	media_ack,
	media_allowed,
	nairobi_date,
	new_session,
	normalize,
	normalize_phone,
	parse_date,
	pause,
	resolve_choice,
	run,
	split_text,
	t,
	to_media,
	urgent,
)
from surveillance.whatsapp.conversation.fields import (
	OptionalSelect,
	RCount,
	RDeaths,
	RExtra,
	RName,
	ROnset,
	ROnsetDate,
	RPlace,
	RPlaceGps,
	RPlaceName,
	RRegion,
	RSubCounty,
	RSymptoms,
	RSymptomsMore,
	SelectStep,
)
from surveillance.whatsapp.conversation.portal import Help, Lang, Menu, NotStaff, Reports, Resume, Welcome
from surveillance.whatsapp.conversation.privacy import Privacy, PrivacyNotice, needs_notice, notice_gate
from surveillance.whatsapp.conversation.report import (
	RConsent,
	RDescribe,
	RDone,
	RDuplicate,
	REdit,
	RReview,
	verify_staff,
)
from surveillance.whatsapp.conversation.steps import BACK_TO, step_back
from surveillance.whatsapp.messages import text

__all__ = [
	"MEDIA_TYPES",
	"AttrDict",
	"format_phone",
	"handle",
	"nairobi_date",
	"new_session",
	"normalize_phone",
	"parse_date",
	"split_text",
]


def handle(s, inp, ctx):
	"""Answer one incoming message. Returns the messages to send; never raises."""
	try:
		return dispatch(s, inp, ctx)
	except Exception:
		if getattr(ctx, "log_error", None):
			ctx.log_error("WhatsApp conversation failed")
		return [text(t(s)["errorGeneric"])]


def staff_still_valid(s, ctx):
	"""SRS R62: the account is checked on every message, not only when the staff menu opens. The session lasts
	30 days, so a deactivated user or a number given to someone else must not keep the old roles."""
	fresh = ctx.data.find_staff(s.phone)
	if not fresh or fresh["user"] != s.staff.user:
		return False
	label = s.staff.region_label if s.staff.region == fresh.get("region") else None
	s.staff = AttrDict.wrap(fresh)
	if label:
		s.staff.region_label = label
	return True


def dispatch(s, inp, ctx):
	now = ctx.now()
	previous_active = s.last_active
	first = not s.last_active
	idle = not first and now - s.last_active > ctx.settings.idle_minutes * MIN
	s.last_active = now
	kw = normalize(inp.get("text")) if inp["type"] == "text" else None

	if kw and kw in C.KEYWORDS["privacy"]:
		if s.draft and s.state != "resume":
			s.resume_state = s.state
		return enter(s, "privacy", ctx)
	if needs_notice(s) and s.state != "privacy":
		return notice_gate(s, inp, ctx, previous_active, dispatch)

	if s.staff and not staff_still_valid(s, ctx):
		s.draft = None
		s.resume_state = None
		return run(s, verify_staff(s, ctx), ctx)

	drafting = bool(s.draft) and s.state != "resume"
	if s.draft:  # messages sent while drafting, for on_report_stats
		s.draft.messages = (s.draft.messages or 0) + 1
	if first or (kw and kw in C.KEYWORDS["greeting"]):
		return pause(s, ctx, idle) if drafting else enter(s, "welcome", ctx)
	if kw and kw in C.KEYWORDS["language"]:
		if drafting:
			s.resume_state = s.state
		return enter(s, "lang", ctx)
	if kw and kw in C.KEYWORDS["menu"]:
		return pause(s, ctx, idle) if drafting else enter(s, home(s), ctx)
	if kw and kw in C.KEYWORDS["help"]:
		return enter(s, "help", ctx)
	if kw and kw in C.KEYWORDS["cancel"]:
		had = bool(s.draft)
		s.draft = None
		return run(s, go(home(s), *([text(t(s)["cancelled"])] if had else [])), ctx)
	if idle and drafting:
		return pause(s, ctx, True)
	if kw and kw in C.KEYWORDS["back"] and s.draft and s.state in BACK_TO:
		return run(s, step_back(s, ctx), ctx)

	st = STATES.get(s.state) or STATES["welcome"]
	if inp["type"] == "media" and s.draft and not media_allowed(inp):
		return [text(t(s)["mediaRefused"]), *st.prompt(s, ctx)]
	choice = resolve_choice(st.options(s, ctx), inp, s.shown)
	res = st.on(s, inp, choice, ctx)
	if res:
		out = run(s, res, ctx)
		# The help screen already lists the emergency numbers; anywhere else they go first.
		return [text(t(s)["emergency"]), *out] if urgent(inp) and s.state != "help" else out
	if urgent(inp):
		return enter(s, "help", ctx)

	if inp["type"] == "media" and s.draft:
		s.draft.media.append(to_media(inp))
		return [text(media_ack(s, inp))]
	return [text(t(s)["invalid"]), *(STATES.get(s.state) or STATES["welcome"]).prompt(s, ctx)]


STATES.update(
	{
		"privacy_notice": PrivacyNotice(),
		"privacy": Privacy(),
		"welcome": Welcome(),
		"not_staff": NotStaff(),
		"lang": Lang(),
		"menu": Menu(),
		"reports": Reports(),
		"ask": Ask(),
		"help": Help(),
		"resume": Resume(),
		"r_describe": RDescribe(),
		"r_not_report": RNotReport(),
		"r_name": RName(),
		"r_category": SelectStep("r_category", "category", "category"),
		"r_signal": SelectStep("r_signal", "signal_type", "signal"),
		"r_symptoms": RSymptoms(),
		"r_symptoms_more": RSymptomsMore(),
		"r_count": RCount(),
		"r_age": OptionalSelect("r_age", "age_group", "age"),
		"r_exposure": OptionalSelect("r_exposure", "animal_exposure", "exposure"),
		"r_deaths": RDeaths(),
		"r_region": RRegion(),
		"r_subcounty": RSubCounty(),
		"r_place": RPlace(),
		"r_place_gps": RPlaceGps(),
		"r_place_name": RPlaceName(),
		"r_onset": ROnset(),
		"r_onset_date": ROnsetDate(),
		"r_extra": RExtra(),
		"r_review": RReview(),
		"r_duplicate": RDuplicate(),
		"r_consent": RConsent(),
		"r_edit": REdit(),
		"r_done": RDone(),
	}
)
