"""Research export API routes."""

from __future__ import annotations

import csv
import io

from fastapi import FastAPI, Response

from research_exports import (
    RESEARCH_EXPORTS,
    fetch_research_export_rows,
    get_research_dataset_names,
    normalize_dataset_name,
    research_schema_for_dataset,
)
from routes_shared import RouteContext


def _csv_response(filename: str, columns: list[str], rows: list[dict]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _bool_param(value: bool | str | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def register_research_routes(app: FastAPI, ctx: RouteContext) -> None:
    def _fetch(
        dataset_name: str,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool | str | None = True,
        include_content: bool | str | None = True,
        limit: int = 100000,
        offset: int = 0,
    ) -> tuple[str, list[str], list[dict]]:
        filename = normalize_dataset_name(dataset_name)
        if filename not in RESEARCH_EXPORTS:
            raise ValueError(f"Unsupported export: {dataset_name}")
        columns, rows = fetch_research_export_rows(
            filename,
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            variant_key=variant_key,
            market=market,
            agent_ids=agent_ids,
            anonymize=_bool_param(anonymize, True),
            include_content=_bool_param(include_content, True),
            limit=limit,
            offset=offset,
        )
        return filename, columns, rows

    @app.get("/api/research/datasets")
    async def api_research_datasets():
        return {"datasets": get_research_dataset_names()}

    @app.get("/api/research/events")
    async def api_research_events(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 1000,
        offset: int = 0,
    ):
        _filename, columns, rows = _fetch(
            "events",
            start_at=start_at,
            end_at=end_at,
            experiment_key=experiment_key,
            variant_key=variant_key,
            market=market,
            agent_ids=agent_ids,
            anonymize=anonymize,
            include_content=include_content,
            limit=limit,
            offset=offset,
        )
        return {"columns": columns, "events": rows, "limit": max(1, min(limit, 100000)), "offset": max(0, offset)}

    @app.get("/api/research/export/{dataset_name}.csv")
    async def api_research_export_csv(
        dataset_name: str,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 100000,
        offset: int = 0,
    ):
        try:
            filename, columns, rows = _fetch(
                dataset_name,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                agent_ids=agent_ids,
                anonymize=anonymize,
                include_content=include_content,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return _csv_response(filename, columns, rows)

    @app.get("/api/research/export/{dataset_name}.json")
    async def api_research_export_json(
        dataset_name: str,
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        agent_ids: str | None = None,
        anonymize: bool = True,
        include_content: bool = True,
        limit: int = 100000,
        offset: int = 0,
    ):
        try:
            filename, columns, rows = _fetch(
                dataset_name,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                agent_ids=agent_ids,
                anonymize=anonymize,
                include_content=include_content,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return {"dataset": filename, "columns": columns, "rows": rows, "limit": max(1, min(limit, 100000)), "offset": max(0, offset)}

    @app.get("/api/research/schema/{dataset_name}")
    async def api_research_schema(dataset_name: str):
        try:
            return research_schema_for_dataset(dataset_name)
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)

    async def _download(
        filename: str,
        start_at: str | None,
        end_at: str | None,
        experiment_key: str | None,
        variant_key: str | None,
        market: str | None,
        limit: int,
        offset: int,
    ) -> Response:
        try:
            normalized, columns, rows = _fetch(
                filename,
                start_at=start_at,
                end_at=end_at,
                experiment_key=experiment_key,
                variant_key=variant_key,
                market=market,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return Response(content=str(exc), status_code=400)
        return _csv_response(normalized, columns, rows)

    @app.get("/api/research/agents.csv")
    async def api_research_agents_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("agents.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/events.csv")
    async def api_research_events_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("events.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/signals.csv")
    async def api_research_signals_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("signals.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)

    @app.get("/api/research/network_edges.csv")
    async def api_research_network_edges_csv(
        start_at: str | None = None,
        end_at: str | None = None,
        experiment_key: str | None = None,
        variant_key: str | None = None,
        market: str | None = None,
        limit: int = 100000,
        offset: int = 0,
    ):
        return await _download("network_edges.csv", start_at, end_at, experiment_key, variant_key, market, limit, offset)
