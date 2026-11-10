"""Questions to the Response Support Chatbot, and messages that were not a report."""

import uuid

from surveillance.whatsapp.conversation.core import (
	AttrDict,
	State,
	_call,
	go,
	home,
	normalize,
	normalize_phone,
	quiet,
	split_text,
	t,
)
from surveillance.whatsapp.conversation.free_text import describe
from surveillance.whatsapp.conversation.report import begin_report, report_from_question, seed_report
from surveillance.whatsapp.conversation.steps import ask, choose, first_missing, missing_steps
from surveillance.whatsapp.messages import menu, text
from surveillance.whatsapp.redact import pseudonym, redact


def _chatbot_options(s, ctx):
	return (
		[{"id": "ask", "title": t(s)["menuAsk"], "aliases": ["ask", "question", "uliza", "swali"]}]
		if ctx.chatbot
		else []
	)


def _user_ref(s, ctx):
	"""Staff by login, as the chatbot's access decision needs. A community member's number stays in Frappe."""
	if s.staff:
		return s.staff.user
	return pseudonym(normalize_phone(s.phone), getattr(ctx, "pseudonym_key", None))


def _is_question(inp, ctx):
	return bool(ctx.chatbot) and inp["type"] == "text" and len(normalize(inp.get("text"))) >= 3


class Ask(State):
	def options(self, s, ctx):
		return [
			*((s.question or {}).get("options") or []),
			{"id": "report", "title": t(s)["menuReport"], "aliases": ["report", "ripoti", "taarifa"]},
			{"id": "menu", "title": t(s)["backToMenu"]},
		]

	def prompt(self, s, ctx):
		s.question = None
		s.shown = ["menu"]
		return [
			menu(
				t(s)["askPrompt"] if s.staff else t(s)["askPromptCommunity"],
				[{"id": "menu", "title": t(s)["backToMenu"]}],
			)
		]

	def on(self, s, inp, choice, ctx):
		if choice == "menu":
			return go(home(s))
		if choice == "report":
			q = s.question
			return report_from_question(s, q.text, ctx) if q and q.get("report") else begin_report(s, ctx)
		if choice and choice.startswith("p:") and s.question:
			return ask_chatbot(s, s.question.text, ctx, choice[2:])
		if inp["type"] == "text" and normalize(inp.get("text")):
			return ask_chatbot(s, inp["text"], ctx)
		return None


class RNotReport(State):
	"""A description with no sign of illness is never dropped (SRS H.12): a report after all, or passed on."""

	def options(self, s, ctx):
		return [
			{"id": "sick", "title": t(s)["notReportSick"], "aliases": ["yes", "ndiyo"]},
			{"id": "other", "title": t(s)["notReportOther"], "aliases": ["no", "hapana"]},
			{"id": "menu", "title": t(s)["backToMenu"]},
		]

	def prompt(self, s, ctx):
		return [choose(s, t(s)["notReport"], self.options(s, ctx))]

	def on(self, s, inp, choice, ctx):
		if choice == "sick":
			s.draft.followups = missing_steps(s, ctx)
			return go(first_missing(s, ctx))
		if choice == "menu":
			s.draft = None
			return go(home(s))
		if choice == "other":
			question = s.draft.description
			s.draft = None
			if ctx.chatbot:
				return ask_chatbot(s, question, ctx)
			req = {"request_id": str(uuid.uuid4()), "user_ref": _user_ref(s, ctx)}
			_call(ctx, "on_escalate", question=question, session=s, request=req, reason="not_a_report")
			return go("r_done", text(t(s)["notReportPassed"]))
		if inp["type"] == "text" and len(normalize(inp.get("text"))) >= 3:
			return describe(s, inp["text"], ctx)
		return None


def ask_chatbot(s, question, ctx, selected_protocol_id=None):
	"""Roles and region come from Frappe, never from the message. The reply is approved content or a fixed
	template and is shown unchanged; the conversation then stays in `ask`."""
	s.state = "ask"
	s.page = 0
	roles = ctx.data.roles_of(s.staff.user) if s.staff else []
	req = {
		"message": redact(question),
		"roles": roles or ["Guest"],
		"language": s.lang,
		"location": s.staff.region if s.staff else None,
		"selected_protocol_id": selected_protocol_id,
		"user_ref": _user_ref(s, ctx),
		"request_id": str(uuid.uuid4()),
		# The bot does not run report counts for the user, so it never offers that capability.
		"capabilities": [],
	}
	try:
		r = ctx.chatbot.ask(req)
	except Exception as e:
		_call(
			ctx,
			"on_escalate",
			question=question,
			session=s,
			request=req,
			reason="service_unavailable",
			error=str(e),
		)
		return quiet(text(t(s)["askUnavailable"](t(s)["askTeam"])))
	_call(ctx, "on_chatbot", request=req, response=r, session=s)
	reply = [text(part) for part in split_text(r["message"])] if r.get("message") else []

	if r.get("outcome") == "clarify" and r.get("options"):
		options = [{"id": f"p:{o['protocol_id']}", "title": o["title"]} for o in r["options"]]
		s.question = AttrDict(text=question, options=options)
		return quiet(ask(s, t(s)["askClarify"], options, extra=[{"id": "menu", "title": t(s)["backToMenu"]}]))
	s.question = None

	def offer_report():
		s.question = AttrDict(text=question, options=[], report=True)
		return choose(
			s,
			t(s)["askRouted"] if r.get("outcome") == "routed" else t(s)["askMixed"],
			[
				{"id": "report", "title": t(s)["menuReport"]},
				{"id": "menu", "title": t(s)["backToMenu"]},
			],
		)

	if r.get("outcome") == "routed":
		return (not s.staff and seed_report(s, question, ctx)) or quiet(offer_report())
	if r.get("route") == "report_count":
		return quiet(text(t(s)["askCount"]))
	if r.get("escalate") or r.get("outcome") == "escalate":
		_call(
			ctx, "on_escalate", question=question, session=s, request=req, reason=r.get("reason"), response=r
		)
	if r.get("route") == "mixed":
		return quiet(*reply, offer_report())
	return quiet(*(reply or [text(t(s)["askUnavailable"](t(s)["askTeam"]))]))
