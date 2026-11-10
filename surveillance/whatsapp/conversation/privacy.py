"""The privacy notice and consent (DPA data subject clauses, Clause 12.3), and the PRIVACY keyword.

Nothing a person sends reaches a report or an AI service until they have agreed to the current notice: the first
message waits in the session and is answered afterwards. Each answer goes in the WhatsApp Consent Log first, so a
person is only treated as having agreed once that is on record. Changing C.PRIVACY_VERSION asks everyone again.
"""

import uuid

from surveillance.whatsapp import content as C
from surveillance.whatsapp.conversation.core import (
	STATES,
	AttrDict,
	State,
	_call,
	go,
	home,
	quiet,
	resolve_choice,
	t,
	urgent,
)
from surveillance.whatsapp.conversation.steps import choose
from surveillance.whatsapp.messages import text


def needs_notice(s):
	return s.privacy_version != C.PRIVACY_VERSION


def _record(s, ctx, event):
	"""Raises if it can't be saved, so the person's answer is not acted on: they get the error reply and are asked again."""
	save = getattr(ctx, "on_privacy", None)
	if save:
		save(
			phone=s.phone,
			event=event,
			version=C.PRIVACY_VERSION,
			language=s.lang,
			message_id=getattr(ctx, "message_id", None),
		)


class PrivacyNotice(State):
	def options(self, s, ctx):
		return [
			{"id": "agree", "title": "Agree / Nakubali", "aliases": ["agree", "yes", "ndiyo", "nakubali", "kubali"]},
			{"id": "decline", "title": "Decline / Sikubali", "aliases": ["decline", "no", "hapana", "sikubali", "kataa"]},
		]

	def prompt(self, s, ctx):
		return [choose(s, C.PRIVACY_NOTICE, self.options(s, ctx))]


def notice_gate(s, inp, ctx, last_active, answer):
	"""Before agreeing, every message comes here. `answer(s, inp, ctx)` handles the waiting message afterwards."""
	st = STATES["privacy_notice"]
	if s.state != "privacy_notice":
		s.held = AttrDict(inp=inp, state=s.state, last_active=last_active)
		s.state = "privacy_notice"
		return [*([text(t(s)["emergency"])] if urgent(inp) else []), *st.prompt(s, ctx)]
	choice = resolve_choice(st.options(s, ctx), inp, s.shown)
	if choice == "agree":
		_record(s, ctx, "Accepted")
		s.privacy_version = C.PRIVACY_VERSION
		held, s.held = s.held or AttrDict(inp={"type": "text", "text": "hi"}, state="welcome", last_active=0), None
		s.state, s.last_active = held.state, held.last_active
		return answer(s, held.inp, ctx)
	if choice == "decline":
		_record(s, ctx, "Declined")
		s.held = s.draft = None
		s.state = "welcome"
		return [text(C.PRIVACY_DECLINED)]
	return [*([text(t(s)["emergency"])] if urgent(inp) else []), *st.prompt(s, ctx)]


class Privacy(State):
	"""What the keyword opens, whether or not the person has agreed: withdrawing can't depend on agreeing first."""

	def options(self, s, ctx):
		return [
			{"id": "withdraw", "title": t(s)["privacyWithdraw"], "aliases": ["withdraw", "ondoa"]},
			{"id": "request", "title": t(s)["privacyRequest"], "aliases": ["delete", "see", "futa"]},
			{"id": "back", "title": t(s)["back"]},
		]

	def prompt(self, s, ctx):
		return [text(t(s)["privacyFull"]), choose(s, t(s)["privacyAsk"], self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "back":
			return go(_back(s))
		if choice == "withdraw":
			_record(s, ctx, "Withdrawn")
			s.privacy_version = s.draft = s.resume_state = s.staff = s.mode = s.seed = s.question = None
			s.state = "welcome"
			return quiet(text(t(s)["privacyWithdrawn"]))
		if choice == "request":
			_record(s, ctx, "Data Request")
			_call(
				ctx,
				"on_escalate",
				question="Asked to see, correct or delete their information.",
				session=s,
				request={"request_id": str(uuid.uuid4()), "user_ref": s.staff.user if s.staff else "privacy request"},
				reason="privacy_request",
			)
			return go(_back(s), text(t(s)["privacyRequested"]))
		return None


def _back(s):
	if s.draft:
		return "resume"
	return "welcome" if needs_notice(s) else home(s)
