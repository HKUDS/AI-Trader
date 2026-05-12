"""Challenge API routes."""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from challenges import (
    ChallengeError,
    ChallengeNotFound,
    cancel_challenge,
    create_challenge,
    create_submission,
    get_agent_challenges,
    get_challenge,
    get_challenge_leaderboard,
    get_challenge_submissions,
    join_challenge,
    list_challenges,
    settle_challenge,
)
from experiment_notifications import (
    ExperimentNotificationError,
    build_experiment_target_rule,
    resolve_challenge_notification_targets,
    send_agent_notifications,
)
from routes_models import (
    ChallengeCreateRequest,
    ChallengeJoinRequest,
    ExperimentNotificationRequest,
    ChallengeSettleRequest,
    ChallengeSubmissionRequest,
)
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ChallengeNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ChallengeError, ExperimentNotificationError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=f'Challenge request failed: {exc}')


def _require_agent(authorization: str | None) -> dict:
    token = _extract_token(authorization)
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail='Invalid token')
    return agent


def _require_challenge_creator(challenge_key: str, agent_id: int) -> None:
    challenge = get_challenge(challenge_key)
    creator_id = challenge.get('created_by_agent_id')
    if creator_id and creator_id != agent_id:
        raise HTTPException(status_code=403, detail='Only the challenge creator can perform this action')


def register_challenge_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get('/api/challenges')
    async def api_list_challenges(status: str | None = None, limit: int = 50, offset: int = 0):
        try:
            return list_challenges(status=status, limit=limit, offset=offset)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges')
    async def api_create_challenge(data: ChallengeCreateRequest, authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return create_challenge(data, agent['id'])
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get('/api/challenges/me')
    async def api_my_challenges(authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return get_agent_challenges(agent['id'])
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get('/api/challenges/{challenge_key}/leaderboard')
    async def api_challenge_leaderboard(challenge_key: str):
        try:
            return get_challenge_leaderboard(challenge_key)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get('/api/challenges/{challenge_key}/submissions')
    async def api_challenge_submissions(challenge_key: str, limit: int = 100, offset: int = 0):
        try:
            return get_challenge_submissions(challenge_key, limit=limit, offset=offset)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges/{challenge_key}/join')
    async def api_join_challenge(
        challenge_key: str,
        data: ChallengeJoinRequest | None = None,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return join_challenge(challenge_key, agent['id'], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges/{challenge_key}/submit')
    async def api_submit_challenge(
        challenge_key: str,
        data: ChallengeSubmissionRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return create_submission(challenge_key, agent['id'], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges/{challenge_key}/settle')
    async def api_settle_challenge(
        challenge_key: str,
        data: ChallengeSettleRequest | None = None,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            _require_challenge_creator(challenge_key, agent['id'])
            return settle_challenge(challenge_key, force=bool(data.force if data else False))
        except HTTPException:
            raise
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges/{challenge_key}/cancel')
    async def api_cancel_challenge(challenge_key: str, authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return cancel_challenge(challenge_key, agent['id'])
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post('/api/challenges/{challenge_key}/notify')
    async def api_notify_challenge(
        challenge_key: str,
        data: ExperimentNotificationRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            challenge = get_challenge(challenge_key)
            experiment_key = challenge.get('experiment_key') or (data.data or {}).get('experiment_key') or ''
            targets = resolve_challenge_notification_targets(
                challenge_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
            )
            target_rule = build_experiment_target_rule(
                experiment_key=experiment_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
                challenge_key=challenge_key,
                target='challenge',
            )
            return await send_agent_notifications(
                ctx,
                targets,
                actor_agent_id=agent['id'],
                message_type=data.message_type,
                title=data.title,
                content=data.content,
                experiment_key=experiment_key or None,
                variant_key=data.variant_key,
                challenge_key=challenge_key,
                data=data.data,
                dry_run=data.dry_run,
                event_type='challenge_notification_sent',
                target_rule=target_rule,
            )
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get('/api/challenges/{challenge_key}')
    async def api_get_challenge(challenge_key: str):
        try:
            return get_challenge(challenge_key)
        except Exception as exc:
            raise _to_http_error(exc)
