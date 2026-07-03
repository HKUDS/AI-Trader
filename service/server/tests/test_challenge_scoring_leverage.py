import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from challenge_scoring import score_agent_trades


def _challenge(**overrides):
    challenge = {
        'initial_capital': 10000.0,
        'max_position_pct': 100.0,
        'max_drawdown_pct': 100.0,
        'scoring_method': 'return-only',
        'rules_json': None,
    }
    challenge.update(overrides)
    return challenge


def _participant(starting_cash=10000.0):
    return {'agent_id': 1, 'starting_cash': starting_cash, 'status': 'joined'}


def _trade(trade_id, side, symbol, price, quantity, executed_at):
    return {
        'id': trade_id,
        'side': side,
        'market': 'us-stock',
        'symbol': symbol,
        'price': price,
        'quantity': quantity,
        'executed_at': executed_at,
    }


class ChallengeScoringLeverageTests(unittest.TestCase):
    """Regression: challenge replay must enforce the cash constraint.

    Live trading rejects buys/shorts whose value exceeds available cash, but
    the challenge replay applied them with no cash check, letting cash go
    negative silently. The per-symbol max_position_pct guard does not catch
    exposure spread across several symbols, so a participant trading a larger
    live account inside a smaller-capital challenge gained hidden leverage
    that inflated return_pct against starting_cash.
    """

    def test_overspending_across_symbols_is_disqualified(self):
        # 10k starting cash; two 6k buys = 12k deployed, cash -2k.
        # Each position is only 60% of equity so max_position_pct passes;
        # before the fix this scored return_pct on 1.2x hidden leverage.
        trades = [
            _trade(1, 'buy', 'AAA', 100.0, 60, '2026-01-02T15:00:00Z'),
            _trade(2, 'buy', 'BBB', 100.0, 60, '2026-01-02T15:05:00Z'),
        ]
        result = score_agent_trades(_challenge(), _participant(), trades)
        self.assertEqual(result['disqualified_reason'], 'insufficient_challenge_cash:BBB')
        self.assertIsNone(result['final_score'])

    def test_short_escrow_is_cash_bounded(self):
        # Shorts escrow price * quantity in the live model, so they are
        # bounded by cash exactly like buys.
        trades = [
            _trade(1, 'short', 'AAA', 100.0, 60, '2026-01-02T15:00:00Z'),
            _trade(2, 'short', 'BBB', 100.0, 60, '2026-01-02T15:05:00Z'),
        ]
        result = score_agent_trades(_challenge(), _participant(), trades)
        self.assertEqual(result['disqualified_reason'], 'insufficient_challenge_cash:BBB')
        self.assertIsNone(result['final_score'])

    def test_full_deployment_without_overspend_is_allowed(self):
        # Spending exactly the starting cash must not trip the guard.
        trades = [
            _trade(1, 'buy', 'AAA', 100.0, 100, '2026-01-02T15:00:00Z'),
            _trade(2, 'sell', 'AAA', 110.0, 100, '2026-01-03T15:00:00Z'),
        ]
        result = score_agent_trades(_challenge(), _participant(), trades)
        self.assertIsNone(result['disqualified_reason'])
        self.assertAlmostEqual(result['return_pct'], 10.0, places=6)
        self.assertAlmostEqual(result['final_score'], 10.0, places=6)

    def test_honest_partial_deployment_unchanged(self):
        trades = [
            _trade(1, 'buy', 'AAA', 100.0, 60, '2026-01-02T15:00:00Z'),
            _trade(2, 'sell', 'AAA', 120.0, 60, '2026-01-03T15:00:00Z'),
        ]
        result = score_agent_trades(_challenge(), _participant(), trades)
        self.assertIsNone(result['disqualified_reason'])
        self.assertAlmostEqual(result['return_pct'], 12.0, places=6)


if __name__ == '__main__':
    unittest.main()
