"""Team mission API routes."""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

from experiment_notifications import (
    ExperimentNotificationError,
    build_experiment_target_rule,
    resolve_team_mission_notification_targets,
    send_agent_notifications,
)
from routes_models import (
    ExperimentNotificationRequest,
    TeamJoinRequest,
    TeamMessageLinkRequest,
    TeamMissionCreateRequest,
    TeamMissionSettleRequest,
    TeamSubmissionRequest,
)
from routes_shared import RouteContext
from services import _get_agent_by_token
from team_missions import (
    TeamMissionError,
    TeamMissionNotFound,
    auto_form_teams,
    create_team_for_mission,
    create_team_mission,
    get_agent_team_missions,
    get_mission_teams,
    get_team,
    get_team_mission,
    get_team_mission_leaderboard,
    get_team_submissions,
    join_team,
    join_team_mission,
    link_signal_to_team,
    list_team_missions,
    settle_team_mission,
)
from utils import _extract_token


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TeamMissionNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (TeamMissionError, ExperimentNotificationError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=f"Team mission request failed: {exc}")


def _require_agent(authorization: str | None) -> dict:
    token = _extract_token(authorization)
    agent = _get_agent_by_token(token)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid token")
    return agent


def register_team_mission_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/team-missions")
    async def api_list_team_missions(status: str | None = None, limit: int = 50, offset: int = 0):
        try:
            return list_team_missions(status=status, limit=limit, offset=offset)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions")
    async def api_create_team_mission(data: TeamMissionCreateRequest, authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return create_team_mission(data, created_by_agent_id=agent["id"])
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/team-missions/me")
    async def api_my_team_missions(authorization: str = Header(None)):
        agent = _require_agent(authorization)
        try:
            return get_agent_team_missions(agent["id"])
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/team-missions/{mission_key}/teams")
    async def api_mission_teams(mission_key: str):
        try:
            return get_mission_teams(mission_key)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/team-missions/{mission_key}/leaderboard")
    async def api_mission_leaderboard(mission_key: str):
        try:
            return get_team_mission_leaderboard(mission_key)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions/{mission_key}/join")
    async def api_join_team_mission(
        mission_key: str,
        data: TeamJoinRequest | None = None,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return join_team_mission(mission_key, agent["id"], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions/{mission_key}/teams")
    async def api_create_team(
        mission_key: str,
        data: TeamJoinRequest | None = None,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return create_team_for_mission(mission_key, agent["id"], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions/{mission_key}/auto-form-teams")
    async def api_auto_form_teams(
        mission_key: str,
        data: TeamMissionSettleRequest | None = None,
        authorization: str = Header(None),
    ):
        _require_agent(authorization)
        try:
            return auto_form_teams(mission_key, assignment_mode=data.assignment_mode if data else None)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions/{mission_key}/settle")
    async def api_settle_team_mission(
        mission_key: str,
        data: TeamMissionSettleRequest | None = None,
        authorization: str = Header(None),
    ):
        _require_agent(authorization)
        try:
            return settle_team_mission(mission_key, force=bool(data.force if data else False))
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/team-missions/{mission_key}/notify")
    async def api_notify_team_mission(
        mission_key: str,
        data: ExperimentNotificationRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            mission = get_team_mission(mission_key)
            experiment_key = mission.get("experiment_key") or (data.data or {}).get("experiment_key") or ""
            targets = resolve_team_mission_notification_targets(
                mission_key,
                team_key=data.team_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
            )
            target_rule = build_experiment_target_rule(
                experiment_key=experiment_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
                mission_key=mission_key,
                team_key=data.team_key,
                target="team_mission",
            )
            return await send_agent_notifications(
                ctx,
                targets,
                actor_agent_id=agent["id"],
                message_type=data.message_type,
                title=data.title,
                content=data.content,
                experiment_key=experiment_key or None,
                variant_key=data.variant_key,
                mission_key=mission_key,
                team_key=data.team_key,
                data=data.data,
                dry_run=data.dry_run,
                event_type="team_mission_notification_sent",
                target_rule=target_rule,
            )
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/team-missions/{mission_key}")
    async def api_get_team_mission(mission_key: str):
        try:
            return get_team_mission(mission_key)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/teams/{team_key}/submissions")
    async def api_team_submissions(team_key: str):
        try:
            return get_team_submissions(team_key)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/teams/{team_key}/join")
    async def api_join_team(
        team_key: str,
        data: TeamJoinRequest | None = None,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return join_team(team_key, agent["id"], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/teams/{team_key}/messages/link-signal")
    async def api_link_team_signal(
        team_key: str,
        data: TeamMessageLinkRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            return link_signal_to_team(team_key, agent["id"], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/teams/{team_key}/submit")
    async def api_submit_team(
        team_key: str,
        data: TeamSubmissionRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            from team_missions import submit_team

            return submit_team(team_key, agent["id"], data)
        except Exception as exc:
            raise _to_http_error(exc)

    @app.post("/api/teams/{team_key}/notify")
    async def api_notify_team(
        team_key: str,
        data: ExperimentNotificationRequest,
        authorization: str = Header(None),
    ):
        agent = _require_agent(authorization)
        try:
            team = get_team(team_key)
            mission = team.get("mission") or {}
            mission_key = mission.get("mission_key") or data.mission_key
            if not mission_key:
                raise ExperimentNotificationError("mission_key is required for team targeting")
            experiment_key = mission.get("experiment_key") or (data.data or {}).get("experiment_key") or ""
            targets = resolve_team_mission_notification_targets(
                mission_key,
                team_key=team_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
            )
            target_rule = build_experiment_target_rule(
                experiment_key=experiment_key,
                variant_key=data.variant_key,
                agent_ids=data.agent_ids,
                limit=data.limit,
                mission_key=mission_key,
                team_key=team_key,
                target="team",
            )
            return await send_agent_notifications(
                ctx,
                targets,
                actor_agent_id=agent["id"],
                message_type=data.message_type,
                title=data.title,
                content=data.content,
                experiment_key=experiment_key or None,
                variant_key=data.variant_key,
                mission_key=mission_key,
                team_key=team_key,
                data=data.data,
                dry_run=data.dry_run,
                event_type="team_mission_notification_sent",
                target_rule=target_rule,
            )
        except Exception as exc:
            raise _to_http_error(exc)

    @app.get("/api/teams/{team_key}")
    async def api_get_team(team_key: str):
        try:
            return get_team(team_key)
        except Exception as exc:
            raise _to_http_error(exc)
