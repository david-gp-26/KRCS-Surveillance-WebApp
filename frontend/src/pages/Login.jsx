import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { login } from '../api/frappe'

export default function Login() {
  const [usr, setUsr] = useState('')
  const [pwd, setPwd] = useState('')
  const [error, setError] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const ok = await login(usr, pwd)
      if (ok) {
        // Full page load: the CSRF token and capabilities come with the page, and the guest ones are now stale.
        window.location.assign('/surveillance/dashboard')
      } else {
        setError('Invalid email or password. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white min-h-screen w-full flex items-center justify-center">
      <div className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-[1fr_1.5px_1fr] overflow-hidden">
        <div className="p-10 md:p-14 flex flex-col justify-center">
          <div className="mb-10">
            <img src="/assets/surveillance/images/newlogo.svg" alt="Kenya Red Cross" className="h-10 w-auto object-contain" />
          </div>
          <h1 className="text-3xl font-extrabold text-brand-navy mb-1">Welcome Back!</h1>
          <p className="text-gray-400 mb-8">Login to your account</p>

          <form onSubmit={handleLogin}>
            <label className="block text-sm font-semibold text-gray-800 mb-1">Username or Email</label>
            <input
              value={usr}
              onChange={(e) => setUsr(e.target.value)}
              type="text"
              required
              className="w-full bg-gray-100 rounded-lg px-4 py-3 mb-5 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
              placeholder="Enter your username or email"
            />

            <label className="block text-sm font-semibold text-gray-800 mb-1">Password</label>
            <div className="relative mb-6">
              <input
                value={pwd}
                onChange={(e) => setPwd(e.target.value)}
                type={showPwd ? 'text' : 'password'}
                required
                className="w-full bg-gray-100 rounded-lg px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
                placeholder="Enter your password"
              />
              <button
                type="button"
                onClick={() => setShowPwd(!showPwd)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 cursor-pointer transition-colors"
                aria-label={showPwd ? 'Hide password' : 'Show password'}
              >
                {!showPwd ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="w-5 h-5"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"
                    />
                    <circle cx="12" cy="12" r="2.5" />
                  </svg>
                ) : (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="w-5 h-5"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 12c2.2 2.7 5.2 4 9 4s6.8-1.3 9-4"
                    />
                    <path strokeLinecap="round" d="M7 10.5 5.5 9" />
                    <path strokeLinecap="round" d="M12 9.5V8" />
                    <path strokeLinecap="round" d="M17 10.5 18.5 9" />
                    <path strokeLinecap="round" strokeWidth="2" d="M4 4l16 16" />
                  </svg>
                )}
              </button>
            </div>

            {error && <p className="text-red-700 text-sm mb-4">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-red-600 hover:bg-red-700 disabled:bg-red-400 disabled:cursor-not-allowed text-white font-semibold rounded-lg py-3 mb-4 flex items-center justify-center gap-2 transition-colors"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Logging in...' : 'Login'}
            </button>
            <p className="text-center text-sm text-gray-600">Forgot Password? <a href="#" className="text-red-700 font-medium">Reset</a></p>
          </form>
        </div>

        <div className="hidden md:block bg-gray-300"></div>

        <div className="hidden md:flex items-center justify-center bg-white p-10">
          <img src="/assets/surveillance/images/crest.svg" alt="" className="w-80 h-80 object-contain" />
        </div>
      </div>
    </div>
  )
}
