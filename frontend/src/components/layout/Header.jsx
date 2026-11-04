import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  Bell,
  Sparkles,
  ChevronDown,
  Settings,
  LogOut,
  Menu
} from 'lucide-react'

import {
  currentUserFullName,
  getMyCapabilities,
  getMyNotifications,
  markNotificationsRead,
  logout
} from '../../api/frappe'
import { FOCUS, relTime } from '../../data/eventHelpers'

export default function Header({ onOpenNav }) {
  const navigate = useNavigate()

  const [fullName] = useState(currentUserFullName())
  const [userRole, setUserRole] = useState('')

  const firstName = useMemo(() => fullName.split(' ')[0], [fullName])

  const initials = useMemo(() =>
    fullName
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0].toUpperCase())
      .join(''),
    [fullName]
  )

  const [now, setNow] = useState(new Date())

  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef(null)
  const [notif, setNotif] = useState({ unread: 0, items: [] })

  async function loadNotifications() {
    try {
      const data = await getMyNotifications()
      setNotif({ unread: data?.unread || 0, items: data?.items || [] })
    } catch {
      // bell keeps working without a badge
    }
  }

  useEffect(() => {
    loadNotifications()
    const poll = setInterval(() => {
      if (document.visibilityState === 'visible') loadNotifications()
    }, 60000)

    function onKeyDown(e) {
      if (e.key === 'Escape') setNotifOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)

    return () => {
      clearInterval(poll)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  async function markAllRead() {
    try {
      await markNotificationsRead()
    } catch {
      return
    }
    loadNotifications()
  }

  async function openNotification(item) {
    setNotifOpen(false)
    try {
      await markNotificationsRead(item.id)
      loadNotifications()
    } catch {
      // ignore
    }
    if (item.link) navigate(item.link)
  }

  useEffect(() => {
    getMyCapabilities()
      .then(({ primary_role }) => {
        setUserRole(primary_role)
      })
      .catch((error) => {
        console.error('Failed to fetch user role:', error)
      })

    const timer = setInterval(() => {
      setNow(new Date())
    }, 30000)

    function onClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false)
      }
    }

    document.addEventListener('click', onClickOutside)

    return () => {
      clearInterval(timer)
      document.removeEventListener('click', onClickOutside)
    }
  }, [])

  const timeOfDay = useMemo(() => {
    const h = now.getHours()
    return h < 12 ? 'Morning' : h < 17 ? 'Afternoon' : 'Evening'
  }, [now])

  const dateTimeLabel = useMemo(() =>
    now.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    }) +
    ' • ' +
    now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    }),
    [now]
  )

  function goToSettings() {
    setMenuOpen(false)
    navigate('/settings')
  }

  function goToAiAssistant() {
    navigate('/ai-data-assistant')
  }

  async function handleLogout() {
    setMenuOpen(false)
    await logout()
    // Full page load so nothing from this session stays in memory for the next user.
    window.location.assign('/surveillance/login')
  }

  return (
    <header className="bg-white px-4 lg:px-8 py-4 h-20 flex items-center justify-between gap-3 border-b border-gray-100">
      <div className="flex items-center gap-3 min-w-0">
        <button type="button" onClick={onOpenNav} aria-label="Open menu" className={`lg:hidden shrink-0 w-10 h-10 rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50 ${FOCUS}`}>
          <Menu className="w-5 h-5" />
        </button>
        <div className="min-w-0 hidden sm:block">
          <h1 className="text-lg font-semibold text-brand-navy leading-tight truncate">Good {timeOfDay}, {firstName}!</h1>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{dateTimeLabel}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <div className="bg-gray-100 rounded-full h-11 hidden xl:flex items-center gap-2 pl-1 pr-4 w-64">
          <span className="w-9 h-9 rounded-full bg-white flex items-center justify-center shrink-0">
            <Search className="w-4 h-4 text-gray-600" />
          </span>
          <input
            type="text"
            aria-label="Search"
            placeholder="Search..."
            className="bg-transparent flex-1 text-sm text-gray-900 placeholder-gray-500 focus:outline-none"
          />
        </div>

        <div className="bg-gray-100 rounded-full h-11 flex items-center gap-1.5 px-1.5">
          <div ref={notifRef} className="relative">
            <button
              aria-label="Notifications"
              aria-expanded={notifOpen}
              className={`relative w-8 h-8 rounded-full bg-white flex items-center justify-center hover:bg-gray-50 transition-colors cursor-pointer ${FOCUS}`}
              onClick={() => setNotifOpen(!notifOpen)}
            >
              <Bell className="w-4 h-4 text-gray-600" />
              {notif.unread > 0 && (
                <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold flex items-center justify-center">
                  {notif.unread > 9 ? '9+' : notif.unread}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 top-[calc(100%+8px)] w-80 max-h-96 overflow-y-auto bg-white rounded-xl shadow-lg border border-gray-100 py-3 z-50">
                <div className="flex items-center justify-between px-4 pb-2">
                  <p className="text-sm font-semibold text-gray-900">Notifications</p>
                  <button
                    type="button"
                    onClick={markAllRead}
                    className={`text-xs font-medium text-red-700 hover:text-red-800 rounded ${FOCUS}`}
                  >
                    Mark all as read
                  </button>
                </div>
                {notif.items.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-gray-400">No notifications yet.</p>
                ) : (
                  <ul>
                    {notif.items.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => openNotification(item)}
                          className={`w-full flex items-start gap-2 px-4 py-2.5 text-left hover:bg-gray-50 ${item.read ? '' : 'bg-red-50'} ${FOCUS}`}
                        >
                          <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${item.read ? 'bg-transparent' : 'bg-red-600'}`} />
                          <span className="min-w-0">
                            <span className="block text-sm text-gray-900">{item.text}</span>
                            <span className="block text-xs text-gray-400 mt-0.5">{relTime(item.at)}</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <button
            aria-label="Open AI assistant"
            className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center hover:bg-gray-200 transition-colors cursor-pointer"
            onClick={goToAiAssistant}
          >
            <Sparkles className="w-4 h-4 text-gray-900" />
          </button>
        </div>

        <div ref={menuRef} className="relative">
          <button
            aria-label={`Account menu for ${fullName}`}
            aria-expanded={menuOpen}
            className="bg-gray-100 rounded-full h-11 flex items-center gap-2 pl-1.5 pr-1.5 sm:pr-3 hover:bg-gray-200 transition-colors cursor-pointer"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            <span className="w-8 h-8 rounded-full bg-red-600 text-white flex items-center justify-center text-xs font-semibold shrink-0">
              {initials}
            </span>
            <span className="text-left leading-tight hidden sm:block">
              <span className="block text-sm font-semibold text-gray-900">{fullName}</span>
              <span className="block text-xs text-gray-500">
                {userRole}
              </span>
            </span>
            <ChevronDown className={['w-4 h-4 text-gray-500 transition-transform hidden sm:block', menuOpen ? 'rotate-180' : ''].join(' ')} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-[calc(100%+8px)] w-48 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50">
              <button
                className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors cursor-pointer"
                onClick={goToSettings}
              >
                <Settings className="w-4 h-4 text-gray-500" />
                Settings
              </button>
              <button
                className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-red-700 hover:bg-red-50 transition-colors cursor-pointer"
                onClick={handleLogout}
              >
                <LogOut className="w-4 h-4" />
                Log Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
