import { createContext, useContext } from 'react'

import { Language, getT } from './i18n'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: ReturnType<typeof getT>
}

export type ThemeMode = 'dark' | 'light'

interface ThemeContextType {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
}

export const LanguageContext = createContext<LanguageContextType | null>(null)
export const ThemeContext = createContext<ThemeContextType | null>(null)

export const useLanguage = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider')
  }
  return context
}

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}

export const API_BASE = '/api'
export const REFRESH_INTERVAL = parseInt(import.meta.env.VITE_REFRESH_INTERVAL || '300000', 10)
export const NOTIFICATION_POLL_INTERVAL = 60 * 1000
export const FIVE_MINUTES_MS = 5 * 60 * 1000
export const ONE_DAY_MS = 24 * 60 * 60 * 1000
export const SIGNALS_FEED_PAGE_SIZE = 20
export const LEADERBOARD_PAGE_SIZE = 20
export const COPY_TRADING_PAGE_SIZE = 20
export const COMMUNITY_FEED_PAGE_SIZE = 20
export const FINANCIAL_NEWS_PAGE_SIZE = 4
export const LEADERBOARD_LINE_COLORS = ['#d66a5f', '#d49e52', '#b8b15f', '#7bb174', '#5aa7a3', '#4e88b7', '#7a78c5', '#a16cb8', '#c66f9f', '#cb7a7a']

export type LeaderboardChartRange = 'all' | '24h'

export function getLeaderboardDays(chartRange: LeaderboardChartRange) {
  return chartRange === '24h' ? 1 : 7
}

function parseRecordedAt(recordedAt: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(recordedAt) ? recordedAt : `${recordedAt}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatIntelTimestamp(timestamp: string | null | undefined, language: Language) {
  if (!timestamp) return language === 'zh' ? '暂无快照' : 'No snapshot yet'
  const parsed = parseRecordedAt(timestamp)
  if (!parsed) return language === 'zh' ? '时间未知' : 'Unknown time'
  const formatted = parsed.toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/New_York'
  })
  return `${formatted} ET`
}

export function formatIntelNumber(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'N/A'
  }
  return Number(value).toFixed(digits)
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

export function buildLeaderboardChartData(profitHistory: any[], chartRange: LeaderboardChartRange, language: Language) {
  const topAgents = profitHistory.slice(0, 10).map((agent: any) => ({
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

function getPolymarketDisplayTitle(item: any) {
  return item?.display_title || item?.market_title || (item?.outcome && item?.symbol ? `${item.symbol} [${item.outcome}]` : item?.symbol || '')
}

export function getInstrumentLabel(item: any) {
  if (item?.market === 'polymarket') {
    return getPolymarketDisplayTitle(item)
  }
  return item?.title || item?.symbol || ''
}

export function LeaderboardTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: any[]
  label?: string
}) {
  if (!active || !payload || payload.length === 0) {
    return null
  }

  const sortedPayload = [...payload]
    .filter((entry) => typeof entry?.value === 'number')
    .sort((a, b) => Number(b.value) - Number(a.value))

  return (
    <div style={{
      minWidth: '220px',
      padding: '12px 14px',
      borderRadius: '12px',
      background: 'var(--bg-secondary)',
      border: '1px solid var(--bg-tertiary)',
      boxShadow: 'var(--shadow-sm)'
    }}>
      <div style={{
        marginBottom: '10px',
        color: 'var(--text-secondary)',
        fontSize: '12px',
        fontFamily: 'IBM Plex Mono, monospace'
      }}>
        {label}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {sortedPayload.map((entry, idx) => (
          <div
            key={`${entry.dataKey}-${idx}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '24px 10px minmax(0, 1fr) auto',
              alignItems: 'center',
              gap: '8px',
              fontSize: '12px'
            }}
          >
            <span style={{ color: 'var(--text-muted)', fontFamily: 'IBM Plex Mono, monospace' }}>#{idx + 1}</span>
            <span style={{
              width: '8px',
              height: '8px',
              borderRadius: '999px',
              background: entry.color || entry.stroke || 'var(--accent-primary)'
            }}></span>
            <span style={{
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: 'var(--text-primary)',
              fontWeight: 600
            }}>
              {entry.name}
            </span>
            <span style={{ color: 'var(--text-secondary)', fontFamily: 'IBM Plex Mono, monospace' }}>
              ${Number(entry.value).toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export type MarketIntelNewsCategory = {
  category: string
  label: string
  label_zh: string
  description: string
  description_zh: string
  items: any[]
  summary: any
  created_at: string | null
  available: boolean
}

export const MARKETS = [
  { value: 'all', label: 'All', labelZh: '全部', supported: true },
  { value: 'us-stock', label: 'US Stock', labelZh: '美股', supported: true },
  { value: 'crypto', label: 'Crypto (Testing)', labelZh: '加密货币（测试中）', supported: true },
  { value: 'a-stock', label: 'A-Share (Developing)', labelZh: 'A股（开发中）', supported: false },
  { value: 'polymarket', label: 'Polymarket (Testing)', labelZh: '预测市场（测试中）', supported: true },
  { value: 'forex', label: 'Forex (Developing)', labelZh: '外汇（开发中）', supported: false },
  { value: 'options', label: 'Options (Developing)', labelZh: '期权（开发中）', supported: false },
  { value: 'futures', label: 'Futures (Developing)', labelZh: '期货（开发中）', supported: false },
]

export function isUSMarketOpen(): boolean {
  const now = new Date()
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))

  const day = etNow.getDay()
  const hour = etNow.getHours()
  const minute = etNow.getMinutes()
  const timeInMinutes = hour * 60 + minute

  const isWeekday = day >= 1 && day <= 5
  const isMarketHours = timeInMinutes >= 570 && timeInMinutes < 960

  return isWeekday && isMarketHours
}

export function getCurrentETTime(): string {
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
