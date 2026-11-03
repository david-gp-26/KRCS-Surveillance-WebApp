const BASE = ''


function getCookie(name) {
  const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)')
  return match ? decodeURIComponent(match.pop()) : null
}


export const csrfToken = () => window.FRAPPE_CSRF_TOKEN || ''
export const currentUserFullName = () => (getCookie('full_name') || 'User').replace(/^"|"$/g, '')
export const currentUserId = () => (getCookie('user_id') || '').replace(/^"|"$/g, '')

function extractErrorMessage(data) {
  if (data && typeof data._server_messages === 'string') {
    try {
      const messages = JSON.parse(data._server_messages)
      for (const raw of messages) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && parsed.message) return parsed.message
        } catch (e) {
          if (raw) return raw
        }
      }
    } catch (e) {
      // ignore malformed _server_messages
    }
  }
  return (data && data.exception) || 'Request failed'
}

async function callMethod(path) {
  const res = await fetch(`${BASE}${path}`)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw Object.assign(new Error(extractErrorMessage(data)), { status: res.status })
  }
  return data.message
}

async function callMethodPost(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': csrfToken(),
    },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw Object.assign(new Error(extractErrorMessage(data)), { status: res.status })
  }
  return data.message
}

export async function getCurrentUser() {
  const email = currentUserId()
  if (!email || email === 'Guest') return null
  return getDoc('User', email)
}

export async function getMySurveillanceRole() {
  const user = await getCurrentUser()

  if (!user || !user.roles) {
    return null
  }

  const roles = user.roles
    .map(r => r.role)
    .filter(Boolean)

  // Get roles that are defined as Surveillance roles
  const surveillanceRoles = await getRoles()

  const surveillanceRoleNames = surveillanceRoles.map(r => r.role)

  return roles.find(role =>
    surveillanceRoleNames.includes(role)
  ) || null
}

export async function getMyCapabilities() {
  const message = (await callMethod('/api/method/surveillance.capabilities.get_my_capabilities')) || {}
  return {
    capabilities: message.capabilities || [],
    primary_role: message.primary_role || '',
    workspace: message.workspace || 'full',
    names: message.names || {},
  }
}

export async function getCapabilityCatalog() {
  return (await callMethod('/api/method/surveillance.capabilities.get_capability_catalog')) || []
}

export async function getAlertThresholds() {
  return callMethod('/api/method/surveillance.alert_thresholds.get_alert_thresholds')
}

export async function addDisease({ disease_name, threshold, category, priority, icd11_code, icd11_title, icd11_uri }) {
  const body = { disease_name, threshold, category }
  if (priority !== undefined) body.priority = priority
  if (icd11_code !== undefined) body.icd11_code = icd11_code
  if (icd11_title !== undefined) body.icd11_title = icd11_title
  if (icd11_uri !== undefined) body.icd11_uri = icd11_uri
  return callMethodPost('/api/method/surveillance.alert_thresholds.add_disease', body)
}

export async function searchIcd11(q) {
  return callMethod('/api/method/surveillance.icd11.search_icd11?q=' + encodeURIComponent(q))
}

export async function setIcd11(diseaseKey, { code, title, uri }) {
  return callMethodPost('/api/method/surveillance.icd11.set_icd11', {
    disease_key: diseaseKey,
    code,
    title,
    uri,
  })
}

export async function saveAlertThresholds(thresholds, outbreakMultiplier, priorities) {
  return callMethodPost('/api/method/surveillance.alert_thresholds.save_alert_thresholds', {
    thresholds,
    outbreak_multiplier: outbreakMultiplier,
    priorities,
  })
}

export async function login(usr, pwd) {
  const res = await fetch(`${BASE}/api/method/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `usr=${encodeURIComponent(usr)}&pwd=${encodeURIComponent(pwd)}`,
  })
  return res.ok
}


export async function logout() {
  await fetch(`${BASE}/api/method/logout`, {
    method: 'POST',
    headers: { 'X-Frappe-CSRF-Token': csrfToken() },
  })
}


export async function getList(doctype, fields, opts = {}) {
  const params = new URLSearchParams({
    fields: JSON.stringify(fields),
    limit_page_length: opts.limit || 200,
    limit_start: opts.start || 0,
  })
  if (opts.orderBy) params.set('order_by', opts.orderBy)
  if (opts.filters && Object.keys(opts.filters).length) {
    params.set('filters', JSON.stringify(Object.entries(opts.filters).map(([k, v]) => [k, '=', v])))
  }
  const res = await fetch(`${BASE}/api/resource/${encodeURIComponent(doctype)}?${params}`)
  const data = await res.json()
  return data.data || []
}


export async function getCount(doctype, filtersObj = {}) {
  const filters = Object.entries(filtersObj).map(([k, v]) => [k, '=', v])
  const res = await fetch(`${BASE}/api/method/frappe.client.get_count?doctype=${encodeURIComponent(doctype)}&filters=${encodeURIComponent(JSON.stringify(filters))}`)
  const data = await res.json()
  return data.message || 0
}


export async function insertDoc(doc) {
  const res = await fetch(`${BASE}/api/method/frappe.client.insert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken() },
    body: JSON.stringify({ doc }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.exception || 'Request failed')
  }
  return res.json()
}


export function exportExcel(doctype, fields) {
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = '/api/method/frappe.desk.reportview.export_query'
  form.target = '_blank'
  const data = { doctype, file_format_type: 'Excel', fields: JSON.stringify(fields) }
  Object.entries(data).forEach(([k, v]) => {
    const input = document.createElement('input')
    input.type = 'hidden'; input.name = k; input.value = v
    form.appendChild(input)
  })
  document.body.appendChild(form)
  form.submit()
  form.remove()
}

export async function getDoc(doctype, name) {
  const res = await fetch(
    `${BASE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`
  )

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.exception || data._server_messages || 'Failed to fetch document')
  }

  return data.data
}


export async function createDoc(doctype, fields) {
  const res = await fetch(
    `${BASE}/api/resource/${encodeURIComponent(doctype)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken(),
      },
      body: JSON.stringify(fields),
    }
  )

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new Error(
      data.exception ||
      data.message ||
      data._server_messages ||
      'Failed to create document'
    )
  }

  return data.data
}


export async function createUser(userData) {
  return createDoc('User', {
    doctype: 'User',
    email: userData.email,
    first_name: userData.first_name,
    last_name: userData.last_name || '',
    user_type: 'System User',

    primary_role: userData.primary_role || '',
    roles: userData.primary_role
      ? [{ role: userData.primary_role }]
      : [],

    assigned_region: userData.assigned_region || '',
    assigned_sub_county: userData.assigned_sub_county || '',
    mobile_no: (userData.mobile_no || '').trim(),
    account_status: userData.account_status || 'Active',

    enabled:
      userData.account_status !== 'Inactive' &&
      userData.account_status !== 'Suspended',

    new_password: userData.password,
    send_welcome_email: 0,
  })
}

export async function updateDoc(doctype, name, fields) {
  const res = await fetch(
    `${BASE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': csrfToken(),
      },
      body: JSON.stringify(fields),
    }
  )

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new Error(
      data.exception ||
      data.message ||
      data._server_messages ||
      'Update failed'
    )
  }

  return data.data
}


export async function getUserRoles(name) {
  const doc = await getDoc('User', name)
  return (doc.roles || []).map((r) => r.role)
}

export async function updateUser(name, userData) {
  const newRole = userData.primary_role || ''
  if (newRole === 'System Manager') {
    throw new Error('System Manager cannot be assigned from this form.')
  }

  const existing = await getDoc('User', name)
  const oldRole = existing.primary_role || ''
  let roles = existing.roles || []

  if (newRole !== oldRole) {
    roles = roles.filter((r) => r.role !== oldRole)
    if (newRole && !roles.some((r) => r.role === newRole)) {
      roles = [...roles, { role: newRole }]
    }
  }

  return updateDoc('User', name, {
    first_name: userData.first_name,
    last_name: userData.last_name || '',

    primary_role: newRole,
    roles,
    assigned_region: userData.assigned_region || '',
    assigned_sub_county: userData.assigned_sub_county || '',
    mobile_no: (userData.mobile_no || '').trim(),
    account_status: userData.account_status || 'Active',

    enabled: userData.account_status !== 'Inactive' &&
             userData.account_status !== 'Suspended',
  })
}


export async function deleteDoc(doctype, name) {
  const res = await fetch(
    `${BASE}/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
    {
      method: 'DELETE',
      headers: {
        'X-Frappe-CSRF-Token': csrfToken(),
      },
    }
  )

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    throw new Error(
      data.exception ||
      data.message ||
      data._server_messages ||
      'Delete failed'
    )
  }

  return true
}


export async function deleteUser(name) {
  return deleteDoc('User', name)
}

export async function getUsers(opts = {}) {
  return getList(
    'User',
    [
      'name',
      'first_name',
      'last_name',
      'full_name',
      'user_image',
      'primary_role',
      'assigned_region',
      'assigned_sub_county',
      'mobile_no',
      'account_status',
      'last_login',
      'enabled'
    ],
    {
      limit: opts.limit || 50,
      start: opts.start || 0,
      orderBy: 'creation desc'
    }
  )
}


export async function getRoles() {
  return getList(
    'Surveillance Role',
    ['name', 'role'],
    { limit: 200, start: 0, orderBy: 'role asc' }
  )
}

export async function getRegions() {
  return getList(
    'Region',
    ['name', 'region_name'],
    {
      limit: 200,
      start: 0,
      orderBy: 'region_name asc'
    }
  )
}


export async function createRole(roleName) {
  await createDoc('Role', {
    doctype: 'Role',
    role_name: roleName,
    name: roleName,
  })
  return createDoc('Surveillance Role', {
    doctype: 'Surveillance Role',
    role: roleName,
  })
}
export async function createRegion(regionData) {
  return createDoc('Region', {
    doctype: 'Region',
    ...regionData,
  })
}

export async function getRoleCapabilities(role) {
  return callMethod('/api/method/surveillance.capabilities.get_role_capabilities?role=' + encodeURIComponent(role))
}

export async function setRoleCapability(role, capability, enabled) {
  return callMethodPost('/api/method/surveillance.capabilities.set_role_capability', { role, capability, enabled })
}

export function exportCsv(filename, rows, columns) {
  const escape = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const header = columns.map((c) => escape(c.label)).join(',')
  const lines = rows.map((row) => columns.map((c) => escape(c.value(row))).join(','))
  const csv = [header, ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const AI_MOCK_RESPONSES = [
  {
    match: /cholera/i,
    answer: 'Here is the latest cholera case breakdown by region based on current surveillance data.',
    table: {
      columns: ['Region', 'Confirmed Cases', 'Suspected Cases', 'Trend'],
      rows: [
        ['Garissa', 42, 15, 'Rising'],
        ['Dadaab', 31, 9, 'Rising'],
        ['Wajir', 12, 6, 'Stable'],
        ['Mombasa', 5, 2, 'Falling'],
      ],
    },
  },
  {
    match: /alert/i,
    answer: 'Found 4 active alerts matching your query, sorted by severity.',
    table: {
      columns: ['Alert ID', 'Signal', 'Location', 'Severity', 'Status'],
      rows: [
        ['ALT-021', 'Cholera Cluster', 'Dadaab', 'Critical', 'Open'],
        ['ALT-018', 'Measles Spike', 'Garissa', 'High', 'Investigating'],
        ['ALT-014', 'AWD Increase', 'Wajir', 'Medium', 'Open'],
        ['ALT-009', 'Malnutrition Rise', 'Turkana', 'Medium', 'Closed'],
      ],
    },
  },
  {
    match: /case|report/i,
    answer: 'Here is a summary of recent case reports across all channels.',
    table: {
      columns: ['Status', 'Count'],
      rows: [
        ['Submitted', 28],
        ['Reviewed', 54],
        ['Linked', 12],
        ['Investigating', 7],
      ],
    },
  },
]

function buildMockAiAnswer(question) {
  const hit = AI_MOCK_RESPONSES.find((r) => r.match.test(question))
  if (hit) return { answer: hit.answer, table: hit.table }
  const fallback = 'I looked into "' + question + '" but no matching data source is wired up yet. Try asking about cholera cases, alerts, or reports.'
  return { answer: fallback }
}

/*
|--------------------------------------------------------------------------
| AI Data Assistant
|--------------------------------------------------------------------------
|
| Backed by mock data for now. Once the backend AI/NL-to-query endpoint
| exists, swap the body of queryAiAssistant() for a real API call that
| resolves the same shape: { answer: string, table?: { columns, rows } }.
| The page consuming this function only depends on that return shape.
*/
export async function queryAiAssistant(question) {
  await new Promise((resolve) => setTimeout(resolve, 600 + Math.random() * 500))
  return buildMockAiAnswer(question)
}

// ---------- Analytics ----------
// In src/api/frappe.js: DELETE the nine mock analytics functions (getAnalyticsSummary, getDiseaseTrends,
// getFacilityResponseTime, getAiPredictiveForecast, getMonthOverMonthComparison, getResponseTimeImprovement,
// getAgeGenderDistribution, getAlertReportingPattern, getResponseEffectivenessScore) and their MOCK_ data,
// then paste this in their place.

export async function getAnalytics({ weeks = 13, source = 'all', disease = '' } = {}) {
  const qs = new URLSearchParams({ weeks, source })
  if (disease) qs.set('disease', disease)
  return callMethod(`/api/method/surveillance.analytics.get_analytics?${qs}`)
}



export async function getDashboard(trendSource = 'community') {
  return callMethod('/api/method/surveillance.dashboard.get_dashboard?trend_source=' + encodeURIComponent(trendSource))
}

/*
|--------------------------------------------------------------------------
| Surveillance Officer Dashboard
|--------------------------------------------------------------------------
|
| Backed by mock data for now. Each function resolves the exact shape the
| SurveillanceDashboard page expects, so swapping in real data later just
| means replacing the function body with a fetch/getList call that
| resolves to the same shape - no changes needed in the page.
*/

const MOCK_SURVEILLANCE_OFFICER_STATS = [
  { key: 'new_signals', label: 'New signals', value: '18', icon: 'FileText', changePct: 12.5, trend: 'down', sentiment: 'positive' },
  { key: 'priority_alerts', label: 'Priority alerts', value: '3', icon: 'CheckCircle', changePct: 8.3, trend: 'down', sentiment: 'negative' },
  { key: 'awaiting_verification', label: 'Awaiting verification', value: '2', icon: 'ArrowLeftRight', changePct: 15.2, trend: 'down', sentiment: 'positive' },
  { key: 'active_investigations', label: 'Active investigations', value: '3', icon: 'CheckCheck', changePct: 6.8, trend: 'down', sentiment: 'negative' },
]

const MOCK_SIGNAL_TREND = {
  labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5', 'Week 6'],
  data: [4, 5, 3, 7, 12, 18],
}

const MOCK_PRIORITY_ALERT_QUEUE = [
  { id: 'PAQ-001', title: 'Suspected acute watery diarrhea cluster', location: 'Dagahaley, Dadaab - Block B4', status: 'pending', affected: 14, risk: 87 },
  { id: 'PAQ-002', title: 'Acute Watery Diarrhea Cluster', location: 'Dagahaley, Dadaab', status: 'critical', affected: 12, risk: 94 },
  { id: 'PAQ-003', title: 'Measles Suspected Cases', location: 'Kalobeyei Zone 1', status: 'pending', affected: 5, risk: 90 },
]

// ---------- Surveillance Officer workspace ----------

const OFFICER = '/api/method/surveillance.officer.'

export async function getOfficerDashboard() {
  return callMethod(`${OFFICER}get_officer_dashboard`)
}

export async function getLifecycle({ search = '', severity = '', stage = '' } = {}) {
  const qs = new URLSearchParams()
  if (search) qs.set('search', search)
  if (severity) qs.set('severity', severity)
  if (stage) qs.set('stage', stage)
  return callMethod(`${OFFICER}get_lifecycle?${qs}`)
}

export async function getEventLifecycle(event) {
  return callMethod(`${OFFICER}get_event_lifecycle?event=${encodeURIComponent(event)}`)
}

export async function getDataQuality(days = 30) {
  return callMethod(`${OFFICER}get_data_quality?days=${days}`)
}

export async function dismissDataIssue(key, note) {
  return callMethodPost(`${OFFICER}dismiss_issue`, { key, note: note || '' })
}

export async function getResponseActions(status = '', search = '') {
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  if (search) qs.set('search', search)
  return callMethod(`/api/method/surveillance.event_tasks.get_response_actions?${qs}`)
}

export async function getEventsForResponse() {
  return (await callMethod('/api/method/surveillance.event_tasks.get_events_for_response')) || []
}

export async function createResponseAction(a) {
  return callMethodPost('/api/method/surveillance.event_tasks.create_response_action', {
    event: a.event, title: a.title, assigned_to: a.assignedTo, due_date: a.dueDate, team: a.team || '', instructions: a.instructions || '',
  })
}

export async function getSurveillanceOfficerStats() {
  return MOCK_SURVEILLANCE_OFFICER_STATS
}

export async function getSignalTrend() {
  return MOCK_SIGNAL_TREND
}

export async function getPriorityAlertQueue() {
  return MOCK_PRIORITY_ALERT_QUEUE
}
export async function getAlertsSignals(opts = {}) {
  return (await callMethod(`/api/method/surveillance.alerts.get_alerts?limit=${opts.limit || 500}`)) || []
}
export async function getAlertRegions() {
  return (await callMethod('/api/method/surveillance.alerts.get_alert_regions')) || []
}
export async function getAlertSignal(id) {
  return callMethod('/api/method/surveillance.alerts.get_alert?name=' + encodeURIComponent(id))
}
export async function updateAlertStatus(id, status) {
  return callMethodPost('/api/method/surveillance.alerts.update_alert_status', { name: id, status })
}
export async function investigateAlert(id) {
  return callMethodPost('/api/method/surveillance.alerts.investigate_alert', { name: id })
}
export async function reviewAlert(id, outcome, note) {
  return callMethodPost('/api/method/surveillance.alerts.review_alert', { name: id, outcome, note })
}
export async function reopenAlert(id) {
  return callMethodPost('/api/method/surveillance.alerts.reopen_alert', { name: id })
}
export async function addAlertNote(id, note) {
  return callMethodPost('/api/method/surveillance.alerts.add_alert_note', { name: id, note })
}
export async function getMapData(weeks = 8) {
  return callMethod(`/api/method/surveillance.alerts.get_map_data?weeks=${weeks}`)
}
export async function getMapEvents(params = {}) {
  const q = new URLSearchParams({
    status: params.status || 'open',
    days: String(params.days || 30),
  })
  if (params.disease) q.set('disease', params.disease)
  return callMethod(`/api/method/surveillance.events.get_map_events?${q.toString()}`)
}

export async function mergeEvents(event, into, note) {
  return callMethodPost('/api/method/surveillance.events.merge_events', { event, into, note })
}


export async function getChannelStats(days = 30) {
  return (await callMethod(`/api/method/surveillance.surveillance.api.get_channel_stats?days=${days}`)) || { channels: [], total: 0, days }
}

export async function getSourceStats(days = 30) {
  const res = await fetch(`/api/method/surveillance.surveillance.api.get_source_stats?days=${days}`, { credentials: 'include' })
  const data = await res.json()
  if (!res.ok) throw new Error(data?._server_messages || data?.exception || 'Could not load data sources')
  return data.message || { sources: [] }
}


export async function getDataExplorerOptions() {
  return callMethod('/api/method/surveillance.data_explorer.get_options')
}

export async function queryDataExplorer(params) {
  return callMethodPost('/api/method/surveillance.data_explorer.query', { params: JSON.stringify(params) })
}

export async function exportDataExplorer(params) {
  return callMethodPost('/api/method/surveillance.data_explorer.export', { params: JSON.stringify(params) })
}

/*
|--------------------------------------------------------------------------
| AI Governance & Monitoring Dashboard (Data & AI Administrator)
|--------------------------------------------------------------------------
|
| Backed by mock data for now. Each function resolves the exact shape the
| AiGovernanceDashboard page expects, so swapping in real data later just
| means replacing the function body with a fetch/getList call that
| resolves to the same shape - no changes needed in the page.
*/

const MOCK_AI_GOVERNANCE_STATS = [
  { key: 'models_in_service', label: 'Models in service', value: '4', icon: 'Sparkles' },
  { key: 'avg_accuracy', label: 'Avg. accuracy', value: '88%', icon: 'LineChart' },
  { key: 'human_override_rate', label: 'Human override rate', value: '12%', icon: 'ThumbsDown' },
  { key: 'since_last_retrain', label: 'Since last retrain', value: '9 Days', icon: 'RefreshCw' },
]

const MOCK_MODEL_REGISTRY = [
  { name: 'Signal Extraction (NLP/NER)', version: 'v2.3', status: 'Production', accuracy: 91, precision: 0.89, recall: 0.86, drift: 'Low', lastRetrained: '2026-06-14' },
  { name: 'Alert Risk Scoring', version: 'v1.8', status: 'Production', accuracy: 88, precision: 0.85, recall: 0.90, drift: 'Low', lastRetrained: '2026-05-30' },
  { name: 'Anomaly Detection', version: 'v3.1', status: 'Production', accuracy: 84, precision: 0.80, recall: 0.87, drift: 'Moderate', lastRetrained: '2026-07-02' },
  { name: 'Outbreak Forecasting', version: 'v1.9', status: 'Shadow', accuracy: 79, precision: 0.76, recall: 0.82, drift: 'Monitoring', lastRetrained: '2026-07-18' },
]

const MOCK_CONFIDENCE_DISTRIBUTION = {
  labels: ['50-60%', '60-70%', '70-80%', '80-90%', '90-100%'],
  data: [12, 24, 41, 58, 33],
}

const MOCK_COMPOSITE_PERFORMANCE = {
  labels: ['Accuracy', 'Precision', 'Recall', 'Timeliness', 'Explainability'],
  data: [88, 85, 87, 90, 72],
}

export async function getAiGovernanceStats() {
  return MOCK_AI_GOVERNANCE_STATS
}

export async function getModelRegistry() {
  return MOCK_MODEL_REGISTRY
}

export async function getConfidenceDistribution() {
  return MOCK_CONFIDENCE_DISTRIBUTION
}

export async function getCompositePerformance() {
  return MOCK_COMPOSITE_PERFORMANCE
}

// --- Reference data lookups (Region, Symptom) — always readable regardless of role ---
let referenceLabelsCache = null
export async function getReferenceLabels() {
  if (referenceLabelsCache) return referenceLabelsCache
  const res = await fetch('/api/method/surveillance.surveillance.api.get_reference_labels')
  const data = await res.json()
  referenceLabelsCache = data.message || { regions: {}, symptoms: {} }
  return referenceLabelsCache
}

export async function getAuditLogs(opts = {}) {
  const res = await fetch(`/api/method/surveillance.surveillance.api.get_audit_logs?limit=${opts.limit || 1000}`)
  const data = await res.json()
  return data.message || []
}

// --- Case Report (health signal) CRUD ---
export async function getReport(name) {
  return getDoc('Case Report', name)
}

export async function createReport(fields) {
  const res = await fetch(`${BASE}/api/method/frappe.client.insert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken() },
    body: JSON.stringify({ doc: { doctype: 'Case Report', ...fields } }),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(extractErrorMessage(data).replace(/<[^>]+>/g, ''))
  }
  return data.message
}

export async function updateReport(name, fields) {
  return updateDoc('Case Report', name, fields)
}

export async function deleteReport(name) {
  return deleteDoc('Case Report', name)
}

export async function classifyPreview({ symptoms, age_group, animal_exposure }) {
  const params = new URLSearchParams({ symptoms: JSON.stringify(symptoms || []) })
  if (age_group) params.set('age_group', age_group)
  if (animal_exposure) params.set('animal_exposure', animal_exposure)
  return (await callMethod(`/api/method/surveillance.case_definitions.classify_preview?${params}`)) || []
}

export async function getDiseaseOptions() {
  return (await callMethod('/api/method/surveillance.case_definitions.get_disease_options')) || []
}

export async function setSuspectedDisease(report, disease) {
  return callMethodPost('/api/method/surveillance.case_definitions.set_suspected_disease', {
    report,
    disease,
  })
}

export async function getSubCounties(region) {
  const r = await fetch('/api/method/surveillance.locations.get_sub_counties?region=' + encodeURIComponent(region || ''), { credentials: 'include' })
  const d = await r.json()
  return d.message || []
}

export async function getMyProfile() {
  const res = await fetch('/api/method/surveillance.surveillance.api.get_my_profile')
  const data = await res.json()
  return data.message || { name: '', full_name: '', phone_number: '' }
}

export async function getLoggedInUserPhone() {
  try {
    const res = await fetch('/api/method/frappe.auth.get_logged_user', { credentials: 'include' })
    const data = await res.json()
    const user = data.message
    if (!user || user === 'Guest') return ''
    const doc = await getDoc('User', user)
    return doc.mobile_no || ''
  } catch {
    return ''
  }
}

export async function uploadFile(file, isPrivate = 1) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('is_private', isPrivate)

  const res = await fetch('/api/method/upload_file', {
    method: 'POST',
    headers: { 'X-Frappe-CSRF-Token': window.FRAPPE_CSRF_TOKEN || '' },
    body: formData,
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.exception || 'File upload failed')
  }
  const data = await res.json()
  return data.message.file_url
}


export function uploadFileWithProgress(file, { fileName, isPrivate = 1, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file, fileName || file.name)
    formData.append('is_private', isPrivate)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/method/upload_file')
    xhr.setRequestHeader('X-Frappe-CSRF-Token', window.FRAPPE_CSRF_TOKEN || '')
    xhr.withCredentials = true
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onerror = () => reject(new Error('Network error. Check your connection and retry.'))
    xhr.onload = () => {
      let data = {}
      try { data = JSON.parse(xhr.responseText) } catch { /* non-JSON response */ }
      if (xhr.status >= 200 && xhr.status < 300 && data.message && data.message.file_url) {
        resolve(data.message.file_url)
      } else {
        reject(new Error(extractErrorMessage(data).replace(/<[^>]+>/g, '') || 'File upload failed'))
      }
    }
    xhr.send(formData)
  })
}


// ---------- Knowledge Base API ----------

function frappeErrorMessage(data, status) {
  try {
    if (data?._server_messages) {
      const msgs = JSON.parse(data._server_messages).map((m) => {
        try { return JSON.parse(m).message } catch { return m }
      })
      const text = msgs.join(' ').replace(/<[^>]+>/g, '').trim()
      if (text) return text
    }
  } catch { /* fall through */ }
  if (data?.exception) return String(data.exception).split(':').slice(1).join(':').trim() || data.exception
  if (status === 403) return 'You do not have permission to do this.'
  if (status === 503) return 'The knowledge base is temporarily unavailable. Please try again shortly.'
  return 'Something went wrong. Please try again.'
}

async function kbRequest(method, params = {}, httpMethod = 'GET') {
  const encoded = {}
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null) return
    encoded[k] = Array.isArray(v) ? JSON.stringify(v) : v
  })
  let url = `/api/method/surveillance.knowledge_base.${method}`
  const opts = { method: httpMethod, credentials: 'include', headers: { Accept: 'application/json' } }
  if (httpMethod === 'GET') {
    const qs = new URLSearchParams(encoded).toString()
    if (qs) url += `?${qs}`
  } else {
    opts.headers['Content-Type'] = 'application/json'
    opts.headers['X-Frappe-CSRF-Token'] = window.csrf_token || ''
    opts.body = JSON.stringify(encoded)
  }
  const res = await fetch(url, opts)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(frappeErrorMessage(data, res.status))
    err.status = res.status
    throw err
  }
  return data.message
}

export const getKbDocuments = () => kbRequest('list_documents')

export const createKbDocument = ({ file_url, category, applied_to, diseases, version, language, regions, review_date, expiry_date, effective_from, audience_class, sensitivity }) =>
  kbRequest('create_document', { file_url, category, applied_to, diseases, version, language, regions, review_date, expiry_date, effective_from, audience_class, sensitivity }, 'POST')

export const updateKbDocument = (name, { category, version, applied_to, diseases, language, regions, review_date, expiry_date, effective_from, audience_class, sensitivity }) =>
  kbRequest('update_document', { name, category, version, applied_to, diseases, language, regions, review_date, expiry_date, effective_from, audience_class, sensitivity }, 'POST')

export const setKbApproval = (name, status) => kbRequest('set_approval', { name, status }, 'POST')

export const reindexKbDocument = (name) => kbRequest('reindex_document', { name }, 'POST')

export const deleteKbDocument = (name) => kbRequest('delete_document', { name }, 'POST')

export const searchKnowledgeBase = ({ query, limit = 5, disease, category, language, includeDrafts, preview, audience } = {}) =>
  kbRequest('search', { query, limit, disease, category, language, audience, include_drafts: includeDrafts ? 1 : undefined, preview: preview ? 1 : undefined })

export const askKnowledgeBase = ({ query, language, history = [], streamId } = {}) =>
  kbRequest('ask', { query, language, history: JSON.stringify(history), stream_id: streamId }, 'POST')

export const getKbPassage = (id) => kbRequest('get_passage', { id })

export const getDiseaseVocabulary = () => kbRequest('get_disease_vocabulary')

// Chatbot Query Log (surveillance.chatbot_log)
const qs = (params) => {
  const u = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') u.set(k, v) })
  const s = u.toString()
  return s ? `?${s}` : ''
}
export const listChatbotLogs = (params) => callMethod(`/api/method/surveillance.chatbot_log.list_logs${qs(params)}`)
export const getChatbotLog = (name) => callMethod(`/api/method/surveillance.chatbot_log.get_log${qs({ name })}`)
export const getChatbotMetrics = (params) => callMethod(`/api/method/surveillance.chatbot_log.get_metrics${qs(params)}`)
export const updateChatbotEscalation = (name, status, note) =>
  callMethodPost('/api/method/surveillance.chatbot_log.update_escalation', { name, status, note })
export const submitChatbotFeedback = (name, helpful, comment) =>
  callMethodPost('/api/method/surveillance.chatbot_log.submit_feedback', { name, helpful: helpful ? 1 : 0, comment })

export async function getReviewEvents(params = {}) {
  const qs = new URLSearchParams()
  Object.entries({ status: 'New', ...params }).forEach(([k, v]) => {
    if (v !== '' && v != null) qs.set(k, v)
  })
  return callMethod(`/api/method/surveillance.events.get_events?${qs}`)
}

export async function getReviewEvent(id) {
  return callMethod('/api/method/surveillance.events.get_event?event=' + encodeURIComponent(id))
}

export async function addEventNote(id, note) {
  return callMethodPost('/api/method/surveillance.events.add_note', { event: id, note })
}

export async function setEventStatus(id, action, note, facility) {
  return callMethodPost('/api/method/surveillance.events.set_status', { event: id, action, note, facility: facility || '' })
}

export async function getMyNotifications(limit = 20) {
  return callMethod(`/api/method/surveillance.notifications.get_my_notifications?limit=${limit}`)
}

export async function markNotificationsRead(name) {
  return callMethodPost('/api/method/surveillance.notifications.mark_notifications_read', name ? { name } : {})
}

export async function getEscalationPreview(eventId) {
  return callMethod('/api/method/surveillance.notifications.get_escalation_preview?event=' + encodeURIComponent(eventId))
}

// ---------- Response Protocols ----------

export async function getProtocols({ search, disease, status } = {}) {
  const qs = new URLSearchParams()
  if (search) qs.set('search', search)
  if (disease) qs.set('disease', disease)
  if (status) qs.set('status', status)
  const q = qs.toString()
  return callMethod(`/api/method/surveillance.protocols.list_protocols${q ? `?${q}` : ''}`)
}

export async function getProtocol(id) {
  return callMethod('/api/method/surveillance.protocols.get_protocol?name=' + encodeURIComponent(id))
}

export async function getProtocolForDisease(disease) {
  return callMethod('/api/method/surveillance.protocols.get_protocol_for_disease?disease=' + encodeURIComponent(disease))
}

export async function saveProtocol(data) {
  const body = {
    title: data.title,
    disease: data.disease,
    summary: data.summary,
    version: data.version,
    source: data.source,
    source_url: data.source_url,
    review_date: data.review_date,
    steps: JSON.stringify(data.steps || []),
    questions: JSON.stringify(data.questions || []),
    notify_immediately: data.notifyImmediately ? 1 : 0,
  }
  if (data.name) body.name = data.name
  return callMethodPost('/api/method/surveillance.protocols.save_protocol', body)
}

export async function setProtocolStatus(id, status) {
  return callMethodPost('/api/method/surveillance.protocols.set_protocol_status', { name: id, status })
}

export async function deleteProtocol(id) {
  return callMethodPost('/api/method/surveillance.protocols.delete_protocol', { name: id })
}

export async function getEventChecklist(eventId) {
  return callMethod('/api/method/surveillance.protocols.get_event_checklist?event=' + encodeURIComponent(eventId))
}

export async function toggleEventStep(eventId, n, done) {
  return callMethodPost('/api/method/surveillance.protocols.toggle_event_step', { event: eventId, step_no: n, done })
}

export async function getInvestigation(eventId) {
  return callMethod('/api/method/surveillance.investigation.get_investigation?event=' + encodeURIComponent(eventId))
}

export async function answerVerification(eventId, questionNo, answer) {
  return callMethodPost('/api/method/surveillance.investigation.answer_question', { event: eventId, question_no: questionNo, answer })
}

export async function setStepOutcome(eventId, stepNo, outcome, reason) {
  return callMethodPost('/api/method/surveillance.investigation.set_step_outcome', { event: eventId, step_no: stepNo, outcome: outcome || '', reason: reason || '' })
}

export async function saveFindings(eventId, findings) {
  return callMethodPost('/api/method/surveillance.investigation.save_findings', { event: eventId, findings })
}

export async function addEvidence(eventId, attachmentType, fileUrl, text, consent) {
  return callMethodPost('/api/method/surveillance.investigation.add_evidence', { event: eventId, attachment_type: attachmentType, file_url: fileUrl || '', text: text || '', ...(consent || {}) })
}

export async function removeEvidence(eventId, evidenceId) {
  return callMethodPost('/api/method/surveillance.investigation.remove_evidence', { event: eventId, evidence_id: evidenceId })
}

export async function checkReport(eventId, signalId, reached, meetsCaseDefinition, note) {
  return callMethodPost('/api/method/surveillance.investigation.check_report', {
    event: eventId, signal: signalId, reached: reached || '', meets_case_definition: meetsCaseDefinition || '', note: note || '',
  })
}

export async function splitReport(eventId, signalId, reason) {
  return callMethodPost('/api/method/surveillance.investigation.split_report', { event: eventId, signal: signalId, reason })
}

// export async function getRegions() {
//   const res = await fetch('/api/resource/Region?fields=["name","region_name"]&limit_page_length=0', {
//     credentials: 'include', headers: { Accept: 'application/json' },
//   })
//   const data = await res.json().catch(() => ({}))
//   if (!res.ok) throw new Error(frappeErrorMessage(data, res.status))
//   return (data.data || []).map((r) => r.name)
// }


const FD = '/api/method/surveillance.facility_data'

export async function previewFacilityUpload(fileUrl) {
  return callMethodPost(`${FD}.preview_upload`, { file_url: fileUrl })
}

export async function confirmFacilityUpload(name, runDetection = true) {
  return callMethodPost(`${FD}.confirm_upload`, { name, run_detection: runDetection ? 1 : 0 })
}

export async function discardFacilityUpload(name) {
  return callMethodPost(`${FD}.discard_upload`, { name })
}

export async function getFacilityUploads(limit = 100) {
  return (await callMethod(`${FD}.get_uploads?limit=${limit}`)) || []
}

export async function getFacilityCoverage(weeks = 12) {
  return (await callMethod(`${FD}.get_coverage?weeks=${weeks}`)) || { weeks: [], facilities: [] }
}

export async function getReportingFacilities() {
  return (await callMethod(`${FD}.get_facilities`)) || []
}

export async function saveReportingFacility({ name, facilityName, khisMatch, subCounty, active = true }) {
  return callMethodPost(`${FD}.save_facility`, {
    name: name || null,
    facility_name: facilityName,
    khis_match: khisMatch,
    sub_county: subCounty,
    active: active ? 1 : 0,
  })
}
// ---------- Context data (weather, population, WASH) ----------
// Paste at the END of src/api/frappe.js

const CTX = '/api/method/surveillance.context'

export async function getPlaceContext({ subCounty, county, people, disease } = {}) {
  const qs = new URLSearchParams()
  if (subCounty) qs.set('sub_county', subCounty)
  if (county) qs.set('county', county)
  if (people != null) qs.set('people', people)
  if (disease) qs.set('disease', disease)
  return callMethod(`${CTX}.get_context?${qs}`)
}
export async function getAreaContext() {
  return (await callMethod(`${CTX}.get_area_context`)) || []
}
export async function getContextOptions() {
  return callMethod(`${CTX}.get_options`)
}
export async function getWashAssessments(subCounty) {
  return (await callMethod(`${CTX}.get_wash_assessments${subCounty ? `?sub_county=${encodeURIComponent(subCounty)}` : ''}`)) || []
}
export async function saveWashAssessment(fields) {
  return callMethodPost(`${CTX}.save_wash_assessment`, fields)
}
export async function getPopulationFigures(subCounty) {
  return (await callMethod(`${CTX}.get_population_figures${subCounty ? `?sub_county=${encodeURIComponent(subCounty)}` : ''}`)) || []
}
export async function savePopulationFigure(fields) {
  return callMethodPost(`${CTX}.save_population_figure`, fields)
}
export async function deleteContextRecord(doctype, name) {
  return callMethodPost(`${CTX}.delete_context_record`, { doctype, name })
}
export async function getWeatherStatus() {
  return (await callMethod(`${CTX}.get_weather_status`)) || []
}
export async function getWeatherSeries(subCounty, days = 90) {
  return (await callMethod(`${CTX}.get_weather?sub_county=${encodeURIComponent(subCounty)}&days=${days}`)) || []
}
export async function refreshWeather() {
  return callMethodPost(`${CTX}.refresh_weather`, {})
}

// ---------- Event tasks (field visits, referrals, sample collection, follow-ups) ----------

const TASKS = '/api/method/surveillance.event_tasks.'

export async function getEventTasks(eventId) {
  return callMethod(`${TASKS}get_event_tasks?event=${encodeURIComponent(eventId)}`)
}

export async function getTaskAssignees(eventId) {
  return callMethod(`${TASKS}get_assignees?event=${encodeURIComponent(eventId)}`)
}

export async function createEventTask(eventId, task) {
  return callMethodPost(`${TASKS}create_task`, {
    event: eventId,
    task_type: task.type,
    title: task.title,
    assigned_to: task.assignedTo,
    due_date: task.dueDate,
    instructions: task.instructions || '',
    facility: task.facility || '',
    urgency: task.urgency || '',
    step_phase: task.stepPhase || '',
    step_no: task.stepNo || 0,
  })
}

export async function createFollowups(eventId, assignedTo, days, instructions) {
  return callMethodPost(`${TASKS}create_followups`, { event: eventId, assigned_to: assignedTo, days: days.join(','), instructions: instructions || '' })
}

export async function updateEventTask(taskId, changes) {
  const body = { task: taskId }
  if (changes.status) body.status = changes.status
  if (changes.outcome != null) body.outcome = changes.outcome
  if (changes.dueDate) body.due_date = changes.dueDate
  if (changes.assignedTo) body.assigned_to = changes.assignedTo
  if (changes.progress != null) body.progress = changes.progress
  return callMethodPost(`${TASKS}update_task`, body)
}

export async function deleteEventTask(taskId) {
  return callMethodPost(`${TASKS}delete_task`, { task: taskId })
}

export async function getMyTasks(scope = 'mine', status = 'open', kind = '') {
  return callMethod(`${TASKS}get_my_tasks?scope=${scope}&status=${status}${kind ? `&kind=${kind}` : ''}`)
}

export async function createReferral(r) {
  return callMethodPost(`${TASKS}create_referral`, {
    facility: r.facility, reason: r.reason, case_report: r.caseReport || '',
    age_group: r.ageGroup || '', sex: r.sex || '', urgency: r.urgency || '',
  })
}

export async function getMyReferableReports() {
  return (await callMethod(`${TASKS}get_my_referable_reports`)) || []
}

// ---------- CHP workspace ----------

export async function getChpDashboard() {
  return callMethod('/api/method/surveillance.chp.get_chp_dashboard')
}

export async function getMyAccount() {
  return callMethod('/api/method/surveillance.chp.get_my_account')
}

export async function updateMyProfile(changes) {
  return callMethodPost('/api/method/surveillance.chp.update_my_profile', changes)
}

export async function changeMyPassword(oldPassword, newPassword) {
  return callMethodPost('/api/method/frappe.core.doctype.user.user.update_password', {
    old_password: oldPassword, new_password: newPassword, logout_all_sessions: 0,
  })
}

// ---------- Feedback ----------

const FEEDBACK = '/api/method/surveillance.feedback.'

export async function submitFeedback(type, message, page) {
  return callMethodPost(`${FEEDBACK}submit_feedback`, { feedback_type: type, message, page: page || '' })
}

export async function getMyFeedback() {
  return (await callMethod(`${FEEDBACK}get_my_feedback`)) || []
}

export async function listFeedback(status = '', type = '') {
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  if (type) qs.set('feedback_type', type)
  return callMethod(`${FEEDBACK}list_feedback?${qs}`)
}

export async function setFeedbackStatus(name, status, response) {
  return callMethodPost(`${FEEDBACK}set_feedback_status`, { name, status, ...(response != null ? { response } : {}) })
}

// ---------- Risk score ----------

export async function getRiskWeights() {
  return callMethod('/api/method/surveillance.risk.get_weights')
}

export async function saveRiskWeights(weights) {
  return callMethodPost('/api/method/surveillance.risk.save_weights', { weights })
}

export async function getCbsContact(signal) {
  return callMethod(`/api/method/surveillance.cbs_feed.get_reporter_contact?signal=${encodeURIComponent(signal)}`)
}

export async function getTrendCbsReports(event) {
  return callMethod(`/api/method/surveillance.cbs_feed.get_trend_cbs_reports?event=${encodeURIComponent(event)}`)
}

export async function getReporterAdvice(disease) {
  return callMethod(`/api/method/surveillance.protocols.get_reporter_advice?disease=${encodeURIComponent(disease || '')}`)
}

export async function getRedFlags() {
  return callMethod('/api/method/surveillance.risk.get_red_flags')
}

export async function saveRedFlags(symptoms) {
  return callMethodPost('/api/method/surveillance.risk.save_red_flags', { symptoms: JSON.stringify(symptoms) })
}
