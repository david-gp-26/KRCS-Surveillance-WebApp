"""
Capabilities: business-level permissions for the KRCS surveillance app.

Sources of truth:
  - WHAT capabilities exist   -> CAPABILITIES below (code, in git)
  - WHO has which capability  -> "Role Capability" records (data, edited in the Roles & Permissions page)
  - Frappe DocType permissions for managed DocTypes are DERIVED from those two by
    sync_role_permissions(). Do not edit them by hand in Role Permissions Manager:
    the next sync (every `bench migrate`) overwrites them.
"""
import frappe
from frappe import _
from frappe.permissions import setup_custom_perms

ROLE_CAPABILITY = "Role Capability"
RESERVED_ROLES = {"Administrator", "System Manager", "Guest", "All"}

# key -> definition. "grants" = Frappe permissions this capability gives on each DocType.
# Grants on DocTypes that don't exist yet are skipped and applied automatically once the DocType exists.
CAPABILITIES = [
	# Case Reports
	{"key": "view_reports", "name": "View Reports", "category": "Case Reports",
	 "description": "View all case reports in the user's area", "grants": {"Case Report": ["read"]}},
	{"key": "view_own_reports", "name": "View Own Reports", "category": "Case Reports",
	 "description": "View only the reports the user submitted (e.g. CHPs)", "grants": {"Case Report": ["read"]}},
	{"key": "create_reports", "name": "Create Reports", "category": "Case Reports",
	 "description": "Submit new case reports",
	 "grants": {"Case Report": ["read", "create"], "Region": ["read"], "Symptom": ["read"], "Sub County": ["read"]}},
	{"key": "edit_reports", "name": "Edit Reports", "category": "Case Reports",
	 "description": "Edit existing case reports", "grants": {"Case Report": ["read", "write"]}},
	{"key": "delete_reports", "name": "Delete Reports", "category": "Case Reports",
	 "description": "Delete case reports", "grants": {"Case Report": ["read", "delete"]}},
	{"key": "export_reports", "name": "Export Reports", "category": "Case Reports",
	 "description": "Export case reports to file", "grants": {"Case Report": ["read", "export"]}},
	{"key": "verify_suspected_disease", "name": "Verify Suspected Disease", "category": "Case Reports",
	 "description": "Confirm or change the suspected disease on a case report", "grants": {"Case Report": ["read"]}},

	# Alerts & Risk
	{"key": "view_alerts", "name": "View Alerts", "category": "Alerts & Risk",
	 "description": "View alerts and signals", "grants": {"Risk Alert": ["read"]}},
	{"key": "manage_alert_thresholds", "name": "Manage Alert Thresholds", "category": "Alerts & Risk",
	 "description": "Add diseases and change alert thresholds",
	 "grants": {"Alert Threshold Config": ["read", "write", "create"],
	            "Alert Threshold Settings": ["read", "write"]}},
	{"key": "investigate_alerts", "name": "Investigate Alerts", "category": "Alerts & Risk",
	 "description": "Change alert status and add investigation notes", "grants": {"Risk Alert": ["read", "write"]}},
    

		# Review Queue
	{"key": "view_review_queue", "name": "View Review Queue", "category": "Review Queue",
	 "description": "See reported events for your region",
	 "grants": {"Surveillance Event": ["read"], "Surveillance Signal": ["read"]}},
	{"key": "act_on_events", "name": "Act on Events", "category": "Review Queue",
	 "description": "Verify, discard, escalate and close events",
	 "grants": {"Surveillance Event": ["read", "write"], "Event Task": ["read", "write", "create"]}},
	{"key": "view_all_tasks", "name": "View All Tasks", "category": "Review Queue",
	 "description": "See every task assigned in your region and whether it was completed (e.g. SCDSC)",
	 "grants": {"Event Task": ["read"]}},
	{"key": "receive_tasks", "name": "Receive Tasks", "category": "Review Queue",
	 "description": "Get follow-ups and referrals from officers and record referrals (e.g. CHPs)",
	 "grants": {"Event Task": ["read"]}},

	 
	# Response
	{"key": "view_response_protocols", "name": "View Response Protocols", "category": "Response",
	 "description": "View response protocols", "grants": {"Response Protocol": ["read"]}},
	{"key": "manage_response_protocols", "name": "Manage Response Protocols", "category": "Response",
	 "description": "Create, edit and approve response protocols",
	 "grants": {"Response Protocol": ["read", "write", "create", "delete"]}},
	{"key": "view_chatbot_logs", "name": "View Chatbot Query Log", "category": "Response",
	 "description": "View questions asked to the response chatbot", "grants": {"Chatbot Query Log": ["read"]}},
	{"key": "handle_chatbot_escalations", "name": "Handle Chatbot Escalations", "category": "Response",
	 "description": "Follow up questions the chatbot escalated to a person", "grants": {"Chatbot Query Log": ["read", "write"]}},

	# Users & Roles
	{"key": "view_users", "name": "View Users", "category": "Users & Roles",
	 "description": "View user accounts", "grants": {"User": ["read"]}},
	{"key": "manage_users", "name": "Manage Users", "category": "Users & Roles",
	 "description": "Create and edit user accounts", "grants": {"User": ["read", "write", "create"]}},
	{"key": "manage_roles", "name": "Manage Roles & Permissions", "category": "Users & Roles",
	 "description": "Change which capabilities each role has", "grants": {}},
    {"key": "view_all_regions", "name": "View All Regions", "category": "Users & Roles",
	 "description": "See events and dashboard figures for every region, even if the user has a region assigned",
	 "grants": {}},

	# Analytics
	{"key": "view_analytics", "name": "View Analytics", "category": "Analytics",
	 "description": "View analytics dashboards", "grants": {}},
	{"key": "view_surveillance_map", "name": "View Surveillance Map", "category": "Analytics",
	 "description": "View the surveillance map", "grants": {}},
	{"key": "export_data", "name": "Export Data", "category": "Analytics",
	 "description": "Export analytics data", "grants": {}},

	# Audit
	{"key": "view_audit_log", "name": "View Audit Log", "category": "Audit",
	 "description": "View the change history of records", "grants": {"Version": ["read"]}},

	# Reference Data
	{"key": "manage_reference_data", "name": "Manage Regions & Symptoms", "category": "Reference Data",
	 "description": "Add and edit regions and symptoms",
	 "grants": {"Region": ["read", "write", "create"], "Symptom": ["read", "write", "create"],
	            "Sub County": ["read", "write", "create"]}},

	{"key": "manage_context_data", "name": "Manage Context Data", "category": "Reference Data",
	 "description": "Record WASH assessments and population figures, and refresh weather",
	 "grants": {"Camp WASH Assessment": ["read"], "Population Bulletin Import": ["read"], "Weather Snapshot": ["read"]}},

    # Facility Data
	{"key": "upload_facility_data", "name": "Upload Facility Data", "category": "Facility Data",
	 "description": "Upload MOH 505 (IDSR) exports from KHIS and manage the reporting facility list",
	 "grants": {"Reporting Facility": ["read"], "IDSR Upload": ["read"]}},

	# Knowledge Base
	{"key": "manage_knowledge_base", "name": "Manage Knowledge Base", "category": "Knowledge Base",
	 "description": "Upload, reindex and delete AI knowledge base documents", "grants": {"Knowledge Document": ["read", "write", "create", "delete"]}},
	{"key": "approve_knowledge_base", "name": "Approve Knowledge Base", "category": "Knowledge Base",
	 "description": "Approve or retire knowledge base documents", "grants": {"Knowledge Document": ["read", "write"]}},
	{"key": "use_knowledge_base", "name": "Use Knowledge Base", "category": "Knowledge Base",
	 "description": "Search approved knowledge base documents for your own role", "grants": {}},
	{"key": "kb_service", "name": "Knowledge Base Service Access", "category": "Knowledge Base",
	 "description": "Search on behalf of another role (chatbot service account only)", "grants": {}},
	{"key": "view_sensitive_kb", "name": "View Sensitive Knowledge Base Content", "category": "Knowledge Base",
	 "description": "Read Knowledge Base documents marked Sensitive", "grants": {}},
	{"key": "view_restricted_kb", "name": "View Restricted Knowledge Base Content", "category": "Knowledge Base",
	 "description": "Read Knowledge Base documents with audience class Restricted", "grants": {}},
	{"key": "kb_national_scope", "name": "Knowledge Base National Scope", "category": "Knowledge Base",
	 "description": "Read Knowledge Base documents for every region and sub-county (national staff)", "grants": {}},
]
CAPABILITIES += [
	# Workspaces: which simple dashboard and menu a role gets. Admins never get these automatically.
	{"key": "chp_workspace", "name": "CHP Workspace", "category": "Workspaces",
	 "description": "Simple CHP dashboard and menu: report, follow-ups, referrals, AI assistant, feedback",
	 "grants": {}},
	{"key": "officer_workspace", "name": "Surveillance Officer Workspace", "category": "Workspaces",
	 "description": "Officer dashboard and menu: Review Queue, Epi Trends, map, response, event lifecycle, data quality",
	 "grants": {}},
	{"key": "view_data_quality", "name": "View Data Quality", "category": "Analytics",
	 "description": "See and check data quality issues (missing places, late or duplicate reports, facility completeness)",
	 "grants": {}},
	# Feedback
	{"key": "view_feedback", "name": "View Feedback", "category": "Users & Roles",
	 "description": "Read and resolve feedback sent by users", "grants": {}},
]
CAPABILITY_MAP = {c["key"]: c for c in CAPABILITIES}

# Not given to Administrator / System Manager automatically: these change what the user sees
# (a field worker's menu and dashboard), not what they are allowed to do.
NOT_AUTO_FOR_ADMIN = {"chp_workspace", "officer_workspace", "receive_tasks", "view_own_reports"}

# Workspace for each workspace capability, checked in order. Users without one get the full app.
WORKSPACES = [("chp_workspace", "chp"), ("officer_workspace", "officer")]

# Capabilities set for the CHP role by setup_chp_role (run once; adjust later in Roles & Permissions)
CHP_CAPABILITIES = ["chp_workspace", "create_reports", "view_own_reports", "receive_tasks", "use_knowledge_base"]

# Applied on migrate ONLY to roles that have no capabilities yet, so fresh environments
# (staging, production, KRCS handover) come preconfigured. Add your other roles here.
DEFAULT_ROLE_CAPABILITIES = {
	"HQ Admin": [c["key"] for c in CAPABILITIES],
}


# ---------- checking ----------

def get_user_capabilities(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return set()
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or "System Manager" in roles:
		return set(CAPABILITY_MAP) - NOT_AUTO_FOR_ADMIN
	keys = frappe.get_all(ROLE_CAPABILITY, filters={"role": ["in", list(roles)]}, pluck="capability")
	return {k for k in keys if k in CAPABILITY_MAP}


def has_capability(key, user=None):
	return key in get_user_capabilities(user)


def require_capability(key):
	"""Use at the top of any whitelisted API that changes data."""
	if not has_capability(key):
		frappe.throw(_("You do not have permission to perform this action."), frappe.PermissionError)


# ---------- syncing to Frappe permissions ----------

def _managed_doctypes():
	return {dt for c in CAPABILITIES for dt in c.get("grants", {})}


def sync_role_permissions(role):
	"""Rebuild this role's Frappe permissions on managed DocTypes from its capabilities."""
	if role in RESERVED_ROLES:
		return

	desired = {}
	for key in frappe.get_all(ROLE_CAPABILITY, filters={"role": role}, pluck="capability"):
		for dt, ptypes in CAPABILITY_MAP.get(key, {}).get("grants", {}).items():
			desired.setdefault(dt, set()).update(ptypes)

	for dt in _managed_doctypes():
		if not frappe.db.exists("DocType", dt):
			continue
		setup_custom_perms(dt)  # copies standard rules first, so System Manager etc. keep access
		frappe.db.delete("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0, "if_owner": 0})

		ptypes = desired.get(dt)
		if ptypes:
			ptypes = set(ptypes) | {"read", "report"}  # any access needs read; report enables list/report view
			frappe.get_doc({
				"doctype": "Custom DocPerm",
				"parent": dt,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 0,
				**{p: 1 for p in ptypes},
			}).insert(ignore_permissions=True)

		frappe.clear_cache(doctype=dt)


def sync_all_role_permissions():
	roles = set(frappe.get_all(ROLE_CAPABILITY, pluck="role"))
	for dt in _managed_doctypes():
		roles |= set(frappe.get_all("Custom DocPerm", filters={"parent": dt}, pluck="role"))
	for role in roles - RESERVED_ROLES:
		sync_role_permissions(role)


# ---------- API ----------

@frappe.whitelist()
def get_my_capabilities():
	user = frappe.session.user
	primary_role = frappe.db.get_value("User", user, "primary_role") if user != "Guest" else None
	caps = get_user_capabilities(user)
	workspace = next((name for key, name in WORKSPACES if key in caps), "full")
	return {
		"capabilities": sorted(caps),
		"primary_role": primary_role or "User",
		"workspace": workspace,
		"names": {k: CAPABILITY_MAP[k]["name"] for k in caps},
	}


@frappe.whitelist()
def get_capability_catalog():
	return [{k: c[k] for k in ("key", "name", "category", "description")} for c in CAPABILITIES]


@frappe.whitelist()
def get_role_capabilities(role):
	require_capability("manage_roles")
	enabled = set(frappe.get_all(ROLE_CAPABILITY, filters={"role": role}, pluck="capability"))
	return {
		"role": role,
		"locked": role in RESERVED_ROLES,
		"capabilities": [
			{
				"key": c["key"],
				"name": c["name"],
				"category": c["category"],
				"description": c["description"],
				"enabled": role == "System Manager" or c["key"] in enabled,
			}
			for c in CAPABILITIES
		],
	}


def _truthy(value):
	return str(value).strip().lower() in ("1", "true", "yes", "on")


@frappe.whitelist(methods=["POST"])
def set_role_capability(role, capability, enabled):
	require_capability("manage_roles")

	if role in RESERVED_ROLES:
		frappe.throw(_("{0} is a system role and cannot be changed here").format(role))
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))
	if capability not in CAPABILITY_MAP:
		frappe.throw(_("Unknown capability: {0}").format(capability))

	enabled = _truthy(enabled)

	# Stop admins from removing their own last route to managing roles
	if capability == "manage_roles" and not enabled and role in frappe.get_roles():
		user_roles = set(frappe.get_roles()) - {role}
		if "System Manager" not in user_roles and not frappe.db.exists(
			ROLE_CAPABILITY, {"role": ["in", list(user_roles) or [""]], "capability": "manage_roles"}
		):
			frappe.throw(_("You can't remove your own access to Roles & Permissions"))

	existing = frappe.db.exists(ROLE_CAPABILITY, {"role": role, "capability": capability})
	if enabled and not existing:
		frappe.get_doc({"doctype": ROLE_CAPABILITY, "role": role, "capability": capability}).insert(
			ignore_permissions=True
		)
	elif not enabled and existing:
		frappe.delete_doc(ROLE_CAPABILITY, existing, ignore_permissions=True)

	sync_role_permissions(role)
	return get_role_capabilities(role)


# ---------- setup ----------

def after_migrate():
	for role, keys in DEFAULT_ROLE_CAPABILITIES.items():
		if not frappe.db.exists("Role", role) or frappe.db.exists(ROLE_CAPABILITY, {"role": role}):
			continue
		for key in keys:
			frappe.get_doc({"doctype": ROLE_CAPABILITY, "role": role, "capability": key}).insert(
				ignore_permissions=True
			)
	sync_all_role_permissions()
	frappe.db.commit()


def setup_chp_role(role="CHP"):
	"""Give the CHP role exactly the CHP capabilities (removes others, e.g. View Reports for all reports).
	bench --site <site> execute surveillance.capabilities.setup_chp_role"""
	if not frappe.db.exists("Role", role):
		frappe.throw(f"Role {role} does not exist")
	before = set(frappe.get_all(ROLE_CAPABILITY, filters={"role": role}, pluck="capability"))
	frappe.db.delete(ROLE_CAPABILITY, {"role": role})
	for key in CHP_CAPABILITIES:
		frappe.get_doc({"doctype": ROLE_CAPABILITY, "role": role, "capability": key}).insert(ignore_permissions=True)
	sync_role_permissions(role)
	frappe.db.commit()
	print(f"{role}: removed {sorted(before - set(CHP_CAPABILITIES)) or 'nothing'}; now {CHP_CAPABILITIES}")


OFFICER_CAPABILITIES = ["officer_workspace", "view_review_queue", "act_on_events", "view_alerts", "investigate_alerts",
	"view_surveillance_map", "view_response_protocols", "view_analytics", "view_reports", "verify_suspected_disease",
	"view_data_quality", "use_knowledge_base"]


def setup_officer_role(role="Surveillance Officer"):
	"""Give the Surveillance Officer role the officer workspace capabilities (keeps any others it already has).
	bench --site <site> execute surveillance.capabilities.setup_officer_role"""
	if not frappe.db.exists("Role", role):
		frappe.throw(f"Role {role} does not exist")
	have = set(frappe.get_all(ROLE_CAPABILITY, filters={"role": role}, pluck="capability"))
	added = [k for k in OFFICER_CAPABILITIES if k not in have]
	for key in added:
		frappe.get_doc({"doctype": ROLE_CAPABILITY, "role": role, "capability": key}).insert(ignore_permissions=True)
	sync_role_permissions(role)
	frappe.db.commit()
	print(f"{role}: added {added or 'nothing'}; now has {sorted(have | set(added))}")


def reset_managed_permissions():
	"""ONE-TIME cleanup in dev: removes Custom DocPerms created by the old Server Scripts, then rebuilds."""
	for dt in _managed_doctypes():
		frappe.db.delete("Custom DocPerm", {"parent": dt})
		frappe.clear_cache(doctype=dt)
	after_migrate()