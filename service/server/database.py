"""
Database Module

数据库初始化、连接和管理
"""

import sqlite3
from typing import Optional, Dict, Any
import os

from config import DATABASE_URL


def get_db_connection():
    """Get database connection. Supports both SQLite and PostgreSQL."""
    if DATABASE_URL:
        # Use PostgreSQL (production)
        # For now, just use SQLite for development
        pass

    # Use SQLite
    db_path = os.path.join(os.path.dirname(__file__), "data", "clawtrader.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    return conn


def init_database():
    """Initialize database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

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
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            opened_at TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (leader_id) REFERENCES agents(id)
        )
    """)

    # Add market column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE positions ADD COLUMN market TEXT NOT NULL DEFAULT 'us-stock'")
    except:
        pass  # Column already exists

    # Add cash column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN cash REAL DEFAULT 100000.0")
    except:
        pass  # Column already exists

    # Add deposited column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE agents ADD COLUMN deposited REAL DEFAULT 0.0")
    except:
        pass  # Column already exists

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
        CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_message_type ON signals(message_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)
    """)

    conn.commit()
    conn.close()
    print("[INFO] Database initialized")
