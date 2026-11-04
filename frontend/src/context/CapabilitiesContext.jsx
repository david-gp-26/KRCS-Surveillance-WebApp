import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getMyCapabilities } from '../api/frappe'

const CapabilitiesContext = createContext(null)

export function CapabilitiesProvider({ children }) {
  const [capabilities, setCapabilities] = useState([])
  const [primaryRole, setPrimaryRole] = useState('')
  const [workspace, setWorkspace] = useState('full')
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const { capabilities: caps, primary_role, workspace: ws } = await getMyCapabilities()
      setCapabilities(caps)
      setPrimaryRole(primary_role)
      setWorkspace(ws || 'full')
    } catch (e) {
      // Guests have no capabilities. Keep what we have on other errors, such as a dropped connection.
      if (e?.status === 401 || e?.status === 403) {
        setCapabilities([])
        setPrimaryRole('')
        setWorkspace('full')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // key can be one capability or a list (any of them is enough)
  const has = useCallback(
    (key) => (Array.isArray(key) ? key.some((k) => capabilities.includes(k)) : capabilities.includes(key)),
    [capabilities]
  )

  const value = useMemo(
    () => ({ capabilities, primaryRole, workspace, loading, has, refresh }),
    [capabilities, primaryRole, workspace, loading, has, refresh]
  )

  return <CapabilitiesContext.Provider value={value}>{children}</CapabilitiesContext.Provider>
}

export function useCapabilities() {
  const ctx = useContext(CapabilitiesContext)
  if (!ctx) throw new Error('useCapabilities must be used within a CapabilitiesProvider')
  return ctx
}
