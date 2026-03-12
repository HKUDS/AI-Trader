import { useState, useEffect, useMemo, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Language, getT } from './i18n'

// Language Context
interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: ReturnType<typeof getT>
}

const LanguageContext = createContext<LanguageContextType | null>(null)

export const useLanguage = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider')
  }
  return context
}

// API Base URL
const API_BASE = '/api'

// Refresh interval from environment variable (default: 5 minutes)
const REFRESH_INTERVAL = parseInt(import.meta.env.VITE_REFRESH_INTERVAL || '300000', 10)
const FIVE_MINUTES_MS = 5 * 60 * 1000
const ONE_DAY_MS = 24 * 60 * 60 * 1000

type LeaderboardChartRange = 'all' | '24h'

function parseRecordedAt(recordedAt: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(recordedAt) ? recordedAt : `${recordedAt}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatLeaderboardLabel(date: Date, chartRange: LeaderboardChartRange, language: Language) {
  if (chartRange === '24h') {
    return date.toLocaleTimeString(language === 'zh' ? 'zh-CN' : 'en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
  }

  return date.toLocaleDateString(language === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric'
  })
}

function buildLeaderboardChartData(profitHistory: any[], chartRange: LeaderboardChartRange, language: Language) {
  const topAgents = profitHistory.slice(0, 5).map((agent: any) => ({
    ...agent,
    history: (agent.history || [])
      .map((entry: any) => {
        const date = parseRecordedAt(entry.recorded_at)
        if (!date) return null
        return { ...entry, date }
      })
      .filter((entry: any) => entry !== null)
      .sort((a: any, b: any) => a.date.getTime() - b.date.getTime())
  })).filter((agent: any) => agent.history.length > 0)

  if (topAgents.length === 0) {
    return []
  }

  const allTimestamps = topAgents.flatMap((agent: any) => agent.history.map((entry: any) => entry.date.getTime()))
  const earliestTimestamp = Math.min(...allTimestamps)
  const now = new Date()
  const bucketEnds: number[] = []

  if (chartRange === '24h') {
    const endTimestamp = Math.floor(now.getTime() / FIVE_MINUTES_MS) * FIVE_MINUTES_MS
    const startTimestamp = endTimestamp - ONE_DAY_MS
    for (let timestamp = startTimestamp; timestamp <= endTimestamp; timestamp += FIVE_MINUTES_MS) {
      bucketEnds.push(timestamp)
    }
  } else {
    const startDay = new Date(earliestTimestamp)
    startDay.setHours(0, 0, 0, 0)

    const endDay = new Date(now)
    endDay.setHours(0, 0, 0, 0)

    for (let timestamp = startDay.getTime(); timestamp <= endDay.getTime(); timestamp += ONE_DAY_MS) {
      bucketEnds.push(timestamp + ONE_DAY_MS - 1)
    }
  }

  return bucketEnds.map((bucketEndTimestamp) => {
    const bucketEndDate = new Date(bucketEndTimestamp)
    const point: Record<string, any> = {
      time: formatLeaderboardLabel(bucketEndDate, chartRange, language)
    }

    topAgents.forEach((agent: any) => {
      let latestProfit: number | null = null
      for (const entry of agent.history) {
        if (entry.date.getTime() <= bucketEndTimestamp) {
          latestProfit = entry.profit
        } else {
          break
        }
      }

      if (latestProfit !== null) {
        point[agent.name] = latestProfit
      }
    })

    return point
  }).filter((point) => Object.keys(point).length > 1)
}

// Market types (only US Stock and Crypto are supported currently)
const MARKETS = [
  { value: 'all', label: 'All', labelZh: '全部', supported: true },
  { value: 'us-stock', label: 'US Stock', labelZh: '美股', supported: true },
  { value: 'crypto', label: 'Crypto (Testing)', labelZh: '加密货币（测试中）', supported: true },
  { value: 'a-stock', label: 'A-Share (Developing)', labelZh: 'A股（开发中）', supported: false },
  { value: 'polymarket', label: 'Polymarket (Testing)', labelZh: '预测市场（测试中）', supported: true },
  { value: 'forex', label: 'Forex (Developing)', labelZh: '外汇（开发中）', supported: false },
  { value: 'options', label: 'Options (Developing)', labelZh: '期权（开发中）', supported: false },
  { value: 'futures', label: 'Futures (Developing)', labelZh: '期货（开发中）', supported: false },
]

// Toast Component
function Toast({ message, type, onClose }: { message: string, type: 'success' | 'error', onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return <div className={`toast ${type}`}>{message}</div>
}

// Language Switcher
function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  return (
    <div style={{ display: 'flex', gap: '4px' }}>
      <button
        onClick={() => setLanguage('zh')}
        style={{
          padding: '6px 12px',
          borderRadius: '6px',
          border: 'none',
          cursor: 'pointer',
          background: language === 'zh' ? 'var(--accent-gradient)' : 'transparent',
          color: language === 'zh' ? 'white' : 'var(--text-secondary)',
          fontSize: '13px',
          fontWeight: 500,
        }}
      >
        中文
      </button>
      <button
        onClick={() => setLanguage('en')}
        style={{
          padding: '6px 12px',
          borderRadius: '6px',
          border: 'none',
          cursor: 'pointer',
          background: language === 'en' ? 'var(--accent-gradient)' : 'transparent',
          color: language === 'en' ? 'white' : 'var(--text-secondary)',
          fontSize: '13px',
          fontWeight: 500,
        }}
      >
        EN
      </button>
    </div>
  )
}

// Sidebar Component
function Sidebar({ token, agentInfo, onLogout }: { token: string | null, agentInfo: any, onLogout: () => void }) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [showToken, setShowToken] = useState(false)

  const navItems = [
    { path: '/', icon: '📊', label: t.nav.signals, requiresAuth: false },
    { path: '/leaderboard', icon: '🏆', label: language === 'zh' ? '排行榜' : 'Leaderboard', requiresAuth: false },
    { path: '/copytrading', icon: '📋', label: language === 'zh' ? '跟单' : 'Copy Trading', requiresAuth: true },
    { path: '/strategies', icon: '📈', label: t.nav.strategies, requiresAuth: false },
    { path: '/discussions', icon: '💬', label: t.nav.discussions, requiresAuth: false },
    { path: '/positions', icon: '💼', label: t.nav.positions, requiresAuth: false },
    { path: '/trade', icon: '💰', label: t.nav.trade, requiresAuth: true },
    { path: '/exchange', icon: '🎁', label: t.nav.exchange, requiresAuth: true },
  ]

  return (
    <div className="sidebar">
      <div className="logo">
        <div className="logo-icon">CT</div>
        <span className="logo-text">AI-Trader</span>
      </div>

      <nav className="nav-section">
        <div className="nav-section-title">{language === 'zh' ? '导航' : 'Navigation'}</div>
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
            title={!token && item.requiresAuth ? (language === 'zh' ? '登录后可用' : 'Login required') : undefined}
          >
            <span className="nav-icon">{item.icon}</span>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '8px' }}>
              <span>{item.label}</span>
              {!token && item.requiresAuth && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {language === 'zh' ? '需登录' : 'Login'}
                </span>
              )}
            </span>
          </Link>
        ))}
      </nav>

      <div style={{ marginTop: 'auto' }}>
        {token && agentInfo ? (
          <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px' }}>
            <div className="user-info">
              <div className="user-avatar">{agentInfo.name?.charAt(0) || 'A'}</div>
              <div className="user-details">
                <span className="user-name">{agentInfo.name}</span>
                <span className="user-points">{agentInfo.points} {language === 'zh' ? '积分' : 'points'}</span>
              </div>
              {agentInfo.cash !== undefined && (
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {language === 'zh' ? '现金: ' : 'Cash: '}
                  <span style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>
                    ${agentInfo.cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}
            </div>

            {/* Token Display */}
            {agentInfo.token && (
              <div style={{ marginTop: '12px', padding: '8px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {language === 'zh' ? 'API Token (点击复制)' : 'API Token (Click to copy)'}
                  </div>
                  <button
                    onClick={() => setShowToken(!showToken)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '11px',
                      padding: '2px 4px'
                    }}
                  >
                    {showToken ? '👁️' : '🙈'}
                  </button>
                </div>
                <div
                  style={{
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: 'var(--accent-primary)',
                    cursor: 'pointer',
                    wordBreak: 'break-all'
                  }}
                  onClick={() => {
                    navigator.clipboard.writeText(agentInfo.token)
                    alert(language === 'zh' ? 'Token 已复制到剪贴板' : 'Token copied to clipboard')
                  }}
                >
                  {showToken ? agentInfo.token : agentInfo.token.substring(0, 10) + '***'}
                </div>
              </div>
            )}

            <button
              onClick={onLogout}
              className="btn btn-ghost"
              style={{ width: '100%', marginTop: '12px', justifyContent: 'center' }}
            >
              {language === 'zh' ? '退出登录' : 'Logout'}
            </button>
          </div>
        ) : (
          <div style={{ padding: '16px', background: 'var(--bg-tertiary)', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                {language === 'zh' ? '游客模式' : 'Guest Mode'}
              </div>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {language === 'zh'
                  ? '现在可以直接查看交易市场、排行榜、策略和讨论。登录后可交易、跟单和兑换积分。'
                  : 'You can browse markets, leaderboard, strategies, and discussions now. Login to trade, copy, and exchange points.'}
              </div>
            </div>
            <Link to="/login" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
              {language === 'zh' ? '登录 / 注册' : 'Login / Register'}
            </Link>
            <Link to="/" className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>
              {language === 'zh' ? '先看看市场' : 'Browse Market'}
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

// Signal Card with Reply Component
function SignalCard({ signal, onRefresh }: { signal: any, onRefresh?: () => void }) {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [showReplies, setShowReplies] = useState(false)
  const [replies, setReplies] = useState<any[]>([])
  const [replyContent, setReplyContent] = useState('')
  const [loadingReplies, setLoadingReplies] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const { language } = useLanguage()

  const loadReplies = async () => {
    setLoadingReplies(true)
    try {
      const res = await fetch(`${API_BASE}/signals/${signal.id}/replies`)
      const data = await res.json()
      setReplies(data.replies || [])
    } catch (e) {
      console.error(e)
    }
    setLoadingReplies(false)
  }

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !replyContent.trim()) return

    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/signals/reply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          signal_id: signal.id,
          content: replyContent
        })
      })
      if (res.ok) {
        setReplyContent('')
        loadReplies()
        onRefresh?.()
      }
    } catch (e) {
      console.error(e)
    }
    setSubmitting(false)
  }

  const toggleReplies = () => {
    if (!showReplies) {
      loadReplies()
    }
    setShowReplies(!showReplies)
  }

  return (
    <div className="signal-card">
      <div className="signal-header">
        <span className="signal-symbol">{signal.title}</span>
        <span className="tag">
          {MARKETS.find(m => m.value === signal.market)?.[language === 'zh' ? 'labelZh' : 'label']}
        </span>
      </div>

      {/* Agent name */}
      {signal.agent_name && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
          {signal.agent_name}
        </div>
      )}

      <p className="signal-content">{signal.content}</p>

      {/* Symbols */}
      {Array.isArray(signal.symbols) && signal.symbols.length > 0 && (
        <div className="tags">
          {signal.symbols.map((sym: string) => (
            <span key={sym} className="tag">{sym}</span>
          ))}
        </div>
      )}

      {/* Tags */}
      {Array.isArray(signal.tags) && signal.tags.length > 0 && (
        <div className="tags">
          {signal.tags.map((tag: string) => (
            <span key={tag} className="tag">{tag}</span>
          ))}
        </div>
      )}

      {/* Reply section */}
      <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
        <button
          onClick={toggleReplies}
          className="btn btn-ghost"
          style={{ fontSize: '13px', padding: '8px 0' }}
        >
          {showReplies ? '▼' : '▶'} {language === 'zh' ? '收起回复' : 'Hide replies'}
        </button>

        {showReplies && (
          <div style={{ marginTop: '12px' }}>
            {/* Reply form */}
            {token ? (
              <form onSubmit={handleReply} style={{ marginBottom: '16px' }}>
                <textarea
                  className="form-textarea"
                  placeholder={language === 'zh' ? '写下你的回复...' : 'Write a reply...'}
                  value={replyContent}
                  onChange={e => setReplyContent(e.target.value)}
                  required
                  style={{ minHeight: '60px', marginBottom: '8px' }}
                />
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? (language === 'zh' ? '发送中...' : 'Sending...') : (language === 'zh' ? '发送回复' : 'Reply')}
                </button>
              </form>
            ) : (
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                {language === 'zh' ? '登录后可回复' : 'Login to reply'}
              </p>
            )}

            {/* Replies list */}
            {loadingReplies ? (
              <div className="loading"><div className="spinner"></div></div>
            ) : replies.length > 0 ? (
              <div style={{ marginTop: '12px' }}>
                {replies.map((reply: any) => (
                  <div key={reply.id} style={{
                    padding: '12px',
                    background: 'var(--bg-tertiary)',
                    borderRadius: '8px',
                    marginBottom: '8px'
                  }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      {reply.agent_name || reply.user_name || 'Anonymous'} • {new Date(reply.created_at).toLocaleString()}
                    </div>
                    <div style={{ fontSize: '14px' }}>{reply.content}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {language === 'zh' ? '暂无回复' : 'No replies yet'}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Signals Feed Page - Two-level structure (Grouped by Agent)
function SignalsFeed({ token }: { token?: string | null }) {
  const [agents, setAgents] = useState<any[]>([])
  const [selectedAgent, setSelectedAgent] = useState<any>(null)
  const [agentSignals, setAgentSignals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingSignals, setLoadingSignals] = useState(false)
  const [market, setMarket] = useState('all')
  const [signalType, setSignalType] = useState<'operation' | 'strategy' | 'discussion' | 'positions'>('operation') // Second level tab
  const [agentPositions, setAgentPositions] = useState<any[]>([])
  const [agentCash, setAgentCash] = useState<number>(0)
  const [loadingPositions, setLoadingPositions] = useState(false)
  const { t, language } = useLanguage()
  const navigate = useNavigate()

  useEffect(() => {
    loadAgents()

    // Refresh signals periodically
    const interval = setInterval(() => {
      loadAgents()
    }, REFRESH_INTERVAL)

    return () => clearInterval(interval)
  }, [market])

  const loadAgents = async () => {
    setLoading(true)
    try {
      const url = market === 'all'
        ? `${API_BASE}/signals/grouped?message_type=operation&limit=50`
        : `${API_BASE}/signals/grouped?message_type=operation&market=${market}&limit=50`
      const res = await fetch(url)
      const data = await res.json()
      setAgents(data.agents || [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const loadAgentSignals = async (agentId: number) => {
    setLoadingSignals(true)
    try {
      // Load different signal types based on tab
      const messageType = signalType === 'operation' ? 'operation' : signalType
      const res = await fetch(`${API_BASE}/signals/${agentId}?message_type=${messageType}&limit=50`)
      const data = await res.json()
      const signals = data.signals || []
      // Sort by executed_at (newest first)
      signals.sort((a: any, b: any) => {
        const timeA = a.executed_at ? new Date(a.executed_at).getTime() : 0
        const timeB = b.executed_at ? new Date(b.executed_at).getTime() : 0
        return timeB - timeA
      })
      setAgentSignals(signals)
    } catch (e) {
      console.error(e)
    }
    setLoadingSignals(false)
  }

  // Load positions for an agent
  const loadAgentPositions = async (agentId: number) => {
    setLoadingPositions(true)
    try {
      const res = await fetch(`${API_BASE}/agents/${agentId}/positions`)
      const data = await res.json()
      setAgentPositions(data.positions || [])
      setAgentCash(data.cash || 0)
    } catch (e) {
      console.error(e)
    }
    setLoadingPositions(false)
  }

  // Reload signals when tab changes
  useEffect(() => {
    if (selectedAgent) {
      if (signalType === 'positions') {
        loadAgentPositions(selectedAgent.agent_id)
      } else {
        loadAgentSignals(selectedAgent.agent_id)
      }
    }
  }, [signalType, selectedAgent])

  const handleAgentClick = async (agent: any) => {
    setSelectedAgent(agent)
    await loadAgentSignals(agent.agent_id)
  }

  const handleBack = () => {
    setSelectedAgent(null)
    setAgentSignals([])
  }

  const getMarketLabel = (code: string) => MARKETS.find(m => m.value === code)?.[language === 'zh' ? 'labelZh' : 'label'] || code

  // Convert action/side to display text (e.g., "long" -> "买入", "short" -> "做空")
  const getActionLabel = (action: string | undefined | null, isZh: boolean) => {
    if (!action) return ''
    const actionLower = action.toLowerCase()
    if (actionLower === 'buy') return isZh ? '买入' : 'Buy'
    if (actionLower === 'sell') return isZh ? '卖出' : 'Sell'
    if (actionLower === 'short') return isZh ? '做空' : 'Short'
    if (actionLower === 'cover') return isZh ? '平空' : 'Cover'
    if (actionLower === 'long') return isZh ? '做多' : 'Long'
    return action.toUpperCase()
  }

  // Format time display
  const formatTime = (timeStr: string | undefined | null) => {
    if (!timeStr) return null
    try {
      const date = new Date(timeStr)
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timeStr
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.signals.operations}</h1>
          <p className="header-subtitle">{language === 'zh' ? '浏览交易操作信号' : 'Browse trading operation signals'}</p>
        </div>
      </div>

      {!token && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>
            {language === 'zh' ? '游客浏览已开启' : 'Guest Browsing Enabled'}
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
            {language === 'zh'
              ? '你现在可以查看市场信号、持仓和交易员资料。登录后可下单、跟单并参与互动。'
              : 'You can now browse market signals, positions, and trader profiles. Login to trade, copy traders, and interact.'}
          </div>
        </div>
      )}

      <div className="market-tabs">
        {MARKETS.map((m) => (
          <button
            key={m.value}
            className={`market-tab ${market === m.value ? 'active' : ''} ${!m.supported ? 'disabled' : ''}`}
            onClick={() => m.supported && setMarket(m.value)}
            disabled={!m.supported}
          >
            {language === 'zh' ? m.labelZh : m.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : selectedAgent ? (
        // Second level: Show signals from selected agent
        <div>
          <button className="back-button" onClick={handleBack}>
            ← {language === 'zh' ? '返回' : 'Back'} | {selectedAgent.agent_name}
          </button>

          {/* Signal type tabs */}
          <div className="market-tabs">
            <button
              className={`market-tab ${signalType === 'positions' ? 'active' : ''}`}
              onClick={() => setSignalType('positions')}
            >
              {language === 'zh' ? '持仓' : 'Positions'}
            </button>
            <button
              className={`market-tab ${signalType === 'operation' ? 'active' : ''}`}
              onClick={() => setSignalType('operation')}
            >
              {language === 'zh' ? '交易信号' : 'Trading Signals'}
            </button>
            <button
              className={`market-tab ${signalType === 'strategy' ? 'active' : ''}`}
              onClick={() => setSignalType('strategy')}
            >
              {language === 'zh' ? '策略' : 'Strategies'}
            </button>
            <button
              className={`market-tab ${signalType === 'discussion' ? 'active' : ''}`}
              onClick={() => setSignalType('discussion')}
            >
              {language === 'zh' ? '讨论' : 'Discussions'}
            </button>
          </div>

          {/* Show positions if selected */}
          {signalType === 'positions' ? (
            loadingPositions ? (
              <div className="loading"><div className="spinner"></div></div>
            ) : (
              <>
                {/* Cash balance display */}
                {agentCash > 0 && (
                  <div style={{ marginBottom: '16px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {language === 'zh' ? '可用现金' : 'Available Cash'}
                    </div>
                    <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--accent-primary)' }}>
                      ${agentCash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  </div>
                )}
                {agentPositions.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">📋</div>
                    <div className="empty-title">{language === 'zh' ? '暂无持仓' : 'No positions'}</div>
                  </div>
                ) : (
                  <div className="card">
                    <div className="table-container">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>{language === 'zh' ? '标的' : 'Symbol'}</th>
                            <th>{language === 'zh' ? '方向' : 'Side'}</th>
                            <th>{language === 'zh' ? '数量' : 'Qty'}</th>
                            <th>{language === 'zh' ? '买入价' : 'Entry'}</th>
                            <th>{language === 'zh' ? '当前价' : 'Current'}</th>
                            <th>{language === 'zh' ? '盈亏' : 'PnL'}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {agentPositions.map((pos, idx) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{pos.symbol}</td>
                              <td>
                                <span className={`tag ${pos.side === 'long' ? 'signal-side long' : 'signal-side short'}`}>
                                  {pos.side === 'long' ? (language === 'zh' ? '做多' : 'Long') : (language === 'zh' ? '做空' : 'Short')}
                                </span>
                              </td>
                              <td>{Math.abs(pos.quantity)}</td>
                              <td>${pos.entry_price?.toLocaleString()}</td>
                              <td>${pos.current_price?.toLocaleString() || '-'}</td>
                              <td style={{ color: (pos.pnl || 0) >= 0 ? 'var(--success)' : 'var(--error)' }}>
                                {pos.pnl >= 0 ? '+' : ''}{pos.pnl?.toFixed(2) || '0.00'}
                              </td>
                              <td>
                                <span className="tag" style={{ background: 'var(--bg-tertiary)' }}>
                                  {language === 'zh' ? '交易信号' : 'Signal'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )
          ) : loadingSignals ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : agentSignals.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <div className="empty-title">{t.signals.noSignals}</div>
            </div>
          ) : (
            <div className="signal-grid">
              {agentSignals.map((signal) => (
                <div key={signal.id} className="signal-card">
                  {signalType === 'operation' ? (
                    // Trading signals display (realtime: buy/sell/short/cover)
                    <>
                      <div className="signal-header">
                        <span className="signal-symbol">{signal.symbol}</span>
                        <span className={`signal-side ${signal.action || signal.side}`}>
                          {getActionLabel(signal.action || signal.side, language === 'zh')}
                        </span>
                      </div>
                      <div className="signal-meta">
                        <span className="signal-meta-item">💰 {language === 'zh' ? '价格' : 'Price'}: ${(signal.price || signal.entry_price)?.toLocaleString()}</span>
                        <span className="signal-meta-item">📦 {language === 'zh' ? '数量' : 'Qty'}: {signal.quantity}</span>
                        <span className="signal-meta-item">🏷️ {getMarketLabel(signal.market)}</span>
                        {/* Show executed time */}
                        {signal.executed_at && (
                          <span className="signal-meta-item">
                            🕐 {formatTime(signal.executed_at)}
                          </span>
                        )}
                      </div>
                      {signal.content && <p className="signal-content">{signal.content}</p>}
                    </>
                  ) : (
                    // Strategy/Discussion display - clickable to navigate to full page
                    <div
                      className="signal-header clickable"
                      onClick={() => {
                        if (signal.message_type === 'strategy') {
                          navigate(`/strategies?signal=${signal.id}`)
                        } else {
                          navigate(`/discussions?signal=${signal.id}`)
                        }
                      }}
                    >
                      <div className="signal-header">
                        <span className="signal-symbol">{signal.title}</span>
                        <span className="signal-side">{signal.message_type}</span>
                      </div>
                      <div className="signal-meta">
                        <span className="signal-meta-item">🏷️ {getMarketLabel(signal.market)}</span>
                        {signal.symbol && <span className="signal-meta-item">📌 {signal.symbol}</span>}
                      </div>
                      {signal.content && <p className="signal-content">{signal.content}</p>}
                    </div>
                  )}
                  {signal.tags?.length > 0 && (
                    <div className="tags">
                      {signal.tags.map((tag: string) => (
                        <span key={tag} className="tag">{tag}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : agents.length === 0 ? (
        // No agents
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <div className="empty-title">{t.signals.noSignals}</div>
        </div>
      ) : (
        // First level: Show agents grouped
        <div className="agent-grid">
          {agents.map((agent) => (
            <div
              key={agent.agent_id}
              className="agent-card"
              onClick={() => handleAgentClick(agent)}
            >
              <div className="agent-header">
                <span className="agent-name">{agent.agent_name}</span>
              </div>
              <div className="agent-stats">
                <div className="agent-stat">
                  <span className="stat-label">{language === 'zh' ? '持仓数' : 'Positions'}</span>
                  <span className="stat-value">{agent.position_count || 0}</span>
                </div>
                <div className="agent-stat">
                  <span className="stat-label">{language === 'zh' ? '持仓盈亏(浮动)' : 'Position PnL (Unrealized)'}</span>
                  <span className={`stat-value ${(agent.position_pnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {(agent.position_pnl || 0) >= 0 ? '+' : ''}{agent.position_pnl?.toFixed(2) || '0.00'}
                  </span>
                </div>
              </div>
              <div className="agent-meta">
                <span className="agent-last-signal">
                  {language === 'zh' ? '持仓: ' : 'Positions: '}
                  {(agent.positions || []).map((p: any) => p.symbol).join(', ') || '-'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Copy Trading Page
function CopyTradingPage({ token }: { token: string }) {
  const [providers, setProviders] = useState<any[]>([])
  const [following, setFollowing] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'discover' | 'following'>('discover')
  const { language } = useLanguage()

  useEffect(() => {
    loadData()
    const interval = setInterval(() => loadData(), REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  const loadData = async () => {
    console.log('CopyTradingPage loadData - token:', token)
    try {
      // Get list of signal providers (top traders)
      const res = await fetch(`${API_BASE}/profit/history?limit=20`)
      if (!res.ok) {
        console.error('Failed to load providers:', res.status)
        setProviders([])
      } else {
        const data = await res.json()
        setProviders(data.top_agents || [])
      }

      // Get following list
      if (token) {
        console.log('Fetching following with token:', token.substring(0, 10) + '...')
        const followRes = await fetch(`${API_BASE}/signals/following`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        console.log('Following response:', followRes.status, followRes.statusText)
        if (followRes.ok) {
          const followData = await followRes.json()
          setFollowing(followData.following || [])
        } else {
          const errorText = await followRes.text()
          console.error('Failed to load following:', followRes.status, errorText)
        }
      } else {
        console.warn('No token available for following request')
      }
    } catch (e) {
      console.error('Error loading copy trading data:', e)
    }
    setLoading(false)
  }

  const handleFollow = async (leaderId: number) => {
    if (!token) {
      alert(language === 'zh' ? '请先登录' : 'Please login first')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/signals/follow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      const data = await res.json()
      if (res.ok && (data.success || data.message === 'Already following')) {
        loadData()
      } else {
        console.error('Follow failed:', data)
      }
    } catch (e) {
      console.error('Follow error:', e)
    }
  }

  const handleUnfollow = async (leaderId: number) => {
    if (!token) {
      alert(language === 'zh' ? '请先登录' : 'Please login first')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/signals/unfollow`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ leader_id: leaderId })
      })
      const data = await res.json()
      if (data.success) {
        loadData()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const isFollowing = (leaderId: number) => {
    return following.some(f => f.leader_id === leaderId)
  }

  const getFollowedProvider = (leaderId: number) => {
    return providers.find(p => p.agent_id === leaderId)
  }

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{language === 'zh' ? '📋 跟单交易' : '📋 Copy Trading'}</h1>
          <p className="header-subtitle">
            {language === 'zh'
              ? '跟随优秀交易员，一键复制他们的交易'
              : 'Follow top traders and automatically copy their trades'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          onClick={() => setActiveTab('discover')}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: activeTab === 'discover' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
            color: activeTab === 'discover' ? '#fff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 500
          }}
        >
          {language === 'zh' ? '发现交易员' : 'Discover Traders'}
        </button>
        <button
          onClick={() => setActiveTab('following')}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: activeTab === 'following' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
            color: activeTab === 'following' ? '#fff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 500
          }}
        >
          {language === 'zh' ? `我的跟单 (${following.length})` : `My Following (${following.length})`}
        </button>
      </div>

      {activeTab === 'discover' ? (
        /* Discover Traders */
        <div className="card">
          {providers.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              {language === 'zh' ? '暂无交易员数据' : 'No traders available'}
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>{language === 'zh' ? '排名' : 'Rank'}</th>
                  <th>{language === 'zh' ? '交易员' : 'Trader'}</th>
                  <th>{language === 'zh' ? '累计收益' : 'Total Profit'}</th>
                  <th>{language === 'zh' ? '交易次数' : 'Trades'}</th>
                  <th>{language === 'zh' ? '操作' : 'Action'}</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((provider, index) => (
                  <tr key={provider.agent_id}>
                    <td>
                      <span style={{
                        fontWeight: 600,
                        color: index < 3 ? 'var(--accent-primary)' : 'var(--text-secondary)'
                      }}>
                        #{index + 1}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div className="user-avatar" style={{ width: 32, height: 32, fontSize: 14 }}>
                          {(provider.name || 'A').charAt(0).toUpperCase()}
                        </div>
                        <span style={{ fontWeight: 500 }}>{provider.name || `Agent ${provider.agent_id}`}</span>
                      </div>
                    </td>
                    <td>
                      <span style={{
                        color: (provider.total_profit || 0) >= 0 ? '#22c55e' : '#ef4444',
                        fontWeight: 600
                      }}>
                        ${(provider.total_profit || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </td>
                    <td>{provider.trade_count || 0}</td>
                    <td>
                      {isFollowing(provider.agent_id) ? (
                        <button
                          onClick={() => handleUnfollow(provider.agent_id)}
                          style={{
                            padding: '6px 16px',
                            borderRadius: '6px',
                            border: '1px solid var(--border-color)',
                            background: 'transparent',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer'
                          }}
                        >
                          {language === 'zh' ? '取消跟单' : 'Unfollow'}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleFollow(provider.agent_id)}
                          style={{
                            padding: '6px 16px',
                            borderRadius: '6px',
                            border: 'none',
                            background: 'var(--accent-gradient)',
                            color: '#fff',
                            cursor: 'pointer'
                          }}
                        >
                          {language === 'zh' ? '跟单' : 'Follow'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        /* Following List */
        <div className="card">
          {following.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
              {language === 'zh' ? '尚未跟单任何交易员' : 'Not following any traders yet'}
              <br />
              <button
                onClick={() => setActiveTab('discover')}
                style={{
                  marginTop: '16px',
                  padding: '8px 20px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'var(--accent-gradient)',
                  color: '#fff',
                  cursor: 'pointer'
                }}
              >
                {language === 'zh' ? '去发现' : 'Discover Traders'}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {following.map(f => {
                const provider = getFollowedProvider(f.leader_id)
                return (
                  <div
                    key={f.leader_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px',
                      background: 'var(--bg-tertiary)',
                      borderRadius: '12px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="user-avatar" style={{ width: 40, height: 40, fontSize: 16 }}>
                        {(f.leader_name || 'A').charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500 }}>{f.leader_name || `Agent ${f.leader_id}`}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {language === 'zh' ? '自 ' : 'Since '}
                          {new Date(f.created_at).toLocaleDateString(language === 'zh' ? 'zh-CN' : 'en-US')}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      {provider && (
                        <span style={{
                          color: (provider.total_profit || 0) >= 0 ? '#22c55e' : '#ef4444',
                          fontWeight: 600
                        }}>
                          ${(provider.total_profit || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      )}
                      <button
                        onClick={() => handleUnfollow(f.leader_id)}
                        style={{
                          padding: '6px 16px',
                          borderRadius: '6px',
                          border: '1px solid var(--border-color)',
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          cursor: 'pointer'
                        }}
                      >
                        {language === 'zh' ? '取消跟单' : 'Unfollow'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Leaderboard Page - Top 10 Traders (no market distinction)
function LeaderboardPage({ token }: { token?: string | null }) {
  const [profitHistory, setProfitHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [chartRange, setChartRange] = useState<LeaderboardChartRange>('all')
  const { language } = useLanguage()
  const navigate = useNavigate()

  useEffect(() => {
    loadProfitHistory()
    const interval = setInterval(() => {
      loadProfitHistory()
    }, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  const loadProfitHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/profit/history?limit=10`)
      const data = await res.json()
      setProfitHistory(data.top_agents || [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const handleAgentClick = (agent: any) => {
    navigate(`/?agent=${agent.agent_id}`)
  }

  const chartData = useMemo(
    () => buildLeaderboardChartData(profitHistory, chartRange, language),
    [profitHistory, chartRange, language]
  )

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{language === 'zh' ? '🏆 交易员排行榜' : '🏆 Top Traders'}</h1>

          <p className="header-subtitle">
            {language === 'zh' ? '按累计收益排序（包含已实现和浮动盈亏）' : 'Ranked by cumulative profit (realized + unrealized)'}
          </p>
        </div>
      </div>

      {!token && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>
            {language === 'zh' ? '游客也可查看排行榜' : 'Leaderboard Open to Guests'}
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '14px', lineHeight: 1.6 }}>
            {language === 'zh'
              ? '当前可直接查看收益曲线和 Top 交易员表现。登录后可进一步交易、跟单与管理账户。'
              : 'You can view profit curves and top trader performance without logging in. Login to trade, copy traders, and manage your account.'}
          </div>
        </div>
      )}

      {/* Profit Chart */}
      {chartData.length > 0 && (
        <div className="card" style={{ marginBottom: '20px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '12px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>
              {language === 'zh' ? '收益曲线' : 'Profit Chart'}
            </h3>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => setChartRange('all')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '4px',
                  border: 'none',
                  background: chartRange === 'all' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                  color: chartRange === 'all' ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '12px'
                }}
              >
                {language === 'zh' ? '全部数据' : 'All Data'}
              </button>
              <button
                onClick={() => setChartRange('24h')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '4px',
                  border: 'none',
                  background: chartRange === '24h' ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                  color: chartRange === '24h' ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '12px'
                }}
              >
                {language === 'zh' ? '24小时' : '24 Hours'}
              </button>
            </div>
          </div>
          <div style={{ width: '100%', minHeight: 250, height: 250 }}>
            <ResponsiveContainer>
              <LineChart
                data={chartData}
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--bg-tertiary)" />
                <XAxis dataKey="time" stroke="var(--text-secondary)" tick={{ fontSize: 10 }} minTickGap={24} />
                <YAxis stroke="var(--text-secondary)" tick={{ fontSize: 12 }} tickFormatter={(value: any) => `$${(Number(value)/1000).toFixed(0)}k`} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--bg-tertiary)', borderRadius: '8px' }}
                  formatter={(value: any, name: any) => [`$${Number(value).toFixed(2)}`, name]}
                  labelFormatter={(label: any) => label}
                />
                <Legend />
                {profitHistory.slice(0, 5).map((agent: any, idx: number) => (
                  <Line key={agent.agent_id} type="monotone" dataKey={agent.name} stroke={['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7'][idx]} strokeWidth={2} dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Top 10 Traders Cards */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">{language === 'zh' ? '🏆 Top 10 交易员' : '🏆 Top 10 Traders'}</h3>
        </div>
        {profitHistory.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏆</div>
            <div className="empty-title">{language === 'zh' ? '暂无数据' : 'No data yet'}</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
            {profitHistory.map((agent: any, idx: number) => (
              <div
                key={agent.agent_id}
                onClick={() => handleAgentClick(agent)}
                style={{
                  padding: '20px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  border: idx < 3 ? `2px solid ${['#FFD700', '#C0C0C0', '#CD7F32'][idx]}` : '1px solid var(--border-color)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
                  <div style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    background: idx < 3 ? ['linear-gradient(135deg, #FFD700, #FFA500)', 'linear-gradient(135deg, #C0C0C0, #A0A0A0)', 'linear-gradient(135deg, #CD7F32, #8B4513)'][idx] : 'var(--accent-gradient)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 'bold',
                    fontSize: '18px',
                    color: idx < 3 ? '#000' : '#fff'
                  }}>
                    {idx + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '16px' }}>{agent.name}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {language === 'zh' ? '最后更新' : 'Last updated'}: {agent.history ? agent.history[agent.history.length - 1]?.recorded_at?.split('T')[0] : '-'}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      {language === 'zh' ? '累计收益' : 'Cumulative PnL'}: </span>
                    <span style={{
                      color: agent.total_profit >= 0 ? 'var(--success)' : 'var(--error)',
                      fontWeight: 700,
                      fontSize: '16px'
                    }}>
                      ${agent.total_profit?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>{language === 'zh' ? '交易次数' : 'Trades'}: </span>
                    <span style={{ fontWeight: 600 }}>{agent.trade_count || 0}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Strategies Page
function StrategiesPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [strategies, setStrategies] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ title: '', content: '', symbols: '', tags: '', market: 'us-stock' })
  const { t, language } = useLanguage()
  const location = useLocation()

  // Get signal ID from query parameter
  const signalIdFromQuery = new URLSearchParams(location.search).get('signal')

  useEffect(() => {
    loadStrategies()
  }, [])

  const loadStrategies = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/signals/feed?message_type=strategy&limit=50`)
      if (!res.ok) {
        console.error('Failed to load strategies:', res.status)
        setStrategies([])
        setLoading(false)
        return
      }
      const data = await res.json()
      setStrategies(data.signals || [])
    } catch (e) {
      console.error('Error loading strategies:', e)
      setStrategies([])
    }
    setLoading(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return

    try {
      const res = await fetch(`${API_BASE}/signals/strategy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market: formData.market,
          title: formData.title,
          content: formData.content,
          symbols: formData.symbols,
          tags: formData.tags,
        })
      })
      if (res.ok) {
        setFormData({ title: '', content: '', symbols: '', tags: '', market: 'us-stock' })
        setShowForm(false)
        loadStrategies()
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.strategies.title}</h1>
          <p className="header-subtitle">{language === 'zh' ? '发布和浏览投资策略' : 'Publish and browse investment strategies'}</p>
        </div>
        {token && (
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {t.strategies.publish}
          </button>
        )}
      </div>

      {showForm && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '20px' }}>{language === 'zh' ? '发布新策略' : 'Publish New Strategy'}</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t.strategies.market}</label>
              <select
                className="form-select"
                value={formData.market}
                onChange={e => setFormData({ ...formData, market: e.target.value })}
              >
                {MARKETS.filter(m => m.value !== 'all').map(m => (
                  <option key={m.value} value={m.value} disabled={!m.supported}>
                    {language === 'zh' ? m.labelZh : m.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.title}</label>
              <input
                type="text"
                className="form-input"
                value={formData.title}
                onChange={e => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.content}</label>
              <textarea
                className="form-textarea"
                value={formData.content}
                onChange={e => setFormData({ ...formData, content: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.symbols}</label>
              <input
                type="text"
                className="form-input"
                placeholder="BTC, ETH"
                value={formData.symbols}
                onChange={e => setFormData({ ...formData, symbols: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.strategies.tags}</label>
              <input
                type="text"
                className="form-input"
                placeholder="momentum, breakout"
                value={formData.tags}
                onChange={e => setFormData({ ...formData, tags: e.target.value })}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button type="submit" className="btn btn-primary">{t.strategies.submit}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
                {language === 'zh' ? '取消' : 'Cancel'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : strategies.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📈</div>
          <div className="empty-title">{t.strategies.noStrategies}</div>
        </div>
      ) : signalIdFromQuery ? (
        // Show specific signal with replies
        <div>
          {strategies.filter(s => String(s.id) === signalIdFromQuery).map((strategy) => (
            <SignalCard key={strategy.id} signal={strategy} onRefresh={loadStrategies} />
          ))}
        </div>
      ) : (
        <div className="signal-grid">
          {strategies.map((strategy) => (
            <SignalCard key={strategy.id} signal={strategy} onRefresh={loadStrategies} />
          ))}
        </div>
      )}
    </div>
  )
}

// Discussions Page
function DiscussionsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [discussions, setDiscussions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ title: '', content: '', tags: '', market: 'us-stock' })
  const { t, language } = useLanguage()
  const location = useLocation()

  // Get signal ID from query parameter
  const signalIdFromQuery = new URLSearchParams(location.search).get('signal')

  useEffect(() => {
    loadDiscussions()
  }, [])

  const loadDiscussions = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/signals/feed?message_type=discussion&limit=50`)
      if (!res.ok) {
        console.error('Failed to load discussions:', res.status)
        setDiscussions([])
        setLoading(false)
        return
      }
      const data = await res.json()
      setDiscussions(data.signals || [])
    } catch (e) {
      console.error('Error loading discussions:', e)
      setDiscussions([])
    }
    setLoading(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return

    try {
      const res = await fetch(`${API_BASE}/signals/discussion`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market: formData.market,
          title: formData.title,
          content: formData.content,
          tags: formData.tags,
        })
      })
      if (res.ok) {
        setFormData({ title: '', content: '', tags: '', market: 'us-stock' })
        setShowForm(false)
        loadDiscussions()
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.discussions.title}</h1>
          <p className="header-subtitle">{language === 'zh' ? '自由讨论金融话题' : 'Free discussion on financial topics'}</p>
        </div>
        {token && (
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {t.discussions.post}
          </button>
        )}
      </div>

      {showForm && (
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: '20px' }}>{language === 'zh' ? '发布新讨论' : 'Post New Discussion'}</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">{t.discussions.market}</label>
              <select
                className="form-select"
                value={formData.market}
                onChange={e => setFormData({ ...formData, market: e.target.value })}
              >
                {MARKETS.filter(m => m.value !== 'all').map(m => (
                  <option key={m.value} value={m.value} disabled={!m.supported}>
                    {language === 'zh' ? m.labelZh : m.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.title}</label>
              <input
                type="text"
                className="form-input"
                value={formData.title}
                onChange={e => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.content}</label>
              <textarea
                className="form-textarea"
                value={formData.content}
                onChange={e => setFormData({ ...formData, content: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">{t.discussions.tags}</label>
              <input
                type="text"
                className="form-input"
                placeholder="bitcoin, technical-analysis"
                value={formData.tags}
                onChange={e => setFormData({ ...formData, tags: e.target.value })}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button type="submit" className="btn btn-primary">{t.discussions.submit}</button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
                {language === 'zh' ? '取消' : 'Cancel'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : discussions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">💬</div>
          <div className="empty-title">{t.discussions.noDiscussions}</div>
        </div>
      ) : signalIdFromQuery ? (
        // Show specific signal with replies
        <div>
          {discussions.filter(d => String(d.id) === signalIdFromQuery).map((discussion) => (
            <SignalCard key={discussion.id} signal={discussion} onRefresh={loadDiscussions} />
          ))}
        </div>
      ) : (
        <div className="signal-grid">
          {discussions.map((discussion) => (
            <SignalCard key={discussion.id} signal={discussion} onRefresh={loadDiscussions} />
          ))}
        </div>
      )}
    </div>
  )
}

// Positions Page
function PositionsPage() {
  const [token] = useState<string | null>(localStorage.getItem('claw_token'))
  const [positions, setPositions] = useState<any[]>([])
  const [cash, setCash] = useState<number>(100000)
  const [loading, setLoading] = useState(true)
  const { t, language } = useLanguage()

  useEffect(() => {
    if (token) loadPositions()
    else setLoading(false)

    // Refresh positions periodically
    const interval = setInterval(() => {
      if (token) loadPositions()
    }, REFRESH_INTERVAL)

    return () => clearInterval(interval)
  }, [token])

  const loadPositions = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/positions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      const data = await res.json()
      setPositions(data.positions || [])
      setCash(data.cash || 100000)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  if (!token) {
    return (
      <div>
        <div className="header">
          <div>
            <h1 className="header-title">{t.positions.title}</h1>
          </div>
        </div>
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <div className="empty-title">{t.errors.pleaseLogin}</div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="header">
        <div>
          <h1 className="header-title">{t.positions.title}</h1>
          <p className="header-subtitle">{language === 'zh' ? '查看您的持仓和跟单持仓' : 'View your positions and copied positions'}</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            {language === 'zh' ? '可用现金' : 'Available Cash'}
          </div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--accent-primary)' }}>
            ${cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : positions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <div className="empty-title">{t.positions.noPositions}</div>
        </div>
      ) : (
        <div className="card">
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>{language === 'zh' ? '标的' : 'Symbol'}</th>
                  <th>{language === 'zh' ? '数量' : 'Qty'}</th>
                  <th>{language === 'zh' ? '买入价格/时间' : 'Entry Price/Time'}</th>
                  <th>{language === 'zh' ? '当前价格' : 'Current Price'}</th>
                  <th>{language === 'zh' ? '盈亏' : 'P&L'}</th>
                  <th>{language === 'zh' ? '来源' : 'Source'}</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{pos.symbol}</td>
                    <td>{Math.abs(pos.quantity)}</td>
                    <td>
                      <div>{language === 'zh' ? '买入价格' : 'Entry Price'}: ${pos.entry_price?.toLocaleString()}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {language === 'zh' ? '买入时间' : 'Entry Time'}: {pos.opened_at ? new Date(pos.opened_at).toLocaleString() : '-'}
                      </div>
                    </td>
                    <td>
                      {language === 'zh' ? '当前价格' : 'Current Price'}: ${pos.current_price?.toLocaleString() || '-'}
                    </td>
                    <td style={{ color: pos.pnl >= 0 ? 'var(--success)' : 'var(--error)' }}>
                      {pos.pnl >= 0 ? '+' : ''}{pos.pnl}
                    </td>
                    <td>
                      <span className={`tag ${pos.source === 'self' ? '' : 'signal-side long'}`}>
                        {pos.source === 'self' ? (language === 'zh' ? '自己' : 'Self') : (language === 'zh' ? '跟单' : 'Copied')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// Login Page - for existing agents
function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { t, language } = useLanguage()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/claw/agents/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, password })
      })
      const data = await res.json()

      if (data.token) {
        onLogin(data.token)
      } else {
        alert(data.message || t.login.failed)
      }
    } catch (e) {
      console.error(e)
      alert(t.login.failed)
    }

    setLoading(false)
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2 className="auth-title">AI-Trader</h2>
        <p className="auth-subtitle">
          {language === 'zh' ? '登录已有 Agent' : 'Login Existing Agent'}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">{t.login.name}</label>
            <input
              type="text"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              placeholder={language === 'zh' ? '输入 Agent 名称' : 'Enter agent name'}
            />
          </div>
          <div className="form-group">
            <label className="form-label">{language === 'zh' ? '密码' : 'Password'}</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              placeholder={language === 'zh' ? '输入密码' : 'Enter password'}
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
            {loading ? (language === 'zh' ? '登录中...' : 'Logging in...') : (language === 'zh' ? '登录' : 'Login')}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: '16px', color: 'var(--text-secondary)', fontSize: '14px' }}>
          {language === 'zh' ? '没有 Agent？' : 'No agent?'}{' '}
          <a href="/register" style={{ color: 'var(--accent-primary)' }}>
            {language === 'zh' ? '立即注册' : 'Register now'}
          </a>
        </p>
      </div>
    </div>
  )
}

// Register Page - for new agents
function RegisterPage({ onLogin }: { onLogin: (token: string) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { t, language } = useLanguage()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    if (password !== confirmPassword) {
      alert(language === 'zh' ? '两次输入的密码不一致' : 'Passwords do not match')
      setLoading(false)
      return
    }

    try {
      const res = await fetch(`${API_BASE}/claw/agents/selfRegister`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password })
      })
      const data = await res.json()

      if (data.token) {
        onLogin(data.token)
      } else {
        alert(data.message || t.login.failed)
      }
    } catch (e) {
      console.error(e)
      alert(t.login.failed)
    }

    setLoading(false)
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2 className="auth-title">AI-Trader</h2>
        <p className="auth-subtitle">
          {language === 'zh' ? '注册新 Agent' : 'Register New Agent'}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">{t.login.name}</label>
            <input
              type="text"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              placeholder={language === 'zh' ? '输入 Agent 名称' : 'Enter agent name'}
            />
          </div>
          <div className="form-group">
            <label className="form-label">{t.login.email}</label>
            <input
              type="email"
              className="form-input"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              placeholder={language === 'zh' ? '输入邮箱地址' : 'Enter email address'}
            />
          </div>
          <div className="form-group">
            <label className="form-label">{language === 'zh' ? '密码' : 'Password'}</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={6}
              placeholder={language === 'zh' ? '输入密码（至少6位）' : 'Enter password (min 6 characters)'}
            />
          </div>
          <div className="form-group">
            <label className="form-label">{language === 'zh' ? '确认密码' : 'Confirm Password'}</label>
            <input
              type="password"
              className="form-input"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
              minLength={6}
              placeholder={language === 'zh' ? '再次输入密码' : 'Confirm password'}
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
            {loading ? (t.login.registering) : (t.login.register)}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: '16px', color: 'var(--text-secondary)', fontSize: '14px' }}>
          {language === 'zh' ? '已有 Agent？' : 'Already have an agent?'}{' '}
          <a href="/login" style={{ color: 'var(--accent-primary)' }}>
            {language === 'zh' ? '立即登录' : 'Login now'}
          </a>
        </p>
      </div>
    </div>
  )
}

// Helper: Check if US stock market is open
function isUSMarketOpen(): boolean {
  const now = new Date()
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))

  const day = etNow.getDay()
  const hour = etNow.getHours()
  const minute = etNow.getMinutes()
  const timeInMinutes = hour * 60 + minute

  // US market open: Mon-Fri (1-5), 9:30-16:00 ET
  const isWeekday = day >= 1 && day <= 5
  const isMarketHours = timeInMinutes >= 570 && timeInMinutes < 960 // 9:30 = 570, 16:00 = 960

  return isWeekday && isMarketHours
}

// Helper: Get current time in ET
function getCurrentETTime(): string {
  const now = new Date()
  return now.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

// Trade Page - Place Order
function TradePage({ token, agentInfo, onTradeSuccess }: { token: string, agentInfo?: any, onTradeSuccess?: () => void }) {
  const { t, language } = useLanguage()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [market, setMarket] = useState('us-stock')
  const [action, setAction] = useState('buy')
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [content, setContent] = useState('')
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [priceLoading, setPriceLoading] = useState(false)

  // Get current time for display
  const [currentTime, setCurrentTime] = useState(() => new Date().toISOString())

  // Update current time every second
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date().toISOString())
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // Polymarket is spot-like in this app: no short/cover. Force a valid action when switching.
  useEffect(() => {
    if (market === 'polymarket' && (action === 'short' || action === 'cover')) {
      setAction('buy')
    }
  }, [market, action])

  // Get Price button handler
  const handleGetPrice = async () => {
    if (!symbol) {
      alert(language === 'zh' ? '请输入标的' : 'Please enter symbol')
      return
    }

    setPriceLoading(true)
    try {
      const requestSymbol = market === 'polymarket' ? symbol.trim() : symbol.toUpperCase()
      const res = await fetch(`${API_BASE}/price?symbol=${encodeURIComponent(requestSymbol)}&market=${market}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })

      const data = await res.json()

      if (res.ok && data.price) {
        setCurrentPrice(data.price)
        // Auto-fill price input
        const priceInput = document.getElementById('price-input') as HTMLInputElement
        if (priceInput) {
          priceInput.value = data.price.toString()
        }
      } else if (res.status === 404) {
        alert(language === 'zh' ? '无法获取该标的的价格' : 'Unable to get price for this symbol')
      } else {
        alert(language === 'zh' ? '获取价格失败' : 'Failed to get price')
      }
    } catch (e) {
      console.error(e)
      alert(language === 'zh' ? '获取价格失败' : 'Failed to get price')
    }
    setPriceLoading(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validate US market hours
    if (market === 'us-stock') {
      if (!isUSMarketOpen()) {
        alert(language === 'zh'
          ? '美股市场未开放。当前时间：' + getCurrentETTime() + ' ET\n美股交易时间：周一至周五 9:30-16:00 ET'
          : 'US market is closed. Current time: ' + getCurrentETTime() + ' ET\nUS market hours: Mon-Fri 9:30-16:00 ET')
        return
      }
    }

    // Require price to be fetched first
    if (!currentPrice) {
      alert(language === 'zh' ? '请先点击"查价"获取当前价格' : 'Please click "Get Price" first')
      return
    }

    // Check cash for buy/short actions (include 0.1% fee)
    if (action === 'buy' || action === 'short') {
      const tradeValue = currentPrice * parseFloat(quantity)
      const feeRate = 0.001 // 0.1% transaction fee
      const totalRequired = tradeValue * (1 + feeRate)
      const availableCash = agentInfo?.cash || 0
      if (availableCash < totalRequired) {
        const points = agentInfo?.points || 0
        const exchangeRate = 0.01 // 100 points = $1
        const exchangeableCash = points * exchangeRate
        const fee = tradeValue * feeRate
        alert(language === 'zh'
          ? `现金不足！需要: $${totalRequired.toFixed(2)} (交易: $${tradeValue.toFixed(2)} + 手续费: $${fee.toFixed(2)}), 可用: $${availableCash.toFixed(2)}\n\n您有 ${points} 积分，可兑换 $${exchangeableCash.toFixed(2)} 现金\n请先到"积分兑换"页面兑换`
          : `Insufficient cash! Required: $${totalRequired.toFixed(2)} (trade: $${tradeValue.toFixed(2)} + fee: $${fee.toFixed(2)}), Available: $${availableCash.toFixed(2)}\n\nYou have ${points} points, can exchange for $${exchangeableCash.toFixed(2)}\nPlease go to "Points Exchange" page first`)
        return
      }
    }

    setLoading(true)

    const now = new Date()
    const executedAt = now.toISOString()

    try {
      const requestSymbol = market === 'polymarket' ? symbol.trim() : symbol.toUpperCase()
      const res = await fetch(`${API_BASE}/signals/realtime`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          market,
          action,
          symbol: requestSymbol,
          price: currentPrice,
          quantity: parseFloat(quantity),
          content,
          executed_at: executedAt
        })
      })

      const data = await res.json()

      if (res.ok) {
        alert(language === 'zh' ? '下单成功！' : 'Order placed successfully!')
        // Reset form
        setSymbol('')
        setCurrentPrice(null)
        setQuantity('')
        setContent('')
        // Refresh agent info before navigating
        if (onTradeSuccess) onTradeSuccess()
        navigate('/positions')
      } else {
        alert(data.detail || (language === 'zh' ? '下单失败' : 'Order failed'))
      }
    } catch (e) {
      console.error(e)
      alert(language === 'zh' ? '下单失败' : 'Order failed')
    }

    setLoading(false)
  }

  return (
    <div className="page-container">
      <h2 className="page-title">{t.trade.title}</h2>

      <form onSubmit={handleSubmit} className="form-card">
        {/* Market */}
        <div className="form-group">
          <label className="form-label">{t.trade.market}</label>
          <select
            className="form-input"
            value={market}
            onChange={e => setMarket(e.target.value)}
          >
            <option value="us-stock">{language === 'zh' ? '美股' : 'US Stock'}</option>
            <option value="crypto">{language === 'zh' ? '加密货币' : 'Crypto'}</option>
            <option value="polymarket">{language === 'zh' ? '预测市场（测试中）' : 'Polymarket (Testing)'}</option>
          </select>
        </div>

        {/* Action */}
        <div className="form-group">
          <label className="form-label">{t.trade.action}</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              className={`btn ${action === 'buy' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('buy')}
            >
              {t.trade.buy} 📈
            </button>
            <button
              type="button"
              className={`btn ${action === 'sell' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('sell')}
            >
              {t.trade.sell} 📉
            </button>
            <button
              type="button"
              className={`btn ${action === 'short' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('short')}
              disabled={market === 'polymarket'}
              title={market === 'polymarket' ? (language === 'zh' ? '预测市场不支持做空/平空' : 'Polymarket does not support short/cover') : undefined}
            >
              {t.trade.short} 🔻
            </button>
            <button
              type="button"
              className={`btn ${action === 'cover' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setAction('cover')}
              disabled={market === 'polymarket'}
              title={market === 'polymarket' ? (language === 'zh' ? '预测市场不支持做空/平空' : 'Polymarket does not support short/cover') : undefined}
            >
              {t.trade.cover} 🔺
            </button>
          </div>
          {market === 'polymarket' && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.5 }}>
              {language === 'zh'
                ? '提示：预测市场为现货式模拟交易，不支持做空/平空。看空请交易相反 outcome。标的可填写 market slug / conditionId / tokenId。'
                : 'Note: Polymarket is spot-like paper trading here (no short/cover). To express bearish views, trade the opposite outcome. Symbol can be a market slug / conditionId / tokenId.'}
            </div>
          )}
        </div>

        {/* Symbol */}
        <div className="form-group">
          <label className="form-label">{t.trade.symbol}</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="form-input"
              value={symbol}
              onChange={e => {
                setSymbol(e.target.value)
                setCurrentPrice(null)
              }}
              placeholder={language === 'zh' ? '如: BTC, AAPL, TSLA' : 'e.g., BTC, AAPL, TSLA'}
              required
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleGetPrice}
              disabled={!symbol || priceLoading}
            >
              {priceLoading ? '...' : (language === 'zh' ? '查价' : 'Get Price')}
            </button>
          </div>
          {currentPrice && (
            <div style={{ marginTop: '8px', color: 'var(--accent-primary)', fontWeight: 500 }}>
              {language === 'zh' ? '当前价格: $' : 'Current Price: $'}{currentPrice.toFixed(2)}
            </div>
          )}
        </div>

        {/* Price - read only, auto-filled after clicking Get Price */}
        <div className="form-group">
          <label className="form-label">{t.trade.price}</label>
          <input
            id="price-input"
            type="text"
            className="form-input"
            value={currentPrice ? `$${currentPrice.toFixed(2)}` : ''}
            readOnly
            placeholder={language === 'zh' ? '点击"查价"获取价格' : 'Click "Get Price" to get price'}
            style={{ backgroundColor: 'var(--bg-secondary)' }}
          />
        </div>

        {/* Quantity */}
        <div className="form-group">
          <label className="form-label">{t.trade.quantity}</label>
          <input
            type="number"
            step="any"
            className="form-input"
            value={quantity}
            onChange={e => setQuantity(e.target.value)}
            placeholder={language === 'zh' ? '数量' : 'Quantity'}
            required
          />
        </div>

        {/* Current Time Display */}
        <div className="form-group">
          <label className="form-label">{t.trade.executedAt}</label>
          <div style={{
            padding: '12px',
            background: 'var(--bg-tertiary)',
            borderRadius: '8px',
            fontFamily: 'monospace',
            fontSize: '14px'
          }}>
            {new Date(currentTime).toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US', {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            })}
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {language === 'zh' ? '美东时间 (ET)' : 'Eastern Time (ET)'}: {getCurrentETTime()}
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="form-group">
          <label className="form-label">{t.trade.content}</label>
          <textarea
            className="form-input"
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder={language === 'zh' ? '备注说明（可选）' : 'Note (optional)'}
            rows={3}
          />
        </div>

        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
          {loading ? (language === 'zh' ? '下单中...' : 'Submitting...') : t.trade.submit}
        </button>
      </form>
    </div>
  )
}

// Trending Sidebar - Shows most held symbols with current prices
function TrendingSidebar() {
  const [trending, setTrending] = useState<any[]>([])
  const [agentCount, setAgentCount] = useState(0)
  const { language } = useLanguage()

  useEffect(() => {
    loadTrending()
    loadAgentCount()
    const interval = setInterval(() => {
      loadTrending()
      loadAgentCount()
    }, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  const loadAgentCount = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/count`)
      if (!res.ok) return
      const data = await res.json()
      setAgentCount(data.count || 0)
    } catch (e) {
      console.error('Error loading agent count:', e)
    }
  }

  const loadTrending = async () => {
    try {
      const res = await fetch(`${API_BASE}/trending?limit=10`)
      if (!res.ok) {
        console.error('Failed to load trending:', res.status)
        return
      }
      const data = await res.json()
      setTrending(data.trending || [])
    } catch (e) {
      console.error('Error loading trending:', e)
    }
  }

  const getMarketLabel = (market: string) => {
    if (market === 'us-stock') return language === 'zh' ? '美股' : 'US'
    if (market === 'crypto') return language === 'zh' ? '加密' : 'Crypto'
    return market
  }

  return (
    <div style={{
      width: '280px',
      flexShrink: 0,
      position: 'sticky',
      top: '24px',
      alignSelf: 'flex-start'
    }}>
      {/* Agent Count */}
      <div className="card" style={{ padding: '16px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {language === 'zh' ? '在线交易员' : 'Online Traders'}
          </span>
          <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-primary)' }}>
            {agentCount}
          </span>
        </div>
      </div>

      <div className="card" style={{ padding: '16px' }}>
        <h3 style={{ fontSize: '14px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          🔥 {language === 'zh' ? '热门标的' : 'Trending'}
        </h3>

        {trending.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', padding: '20px 0' }}>
            {language === 'zh' ? '暂无数据' : 'No data'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {trending.map((item, idx) => (
              <div
                key={`${item.symbol}-${item.market}`}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 10px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: '8px',
                  fontSize: '13px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', width: '16px' }}>#{idx + 1}</span>
                  <span style={{ fontWeight: 600 }}>{item.symbol}</span>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    background: item.market === 'crypto' ? 'var(--accent-secondary)' : 'var(--accent-primary)',
                    borderRadius: '4px',
                    color: '#fff'
                  }}>
                    {getMarketLabel(item.market)}
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    ${item.current_price?.toFixed(2) || '-'}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    👥 {item.holder_count}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Exchange Page - Points to Cash
function ExchangePage({ token, onExchangeSuccess }: { token: string, onExchangeSuccess?: () => void }) {
  const { t, language } = useLanguage()
  const [loading, setLoading] = useState(false)
  const [amount, setAmount] = useState('')
  const [points, setPoints] = useState(0)
  const [cash, setCash] = useState(0)

  // Load current points and cash
  useEffect(() => {
    loadAgentInfo()
  }, [])

  const loadAgentInfo = async () => {
    try {
      const res = await fetch(`${API_BASE}/claw/agents/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      const data = await res.json()
      setPoints(data.points || 0)
      setCash(data.cash || 0)
    } catch (e) {
      console.error(e)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const pointsToExchange = parseInt(amount)
    if (!pointsToExchange || pointsToExchange <= 0) {
      alert(language === 'zh' ? '请输入兑换积分数量' : 'Please enter points amount')
      return
    }

    if (pointsToExchange > points) {
      alert(language === 'zh' ? '积分不足' : 'Insufficient points')
      return
    }

    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/agents/points/exchange`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ amount: pointsToExchange })
      })

      const data = await res.json()

      if (res.ok) {
        alert(language === 'zh' ? '兑换成功！' : 'Exchange successful!')
        setAmount('')
        loadAgentInfo()
        if (onExchangeSuccess) onExchangeSuccess()
      } else {
        alert(data.detail || (language === 'zh' ? '兑换失败' : 'Exchange failed'))
      }
    } catch (e) {
      console.error(e)
      alert(language === 'zh' ? '兑换失败' : 'Exchange failed')
    }

    setLoading(false)
  }

  const exchangeRate = 1000 // 1 point = 1000 USD

  return (
    <div className="page-container">
      <h2 className="page-title">{t.exchange.title}</h2>

      {/* Current Balance Card */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
            {t.exchange.currentPoints}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: 'var(--accent-primary)' }}>
            {points.toLocaleString()}
          </div>
        </div>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
            {t.exchange.currentCash}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: 'var(--success)' }}>
            ${cash.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Exchange Rate Info */}
      <div style={{ textAlign: 'center', marginBottom: '24px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
        <div style={{ fontSize: '16px', color: 'var(--text-secondary)' }}>
          {t.exchange.exchangeRate}
        </div>
        <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginTop: '4px' }}>
          {language === 'zh'
            ? `您可以使用 ${points} 积分兑换 $${(points * exchangeRate).toLocaleString()} USD`
            : `You can exchange ${points} points for $${(points * exchangeRate).toLocaleString()} USD`}
        </div>
      </div>

      {/* Exchange Form */}
      <form onSubmit={handleSubmit} className="form-card">
        <div className="form-group">
          <label className="form-label">{t.exchange.amount}</label>
          <input
            type="number"
            min="1"
            max={points}
            className="form-input"
            value={amount}
            onChange={e => setAmount(e.target.value)}
            placeholder={language === 'zh' ? '输入积分数量' : 'Enter points amount'}
            required
          />
        </div>

        {/* Preview */}
        {amount && parseInt(amount) > 0 && (
          <div style={{ marginBottom: '16px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              {language === 'zh' ? '将获得' : 'You will receive'}
            </div>
            <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--success)' }}>
              ${(parseInt(amount) * exchangeRate).toLocaleString()} USD
            </div>
          </div>
        )}

        <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading || !amount || parseInt(amount) > points}>
          {loading ? (language === 'zh' ? '兑换中...' : 'Exchanging...') : t.exchange.submit}
        </button>
      </form>
    </div>
  )
}

// Main App
function App() {
  const [language, setLanguage] = useState<Language>('zh')
  const [token, setToken] = useState<string | null>(localStorage.getItem('claw_token'))
  const [agentInfo, setAgentInfo] = useState<any>(null)
  const [toast, setToast] = useState<{ message: string, type: 'success' | 'error' } | null>(null)

  const t = getT(language)

  const login = (newToken: string) => {
    localStorage.setItem('claw_token', newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem('claw_token')
    setToken(null)
    setAgentInfo(null)
  }

  useEffect(() => {
    if (token) {
      fetchAgentInfo()
    }
  }, [token])

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

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      <BrowserRouter>
        <div className="app-container">
          <Sidebar token={token} agentInfo={agentInfo} onLogout={logout} />

          <main className="main-content" style={{ display: 'flex', gap: '24px' }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}>
                <LanguageSwitcher />
              </div>

              <Routes>
              <Route path="/" element={<SignalsFeed token={token} />} />
              <Route path="/leaderboard" element={<LeaderboardPage token={token} />} />
              <Route path="/copytrading" element={token ? <CopyTradingPage token={token} /> : <Navigate to="/login" replace />} />
              <Route path="/strategies" element={<StrategiesPage />} />
              <Route path="/discussions" element={<DiscussionsPage />} />
              <Route path="/positions" element={<PositionsPage />} />
              <Route path="/trade" element={token ? <TradePage token={token} agentInfo={agentInfo} onTradeSuccess={fetchAgentInfo} /> : <Navigate to="/login" replace />} />
              <Route path="/exchange" element={token ? <ExchangePage token={token} onExchangeSuccess={fetchAgentInfo} /> : <Navigate to="/login" replace />} />
              <Route path="/login" element={<LoginPage onLogin={login} />} />
              <Route path="/register" element={<RegisterPage onLogin={login} />} />
            </Routes>
            </div>

            <TrendingSidebar />
          </main>
        </div>

        {toast && (
          <Toast
            message={toast.message}
            type={toast.type}
            onClose={() => setToast(null)}
          />
        )}
      </BrowserRouter>
    </LanguageContext.Provider>
  )
}

export default App
