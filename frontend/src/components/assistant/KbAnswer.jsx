import { useState, Children, cloneElement, isValidElement } from 'react'
import ReactMarkdown from 'react-markdown'
import { Copy, Check, AlertTriangle, ThumbsUp, ThumbsDown } from 'lucide-react'
import { submitChatbotFeedback } from '../../api/frappe'

const CITE = /\[(\d+)\]/g

function locationOf(s) {
  return s.section || (s.page ? `p. ${s.page}` : '')
}

function shortTitle(title) {
  const t = String(title ?? '').replace(/\.[A-Za-z0-9]{1,5}$/, '')
  return t.length > 30 ? `${t.slice(0, 30)}…` : t
}

function CiteChip({ source, n, onJump }) {
  const [open, setOpen] = useState(false)
  const loc = locationOf(source)
  return (
    <span className="relative inline align-middle" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        onClick={() => onJump(n)}
        aria-label={`Source ${n}: ${source.title}${loc ? `, ${loc}` : ''}`}
        className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-gray-100 px-1 align-middle text-[10px] font-medium leading-none text-gray-600 hover:bg-gray-200"
      >
        {n}
      </button>
      {open && (
        <span role="tooltip" className="absolute bottom-full left-1/2 z-20 mb-1 block w-56 -translate-x-1/2 rounded-lg border border-gray-200 bg-white p-2 text-left text-xs font-normal leading-snug text-gray-600 shadow-lg">
          <span className="block font-semibold text-gray-900">{source.title}</span>
          {loc && <span className="block text-gray-500">{loc}</span>}
        </span>
      )}
    </span>
  )
}

export default function KbAnswer({ result, onFeedback }) {
  const [copied, setCopied] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [openN, setOpenN] = useState(null)
  const [feedback, setFeedback] = useState(result?.feedback || null)
  const [feedbackError, setFeedbackError] = useState(false)

  const answer = result?.answer ?? (result?.passages || []).map((p) => p.text).join('\n\n')
  const sources = Array.isArray(result?.sources) ? result.sources : []
  const usedSet = new Set(result?.used_sources || [])
  const used = sources.filter((s) => usedSet.has(s.n))
  const unused = sources.filter((s) => !usedSet.has(s.n))
  const byN = new Map(sources.map((s) => [s.n, s]))
  const notFound = result?.mode === 'not_found' || result?.mode === 'conflict'
  const MODE_NOTE = {
    verbatim: 'Quoted from approved documents.',
    summary: 'Summary checked against the approved documents. Open a source to read the original.',
    public: 'Approved public guidance.',
  }

  function jump(n) {
    setOpenN(n)
    if (!usedSet.has(n)) setShowAll(true)
  }

  function withCites(children) {
    return Children.map(children, (child) => {
      if (typeof child === 'string') {
        const out = []
        let last = 0
        for (const m of child.matchAll(CITE)) {
          const source = byN.get(Number(m[1]))
          if (!source) continue
          if (m.index > last) out.push(child.slice(last, m.index))
          out.push(<CiteChip key={`${m.index}`} source={source} n={source.n} onJump={jump} />)
          last = m.index + m[0].length
        }
        if (!out.length) return child
        if (last < child.length) out.push(child.slice(last))
        return out
      }
      if (isValidElement(child) && child.props.children) {
        return cloneElement(child, undefined, withCites(child.props.children))
      }
      return child
    })
  }

  const components = {
    p: ({ children }) => <p className="mb-3 last:mb-0">{withCites(children)}</p>,
    li: ({ children }) => <li>{withCites(children)}</li>,
    ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
    strong: ({ children }) => <strong className="font-semibold">{withCites(children)}</strong>,
    h1: ({ children }) => <p className="mb-3 font-semibold">{children}</p>,
    h2: ({ children }) => <p className="mb-3 font-semibold">{children}</p>,
    h3: ({ children }) => <p className="mb-3 font-semibold">{children}</p>,
    a: ({ children }) => <span>{children}</span>,
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  async function rate(value) {
    setFeedback(value)
    setFeedbackError(false)
    try {
      await submitChatbotFeedback(result.log_id, value === 'yes')
      onFeedback?.(value)
    } catch {
      setFeedback(null)
      setFeedbackError(true)
    }
  }

  const footer = [
    result?.detected_disease,
    Number.isFinite(Number(result?.took_ms)) && result?.took_ms != null ? `Answered in ${(Number(result.took_ms) / 1000).toFixed(1)} s` : null,
  ].filter(Boolean)

  const visibleSources = notFound ? [] : showAll ? [...used, ...unused] : used
  const openSource = visibleSources.find((s) => s.n === openN)
  const detail = openSource
    ? [openSource.section && `Section: ${openSource.section}`, openSource.page && `Page ${openSource.page}`, openSource.version && `Version ${openSource.version}`].filter(Boolean).join(' · ')
    : ''

  return (
    <div className="min-w-0 max-w-2xl text-[15px] leading-7 text-gray-800">
      {MODE_NOTE[result?.mode] && (
        <div className="mb-2 text-xs text-gray-500">{MODE_NOTE[result.mode]}</div>
      )}
      {result?.escalated && (
        <div className="mb-2 flex items-center gap-1.5 text-xs text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Passed to {result.escalated_to || 'a person'} for a reply.
        </div>
      )}
      {result?.mode === 'passages' && (
        <div className="mb-2 flex items-center gap-1.5 text-xs text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          The answer model is unavailable, so these are the most relevant passages.
        </div>
      )}

      <div className={notFound ? 'text-gray-500' : ''}>
        <ReactMarkdown components={components}>{answer}</ReactMarkdown>
      </div>

      {(visibleSources.length > 0 || (!notFound && unused.length > 0)) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {visibleSources.map((s) => (
            <button
              key={s.n}
              type="button"
              onClick={() => setOpenN((cur) => (cur === s.n ? null : s.n))}
              aria-expanded={openN === s.n}
              title={s.title}
              className={`rounded-full border px-2.5 py-1 text-xs leading-4 text-gray-600 hover:bg-gray-50 ${openN === s.n ? 'border-gray-400 bg-gray-50' : 'border-gray-200'}`}
            >
              {s.n} · {shortTitle(s.title)}
            </button>
          ))}
          {!notFound && unused.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-xs text-gray-500 underline-offset-2 hover:text-gray-700 hover:underline"
            >
              {showAll ? 'Hide unused sources' : 'Show all sources'}
            </button>
          )}
        </div>
      )}

      {openSource && (
        <div className="mt-2 rounded-lg bg-gray-50 p-3 text-sm leading-normal text-gray-600">
          {detail && <p className="mb-1.5 text-xs text-gray-500">{detail}</p>}
          <p className="whitespace-pre-wrap">{openSource.text}</p>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between gap-3 text-xs leading-5 text-gray-400">
        <span>{footer.join(' · ')}</span>
        <div className="flex items-center gap-1 shrink-0">
          {result?.log_id && (
            <>
              <span className={feedbackError ? 'text-red-700' : ''}>
                {feedbackError ? 'Could not save. Try again.' : feedback ? 'Thanks for your feedback' : 'Was this helpful?'}
              </span>
              <button type="button" onClick={() => rate('yes')} disabled={!!feedback} aria-label="Helpful" aria-pressed={feedback === 'yes'} title="Helpful" className={`rounded p-1 hover:bg-gray-100 ${feedback === 'yes' ? 'text-green-700' : 'text-gray-400'}`}>
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => rate('no')} disabled={!!feedback} aria-label="Not helpful" aria-pressed={feedback === 'no'} title="Not helpful" className={`rounded p-1 hover:bg-gray-100 ${feedback === 'no' ? 'text-red-700' : 'text-gray-400'}`}>
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={copy}
            aria-label="Copy answer"
            title={copied ? 'Copied' : 'Copy'}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
