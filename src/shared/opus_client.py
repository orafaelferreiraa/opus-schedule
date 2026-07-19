"""
Cliente HTTP para a OpusClip REST API.
Autenticacao via API Key (Bearer token).
Secrets carregados de variaveis de ambiente / Key Vault references.

Usa httpx 0.28+ conforme best practices de I/O moderno em Azure Functions Python v2.
"""

from __future__ import annotations

import os
import time
from time import perf_counter

import httpx

from shared.telemetry import attrs, logger, mark_error, mark_ok, publish_latency_ms, tracer

_BASE = "https://api.opus.pro/api"
_SCHEDULER_RATE_LIMIT_S = 1.1  # 1 req/s para publish-schedules (limite da API)


class OpusClient:
    def __init__(self) -> None:
        api_key = os.environ["OPUSCLIP_API_KEY"]
        self._org_id = os.environ.get("OPUSCLIP_ORG_ID", "")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **({"x-opus-org-id": self._org_id} if self._org_id else {}),
        }

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        with tracer.start_as_current_span(f"opus.get {path}") as span:
            started_at = perf_counter()
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(f"{_BASE}{path}", headers=self._headers, params=params)
                    resp.raise_for_status()
                    mark_ok(span, http_method="GET", http_route=path, http_status_code=resp.status_code)
                    return resp.json()
            except Exception as exc:
                mark_error(span, exc, http_method="GET", http_route=path)
                raise
            finally:
                span.set_attribute("lowopscast_http_duration_ms", round((perf_counter() - started_at) * 1000, 2))

    def _post(self, path: str, json: dict) -> dict:
        with tracer.start_as_current_span(f"opus.post {path}") as span:
            started_at = perf_counter()
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(f"{_BASE}{path}", headers=self._headers, json=json)
                    resp.raise_for_status()
                    mark_ok(span, http_method="POST", http_route=path, http_status_code=resp.status_code)
                    return resp.json()
            except Exception as exc:
                mark_error(span, exc, http_method="POST", http_route=path)
                raise
            finally:
                span.set_attribute("lowopscast_http_duration_ms", round((perf_counter() - started_at) * 1000, 2))

    def _put(self, path: str, json: dict) -> dict | list | str:
        with tracer.start_as_current_span(f"opus.put {path}") as span:
            started_at = perf_counter()
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.put(f"{_BASE}{path}", headers=self._headers, json=json)
                    resp.raise_for_status()
                    mark_ok(span, http_method="PUT", http_route=path, http_status_code=resp.status_code)
                    if not resp.text:
                        return ""
                    return resp.json()
            except Exception as exc:
                mark_error(span, exc, http_method="PUT", http_route=path)
                raise
            finally:
                span.set_attribute("lowopscast_http_duration_ms", round((perf_counter() - started_at) * 1000, 2))

    # ------------------------------------------------------------------
    # Social accounts
    # ------------------------------------------------------------------

    def get_social_accounts(self) -> list[dict]:
        """Retorna as contas sociais conectadas a conta OpusClip."""
        data = self._get("/social-accounts", params={"q": "mine"})
        return data if isinstance(data, list) else data.get("data", [])

    # ------------------------------------------------------------------
    # Clips
    # ------------------------------------------------------------------

    def get_clips_by_project(self, project_id: str, page_size: int = 50) -> list[dict]:
        """Lista todos os clips de um projeto (com paginacao automatica)."""
        return self._paginate_clips("findByProjectId", projectId=project_id, page_size=page_size)

    def get_clips_by_collection(self, collection_id: str, page_size: int = 50) -> list[dict]:
        """Lista todos os clips de uma colecao (com paginacao automatica)."""
        return self._paginate_clips("findByCollectionId", collectionId=collection_id, page_size=page_size)

    def _paginate_clips(self, q: str, page_size: int = 50, **kwargs) -> list[dict]:
        clips: list[dict] = []
        page = 1

        with tracer.start_as_current_span("opus.paginate_clips") as span:
            span.set_attribute("lowopscast_query", q)
            span.set_attribute("lowopscast_page_size", page_size)
            while True:
                params = {"q": q, "pageNum": page, "pageSize": page_size, **kwargs}
                data = self._get("/exportable-clips", params=params)
                page_clips = data if isinstance(data, list) else data.get("data", [])
                if not page_clips:
                    break
                clips.extend(page_clips)
                if len(page_clips) < page_size:
                    break
                page += 1
            mark_ok(span, lowopscast_pages=page, lowopscast_clips_count=len(clips))
        return clips

    def prepare_clips_for_split_layout(self, clips: list[dict]) -> list[dict]:
        updated: list[dict] = []

        with tracer.start_as_current_span("opus.prepare_clips_for_split_layout") as span:
            span.set_attribute("lowopscast_clips_count", len(clips))
            for clip in clips:
                full_id = clip.get("id", "")
                if not full_id:
                    continue

                payload = {
                    "renderPref": {
                        "enableSplitLayout": True,
                        "enableFillLayout": False,
                        "enableFitLayout": False,
                        "disableFillLayout": True,
                        "disableFitLayout": True,
                        "layoutAspectRatio": "portrait",
                        "removeFillerWord": True,
                        "removePause": True,
                        "enableEmoji": False,
                    }
                }
                self._put(f"/exportable-clips/{full_id}", json=payload)
                updated.append({
                    "id": full_id,
                    "projectId": clip.get("projectId", ""),
                })

            mark_ok(span, lowopscast_clips_updated=len(updated))

        return updated

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def create_schedules(self, plan: dict) -> list[dict]:
        """
        Cria os agendamentos para cada (clip, rede, horario) no plano.

        with tracer.start_as_current_span("opus.create_schedules_batch") as span:
            span.set_attribute("lowopscast_networks_count", len(plan))
            for network, items in plan.items():
                for item in items:
                    result = self._schedule_one(network, item)
                    results.append(result)
                    time.sleep(_SCHEDULER_RATE_LIMIT_S)  # respeitar 1 req/s
            mark_ok(
                span,
                lowopscast_scheduled_count=len([r for r in results if r.get("ok")]),
                lowopscast_failed_count=len([r for r in results if not r.get("ok")]),
            )
            ...
          ],
          ...
        }
        """
        results: list[dict] = []
        for network, items in plan.items():
            for item in items:
                result = self._schedule_one(network, item)
                results.append(result)
                time.sleep(_SCHEDULER_RATE_LIMIT_S)  # respeitar 1 req/s
        return results

    def _schedule_one(self, network: str, item: dict) -> dict:
        payload = {
            "projectId": item["projectId"],
            "clipId": item["clipId"],
            "postAccountId": item["postAccountId"],
            "postDetail": {
                "title": item.get("title", "")[:100],
                "mediaType": "video",
                "custom": {
                    "description": item.get("description", ""),
                },
            },
            "publishAt": item["publishAt"],
        }
        if item.get("subAccountId"):
            payload["subAccountId"] = item["subAccountId"]

        started_at = perf_counter()

        with tracer.start_as_current_span("opus.publish_schedule") as span:
            op_attrs = attrs(
                lowopscast_network=network,
                lowopscast_clip_id=item["clipId"],
                lowopscast_project_id=item["projectId"],
                lowopscast_publish_at=item["publishAt"],
            )
            for key, value in op_attrs.items():
                span.set_attribute(key, value)

            try:
                data = self._post("/publish-schedules", json=payload)
                schedule_id = data.get("data", {}).get("scheduleId", "")
                elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
                publish_latency_ms.record(elapsed_ms, op_attrs)
                logger.info(
                    "Agendamento criado",
                    extra={
                        "custom_dimensions": {
                            **op_attrs,
                            "lowopscast_schedule_id": schedule_id,
                            "lowopscast_publish_latency_ms": elapsed_ms,
                        }
                    },
                )
                mark_ok(
                    span,
                    lowopscast_schedule_id=schedule_id,
                    lowopscast_publish_latency_ms=elapsed_ms,
                )
                return {
                    "ok": True,
                    "clipId": item["clipId"],
                    "network": network,
                    "scheduleId": schedule_id,
                    "publishAt": item["publishAt"],
                }
            except httpx.HTTPStatusError as exc:
                elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
                publish_latency_ms.record(elapsed_ms, op_attrs)
                logger.error(
                    "Falha ao agendar clip",
                    extra={
                        "custom_dimensions": {
                            **op_attrs,
                            "http_status_code": exc.response.status_code,
                            "lowopscast_publish_latency_ms": elapsed_ms,
                            "lowopscast_error": exc.response.text[:2048],
                        }
                    },
                )
                mark_error(
                    span,
                    exc,
                    http_status_code=exc.response.status_code,
                    lowopscast_publish_latency_ms=elapsed_ms,
                )
                return {
                    "ok": False,
                    "clipId": item["clipId"],
                    "network": network,
                    "error": exc.response.text,
                }
