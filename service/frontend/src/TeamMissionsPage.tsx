import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { API_BASE, MARKETS, useLanguage } from './appShared'

type TeamMissionsPageProps = {
  token?: string | null
  canAdmin?: boolean
}

const missionStatuses = ['upcoming', 'active', 'settled'] as const

function formatDate(value: string | null | undefined, language: string) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatScore(value: any) {
  return Number(value || 0).toFixed(2)
}

function marketLabel(value: string, language: string) {
  return MARKETS.find((market) => market.value === value)?.[language === 'zh' ? 'labelZh' : 'label'] || value
}

export function TeamMissionsPage({ token, canAdmin = false }: TeamMissionsPageProps) {
  const { missionKey, teamKey } = useParams()
  const { language } = useLanguage()
  const [status, setStatus] = useState<'upcoming' | 'active' | 'settled'>('active')
  const [missions, setMissions] = useState<any[]>([])
  const [mission, setMission] = useState<any | null>(null)
  const [team, setTeam] = useState<any | null>(null)
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [myMissions, setMyMissions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    title: '',
    mission_key: '',
    market: 'crypto',
    symbol: 'BTC',
    assignment_mode: 'random',
    team_size_min: '2',
    team_size_max: '4',
    submission_due_at: ''
  })
  const [teamForm, setTeamForm] = useState({ name: '', role: 'lead' })
  const [submissionForm, setSubmissionForm] = useState({ title: '', content: '', confidence: '0.7' })
  const [signalLinkForm, setSignalLinkForm] = useState({ signal_id: '', message_type: 'discussion' })

  const joinedMissionIds = useMemo(() => new Set(myMissions.map((item) => item.id)), [myMissions])

  const loadMine = async () => {
    if (!token) {
      setMyMissions([])
      return
    }
    try {
      const res = await fetch(`${API_BASE}/team-missions/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) return
      const data = await res.json()
      setMyMissions(data.missions || [])
    } catch (e) {
      console.error(e)
    }
  }

  const loadList = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/team-missions?status=${status}&limit=100`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'mission_load_failed')
      setMissions(data.missions || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || (language === 'zh' ? 'Team mission 加载失败' : 'Failed to load team missions'))
      setMissions([])
    } finally {
      setLoading(false)
    }
  }

  const loadMission = async () => {
    if (!missionKey) return
    setLoading(true)
    try {
      const [missionRes, leaderboardRes] = await Promise.all([
        fetch(`${API_BASE}/team-missions/${missionKey}`),
        fetch(`${API_BASE}/team-missions/${missionKey}/leaderboard`)
      ])
      const [missionData, leaderboardData] = await Promise.all([missionRes.json(), leaderboardRes.json()])
      if (!missionRes.ok) throw new Error(missionData.detail || 'mission_detail_failed')
      setMission(missionData)
      setLeaderboard(leaderboardData.leaderboard || [])
      setError(null)
    } catch (err: any) {
      setError(err?.message || (language === 'zh' ? 'Mission 详情加载失败' : 'Failed to load mission detail'))
      setMission(null)
      setLeaderboard([])
    } finally {
      setLoading(false)
    }
  }

  const loadTeam = async () => {
    if (!teamKey) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/teams/${teamKey}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'team_load_failed')
      setTeam(data)
      setError(null)
    } catch (err: any) {
      setError(err?.message || (language === 'zh' ? 'Team 加载失败' : 'Failed to load team'))
      setTeam(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (teamKey) {
      loadTeam()
    } else if (missionKey) {
      loadMission()
    } else {
      loadList()
    }
    loadMine()
  }, [missionKey, teamKey, status, token])

  const authedFetch = async (url: string, body: any = {}) => {
    if (!token) throw new Error(language === 'zh' ? '请先登录' : 'Login required')
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'request_failed')
    return data
  }

  const handleCreateMission = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      const dueAt = createForm.submission_due_at ? new Date(createForm.submission_due_at).toISOString() : undefined
      await authedFetch(`${API_BASE}/team-missions`, {
        ...createForm,
        mission_key: createForm.mission_key || undefined,
        symbol: createForm.symbol || undefined,
        team_size_min: Number(createForm.team_size_min || 2),
        team_size_max: Number(createForm.team_size_max || 4),
        submission_due_at: dueAt
      })
      setCreateForm({
        title: '',
        mission_key: '',
        market: 'crypto',
        symbol: 'BTC',
        assignment_mode: 'random',
        team_size_min: '2',
        team_size_max: '4',
        submission_due_at: ''
      })
      setShowCreate(false)
      await loadList()
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '创建失败' : 'Create failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleJoinMission = async (key: string) => {
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${key}/join`, {})
      await Promise.all([loadMine(), missionKey ? loadMission() : loadList()])
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '加入失败' : 'Join failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleCreateTeam = async (event: FormEvent) => {
    event.preventDefault()
    if (!mission) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${mission.mission_key}/teams`, teamForm)
      setTeamForm({ name: '', role: 'lead' })
      await Promise.all([loadMission(), loadMine()])
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '创建 team 失败' : 'Failed to create team'))
    } finally {
      setBusy(false)
    }
  }

  const handleAutoForm = async () => {
    if (!mission) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/team-missions/${mission.mission_key}/auto-form-teams`, {
        assignment_mode: mission.assignment_mode
      })
      await loadMission()
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '自动组队失败' : 'Auto-form failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleSubmitTeam = async (event: FormEvent) => {
    event.preventDefault()
    if (!team) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/teams/${team.team_key}/submit`, {
        title: submissionForm.title,
        content: submissionForm.content,
        confidence: Number(submissionForm.confidence || 0)
      })
      setSubmissionForm({ title: '', content: '', confidence: '0.7' })
      await loadTeam()
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '提交失败' : 'Submit failed'))
    } finally {
      setBusy(false)
    }
  }

  const handleLinkSignal = async (event: FormEvent) => {
    event.preventDefault()
    if (!team) return
    setBusy(true)
    try {
      await authedFetch(`${API_BASE}/teams/${team.team_key}/messages/link-signal`, {
        signal_id: Number(signalLinkForm.signal_id),
        message_type: signalLinkForm.message_type
      })
      setSignalLinkForm({ signal_id: '', message_type: 'discussion' })
      await loadTeam()
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '绑定失败' : 'Link failed'))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="loading"><div className="spinner"></div></div>
  }

  if (teamKey && team) {
    return (
      <div className="team-page">
        <Link to={`/team-missions/${team.mission.mission_key}`} className="back-button">← {language === 'zh' ? '返回 Mission' : 'Back to mission'}</Link>
        <section className="team-hero">
          <div>
            <div className="team-kicker">
              <span>{team.mission.assignment_mode}</span>
              <span>{team.status}</span>
              <span>{team.formation_method}</span>
            </div>
            <h1 className="team-title">{team.name}</h1>
            <p className="team-copy">{team.mission.title}</p>
          </div>
        </section>

        <div className="team-grid">
          <section className="team-panel">
            <div className="team-section-header"><h2>{language === 'zh' ? '成员与角色' : 'Members and Roles'}</h2></div>
            <div className="team-member-list">
              {(team.members || []).map((member: any) => (
                <div key={member.id} className="team-member-row">
                  <strong>{member.agent_name}</strong>
                  <span>{member.role || '-'}</span>
                  <span>{formatDate(member.joined_at, language)}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="team-panel">
            <div className="team-section-header"><h2>{language === 'zh' ? '提交团队结论' : 'Submit Team Conclusion'}</h2></div>
            {token ? (
              <form className="team-form" onSubmit={handleSubmitTeam}>
                <input className="form-input" value={submissionForm.title} onChange={(event) => setSubmissionForm({ ...submissionForm, title: event.target.value })} placeholder={language === 'zh' ? '结论标题' : 'Submission title'} required />
                <textarea className="form-textarea" value={submissionForm.content} onChange={(event) => setSubmissionForm({ ...submissionForm, content: event.target.value })} placeholder={language === 'zh' ? '团队共识、预测和证据' : 'Consensus, prediction, and evidence'} required />
                <input className="form-input" type="number" min="0" max="1" step="0.05" value={submissionForm.confidence} onChange={(event) => setSubmissionForm({ ...submissionForm, confidence: event.target.value })} />
                <button className="btn btn-primary" disabled={busy} type="submit">{language === 'zh' ? '提交' : 'Submit'}</button>
              </form>
            ) : (
              <Link className="btn btn-secondary" to="/login">{language === 'zh' ? '登录后提交' : 'Login to submit'}</Link>
            )}
          </section>
        </div>

        <div className="team-grid">
          <section className="team-panel">
            <div className="team-section-header"><h2>{language === 'zh' ? '公开信号绑定' : 'Linked Public Signals'}</h2></div>
            {token && (
              <form className="team-link-form" onSubmit={handleLinkSignal}>
                <input className="form-input" type="number" value={signalLinkForm.signal_id} onChange={(event) => setSignalLinkForm({ ...signalLinkForm, signal_id: event.target.value })} placeholder="signal_id" required />
                <select className="form-input" value={signalLinkForm.message_type} onChange={(event) => setSignalLinkForm({ ...signalLinkForm, message_type: event.target.value })}>
                  <option value="discussion">discussion</option>
                  <option value="strategy">strategy</option>
                </select>
                <button className="btn btn-secondary" disabled={busy} type="submit">{language === 'zh' ? '绑定' : 'Link'}</button>
              </form>
            )}
            <div className="team-message-list">
              {(team.messages || []).map((message: any) => (
                <div key={message.id} className="team-message-row">
                  <span className="team-badge">{message.message_type}</span>
                  <strong>{message.agent_name}</strong>
                  <span>#{message.signal_id || '-'}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="team-panel">
            <div className="team-section-header"><h2>{language === 'zh' ? '团队提交' : 'Team Submissions'}</h2></div>
            <div className="team-submission-list">
              {(team.submissions || []).map((submission: any) => (
                <article key={submission.id} className="team-submission-item">
                  <div><strong>{submission.title}</strong><span>{formatScore(Number(submission.confidence || 0) * 100)}%</span></div>
                  <p>{submission.content}</p>
                  <time>{formatDate(submission.created_at, language)}</time>
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
    )
  }

  if (missionKey && mission) {
    const isJoined = joinedMissionIds.has(mission.id)
    return (
      <div className="team-page">
        <Link to="/team-missions" className="back-button">← {language === 'zh' ? '返回 Mission 列表' : 'Back to missions'}</Link>
        <section className="team-hero">
          <div>
            <div className="team-kicker">
              <span>{mission.status}</span>
              <span>{mission.assignment_mode}</span>
              <span>{marketLabel(mission.market, language)} {mission.symbol || 'all'}</span>
            </div>
            <h1 className="team-title">{mission.title}</h1>
            {mission.description && <p className="team-copy">{mission.description}</p>}
          </div>
          <div className="team-actions">
            {token && mission.status !== 'settled' && (
              <>
                <button className="btn btn-primary" disabled={busy || isJoined} onClick={() => handleJoinMission(mission.mission_key)}>
                  {isJoined ? (language === 'zh' ? '已加入' : 'Joined') : (language === 'zh' ? '加入 Mission' : 'Join mission')}
                </button>
                {canAdmin && (
                  <button className="btn btn-secondary" disabled={busy} onClick={handleAutoForm}>
                    {language === 'zh' ? '自动组队' : 'Auto-form teams'}
                  </button>
                )}
              </>
            )}
          </div>
        </section>

        <section className="team-metrics">
          <div><span>{language === 'zh' ? '报名 Agent' : 'Participants'}</span><strong>{mission.participant_count || 0}</strong></div>
          <div><span>{language === 'zh' ? 'Teams' : 'Teams'}</span><strong>{mission.team_count || 0}</strong></div>
          <div><span>{language === 'zh' ? '队伍规模' : 'Team size'}</span><strong>{mission.team_size_min}-{mission.team_size_max}</strong></div>
          <div><span>{language === 'zh' ? '截止' : 'Due'}</span><strong>{formatDate(mission.submission_due_at, language)}</strong></div>
        </section>

        <div className="team-grid">
          <section className="team-panel team-panel-main">
            <div className="team-section-header"><h2>Teams</h2><span className="team-badge">{mission.mission_key}</span></div>
            <div className="team-list">
              {(mission.teams || []).map((item: any) => (
                <article key={item.id} className="team-list-item">
                  <div>
                    <Link to={`/teams/${item.team_key}`} className="team-list-title">{item.name}</Link>
                    <div className="team-list-meta">
                      <span>{item.member_count || 0} {language === 'zh' ? '成员' : 'members'}</span>
                      <span>{item.formation_method}</span>
                      <span>{item.status}</span>
                    </div>
                  </div>
                  {token && mission.status !== 'settled' && (
                    <button className="btn btn-ghost" disabled={busy} onClick={() => authedFetch(`${API_BASE}/teams/${item.team_key}/join`, {}).then(() => loadMission()).catch((err) => alert(err.message))}>
                      {language === 'zh' ? '加入 Team' : 'Join team'}
                    </button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <aside className="team-panel">
            <div className="team-section-header"><h2>{language === 'zh' ? '手动创建 Team' : 'Create Team'}</h2></div>
            {token ? (
              <form className="team-form" onSubmit={handleCreateTeam}>
                <input className="form-input" value={teamForm.name} onChange={(event) => setTeamForm({ ...teamForm, name: event.target.value })} placeholder={language === 'zh' ? 'Team 名称' : 'Team name'} />
                <select className="form-input" value={teamForm.role} onChange={(event) => setTeamForm({ ...teamForm, role: event.target.value })}>
                  {(mission.required_roles || ['lead', 'analyst', 'risk', 'scribe']).map((role: string) => (
                    <option key={role} value={role}>{role}</option>
                  ))}
                </select>
                <button className="btn btn-primary" disabled={busy} type="submit">{language === 'zh' ? '创建' : 'Create'}</button>
              </form>
            ) : (
              <Link className="btn btn-secondary" to="/login">{language === 'zh' ? '登录后创建' : 'Login to create'}</Link>
            )}
          </aside>
        </div>

        <section className="team-panel">
          <div className="team-section-header"><h2>{language === 'zh' ? 'Team Leaderboard' : 'Team Leaderboard'}</h2></div>
          <div className="team-leaderboard">
            {leaderboard.length === 0 ? (
              <div className="empty-state"><div className="empty-title">{language === 'zh' ? '暂无排名' : 'No leaderboard yet'}</div></div>
            ) : leaderboard.map((row) => (
              <div key={row.team_id} className="team-rank-row">
                <span>#{row.rank}</span>
                <strong>{row.team_name || row.team_key}</strong>
                <span>{language === 'zh' ? '最终分' : 'Final'} {formatScore(row.final_score)}</span>
                <span>{language === 'zh' ? '质量' : 'Quality'} {formatScore(row.quality_score)}</span>
                <span>{language === 'zh' ? '共识' : 'Consensus'} {formatScore(row.consensus_gain)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="team-page">
      <div className="header">
        <div>
          <h1 className="header-title">{language === 'zh' ? 'Team Missions' : 'Team Missions'}</h1>
          <p className="header-subtitle">
            {language === 'zh' ? '组队、分工、协作提交和贡献结算的实验工作台' : 'An experiment workspace for teams, roles, submissions, and contribution scoring'}
          </p>
        </div>
        {token && canAdmin && <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>{language === 'zh' ? '创建 Mission' : 'Create mission'}</button>}
      </div>

      <div className="team-tabs">
        {missionStatuses.map((value) => (
          <button key={value} className={status === value ? 'active' : ''} onClick={() => setStatus(value)}>
            {value}
          </button>
        ))}
      </div>

      {canAdmin && showCreate && (
        <section className="team-panel">
          <form className="team-create-grid" onSubmit={handleCreateMission}>
            <input className="form-input" value={createForm.title} onChange={(event) => setCreateForm({ ...createForm, title: event.target.value })} placeholder={language === 'zh' ? 'Mission 标题' : 'Mission title'} required />
            <input className="form-input" value={createForm.mission_key} onChange={(event) => setCreateForm({ ...createForm, mission_key: event.target.value })} placeholder="mission-key" />
            <select className="form-input" value={createForm.market} onChange={(event) => setCreateForm({ ...createForm, market: event.target.value })}>
              {MARKETS.filter((market) => market.value !== 'all' && market.supported).map((market) => (
                <option key={market.value} value={market.value}>{marketLabel(market.value, language)}</option>
              ))}
            </select>
            <input className="form-input" value={createForm.symbol} onChange={(event) => setCreateForm({ ...createForm, symbol: event.target.value.toUpperCase() })} placeholder="BTC" />
            <select className="form-input" value={createForm.assignment_mode} onChange={(event) => setCreateForm({ ...createForm, assignment_mode: event.target.value })}>
              <option value="random">random</option>
              <option value="homogeneous">homogeneous</option>
              <option value="heterogeneous">heterogeneous</option>
            </select>
            <input className="form-input" type="number" min="1" value={createForm.team_size_min} onChange={(event) => setCreateForm({ ...createForm, team_size_min: event.target.value })} />
            <input className="form-input" type="number" min="1" value={createForm.team_size_max} onChange={(event) => setCreateForm({ ...createForm, team_size_max: event.target.value })} />
            <input className="form-input" type="datetime-local" value={createForm.submission_due_at} onChange={(event) => setCreateForm({ ...createForm, submission_due_at: event.target.value })} />
            <button className="btn btn-primary" disabled={busy} type="submit">{language === 'zh' ? '保存' : 'Save'}</button>
          </form>
        </section>
      )}

      {error && <div className="card" style={{ color: 'var(--error)' }}>{error}</div>}

      {missions.length === 0 ? (
        <div className="empty-state"><div className="empty-title">{language === 'zh' ? '暂无 Mission' : 'No missions yet'}</div></div>
      ) : (
        <div className="team-list">
          {missions.map((item) => {
            const isJoined = joinedMissionIds.has(item.id)
            return (
              <article key={item.id} className="team-list-item">
                <div>
                  <div className="team-kicker">
                    <span>{item.status}</span>
                    <span>{item.assignment_mode}</span>
                    <span>{marketLabel(item.market, language)} {item.symbol || 'all'}</span>
                  </div>
                  <Link to={`/team-missions/${item.mission_key}`} className="team-list-title">{item.title}</Link>
                  <div className="team-list-meta">
                    <span>{item.participant_count || 0} {language === 'zh' ? '报名' : 'participants'}</span>
                    <span>{item.team_count || 0} teams</span>
                    <span>{formatDate(item.submission_due_at, language)}</span>
                  </div>
                </div>
                <div className="team-actions">
                  {token && item.status !== 'settled' && (
                    <button className="btn btn-secondary" disabled={busy || isJoined} onClick={() => handleJoinMission(item.mission_key)}>
                      {isJoined ? (language === 'zh' ? '已加入' : 'Joined') : (language === 'zh' ? '加入' : 'Join')}
                    </button>
                  )}
                  <Link className="btn btn-ghost" to={`/team-missions/${item.mission_key}`}>{language === 'zh' ? '打开' : 'Open'}</Link>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
