"""Conversation state per phone number, in Redis (frappe.cache), kept after the last message for the number of days
in WhatsApp Settings (30 unless changed).

Survives app restarts and deploys. Redis is not persisted on a standard bench, so a restart of
redis-cache itself (e.g. a server reboot) loses unfinished drafts; submitted reports are safe in the database.
"""

import json

import frappe
from frappe.utils import cint

from surveillance.whatsapp import data
from surveillance.whatsapp.conversation import AttrDict, new_session

KEY = "whatsapp:session:{}"
DEFAULT_DAYS = 30
DAY = 24 * 3600


def load(phone):
	# expires=True: read Redis every time. Otherwise a miss is kept in frappe.local.cache for the rest of the
	# job, and a job that answers several messages from one number would start a new session for each.
	raw = frappe.cache.get_value(KEY.format(phone), expires=True)
	return AttrDict.wrap(json.loads(raw)) if raw else new_session(phone)


def save(session):
	days = cint(data.settings().session_retention_days) or DEFAULT_DAYS
	frappe.cache.set_value(KEY.format(session.phone), json.dumps(session, default=str), expires_in_sec=days * DAY)


def clear(phone):
	frappe.cache.delete_value(KEY.format(phone))
