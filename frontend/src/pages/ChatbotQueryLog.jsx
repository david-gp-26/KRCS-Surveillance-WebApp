import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import { CARD, INPUT, TEXTAREA, BTN_PRIMARY, BTN_SECONDARY, BTN_SMALL, Badge, Toast, PageTitle, shortWhen } from '../components/chp/ui'
import { getChatbotLog, getChatbotMetrics, listChatbotLogs, updateChatbotEscalation } from '../api/frappe'
import { useCapabilities } from '../context/CapabilitiesContext'

const OUTCOME_TONE = {
  Matched: 'softGreen', 'No Match': 'softAmber', Restricted: 'red', Escalated: 'amber', Conflict: 'amber',
  Clarify: 'gray', Routed: 'gray', Info: 'gray', Error: 'red',
}
const ESC_TONE = { Open: 'red', 'In Progress': 'amber', Answered: 'green', Closed: 'gray' }
const OUTCOMES = ['Matched', 'No Match', 'Restricted', 'Escalated', 'Conflict', 'Clarify', 'Routed', 'Info', 'Error']
const CHANNELS = ['Web', 'Mobile', 'WhatsApp', 'SMS', 'USSD', 'API']
const today = () => new Date().toISOString().slice(0, 10)
const daysAgo = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10)

function Metric({ label, value, target, good, hint }) {
  const met = value == null || good == null ? null : good(value)
  return (
    <div className={`${CARD} px-4 py-3`}>
      <span className="block text-xs text-gray-500">{label}</span>
      <span className={`block text-xl font-semibold tabular-nums ${met === false ? 'text-red-600' : 'text-gray-900'}`}>
        {value == null ? '–' : value}
      </span>
      {(target || hint) && <span className="block text-xs text-gray-400 mt-0.5">{target ? `Target ${target}` : hint}</span>}
    </div>
  )
}

function Detail({ id, onClose, canHandle, onChanged }) {
  const [d, setD] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { getChatbotLog(id).then((r) => { setD(r); setNote(r.responseNote || '') }).catch((e) => setErr(e.message)) }, [id])
  async function move(status) {
    setBusy(true); setErr('')
    try { const r = await updateChatbotEscalation(id, status, note); setD({ ...d, ...r }); onChanged() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div role="dialog" aria-modal="true" aria-label="Query details" className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="w-full max-w-xl h-full overflow-y-auto bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Query {id}</h2>
          <button type="button" className={BTN_SMALL} onClick={onClose}>Close</button>
        </div>
        {err && <p className="text-sm text-red-600 mb-3">{err}</p>}
        {!d ? <p className="text-sm text-gray-400">Loading…</p> : (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge tone={OUTCOME_TONE[d.outcome]}>{d.outcome}</Badge>
              <Badge tone={d.accessDecision === 'DENY' ? 'red' : 'softGreen'}>{d.accessDecision || '—'}</Badge>
              {d.escalationStatus && <Badge tone={ESC_TONE[d.escalationStatus]}>{d.escalationStatus}</Badge>}
              {d.preview ? <Badge tone="amber">Editor preview</Badge> : null}
            </div>
            <dl className="grid grid-cols-3 gap-x-3 gap-y-1.5">
              {[
                ['When', shortWhen(d.createdAt)], ['Channel', d.channel], ['Level', d.level], ['Route', d.route],
                ['User', d.userName || d.user || d.userRef], ['Actor class', d.actorClass], ['Audience', d.audience],
                ['Scope', d.scope], ['Language', d.language], ['Reason', d.reason], ['Deny reason', d.denyReason],
                ['Confidence', d.confidence != null ? `${d.confidence} (${d.band || '—'})` : null],
                ['Document', d.matchedDocument], ['Protocol', d.matchedProtocol], ['Content version', d.contentVersion],
                ['Policy', d.policyVersion], ['Retrieval config', d.retrievalConfig], ['Latency', d.latencyMs != null ? `${d.latencyMs} ms` : null],
                ['Escalated to', d.escalatedTo], ['Helpful', d.helpful], ['Correlation', d.correlationId],
              ].filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-gray-500">{k}</dt><dd className="col-span-2 text-gray-900 break-words">{v}</dd></div>
              ))}
            </dl>
            <div><h3 className="font-medium text-gray-900 mb-1">Question</h3><p className="whitespace-pre-wrap text-gray-700">{d.question}</p></div>
            {d.answer && <div><h3 className="font-medium text-gray-900 mb-1">Reply shown</h3><p className="whitespace-pre-wrap text-gray-700">{d.answer}</p></div>}
            {d.error && <div><h3 className="font-medium text-gray-900 mb-1">Error</h3><p className="text-red-600">{d.error}</p></div>}
            {d.feedbackComment && <div><h3 className="font-medium text-gray-900 mb-1">Feedback</h3><p className="text-gray-700">{d.feedbackComment}</p></div>}
            {!!d.passages?.length && (
              <div>
                <h3 className="font-medium text-gray-900 mb-1">Passages considered</h3>
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-gray-500"><th className="py-1">Document</th><th>Section</th><th>Score</th><th>Shown</th></tr></thead>
                  <tbody>{d.passages.map((p, i) => (
                    <tr key={p.id || i} className="border-t border-gray-100"><td className="py-1">{p.doc || p.title}{p.version ? ` ${p.version}` : ''}</td><td>{p.section}</td><td className="tabular-nums">{p.score ?? '—'}</td><td>{p.shown ? 'yes' : ''}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {!!d.related?.length && (
              <div>
                <h3 className="font-medium text-gray-900 mb-1">Linked records</h3>
                <ul className="text-xs text-gray-600 space-y-0.5">{d.related.map((r) => <li key={r.id}>{r.id} · {r.level} · {r.route} · {r.outcome} · {r.accessDecision}</li>)}</ul>
              </div>
            )}
            {canHandle && d.escalated ? (
              <div className="border-t border-gray-100 pt-4">
                <h3 className="font-medium text-gray-900 mb-2">Follow-up</h3>
                <label className="block text-xs text-gray-500 mb-1" htmlFor="esc-note">Response note</label>
                <textarea id="esc-note" rows={3} className={TEXTAREA} value={note} onChange={(e) => setNote(e.target.value)} />
                <div className="flex flex-wrap gap-2 mt-2">
                  {['In Progress', 'Answered', 'Closed'].map((s) => (
                    <button key={s} type="button" disabled={busy || d.escalationStatus === s} className={s === 'Answered' ? BTN_PRIMARY : BTN_SECONDARY} onClick={() => move(s)}>Mark {s.toLowerCase()}</button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatbotQueryLog() {
  const { has } = useCapabilities()
  const [from, setFrom] = useState(daysAgo(30))
  const [to, setTo] = useState(today())
  const [channel, setChannel] = useState('')
  const [level, setLevel] = useState('Conversation')
  const [outcome, setOutcome] = useState('')
  const [esc, setEsc] = useState('')
  const [rows, setRows] = useState(null)
  const [m, setM] = useState(null)
  const [open, setOpen] = useState(null)
  const [toast, setToast] = useState({ text: '' })

  const load = useCallback(() => {
    listChatbotLogs({ from_date: from, to_date: to, channel, level, outcome, escalation_status: esc })
      .then(setRows).catch((e) => setToast({ text: e.message, error: true }))
    getChatbotMetrics({ from_date: from, to_date: to, channel }).then(setM).catch(() => {})
  }, [from, to, channel, level, outcome, esc])
  useEffect(() => { load() }, [load])

  return (
    <AppShell>
      <div className="p-6 max-w-7xl mx-auto">
        <PageTitle title="Chatbot Query Log" subtitle="Every question to the Knowledge Base and the Response Support Chatbot, with what was shown, why, and who could see it. Acceptance metrics follow SRS Table 18 and Table 25." />
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-5">
          <Metric label="Guidance questions" value={m?.guidance_questions} hint={`${m?.questions ?? '–'} records`} />
          <Metric label="Match rate" value={m?.match_rate != null ? `${m.match_rate}%` : null} target="≥ 75%" good={() => m.match_rate >= 75} />
          <Metric label="Escalation rate" value={m?.escalation_rate != null ? `${m.escalation_rate}%` : null} target="≤ 25%" good={() => m.escalation_rate <= 25} />
          <Metric label="Restricted to public" value={m?.public_restricted_leaks} target="0" good={(v) => v === 0} />
          <Metric label="Denied requests" value={m?.denied} hint="access decision DENY" />
          <Metric label="Open escalations" value={m?.open_escalations} hint="Open or in progress" />
          <Metric label="p95 latency" value={m?.p95_latency_ms != null ? `${m.p95_latency_ms} ms` : null} hint={m?.helpful_rate != null ? `${m.helpful_rate}% found it helpful` : 'no feedback yet'} />
        </div>

        <div className="flex flex-wrap gap-3 mb-4 items-end">
          <label className="text-xs text-gray-500">From<input type="date" className={`${INPUT} mt-1`} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="text-xs text-gray-500">To<input type="date" className={`${INPUT} mt-1`} value={to} onChange={(e) => setTo(e.target.value)} /></label>
          <label className="text-xs text-gray-500">Channel<select className={`${INPUT} mt-1`} value={channel} onChange={(e) => setChannel(e.target.value)}><option value="">All</option>{CHANNELS.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="text-xs text-gray-500">Level<select className={`${INPUT} mt-1`} value={level} onChange={(e) => setLevel(e.target.value)}><option value="">All</option><option>Conversation</option><option>Retrieval</option></select></label>
          <label className="text-xs text-gray-500">Outcome<select className={`${INPUT} mt-1`} value={outcome} onChange={(e) => setOutcome(e.target.value)}><option value="">All</option>{OUTCOMES.map((o) => <option key={o}>{o}</option>)}</select></label>
          <label className="text-xs text-gray-500">Escalation<select className={`${INPUT} mt-1`} value={esc} onChange={(e) => setEsc(e.target.value)}><option value="">All</option>{['Open', 'In Progress', 'Answered', 'Closed'].map((o) => <option key={o}>{o}</option>)}</select></label>
          <button type="button" className={BTN_SECONDARY} onClick={load}>Refresh</button>
        </div>

        <section className={CARD}>
          {!rows ? <p className="p-8 text-sm text-gray-400">Loading…</p> : !rows.length ? <p className="p-10 text-center text-sm text-gray-400">No questions in this period.</p> : (
            <div className="relative overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <tr><th className="px-4 py-2">When</th><th className="px-2">Channel</th><th className="px-2">Who</th><th className="px-2">Question</th><th className="px-2">Outcome</th><th className="px-2">Access</th><th className="px-2">Escalation</th><th className="px-2"><span className="sr-only">Open</span></th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b border-gray-50 align-top">
                      <td className="px-4 py-2 whitespace-nowrap text-gray-500">{shortWhen(r.createdAt)}</td>
                      <td className="px-2 py-2">{r.channel}<span className="block text-xs text-gray-400">{r.level}</span></td>
                      <td className="px-2 py-2">{r.userName || r.userRef || r.user || '—'}<span className="block text-xs text-gray-400">{r.actorClass || r.audience}</span></td>
                      <td className="px-2 py-2 max-w-md"><span className="line-clamp-2">{r.question}</span></td>
                      <td className="px-2 py-2"><Badge tone={OUTCOME_TONE[r.outcome]}>{r.outcome}</Badge>{r.reason && <span className="block text-xs text-gray-400 mt-0.5">{r.reason}</span>}</td>
                      <td className="px-2 py-2"><Badge tone={r.accessDecision === 'DENY' ? 'red' : 'softGreen'}>{r.accessDecision || '—'}</Badge>{r.denyReason && <span className="block text-xs text-gray-400 mt-0.5">{r.denyReason}</span>}</td>
                      <td className="px-2 py-2">{r.escalationStatus ? <Badge tone={ESC_TONE[r.escalationStatus]}>{r.escalationStatus}</Badge> : '—'}</td>
                      <td className="px-2 py-2"><button type="button" className={BTN_SMALL} onClick={() => setOpen(r.id)}>View</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {open && <Detail id={open} onClose={() => setOpen(null)} canHandle={has('handle_chatbot_escalations')} onChanged={load} />}
        <Toast {...toast} />
      </div>
    </AppShell>
  )
}
