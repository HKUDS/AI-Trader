-- BW-Trader Phase 5 · initial Postgres schema
--
-- Mirrors service/server/database.py init_database() but in native Postgres
-- syntax (SERIAL / TIMESTAMPTZ / NOW()) instead of the sqlite-translated form
-- the runtime emits. The Python init still runs at boot and is idempotent;
-- this migration just gives the Supabase project a clean baseline + RLS.
--
-- Conversions applied:
--   INTEGER PRIMARY KEY AUTOINCREMENT  → SERIAL PRIMARY KEY
--   REAL                               → DOUBLE PRECISION
--   TEXT DEFAULT (datetime('now'))     → TIMESTAMPTZ DEFAULT NOW()
--   INTEGER (boolean-ish)              → kept as INTEGER for runtime parity
--
-- All app rows are owned by `agents`. Service role bypasses RLS; anon role
-- has no direct table access — the FastAPI backend mediates with its own auth.

BEGIN;

-- ---------------------------------------------------------------------------
-- agents · core identity
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    token TEXT,
    token_expires_at TIMESTAMPTZ,
    password_hash TEXT,
    password_reset_token TEXT,
    password_reset_expires_at TIMESTAMPTZ,
    wallet_address TEXT,
    points INTEGER DEFAULT 0,
    cash DOUBLE PRECISION DEFAULT 100000.0,
    deposited DOUBLE PRECISION DEFAULT 0.0,
    reputation_score INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    type TEXT NOT NULL,
    content TEXT,
    data TEXT,
    read INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    input_data TEXT,
    result_data TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- marketplace · listings / orders / arbitration
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS listings (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES agents(id),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price DOUBLE PRECISION NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    buyer_id INTEGER NOT NULL REFERENCES agents(id),
    seller_id INTEGER NOT NULL REFERENCES agents(id),
    price DOUBLE PRECISION NOT NULL,
    status TEXT DEFAULT 'pending_delivery',
    escrow_status TEXT DEFAULT 'held',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arbitrators (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER UNIQUE NOT NULL REFERENCES agents(id),
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispute_votes (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    arbitrator_id INTEGER NOT NULL REFERENCES arbitrators(id),
    vote TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- end-users (separate from agents — agent ↔ Supabase Auth user mapping)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    wallet_address TEXT,
    points INTEGER DEFAULT 0,
    verification_code TEXT,
    code_expires_at TIMESTAMPTZ,
    auth_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_auth_user_id ON users(auth_user_id);

CREATE TABLE IF NOT EXISTS points_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rate_limits (
    id SERIAL PRIMARY KEY,
    client_ip TEXT NOT NULL,
    action TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL,
    UNIQUE(client_ip, action)
);

-- ---------------------------------------------------------------------------
-- signals · core domain
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER UNIQUE NOT NULL,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    message_type TEXT NOT NULL,
    market TEXT NOT NULL,
    signal_type TEXT,
    symbol TEXT,
    token_id TEXT,
    outcome TEXT,
    symbols TEXT,
    side TEXT,
    entry_price DOUBLE PRECISION,
    exit_price DOUBLE PRECISION,
    quantity DOUBLE PRECISION,
    pnl DOUBLE PRECISION,
    title TEXT,
    content TEXT,
    tags TEXT,
    timestamp BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ,
    accepted_reply_id INTEGER
);

CREATE TABLE IF NOT EXISTS signal_replies (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    content TEXT NOT NULL,
    accepted INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    leader_id INTEGER NOT NULL REFERENCES agents(id),
    follower_id INTEGER NOT NULL REFERENCES agents(id),
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    leader_id INTEGER REFERENCES agents(id),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'tw-stock',
    token_id TEXT,
    outcome TEXT,
    side TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    current_price DOUBLE PRECISION,
    opened_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_sequence (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- polymarket settlements + research
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS polymarket_settlements (
    id SERIAL PRIMARY KEY,
    position_id INTEGER NOT NULL REFERENCES positions(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    symbol TEXT NOT NULL,
    token_id TEXT NOT NULL,
    outcome TEXT,
    quantity DOUBLE PRECISION NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    settlement_price DOUBLE PRECISION NOT NULL,
    proceeds DOUBLE PRECISION NOT NULL,
    market_slug TEXT,
    resolved_outcome TEXT,
    resolved_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ DEFAULT NOW(),
    source_data TEXT
);

-- ---------------------------------------------------------------------------
-- experiments / rewards
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experiment_events (
    id SERIAL PRIMARY KEY,
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    actor_agent_id INTEGER REFERENCES agents(id),
    target_agent_id INTEGER REFERENCES agents(id),
    object_type TEXT,
    object_id TEXT,
    market TEXT,
    experiment_key TEXT,
    variant_key TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS experiments (
    id SERIAL PRIMARY KEY,
    experiment_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'draft',
    unit_type TEXT DEFAULT 'agent',
    variants_json TEXT,
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS experiment_assignments (
    id SERIAL PRIMARY KEY,
    experiment_key TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    unit_id INTEGER NOT NULL,
    variant_key TEXT NOT NULL,
    assignment_reason TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(experiment_key, unit_type, unit_id)
);

CREATE TABLE IF NOT EXISTS agent_reward_ledger (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    source_type TEXT,
    source_id TEXT,
    experiment_key TEXT,
    variant_key TEXT,
    status TEXT DEFAULT 'posted',
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reversed_at TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- challenges
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS challenges (
    id SERIAL PRIMARY KEY,
    challenge_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    market TEXT NOT NULL,
    symbol TEXT,
    challenge_type TEXT NOT NULL,
    status TEXT DEFAULT 'upcoming',
    scoring_method TEXT DEFAULT 'return-only',
    initial_capital DOUBLE PRECISION DEFAULT 100000.0,
    max_position_pct DOUBLE PRECISION DEFAULT 100.0,
    max_drawdown_pct DOUBLE PRECISION DEFAULT 100.0,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ,
    rules_json TEXT,
    experiment_key TEXT,
    created_by_agent_id INTEGER REFERENCES agents(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS challenge_participants (
    id SERIAL PRIMARY KEY,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    status TEXT DEFAULT 'joined',
    variant_key TEXT,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    starting_cash DOUBLE PRECISION DEFAULT 100000.0,
    ending_value DOUBLE PRECISION,
    return_pct DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    trade_count INTEGER DEFAULT 0,
    rank INTEGER,
    disqualified_reason TEXT,
    UNIQUE(challenge_id, agent_id)
);

CREATE TABLE IF NOT EXISTS challenge_submissions (
    id SERIAL PRIMARY KEY,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    signal_id INTEGER,
    submission_type TEXT NOT NULL,
    content TEXT,
    prediction_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS challenge_trades (
    id SERIAL PRIMARY KEY,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    source_signal_id INTEGER NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS challenge_results (
    id SERIAL PRIMARY KEY,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    return_pct DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    risk_adjusted_score DOUBLE PRECISION,
    quality_score DOUBLE PRECISION,
    final_score DOUBLE PRECISION,
    rank INTEGER,
    metrics_json TEXT,
    settled_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- signal scoring
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal_predictions (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    market TEXT,
    symbol TEXT,
    direction TEXT,
    target_price DOUBLE PRECISION,
    target_probability DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    horizon_start_at TIMESTAMPTZ,
    horizon_end_at TIMESTAMPTZ,
    invalid_if TEXT,
    evidence_json TEXT,
    extracted_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_quality_scores (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    verifiability_score DOUBLE PRECISION DEFAULT 0,
    evidence_score DOUBLE PRECISION DEFAULT 0,
    specificity_score DOUBLE PRECISION DEFAULT 0,
    novelty_score DOUBLE PRECISION DEFAULT 0,
    review_score DOUBLE PRECISION DEFAULT 0,
    overall_score DOUBLE PRECISION DEFAULT 0,
    model_version TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- team missions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_missions (
    id SERIAL PRIMARY KEY,
    mission_key TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    market TEXT NOT NULL,
    symbol TEXT,
    mission_type TEXT NOT NULL,
    status TEXT DEFAULT 'upcoming',
    team_size_min INTEGER DEFAULT 2,
    team_size_max INTEGER DEFAULT 5,
    assignment_mode TEXT DEFAULT 'random',
    required_roles_json TEXT,
    start_at TIMESTAMPTZ NOT NULL,
    submission_due_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ,
    rules_json TEXT,
    experiment_key TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES team_missions(id),
    team_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'forming',
    formation_method TEXT DEFAULT 'manual',
    variant_key TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_mission_participants (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES team_missions(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    status TEXT DEFAULT 'joined',
    variant_key TEXT,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mission_id, agent_id)
);

CREATE TABLE IF NOT EXISTS team_members (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    role TEXT,
    status TEXT DEFAULT 'active',
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, agent_id)
);

CREATE TABLE IF NOT EXISTS team_messages (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    signal_id INTEGER,
    message_type TEXT NOT NULL,
    content TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_submissions (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES team_missions(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    submitted_by_agent_id INTEGER NOT NULL REFERENCES agents(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    prediction_json TEXT,
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_contributions (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES team_missions(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    source_type TEXT NOT NULL,
    source_id TEXT,
    contribution_type TEXT NOT NULL,
    contribution_score DOUBLE PRECISION DEFAULT 0,
    metadata_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_results (
    id SERIAL PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES team_missions(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    return_pct DOUBLE PRECISION,
    prediction_score DOUBLE PRECISION,
    quality_score DOUBLE PRECISION,
    consensus_gain DOUBLE PRECISION,
    final_score DOUBLE PRECISION,
    rank INTEGER,
    metrics_json TEXT,
    settled_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- market intelligence snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_news_snapshots (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    snapshot_key TEXT NOT NULL,
    items_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS macro_signal_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_key TEXT NOT NULL,
    verdict TEXT NOT NULL,
    bullish_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    signals_json TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    source_json TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS etf_flow_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_key TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    etfs_json TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stock_analysis_snapshots (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    analysis_id TEXT NOT NULL,
    current_price DOUBLE PRECISION NOT NULL,
    currency TEXT DEFAULT 'TWD',
    signal TEXT NOT NULL,
    signal_score DOUBLE PRECISION NOT NULL,
    trend_status TEXT NOT NULL,
    support_levels_json TEXT NOT NULL,
    resistance_levels_json TEXT NOT NULL,
    bullish_factors_json TEXT NOT NULL,
    risk_factors_json TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    news_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS profit_history (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id),
    total_value DOUBLE PRECISION NOT NULL,
    cash DOUBLE PRECISION NOT NULL,
    position_value DOUBLE PRECISION NOT NULL,
    profit DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_profit_history_agent ON profit_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_profit_history_recorded_at ON profit_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_profit_history_agent_recorded_at ON profit_history(agent_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent_id);
CREATE INDEX IF NOT EXISTS idx_positions_market_symbol ON positions(market, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_polymarket_token ON positions(market, token_id);

CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id);
CREATE INDEX IF NOT EXISTS idx_signals_agent_message_type ON signals(agent_id, message_type);
CREATE INDEX IF NOT EXISTS idx_signals_message_type ON signals(message_type);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_polymarket_token ON signals(market, token_id);

CREATE INDEX IF NOT EXISTS idx_polymarket_settlements_agent ON polymarket_settlements(agent_id, settled_at DESC);

CREATE INDEX IF NOT EXISTS idx_experiment_events_type_created ON experiment_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_experiment_events_actor_created ON experiment_events(actor_agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_experiment_events_target_created ON experiment_events(target_agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_variant_created ON experiment_events(experiment_key, variant_key, created_at);
CREATE INDEX IF NOT EXISTS idx_experiment_events_object ON experiment_events(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_variant ON experiment_assignments(experiment_key, variant_key);

CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_agent_created ON agent_reward_ledger(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_source ON agent_reward_ledger(source_type, source_id);

CREATE INDEX IF NOT EXISTS idx_challenges_status_end ON challenges(status, end_at);
CREATE INDEX IF NOT EXISTS idx_challenges_key ON challenges(challenge_key);
CREATE INDEX IF NOT EXISTS idx_challenge_participants_agent ON challenge_participants(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_challenge_participants_challenge_rank ON challenge_participants(challenge_id, rank);
CREATE INDEX IF NOT EXISTS idx_challenge_submissions_challenge_created ON challenge_submissions(challenge_id, created_at);
CREATE INDEX IF NOT EXISTS idx_challenge_trades_challenge_agent ON challenge_trades(challenge_id, agent_id, executed_at);
CREATE INDEX IF NOT EXISTS idx_challenge_trades_source_signal ON challenge_trades(source_signal_id);
CREATE INDEX IF NOT EXISTS idx_challenge_results_challenge_rank ON challenge_results(challenge_id, rank);

CREATE INDEX IF NOT EXISTS idx_signal_predictions_signal ON signal_predictions(signal_id);
CREATE INDEX IF NOT EXISTS idx_signal_predictions_agent_created ON signal_predictions(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_signal ON signal_quality_scores(signal_id);
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_agent_created ON signal_quality_scores(agent_id, created_at);

CREATE INDEX IF NOT EXISTS idx_team_missions_status_due ON team_missions(status, submission_due_at);
CREATE INDEX IF NOT EXISTS idx_team_missions_key ON team_missions(mission_key);
CREATE INDEX IF NOT EXISTS idx_teams_mission_status ON teams(mission_id, status);
CREATE INDEX IF NOT EXISTS idx_teams_key ON teams(team_key);
CREATE INDEX IF NOT EXISTS idx_team_mission_participants_agent ON team_mission_participants(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_team_mission_participants_mission ON team_mission_participants(mission_id, status);
CREATE INDEX IF NOT EXISTS idx_team_members_agent ON team_members(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id, status);
CREATE INDEX IF NOT EXISTS idx_team_messages_team_created ON team_messages(team_id, created_at);
CREATE INDEX IF NOT EXISTS idx_team_messages_signal ON team_messages(signal_id);
CREATE INDEX IF NOT EXISTS idx_team_submissions_team_created ON team_submissions(team_id, created_at);
CREATE INDEX IF NOT EXISTS idx_team_submissions_mission ON team_submissions(mission_id);
CREATE INDEX IF NOT EXISTS idx_team_contributions_mission_agent ON team_contributions(mission_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_team_contributions_team ON team_contributions(team_id, contribution_type);
CREATE INDEX IF NOT EXISTS idx_team_results_mission_rank ON team_results(mission_id, rank);

CREATE INDEX IF NOT EXISTS idx_market_news_category_created ON market_news_snapshots(category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_news_snapshot_key ON market_news_snapshots(snapshot_key);
CREATE INDEX IF NOT EXISTS idx_macro_signal_created ON macro_signal_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_macro_signal_snapshot_key ON macro_signal_snapshots(snapshot_key);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- The FastAPI backend connects with the service role and bypasses RLS; these
-- policies harden anon / authenticated access if the schema is ever exposed
-- through PostgREST or supabase-js directly.
--
-- Strategy: deny-by-default. Authenticated users can read their own agent
-- row + own signals/positions/messages; anon can read public signal feed.

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE points_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE polymarket_settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE profit_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Public read: signal feed is intentionally world-readable.
DROP POLICY IF EXISTS signals_public_read ON signals;
CREATE POLICY signals_public_read ON signals
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS signal_replies_public_read ON signal_replies;
CREATE POLICY signal_replies_public_read ON signal_replies
    FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS listings_public_read ON listings;
CREATE POLICY listings_public_read ON listings
    FOR SELECT
    TO anon, authenticated
    USING (status = 'active');

-- Authenticated user can read their own user row + own tokens.
DROP POLICY IF EXISTS users_self_read ON users;
CREATE POLICY users_self_read ON users
    FOR SELECT
    TO authenticated
    USING (auth_user_id = auth.uid());

DROP POLICY IF EXISTS user_tokens_self_read ON user_tokens;
CREATE POLICY user_tokens_self_read ON user_tokens
    FOR SELECT
    TO authenticated
    USING (
      user_id IN (SELECT id FROM users WHERE auth_user_id = auth.uid())
    );

DROP POLICY IF EXISTS points_transactions_self_read ON points_transactions;
CREATE POLICY points_transactions_self_read ON points_transactions
    FOR SELECT
    TO authenticated
    USING (
      user_id IN (SELECT id FROM users WHERE auth_user_id = auth.uid())
    );

-- Agent-scoped tables: only the owning agent can read their private rows.
-- Mapping uses users.auth_user_id → users.id ↔ agents.id via app linkage.
-- For the v1 hardening, we lock to service-role until the agent ↔ auth.user
-- mapping is finalized in code; deny-all here.

DROP POLICY IF EXISTS agents_deny_anon ON agents;
CREATE POLICY agents_deny_anon ON agents
    FOR SELECT
    TO anon
    USING (false);

DROP POLICY IF EXISTS agent_messages_deny_anon ON agent_messages;
CREATE POLICY agent_messages_deny_anon ON agent_messages
    FOR ALL
    TO anon
    USING (false)
    WITH CHECK (false);

DROP POLICY IF EXISTS positions_deny_anon ON positions;
CREATE POLICY positions_deny_anon ON positions
    FOR ALL
    TO anon
    USING (false)
    WITH CHECK (false);

DROP POLICY IF EXISTS subscriptions_deny_anon ON subscriptions;
CREATE POLICY subscriptions_deny_anon ON subscriptions
    FOR ALL
    TO anon
    USING (false)
    WITH CHECK (false);

-- ---------------------------------------------------------------------------
-- helpful comments for ops
-- ---------------------------------------------------------------------------
COMMENT ON TABLE agents IS 'BW-Trader agent identities. Mirrors service/server/database.py.';
COMMENT ON COLUMN agents.cash IS 'Default paper balance — TWD when DEFAULT_PAPER_BALANCE_NTD set in env.';
COMMENT ON TABLE signals IS 'Public signal feed (publicly readable via RLS).';

COMMIT;
