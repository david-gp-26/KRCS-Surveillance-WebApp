// Full app menu (officers, admins). Items are filtered by capability.
export const SIDEBAR_MENU = [
  { section: 'OVERVIEW', items: [
    { label: 'Dashboard', icon: 'LayoutGrid', page: 'dashboard', requiresCapability: null },
    { label: 'My Tasks', icon: 'ClipboardCheck', page: 'my-tasks', requiresCapability: 'receive_tasks' },
  ]},
  { section: 'FIELD ACTIVITIES', items: [
    { label: 'Reports', icon: 'FileText', page: 'reports', requiresCapability: 'view_reports' },
    { label: 'Review Queue', icon: 'BellRing', page: 'alerts-signals', requiresCapability: 'view_review_queue' },
    { label: 'Epi Trends', icon: 'TrendingUp', page: 'epi-trends', requiresCapability: 'view_alerts' },
    { label: 'Surveillance Map', icon: 'Map', page: 'surveillance-map', requiresCapability: 'view_surveillance_map' },
  ]},
  { section: 'RESPONSE', items: [
    { label: 'Response Protocols', icon: 'Layers', page: 'response-protocols', requiresCapability: 'view_response_protocols' },
    { label: 'Response', icon: 'MessageSquareShare', page: 'response', requiresCapability: 'view_review_queue' },
    { label: 'Event Lifecycle', icon: 'LifeBuoy', page: 'event-lifecycle', requiresCapability: 'view_review_queue' },
    { label: 'Knowledge Base', icon: 'BookOpen', page: 'knowledge-base', requiresCapability: ['manage_knowledge_base', 'approve_knowledge_base'] },
    { label: 'AI Data Assistant', icon: 'Sparkles', page: 'ai-data-assistant', requiresCapability: null },
    { label: 'Chatbot Query Log', icon: 'MessagesSquare', page: 'chatbot-query-log', requiresCapability: 'view_chatbot_logs' },
  ]},
  { section: 'DATA', items: [
    { label: 'Analytics', icon: 'BarChart3', page: 'analytics', requiresCapability: 'view_analytics' },
    { label: 'Data Explorer', icon: 'FileSearch', page: 'data-explorer', requiresCapability: 'view_analytics' },
    { label: 'Data Quality', icon: 'CircleDashed', page: 'data-quality', requiresCapability: 'view_data_quality' },
    { label: 'Reporting Channels', icon: 'Radar', page: 'channels', requiresCapability: null },
    { label: 'Facility Data', icon: 'FileSpreadsheet', page: 'facility-data', requiresCapability: 'upload_facility_data' },
    { label: 'Context Data', icon: 'CloudSun', page: 'context-data', requiresCapability: null },
  ]},
  { section: 'ADMINISTRATION', items: [
    { label: 'User Management', icon: 'Users', page: 'user-management', requiresCapability: 'view_users' },
    { label: 'Audit Log', icon: 'ClipboardList', page: 'audit-log', requiresCapability: 'view_audit_log' },
    { label: 'Settings', icon: 'Settings', page: 'settings', requiresCapability: null },
    { label: 'Help Center', icon: 'HelpCircle', page: 'help-center', requiresCapability: null },
  ]},
]

// CHP workspace menu (Figma "CHP" screens). Only these pages are reachable for CHPs.
export const CHP_MENU = [
  { section: 'OVERVIEW', items: [
    { label: 'Dashboard', icon: 'LayoutGrid', page: 'dashboard', requiresCapability: null },
  ]},
  { section: 'REPORTING', items: [
    { label: 'Report', icon: 'FileText', page: 'reports', requiresCapability: 'view_own_reports' },
  ]},
  { section: 'MY WORK', items: [
    { label: 'Follow-ups', icon: 'ClipboardList', page: 'follow-ups', requiresCapability: 'receive_tasks' },
    { label: 'Referrals', icon: 'ArrowRightLeft', page: 'referrals', requiresCapability: 'receive_tasks' },
  ]},
  { section: 'ARTIFICIAL INTELLIGENCE', items: [
    { label: 'AI Assistant', icon: 'Sparkles', page: 'ai-data-assistant', requiresCapability: null },
  ]},
  { section: 'SUPPORT', items: [
    { label: 'Feedback', icon: 'MessageSquareWarning', page: 'feedback', requiresCapability: null },
    { label: 'Help Center', icon: 'HelpCircle', page: 'help-center', requiresCapability: null },
  ]},
  { section: 'SYSTEM', items: [
    { label: 'Settings', icon: 'Settings', page: 'settings', requiresCapability: null },
  ]},
]

// Surveillance Officer workspace menu (Figma "Surveillance Officer" screens)
export const OFFICER_MENU = [
  { section: 'OVERVIEW', items: [
    { label: 'Dashboard', icon: 'LayoutGrid', page: 'dashboard', requiresCapability: null },
  ]},
  { section: 'LIVE MONITORING', items: [
    { label: 'Review Queue', icon: 'BellRing', page: 'alerts-signals', requiresCapability: 'view_review_queue' },
    { label: 'Epi Trends', icon: 'TrendingUp', page: 'epi-trends', requiresCapability: 'view_alerts' },
    { label: 'Surveillance Map', icon: 'Map', page: 'surveillance-map', requiresCapability: 'view_surveillance_map' },
  ]},
  { section: 'OPERATIONS', items: [
    { label: 'Response', icon: 'MessageSquareShare', page: 'response', requiresCapability: 'view_review_queue' },
    { label: 'Event Lifecycle', icon: 'LifeBuoy', page: 'event-lifecycle', requiresCapability: 'view_review_queue' },
    { label: 'Chatbot Query Log', icon: 'MessagesSquare', page: 'chatbot-query-log', requiresCapability: 'view_chatbot_logs' },
  ]},
  { section: 'ANALYTICS', items: [
    { label: 'Data Quality', icon: 'CircleDashed', page: 'data-quality', requiresCapability: 'view_data_quality' },
    { label: 'Trends', icon: 'Activity', page: 'analytics', requiresCapability: 'view_analytics' },
  ]},
  { section: 'ARTIFICIAL INTELLIGENCE', items: [
    { label: 'AI Assistant', icon: 'Sparkles', page: 'ai-data-assistant', requiresCapability: null },
  ]},
  { section: 'SUPPORT', items: [
    { label: 'Feedback', icon: 'MessageSquareWarning', page: 'feedback', requiresCapability: null },
    { label: 'Help Center', icon: 'HelpCircle', page: 'help-center', requiresCapability: null },
  ]},
  { section: 'SYSTEM', items: [
    { label: 'Settings', icon: 'Settings', page: 'settings', requiresCapability: null },
  ]},
]

export const MENUS = { full: SIDEBAR_MENU, chp: CHP_MENU, officer: OFFICER_MENU }

// Pages each workspace may open (menu pages plus their detail pages). 'full' = no restriction.
export const WORKSPACE_PAGES = {
  chp: ['login', 'dashboard', 'reports', 'report-detail', 'record-health-signal', 'follow-ups', 'referrals',
    'ai-data-assistant', 'feedback', 'help-center', 'settings', 'my-tasks'],
  officer: ['login', 'dashboard', 'alerts-signals', 'alerts-signals-detail', 'epi-trends', 'alert-detail', 'surveillance-map',
    'response', 'event-lifecycle', 'data-quality', 'analytics', 'ai-data-assistant', 'feedback', 'help-center', 'settings',
    'reports', 'report-detail', 'response-protocols', 'my-tasks', 'chatbot-query-log'],
}
