app_name = "surveillance"
app_title = "Surveillance"
app_publisher = "Good Partners"
app_description = "KRCS AI-Enabled Public Health Surveillance System"
app_email = "maureen@goodpartnerske.org"
app_license = "mit"


website_route_rules = [
    {"from_route": "/surveillance/<path:app_path>", "to_route": "surveillance"},
]
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "surveillance",
# 		"logo": "/assets/surveillance/logo.png",
# 		"title": "Surveillance",
# 		"route": "/surveillance",
# 		"has_permission": "surveillance.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/surveillance/css/surveillance.css"
# app_include_js = "/assets/surveillance/js/surveillance.js"

# include js, css files in header of web template
# web_include_css = "/assets/surveillance/css/surveillance.css"
# web_include_js = "/assets/surveillance/js/surveillance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "surveillance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "surveillance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "surveillance.utils.jinja_methods",
# 	"filters": "surveillance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "surveillance.install.before_install"
# after_install = "surveillance.install.after_install"

after_migrate = [
	"surveillance.alert_thresholds.seed_defaults",
	"surveillance.case_definitions.seed_case_definitions",
	"surveillance.locations.seed_sub_counties",
	"surveillance.weekly_counts.seed_reporting_facilities",
	"surveillance.alert_thresholds.seed_extra_diseases", 
	"surveillance.capabilities.after_migrate",
	"surveillance.whatsapp.setup.after_migrate",
]

# Fixtures: shipped with the app and installed on every site on migrate
SURVEILLANCE_ROLES = [
	"HQ Admin", "Public Health HQ", "CHP", "CDSC", "MOH DDSR",
	"Surveillance Officer", "Public Health Officer", "HIS Officer", "Facility Health Worker", "Data & AI Administrator",
	"Knowledge Base Client", "WhatsApp Bot",
]

fixtures = [
	{"dt": "Custom Field", "filters": [["name", "in", ["User-primary_role", "User-account_status", "User-assigned_region", "User-assigned_sub_county"]]]},
	{"dt": "Role", "filters": [["name", "in", SURVEILLANCE_ROLES]]},
	{"dt": "Surveillance Role"},
	{"dt": "Region"},
	{"dt": "Symptom"},
]

# Uninstallation
# ------------

# before_uninstall = "surveillance.uninstall.before_uninstall"
# after_uninstall = "surveillance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "surveillance.utils.before_app_install"
# after_app_install = "surveillance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "surveillance.utils.before_app_uninstall"
# after_app_uninstall = "surveillance.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "surveillance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events


WHATSAPP_CATALOG = {
	"on_update": "surveillance.whatsapp.data.clear_catalog_cache",
	"on_trash": "surveillance.whatsapp.data.clear_catalog_cache",
}

doc_events = {
	"Surveillance Event": {
		"before_save": "surveillance.risk.on_event_save",
	},
	"Notification Log": {
		"after_insert": "surveillance.push.on_notification",
	},
	"Case Report": {
		"validate": "surveillance.case_report_rules.validate_complete",
		"on_update": ["surveillance.events.on_case_report", "surveillance.transcription.on_case_report"],
		"on_trash": "surveillance.events.on_case_report_trash",
	},
	# WhatsApp: staff are matched by User.mobile_no; lists come from these DocTypes
	"User": {
		"after_insert": "surveillance.whatsapp.data.clear_staff_cache",
		"on_update": "surveillance.whatsapp.data.clear_staff_cache",
		"on_trash": "surveillance.whatsapp.data.clear_staff_cache",
	},
	"Region": WHATSAPP_CATALOG,
	"Sub County": WHATSAPP_CATALOG,
	"Symptom": WHATSAPP_CATALOG,
	"Community Advice": WHATSAPP_CATALOG,
}
# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }


# Scheduled Tasks
# ---------------


scheduler_events = {
	"daily": ["surveillance.knowledge_base.retire_expired", "surveillance.knowledge_base.notify_upcoming_reviews", "surveillance.chatbot_log.purge_old_logs",
		"surveillance.kb_ops.daily_reconcile", "surveillance.context.import_weather",
		"surveillance.event_tasks.daily_reminders", "surveillance.whatsapp.retention.daily"],
	"hourly_long": ["surveillance.cbs_feed.hourly", "surveillance.risk.refresh_open", "surveillance.push.check_receipts",
		"surveillance.transcription.retry_failed"],
	"daily_long": ["surveillance.cbs_feed.daily"],
}
# scheduler_events = {
# 	"all": [
# 		"surveillance.tasks.all"
# 	],
# 	"daily": [
# 		"surveillance.tasks.daily"
# 	],
# 	"hourly": [
# 		"surveillance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"surveillance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"surveillance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "surveillance.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "surveillance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "surveillance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["surveillance.utils.before_request"]
# after_request = ["surveillance.utils.after_request"]

# Job Events
# ----------
# before_job = ["surveillance.utils.before_job"]
# after_job = ["surveillance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"surveillance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Case Reports: CHPs (View Own Reports) only see the reports they submitted
permission_query_conditions = {
	"Case Report": "surveillance.report_access.case_report_query",
}
has_permission = {
	"Case Report": "surveillance.report_access.case_report_permission",
}

# Mobile app background sync: "Authorization: device <key>:<secret>" (one key per phone, see field_api)
auth_hooks = ["surveillance.field_api.device_auth"]
