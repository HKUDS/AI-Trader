#!/usr/bin/env python3
"""
One-time script to fix an agent with absurd profit/cash (e.g. from bad Polymarket price data).

Usage (from repo root):
  cd service/server && python -c "
from scripts.fix_agent_profit import fix_agent_by_name
fix_agent_by_name('BotTrade23')
"

Or run from service/server:
  python scripts/fix_agent_profit.py BotTrade23
"""
import os
import sys

# Allow importing from parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection

INITIAL_CAPITAL = 100000.0


def fix_agent_by_name(agent_name: str) -> bool:
    """Reset agent cash to initial capital and delete their profit_history (cleans chart)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, cash, deposited FROM agents WHERE name = ?", (agent_name,))
    row = cursor.fetchone()
    if not row:
        print(f"Agent '{agent_name}' not found.")
        conn.close()
        return False
    agent_id = row["id"]
    old_cash = row["cash"]
    old_deposited = row["deposited"]
    cursor.execute("UPDATE agents SET cash = ?, deposited = 0.0 WHERE id = ?", (INITIAL_CAPITAL, agent_id))
    cursor.execute("DELETE FROM profit_history WHERE agent_id = ?", (agent_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"Fixed agent id={agent_id} name={agent_name}: cash {old_cash} -> {INITIAL_CAPITAL}, deposited {old_deposited} -> 0, deleted {deleted} profit_history rows.")
    return True


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "BotTrade23"
    fix_agent_by_name(name)
