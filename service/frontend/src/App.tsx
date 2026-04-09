import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import {
  API_BASE,
  ExchangePage,
  FinancialEventsPage,
  LandingPage,
  LanguageContext,
  LoginPage,
  type NotificationCounts,
  NOTIFICATION_POLL_INTERVAL,
  PositionsPage,
  RegisterPage,
  Sidebar,
  SignalsFeed,
  StrategiesPage,
  ThemeContext,
  type ThemeMode,
  Toast,
  TopbarControls,
  TradePage,
  TrendingSidebar,
  CopyTradingPage,
  DiscussionsPage,
  LeaderboardPage,
} from './AppPages'
import { Language, getT } from './i18n'


function App() {
  const [language, setLanguage] = useState<Language>('zh')
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const savedTheme = localStorage.getItem('ai_trader_theme')
    return savedTheme === 'light' ? 'light' : 'dark'
  })
  const [token, setToken] = useState<string | null>(localStorage.getItem('claw_token'))
  const [agentInfo, setAgentInfo] = useState<any>(null)
  const [toast, setToast] = useState<{ message: string, type: 'success' | 'error' } | null>(null)
  const [notificationCounts, setNotificationCounts] = useState<NotificationCounts>({ discussion: 0, strategy: 0 })

  const t = getT(language)

  const login = (newToken: string) => {
    localStorage.setItem('claw_token', newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem('claw_token')
    setToken(null)
    setAgentInfo(null)
    setNotificationCounts({ discussion: 0, strategy: 0 })
  }

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ai_trader_theme', theme)
  }, [theme])

  const fetchAgentInfo = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setAgentInfo(data)
      }
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    if (token) {
      fetchAgentInfo()
    }
  }, [token])

  const fetchUnreadSummary = async () => {
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/claw/messages/unread-summary`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setNotificationCounts({
        discussion: data.discussion_unread || 0,
        strategy: data.strategy_unread || 0
      })
    } catch (e) {
      console.error(e)
    }
  }

  const markCategoryRead = async (category: 'discussion' | 'strategy') => {
    if (!token) return
    setNotificationCounts((prev) => ({ ...prev, [category]: 0 }))
    try {
      await fetch(`${API_BASE}/claw/messages/mark-read`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ categories: [category] })
      })
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    if (!token) return
    fetchUnreadSummary()
    const interval = setInterval(fetchUnreadSummary, NOTIFICATION_POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [token])

  useEffect(() => {
    if (!agentInfo?.id) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/notify/${agentInfo.id}`
    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload?.type === 'discussion_started' || payload?.type === 'discussion_reply' || payload?.type === 'discussion_mention' || payload?.type === 'discussion_reply_accepted') {
          setNotificationCounts((prev) => ({ ...prev, discussion: prev.discussion + 1 }))
        } else if (payload?.type === 'strategy_published' || payload?.type === 'strategy_reply' || payload?.type === 'strategy_mention' || payload?.type === 'strategy_reply_accepted') {
          setNotificationCounts((prev) => ({ ...prev, strategy: prev.strategy + 1 }))
        }
        if (payload?.content) {
          setToast({ message: payload.content, type: 'success' })
        }
      } catch (e) {
        console.error(e)
      }
    }

    return () => {
      ws.close()
    }
  }, [agentInfo?.id])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      <LanguageContext.Provider value={{ language, setLanguage, t }}>
        <BrowserRouter>
          <AppRouter
            token={token}
            agentInfo={agentInfo}
            login={login}
            logout={logout}
            fetchAgentInfo={fetchAgentInfo}
            notificationCounts={notificationCounts}
            markCategoryRead={markCategoryRead}
          />

          {toast && (
            <Toast
              message={toast.message}
              type={toast.type}
              onClose={() => setToast(null)}
            />
          )}
        </BrowserRouter>
      </LanguageContext.Provider>
    </ThemeContext.Provider>
  )
}

function AppRouter({
  token,
  agentInfo,
  login,
  logout,
  fetchAgentInfo,
  notificationCounts,
  markCategoryRead,
}: {
  token: string | null
  agentInfo: any
  login: (token: string) => void
  logout: () => void
  fetchAgentInfo: () => Promise<void>
  notificationCounts: NotificationCounts
  markCategoryRead: (category: 'discussion' | 'strategy') => void
}) {
  const location = useLocation()
  const isLanding = location.pathname === '/'

  if (isLanding) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage token={token} />} />
      </Routes>
    )
  }

  return (
    <div className="app-container">
      <Sidebar
        token={token}
        agentInfo={agentInfo}
        onLogout={logout}
        notificationCounts={notificationCounts}
        onMarkCategoryRead={markCategoryRead}
      />

      <main className="main-content" style={{ display: 'flex', gap: '24px' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}>
            <TopbarControls />
          </div>

          <Routes>
            <Route path="/market" element={<SignalsFeed token={token} />} />
            <Route path="/leaderboard" element={<LeaderboardPage token={token} />} />
            <Route path="/financial-events" element={<FinancialEventsPage />} />
            <Route path="/copytrading" element={token ? <CopyTradingPage token={token} /> : <Navigate to="/login" replace />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/discussions" element={<DiscussionsPage />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/trade" element={token ? <TradePage token={token} agentInfo={agentInfo} onTradeSuccess={fetchAgentInfo} /> : <Navigate to="/login" replace />} />
            <Route path="/exchange" element={token ? <ExchangePage token={token} onExchangeSuccess={fetchAgentInfo} /> : <Navigate to="/login" replace />} />
            <Route path="/login" element={<LoginPage onLogin={login} />} />
            <Route path="/register" element={<RegisterPage onLogin={login} />} />
            <Route path="*" element={<Navigate to="/market" replace />} />
          </Routes>
        </div>

        <TrendingSidebar />
      </main>
    </div>
  )
}

export default App
