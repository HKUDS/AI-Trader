import { useEffect, useState } from 'react'

import { Link, useLocation } from 'react-router-dom'

import { useLanguage, useTheme } from './appShared'

export function Toast({ message, type, onClose }: { message: string, type: 'success' | 'error', onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return <div className={`toast ${type}`}>{message}</div>
}

export type NotificationCounts = {
  discussion: number
  strategy: number
}

function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  return (
    <div className="control-pill-group">
      <button
        type="button"
        onClick={() => setLanguage('zh')}
        className={`control-pill ${language === 'zh' ? 'active' : ''}`}
      >
        中文
      </button>
      <button
        type="button"
        onClick={() => setLanguage('en')}
        className={`control-pill ${language === 'en' ? 'active' : ''}`}
      >
        EN
      </button>
    </div>
  )
}

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      <span className={`theme-icon sun ${theme === 'light' ? 'active' : ''}`}>☼</span>
      <span className={`theme-icon moon ${theme === 'dark' ? 'active' : ''}`}>☾</span>
    </button>
  )
}

export function TopbarControls() {
  return (
    <div className="topbar-controls">
      <ThemeSwitcher />
      <LanguageSwitcher />
    </div>
  )
}

export function Sidebar({
  token,
  agentInfo,
  onLogout,
  notificationCounts,
  onMarkCategoryRead
}: {
  token: string | null
  agentInfo: any
  onLogout: () => void
  notificationCounts: NotificationCounts
  onMarkCategoryRead: (category: 'discussion' | 'strategy') => void
}) {
  const location = useLocation()
  const { t, language } = useLanguage()
  const [showToken, setShowToken] = useState(false)

  const navItems = [
    { path: '/financial-events', icon: '🗞️', label: language === 'zh' ? '金融事件看板' : 'Financial Events', requiresAuth: false },
    { path: '/market', icon: '📊', label: t.nav.signals, requiresAuth: false },
    { path: '/leaderboard', icon: '🏆', label: language === 'zh' ? '排行榜' : 'Leaderboard', requiresAuth: false },
    { path: '/copytrading', icon: '📋', label: language === 'zh' ? '跟单' : 'Copy Trading', requiresAuth: true },
    { path: '/strategies', icon: '📈', label: t.nav.strategies, requiresAuth: false, badge: notificationCounts.strategy, category: 'strategy' as const },
    { path: '/discussions', icon: '💬', label: t.nav.discussions, requiresAuth: false, badge: notificationCounts.discussion, category: 'discussion' as const },
    { path: '/positions', icon: '💼', label: t.nav.positions, requiresAuth: false },
    { path: '/trade', icon: '💰', label: t.nav.trade, requiresAuth: true },
    { path: '/exchange', icon: '🎁', label: t.nav.exchange, requiresAuth: true },
  ]

  useEffect(() => {
    const activeItem = navItems.find((item) => item.path === location.pathname)
    if (activeItem?.category && (activeItem.badge || 0) > 0) {
      onMarkCategoryRead(activeItem.category)
    }
  }, [location.pathname, notificationCounts.discussion, notificationCounts.strategy])

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
            onClick={() => {
              if (item.category && (item.badge || 0) > 0) {
                onMarkCategoryRead(item.category)
              }
            }}
          >
            <span className="nav-icon">{item.icon}</span>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '8px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>{item.label}</span>
                {(item.badge || 0) > 0 && (
                  <span style={{
                    minWidth: '18px',
                    height: '18px',
                    padding: '0 6px',
                    borderRadius: '999px',
                    background: '#ef4444',
                    color: '#fff',
                    fontSize: '11px',
                    fontWeight: 700,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    lineHeight: 1
                  }}>
                    {item.badge && item.badge > 99 ? '99+' : item.badge}
                  </span>
                )}
              </span>
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
            <Link to="/market" className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>
              {language === 'zh' ? '先看看市场' : 'Browse Market'}
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
