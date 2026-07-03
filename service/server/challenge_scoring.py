"""Challenge portfolio replay and scoring."""

from __future__ import annotations

import json
import math
from typing import Any

PositionKey = tuple[str, str, str, str]


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None and not isinstance(row, dict) else (row or {})


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) else default


def _rules(challenge: dict[str, Any]) -> dict[str, Any]:
    raw = challenge.get('rules_json')
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _position_value(position: dict[str, Any], mark_price: float) -> float:
    qty = _safe_float(position.get('quantity'))
    entry = _safe_float(position.get('entry_price'))
    if qty >= 0:
        return mark_price * qty
    return (2 * entry - mark_price) * abs(qty)


def _position_key(market: str, symbol: str, token_id: Any = None, outcome: Any = None) -> PositionKey:
    token = str(token_id or '').strip()
    resolved_outcome = str(outcome or '').strip()
    if market != 'polymarket':
        token = ''
        resolved_outcome = ''
    return (market, symbol, token, resolved_outcome)


def _mark_price(marks: dict[Any, float], key: PositionKey) -> float:
    mark = marks.get(key)
    if mark is None:
        mark = marks.get((key[0], key[1]))
    return _safe_float(mark, 0.0)


def _portfolio_value(cash: float, positions: dict[PositionKey, dict[str, Any]], marks: dict[Any, float]) -> float:
    value = cash
    for key, position in positions.items():
        mark_price = _mark_price(marks, key) or _safe_float(position.get('entry_price'))
        value += _position_value(position, mark_price)
    return value


def score_agent_trades(
    challenge: Any,
    participant: Any,
    trades: list[Any],
    mark_prices: dict[Any, float] | None = None,
    mark_timestamp: str | None = None,
) -> dict[str, Any]:
    challenge_data = _row_dict(challenge)
    participant_data = _row_dict(participant)
    rules = _rules(challenge_data)

    starting_cash = _safe_float(
        participant_data.get('starting_cash'),
        _safe_float(challenge_data.get('initial_capital'), 100000.0),
    )
    max_position_pct = _safe_float(challenge_data.get('max_position_pct'), 100.0)
    max_drawdown_pct = _safe_float(challenge_data.get('max_drawdown_pct'), 100.0)

    cash = starting_cash
    positions: dict[PositionKey, dict[str, Any]] = {}
    marks: dict[Any, float] = {}
    equity_curve = [starting_cash]
    peak = starting_cash
    max_drawdown = 0.0
    disqualified_reason = participant_data.get('disqualified_reason')

    def update_drawdown(equity: float) -> None:
        nonlocal peak, max_drawdown
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)

    ordered_trades = sorted(
        [_row_dict(trade) for trade in trades],
        key=lambda item: (item.get('executed_at') or '', item.get('id') or 0),
    )

    for trade in ordered_trades:
        if disqualified_reason:
            break

        side = str(trade.get('side') or '').lower()
        market = str(trade.get('market') or '')
        symbol = str(trade.get('symbol') or '')
        token_id = str(trade.get('token_id') or '').strip() or None
        outcome = str(trade.get('outcome') or '').strip() or None
        key = _position_key(market, symbol, token_id, outcome)
        price = _safe_float(trade.get('price'))
        quantity = _safe_float(trade.get('quantity'))

        if price <= 0 or quantity <= 0 or not side:
            disqualified_reason = 'invalid_trade_snapshot'
            break

        marks[key] = price
        current = positions.get(key)
        current_qty = _safe_float(current.get('quantity')) if current else 0.0
        current_entry = _safe_float(current.get('entry_price')) if current else 0.0

        if side == 'buy':
            if current_qty < 0:
                disqualified_reason = f'buy_used_while_short:{symbol}'
                break
            cash -= price * quantity
            if cash < -1e-9:
                # Live trading rejects buys that exceed available cash; replaying
                # with the challenge's starting cash must enforce the same rule,
                # otherwise spreading buys across symbols yields hidden leverage
                # that inflates return_pct against starting_cash.
                disqualified_reason = f'insufficient_challenge_cash:{symbol}'
                break
            new_qty = current_qty + quantity
            new_entry = (
                ((current_qty * current_entry) + (quantity * price)) / new_qty
                if current_qty > 0
                else price
            )
            positions[key] = {
                'market': market,
                'symbol': symbol,
                'token_id': token_id,
                'outcome': outcome,
                'quantity': new_qty,
                'entry_price': new_entry,
            }
        elif side == 'sell':
            if current_qty <= 0 or quantity > current_qty + 1e-12:
                disqualified_reason = f'sell_exceeds_challenge_long:{symbol}'
                break
            cash += price * quantity
            new_qty = current_qty - quantity
            if new_qty <= 1e-12:
                positions.pop(key, None)
            else:
                positions[key] = {
                    'market': market,
                    'symbol': symbol,
                    'token_id': token_id,
                    'outcome': outcome,
                    'quantity': new_qty,
                    'entry_price': current_entry,
                }
        elif side == 'short':
            if current_qty > 0:
                disqualified_reason = f'short_used_while_long:{symbol}'
                break
            cash -= price * quantity
            if cash < -1e-9:
                # Shorts escrow price * quantity in the live model, so they are
                # cash-bounded exactly like buys.
                disqualified_reason = f'insufficient_challenge_cash:{symbol}'
                break
            new_qty = current_qty - quantity
            current_short_qty = abs(current_qty)
            new_entry = (
                ((current_short_qty * current_entry) + (quantity * price)) / abs(new_qty)
                if current_qty < 0
                else price
            )
            positions[key] = {
                'market': market,
                'symbol': symbol,
                'token_id': token_id,
                'outcome': outcome,
                'quantity': new_qty,
                'entry_price': new_entry,
            }
        elif side == 'cover':
            if current_qty >= 0 or quantity > abs(current_qty) + 1e-12:
                disqualified_reason = f'cover_exceeds_challenge_short:{symbol}'
                break
            cash += ((2 * current_entry) - price) * quantity
            new_qty = current_qty + quantity
            if new_qty >= -1e-12:
                positions.pop(key, None)
            else:
                positions[key] = {
                    'market': market,
                    'symbol': symbol,
                    'token_id': token_id,
                    'outcome': outcome,
                    'quantity': new_qty,
                    'entry_price': current_entry,
                }
        else:
            disqualified_reason = f'unsupported_side:{side}'
            break

        equity = _portfolio_value(cash, positions, marks)
        equity_curve.append(equity)
        update_drawdown(equity)

        if max_position_pct > 0 and equity > 0:
            max_notional = max((abs(pos['quantity']) * (_mark_price(marks, pos_key) or pos['entry_price'])) for pos_key, pos in positions.items()) if positions else 0.0
            if (max_notional / equity) * 100 > max_position_pct + 1e-9:
                disqualified_reason = 'max_position_pct_exceeded'
                break

    live_marks: list[dict[str, Any]] = []
    if mark_prices and positions:
        for key in positions:
            live_mark = _mark_price(mark_prices, key)
            if live_mark <= 0:
                continue
            marks[key] = live_mark
            live_marks.append({
                'market': key[0],
                'symbol': key[1],
                'token_id': key[2] or None,
                'outcome': key[3] or None,
                'price': live_mark,
            })
        if live_marks:
            equity = _portfolio_value(cash, positions, marks)
            equity_curve.append(equity)
            update_drawdown(equity)

    ending_value = _portfolio_value(cash, positions, marks)
    return_pct = ((ending_value - starting_cash) / starting_cash * 100) if starting_cash > 0 else 0.0

    if rules.get('disqualify_on_drawdown') and max_drawdown_pct > 0 and max_drawdown > max_drawdown_pct + 1e-9:
        disqualified_reason = disqualified_reason or 'max_drawdown_pct_exceeded'

    scoring_method = str(challenge_data.get('scoring_method') or 'return-only').lower().replace('_', '-')
    allowed_drawdown = _safe_float(rules.get('allowed_drawdown'), max_drawdown_pct)
    drawdown_penalty = _safe_float(rules.get('drawdown_penalty'), 1.0)
    risk_adjusted_score = return_pct - max(0.0, max_drawdown - allowed_drawdown) * drawdown_penalty
    final_score = risk_adjusted_score if scoring_method == 'risk-adjusted' else return_pct

    if participant_data.get('status') == 'disqualified':
        disqualified_reason = disqualified_reason or 'manual_disqualification'

    metrics = {
        'cash': cash,
        'positions': list(positions.values()),
        'equity_curve': equity_curve,
        'marked_to_market': bool(live_marks),
        'mark_timestamp': mark_timestamp if live_marks else None,
        'live_marks': live_marks,
        'scoring_method': scoring_method,
        'allowed_drawdown': allowed_drawdown,
        'drawdown_penalty': drawdown_penalty,
    }

    return {
        'agent_id': participant_data.get('agent_id'),
        'starting_cash': starting_cash,
        'ending_value': ending_value,
        'return_pct': return_pct,
        'max_drawdown': max_drawdown,
        'risk_adjusted_score': risk_adjusted_score,
        'quality_score': 0.0,
        'final_score': None if disqualified_reason or not ordered_trades else final_score,
        'trade_count': len(ordered_trades),
        'disqualified_reason': disqualified_reason,
        'metrics': metrics,
    }


def rank_scored_results(scored_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_candidates = [
        result
        for result in scored_results
        if (
            not result.get('disqualified_reason')
            and result.get('final_score') is not None
            and int(result.get('trade_count') or 0) > 0
        )
    ]
    ranked_candidates.sort(key=lambda item: item['final_score'], reverse=True)
    rank_by_agent = {item['agent_id']: index + 1 for index, item in enumerate(ranked_candidates)}

    ranked_results = []
    for result in scored_results:
        ranked = dict(result)
        ranked['rank'] = rank_by_agent.get(result.get('agent_id'))
        ranked_results.append(ranked)
    return ranked_results


def score_challenge_results(
    challenge: Any,
    participants: list[Any],
    trades_by_agent: dict[int, list[Any]],
    mark_prices: dict[Any, float] | None = None,
    mark_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    scored = [
        score_agent_trades(
            challenge,
            participant,
            trades_by_agent.get(_row_dict(participant).get('agent_id'), []),
            mark_prices=mark_prices,
            mark_timestamp=mark_timestamp,
        )
        for participant in participants
    ]
    return rank_scored_results(scored)
