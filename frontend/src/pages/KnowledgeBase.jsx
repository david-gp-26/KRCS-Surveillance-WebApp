import { useMemo, useRef, useState, useEffect, useCallback } from 'react'
import {
  FileText,
  Clock,
  ShieldCheck,
  Database,
  UploadCloud,
  Search,
  SlidersHorizontal,
  RotateCcw,
  Trash2,
  X,
  ChevronDown,
  Check,
  Ban,
  Undo2,
  Pencil,
  MoreHorizontal,
  Loader2,
  AlertTriangle,
  CopyPlus,
} from 'lucide-react'
import AppShell from '../components/layout/AppShell'
import { KB_CATEGORIES, KB_WORKSPACE_LIMIT_BYTES } from '../data/mockKnowledgeBase'
import {
  uploadFile, getKbDocuments, createKbDocument, reindexKbDocument, deleteKbDocument, updateKbDocument,
  setKbApproval, getRoles, getDiseaseOptions, getRegions, searchKnowledgeBase, getKbHealth, runKbReconcile, getSubCounties,
} from '../api/frappe'
import { useCapabilities } from '../context/CapabilitiesContext'

// ---------- constants & helpers ----------

const ALL_ROLES = 'All roles'
const ALL_REGIONS = 'All regions'
const LANGUAGES = [
  { value: 'English', label: 'English', short: 'EN' },
  { value: 'Kiswahili', label: 'Kiswahili', short: 'SW' },
]
const DATE_HELP = 'Expired documents are removed from search automatically.'
const AUDIENCE_CLASSES = [
  { value: 'Public', label: 'Public', help: 'Community members (WhatsApp). Only Public documents are ever shown to them.' },
  { value: 'Community Health Worker', label: 'Community Health Worker', help: 'CHPs and all other staff.' },
  { value: 'Professional', label: 'Professional', help: 'Officers, clinicians and specialists. Not CHPs.' },
  { value: 'Restricted', label: 'Restricted', help: 'Only users allowed to see restricted content.' },
]
const DEFAULT_AUDIENCE_CLASS = 'Community Health Worker'
const VERSION_RE = /^v\d+(\.\d+){0,2}$/
function nextVersion(v) {
  const m = /^v(\d+)/.exec(v || '')
  return m ? `v${Number(m[1]) + 1}.0` : 'v2.0'
}
const AUDIENCE_SHORT = { Public: 'Public', 'Community Health Worker': 'CHW', Professional: 'Professional', Restricted: 'Restricted' }
const ACCEPTED = ['pdf', 'docx', 'txt', 'md']
const MAX_BYTES = 25 * 1024 * 1024

const CONFIDENCE_STYLES = {
  high: 'bg-emerald-500/10 text-emerald-600',
  medium: 'bg-amber-500/10 text-amber-600',
  low: 'bg-gray-100 text-gray-600',
}

const INPUT = 'w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-red-100'
const LABEL = 'block text-sm font-medium text-gray-700 mb-1.5'

const approvalKey = (doc) => String(doc.approvalStatus || 'draft').toLowerCase()

function formatBytes(bytes) {
  if (!bytes) return '0 KB'
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function formatDate(v) {
  if (!v) return ''
  const d = new Date(String(v).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function normalizeRegions(prev, next) {
  if (!next.length) return [ALL_REGIONS]
  if (next.includes(ALL_REGIONS) && next.length > 1) {
    return prev.includes(ALL_REGIONS) ? next.filter((r) => r !== ALL_REGIONS) : [ALL_REGIONS]
  }
  return next
}

function langShort(language) {
  return LANGUAGES.find((l) => l.value === language)?.short || (language ? String(language).slice(0, 2).toUpperCase() : 'EN')
}

function parseDate(v) {
  if (!v) return null
  const d = new Date(String(v).slice(0, 10) + 'T00:00:00')
  return Number.isNaN(d.getTime()) ? null : d
}

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function dateFlags(doc) {
  const today = startOfToday()
  const expiry = parseDate(doc.expiryDate)
  const review = parseDate(doc.reviewDate)
  const expired = !!expiry && expiry < today
  const daysLeft = expiry ? Math.ceil((expiry - today) / 86400000) : null
  return {
    expired,
    expiresSoon: !expired && daysLeft !== null && daysLeft <= 30,
    daysLeft,
    reviewDue: !!review && review < today,
  }
}

function needsAttention(doc) {
  const f = dateFlags(doc)
  return doc.status === 'failed' || f.expired || f.expiresSoon || f.reviewDue
}

function toOptions(list) {
  return (list || []).map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
}

function useClickOutside(ref, handler) {
  useEffect(() => {
    function onClick(e) {
      if (ref.current && !ref.current.contains(e.target)) handler()
    }
    document.addEventListener('click', onClick, true)
    return () => document.removeEventListener('click', onClick, true)
  }, [ref, handler])
}

// ---------- small components ----------

function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 px-5 py-4 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="text-xs font-medium text-gray-400">{label}</div>
        <div className="text-xl font-semibold text-gray-900 mt-1">{value}</div>
        <div className="text-xs text-gray-400 mt-1 truncate">{sub}</div>
      </div>
      <div className="bg-gray-100 rounded-full w-10 h-10 flex items-center justify-center shrink-0">
        <Icon className="w-5 h-5 text-gray-500" />
      </div>
    </div>
  )
}

function SelectField({ value, onChange, children, className = '' }) {
  return (
    <div className={`relative ${className}`}>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${INPUT} appearance-none pr-9`}>
        {children}
      </select>
      <ChevronDown className="w-4 h-4 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
    </div>
  )
}

function MultiSelectDropdown({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const close = useCallback(() => setOpen(false), [])
  useClickOutside(ref, close)
  const normalized = toOptions(options)
  const labelFor = (v) => normalized.find((o) => o.value === v)?.label || v
  const toggleOption = (v) => onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v])
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`${INPUT} flex items-center justify-between gap-3 text-left`}
      >
        <span className={['truncate', selected.length ? 'text-gray-700' : 'text-gray-400'].join(' ')}>
          {selected.length ? selected.map(labelFor).join(', ') : label}
        </span>
        <ChevronDown className={['w-4 h-4 text-gray-400 shrink-0 transition-transform', open ? 'rotate-180' : ''].join(' ')} />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-full bg-white border border-gray-100 rounded-xl shadow-lg py-1 max-h-56 overflow-y-auto">
          {normalized.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2.5 px-3.5 py-2 text-sm text-gray-700 hover:bg-gray-50 cursor-pointer">
              <input type="checkbox" checked={selected.includes(opt.value)} onChange={() => toggleOption(opt.value)} className="accent-red-600" />
              {opt.label}
            </label>
          ))}
          {!normalized.length && <div className="px-3.5 py-2 text-sm text-gray-400">No options</div>}
        </div>
      )}
    </div>
  )
}

function ChipList({ items, className, labelFor = (x) => x, max = 2 }) {
  if (!items?.length) return null
  const shown = items.slice(0, max)
  const rest = items.slice(max)
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {shown.map((k) => (
        <span key={k} className={`text-[11px] px-2 py-0.5 rounded-full ${className}`}>{labelFor(k)}</span>
      ))}
      {!!rest.length && (
        <span title={rest.map(labelFor).join(', ')} className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 cursor-default">
          +{rest.length}
        </span>
      )}
    </div>
  )
}

function StatusBadge({ doc }) {
  const f = dateFlags(doc)
  const a = approvalKey(doc)
  let badge
  if (doc.status === 'processing') {
    badge = <span className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1 rounded-full bg-amber-500/10 text-amber-600"><Loader2 className="w-3 h-3 animate-spin" />Processing</span>
  } else if (doc.status === 'failed') {
    badge = <span title={doc.error || ''} className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1 rounded-full bg-red-500/10 text-red-700"><AlertTriangle className="w-3 h-3" />Failed</span>
  } else if (f.expired) {
    badge = <span className="text-xs font-medium px-3 py-1 rounded-full bg-red-500/10 text-red-700">Expired</span>
  } else if (a === 'approved') {
    badge = <span className="text-xs font-medium px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-600">Approved</span>
  } else if (a === 'retired') {
    badge = <span className="text-xs font-medium px-3 py-1 rounded-full bg-amber-500/10 text-amber-600">Retired</span>
  } else {
    badge = <span className="text-xs font-medium px-3 py-1 rounded-full bg-gray-100 text-gray-600">Draft</span>
  }
  return (
    <div className="flex flex-col items-start gap-1">
      {badge}
      {a === 'approved' && doc.approvedBy && doc.status === 'indexed' && !f.expired && (
        <span className="text-[11px] text-gray-400">by {doc.approvedBy}</span>
      )}
      {doc.supersededBy && <span className="text-[11px] text-gray-500">Replaced by {doc.supersededBy}</span>}
      {doc.governanceNote && a === 'draft' && (
        <span className="text-[11px] text-amber-700 max-w-[200px] truncate" title={doc.governanceNote}>Needs approval again</span>
      )}
      {doc.status === 'failed' && doc.error && (
        <span className="text-[11px] text-red-700 max-w-[180px] truncate" title={doc.error}>{doc.error}</span>
      )}
      {f.expiresSoon && <span className="text-[11px] text-amber-600">Expires in {f.daysLeft} {f.daysLeft === 1 ? 'day' : 'days'}</span>}
      {f.reviewDue && <span className="text-[11px] text-gray-500">Review due</span>}
    </div>
  )
}

function RowMenu({ items }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const close = useCallback(() => setOpen(false), [])
  useClickOutside(ref, close)
  if (!items.length) return null
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More actions"
        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 hover:text-gray-900"
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 w-44 bg-white border border-gray-100 rounded-xl shadow-lg py-1">
          {items.map(({ label, Icon, onClick, danger, disabled }) => (
            <button
              key={label}
              type="button"
              disabled={disabled}
              onClick={() => { setOpen(false); onClick() }}
              className={['w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left disabled:opacity-40 disabled:cursor-not-allowed',
                danger ? 'text-red-700 hover:bg-red-50' : 'text-gray-700 hover:bg-gray-50'].join(' ')}
            >
              <Icon className="w-4 h-4" />{label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function optionsDateError({ effectiveFrom, reviewDate, expiryDate }) {
  if (reviewDate && expiryDate && reviewDate > expiryDate) return 'Review date must not be after the expiry date.'
  if (effectiveFrom && expiryDate && effectiveFrom > expiryDate) return 'Effective date must not be after the expiry date.'
  return ''
}

// More options (diseases, language, regions, dates) shared by upload and edit
function MoreOptions({ values, setValues, diseaseOptions, regionOptions, diseaseNames }) {
  const [open, setOpen] = useState(false)
  const { diseases, language, regions, reviewDate, expiryDate, effectiveFrom } = values
  const audienceClass = values.audienceClass || DEFAULT_AUDIENCE_CLASS
  const subCounties = values.subCounties || []
  const [subCountyList, setSubCountyList] = useState([])
  const [regionRows, setRegionRows] = useState([])
  useEffect(() => {
    if (!open) return
    getSubCounties('').then(setSubCountyList).catch(() => {})
    getRegions().then(setRegionRows).catch(() => {})
  }, [open])
  // sub-counties belong to the region record; the form names regions by display name
  const regionIds = new Set(regionRows.filter((r) => regions.includes(r.region_name || r.name) || regions.includes(r.name)).map((r) => r.name))
  const subCountyOptions = regions.includes(ALL_REGIONS) ? [] : subCountyList
    .filter((s) => regionIds.has(s.region))
    .map((s) => ({ value: s.name, label: `${s.sub_county_name}${s.county ? ` (${s.county})` : ''}` }))
  const sensitivity = values.sensitivity || 'Standard'
  const dateError = optionsDateError(values)
  const summary = [
    AUDIENCE_SHORT[audienceClass] || audienceClass,
    sensitivity === 'Sensitive' ? 'Sensitive' : null,
    language || 'English',
    regions.includes(ALL_REGIONS) ? 'All regions' : regions.join(', '),
    diseases.length ? diseases.map((k) => diseaseNames[k] || k).join(', ') : 'No diseases',
    effectiveFrom ? `From ${formatDate(effectiveFrom)}` : null,
    expiryDate ? `Expires ${formatDate(expiryDate)}` : 'No expiry',
  ].filter(Boolean).join(' · ')

  return (
    <div className="border border-gray-100 rounded-xl">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left">
        <div className="min-w-0">
          <div className="text-sm font-medium text-gray-900">More options <span className="font-normal text-gray-400">(optional)</span></div>
          {!open && <div className="text-xs text-gray-400 truncate mt-0.5">{summary}</div>}
        </div>
        <ChevronDown className={['w-4 h-4 text-gray-400 shrink-0 transition-transform', open ? 'rotate-180' : ''].join(' ')} />
      </button>
      {open && (
        <div className="px-4 pb-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className={LABEL}>Diseases</label>
            <MultiSelectDropdown label="Select diseases" options={diseaseOptions} selected={diseases} onChange={(v) => setValues({ diseases: v })} />
          </div>
          <div>
            <label className={LABEL}>Audience class</label>
            <SelectField value={audienceClass} onChange={(v) => setValues(v === 'Public' ? { audienceClass: v, sensitivity: 'Standard' } : { audienceClass: v })}>
              {AUDIENCE_CLASSES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
            </SelectField>
            <p className="text-xs text-gray-400 mt-1">{AUDIENCE_CLASSES.find((a) => a.value === audienceClass)?.help}</p>
          </div>
          <div>
            <label className={LABEL}>Authority</label>
            <SelectField value={values.authority || 'KRCS protocol'} onChange={(v) => setValues({ authority: v })}>
              {['National guideline', 'KRCS protocol', 'Partner guidance', 'Other'].map((a) => <option key={a} value={a}>{a}</option>)}
            </SelectField>
            <p className="text-xs text-gray-400 mt-1">When documents disagree, higher authority is shown.</p>
          </div>
          <div>
            <label className={LABEL}>Conflicts with</label>
            <input value={values.conflictsWith || ''} onChange={(e) => setValues({ conflictsWith: e.target.value })} placeholder="e.g. KB-00012" className={INPUT} />
            <p className="text-xs text-gray-400 mt-1">Document IDs giving different guidance. Equal authority is passed to a person.</p>
          </div>
          <div>
            <label className={LABEL}>Sensitivity</label>
            <SelectField value={sensitivity} onChange={(v) => setValues({ sensitivity: v })}>
              <option value="Standard">Standard</option>
              {audienceClass !== 'Public' && <option value="Sensitive">Sensitive</option>}
            </SelectField>
            <p className="text-xs text-gray-400 mt-1">Sensitive documents are shown only to users allowed to see sensitive content.</p>
          </div>
          <div>
            <label className={LABEL}>Language</label>
            <SelectField value={language} onChange={(v) => setValues({ language: v })}>
              {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </SelectField>
          </div>
          <div>
            <label className={LABEL}>Regions</label>
            <MultiSelectDropdown label="Select regions" options={regionOptions} selected={regions} onChange={(next) => setValues({ regions: normalizeRegions(regions, next), subCounties: [] })} />
          </div>
          {subCountyOptions.length > 0 && (
            <div className="sm:col-span-2">
              <label className={LABEL}>Sub-counties / camps <span className="font-normal text-gray-400">(optional)</span></label>
              <MultiSelectDropdown label="Whole region" options={subCountyOptions} selected={subCounties} onChange={(v) => setValues({ subCounties: v })} />
              <p className="text-xs text-gray-400 mt-1">Narrow the document to these sub-counties. Regional staff still see it; staff in other sub-counties do not.</p>
            </div>
          )}
          <div>
            <label className={LABEL}>Effective from</label>
            <input type="date" value={effectiveFrom || ''} onChange={(e) => setValues({ effectiveFrom: e.target.value })} className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Review date</label>
            <input type="date" value={reviewDate} onChange={(e) => setValues({ reviewDate: e.target.value })} className={INPUT} />
          </div>
          <div>
            <label className={LABEL}>Expiry date</label>
            <input type="date" value={expiryDate} onChange={(e) => setValues({ expiryDate: e.target.value })} className={INPUT} />
          </div>
          <p className="sm:col-span-2 text-xs text-gray-400 -mt-2">{DATE_HELP}</p>
          {dateError && <p className="sm:col-span-2 text-xs text-red-700 -mt-2">{dateError}</p>}
        </div>
      )}
    </div>
  )
}

const EMPTY_OPTIONS = { diseases: [], language: 'English', regions: [ALL_REGIONS], effectiveFrom: '', reviewDate: '', expiryDate: '', audienceClass: DEFAULT_AUDIENCE_CLASS, sensitivity: 'Standard' }

function UploadDrawer({ open, onClose, roleOptions, diseaseOptions, regionOptions, diseaseNames, onUploaded, supersedes = null }) {
  const [files, setFiles] = useState([])
  const [category, setCategory] = useState(KB_CATEGORIES[0])
  const [applyTo, setApplyTo] = useState([ALL_ROLES])
  const [opts, setOpts] = useState(EMPTY_OPTIONS)
  const [isDragging, setIsDragging] = useState(false)
  const [progress, setProgress] = useState(null)
  const [errors, setErrors] = useState([])
  const fileInputRef = useRef(null)
  const [version, setVersion] = useState('v1.0')
  const versionError = version && !VERSION_RE.test(version.trim()) ? 'Version must look like v1, v1.2 or v1.2.3.' : ''
  const dateError = optionsDateError(opts) || versionError

  // a new version starts from the current version's details; it is a Draft until someone approves it
  useEffect(() => {
    if (!open) return
    if (supersedes) {
      setCategory(supersedes.category || KB_CATEGORIES[0])
      setApplyTo(supersedes.appliedTo?.length ? supersedes.appliedTo : [ALL_ROLES])
      setOpts({
        ...EMPTY_OPTIONS, diseases: supersedes.diseases || [], language: supersedes.language || 'English',
        regions: supersedes.regions?.length ? supersedes.regions : [ALL_REGIONS],
        audienceClass: supersedes.audienceClass || DEFAULT_AUDIENCE_CLASS, sensitivity: supersedes.sensitivity || 'Standard',
      })
      setVersion(nextVersion(supersedes.version))
    } else {
      setVersion('v1.0')
    }
  }, [open, supersedes])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape' && !progress) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, progress, onClose])

  function reset() {
    setFiles([])
    setCategory(KB_CATEGORIES[0])
    setApplyTo([ALL_ROLES])
    setOpts(EMPTY_OPTIONS)
    setErrors([])
  }

  function addFiles(fileList) {
    const list = Array.from(fileList || []).slice(0, supersedes ? 1 : undefined)
    const bad = list.filter((f) => !ACCEPTED.includes((f.name.split('.').pop() || '').toLowerCase()) || f.size > MAX_BYTES)
    setErrors(bad.map((f) => `${f.name}: only PDF, Word, TXT or Markdown up to 25 MB`))
    const ok = list.filter((f) => !bad.includes(f))
    if (ok.length) setFiles((prev) => (supersedes ? ok.slice(0, 1) : [...prev, ...ok]))
  }

  async function upload() {
    if (!files.length || dateError) return
    const failed = []
    let done = 0
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      setProgress({ current: i + 1, total: files.length })
      try {
        const fileUrl = await uploadFile(file, 1)
        const doc = await createKbDocument({
          file_url: fileUrl,
          category,
          applied_to: applyTo.length ? applyTo : [ALL_ROLES],
          diseases: opts.diseases,
          language: opts.language,
          regions: opts.regions,
          effective_from: opts.effectiveFrom,
          audience_class: opts.audienceClass,
          sensitivity: opts.sensitivity,
          version: version.trim(),
          supersedes: supersedes?.id,
          authority: opts.authority,
          conflicts_with: opts.conflictsWith,
          sub_counties: opts.subCounties,
          review_date: opts.reviewDate,
          expiry_date: opts.expiryDate,
        })
        onUploaded(doc)
        done += 1
      } catch (e) {
        failed.push({ file, message: `${file.name}: ${e.message || 'upload failed'}` })
      }
    }
    setProgress(null)
    if (failed.length) {
      setFiles(failed.map((f) => f.file))
      setErrors(failed.map((f) => f.message))
      if (done) onUploaded(null, `${done} document(s) uploaded. ${failed.length} failed.`)
    } else {
      onUploaded(null, `${done} document(s) uploaded. Indexing in progress.`)
      reset()
      onClose()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={() => !progress && onClose()} />
      <div role="dialog" aria-modal="true" aria-label="Upload documents" className="relative w-full max-w-lg h-full bg-white shadow-xl flex flex-col">
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{supersedes ? 'Upload a new version' : 'Upload documents'}</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {supersedes
                ? `Replaces "${supersedes.name}" (${supersedes.version}) once the new version is approved.`
                : 'New documents start as drafts until approved by someone other than the uploader.'}
            </p>
          </div>
          <button onClick={() => !progress && onClose()} aria-label="Close" className="text-gray-400 hover:text-gray-700"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          <section>
            <label className={LABEL} htmlFor="kb-version">Version</label>
            <input id="kb-version" value={version} onChange={(e) => setVersion(e.target.value)} className={INPUT} placeholder="v1.0" />
            {versionError && <p className="text-xs text-red-700 mt-1">{versionError}</p>}
          </section>
          <section>
            <h3 className="text-sm font-semibold text-gray-900 mb-2">1. Choose {supersedes ? 'the new file' : 'files'}</h3>
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => { e.preventDefault(); setIsDragging(false); addFiles(e.dataTransfer.files) }}
              onClick={() => fileInputRef.current?.click()}
              className={['rounded-xl border-2 border-dashed p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors',
                isDragging ? 'border-red-400 bg-red-50/40' : 'border-gray-200 hover:bg-gray-50'].join(' ')}
            >
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
              <UploadCloud className="w-7 h-7 text-gray-400 mb-2" />
              <p className="text-sm text-gray-900">Drag files here or <span className="text-red-700 font-medium">browse</span></p>
              <p className="text-xs text-gray-400 mt-1">PDF, Word, TXT or Markdown, up to 25 MB each</p>
            </div>
            {!!files.length && (
              <ul className="mt-3 divide-y divide-gray-50 border border-gray-100 rounded-xl">
                {files.map((file, i) => (
                  <li key={`${file.name}-${i}`} className="flex items-center gap-3 px-3.5 py-2.5 text-sm">
                    <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="flex-1 truncate text-gray-700">{file.name}</span>
                    <span className="text-xs text-gray-400 shrink-0">{formatBytes(file.size)}</span>
                    <button onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))} disabled={!!progress} aria-label={`Remove ${file.name}`} className="text-gray-400 hover:text-red-700">
                      <X className="w-4 h-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!!errors.length && (
              <ul className="mt-3 bg-red-50 rounded-lg px-4 py-3 space-y-1">
                {errors.map((m) => <li key={m} className="text-xs text-red-700">{m}</li>)}
              </ul>
            )}
          </section>

          {!!files.length && (
            <>
              <section>
                <h3 className="text-sm font-semibold text-gray-900 mb-3">2. Basic details</h3>
                <div className="space-y-4">
                  <div>
                    <label className={LABEL}>Category</label>
                    <SelectField value={category} onChange={setCategory}>
                      {KB_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                    </SelectField>
                  </div>
                  <div>
                    <label className={LABEL}>Who should query from it</label>
                    <MultiSelectDropdown label="Select roles" options={roleOptions} selected={applyTo} onChange={setApplyTo} />
                  </div>
                </div>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-gray-900 mb-3">3. More details</h3>
                <MoreOptions
                  values={opts}
                  setValues={(patch) => setOpts((prev) => ({ ...prev, ...patch }))}
                  diseaseOptions={diseaseOptions}
                  regionOptions={regionOptions}
                  diseaseNames={diseaseNames}
                />
              </section>
            </>
          )}
        </div>

        <div className="border-t border-gray-100 px-6 py-4 flex items-center justify-end gap-3">
          <button onClick={onClose} disabled={!!progress} className="px-5 py-2.5 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">Cancel</button>
          <button
            onClick={upload}
            disabled={!files.length || !!progress || !!dateError}
            className="px-5 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-gray-200 disabled:cursor-not-allowed text-white text-sm font-medium inline-flex items-center gap-2"
          >
            {progress && <Loader2 className="w-4 h-4 animate-spin" />}
            {progress ? `Uploading ${progress.current} of ${progress.total}…` : `Upload ${files.length || ''} document${files.length === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

function EditDocumentModal({ doc, roleOptions, diseaseOptions, regionOptions, diseaseNames, onClose, onSave }) {
  const [category, setCategory] = useState(doc.category)
  const [version, setVersion] = useState(doc.version || 'v1.0')
  const [appliedTo, setAppliedTo] = useState(doc.appliedTo?.length ? doc.appliedTo : [ALL_ROLES])
  const [opts, setOpts] = useState({
    diseases: doc.diseases || [],
    language: doc.language || 'English',
    regions: doc.regions?.length ? doc.regions : [ALL_REGIONS],
    reviewDate: doc.reviewDate ? String(doc.reviewDate).slice(0, 10) : '',
    expiryDate: doc.expiryDate ? String(doc.expiryDate).slice(0, 10) : '',
    effectiveFrom: doc.effectiveFrom ? String(doc.effectiveFrom).slice(0, 10) : '',
    audienceClass: doc.audienceClass || DEFAULT_AUDIENCE_CLASS,
    sensitivity: doc.sensitivity || 'Standard',
    authority: doc.authority || 'KRCS protocol',
    conflictsWith: (doc.conflictsWith || []).join(', '),
    subCounties: doc.subCounties || [],
  })
  const [saving, setSaving] = useState(false)
  const dateError = !!optionsDateError(opts)

  async function submit() {
    if (dateError) return
    setSaving(true)
    await onSave({
      category, version, applied_to: appliedTo.length ? appliedTo : [ALL_ROLES], diseases: opts.diseases,
      language: opts.language, regions: opts.regions, review_date: opts.reviewDate, expiry_date: opts.expiryDate,
      effective_from: opts.effectiveFrom, audience_class: opts.audienceClass, sensitivity: opts.sensitivity,
      authority: opts.authority, conflicts_with: opts.conflictsWith, sub_counties: opts.subCounties,
    })
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="bg-white rounded-2xl border border-gray-100 w-full max-w-lg max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-6 pb-3">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-gray-900">Edit document</h3>
            <p className="text-sm text-gray-500 truncate">{doc.name}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-700"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 pb-2 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2">
              <label className={LABEL}>Category</label>
              <SelectField value={category} onChange={setCategory}>
                {KB_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </SelectField>
            </div>
            <div>
              <label className={LABEL}>Version</label>
              <input value={version} onChange={(e) => setVersion(e.target.value)} className={INPUT} />
            </div>
          </div>
          <div>
            <label className={LABEL}>Who should see it</label>
            <MultiSelectDropdown label="Select roles" options={roleOptions} selected={appliedTo} onChange={setAppliedTo} />
          </div>
          <MoreOptions
            values={opts}
            setValues={(patch) => setOpts((prev) => ({ ...prev, ...patch }))}
            diseaseOptions={diseaseOptions}
            regionOptions={regionOptions}
            diseaseNames={diseaseNames}
          />
          <p className="text-xs text-gray-400">All changes apply to search immediately.</p>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose} className="px-5 py-2.5 rounded-lg border border-gray-200 text-gray-700 text-sm hover:bg-gray-50">Cancel</button>
          <button onClick={submit} disabled={saving || !!dateError} className="px-5 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-gray-200 text-white text-sm font-medium">
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FiltersPopover({ filters, setFilters, roleOptions, regionOptions }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const close = useCallback(() => setOpen(false), [])
  useClickOutside(ref, close)
  const active = Object.values(filters).filter(Boolean).length
  const set = (k) => (v) => setFilters((prev) => ({ ...prev, [k]: v }))
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 border border-gray-200 rounded-lg px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        <SlidersHorizontal className="w-4 h-4" /> Filters
        {!!active && <span className="text-[11px] min-w-5 h-5 px-1.5 rounded-full bg-red-600 text-white flex items-center justify-center">{active}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 bg-white border border-gray-100 rounded-xl shadow-lg p-4 space-y-3">
          <div>
            <label className={LABEL}>Category</label>
            <SelectField value={filters.category} onChange={set('category')}>
              <option value="">Any</option>
              {KB_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </SelectField>
          </div>
          <div>
            <label className={LABEL}>Who can see it</label>
            <SelectField value={filters.role} onChange={set('role')}>
              <option value="">Any</option>
              {roleOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </SelectField>
          </div>
          <div>
            <label className={LABEL}>Language</label>
            <SelectField value={filters.language} onChange={set('language')}>
              <option value="">Any</option>
              {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </SelectField>
          </div>
          <div>
            <label className={LABEL}>Region</label>
            <SelectField value={filters.region} onChange={set('region')}>
              <option value="">Any</option>
              {regionOptions.filter((r) => r !== ALL_REGIONS).map((r) => <option key={r} value={r}>{r}</option>)}
            </SelectField>
          </div>
          <div>
            <label className={LABEL}>Indexing</label>
            <SelectField value={filters.indexing} onChange={set('indexing')}>
              <option value="">Any</option>
              <option value="indexed">Indexed</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
            </SelectField>
          </div>
          <div className="flex justify-between pt-1">
            <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="text-sm text-red-700 hover:underline">Clear all</button>
            <button type="button" onClick={close} className="text-sm font-medium text-gray-700 hover:underline">Done</button>
          </div>
        </div>
      )}
    </div>
  )
}

const EMPTY_FILTERS = { category: '', role: '', language: '', region: '', indexing: '' }

function TestSearch() {
  const [query, setQuery] = useState('')
  const [drafts, setDrafts] = useState(true)
  const [viewAs, setViewAs] = useState('all')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})

  async function run(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setExpanded({})
    try {
      const res = await searchKnowledgeBase({ query: query.trim(), limit: 5, includeDrafts: drafts && viewAs !== 'me', preview: viewAs === 'all', audience: viewAs === 'public' ? 'Public' : undefined })
      setResults(Array.isArray(res) ? res : res?.results || [])
    } catch (err) {
      setError(err.message || 'Search failed')
      setResults(null)
    }
    setLoading(false)
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6">
      <p className="text-sm text-gray-500 mb-4">Check that documents answer the questions people will ask, before approving them.</p>
      <form onSubmit={run} className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. What is the case definition for cholera?" className={`${INPUT} pl-10`} />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} className="accent-red-600" />
          Include drafts
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          View as
          <select value={viewAs} onChange={(e) => setViewAs(e.target.value)} className="border border-gray-200 rounded-lg px-2 py-2 text-sm bg-white" aria-label="View as">
            <option value="all">All audiences</option>
            <option value="public">A community member (Public)</option>
            <option value="me">Myself</option>
          </select>
        </label>
        <button type="submit" disabled={loading || !query.trim()} className="px-5 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-gray-200 text-white text-sm font-medium inline-flex items-center gap-2">
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}{loading ? 'Searching…' : 'Search'}
        </button>
      </form>
      {error && <p className="mt-4 bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3">{error}</p>}
      {results && !results.length && <p className="mt-6 text-sm text-gray-400 text-center">No matching passages.</p>}
      {!!results?.length && (
        <ul className="mt-5 space-y-3">
          {results.map((r, i) => {
            const key = r.id || i
            const text = String(r.text || '')
            const long = text.length > 300
            const approval = String(r.approval_status || '').toLowerCase()
            return (
              <li key={key} className="border border-gray-100 rounded-xl p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">{r.title}</span>
                  {r.section && <span className="text-xs text-gray-500">· {r.section}{r.page ? `, page ${r.page}` : ''}</span>}
                  {r.confidence && <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${CONFIDENCE_STYLES[r.confidence] || CONFIDENCE_STYLES.low}`}>{r.confidence} match</span>}
                  {typeof r.score === 'number' && <span className="text-[11px] text-gray-400" title="How closely this passage matches the question">{Math.round(r.score * 100)}%</span>}
                  {approval && approval !== 'approved' && <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 capitalize">{approval}</span>}
                  {r.audience_class && <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">{AUDIENCE_SHORT[r.audience_class] || r.audience_class}</span>}
                  {r.sensitive && <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">Sensitive</span>}
                </div>
                <p className="text-sm text-gray-600 mt-2 whitespace-pre-wrap">{expanded[key] || !long ? text : `${text.slice(0, 300)}…`}</p>
                {long && (
                  <button type="button" onClick={() => setExpanded((p) => ({ ...p, [key]: !p[key] }))} className="text-xs font-medium text-red-700 mt-1 hover:underline">
                    {expanded[key] ? 'Show less' : 'Show more'}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function HealthPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    setError('')
    try { setData(await getKbHealth()) } catch (e) { setError(e.message || 'Could not load health') }
  }
  useEffect(() => { load() }, [])

  async function reconcile() {
    setBusy(true)
    try { await runKbReconcile(); await load() } catch (e) { setError(e.message || 'Reconcile failed') }
    setBusy(false)
  }

  if (error) return <p className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3">{error}</p>
  if (!data) return <p className="text-sm text-gray-400">Loading…</p>
  const q = data.qdrant || {}
  const rec = data.last_reconcile
  const row = (label, value, ok = true) => (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm text-right ${ok ? 'text-gray-900' : 'text-red-700 font-medium'}`}>{value}</span>
    </div>
  )
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {!!data.warnings?.length && (
        <div className="lg:col-span-2 bg-amber-50 border border-amber-100 rounded-2xl p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-800 mb-1"><AlertTriangle className="w-4 h-4" /> Needs attention</div>
          <ul className="list-disc pl-5 text-sm text-amber-800 space-y-0.5">{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      <div className="bg-white rounded-2xl border border-gray-100 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Search index</h3>
        {row('Qdrant', q.reachable ? 'Reachable' : `Unreachable: ${q.error || ''}`, q.reachable)}
        {row('Collection', `${q.collection || '-'} · ${q.points ?? 0} passages`)}
        {row('API key / TLS', `${q.api_key ? 'Key set' : 'No key'} · ${q.tls ? 'TLS' : 'No TLS'}`, q.api_key)}
        {row('Last reconciliation', rec ? `${rec.at?.slice(0, 16)} · ${rec.checked} checked, ${rec.missing?.length || 0} missing, ${rec.orphans?.length || 0} orphans` : 'Not run yet')}
        <button type="button" onClick={reconcile} disabled={busy} className="mt-3 text-xs font-medium border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50">
          {busy ? 'Checking…' : 'Check index now'}
        </button>
      </div>
      <div className="bg-white rounded-2xl border border-gray-100 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Models and licences</h3>
        {Object.entries(data.models || {}).map(([k, m]) => row(k, `${m.model} · ${m.licence}`, m.approved_for_use))}
        {row('Answer model', data.llm?.reachable ? (data.llm.pulled ? 'Ready' : 'Not downloaded') : 'Unreachable', !!data.llm?.reachable)}
        {row('Retrieval config', <code className="text-xs">{data.retrieval_config}</code>)}
        {row('Access policy', data.access_policy)}
      </div>
      <div className="bg-white rounded-2xl border border-gray-100 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Documents</h3>
        {Object.entries(data.documents || {}).map(([k, v]) => row(k, v, !(k === 'failed' && v > 0)))}
      </div>
      <div className="bg-white rounded-2xl border border-gray-100 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Chatbot service</h3>
        {row('Last protocol reload', data.chatbot_last_reload ? `${data.chatbot_last_reload.at?.slice(0, 16)} · HTTP ${data.chatbot_last_reload.status ?? 'error'}` : 'None yet', !data.chatbot_last_reload || data.chatbot_last_reload.status === 200)}
      </div>
    </div>
  )
}

// ---------- page ----------

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [roles, setRoles] = useState([])
  const [diseaseOptions, setDiseaseOptions] = useState([])
  const [regionList, setRegionList] = useState([])
  const [uploadOpen, setUploadOpen] = useState(false)
  const [newVersionOf, setNewVersionOf] = useState(null)
  const [editingDoc, setEditingDoc] = useState(null)
  const [tab, setTab] = useState('documents')
  const [search, setSearch] = useState('')
  const [quick, setQuick] = useState('all')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [toast, setToast] = useState({ show: false, message: '', error: false })
  const toastTimer = useRef(null)

  const { has } = useCapabilities()
  const canManage = has('manage_knowledge_base')
  const canApprove = has('approve_knowledge_base')

  const showToast = useCallback((message, error = false) => {
    setToast({ show: true, message, error })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, show: false })), 3500)
  }, [])
  useEffect(() => () => clearTimeout(toastTimer.current), [])

  const roleOptions = useMemo(
    () => [ALL_ROLES, ...roles.map((r) => (typeof r === 'string' ? r : r.name)).filter((n) => n && n !== ALL_ROLES)],
    [roles]
  )
  const regionOptions = useMemo(
    () => [ALL_REGIONS, ...regionList.map((r) => (typeof r === 'string' ? r : r.region_name || r.name)).filter((n) => n && n !== ALL_REGIONS)],
    [regionList]
  )
  const diseaseSelectOptions = useMemo(() => diseaseOptions.map((d) => ({ value: d.key, label: d.name })), [diseaseOptions])
  const diseaseNames = useMemo(() => Object.fromEntries(diseaseOptions.map((d) => [d.key, d.name])), [diseaseOptions])

  const loadDocuments = useCallback(async () => {
    try {
      setDocuments(await getKbDocuments())
      setLoadError('')
    } catch (e) {
      setLoadError(e.message || 'Could not load documents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
    getRoles().then(setRoles).catch(() => {})
    getDiseaseOptions().then(setDiseaseOptions).catch(() => {})
    getRegions().then(setRegionList).catch(() => {})
  }, [loadDocuments])

  // While anything is processing, refresh every 3 seconds
  const anyProcessing = documents.some((d) => d.status === 'processing')
  useEffect(() => {
    if (!anyProcessing) return
    const t = setInterval(loadDocuments, 3000)
    return () => clearInterval(t)
  }, [anyProcessing, loadDocuments])

  const stats = useMemo(() => {
    const totalSize = documents.reduce((sum, d) => sum + (d.sizeBytes || 0), 0)
    const indexedDocs = documents.filter((d) => d.status === 'indexed')
    return {
      total: documents.length,
      categories: new Set(documents.map((d) => d.category)).size,
      processing: documents.filter((d) => d.status === 'processing').length,
      ready: indexedDocs.length,
      approved: indexedDocs.filter((d) => approvalKey(d) === 'approved' && !dateFlags(d).expired).length,
      sizeLabel: formatBytes(totalSize),
      sizePct: Math.min(100, Math.round((totalSize / KB_WORKSPACE_LIMIT_BYTES) * 100)),
    }
  }, [documents])

  const quickCounts = useMemo(() => ({
    all: documents.length,
    draft: documents.filter((d) => approvalKey(d) === 'draft').length,
    approved: documents.filter((d) => approvalKey(d) === 'approved').length,
    attention: documents.filter(needsAttention).length,
  }), [documents])

  const filteredDocuments = useMemo(() => {
    const q = search.trim().toLowerCase()
    return documents.filter((d) => {
      if (quick === 'draft' && approvalKey(d) !== 'draft') return false
      if (quick === 'approved' && approvalKey(d) !== 'approved') return false
      if (quick === 'attention' && !needsAttention(d)) return false
      if (q && !`${d.name} ${d.category} ${(d.diseases || []).map((k) => diseaseNames[k] || k).join(' ')}`.toLowerCase().includes(q)) return false
      if (filters.category && d.category !== filters.category) return false
      if (filters.role && !(d.appliedTo || []).includes(filters.role)) return false
      if (filters.indexing && d.status !== filters.indexing) return false
      if (filters.language && (d.language || 'English') !== filters.language) return false
      if (filters.region) {
        const r = d.regions || []
        if (r.length && !r.includes(ALL_REGIONS) && !r.includes(filters.region)) return false
      }
      return true
    })
  }, [documents, search, quick, filters, diseaseNames])

  function handleUploaded(doc, message) {
    if (doc) setDocuments((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)])
    if (message) showToast(message)
  }

  async function reindexDocument(id) {
    try {
      const doc = await reindexKbDocument(id)
      setDocuments((prev) => prev.map((d) => (d.id === id ? doc : d)))
      showToast('Re-indexing started')
    } catch (e) {
      showToast(e.message || 'Could not reindex', true)
    }
  }

  async function changeApproval(doc, status, message) {
    try {
      const updated = await setKbApproval(doc.id, status)
      const retired = new Set(updated.retiredVersions || [])
      setDocuments((prev) => prev.map((d) => (d.id === doc.id ? updated
        : retired.has(d.id) ? { ...d, approvalStatus: 'retired', supersededBy: doc.id } : d)))
      showToast(retired.size ? `${message}. The previous version was retired.` : message)
    } catch (e) {
      showToast(e.message || 'Could not update approval', true)
    }
  }

  async function saveEdit(values) {
    try {
      const wasApproved = approvalKey(editingDoc) === 'approved'
      const updated = await updateKbDocument(editingDoc.id, values)
      setDocuments((prev) => prev.map((d) => (d.id === editingDoc.id ? updated : d)))
      setEditingDoc(null)
      showToast(wasApproved && updated.approvalStatus === 'draft'
        ? 'Document updated. It is back in draft and hidden from search until approved again.'
        : 'Document updated')
    } catch (e) {
      showToast(e.message || 'Could not update document', true)
    }
  }

  async function deleteDocument(doc) {
    const kept = doc.approvedAt
    if (!window.confirm(kept
      ? `"${doc.name}" has been approved, so it is kept for audit. It will be retired and stop being used. Continue?`
      : `Delete "${doc.name}"? It will be removed from the knowledge base and cannot be undone.`)) return
    try {
      const res = await deleteKbDocument(doc.id)
      if (res?.retired) {
        setDocuments((prev) => prev.map((d) => (d.id === doc.id ? res.document : d)))
        showToast('Document retired. It was used for answers, so it is kept for audit.')
      } else {
        setDocuments((prev) => prev.filter((d) => d.id !== doc.id))
        showToast('Document deleted')
      }
    } catch (e) {
      showToast(e.message || 'Could not delete', true)
    }
  }

  function retireDocument(doc) {
    if (!window.confirm('Retire this document? It will stop being used by the assistant and chatbot.')) return
    changeApproval(doc, 'Retired', 'Document retired')
  }

  function menuItems(doc) {
    const a = approvalKey(doc)
    const items = []
    if (canManage) items.push({ label: 'Edit', Icon: Pencil, onClick: () => setEditingDoc(doc) })
    if (canManage && a !== 'retired') items.push({ label: 'Upload new version', Icon: CopyPlus, onClick: () => { setNewVersionOf(doc); setUploadOpen(true) } })
    if (canApprove && a === 'approved') items.push({ label: 'Retire', Icon: Ban, onClick: () => retireDocument(doc) })
    if (canApprove && a !== 'draft') items.push({ label: 'Back to draft', Icon: Undo2, onClick: () => changeApproval(doc, 'Draft', 'Moved back to draft') })
    if (canManage) items.push({ label: 'Re-index', Icon: RotateCcw, onClick: () => reindexDocument(doc.id), disabled: doc.status === 'processing' })
    if (canManage) items.push({ label: 'Delete', Icon: Trash2, onClick: () => deleteDocument(doc), danger: true })
    return items
  }

  const QUICK = [
    { key: 'all', label: 'All' },
    { key: 'draft', label: 'Drafts' },
    { key: 'approved', label: 'Approved' },
    { key: 'attention', label: 'Needs attention' },
  ]
  const hasFilters = search || quick !== 'all' || Object.values(filters).some(Boolean)

  return (
    <AppShell>
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="text-xl font-semibold text-brand-navy">Knowledge Base</h1>
          <p className="text-sm text-gray-400 mt-1">Approved KRCS documents that the AI assistant and chatbot quote from.</p>
        </div>
        {canManage && (
          <button
            onClick={() => setUploadOpen(true)}
            className="inline-flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium"
          >
            <UploadCloud className="w-4 h-4" /> Upload documents
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard icon={FileText} label="Total Documents" value={stats.total} sub={`${stats.categories} categories`} />
        <StatCard icon={Clock} label="Processing" value={stats.processing} sub="in the indexing queue" />
        <StatCard icon={ShieldCheck} label="Ready to search" value={stats.ready} sub={`${stats.approved} approved`} />
        <StatCard icon={Database} label="Knowledge Size" value={stats.sizeLabel} sub={`${stats.sizePct}% of 2 GB workspace`} />
      </div>

      {canManage && (
        <div className="flex gap-6 border-b border-gray-100 mb-5">
          {[{ key: 'documents', label: 'Documents' }, { key: 'test', label: 'Test search' }, { key: 'health', label: 'Health' }].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={['pb-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                tab === t.key ? 'border-red-600 text-red-700' : 'border-transparent text-gray-500 hover:text-gray-900'].join(' ')}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {tab === 'health' && canManage ? (
        <HealthPanel />
      ) : tab === 'test' && canManage ? (
        <TestSearch />
      ) : (
        <>
          <div className="flex items-center gap-3 flex-wrap mb-4">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                type="text"
                placeholder="Search by name, category or disease…"
                className={`${INPUT} pl-10 bg-white`}
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              {QUICK.map((q) => (
                <button
                  key={q.key}
                  onClick={() => setQuick(q.key)}
                  className={['inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm border transition-colors',
                    quick === q.key ? 'border-red-600 bg-red-50 text-red-700' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'].join(' ')}
                >
                  {q.key === 'attention' && quickCounts.attention > 0 && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                  {q.label}
                  <span className="text-xs text-gray-400">{quickCounts[q.key]}</span>
                </button>
              ))}
            </div>
            <FiltersPopover filters={filters} setFilters={setFilters} roleOptions={roleOptions} regionOptions={regionOptions} />
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            {loading ? (
              <div className="divide-y divide-gray-50 animate-pulse">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="px-6 py-5 flex gap-4">
                    <div className="w-5 h-5 bg-gray-100 rounded" />
                    <div className="flex-1 space-y-2"><div className="h-3 w-1/3 bg-gray-100 rounded" /><div className="h-3 w-1/2 bg-gray-100 rounded" /></div>
                  </div>
                ))}
              </div>
            ) : loadError ? (
              <div className="py-16 text-center">
                <p className="text-sm text-red-700 mb-3">{loadError}</p>
                <button onClick={loadDocuments} className="text-sm font-medium text-red-700 hover:underline">Try again</button>
              </div>
            ) : !documents.length ? (
              <div className="py-16 px-6 text-center flex flex-col items-center">
                <span className="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center mb-4"><FileText className="w-6 h-6 text-gray-400" /></span>
                <p className="text-base font-medium text-gray-900">No documents yet</p>
                <p className="text-sm text-gray-400 mt-1 max-w-sm">Upload KRCS protocols and guidelines so the assistant can answer from them.</p>
                {canManage && (
                  <button onClick={() => setUploadOpen(true)} className="mt-5 inline-flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium">
                    <UploadCloud className="w-4 h-4" /> Upload documents
                  </button>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[760px]">
                  <thead>
                    <tr className="text-left text-gray-500 text-xs bg-gray-50 border-b border-gray-100">
                      <th className="px-6 py-3 font-medium">Document</th>
                      <th className="px-6 py-3 font-medium">Audience</th>
                      <th className="px-6 py-3 font-medium">Status</th>
                      <th className="px-6 py-3 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDocuments.map((doc) => {
                      const a = approvalKey(doc)
                      const showApprove = canApprove && a !== 'approved'
                      return (
                        <tr key={doc.id} className="border-b border-gray-50 hover:bg-gray-50/60 align-top">
                          <td className="px-6 py-4">
                            <div className="flex items-start gap-3">
                              <FileText className="w-5 h-5 text-gray-400 mt-0.5 shrink-0" />
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-900 font-medium truncate max-w-[300px]" title={doc.name}>{doc.name}</span>
                                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 shrink-0">{langShort(doc.language)}</span>
                                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 ${doc.audienceClass === 'Public' ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-700'}`} title="Audience class">{AUDIENCE_SHORT[doc.audienceClass] || 'CHW'}</span>
                                  {doc.sensitivity === 'Sensitive' && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 shrink-0">Sensitive</span>}
                                </div>
                                <div className="text-xs text-gray-400 mt-0.5">
                                  {doc.category} · {doc.version} · {doc.extension} · {formatBytes(doc.sizeBytes)}
                                </div>
                                <div className="text-xs text-gray-400">
                                  {doc.uploadedBy} · {formatDate(doc.uploadedAt)}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <div className="text-xs text-gray-700">{(doc.appliedTo || [ALL_ROLES]).join(', ')}</div>
                            <ChipList items={(doc.regions || []).filter((r) => r !== ALL_REGIONS)} className="bg-sky-50 text-sky-600" />
                            <ChipList items={doc.diseases} className="bg-gray-100 text-gray-600" labelFor={(k) => diseaseNames[k] || k} />
                          </td>
                          <td className="px-6 py-4"><StatusBadge doc={doc} /></td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-end gap-2">
                              {showApprove && (
                                <button
                                  onClick={() => changeApproval(doc, 'Approved', 'Document approved')}
                                  disabled={doc.status !== 'indexed' || doc.selfApprovalBlocked}
                                  title={doc.selfApprovalBlocked ? 'You uploaded this document, so someone else must approve it' : doc.status !== 'indexed' ? 'Available once indexing completes' : 'Approve for search'}
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 text-emerald-700 px-3 py-1.5 text-xs font-medium hover:bg-emerald-50 disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                  <Check className="w-3.5 h-3.5" /> Approve
                                </button>
                              )}
                              <RowMenu items={menuItems(doc)} />
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {!filteredDocuments.length && (
                      <tr>
                        <td colSpan={4} className="px-6 py-12 text-center text-gray-400">
                          No documents match your filters.
                          {hasFilters && (
                            <button
                              onClick={() => { setSearch(''); setQuick('all'); setFilters(EMPTY_FILTERS) }}
                              className="ml-2 text-red-700 font-medium hover:underline"
                            >
                              Clear filters
                            </button>
                          )}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <UploadDrawer
        open={uploadOpen}
        onClose={() => { setUploadOpen(false); setNewVersionOf(null) }}
        supersedes={newVersionOf}
        roleOptions={roleOptions}
        diseaseOptions={diseaseSelectOptions}
        regionOptions={regionOptions}
        diseaseNames={diseaseNames}
        onUploaded={handleUploaded}
      />

      {editingDoc && (
        <EditDocumentModal
          doc={editingDoc}
          roleOptions={roleOptions}
          diseaseOptions={diseaseSelectOptions}
          regionOptions={regionOptions}
          diseaseNames={diseaseNames}
          onClose={() => setEditingDoc(null)}
          onSave={saveEdit}
        />
      )}

      {toast.show && (
        <div role="status" className={['fixed bottom-6 right-6 z-50 rounded-xl px-5 py-3 text-sm text-white shadow-lg', toast.error ? 'bg-red-600' : 'bg-gray-900'].join(' ')}>
          {toast.message}
        </div>
      )}
    </AppShell>
  )
}