import { useEffect, useState, type FormEvent } from 'react'

import { API_BASE, useLanguage } from './appShared'

type ExperimentAdminPageProps = {
  token?: string | null
}

const defaultVariants = JSON.stringify([
  { key: 'control', weight: 1, reward_mode: 'fixed' },
  { key: 'quality-weighted', weight: 1, reward_mode: 'quality_weighted', reward_multiplier: 1.4 }
], null, 2)

const experimentMessageTypes = [
  'experiment_announcement',
  'experiment_assignment',
  'experiment_reminder',
  'experiment_rule_update',
  'experiment_result_update',
  'challenge_invite',
  'team_mission_invite'
]

export function ExperimentAdminPage({ token }: ExperimentAdminPageProps) {
  const { language } = useLanguage()
  const [experiments, setExperiments] = useState<any[]>([])
  const [selectedExperiment, setSelectedExperiment] = useState<any | null>(null)
  const [assignments, setAssignments] = useState<any[]>([])
  const [variantCounts, setVariantCounts] = useState<any[]>([])
  const [variantMetrics, setVariantMetrics] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notificationBusy, setNotificationBusy] = useState(false)
  const [notificationPreview, setNotificationPreview] = useState<any | null>(null)
  const [formData, setFormData] = useState({
    title: '',
    experiment_key: '',
    status: 'active',
    unit_type: 'agent',
    variants_json: defaultVariants,
    start_at: '',
    end_at: ''
  })
  const [notificationForm, setNotificationForm] = useState({
    experiment_key: '',
    variant_key: '',
    message_type: 'experiment_announcement',
    title: '',
    content: '',
    agent_ids: '',
    limit: 500,
    dry_run: true,
    create_task: false,
    task_type: 'submit_strategy'
  })

  const loadExperiments = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/experiments?limit=100`)
      const data = await res.json()
      setExperiments(data.experiments || [])
      if (!notificationForm.experiment_key && data.experiments?.[0]?.experiment_key) {
        setNotificationForm((prev) => ({ ...prev, experiment_key: data.experiments[0].experiment_key }))
      }
    } catch (e) {
      console.error(e)
      setExperiments([])
    } finally {
      setLoading(false)
    }
  }

  const loadAssignments = async (experimentKey: string) => {
    try {
      const res = await fetch(`${API_BASE}/experiments/${experimentKey}/assignments?limit=500`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'assignment_load_failed')
      setSelectedExperiment(data.experiment)
      setAssignments(data.assignments || [])
      setVariantCounts(data.variant_counts || [])
      setVariantMetrics(data.variant_metrics || [])
      setNotificationForm((prev) => ({ ...prev, experiment_key: experimentKey }))
    } catch (e) {
      console.error(e)
      setAssignments([])
      setVariantCounts([])
      setVariantMetrics([])
    }
  }

  useEffect(() => {
    loadExperiments()
  }, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    if (!token) return
    setBusy(true)
    try {
      let variants
      try {
        variants = JSON.parse(formData.variants_json)
      } catch {
        alert(language === 'zh' ? 'Variants JSON 格式错误' : 'Invalid variants JSON')
        return
      }
      const res = await fetch(`${API_BASE}/experiments`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          title: formData.title,
          experiment_key: formData.experiment_key || undefined,
          status: formData.status,
          unit_type: formData.unit_type,
          variants_json: variants,
          start_at: formData.start_at ? new Date(formData.start_at).toISOString() : undefined,
          end_at: formData.end_at ? new Date(formData.end_at).toISOString() : undefined
        })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'create_failed')
      setFormData({ title: '', experiment_key: '', status: 'active', unit_type: 'agent', variants_json: defaultVariants, start_at: '', end_at: '' })
      await loadExperiments()
      await loadAssignments(data.experiment_key)
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '创建实验失败' : 'Failed to create experiment'))
    } finally {
      setBusy(false)
    }
  }

  const updateStatus = async (experimentKey: string, status: string) => {
    if (!token) return
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/experiments/${experimentKey}/status`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ status })
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'status_failed')
      }
      await loadExperiments()
      await loadAssignments(experimentKey)
    } catch (err: any) {
      alert(err?.message || (language === 'zh' ? '状态更新失败' : 'Failed to update status'))
    } finally {
      setBusy(false)
    }
  }

  const notificationVariants = experiments
    .find((experiment) => experiment.experiment_key === notificationForm.experiment_key)
    ?.variants || []

  const submitNotification = async (dryRun: boolean) => {
    if (!token || !notificationForm.experiment_key) return
    if (!dryRun) {
      const confirmed = window.confirm('Send this experiment notification now? This writes agent messages for the selected targets.')
      if (!confirmed) return
    }

    setNotificationBusy(true)
    try {
      const agentIds = notificationForm.agent_ids
        .split(',')
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isFinite(value) && value > 0)
      const res = await fetch(`${API_BASE}/experiments/${encodeURIComponent(notificationForm.experiment_key)}/notify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message_type: notificationForm.message_type,
          title: notificationForm.title,
          content: notificationForm.content,
          variant_key: notificationForm.variant_key || undefined,
          agent_ids: agentIds.length ? agentIds : undefined,
          dry_run: dryRun,
          limit: Number(notificationForm.limit) || 500,
          create_task: notificationForm.create_task,
          task_type: notificationForm.create_task ? notificationForm.task_type : undefined,
          data: {
            source: 'experiment_admin_page'
          }
        })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'notification_failed')
      setNotificationPreview(data)
      if (!dryRun) {
        setNotificationForm((prev) => ({ ...prev, dry_run: true }))
      }
    } catch (err: any) {
      alert(err?.message || 'Failed to send notification')
    } finally {
      setNotificationBusy(false)
    }
  }

  return (
    <div className="experiment-page">
      <div className="header">
        <div>
          <h1 className="header-title">{language === 'zh' ? '实验控制台' : 'Experiment Console'}</h1>
          <p className="header-subtitle">
            {language === 'zh' ? '创建分组、查看 assignment 规模和奖励机制' : 'Create assignments, inspect variant scale, and manage reward policy'}
          </p>
        </div>
      </div>

      <div className="experiment-grid">
        <section className="experiment-panel experiment-panel-main">
          <div className="experiment-section-header">
            <h2>{language === 'zh' ? '实验列表' : 'Experiments'}</h2>
            <button className="btn btn-ghost" onClick={loadExperiments}>{language === 'zh' ? '刷新' : 'Refresh'}</button>
          </div>
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : experiments.length === 0 ? (
            <div className="empty-state"><div className="empty-title">{language === 'zh' ? '暂无实验' : 'No experiments yet'}</div></div>
          ) : (
            <div className="experiment-list">
              {experiments.map((experiment) => (
                <article key={experiment.experiment_key} className="experiment-list-item">
                  <div>
                    <div className="experiment-kicker">
                      <span>{experiment.status}</span>
                      <span>{experiment.unit_type}</span>
                      <span>{experiment.experiment_key}</span>
                    </div>
                    <button className="experiment-list-title" onClick={() => loadAssignments(experiment.experiment_key)}>
                      {experiment.title}
                    </button>
                    <div className="experiment-list-meta">
                      {(experiment.variants || []).map((variant: any) => (
                        <span key={variant.key}>{variant.key} / {variant.weight}</span>
                      ))}
                    </div>
                  </div>
                  {token && (
                    <div className="experiment-actions">
                      <button className="btn btn-secondary" disabled={busy} onClick={() => updateStatus(experiment.experiment_key, experiment.status === 'active' ? 'paused' : 'active')}>
                        {experiment.status === 'active' ? (language === 'zh' ? '暂停' : 'Pause') : (language === 'zh' ? '启动' : 'Start')}
                      </button>
                      <button className="btn btn-ghost" onClick={() => loadAssignments(experiment.experiment_key)}>
                        {language === 'zh' ? '分组' : 'Assignments'}
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="experiment-panel">
          <div className="experiment-section-header"><h2>{language === 'zh' ? '创建实验' : 'Create Experiment'}</h2></div>
          {token ? (
            <form className="experiment-form" onSubmit={handleCreate}>
              <input className="form-input" value={formData.title} onChange={(event) => setFormData({ ...formData, title: event.target.value })} placeholder={language === 'zh' ? '实验标题' : 'Experiment title'} required />
              <input className="form-input" value={formData.experiment_key} onChange={(event) => setFormData({ ...formData, experiment_key: event.target.value })} placeholder="experiment-key" />
              <div className="experiment-form-row">
                <select className="form-select" value={formData.status} onChange={(event) => setFormData({ ...formData, status: event.target.value })}>
                  <option value="active">active</option>
                  <option value="draft">draft</option>
                  <option value="paused">paused</option>
                </select>
                <select className="form-select" value={formData.unit_type} onChange={(event) => setFormData({ ...formData, unit_type: event.target.value })}>
                  <option value="agent">agent</option>
                </select>
              </div>
              <div className="experiment-form-row">
                <input className="form-input" type="datetime-local" value={formData.start_at} onChange={(event) => setFormData({ ...formData, start_at: event.target.value })} />
                <input className="form-input" type="datetime-local" value={formData.end_at} onChange={(event) => setFormData({ ...formData, end_at: event.target.value })} />
              </div>
              <textarea className="form-textarea experiment-json" value={formData.variants_json} onChange={(event) => setFormData({ ...formData, variants_json: event.target.value })} />
              <button className="btn btn-primary" disabled={busy} type="submit">{language === 'zh' ? '保存实验' : 'Save experiment'}</button>
            </form>
          ) : (
            <div className="empty-state"><div className="empty-title">{language === 'zh' ? '登录后可创建实验' : 'Login to create experiments'}</div></div>
          )}
        </aside>
      </div>

      {token && (
        <section className="experiment-panel">
          <div className="experiment-section-header">
            <h2>{language === 'zh' ? '实验通知' : 'Experiment Notifications'}</h2>
            <span className="experiment-badge">{notificationPreview?.campaign_id || 'dry-run first'}</span>
          </div>
          <form
            className="experiment-form experiment-notification-form"
            onSubmit={(event) => {
              event.preventDefault()
              submitNotification(notificationForm.dry_run)
            }}
          >
            <div className="experiment-form-row">
              <select
                className="form-select"
                value={notificationForm.experiment_key}
                onChange={(event) => setNotificationForm({ ...notificationForm, experiment_key: event.target.value, variant_key: '' })}
                required
              >
                <option value="">{language === 'zh' ? '选择实验' : 'Select experiment'}</option>
                {experiments.map((experiment) => (
                  <option key={experiment.experiment_key} value={experiment.experiment_key}>{experiment.title || experiment.experiment_key}</option>
                ))}
              </select>
              <select
                className="form-select"
                value={notificationForm.variant_key}
                onChange={(event) => setNotificationForm({ ...notificationForm, variant_key: event.target.value })}
              >
                <option value="">{language === 'zh' ? '全部 variant' : 'All variants'}</option>
                {notificationVariants.map((variant: any) => (
                  <option key={variant.key} value={variant.key}>{variant.key}</option>
                ))}
              </select>
              <select
                className="form-select"
                value={notificationForm.message_type}
                onChange={(event) => setNotificationForm({ ...notificationForm, message_type: event.target.value })}
              >
                {experimentMessageTypes.map((messageType) => (
                  <option key={messageType} value={messageType}>{messageType}</option>
                ))}
              </select>
            </div>
            <input
              className="form-input"
              value={notificationForm.title}
              onChange={(event) => setNotificationForm({ ...notificationForm, title: event.target.value })}
              placeholder="Notification title"
              required
            />
            <textarea
              className="form-textarea"
              value={notificationForm.content}
              onChange={(event) => setNotificationForm({ ...notificationForm, content: event.target.value })}
              placeholder="Write the notification body in English."
              required
            />
            <div className="experiment-form-row">
              <input
                className="form-input"
                value={notificationForm.agent_ids}
                onChange={(event) => setNotificationForm({ ...notificationForm, agent_ids: event.target.value })}
                placeholder="Optional agent ids: 1,2,3"
              />
              <input
                className="form-input"
                type="number"
                min="1"
                max="5000"
                value={notificationForm.limit}
                onChange={(event) => setNotificationForm({ ...notificationForm, limit: Number(event.target.value) || 500 })}
              />
            </div>
            <div className="experiment-form-row">
              <label className="experiment-check">
                <input
                  type="checkbox"
                  checked={notificationForm.dry_run}
                  onChange={(event) => setNotificationForm({ ...notificationForm, dry_run: event.target.checked })}
                />
                <span>Dry run</span>
              </label>
              <label className="experiment-check">
                <input
                  type="checkbox"
                  checked={notificationForm.create_task}
                  onChange={(event) => setNotificationForm({ ...notificationForm, create_task: event.target.checked })}
                />
                <span>Create task</span>
              </label>
              <select
                className="form-select"
                disabled={!notificationForm.create_task}
                value={notificationForm.task_type}
                onChange={(event) => setNotificationForm({ ...notificationForm, task_type: event.target.value })}
              >
                <option value="join_challenge">join_challenge</option>
                <option value="join_team_mission">join_team_mission</option>
                <option value="submit_strategy">submit_strategy</option>
                <option value="submit_team_view">submit_team_view</option>
                <option value="review_results">review_results</option>
              </select>
            </div>
            <div className="experiment-actions">
              <button className="btn btn-secondary" type="button" disabled={notificationBusy} onClick={() => submitNotification(true)}>
                {language === 'zh' ? 'Dry run 预览' : 'Dry run preview'}
              </button>
              <button className="btn btn-primary" type="submit" disabled={notificationBusy || notificationForm.dry_run}>
                {language === 'zh' ? '确认发送' : 'Confirm send'}
              </button>
            </div>
          </form>
          {notificationPreview && (
            <div className="experiment-notification-preview">
              <div><span>Targets</span><strong>{notificationPreview.target_count}</strong></div>
              <div><span>Sent</span><strong>{notificationPreview.sent_count}</strong></div>
              <div><span>Online</span><strong>{notificationPreview.online_count}</strong></div>
              <div><span>Tasks</span><strong>{notificationPreview.task_created_count}</strong></div>
              <div><span>Skipped</span><strong>{notificationPreview.skipped_count}</strong></div>
              <div><span>Mode</span><strong>{notificationPreview.dry_run ? 'dry-run' : 'sent'}</strong></div>
              <pre>{JSON.stringify(notificationPreview.targets_preview || [], null, 2)}</pre>
            </div>
          )}
        </section>
      )}

      {selectedExperiment && (
        <section className="experiment-panel">
          <div className="experiment-section-header">
            <h2>{selectedExperiment.title}</h2>
            <span className="experiment-badge">{selectedExperiment.experiment_key}</span>
          </div>
          <div className="experiment-metrics">
            {(variantMetrics.length > 0 ? variantMetrics : variantCounts).map((row) => (
              <div key={row.variant_key}>
                <span>{row.variant_key}</span>
                <strong>{row.agent_count || row.count}</strong>
                {row.quality_score_avg !== undefined && (
                  <small>
                    {language === 'zh' ? '收益' : 'Return'} {Number(row.return_pct_avg || 0).toFixed(2)}%
                    {' · '}
                    {language === 'zh' ? '回撤' : 'DD'} {Number(row.max_drawdown_avg || 0).toFixed(2)}%
                    {' · '}
                    {language === 'zh' ? '交易' : 'Trades'} {Number(row.trade_count || 0)}
                    {' · '}
                    {language === 'zh' ? '质量' : 'Quality'} {Number(row.quality_score_avg || 0).toFixed(2)}
                  </small>
                )}
              </div>
            ))}
          </div>
          <div className="experiment-assignment-table">
            {assignments.slice(0, 60).map((assignment) => (
              <div key={assignment.id} className="experiment-assignment-row">
                <span>{assignment.unit_type}</span>
                <strong>{assignment.agent_name || assignment.unit_id}</strong>
                <span>{assignment.variant_key}</span>
                <span>{assignment.assignment_reason}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
