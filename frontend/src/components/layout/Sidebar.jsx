import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import * as icons from 'lucide-react'
import { MENUS } from '../../data/sidebarMenu'
import { useCapabilities } from '../../context/CapabilitiesContext'
import { getReviewEvents } from '../../api/frappe'

function iconFor(name) {
  return icons[name] || icons.Circle
}

export default function Sidebar({ open = false, onClose }) {
  const location = useLocation()
  const currentPage = location.pathname.replace('/', '').split('/')[0]

  const { capabilities, workspace, has } = useCapabilities()
  const canSeeQueue = capabilities.includes('view_review_queue')

  const visibleMenu = useMemo(() =>
    (MENUS[workspace] || MENUS.full).map(group => ({
      ...group,
      items: group.items.filter(item => !item.requiresCapability || has(item.requiresCapability)),
    })).filter(group => group.items.length > 0),
    [has, workspace]
  )

  const [newCount, setNewCount] = useState(0)
  useEffect(() => {
    if (!canSeeQueue) return undefined
    let active = true
    const load = () => getReviewEvents({ limit: 1 })
      .then((res) => { if (active) setNewCount(res?.counts?.new || 0) })
      .catch(() => {})
    load()
    const timer = setInterval(load, 5 * 60 * 1000)
    return () => { active = false; clearInterval(timer) }
  }, [canSeeQueue])

  const [collapsed, setCollapsed] = useState(localStorage.getItem('sidebarCollapsed') === 'true')
  function toggle() {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('sidebarCollapsed', next)
  }

  return (
    <>
    {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={onClose} aria-hidden="true" />}
    <aside className={['bg-white border-r border-gray-100 h-screen fixed lg:sticky top-0 left-0 z-40 flex flex-col transition-all duration-300 shrink-0 w-64',
      open ? 'translate-x-0' : '-translate-x-full invisible lg:visible lg:translate-x-0',
      collapsed ? 'lg:w-20' : ''].join(' ')}>
      <div className="flex items-center justify-between px-5 py-6">
        <div className="flex items-center overflow-hidden flex-1">
          <img
            src="/assets/surveillance/images/newlogo.svg"
            alt="Kenya Red Cross"
            className={[
              'object-contain object-left transition-all duration-300',
              collapsed ? 'h-13 w-full lg:h-8 lg:w-8' : 'h-13 w-full'
            ].join(' ')}
          />
        </div>
        <button type="button" onClick={onClose} aria-label="Close menu" className="lg:hidden border border-gray-200 rounded-full p-1 text-gray-400 hover:bg-gray-50 shrink-0">
          <icons.X className="w-4 h-4" />
        </button>
        <button onClick={toggle} aria-label={collapsed ? 'Expand menu' : 'Collapse menu'} className="hidden lg:block border border-gray-200 rounded-full p-1 text-gray-400 hover:bg-gray-50 shrink-0">
          {!collapsed ? <icons.ChevronLeft className="w-4 h-4" /> : <icons.ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-6">
        {visibleMenu.map((group) => (
          <div key={group.section}>
            <div className={['px-2 text-xs font-semibold text-gray-400 tracking-wide mb-2 mt-5', collapsed ? 'lg:hidden' : ''].join(' ')}>{group.section}</div>
            {group.items.map((item) => {
              const Icon = iconFor(item.icon)
              return (
                <Link
                  key={item.page}
                  to={`/${item.page}`}
                  aria-label={item.label}
                  className={['relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium mb-1',
                    currentPage === item.page ? 'bg-red-600 text-white' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'].join(' ')}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className={['whitespace-nowrap', collapsed ? 'lg:hidden' : ''].join(' ')}>{item.label}</span>
                  {item.page === 'alerts-signals' && newCount > 0 && (
                    <span className={['bg-red-600 text-white text-[10px] font-semibold rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center', collapsed ? 'absolute top-1 right-1 ring-2 ring-white' : 'ml-auto'].join(' ')}>
                      {newCount > 99 ? '99+' : newCount}
                    </span>
                  )}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>
    </aside>
    </>
  )
}
