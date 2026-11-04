import { useState, useEffect, useRef, useMemo } from 'react'
import { Plus, History, Trash2, Sparkles, Mic, ArrowUp } from 'lucide-react'
import AppShell from '../components/layout/AppShell'
import KbAnswer from '../components/assistant/KbAnswer'
import { queryAiAssistant, askKnowledgeBase, currentUserId } from '../api/frappe'

// Chats are kept per signed-in user, so the next person on a shared device does not see them (R82).
const LEGACY_STORAGE_KEY = 'krcs_ai_assistant_chats'
const storageKey = () => `${LEGACY_STORAGE_KEY}:${currentUserId() || 'Guest'}`
const MAX_CHATS = 50

// The Surveillance data source is not ready to offer yet; flip this when it is.
const DATA_SOURCE_AVAILABLE = false

const SUGGESTED_PROMPTS = {
  documents: [
    'What is the case definition for acute watery diarrhoea?',
    'How do I report a suspected measles case?',
    'Dalili za kipindupindu ni zipi?',
  ],
  data: [
    'Show cholera cases by region',
    'What are the active alerts this week?',
    'Summarize recent case reports',
  ],
}

const GENERIC_ERROR = 'Sorry, something went wrong while processing that request.'

function defaultLanguage() {
  const lang = typeof navigator !== 'undefined' ? navigator.language || '' : ''
  return lang.toLowerCase().startsWith('sw') ? 'Kiswahili' : 'English'
}

function capChats(list) {
  if (list.length <= MAX_CHATS) return list
  return [...list].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CHATS)
}

function loadChats() {
  try {
    // Older chats were stored with no owner, so nobody can safely be shown them.
    localStorage.removeItem(LEGACY_STORAGE_KEY)
    const raw = localStorage.getItem(storageKey())
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? capChats(parsed) : []
  } catch {
    return []
  }
}

function kbHistory(messages) {
  return messages.slice(-6).map((m) => ({
    role: m.role,
    content: m.kind === 'kb' ? m.result?.answer || m.content || '' : m.content || '',
  }))
}

function getRealtime() {
  const rt = typeof window !== 'undefined' ? window.frappe?.realtime : null
  return rt && typeof rt.on === 'function' ? rt : null
}

function buildErrorReply(e, question, source, language) {
  if (e?.status === 503) {
    return { role: 'assistant', kind: 'error', content: 'The knowledge base is temporarily unavailable. Try again in a moment.', retryable: true, question, source, language }
  }
  if (e?.status === 403) {
    return { role: 'assistant', kind: 'error', content: 'You don\u2019t have access to the knowledge base. Ask an administrator.' }
  }
  return { role: 'assistant', kind: 'error', content: GENERIC_ERROR }
}

function PillToggle({ label, options, value, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={o.disabled}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={['flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors',
            value === o.value ? 'bg-red-600 text-white' : 'text-gray-600 hover:bg-gray-100',
            o.disabled ? 'opacity-60 cursor-not-allowed hover:bg-transparent' : ''].join(' ')}
        >
          {o.label}
          {o.badge && <span className="rounded-full bg-gray-200 text-gray-600 px-1.5 text-[10px] font-medium">{o.badge}</span>}
        </button>
      ))}
    </div>
  )
}

function formatTime(ts) {
  const d = new Date(ts)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' \u2022 ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

const voiceSupported = typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition)

export default function AiDataAssistant() {
  const [chats, setChats] = useState(loadChats)
  const [currentChatId, setCurrentChatId] = useState(null)
  const [inputText, setInputText] = useState(() => new URLSearchParams(window.location.search).get('q') || '')
  const [isLoading, setIsLoading] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [draftSource, setDraftSource] = useState('documents')
  const [draftLanguage, setDraftLanguage] = useState(defaultLanguage)
  const [live, setLive] = useState(null)

  const scrollAreaRef = useRef(null)
  const textareaRef = useRef(null)
  const historyRef = useRef(null)
  const recognitionRef = useRef(null)
  const chatsRef = useRef(chats)
  chatsRef.current = chats

  const currentChat = useMemo(() => chats.find((c) => c.id === currentChatId) || null, [chats, currentChatId])
  const messages = currentChat?.messages || []
  const sortedChats = useMemo(() => [...chats].sort((a, b) => b.updatedAt - a.updatedAt), [chats])
  const storedSource = currentChat ? currentChat.source : draftSource
  const source = DATA_SOURCE_AVAILABLE && storedSource === 'data' ? 'data' : 'documents'
  const language = (currentChat ? currentChat.language : draftLanguage) || defaultLanguage()

  function persistChats(next) {
    try {
      localStorage.setItem(storageKey(), JSON.stringify(next))
    } catch {
      // storage unavailable or full; chats stay in memory only
    }
  }

  function updateCurrentChat(patch) {
    if (!currentChatId) return false
    setChats((prev) => {
      const next = prev.map((c) => (c.id === currentChatId ? { ...c, ...patch } : c))
      persistChats(next)
      return next
    })
    return true
  }

  function changeSource(value) {
    if (!updateCurrentChat({ source: value })) setDraftSource(value)
  }

  function changeLanguage(value) {
    updateCurrentChat({ language: value })
    setDraftLanguage(value) // the next New Query keeps this choice
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (scrollAreaRef.current) scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
    })
  }

  function autoGrowTextarea() {
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (!el) return
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 160) + 'px'
    })
  }

  function startNewQuery() {
    setCurrentChatId(null)
    setInputText('')
    setShowHistory(false)
  }

  function selectChat(id) {
    setCurrentChatId(id)
    setShowHistory(false)
    scrollToBottom()
  }

  function deleteChat(id) {
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== id)
      persistChats(next)
      return next
    })
    if (currentChatId === id) setCurrentChatId(null)
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  async function runQuery(chatId, question, querySource, queryLanguage) {
    setIsLoading(true)
    scrollToBottom()

    let reply
    try {
      if (querySource === 'data') {
        const result = await queryAiAssistant(question)
        reply = { role: 'assistant', content: result.answer, table: result.table }
      } else {
        const history = kbHistory(chatsRef.current.find((c) => c.id === chatId)?.messages.slice(0, -1) || [])
        const streamId = crypto.randomUUID()
        const rt = getRealtime()
        const handler = (data) => {
          if (!data || data.stream_id !== streamId) return
          if (data.done) {
            rt.off?.('kb_answer', handler)
            return
          }
          if (data.status === 'checking') {
            setLive({ streamId, text: 'Writing a summary and checking it against the approved documents…' })
            return
          }
          if (data.delta) {
            setLive((prev) => ({ streamId, text: (prev?.streamId === streamId && !prev.checking ? prev.text : '') + data.delta }))
            scrollToBottom()
          }
        }
        if (rt) rt.on('kb_answer', handler)
        let result
        try {
          result = await askKnowledgeBase({ query: question, language: queryLanguage, history, streamId, conversationId: chatId })
        } finally {
          rt?.off?.('kb_answer', handler)
          setLive(null)
        }
        reply = { role: 'assistant', kind: 'kb', result, content: result.answer }
      }
    } catch (e) {
      reply = buildErrorReply(e, question, querySource, queryLanguage)
    }

    setChats((prev) => {
      const next = capChats(
        prev.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, reply], updatedAt: Date.now() } : c))
      )
      persistChats(next)
      return next
    })
    setIsLoading(false)
    scrollToBottom()
  }

  function send(preset) {
    const question = (preset ?? inputText).trim()
    if (!question || isLoading) return

    let chatId = currentChatId
    let chats0 = chatsRef.current
    if (!chatId) {
      chatId = crypto.randomUUID()
      const chat = { id: chatId, title: question.slice(0, 60), messages: [], updatedAt: Date.now(), source, language }
      chats0 = [...chats0, chat]
      setCurrentChatId(chatId)
    }

    chats0 = capChats(chats0.map((c) =>
      c.id === chatId ? { ...c, messages: [...c.messages, { role: 'user', content: question }], updatedAt: Date.now() } : c
    ))
    chatsRef.current = chats0
    setChats(chats0)
    setInputText('')
    autoGrowTextarea()
    persistChats(chats0)
    scrollToBottom()

    runQuery(chatId, question, source, language)
  }

  function rememberFeedback(index, value) {
    updateCurrentChat({
      messages: currentChat.messages.map((m, i) => (i === index ? { ...m, result: { ...m.result, feedback: value } } : m)),
    })
  }

  function retry(index) {
    if (isLoading || !currentChat) return
    const msg = currentChat.messages[index]
    if (!msg?.retryable) return
    const next = chatsRef.current.map((c) =>
      c.id === currentChat.id ? { ...c, messages: c.messages.filter((_, i) => i !== index) } : c
    )
    chatsRef.current = next
    setChats(next)
    persistChats(next)
    runQuery(currentChat.id, msg.question, msg.source, msg.language)
  }

  function setupRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return null
    const rec = new SpeechRecognition()
    rec.continuous = false
    rec.interimResults = false
    rec.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setInputText((prev) => (prev ? prev + ' ' : '') + transcript)
      autoGrowTextarea()
    }
    rec.onend = () => setIsRecording(false)
    rec.onerror = () => setIsRecording(false)
    return rec
  }

  function toggleVoice() {
    if (!voiceSupported) return
    if (isRecording) {
      recognitionRef.current?.stop()
      setIsRecording(false)
      return
    }
    recognitionRef.current = recognitionRef.current || setupRecognition()
    if (!recognitionRef.current) return
    recognitionRef.current.lang = language === 'Kiswahili' ? 'sw-KE' : 'en-US'
    setIsRecording(true)
    recognitionRef.current.start()
  }

  useEffect(() => {
    function onClickOutside(e) {
      if (showHistory && historyRef.current && !historyRef.current.contains(e.target)) {
        setShowHistory(false)
      }
    }
    document.addEventListener('click', onClickOutside)
    return () => {
      document.removeEventListener('click', onClickOutside)
      recognitionRef.current?.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showHistory])

  return (
    <AppShell>
      <div className="flex flex-col h-[calc(100vh-140px)] bg-white rounded-2xl border border-gray-100 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 sm:px-6 py-4 border-b border-gray-100">
          <button
            onClick={startNewQuery}
            aria-label="New Query"
            className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 sm:px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">New Query</span>
          </button>

          <div className="relative shrink-0" ref={historyRef}>
            <button
              onClick={() => setShowHistory((v) => !v)}
              aria-label="Your Chats"
              className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 sm:px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              <History className="w-4 h-4" />
              <span className="hidden sm:inline">Your Chats</span>
            </button>

            {showHistory && (
              <div className="absolute right-0 mt-2 w-72 max-h-96 overflow-y-auto bg-white border border-gray-100 rounded-xl shadow-lg z-30 py-2">
                {!chats.length && <div className="px-4 py-6 text-sm text-gray-400 text-center">No chats yet</div>}
                {sortedChats.map((chat) => (
                  <div key={chat.id} className={['group flex items-start gap-2 pr-3 hover:bg-gray-50', chat.id === currentChatId ? 'bg-red-50' : ''].join(' ')}>
                    <button type="button" onClick={() => selectChat(chat.id)} className="min-w-0 flex-1 text-left pl-4 py-2.5">
                      <div className="text-sm font-medium text-gray-900 truncate">{chat.title}</div>
                      <div className="text-xs text-gray-400">{formatTime(chat.updatedAt)}</div>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); deleteChat(chat.id) }}
                      aria-label={`Delete chat: ${chat.title}`}
                      className="opacity-0 group-hover:opacity-100 focus:opacity-100 text-gray-300 hover:text-red-700 shrink-0 mt-3"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div ref={scrollAreaRef} className="flex-1 overflow-y-auto px-4 pt-6 sm:px-6">
          {!messages.length ? (
            <div className="h-full flex flex-col items-center justify-center text-center px-4 py-10">
              <img src="/assets/surveillance/images/logo.png" alt="KRCS" className="w-20 h-18 object-contain mb-5" />
              <h2 className="text-2xl sm:text-3xl font-medium text-brand-navy mb-3">Welcome to KRCS AI DataAssistant</h2>
              <p className="text-gray-500 text-base sm:text-lg max-w-2xl mb-8">
                {source === 'documents'
                  ? 'Ask about KRCS protocols, case definitions and guidelines. Answers are written from approved KRCS documents, with their sources.'
                  : 'Ask me about community health data, disease trends, alerts, or reports. I\'ll query the database and show you results.'}
              </p>
              <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
                {SUGGESTED_PROMPTS[source].map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => send(prompt)}
                    className="text-sm text-gray-600 border border-gray-200 rounded-full px-4 py-2 hover:bg-gray-50 hover:border-gray-300"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto pb-6 space-y-6">
              {messages.map((m, i) => (
                <div key={i} className={['flex', m.role === 'user' ? 'justify-end' : 'justify-start'].join(' ')}>
                  {m.role === 'assistant' ? (
                    <div className="flex gap-3 min-w-0">
                      <div className="w-7 h-7 mt-1 rounded-full bg-red-600 flex items-center justify-center shrink-0">
                        <Sparkles className="w-3.5 h-3.5 text-white" />
                      </div>
                      <div className="space-y-3 min-w-0">
                        {m.kind === 'kb' ? (
                          <KbAnswer result={m.result} onFeedback={(value) => rememberFeedback(i, value)} />
                        ) : (
                        <div className="max-w-2xl text-[15px] leading-7 text-gray-800">
                          {m.content}
                          {m.retryable && i === messages.length - 1 && (
                            <div className="mt-2">
                              <button
                                type="button"
                                onClick={() => retry(i)}
                                disabled={isLoading}
                                className="text-xs font-medium border border-gray-200 bg-white rounded-lg px-3 py-1 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                              >
                                Retry
                              </button>
                            </div>
                          )}
                        </div>
                        )}
                        {m.table && (
                          <div className="border border-gray-100 rounded-xl overflow-hidden">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="bg-gray-50 text-left text-gray-500 text-xs">
                                  {m.table.columns.map((col) => (
                                    <th key={col} className="px-4 py-2 font-medium">{col}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {m.table.rows.map((row, ri) => (
                                  <tr key={ri} className="border-t border-gray-50">
                                    {row.map((cell, ci) => (
                                      <td key={ci} className="px-4 py-2 text-gray-700">{cell}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="max-w-[75%] bg-red-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] leading-6 break-words whitespace-pre-wrap">
                      {m.content}
                    </div>
                  )}
                </div>
              ))}

              {isLoading && live?.text && (
                <div className="flex gap-3">
                  <div className="w-7 h-7 mt-1 rounded-full bg-red-600 flex items-center justify-center shrink-0">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                  <div className="max-w-2xl text-[15px] leading-7 text-gray-800 whitespace-pre-wrap">{live.text}</div>
                </div>
              )}

              {isLoading && !live?.text && (
                <div className="flex gap-3">
                  <div className="w-7 h-7 mt-1 rounded-full bg-red-600 flex items-center justify-center shrink-0">
                    <Sparkles className="w-3.5 h-3.5 text-white" />
                  </div>
                  <div className="py-3 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }}></span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="px-4 sm:px-6 pb-5 pt-3">
          <div className="max-w-3xl mx-auto">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <PillToggle
                label="Answer source"
                value={source}
                onChange={changeSource}
                options={[
                  { value: 'documents', label: 'Documents' },
                  { value: 'data', label: 'Surveillance data', disabled: !DATA_SOURCE_AVAILABLE, badge: DATA_SOURCE_AVAILABLE ? null : 'Coming soon' },
                ]}
              />
              <PillToggle
                label="Language"
                value={language}
                onChange={changeLanguage}
                options={[
                  { value: 'English', label: 'English' },
                  { value: 'Kiswahili', label: 'Kiswahili' },
                ]}
              />
            </div>

            <div className="flex items-end gap-2 border border-gray-200 bg-gray-50 rounded-3xl px-4 sm:px-5 py-2.5">
              <textarea
                ref={textareaRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={onKeydown}
                rows={1}
                aria-label="Your question"
                placeholder={source === 'documents' ? 'Ask about KRCS protocols and guidelines...' : "Ask about health data... (e.g. 'Show cholera cases by region')"}
                className="flex-1 bg-transparent resize-none focus:outline-none text-sm sm:text-base text-gray-800 placeholder:text-gray-400 py-1.5 max-h-40"
              ></textarea>

              <button
                onClick={toggleVoice}
                disabled={!voiceSupported}
                title={voiceSupported ? 'Voice input' : 'Voice input not supported in this browser'}
                aria-label="Voice input"
                className={['rounded-full w-10 h-10 flex items-center justify-center shrink-0 border transition-colors',
                  isRecording ? 'bg-red-100 border-red-200 text-red-700' : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-100',
                  !voiceSupported ? 'opacity-40 cursor-not-allowed' : ''].join(' ')}
              >
                <Mic className="w-4 h-4" />
              </button>

              <button
                onClick={() => send()}
                aria-label="Send"
                disabled={!inputText.trim() || isLoading}
                className="rounded-full w-10 h-10 flex items-center justify-center shrink-0 bg-red-600 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-red-700 transition-colors"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>

            <p className="text-center text-xs text-gray-400 mt-3">
              {source === 'documents'
                ? 'Answers come from approved KRCS documents uploaded on the Knowledge Base page.'
                : 'AI translates your questions into database queries. Results are based on current surveillance data.'}
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
