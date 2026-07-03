"""Challenge creation, participation, submission, dedicated trading, and settlement."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from challenge_scoring import score_agent_trades, score_challenge_results
from database import begin_write_transaction, get_db_connection
from experiment_events import record_event
from experiments import experiment_accepts_unit, normalize_variants, stable_bucket
from rewards import grant_agent_reward
from routes_shared import agent_identity_status, agent_is_verified, utc_now_iso_z


class ChallengeError(ValueError):
    pass


class ChallengeNotFound(ChallengeError):
    pass


DEFAULT_CHALLENGE_REWARDS = {'1': 100, '2': 50, '3': 25}
SUPPORTED_SCORING_METHODS = {'return-only', 'risk-adjusted'}
SUPPORTED_CHALLENGE_TRACKS = {'crypto', 'us-stock', 'polymarket'}
SUPPORTED_CHALLENGE_MODES = {'individual', 'team', 'hybrid'}
AUTHORITATIVE_CHALLENGE_PRICE_MARKETS = {'crypto', 'us-stock', 'polymarket'}
POLYMARKET_CHALLENGE_CLOCK_SKEW_SECONDS = 300


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None and not isinstance(row, dict) else (row or {})


def _model_dump(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if hasattr(data, 'model_dump'):
        return data.model_dump()
    return dict(data)


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value is None or value == '':
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception as exc:
        raise ChallengeError(f'Invalid datetime: {value}') from exc


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _live_mark_timestamp(challenge: dict[str, Any]) -> Optional[str]:
    if challenge.get('status') != 'active':
        return None
    try:
        now = datetime.now(timezone.utc)
        start_dt = _parse_dt(challenge.get('start_at'))
        end_dt = _parse_dt(challenge.get('end_at'))
    except Exception:
        return None
    if start_dt and now < start_dt:
        return None
    if end_dt and now >= end_dt:
        return None
    return _iso(now)


def _fetch_live_mark_prices(scored_results: list[dict[str, Any]], mark_timestamp: str) -> dict[tuple[str, str, str, str], float]:
    position_keys: set[tuple[str, str, str, str]] = set()
    for result in scored_results:
        metrics = result.get('metrics') or {}
        for position in metrics.get('positions') or []:
            market = str(position.get('market') or '').strip()
            symbol = str(position.get('symbol') or '').strip()
            token_id = str(position.get('token_id') or '').strip()
            outcome = str(position.get('outcome') or '').strip()
            quantity = position.get('quantity')
            try:
                quantity_float = float(quantity)
            except Exception:
                quantity_float = 0.0
            if market and symbol and abs(quantity_float) > 1e-12:
                if market == 'polymarket' and not (token_id or outcome):
                    continue
                position_keys.add((market, symbol, token_id, outcome))

    if not position_keys:
        return {}

    try:
        import price_fetcher
        from price_fetcher import price_fetch_logging
    except Exception:
        return {}

    mark_prices: dict[tuple[str, str, str, str], float] = {}
    with price_fetch_logging(False):
        for market, symbol, token_id, outcome in sorted(position_keys):
            try:
                price = price_fetcher.get_price_from_market(
                    symbol,
                    mark_timestamp,
                    market,
                    token_id=token_id or None,
                    outcome=outcome or None,
                )
                parsed = float(price) if price is not None else 0.0
            except Exception:
                continue
            if math.isfinite(parsed) and parsed > 0:
                mark_prices[(market, symbol, token_id, outcome)] = parsed
    return mark_prices


def _resolve_polymarket_challenge_contract(symbol: str, token_id: Any = None, outcome: Any = None) -> tuple[Optional[str], Optional[str]]:
    resolved_token_id = str(token_id or '').strip() or None
    resolved_outcome = str(outcome or '').strip() or None
    if not (resolved_token_id or resolved_outcome):
        raise ChallengeError('Polymarket challenge trades require an explicit token_id or outcome')

    try:
        import price_fetcher
        from price_fetcher import price_fetch_logging
    except Exception as exc:
        raise ChallengeError('Server price fetcher is unavailable') from exc

    with price_fetch_logging(False):
        try:
            contract = price_fetcher.describe_polymarket_contract(
                symbol,
                token_id=resolved_token_id,
                outcome=resolved_outcome,
            )
        except Exception as exc:
            raise ChallengeError(f'Unable to resolve Polymarket contract for {symbol}') from exc

    if not contract or not contract.get('token_id'):
        raise ChallengeError('Polymarket challenge trade must resolve to a single outcome token')
    return str(contract.get('token_id') or '').strip() or None, str(contract.get('outcome') or resolved_outcome or '').strip() or None


def _fetch_authoritative_challenge_trade_price(
    market: str,
    symbol: str,
    executed_at: str,
    token_id: Any = None,
    outcome: Any = None,
) -> Optional[float]:
    if market not in AUTHORITATIVE_CHALLENGE_PRICE_MARKETS:
        return None

    try:
        import price_fetcher
        from price_fetcher import price_fetch_logging
    except Exception as exc:
        raise ChallengeError('Server price fetcher is unavailable') from exc

    with price_fetch_logging(False):
        try:
            price = price_fetcher.get_price_from_market(
                symbol,
                executed_at,
                market,
                token_id=str(token_id or '').strip() or None,
                outcome=str(outcome or '').strip() or None,
            )
        except Exception as exc:
            raise ChallengeError(f'Unable to fetch server price for {symbol}') from exc

    try:
        parsed = float(price) if price is not None else 0.0
    except Exception:
        parsed = 0.0
    if not math.isfinite(parsed) or parsed <= 0:
        raise ChallengeError(f'Unable to fetch server price for {symbol}')
    if market == 'polymarket' and parsed > 1:
        raise ChallengeError(f'Invalid Polymarket price for {symbol}')
    return parsed


def _score_challenge_results_with_live_marks(
    challenge: dict[str, Any],
    participants: list[dict[str, Any]],
    trades_by_agent: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    scored = score_challenge_results(challenge, participants, trades_by_agent)
    mark_timestamp = _live_mark_timestamp(challenge)
    if not mark_timestamp:
        return scored
    mark_prices = _fetch_live_mark_prices(scored, mark_timestamp)
    if not mark_prices:
        return scored
    return score_challenge_results(
        challenge,
        participants,
        trades_by_agent,
        mark_prices=mark_prices,
        mark_timestamp=mark_timestamp,
    )


def _normalize_key(key: Optional[str], title: str) -> str:
    candidate = (key or '').strip().lower()
    if not candidate:
        candidate = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        candidate = f'{candidate[:44] or "challenge"}-{uuid.uuid4().hex[:8]}'
    candidate = re.sub(r'[^a-z0-9_\-]+', '-', candidate).strip('-_')
    if not candidate:
        raise ChallengeError('challenge_key is required')
    return candidate[:80]


def _derive_status(start_at: str, end_at: str, requested_status: Optional[str] = None) -> str:
    if requested_status:
        normalized = requested_status.strip().lower()
        if normalized not in {'upcoming', 'active', 'settled', 'canceled'}:
            raise ChallengeError('Unsupported challenge status')
        return normalized
    now = datetime.now(timezone.utc)
    start_dt = _parse_dt(start_at)
    end_dt = _parse_dt(end_at)
    if start_dt and start_dt > now:
        return 'upcoming'
    if end_dt and end_dt <= now:
        return 'active'
    return 'active'


def _normalize_challenge_track(value: Optional[str], *, allow_all: bool = False) -> Optional[str]:
    normalized = (value or '').strip().lower().replace('_', '-')
    if allow_all and (not normalized or normalized == 'all'):
        return None
    if normalized not in SUPPORTED_CHALLENGE_TRACKS:
        raise ChallengeError('Unsupported challenge track')
    return normalized


def _normalize_challenge_mode(value: Optional[str]) -> str:
    normalized = (value or 'individual').strip().lower().replace('_', '-')
    if normalized not in SUPPORTED_CHALLENGE_MODES:
        raise ChallengeError('Unsupported challenge mode')
    return normalized


def _load_challenge(cursor: Any, challenge_key: Optional[str] = None, challenge_id: Optional[int] = None) -> dict[str, Any]:
    if challenge_id is not None:
        cursor.execute("SELECT * FROM challenges WHERE id = ?", (challenge_id,))
    else:
        cursor.execute("SELECT * FROM challenges WHERE challenge_key = ?", (challenge_key,))
    row = cursor.fetchone()
    if not row:
        raise ChallengeNotFound('Challenge not found')
    return _row_dict(row)


def _serialize_challenge(row: Any, participant_count: Optional[int] = None) -> dict[str, Any]:
    data = _row_dict(row)
    if not data:
        return {}
    data['mode'] = _normalize_challenge_mode(data.get('mode'))
    data['rules'] = _json_loads(data.get('rules_json'), {})
    if participant_count is not None:
        data['participant_count'] = participant_count
    return data


def refresh_challenge_statuses(cursor: Any) -> None:
    now = utc_now_iso_z()
    cursor.execute(
        """
        UPDATE challenges
        SET status = 'active', updated_at = ?
        WHERE status = 'upcoming' AND start_at <= ? AND end_at > ?
        """,
        (now, now, now),
    )


def create_challenge(data: Any, created_by_agent_id: int) -> dict[str, Any]:
    payload = _model_dump(data)
    title = (payload.get('title') or '').strip()
    if not title:
        raise ChallengeError('title is required')

    raw_market = (payload.get('market') or '').strip()
    if not raw_market:
        raise ChallengeError('market is required')
    market = _normalize_challenge_track(raw_market)

    scoring_method = (payload.get('scoring_method') or 'return-only').strip().lower().replace('_', '-')
    if scoring_method not in SUPPORTED_SCORING_METHODS:
        raise ChallengeError('Unsupported scoring_method')

    now_dt = datetime.now(timezone.utc)
    start_at = _iso(_parse_dt(payload.get('start_at')) or now_dt)
    end_at = _iso(_parse_dt(payload.get('end_at')) or (now_dt + timedelta(hours=24)))
    if _parse_dt(end_at) <= _parse_dt(start_at):
        raise ChallengeError('end_at must be after start_at')

    challenge_key = _normalize_key(payload.get('challenge_key'), title)
    status = _derive_status(start_at, end_at, payload.get('status'))
    rules = payload.get('rules_json') or {}
    if isinstance(rules, str):
        rules = _json_loads(rules, {})
    if 'reward_points' not in rules and rules.get('grant_rewards', True):
        rules['reward_points'] = DEFAULT_CHALLENGE_REWARDS
    mode = _normalize_challenge_mode(payload.get('mode'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        cursor.execute(
            """
            INSERT INTO challenges
            (challenge_key, title, description, market, symbol, challenge_type, mode, status,
             scoring_method, initial_capital, max_position_pct, max_drawdown_pct,
             start_at, end_at, rules_json, experiment_key, created_by_agent_id,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge_key,
                title,
                payload.get('description'),
                market,
                (payload.get('symbol') or '').strip() or None,
                (payload.get('challenge_type') or 'multi-agent').strip(),
                mode,
                status,
                scoring_method,
                float(payload.get('initial_capital') or 100000.0),
                float(payload.get('max_position_pct') or 100.0),
                float(payload.get('max_drawdown_pct') or 100.0),
                start_at,
                end_at,
                _json_dumps(rules),
                (payload.get('experiment_key') or '').strip() or None,
                created_by_agent_id,
                utc_now_iso_z(),
                utc_now_iso_z(),
            ),
        )
        challenge_id = cursor.lastrowid
        record_event(
            'challenge_created',
            actor_agent_id=created_by_agent_id,
            object_type='challenge',
            object_id=challenge_id,
            market=market,
            experiment_key=(payload.get('experiment_key') or '').strip() or None,
            metadata={'challenge_key': challenge_key, 'scoring_method': scoring_method, 'mode': mode},
            cursor=cursor,
        )
        conn.commit()
        challenge = _load_challenge(cursor, challenge_id=challenge_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return _serialize_challenge(challenge, participant_count=0)


def list_challenges(
    status: Optional[str] = None,
    market: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    track = _normalize_challenge_track(market, allow_all=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        params: list[Any] = []
        conditions: list[str] = []
        if status:
            conditions.append('c.status = ?')
            params.append(status)
        if track:
            conditions.append('c.market = ?')
            params.append(track)
        where = ' AND '.join(conditions) if conditions else '1=1'

        cursor.execute(f"SELECT COUNT(*) AS total FROM challenges c WHERE {where}", params)
        total = cursor.fetchone()['total']
        cursor.execute(
            f"""
            SELECT c.*,
                   (SELECT COUNT(*) FROM challenge_participants cp WHERE cp.challenge_id = c.id) AS participant_count,
                   (SELECT COUNT(*) FROM challenge_teams ct WHERE ct.challenge_id = c.id) AS team_count
            FROM challenges c
            WHERE {where}
            ORDER BY c.start_at DESC, c.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )
        rows = []
        for row in cursor.fetchall():
            challenge = _serialize_challenge(row, row['participant_count'])
            challenge['team_count'] = row['team_count']
            rows.append(challenge)
        return {'challenges': rows, 'total': total}
    finally:
        conn.close()


def get_challenge(challenge_key: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        cursor.execute(
            """
            SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_participants cp
            JOIN agents a ON a.id = cp.agent_id
            WHERE cp.challenge_id = ?
            ORDER BY COALESCE(cp.rank, 999999), cp.joined_at, cp.id
            """,
            (challenge['id'],),
        )
        participants = []
        for row in cursor.fetchall():
            participant = dict(row)
            participant['agent_identity_status'] = agent_identity_status(row)
            participant['agent_is_verified'] = agent_is_verified(row)
            participants.append(participant)
        result = _serialize_challenge(challenge, len(participants))
        result['participants'] = participants
        result['teams'] = _list_challenge_teams_with_cursor(cursor, challenge['id'])
        result['team_count'] = len(result['teams'])
        return result
    finally:
        conn.close()


def _resolve_variant(cursor: Any, experiment_key: Optional[str], agent_id: int, requested_variant: Optional[str]) -> Optional[str]:
    variant_key = (requested_variant or '').strip() or None
    if not experiment_key:
        return variant_key

    cursor.execute(
        """
        SELECT variant_key
        FROM experiment_assignments
        WHERE experiment_key = ? AND unit_type = 'agent' AND unit_id = ?
        """,
        (experiment_key, agent_id),
    )
    row = cursor.fetchone()
    if row:
        return row['variant_key']

    cursor.execute("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
    experiment = cursor.fetchone()
    if not experiment:
        return variant_key
    experiment_data = _row_dict(experiment)
    if not experiment_accepts_unit(experiment_data, 'agent', agent_id):
        return variant_key

    if variant_key:
        chosen_variant = variant_key
    else:
        variants = normalize_variants(experiment_data.get('variants_json'))
        total_weight = sum(float(item.get('weight', 1)) for item in variants)
        if total_weight <= 0:
            chosen_variant = variants[0]['key']
        else:
            bucket = stable_bucket(experiment_key, 'agent', agent_id) % 1_000_000
            threshold = bucket / 1_000_000 * total_weight
            cursor_position = 0.0
            chosen_variant = variants[-1]['key']
            for variant in variants:
                cursor_position += float(variant.get('weight', 1))
                if threshold < cursor_position:
                    chosen_variant = variant['key']
                    break

    if chosen_variant:
        cursor.execute(
            """
            INSERT INTO experiment_assignments
            (experiment_key, unit_type, unit_id, variant_key, assignment_reason, metadata_json, created_at)
            VALUES (?, 'agent', ?, ?, 'challenge_join', ?, ?)
            """,
            (experiment_key, agent_id, chosen_variant, _json_dumps({'source': 'challenge_join'}), utc_now_iso_z()),
        )
        record_event(
            'experiment_assigned',
            actor_agent_id=agent_id,
            object_type='experiment_assignment',
            object_id=f'{experiment_key}:agent:{agent_id}',
            experiment_key=experiment_key,
            variant_key=chosen_variant,
            metadata={'unit_type': 'agent', 'unit_id': agent_id, 'assignment_reason': 'challenge_join'},
            cursor=cursor,
        )
    return chosen_variant


def join_challenge(challenge_key: str, agent_id: int, data: Any = None) -> dict[str, Any]:
    payload = _model_dump(data) if data is not None else {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        if _normalize_challenge_mode(challenge.get('mode')) == 'team':
            raise ChallengeError('Team challenges require joining a challenge team')
        if challenge['status'] not in {'upcoming', 'active'}:
            raise ChallengeError('Challenge is not joinable')

        cursor.execute(
            """
            SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_participants cp
            JOIN agents a ON a.id = cp.agent_id
            WHERE cp.challenge_id = ? AND cp.agent_id = ?
            """,
            (challenge['id'], agent_id),
        )
        existing = cursor.fetchone()
        if existing:
            participant = dict(existing)
            participant['agent_identity_status'] = agent_identity_status(existing)
            participant['agent_is_verified'] = agent_is_verified(existing)
            conn.commit()
            return {'joined': False, 'idempotent': True, 'participant': participant}

        variant_key = _resolve_variant(cursor, challenge.get('experiment_key'), agent_id, payload.get('variant_key'))
        starting_cash = float(payload.get('starting_cash') or challenge.get('initial_capital') or 100000.0)
        if not math.isfinite(starting_cash) or starting_cash <= 0:
            raise ChallengeError('starting_cash must be a positive finite number')
        cursor.execute(
            """
            INSERT INTO challenge_participants
            (challenge_id, agent_id, status, variant_key, joined_at, starting_cash)
            VALUES (?, ?, 'joined', ?, ?, ?)
            """,
            (challenge['id'], agent_id, variant_key, utc_now_iso_z(), starting_cash),
        )
        participant_id = cursor.lastrowid
        record_event(
            'challenge_joined',
            actor_agent_id=agent_id,
            object_type='challenge_participant',
            object_id=participant_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=variant_key,
            metadata={'challenge_key': challenge['challenge_key'], 'challenge_id': challenge['id']},
            cursor=cursor,
        )
        conn.commit()

        cursor.execute(
            """
            SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_participants cp
            JOIN agents a ON a.id = cp.agent_id
            WHERE cp.id = ?
            """,
            (participant_id,),
        )
        participant_row = cursor.fetchone()
        participant = dict(participant_row)
        participant['agent_identity_status'] = agent_identity_status(participant_row)
        participant['agent_is_verified'] = agent_is_verified(participant_row)
        return {'joined': True, 'idempotent': False, 'participant': participant}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _challenge_rules(challenge: dict[str, Any]) -> dict[str, Any]:
    return _json_loads(challenge.get('rules_json'), {}) or {}


def _team_size_max(challenge: dict[str, Any]) -> int:
    rules = _challenge_rules(challenge)
    try:
        value = int(rules.get('team_size_max') or 5)
    except Exception:
        value = 5
    return max(1, min(value, 50))


def _require_team_challenge(challenge: dict[str, Any]) -> None:
    if _normalize_challenge_mode(challenge.get('mode')) not in {'team', 'hybrid'}:
        raise ChallengeError('Challenge does not support teams')


def _serialize_challenge_team(row: Any, *, members: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    team = _row_dict(row)
    if members is not None:
        team['members'] = members
        team['member_count'] = len(members)
    return team


def _load_challenge_team(cursor: Any, challenge_id: int, team_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT ct.*, a.name AS creator_name
        FROM challenge_teams ct
        JOIN agents a ON a.id = ct.created_by_agent_id
        WHERE ct.challenge_id = ? AND ct.id = ?
        """,
        (challenge_id, team_id),
    )
    row = cursor.fetchone()
    if not row:
        raise ChallengeError('Challenge team not found')
    return dict(row)


def _list_team_members_with_cursor(cursor: Any, team_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT ctm.*, a.name AS agent_name, a.identity_status AS agent_identity_status
        FROM challenge_team_members ctm
        JOIN agents a ON a.id = ctm.agent_id
        WHERE ctm.team_id = ?
        ORDER BY ctm.joined_at, ctm.id
        """,
        (team_id,),
    )
    members = []
    for row in cursor.fetchall():
        member = dict(row)
        member['agent_identity_status'] = agent_identity_status(row)
        member['agent_is_verified'] = agent_is_verified(row)
        members.append(member)
    return members


def _list_challenge_teams_with_cursor(cursor: Any, challenge_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT ct.*, a.name AS creator_name,
               (SELECT COUNT(*) FROM challenge_team_members ctm WHERE ctm.team_id = ct.id) AS member_count,
               (SELECT COUNT(DISTINCT ctt.agent_id) FROM challenge_team_trades ctt WHERE ctt.team_id = ct.id) AS trade_agent_count,
               (SELECT COUNT(*) FROM challenge_team_trades ctt WHERE ctt.team_id = ct.id) AS trade_count_live,
               (SELECT COUNT(*) FROM challenge_team_submissions cts WHERE cts.team_id = ct.id) AS submission_count
        FROM challenge_teams ct
        JOIN agents a ON a.id = ct.created_by_agent_id
        WHERE ct.challenge_id = ?
        ORDER BY COALESCE(ct.rank, 999999), ct.created_at, ct.id
        """,
        (challenge_id,),
    )
    teams = []
    for row in cursor.fetchall():
        team = dict(row)
        team['trade_count'] = team.get('trade_count') or team.get('trade_count_live') or 0
        teams.append(team)
    return teams


def create_challenge_team(challenge_key: str, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    name = (payload.get('name') or '').strip()
    if not name:
        raise ChallengeError('team name is required')
    role = (payload.get('role') or 'captain').strip().lower() or 'captain'

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        if challenge['status'] not in {'upcoming', 'active'}:
            raise ChallengeError('Challenge is not accepting teams')

        cursor.execute(
            """
            SELECT ctm.*, ct.team_key, ct.name AS team_name
            FROM challenge_team_members ctm
            JOIN challenge_teams ct ON ct.id = ctm.team_id
            WHERE ctm.challenge_id = ? AND ctm.agent_id = ?
            """,
            (challenge['id'], agent_id),
        )
        if cursor.fetchone():
            raise ChallengeError('Agent already belongs to a team in this challenge')

        team_key = _normalize_key(payload.get('team_key'), name)
        cursor.execute(
            "SELECT id FROM challenge_teams WHERE challenge_id = ? AND team_key = ?",
            (challenge['id'], team_key),
        )
        if cursor.fetchone():
            raise ChallengeError('team_key already exists for this challenge')

        variant_key = _resolve_variant(cursor, challenge.get('experiment_key'), agent_id, payload.get('variant_key'))
        starting_cash = float(payload.get('starting_cash') or challenge.get('initial_capital') or 100000.0)
        now = utc_now_iso_z()
        cursor.execute(
            """
            INSERT INTO challenge_teams
            (challenge_id, team_key, name, status, variant_key, created_by_agent_id,
             starting_cash, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (challenge['id'], team_key, name, variant_key, agent_id, starting_cash, now, now),
        )
        team_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO challenge_team_members
            (challenge_id, team_id, agent_id, role, status, variant_key, joined_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (challenge['id'], team_id, agent_id, role, variant_key, now),
        )
        member_id = cursor.lastrowid
        record_event(
            'challenge_team_created',
            actor_agent_id=agent_id,
            object_type='challenge_team',
            object_id=team_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=variant_key,
            metadata={'challenge_key': challenge['challenge_key'], 'team_key': team_key, 'team_id': team_id},
            cursor=cursor,
        )
        record_event(
            'challenge_team_joined',
            actor_agent_id=agent_id,
            object_type='challenge_team_member',
            object_id=member_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=variant_key,
            metadata={'challenge_key': challenge['challenge_key'], 'team_key': team_key, 'team_id': team_id, 'role': role},
            cursor=cursor,
        )
        conn.commit()

        team = _load_challenge_team(cursor, challenge['id'], team_id)
        members = _list_team_members_with_cursor(cursor, team_id)
        return {'created': True, 'team': _serialize_challenge_team(team, members=members)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def join_challenge_team(challenge_key: str, team_id: int, agent_id: int, data: Any = None) -> dict[str, Any]:
    payload = _model_dump(data) if data is not None else {}
    role = (payload.get('role') or 'member').strip().lower() or 'member'
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        if challenge['status'] not in {'upcoming', 'active'}:
            raise ChallengeError('Challenge team is not joinable')

        team = _load_challenge_team(cursor, challenge['id'], int(team_id))
        if team.get('status') not in {'active', 'joined'}:
            raise ChallengeError('Challenge team is not joinable')

        cursor.execute(
            """
            SELECT *
            FROM challenge_team_members
            WHERE challenge_id = ? AND agent_id = ?
            """,
            (challenge['id'], agent_id),
        )
        existing = cursor.fetchone()
        if existing:
            existing_member = dict(existing)
            if existing_member['team_id'] != team['id']:
                raise ChallengeError('Agent already belongs to another team in this challenge')
            conn.commit()
            members = _list_team_members_with_cursor(cursor, team['id'])
            return {'joined': False, 'idempotent': True, 'team': _serialize_challenge_team(team, members=members)}

        members = _list_team_members_with_cursor(cursor, team['id'])
        if len(members) >= _team_size_max(challenge):
            raise ChallengeError('Challenge team is full')

        variant_key = _resolve_variant(cursor, challenge.get('experiment_key'), agent_id, payload.get('variant_key'))
        now = utc_now_iso_z()
        cursor.execute(
            """
            INSERT INTO challenge_team_members
            (challenge_id, team_id, agent_id, role, status, variant_key, joined_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (challenge['id'], team['id'], agent_id, role, variant_key, now),
        )
        member_id = cursor.lastrowid
        record_event(
            'challenge_team_joined',
            actor_agent_id=agent_id,
            object_type='challenge_team_member',
            object_id=member_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=variant_key,
            metadata={'challenge_key': challenge['challenge_key'], 'team_key': team['team_key'], 'team_id': team['id'], 'role': role},
            cursor=cursor,
        )
        conn.commit()
        members = _list_team_members_with_cursor(cursor, team['id'])
        return {'joined': True, 'idempotent': False, 'team': _serialize_challenge_team(team, members=members)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_challenge_teams(challenge_key: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        teams = _list_challenge_teams_with_cursor(cursor, challenge['id'])
        for team in teams:
            team['members'] = _list_team_members_with_cursor(cursor, team['id'])
        return {'challenge': _serialize_challenge(challenge), 'teams': teams, 'total': len(teams)}
    finally:
        conn.close()


def _require_challenge_team_member(cursor: Any, challenge_id: int, team_id: int, agent_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT ctm.*, a.name AS agent_name, a.identity_status AS agent_identity_status
        FROM challenge_team_members ctm
        JOIN agents a ON a.id = ctm.agent_id
        WHERE ctm.challenge_id = ? AND ctm.team_id = ? AND ctm.agent_id = ?
        """,
        (challenge_id, team_id, agent_id),
    )
    row = cursor.fetchone()
    if not row:
        raise ChallengeError('Agent must join the challenge team first')
    member = dict(row)
    member['agent_identity_status'] = agent_identity_status(row)
    member['agent_is_verified'] = agent_is_verified(row)
    if member.get('status') not in {'active', 'joined'}:
        raise ChallengeError('Challenge team membership is not active')
    return member


def _team_participant_snapshot(team: dict[str, Any]) -> dict[str, Any]:
    return {
        'agent_id': team['id'],
        'starting_cash': team.get('starting_cash'),
        'status': team.get('status'),
        'disqualified_reason': team.get('disqualified_reason'),
    }


def _serialize_challenge_team_portfolio(
    challenge: dict[str, Any],
    team: dict[str, Any],
    member: Optional[dict[str, Any]],
    trades: list[dict[str, Any]],
    mark_prices: Optional[dict[Any, float]] = None,
    mark_timestamp: Optional[str] = None,
) -> dict[str, Any]:
    scored = score_agent_trades(
        challenge,
        _team_participant_snapshot(team),
        trades,
        mark_prices=mark_prices,
        mark_timestamp=mark_timestamp,
    )
    metrics = scored.get('metrics') or {}
    return {
        'challenge': _serialize_challenge(challenge),
        'team': team,
        'member': member,
        'portfolio': {
            'starting_cash': scored.get('starting_cash'),
            'cash': metrics.get('cash'),
            'ending_value': scored.get('ending_value'),
            'return_pct': scored.get('return_pct'),
            'max_drawdown': scored.get('max_drawdown'),
            'risk_adjusted_score': scored.get('risk_adjusted_score'),
            'final_score': scored.get('final_score'),
            'trade_count': scored.get('trade_count'),
            'disqualified_reason': scored.get('disqualified_reason'),
            'marked_to_market': metrics.get('marked_to_market') or False,
            'mark_timestamp': metrics.get('mark_timestamp'),
            'live_marks': metrics.get('live_marks') or [],
            'positions': metrics.get('positions') or [],
            'equity_curve': metrics.get('equity_curve') or [],
        },
        'trades': trades,
    }


def get_challenge_team_portfolio(challenge_key: str, team_id: int, agent_id: int) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        team = _load_challenge_team(cursor, challenge['id'], int(team_id))
        member = _require_challenge_team_member(cursor, challenge['id'], team['id'], agent_id)
        cursor.execute(
            """
            SELECT ctt.*, a.name AS agent_name
            FROM challenge_team_trades ctt
            JOIN agents a ON a.id = ctt.agent_id
            WHERE ctt.challenge_id = ? AND ctt.team_id = ?
            ORDER BY ctt.executed_at, ctt.id
            """,
            (challenge['id'], team['id']),
        )
        trades = [dict(row) for row in cursor.fetchall()]
        mark_prices: dict[Any, float] = {}
        mark_timestamp = _live_mark_timestamp(challenge)
        if mark_timestamp:
            baseline = score_agent_trades(challenge, _team_participant_snapshot(team), trades)
            mark_prices = _fetch_live_mark_prices([baseline], mark_timestamp)
        return _serialize_challenge_team_portfolio(
            challenge,
            team,
            member,
            trades,
            mark_prices=mark_prices,
            mark_timestamp=mark_timestamp,
        )
    finally:
        conn.close()


def _create_team_submission_with_cursor(
    cursor: Any,
    challenge: dict[str, Any],
    team: dict[str, Any],
    member: dict[str, Any],
    submission_type: str,
    content: Optional[str],
    prediction_json: Any,
) -> dict[str, Any]:
    if challenge['status'] not in {'upcoming', 'active'}:
        raise ChallengeError('Challenge is not accepting team submissions')
    prediction_text = _json_dumps(prediction_json)
    cursor.execute(
        """
        INSERT INTO challenge_team_submissions
        (challenge_id, team_id, agent_id, submission_type, content, prediction_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            challenge['id'],
            team['id'],
            member['agent_id'],
            submission_type,
            content,
            prediction_text,
            utc_now_iso_z(),
        ),
    )
    submission_id = cursor.lastrowid
    record_event(
        'challenge_team_submission_created',
        actor_agent_id=member['agent_id'],
        object_type='challenge_team_submission',
        object_id=submission_id,
        market=challenge['market'],
        experiment_key=challenge.get('experiment_key'),
        variant_key=member.get('variant_key') or team.get('variant_key'),
        metadata={
            'challenge_key': challenge['challenge_key'],
            'team_key': team['team_key'],
            'team_id': team['id'],
            'submission_type': submission_type,
        },
        cursor=cursor,
    )
    return {
        'id': submission_id,
        'challenge_id': challenge['id'],
        'team_id': team['id'],
        'agent_id': member['agent_id'],
        'submission_type': submission_type,
        'content': content,
        'prediction_json': prediction_text,
    }


def create_challenge_team_submission(challenge_key: str, team_id: int, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        team = _load_challenge_team(cursor, challenge['id'], int(team_id))
        member = _require_challenge_team_member(cursor, challenge['id'], team['id'], agent_id)
        submission = _create_team_submission_with_cursor(
            cursor,
            challenge,
            team,
            member,
            payload.get('submission_type') or 'team_thesis',
            payload.get('content'),
            payload.get('prediction_json'),
        )
        conn.commit()
        return {'submission': submission}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_challenge_team_submissions(
    challenge_key: str,
    team_id: int,
    *,
    viewer_agent_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        team = _load_challenge_team(cursor, challenge['id'], int(team_id))
        cursor.execute(
            "SELECT COUNT(*) AS total FROM challenge_team_submissions WHERE challenge_id = ? AND team_id = ?",
            (challenge['id'], team['id']),
        )
        total = cursor.fetchone()['total']
        viewer_vote_select = ""
        viewer_vote_join = ""
        params: list[Any] = []
        if viewer_agent_id:
            viewer_vote_select = ", my_vote.vote AS my_vote"
            viewer_vote_join = "LEFT JOIN challenge_submission_votes my_vote ON my_vote.submission_id = cts.id AND my_vote.agent_id = ?"
            params.append(viewer_agent_id)
        params.extend([challenge['id'], team['id'], limit, offset])
        cursor.execute(
            f"""
            SELECT cts.*, a.name AS agent_name, a.identity_status AS agent_identity_status,
                   COALESCE(v.approve_count, 0) AS approve_count,
                   COALESCE(v.reject_count, 0) AS reject_count,
                   COALESCE(v.revise_count, 0) AS revise_count
                   {viewer_vote_select}
            FROM challenge_team_submissions cts
            JOIN agents a ON a.id = cts.agent_id
            LEFT JOIN (
                SELECT submission_id,
                       SUM(CASE WHEN vote = 'approve' THEN 1 ELSE 0 END) AS approve_count,
                       SUM(CASE WHEN vote = 'reject' THEN 1 ELSE 0 END) AS reject_count,
                       SUM(CASE WHEN vote = 'revise' THEN 1 ELSE 0 END) AS revise_count
                FROM challenge_submission_votes
                GROUP BY submission_id
            ) v ON v.submission_id = cts.id
            {viewer_vote_join}
            WHERE cts.challenge_id = ? AND cts.team_id = ?
            ORDER BY cts.created_at DESC, cts.id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
        submissions = []
        for row in cursor.fetchall():
            submission = dict(row)
            submission['agent_identity_status'] = agent_identity_status(row)
            submission['agent_is_verified'] = agent_is_verified(row)
            submissions.append(submission)
        return {
            'challenge': _serialize_challenge(challenge),
            'team': team,
            'submissions': submissions,
            'total': total,
        }
    finally:
        conn.close()


def create_challenge_submission_vote(challenge_key: str, submission_id: int, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    vote = (payload.get('vote') or '').strip().lower()
    if vote not in {'approve', 'reject', 'revise'}:
        raise ChallengeError('Unsupported submission vote')
    content = (payload.get('content') or '').strip() or None
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        cursor.execute(
            """
            SELECT cts.*, ct.team_key, ct.variant_key AS team_variant_key
            FROM challenge_team_submissions cts
            JOIN challenge_teams ct ON ct.id = cts.team_id
            WHERE cts.challenge_id = ? AND cts.id = ?
            """,
            (challenge['id'], int(submission_id)),
        )
        submission = cursor.fetchone()
        if not submission:
            raise ChallengeError('Challenge team submission not found')
        team = {
            'id': submission['team_id'],
            'team_key': submission['team_key'],
            'variant_key': submission['team_variant_key'],
        }
        member = _require_challenge_team_member(cursor, challenge['id'], submission['team_id'], agent_id)
        cursor.execute(
            """
            SELECT id
            FROM challenge_submission_votes
            WHERE submission_id = ? AND agent_id = ?
            """,
            (submission_id, agent_id),
        )
        existing = cursor.fetchone()
        now = utc_now_iso_z()
        if existing:
            vote_id = existing['id']
            cursor.execute(
                """
                UPDATE challenge_submission_votes
                SET vote = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (vote, content, now, vote_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO challenge_submission_votes
                (submission_id, agent_id, vote, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (submission_id, agent_id, vote, content, now, now),
            )
            vote_id = cursor.lastrowid
        record_event(
            'challenge_submission_vote_cast',
            actor_agent_id=agent_id,
            object_type='challenge_submission_vote',
            object_id=vote_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=member.get('variant_key') or team.get('variant_key'),
            metadata={
                'challenge_key': challenge['challenge_key'],
                'team_id': team['id'],
                'team_key': team['team_key'],
                'submission_id': submission_id,
                'vote': vote,
            },
            cursor=cursor,
        )
        conn.commit()
        return {'vote': {'id': vote_id, 'submission_id': submission_id, 'agent_id': agent_id, 'vote': vote, 'content': content}}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_submission(challenge_key: str, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        submission = _create_submission_with_cursor(
            cursor,
            challenge,
            agent_id,
            payload.get('submission_type') or 'manual',
            payload.get('content'),
            payload.get('prediction_json'),
            payload.get('signal_id'),
        )
        conn.commit()
        return submission
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_submission_with_cursor(
    cursor: Any,
    challenge: dict[str, Any],
    agent_id: int,
    submission_type: str,
    content: Optional[str],
    prediction_json: Any,
    signal_id: Optional[int] = None,
) -> dict[str, Any]:
    if challenge['status'] not in {'upcoming', 'active'}:
        raise ChallengeError('Challenge is not accepting submissions')

    cursor.execute(
        """
        SELECT *
        FROM challenge_participants
        WHERE challenge_id = ? AND agent_id = ?
        """,
        (challenge['id'], agent_id),
    )
    participant = cursor.fetchone()
    if not participant:
        raise ChallengeError('Agent must join challenge before submitting')

    prediction_text = _json_dumps(prediction_json)
    cursor.execute(
        """
        INSERT INTO challenge_submissions
        (challenge_id, agent_id, signal_id, submission_type, content, prediction_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            challenge['id'],
            agent_id,
            signal_id,
            submission_type,
            content,
            prediction_text,
            utc_now_iso_z(),
        ),
    )
    submission_id = cursor.lastrowid
    record_event(
        'challenge_submission_created',
        actor_agent_id=agent_id,
        object_type='challenge_submission',
        object_id=submission_id,
        market=challenge['market'],
        experiment_key=challenge.get('experiment_key'),
        variant_key=participant['variant_key'],
        metadata={
            'challenge_key': challenge['challenge_key'],
            'submission_type': submission_type,
            'signal_id': signal_id,
        },
        cursor=cursor,
    )
    return {
        'id': submission_id,
        'challenge_id': challenge['id'],
        'agent_id': agent_id,
        'signal_id': signal_id,
        'submission_type': submission_type,
        'content': content,
        'prediction_json': prediction_text,
    }


def record_challenge_submission_from_signal(
    cursor: Any,
    *,
    challenge_key: Optional[str],
    agent_id: int,
    signal_id: int,
    submission_type: str,
    content: Optional[str],
    prediction_json: Any = None,
) -> Optional[dict[str, Any]]:
    if not challenge_key:
        return None
    challenge = _load_challenge(cursor, challenge_key=challenge_key)
    return _create_submission_with_cursor(
        cursor,
        challenge,
        agent_id,
        submission_type,
        content,
        prediction_json,
        signal_id,
    )


def _normalize_challenge_trade_symbol(challenge: dict[str, Any], raw_symbol: Any) -> str:
    fixed_symbol = str(challenge.get('symbol') or '').strip()
    requested_symbol = str(raw_symbol or '').strip()
    if fixed_symbol and fixed_symbol.lower() != 'all':
        symbol = fixed_symbol
        if requested_symbol:
            compare_requested = requested_symbol if challenge['market'] == 'polymarket' else requested_symbol.upper()
            compare_fixed = fixed_symbol if challenge['market'] == 'polymarket' else fixed_symbol.upper()
            if compare_requested != compare_fixed:
                raise ChallengeError('Trade symbol does not match challenge symbol')
    else:
        symbol = requested_symbol
    if not symbol:
        raise ChallengeError('symbol is required for challenge trade')
    return symbol if challenge['market'] == 'polymarket' else symbol.upper()


def _serialize_challenge_portfolio(
    challenge: dict[str, Any],
    participant: dict[str, Any],
    trades: list[dict[str, Any]],
    mark_prices: Optional[dict[Any, float]] = None,
    mark_timestamp: Optional[str] = None,
) -> dict[str, Any]:
    scored = score_agent_trades(
        challenge,
        participant,
        trades,
        mark_prices=mark_prices,
        mark_timestamp=mark_timestamp,
    )
    metrics = scored.get('metrics') or {}
    ending_value = scored.get('ending_value')
    return {
        'challenge': _serialize_challenge(challenge),
        'participant': participant,
        'portfolio': {
            'starting_cash': scored.get('starting_cash'),
            'cash': metrics.get('cash'),
            'ending_value': ending_value,
            'return_pct': scored.get('return_pct'),
            'max_drawdown': scored.get('max_drawdown'),
            'risk_adjusted_score': scored.get('risk_adjusted_score'),
            'final_score': scored.get('final_score'),
            'trade_count': scored.get('trade_count'),
            'disqualified_reason': scored.get('disqualified_reason'),
            'marked_to_market': metrics.get('marked_to_market') or False,
            'mark_timestamp': metrics.get('mark_timestamp'),
            'live_marks': metrics.get('live_marks') or [],
            'positions': metrics.get('positions') or [],
            'equity_curve': metrics.get('equity_curve') or [],
        },
        'trades': trades,
    }


def get_agent_challenge_portfolio(challenge_key: str, agent_id: int) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        cursor.execute(
            """
            SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_participants cp
            JOIN agents a ON a.id = cp.agent_id
            WHERE cp.challenge_id = ? AND cp.agent_id = ?
            """,
            (challenge['id'], agent_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ChallengeError('Agent must join challenge before viewing challenge portfolio')
        participant = dict(row)
        participant['agent_identity_status'] = agent_identity_status(row)
        participant['agent_is_verified'] = agent_is_verified(row)
        cursor.execute(
            """
            SELECT *
            FROM challenge_trades
            WHERE challenge_id = ? AND agent_id = ?
            ORDER BY executed_at, id
            """,
            (challenge['id'], agent_id),
        )
        trades = [dict(trade) for trade in cursor.fetchall()]
        mark_prices: dict[Any, float] = {}
        mark_timestamp = _live_mark_timestamp(challenge)
        if mark_timestamp:
            baseline = score_agent_trades(challenge, participant, trades)
            mark_prices = _fetch_live_mark_prices([baseline], mark_timestamp)
        return _serialize_challenge_portfolio(
            challenge,
            participant,
            trades,
            mark_prices=mark_prices,
            mark_timestamp=mark_timestamp,
        )
    finally:
        conn.close()


def create_challenge_trade(challenge_key: str, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    side = str(payload.get('side') or payload.get('action') or '').strip().lower()
    if side not in {'buy', 'sell', 'short', 'cover'}:
        raise ChallengeError('Unsupported challenge trade side')
    try:
        price = float(payload.get('price'))
        quantity = float(payload.get('quantity'))
    except Exception as exc:
        raise ChallengeError('price and quantity are required') from exc
    if price <= 0 or quantity <= 0:
        raise ChallengeError('price and quantity must be positive')

    executed_at = _iso(_parse_dt(payload.get('executed_at')) or datetime.now(timezone.utc))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        if _normalize_challenge_mode(challenge.get('mode')) == 'team':
            raise ChallengeError('Team challenges require the team trade endpoint')
        if challenge['status'] != 'active':
            raise ChallengeError('Challenge is not active')
        executed_dt = _parse_dt(executed_at)
        if executed_dt < _parse_dt(challenge['start_at']) or executed_dt > _parse_dt(challenge['end_at']):
            raise ChallengeError('Challenge trade must be inside challenge time window')
        if challenge['market'] == 'polymarket':
            current_dt = datetime.now(timezone.utc)
            if abs((current_dt - executed_dt).total_seconds()) > POLYMARKET_CHALLENGE_CLOCK_SKEW_SECONDS:
                raise ChallengeError('Polymarket challenge trades must use current execution time')

        cursor.execute(
            """
            SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_participants cp
            JOIN agents a ON a.id = cp.agent_id
            WHERE cp.challenge_id = ? AND cp.agent_id = ?
            """,
            (challenge['id'], agent_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ChallengeError('Agent must join challenge before trading')
        participant = dict(row)
        participant['agent_identity_status'] = agent_identity_status(row)
        participant['agent_is_verified'] = agent_is_verified(row)
        if participant.get('status') not in {'joined', 'active'}:
            raise ChallengeError('Challenge participant is not tradeable')

        symbol = _normalize_challenge_trade_symbol(challenge, payload.get('symbol'))
        token_id = str(payload.get('token_id') or '').strip() or None
        outcome = str(payload.get('outcome') or '').strip() or None
        if challenge['market'] == 'polymarket':
            if side in {'short', 'cover'}:
                raise ChallengeError('Polymarket challenge trades support buy/sell outcome tokens only')
            token_id, outcome = _resolve_polymarket_challenge_contract(symbol, token_id=token_id, outcome=outcome)
        requested_price = price
        server_price = _fetch_authoritative_challenge_trade_price(
            challenge['market'],
            symbol,
            executed_at,
            token_id=token_id,
            outcome=outcome,
        )
        if server_price is not None:
            price = server_price
        cursor.execute(
            """
            SELECT *
            FROM challenge_trades
            WHERE challenge_id = ? AND agent_id = ?
            ORDER BY executed_at, id
            """,
            (challenge['id'], agent_id),
        )
        existing_trades = [dict(trade) for trade in cursor.fetchall()]
        proposed_trade = {
            'id': (max([int(trade.get('id') or 0) for trade in existing_trades], default=0) + 1),
            'market': challenge['market'],
            'symbol': symbol,
            'token_id': token_id,
            'outcome': outcome,
            'side': side,
            'price': price,
            'quantity': quantity,
            'executed_at': executed_at,
        }
        simulated = score_agent_trades(challenge, participant, [*existing_trades, proposed_trade])
        disqualified_reason = simulated.get('disqualified_reason')
        allowed_rule_disqualifications = {'max_position_pct_exceeded', 'max_drawdown_pct_exceeded'}
        if disqualified_reason and disqualified_reason not in allowed_rule_disqualifications:
            raise ChallengeError(f"Challenge trade rejected: {simulated['disqualified_reason']}")

        cursor.execute(
            """
            INSERT INTO challenge_trades
            (challenge_id, agent_id, source_signal_id, market, symbol, token_id, outcome, side, price, quantity, executed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge['id'],
                agent_id,
                None,
                challenge['market'],
                symbol,
                token_id,
                outcome,
                side,
                price,
                quantity,
                executed_at,
                utc_now_iso_z(),
            ),
        )
        trade_id = cursor.lastrowid
        updated_trade_count = len(existing_trades) + 1
        cursor.execute(
            """
            UPDATE challenge_participants
            SET trade_count = ?
            WHERE challenge_id = ? AND agent_id = ?
            """,
            (updated_trade_count, challenge['id'], agent_id),
        )
        content = (payload.get('content') or '').strip() or None
        if content:
            _create_submission_with_cursor(
                cursor,
                challenge,
                agent_id,
                'trade',
                content,
                None,
                None,
            )
        record_event(
            'challenge_trade_submitted',
            actor_agent_id=agent_id,
            object_type='challenge_trade',
            object_id=trade_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=participant.get('variant_key'),
            metadata={
                'challenge_key': challenge['challenge_key'],
                'challenge_id': challenge['id'],
                'symbol': symbol,
                'token_id': token_id,
                'outcome': outcome,
                'side': side,
                'price': price,
                'requested_price': requested_price,
                'quantity': quantity,
                'trade_count': updated_trade_count,
            },
            cursor=cursor,
        )
        conn.commit()

        cursor.execute(
            """
            SELECT *
            FROM challenge_trades
            WHERE challenge_id = ? AND agent_id = ?
            ORDER BY executed_at, id
            """,
            (challenge['id'], agent_id),
        )
        trades = [dict(trade) for trade in cursor.fetchall()]
        portfolio = _serialize_challenge_portfolio(challenge, participant, trades)
        return {'trade': trades[-1], **portfolio}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_challenge_team_trade(challenge_key: str, team_id: int, agent_id: int, data: Any) -> dict[str, Any]:
    payload = _model_dump(data)
    side = str(payload.get('side') or payload.get('action') or '').strip().lower()
    if side not in {'buy', 'sell', 'short', 'cover'}:
        raise ChallengeError('Unsupported challenge team trade side')
    try:
        price = float(payload.get('price'))
        quantity = float(payload.get('quantity'))
    except Exception as exc:
        raise ChallengeError('price and quantity are required') from exc
    if price <= 0 or quantity <= 0:
        raise ChallengeError('price and quantity must be positive')

    executed_at = _iso(_parse_dt(payload.get('executed_at')) or datetime.now(timezone.utc))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        if challenge['status'] != 'active':
            raise ChallengeError('Challenge is not active')
        executed_dt = _parse_dt(executed_at)
        if executed_dt < _parse_dt(challenge['start_at']) or executed_dt > _parse_dt(challenge['end_at']):
            raise ChallengeError('Challenge team trade must be inside challenge time window')
        if challenge['market'] == 'polymarket':
            current_dt = datetime.now(timezone.utc)
            if abs((current_dt - executed_dt).total_seconds()) > POLYMARKET_CHALLENGE_CLOCK_SKEW_SECONDS:
                raise ChallengeError('Polymarket challenge trades must use current execution time')

        team = _load_challenge_team(cursor, challenge['id'], int(team_id))
        if team.get('status') not in {'active', 'joined'}:
            raise ChallengeError('Challenge team is not tradeable')
        member = _require_challenge_team_member(cursor, challenge['id'], team['id'], agent_id)

        symbol = _normalize_challenge_trade_symbol(challenge, payload.get('symbol'))
        token_id = str(payload.get('token_id') or '').strip() or None
        outcome = str(payload.get('outcome') or '').strip() or None
        if challenge['market'] == 'polymarket':
            if side in {'short', 'cover'}:
                raise ChallengeError('Polymarket challenge trades support buy/sell outcome tokens only')
            token_id, outcome = _resolve_polymarket_challenge_contract(symbol, token_id=token_id, outcome=outcome)
        requested_price = price
        server_price = _fetch_authoritative_challenge_trade_price(
            challenge['market'],
            symbol,
            executed_at,
            token_id=token_id,
            outcome=outcome,
        )
        if server_price is not None:
            price = server_price

        cursor.execute(
            """
            SELECT *
            FROM challenge_team_trades
            WHERE challenge_id = ? AND team_id = ?
            ORDER BY executed_at, id
            """,
            (challenge['id'], team['id']),
        )
        existing_trades = [dict(trade) for trade in cursor.fetchall()]
        proposed_trade = {
            'id': (max([int(trade.get('id') or 0) for trade in existing_trades], default=0) + 1),
            'market': challenge['market'],
            'symbol': symbol,
            'token_id': token_id,
            'outcome': outcome,
            'side': side,
            'price': price,
            'quantity': quantity,
            'executed_at': executed_at,
            'agent_id': agent_id,
        }
        simulated = score_agent_trades(challenge, _team_participant_snapshot(team), [*existing_trades, proposed_trade])
        disqualified_reason = simulated.get('disqualified_reason')
        allowed_rule_disqualifications = {'max_position_pct_exceeded', 'max_drawdown_pct_exceeded'}
        if disqualified_reason and disqualified_reason not in allowed_rule_disqualifications:
            raise ChallengeError(f"Challenge team trade rejected: {simulated['disqualified_reason']}")

        cursor.execute(
            """
            INSERT INTO challenge_team_trades
            (challenge_id, team_id, agent_id, market, symbol, token_id, outcome, side, price, quantity, executed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge['id'],
                team['id'],
                agent_id,
                challenge['market'],
                symbol,
                token_id,
                outcome,
                side,
                price,
                quantity,
                executed_at,
                utc_now_iso_z(),
            ),
        )
        trade_id = cursor.lastrowid
        updated_trade_count = len(existing_trades) + 1
        cursor.execute(
            """
            UPDATE challenge_teams
            SET trade_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (updated_trade_count, utc_now_iso_z(), team['id']),
        )
        team['trade_count'] = updated_trade_count

        content = (payload.get('content') or '').strip() or None
        if content:
            _create_team_submission_with_cursor(
                cursor,
                challenge,
                team,
                member,
                'trade',
                content,
                None,
            )
        record_event(
            'challenge_team_trade_submitted',
            actor_agent_id=agent_id,
            object_type='challenge_team_trade',
            object_id=trade_id,
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            variant_key=member.get('variant_key') or team.get('variant_key'),
            metadata={
                'challenge_key': challenge['challenge_key'],
                'challenge_id': challenge['id'],
                'team_key': team['team_key'],
                'team_id': team['id'],
                'symbol': symbol,
                'token_id': token_id,
                'outcome': outcome,
                'side': side,
                'price': price,
                'requested_price': requested_price,
                'quantity': quantity,
                'trade_count': updated_trade_count,
            },
            cursor=cursor,
        )
        conn.commit()

        cursor.execute(
            """
            SELECT ctt.*, a.name AS agent_name
            FROM challenge_team_trades ctt
            JOIN agents a ON a.id = ctt.agent_id
            WHERE ctt.challenge_id = ? AND ctt.team_id = ?
            ORDER BY ctt.executed_at, ctt.id
            """,
            (challenge['id'], team['id']),
        )
        trades = [dict(trade) for trade in cursor.fetchall()]
        portfolio = _serialize_challenge_team_portfolio(challenge, team, member, trades)
        return {'trade': trades[-1], **portfolio}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_challenge_team_leaderboard(challenge_key: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        _require_team_challenge(challenge)
        teams = _list_challenge_teams_with_cursor(cursor, challenge['id'])
        cursor.execute(
            """
            SELECT *
            FROM challenge_team_trades
            WHERE challenge_id = ?
            ORDER BY team_id, executed_at, id
            """,
            (challenge['id'],),
        )
        trades_by_team: dict[int, list[dict[str, Any]]] = {}
        for row in cursor.fetchall():
            trade = dict(row)
            trades_by_team.setdefault(trade['team_id'], []).append(trade)

        def score_all(mark_prices: Optional[dict[Any, float]] = None, mark_timestamp: Optional[str] = None) -> list[dict[str, Any]]:
            scored_rows = []
            for team in teams:
                scored = score_agent_trades(
                    challenge,
                    _team_participant_snapshot(team),
                    trades_by_team.get(team['id'], []),
                    mark_prices=mark_prices,
                    mark_timestamp=mark_timestamp,
                )
                scored['team_id'] = team['id']
                scored['team_key'] = team.get('team_key')
                scored['team_name'] = team.get('name')
                scored['variant_key'] = team.get('variant_key')
                scored['member_count'] = team.get('member_count') or 0
                scored['submission_count'] = team.get('submission_count') or 0
                scored_rows.append(scored)
            return scored_rows

        scored = score_all()
        mark_timestamp = _live_mark_timestamp(challenge)
        if mark_timestamp:
            mark_prices = _fetch_live_mark_prices(scored, mark_timestamp)
            if mark_prices:
                scored = score_all(mark_prices=mark_prices, mark_timestamp=mark_timestamp)

        ranked_candidates = [
            row
            for row in scored
            if (
                not row.get('disqualified_reason')
                and row.get('final_score') is not None
                and int(row.get('trade_count') or 0) > 0
            )
        ]
        ranked_candidates.sort(key=lambda item: item['final_score'], reverse=True)
        rank_by_team = {item['team_id']: index + 1 for index, item in enumerate(ranked_candidates)}
        for row in scored:
            row['rank'] = rank_by_team.get(row['team_id'])
            row['metrics_json'] = _json_dumps(row.get('metrics'))
        scored.sort(key=lambda item: (item.get('rank') is None, item.get('rank') or 999999, item.get('team_id') or 0))
        return {'challenge': _serialize_challenge(challenge), 'leaderboard': scored, 'provisional': challenge.get('status') != 'settled'}
    finally:
        conn.close()


def _fetch_participants_and_trades(cursor: Any, challenge_id: int) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    cursor.execute(
        """
        SELECT cp.*, a.name AS agent_name, a.identity_status AS agent_identity_status
        FROM challenge_participants cp
        JOIN agents a ON a.id = cp.agent_id
        WHERE cp.challenge_id = ?
        ORDER BY cp.joined_at, cp.id
        """,
        (challenge_id,),
    )
    participants = []
    for row in cursor.fetchall():
        participant = dict(row)
        participant['agent_identity_status'] = agent_identity_status(row)
        participant['agent_is_verified'] = agent_is_verified(row)
        participants.append(participant)

    cursor.execute(
        """
        SELECT *
        FROM challenge_trades
        WHERE challenge_id = ?
        ORDER BY agent_id, executed_at, id
        """,
        (challenge_id,),
    )
    trades_by_agent: dict[int, list[dict[str, Any]]] = {}
    for row in cursor.fetchall():
        trade = dict(row)
        trades_by_agent.setdefault(trade['agent_id'], []).append(trade)

    return participants, trades_by_agent


def get_challenge_leaderboard(challenge_key: str) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        cursor.execute(
            """
            SELECT cr.*, a.name AS agent_name, a.identity_status AS agent_identity_status, cp.disqualified_reason, cp.trade_count
            FROM challenge_results cr
            JOIN agents a ON a.id = cr.agent_id
            LEFT JOIN challenge_participants cp ON cp.challenge_id = cr.challenge_id AND cp.agent_id = cr.agent_id
            WHERE cr.challenge_id = ?
            ORDER BY COALESCE(cr.rank, 999999), cr.final_score DESC, cr.id
            """,
            (challenge['id'],),
        )
        result_rows = []
        for row in cursor.fetchall():
            result_row = dict(row)
            result_row['agent_identity_status'] = agent_identity_status(row)
            result_row['agent_is_verified'] = agent_is_verified(row)
            result_rows.append(result_row)
        if result_rows and challenge.get('status') == 'settled':
            return {'challenge': _serialize_challenge(challenge), 'leaderboard': result_rows, 'provisional': False}

        participants, trades_by_agent = _fetch_participants_and_trades(cursor, challenge['id'])
        scored = _score_challenge_results_with_live_marks(challenge, participants, trades_by_agent)
        names = {item['agent_id']: item.get('agent_name') for item in participants}
        identities = {item['agent_id']: item.get('agent_identity_status') for item in participants}
        for item in scored:
            item['agent_name'] = names.get(item['agent_id'])
            item['agent_identity_status'] = agent_identity_status({'identity_status': identities.get(item['agent_id'])})
            item['agent_is_verified'] = item['agent_identity_status'] == 'verified'
            item['metrics_json'] = _json_dumps(item.get('metrics'))
        scored.sort(key=lambda item: (item.get('rank') is None, item.get('rank') or 999999))
        return {'challenge': _serialize_challenge(challenge), 'leaderboard': scored, 'provisional': True}
    finally:
        conn.close()


def _reward_points_for_rank(rules: dict[str, Any], rank: Optional[int]) -> int:
    if not rank or rules.get('grant_rewards') is False:
        return 0
    reward_points = rules.get('reward_points', DEFAULT_CHALLENGE_REWARDS)
    if isinstance(reward_points, list):
        return int(reward_points[rank - 1]) if rank - 1 < len(reward_points) else 0
    if isinstance(reward_points, dict):
        return int(reward_points.get(str(rank), reward_points.get(rank, 0)) or 0)
    return 0


def settle_challenge(challenge_key: str, *, force: bool = False) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        refresh_challenge_statuses(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        if challenge['status'] == 'settled' and not force:
            conn.commit()
            return get_challenge_leaderboard(challenge_key)
        if challenge['status'] == 'canceled':
            raise ChallengeError('Canceled challenge cannot be settled')

        participants, trades_by_agent = _fetch_participants_and_trades(cursor, challenge['id'])
        scored = score_challenge_results(challenge, participants, trades_by_agent)
        participant_by_agent = {item['agent_id']: item for item in participants}
        rules = _json_loads(challenge.get('rules_json'), {}) or {}
        now = utc_now_iso_z()

        if force:
            cursor.execute("DELETE FROM challenge_results WHERE challenge_id = ?", (challenge['id'],))

        for result in scored:
            participant = participant_by_agent[result['agent_id']]
            metrics_json = _json_dumps(result['metrics'])
            status = 'disqualified' if result.get('disqualified_reason') else 'settled'
            cursor.execute(
                """
                UPDATE challenge_participants
                SET status = ?, ending_value = ?, return_pct = ?, max_drawdown = ?,
                    trade_count = ?, rank = ?, disqualified_reason = ?
                WHERE challenge_id = ? AND agent_id = ?
                """,
                (
                    status,
                    result['ending_value'],
                    result['return_pct'],
                    result['max_drawdown'],
                    result['trade_count'],
                    result.get('rank'),
                    result.get('disqualified_reason'),
                    challenge['id'],
                    result['agent_id'],
                ),
            )
            cursor.execute(
                """
                INSERT INTO challenge_results
                (challenge_id, agent_id, return_pct, max_drawdown, risk_adjusted_score,
                 quality_score, final_score, rank, metrics_json, settled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    challenge['id'],
                    result['agent_id'],
                    result['return_pct'],
                    result['max_drawdown'],
                    result['risk_adjusted_score'],
                    result['quality_score'],
                    result.get('final_score'),
                    result.get('rank'),
                    metrics_json,
                    now,
                ),
            )

            if result.get('disqualified_reason'):
                record_event(
                    'challenge_disqualified',
                    actor_agent_id=result['agent_id'],
                    object_type='challenge_participant',
                    object_id=participant['id'],
                    market=challenge['market'],
                    experiment_key=challenge.get('experiment_key'),
                    variant_key=participant.get('variant_key'),
                    metadata={
                        'challenge_key': challenge['challenge_key'],
                        'reason': result['disqualified_reason'],
                    },
                    cursor=cursor,
                )
                continue

            reward_points = _reward_points_for_rank(rules, result.get('rank'))
            if reward_points > 0:
                grant_agent_reward(
                    result['agent_id'],
                    reward_points,
                    f"challenge_rank_{result['rank']}",
                    source_type='challenge',
                    source_id=challenge['id'],
                    experiment_key=challenge.get('experiment_key'),
                    variant_key=participant.get('variant_key'),
                    metadata={'challenge_key': challenge['challenge_key'], 'rank': result.get('rank')},
                    cursor=cursor,
                )
                record_event(
                    'challenge_reward_granted',
                    actor_agent_id=result['agent_id'],
                    object_type='challenge',
                    object_id=challenge['id'],
                    market=challenge['market'],
                    experiment_key=challenge.get('experiment_key'),
                    variant_key=participant.get('variant_key'),
                    metadata={
                        'challenge_key': challenge['challenge_key'],
                        'rank': result.get('rank'),
                        'points': reward_points,
                    },
                    cursor=cursor,
                )

        cursor.execute(
            """
            UPDATE challenges
            SET status = 'settled', settled_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, challenge['id']),
        )
        record_event(
            'challenge_settled',
            object_type='challenge',
            object_id=challenge['id'],
            market=challenge['market'],
            experiment_key=challenge.get('experiment_key'),
            metadata={'challenge_key': challenge['challenge_key'], 'participant_count': len(participants)},
            cursor=cursor,
        )
        conn.commit()
        return get_challenge_leaderboard(challenge_key)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def settle_due_challenges(limit: int = 20) -> list[dict[str, Any]]:
    now = utc_now_iso_z()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        cursor.execute(
            """
            SELECT challenge_key
            FROM challenges
            WHERE status = 'active' AND end_at <= ?
            ORDER BY end_at ASC
            LIMIT ?
            """,
            (now, max(1, min(limit, 100))),
        )
        keys = [row['challenge_key'] for row in cursor.fetchall()]
    finally:
        conn.close()

    settled = []
    for key in keys:
        settled.append(settle_challenge(key))
    return settled


def cancel_challenge(challenge_key: str, agent_id: int) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        begin_write_transaction(cursor)
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        if challenge.get('created_by_agent_id') and challenge['created_by_agent_id'] != agent_id:
            raise ChallengeError('Only the creator can cancel this challenge')
        if challenge['status'] == 'settled':
            raise ChallengeError('Settled challenge cannot be canceled')
        now = utc_now_iso_z()
        cursor.execute(
            "UPDATE challenges SET status = 'canceled', updated_at = ? WHERE id = ?",
            (now, challenge['id']),
        )
        conn.commit()
        return get_challenge(challenge_key)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_agent_challenges(agent_id: int) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        refresh_challenge_statuses(cursor)
        conn.commit()
        cursor.execute(
            """
            SELECT c.*, cp.status AS participant_status, cp.variant_key, cp.joined_at,
                   cp.return_pct, cp.max_drawdown, cp.trade_count, cp.rank,
                   cp.disqualified_reason,
                   (SELECT COUNT(*) FROM challenge_participants count_cp WHERE count_cp.challenge_id = c.id) AS participant_count
            FROM challenge_participants cp
            JOIN challenges c ON c.id = cp.challenge_id
            WHERE cp.agent_id = ?
            ORDER BY c.status = 'active' DESC, c.start_at DESC, c.id DESC
            """,
            (agent_id,),
        )
        personal_challenges = [_serialize_challenge(row, row['participant_count']) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT c.*, ctm.role AS team_role, ctm.variant_key AS team_member_variant_key,
                   ctm.joined_at AS team_joined_at, ct.id AS team_id, ct.team_key,
                   ct.name AS team_name, ct.rank AS team_rank, ct.return_pct AS team_return_pct,
                   ct.max_drawdown AS team_max_drawdown, ct.trade_count AS team_trade_count,
                   (SELECT COUNT(*) FROM challenge_participants count_cp WHERE count_cp.challenge_id = c.id) AS participant_count,
                   (SELECT COUNT(*) FROM challenge_teams count_ct WHERE count_ct.challenge_id = c.id) AS team_count
            FROM challenge_team_members ctm
            JOIN challenge_teams ct ON ct.id = ctm.team_id
            JOIN challenges c ON c.id = ctm.challenge_id
            WHERE ctm.agent_id = ?
            ORDER BY c.status = 'active' DESC, c.start_at DESC, c.id DESC
            """,
            (agent_id,),
        )
        team_challenges = []
        for row in cursor.fetchall():
            challenge = _serialize_challenge(row, row['participant_count'])
            challenge['team_count'] = row['team_count']
            challenge['team_id'] = row['team_id']
            challenge['team_key'] = row['team_key']
            challenge['team_name'] = row['team_name']
            challenge['team_role'] = row['team_role']
            challenge['team_joined_at'] = row['team_joined_at']
            challenge['team_member_variant_key'] = row['team_member_variant_key']
            challenge['team_rank'] = row['team_rank']
            challenge['team_return_pct'] = row['team_return_pct']
            challenge['team_max_drawdown'] = row['team_max_drawdown']
            challenge['team_trade_count'] = row['team_trade_count']
            team_challenges.append(challenge)
        return {'challenges': personal_challenges, 'team_challenges': team_challenges}
    finally:
        conn.close()


def get_challenge_submissions(challenge_key: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        challenge = _load_challenge(cursor, challenge_key=challenge_key)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM challenge_submissions WHERE challenge_id = ?",
            (challenge['id'],),
        )
        total = cursor.fetchone()['total']
        cursor.execute(
            """
            SELECT cs.*, a.name AS agent_name, a.identity_status AS agent_identity_status
            FROM challenge_submissions cs
            JOIN agents a ON a.id = cs.agent_id
            WHERE cs.challenge_id = ?
            ORDER BY cs.created_at DESC, cs.id DESC
            LIMIT ? OFFSET ?
            """,
            (challenge['id'], limit, offset),
        )
        submissions = []
        for row in cursor.fetchall():
            submission = dict(row)
            submission['agent_identity_status'] = agent_identity_status(row)
            submission['agent_is_verified'] = agent_is_verified(row)
            submissions.append(submission)
        return {
            'challenge': _serialize_challenge(challenge),
            'submissions': submissions,
            'total': total,
        }
    finally:
        conn.close()
