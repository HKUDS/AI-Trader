    # Agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            token TEXT,
            token_expires_at TEXT,
            password_hash TEXT,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            cash REAL DEFAULT 100000.0,
            deposited REAL DEFAULT 0.0,
            reputation_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Agent messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            content TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Agent tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            input_data TEXT,
            result_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Listings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (seller_id) REFERENCES agents(id)
        )
    """)

    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT DEFAULT 'pending_delivery',
            escrow_status TEXT DEFAULT 'held',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (listing_id) REFERENCES listings(id),
            FOREIGN KEY (buyer_id) REFERENCES agents(id),
            FOREIGN KEY (seller_id) REFERENCES agents(id)
        )
    """)

    # Arbitrators table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arbitrators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Dispute votes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dispute_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            arbitrator_id INTEGER NOT NULL,
            vote TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (arbitrator_id) REFERENCES arbitrators(id)
        )
    """)

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            verification_code TEXT,
            code_expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Points transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS points_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # User tokens table (for session management)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Rate limits table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_ip TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            window_start TEXT NOT NULL,
            UNIQUE(client_ip, action)
        )
    """)

    # Signals table - stores trading signals from providers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL,
            message_type TEXT NOT NULL,  -- 'strategy', 'operation', 'discussion'
            market TEXT NOT NULL,  -- 'us-stock', 'a-stock', 'crypto', 'polymarket', etc.
            signal_type TEXT,  -- 'position', 'trade', 'realtime' (for operation type)
            symbol TEXT,
            token_id TEXT,
            outcome TEXT,
            symbols TEXT,  -- JSON array for multiple symbols
            side TEXT,  -- 'long', 'short'
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl REAL,
            title TEXT,  -- For strategy/discussion
            content TEXT,
            tags TEXT,  -- JSON array for tags
            timestamp INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            executed_at TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Signal replies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            accepted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (signal_id) REFERENCES signals(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    # Subscriptions table (for copy trading)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_id INTEGER NOT NULL,
            follower_id INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (leader_id) REFERENCES agents(id),
            FOREIGN KEY (follower_id) REFERENCES agents(id)
        )
    """)

    # Positions table - stores copied positions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            leader_id INTEGER,  -- null if self-opened
            symbol TEXT NOT NULL,
            market TEXT NOT NULL DEFAULT 'us-stock',
            token_id TEXT,
            outcome TEXT,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            opened_at TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (leader_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_sequence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("SELECT COALESCE(MAX(signal_id), 0) AS max_signal_id FROM signals")
    max_signal_id = int(cursor.fetchone()["max_signal_id"] or 0)
    cursor.execute("SELECT COALESCE(MAX(id), 0) AS max_sequence_id FROM signal_sequence")
    max_sequence_id = int(cursor.fetchone()["max_sequence_id"] or 0)
    if max_sequence_id < max_signal_id:
        cursor.executemany(
            "INSERT INTO signal_sequence DEFAULT VALUES",
            [()] * (max_signal_id - max_sequence_id)
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polymarket_settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome TEXT,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            settlement_price REAL NOT NULL,
            proceeds REAL NOT NULL,
            market_slug TEXT,
            resolved_outcome TEXT,
            resolved_at TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            source_data TEXT,
            FOREIGN KEY (position_id) REFERENCES positions(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            actor_agent_id INTEGER,
            target_agent_id INTEGER,
            object_type TEXT,
            object_id TEXT,
            market TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (actor_agent_id) REFERENCES agents(id),
            FOREIGN KEY (target_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            unit_type TEXT DEFAULT 'agent',
            variants_json TEXT,
            start_at TEXT,
            end_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiment_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_key TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            unit_id INTEGER NOT NULL,
            variant_key TEXT NOT NULL,
            assignment_reason TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(experiment_key, unit_type, unit_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_reward_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            source_type TEXT,
            source_id TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            status TEXT DEFAULT 'posted',
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            reversed_at TEXT,
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            market TEXT NOT NULL,
            symbol TEXT,
            challenge_type TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming',
            scoring_method TEXT DEFAULT 'return-only',
            initial_capital REAL DEFAULT 100000.0,
            max_position_pct REAL DEFAULT 100.0,
            max_drawdown_pct REAL DEFAULT 100.0,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_by_agent_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (created_by_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT (datetime('now')),
            starting_cash REAL DEFAULT 100000.0,
            ending_value REAL,
            return_pct REAL,
            max_drawdown REAL,
            trade_count INTEGER DEFAULT 0,
            rank INTEGER,
            disqualified_reason TEXT,
            UNIQUE(challenge_id, agent_id),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            signal_id INTEGER,
            submission_type TEXT NOT NULL,
            content TEXT,
            prediction_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            source_signal_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            executed_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS challenge_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            return_pct REAL,
            max_drawdown REAL,
            risk_adjusted_score REAL,
            quality_score REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (challenge_id) REFERENCES challenges(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            market TEXT,
            symbol TEXT,
            direction TEXT,
            target_price REAL,
            target_probability REAL,
            confidence REAL,
            horizon_start_at TEXT,
            horizon_end_at TEXT,
            invalid_if TEXT,
            evidence_json TEXT,
            extracted_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            verifiability_score REAL DEFAULT 0,
            evidence_score REAL DEFAULT 0,
            specificity_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            review_score REAL DEFAULT 0,
            overall_score REAL DEFAULT 0,
            model_version TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            start_at TEXT NOT NULL,
            submission_due_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'forming',
            formation_method TEXT DEFAULT 'manual',
            variant_key TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_mission_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT (datetime('now')),
            UNIQUE(mission_id, agent_id),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            role TEXT,
            status TEXT DEFAULT 'active',
            joined_at TEXT DEFAULT (datetime('now')),
            UNIQUE(team_id, agent_id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            signal_id INTEGER,
            message_type TEXT NOT NULL,
            content TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            submitted_by_agent_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            prediction_json TEXT,
            confidence REAL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (submitted_by_agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            contribution_type TEXT NOT NULL,
            contribution_score REAL DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            return_pct REAL,
            prediction_score REAL,
            quality_score REAL,
            consensus_gain REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (mission_id) REFERENCES team_missions(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_news_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            snapshot_key TEXT NOT NULL,
            items_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_signal_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_key TEXT NOT NULL,
            verdict TEXT NOT NULL,
            bullish_count INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0,
            signals_json TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            source_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS etf_flow_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_key TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            etfs_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_analysis_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            analysis_id TEXT NOT NULL,
            current_price REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            signal TEXT NOT NULL,
            signal_score REAL NOT NULL,
            trend_status TEXT NOT NULL,
            support_levels_json TEXT NOT NULL,
            resistance_levels_json TEXT NOT NULL,
            bullish_factors_json TEXT NOT NULL,
            risk_factors_json TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            news_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Add market column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN market TEXT NOT NULL DEFAULT 'us-stock'")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN token_id TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN outcome TEXT")
    except Exception:
        pass

    # Add cash column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN cash REAL DEFAULT 100000.0")
    except Exception:
        pass

    # Add deposited column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN deposited REAL DEFAULT 0.0")
    except Exception:
        pass

    # Add password_reset_token column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN password_reset_token TEXT")
    except Exception:
        pass

    # Add password_reset_expires_at column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN password_reset_expires_at TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN token_id TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN outcome TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN accepted_reply_id INTEGER")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE signal_replies ADD COLUMN accepted INTEGER DEFAULT 0")
    except Exception:
        pass

    # Profit history table - tracks agent profit over time
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            position_value REAL NOT NULL,
            profit REAL NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (agent_id) REFERENCES agents(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_agent ON profit_history(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_recorded_at
        ON profit_history(recorded_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_profit_history_agent_recorded_at
        ON profit_history(agent_id, recorded_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_market_symbol
        ON positions(market, symbol)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_polymarket_token
        ON positions(market, token_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_agent_message_type
        ON signals(agent_id, message_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_message_type ON signals(message_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_polymarket_token
        ON signals(market, token_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_polymarket_settlements_agent
        ON polymarket_settlements(agent_id, settled_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_type_created
        ON experiment_events(event_type, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_actor_created
        ON experiment_events(actor_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_target_created
        ON experiment_events(target_agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_variant_created
        ON experiment_events(experiment_key, variant_key, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_events_object
        ON experiment_events(object_type, object_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_variant
        ON experiment_assignments(experiment_key, variant_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_agent_created
        ON agent_reward_ledger(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_source
        ON agent_reward_ledger(source_type, source_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenges_status_end
        ON challenges(status, end_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenges_key
        ON challenges(challenge_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_participants_agent
        ON challenge_participants(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_participants_challenge_rank
        ON challenge_participants(challenge_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_submissions_challenge_created
        ON challenge_submissions(challenge_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_trades_challenge_agent
        ON challenge_trades(challenge_id, agent_id, executed_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_trades_source_signal
        ON challenge_trades(source_signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenge_results_challenge_rank
        ON challenge_results(challenge_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_predictions_signal
        ON signal_predictions(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_predictions_agent_created
        ON signal_predictions(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_signal
        ON signal_quality_scores(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_agent_created
        ON signal_quality_scores(agent_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_missions_status_due
        ON team_missions(status, submission_due_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_missions_key
        ON team_missions(mission_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_teams_mission_status
        ON teams(mission_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_teams_key
        ON teams(team_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_mission_participants_agent
        ON team_mission_participants(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_mission_participants_mission
        ON team_mission_participants(mission_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_members_agent
        ON team_members(agent_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_members_team
        ON team_members(team_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_messages_team_created
        ON team_messages(team_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_messages_signal
        ON team_messages(signal_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_submissions_team_created
        ON team_submissions(team_id, created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_submissions_mission
        ON team_submissions(mission_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_contributions_mission_agent
        ON team_contributions(mission_id, agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_contributions_team
        ON team_contributions(team_id, contribution_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_team_results_mission_rank
        ON team_results(mission_id, rank)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_news_category_created
        ON market_news_snapshots(category, created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_news_snapshot_key
        ON market_news_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_macro_signal_created
        ON macro_signal_snapshots(created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_macro_signal_snapshot_key
        ON macro_signal_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_flow_created
        ON etf_flow_snapshots(created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_etf_flow_snapshot_key
        ON etf_flow_snapshots(snapshot_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_symbol_created
        ON stock_analysis_snapshots(symbol, created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_analysis_market_symbol
        ON stock_analysis_snapshots(market, symbol)
    """)

    if not using_postgres():
        conn.commit()
