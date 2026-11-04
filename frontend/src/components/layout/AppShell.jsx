import { useState } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'

export default function AppShell({ children }) {
  const [navOpen, setNavOpen] = useState(false)
  return (
    <div className="flex bg-white min-h-screen">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex-1 min-w-0 bg-white">
        <Header onOpenNav={() => setNavOpen(true)} />
        <main className="p-4 lg:p-8 bg-white">
          {children}
        </main>
      </div>
    </div>
  )
}
