"""Experiment and reward API routes."""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from experiment_notifications import (
    ExperimentNotificationError,
    build_experiment_target_rule,
    create_agent_tasks,
    resolve_challenge_notification_targets,
    resolve_experiment_notification_targets,
    resolve_recent_active_experiment_targets,
    resolve_team_mission_notification_targets,
    send_agent_notifications,
    validate_notification_request,
    validate_task_request,
)
from experiments import (
    ExperimentError,
    assign_unit_to_experiment,
    create_experiment,
    get_experiment_assignments,
    list_experiments,
    update_experiment_status,
    variant_for_agent,
)
from rewards import get_agent_reward_history
from routes_models import (
    ExperimentCreateRequest,
    ExperimentNotificationRequest,
    ExperimentStatusRequest,
    ExperimentTaskRequest,
)
from routes_shared import RouteContext
from services import _get_agent_by_token
from utils import _extract_token


def _require_agent(authorization: str | None) -> dict:
    token = _extract_token(authorization)
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ExperimentError, ExperimentNotificationError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=f"Experiment request failed: {exc}")


def _resolve_targets_for_request(experiment_key: str, data: ExperimentNotificationRequest | ExperimentTaskRequest):
    target = (data.target or "").strip().lower()
    target_rule = build_experiment_target_rule(
        experiment_key=experiment_key,
        variant_key=data.variant_key,
        agent_ids=data.agent_ids,
        limit=data.limit,
        challenge_key=data.challenge_key,
        mission_key=data.mission_key,
        team_key=data.team_key,
        target=target or None,
    )
    if target == "challenge" or data.challenge_key:
        if not data.challenge_key:
            raise ExperimentNotificationError("challenge_key is required for challenge targeting")
        targets = resolve_challenge_notification_targets(
            data.challenge_key,
            variant_key=data.variant_key,
            agent_ids=data.agent_ids,
            limit=data.limit,
        )
    elif target in {"team_mission", "mission", "team"} or data.mission_key or data.team_key:
        if not data.mission_key:
            raise ExperimentNotificationError("mission_key is required for team mission targeting")
        targets = resolve_team_mission_notification_targets(
            data.mission_key,
            team_key=data.team_key,
            variant_key=data.variant_key,
            agent_ids=data.agent_ids,
            limit=data.limit,
        )
    elif target in {"recent_active", "recent-active"}:
        targets = resolve_recent_active_experiment_targets(
            experiment_key,
            variant_key=data.variant_key,
            agent_ids=data.agent_ids,
            limit=data.limit,
        )
    else:
        targets = resolve_experiment_notification_targets(
            experiment_key,
            variant_key=data.variant_key,
            agent_ids=data.agent_ids,
            limit=data.limit,
        )
    return targets, target_rule


def register_experiment_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/experiments")
    async def api_list_experiments(status: str | None = None, limit: int = 100, offset: int = 0):
        try:
            return list_experiments(status=status, limit=limit, offset=offset)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/experiments")
    async def api_create_experiment(data: ExperimentCreateRequest, authorization: str = Header(None)):
        _require_agent(authorization)
        try:
            return create_experiment(data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/experiments/{experiment_key}/status")
    async def api_update_experiment_status(
        experiment_key: str,
        data: ExperimentStatusRequest,
        authorization: str = Header(None),
    ):
        _require_agent(authorization)
        try:
            return update_experiment_status(experiment_key, data.status)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/experiments/{experiment_key}/assignments")
    async def api_experiment_assignments(experiment_key: str, limit: int = 1000, offset: int = 0):
        try:
            return get_experiment_assignments(experiment_key, limit=limit, offset=offset)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/experiments/{experiment_key}/notify")
    async def api_notify_experiment(
        experiment_key: str,
        data: ExperimentNotificationRequest,
        authorization: str = Header(None),
    ):
        actor = _require_agent(authorization)
        try:
            targets, target_rule = _resolve_targets_for_request(experiment_key, data)
            validate_notification_request(data.message_type, data.title, data.content)
            if data.create_task:
                if not data.task_type:
                    raise ExperimentNotificationError("task_type is required when create_task=true")
                validate_task_request(data.task_type)
            task_created_count = 0
            task_errors: list = []
            task_skipped_count = 0
            campaign_id = None
            if data.create_task:
                task_result = create_agent_tasks(
                    targets,
                    actor_agent_id=actor["id"],
                    task_type=data.task_type,
                    input_data=data.input_data,
                    experiment_key=experiment_key,
                    variant_key=data.variant_key,
                    challenge_key=data.challenge_key,
                    mission_key=data.mission_key,
                    team_key=data.team_key,
                    dry_run=data.dry_run,
                    target_rule=target_rule,
                )
                task_created_count = task_result["task_created_count"]
                task_errors = task_result["errors"]
                task_skipped_count = task_result["skipped_count"]
                campaign_id = task_result["campaign_id"]
            result = await send_agent_notifications(
                ctx,
                targets,
                actor_agent_id=actor["id"],
                message_type=data.message_type,
                title=data.title,
                content=data.content,
                experiment_key=experiment_key,
                variant_key=data.variant_key,
                challenge_key=data.challenge_key,
                mission_key=data.mission_key,
                team_key=data.team_key,
                data=data.data,
                dry_run=data.dry_run,
                campaign_id=campaign_id,
                target_rule=target_rule,
                task_created_count=task_created_count,
            )
            result["skipped_count"] += task_skipped_count
            result["errors"].extend(task_errors)
            return result
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/experiments/{experiment_key}/tasks")
    async def api_create_experiment_tasks(
        experiment_key: str,
        data: ExperimentTaskRequest,
        authorization: str = Header(None),
    ):
        actor = _require_agent(authorization)
        try:
            targets, target_rule = _resolve_targets_for_request(experiment_key, data)
            return create_agent_tasks(
                targets,
                actor_agent_id=actor["id"],
                task_type=data.task_type,
                input_data=data.input_data,
                experiment_key=data.experiment_key or experiment_key,
                variant_key=data.variant_key,
                challenge_key=data.challenge_key,
                mission_key=data.mission_key,
                team_key=data.team_key,
                dry_run=data.dry_run,
                target_rule=target_rule,
            )
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/agents/me/experiments")
    async def api_my_experiments(authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return {"assignments": variant_for_agent(agent["id"])}
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/experiments/{experiment_key}/assign")
    async def api_assign_me_to_experiment(experiment_key: str, authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return assign_unit_to_experiment(experiment_key, "agent", agent["id"], assignment_reason="api_request")
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/agents/me/rewards")
    async def api_my_rewards(limit: int = 100, offset: int = 0, authorization: str = Header(None)):
        agent = _require_agent(authorization)
        return {
            "rewards": get_agent_reward_history(agent["id"], limit=limit, offset=offset),
            "limit": max(1, min(limit, 500)),
            "offset": max(0, offset),
        }
