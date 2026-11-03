"""Knowledge Base access decision: who is asking and what they may retrieve (SRS R62-R65, AI/ML spec 3.8.1).

One function, resolve(), is used by every Knowledge Base API (search, ask, get_passage) and by the chatbot gateway,
so the same rules apply on every channel (R62: "the same authorisation semantics ... across conversational
interfaces, APIs, administrative interfaces, retrieval services"). The decision is made before anything is sent to
Qdrant, the re-ranker or the LLM; the resulting filter is applied inside the vector search.

Who is asking
    direct call       the logged-in user (web, mobile)
    on_behalf_of      the chatbot service (capability kb_service) names the end user; Frappe looks them up itself.
                      "<user id>" for staff, "whatsapp:+<phone>" / "phone:+<phone>" / "Guest" for the public.
                      Roles, region and capabilities are read from the User record, never taken from the caller (R63).
    editor preview    holders of manage_knowledge_base may search as another audience or region, or include drafts,
                      only with an explicit preview (preview=1, include_drafts=1, audience or region). Previews are
                      flagged in the Chatbot Query Log. Without one, editors search as themselves (administrative
                      separation, R62).

MayAccess (R62) is evaluated as:
    IdentityValid      the user exists (or is an anonymous public actor)
    AccountActive      enabled and account_status Active (empty counts as Active: the field defaults to Active,
                       and the WhatsApp channel uses the same rule)
    Capability         the end user holds use_knowledge_base (public actors: public guidance must be enabled)
    Audience / scope   applied as a filter on approval, audience roles and region, inside Qdrant
    ResourceActive / WithinEffectiveDates   approval Approved, effective_from <= today <= expiry (and review date
                       when kb_hide_after_review_date, default on), also inside Qdrant
"""
import frappe
from frappe import _
from frappe.utils import cint

from surveillance.capabilities import get_user_capabilities, has_capability

POLICY_VERSION = "kb-access-2"
MANAGE = "manage_knowledge_base"
USE = "use_knowledge_base"
SERVICE = "kb_service"
PUBLIC_PREFIXES = ("whatsapp:", "phone:", "sms:", "ussd:")
ALL_ROLES = "All roles"
ALL_REGIONS = "All regions"


class KBAccessDenied(frappe.PermissionError):
	"""A protected Knowledge Base action was refused. `code` is the deny reason logged in the Chatbot Query Log."""

	def __init__(self, message, code="DENIED"):
		super().__init__(message)
		self.code = code


def _deny(code, message=None):
	raise KBAccessDenied(message or _("You do not have permission to perform this action."), code)


def _split(value):
	if isinstance(value, str) and value.strip().startswith("["):
		value = frappe.parse_json(value)
	if isinstance(value, (list, tuple)):
		return [str(v).strip() for v in value if str(v).strip()]
	return [v.strip() for v in (value or "").split(",") if v.strip()]


def surveillance_roles():
	return set(frappe.get_all("Surveillance Role", pluck="name"))


def is_public_ref(ref):
	ref = (ref or "").strip()
	return ref == "Guest" or ref.lower().startswith(PUBLIC_PREFIXES)


def account_active(row):
	return bool(row and cint(row.enabled) and (row.get("account_status") or "Active") == "Active")


def _user_row(user):
	fields = ["name", "enabled", "assigned_region"]
	meta = frappe.get_meta("User")
	for f in ("account_status", "assigned_sub_county", "primary_role"):
		if meta.has_field(f):
			fields.append(f)
	return frappe.db.get_value("User", user, fields, as_dict=True)


def _staff_context(user, row):
	roles = sorted(set(frappe.get_roles(user)) & surveillance_roles())
	return {
		"user": user, "user_ref": user, "actor_class": "Staff", "roles": roles,
		"regions": [row.assigned_region] if row.get("assigned_region") else None,
		"sub_county": row.get("assigned_sub_county"),
		"capabilities": get_user_capabilities(user),
	}


def _public_context(ref):
	if not cint(frappe.conf.get("kb_public_enabled")):
		_deny("PUBLIC_NOT_ENABLED", _("Public guidance is not enabled."))
	return {"user": None, "user_ref": ref, "actor_class": "Public", "roles": [], "regions": None,
		"sub_county": None, "capabilities": set()}


def resolve(on_behalf_of=None, audience=None, region=None, include_drafts=0, preview=0):
	"""Return the access context for this request, or raise KBAccessDenied / ValidationError.

	ctx keys: user, user_ref, caller, actor_class (Staff | Public | Editor preview), roles (list, or None = every
	audience), regions (list, or None = every region), approved_only, preview, policy_version, capabilities.
	"""
	caller = frappe.session.user
	if caller == "Guest":
		_deny("NOT_LOGGED_IN")
	caller_row = _user_row(caller)
	if caller != "Administrator" and not account_active(caller_row):
		_deny("ACCOUNT_INACTIVE", _("Your account is not active."))
	is_editor = has_capability(MANAGE)
	is_service = has_capability(SERVICE)
	wants_preview = bool(cint(preview) or cint(include_drafts) or audience or region)

	if on_behalf_of:
		if not is_service:
			_deny("PROXY_NOT_ALLOWED", _("You cannot search on behalf of another user."))
		ref = str(on_behalf_of).strip()
		if is_public_ref(ref):
			ctx = _public_context(ref)
		else:
			row = _user_row(ref)
			if not row:
				_deny("USER_UNKNOWN", _("Unknown user."))
			if not account_active(row):
				_deny("ACCOUNT_INACTIVE", _("This user's account is not active."))
			if not has_capability(USE, ref) and not has_capability(MANAGE, ref):
				_deny("NO_CAPABILITY", _("This user may not use the knowledge base."))
			ctx = _staff_context(ref, row)
		# a service call names a person; its audience/region claims are ignored (R63)
		ctx.update(approved_only=True, preview=False, ignored_claims=bool(audience or region))
	elif wants_preview and (audience or region) and is_service and not is_editor:
		if not cint(frappe.conf.get("kb_allow_legacy_audience")):
			frappe.throw(_("on_behalf_of is required: name the user, not their roles."))
		ctx = _legacy_service_context(audience, region)
	elif wants_preview:
		if not is_editor:
			_deny("PREVIEW_NOT_ALLOWED", _("You cannot search on behalf of another role or region."))
		ctx = _preview_context(caller, audience, region, include_drafts)
	else:
		if not (has_capability(USE) or is_editor):
			_deny("NO_CAPABILITY")
		ctx = _staff_context(caller, caller_row or frappe._dict()) if caller != "Administrator" else \
			{"user": caller, "user_ref": caller, "actor_class": "Staff", "roles": [], "regions": None,
				"sub_county": None, "capabilities": get_user_capabilities(caller)}
		ctx.update(approved_only=True, preview=False)
	ctx["caller"] = caller
	ctx["policy_version"] = POLICY_VERSION
	return ctx


def _clean_roles(audience):
	valid = surveillance_roles()
	return [r for r in _split(audience) if r in valid or r == ALL_ROLES]  # unknown roles are ignored, not fatal


def _clean_regions(region):
	regions = [r for r in _split(region) if r != ALL_REGIONS]
	if not regions:
		return None
	by_name = {r.region_name: r.name for r in frappe.get_all("Region", fields=["name", "region_name"])}
	out, unknown = [], []
	for r in regions:
		if r in by_name.values():
			out.append(r)
		elif r in by_name:
			out.append(by_name[r])
		else:
			unknown.append(r)
	if unknown:
		frappe.throw(_("Unknown region(s): {0}").format(", ".join(unknown)))
	return out


def _preview_context(caller, audience, region, include_drafts):
	return {"user": caller, "user_ref": caller, "actor_class": "Editor preview",
		"roles": _clean_roles(audience) if audience else None,
		"regions": _clean_regions(region) if region else None, "sub_county": None,
		"approved_only": not cint(include_drafts), "preview": True,
		"capabilities": get_user_capabilities(caller)}


def _legacy_service_context(audience, region):
	"""Pre-November contract (audience/region named by the service). Off unless kb_allow_legacy_audience."""
	return {"user": None, "user_ref": None, "actor_class": "Legacy service", "roles": _clean_roles(audience) or [],
		"regions": _clean_regions(region), "sub_county": None, "approved_only": True, "preview": False,
		"capabilities": set()}
