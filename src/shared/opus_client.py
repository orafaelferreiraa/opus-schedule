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


def _extract_list(data: dict | list) -> list[dict]:
    """Desembrulha a lista de itens das respostas de listagem da OpusClip.

    A API envelopa listas como ``{"data": {"list": [...], "total", "limit"}}``.
    Também aceita ``{"data": [...]}`` e arrays crus, por robustez.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    inner = data.get("data", data)
    if isinstance(inner, list):
        return inner
    if isinstance(inner, dict):
        for key in ("list", "items", "results"):
            value = inner.get(key)
            if isinstance(value, list):
                return value
    return []


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
        return _extract_list(self._get("/social-accounts", params={"q": "mine"}))

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def list_collections(self) -> list[dict]:
        """Lista as coleções da conta (GET /api/collections?q=mine)."""
        return _extract_list(self._get("/collections", params={"q": "mine"}))

    def list_projects(self) -> list[dict]:
        """Lista todos os projetos da conta (GET /api/clip-projects?q=mine).

        Endpoint não-documentado no OpenAPI (que só lista POST e GET-by-id), mas
        funciona e devolve o envelope {data:{list:[...]}}. Cada item traz
        `projectId`, `createdAt`, `updatedAt` e `sourceInfo.title`.
        """
        return _extract_list(self._get("/clip-projects", params={"q": "mine"}))

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
                page_clips = _extract_list(data)
                if not page_clips:
                    break
                clips.extend(page_clips)
                if len(page_clips) < page_size:
                    break
                page += 1
            mark_ok(span, lowopscast_pages=page, lowopscast_clips_count=len(clips))
        return clips

    # renderPref para forçar o layout "dividir" (split). Só campos do
    # RenderPreferenceDto documentado — sem removeFillerWord/removePause (que não
    # existem no DTO e podem fazer o PUT falhar).
    _SPLIT_RENDER_PREF = {
        "enableSplitLayout": True,
        "enableFillLayout": False,
        "enableFitLayout": False,
        "disableFillLayout": True,
        "disableFitLayout": True,
        "layoutAspectRatio": "portrait",
    }

    def prepare_clips_for_split_layout(self, clips: list[dict]) -> list[dict]:
        """Força o layout split em cada corte via PUT /exportable-clips/{id}.

        Retorna um resultado por corte: ``{id, projectId, ok, error?}``. Uma
        falha individual não aborta o lote (registra ``ok=False`` e segue).
        """
        results: list[dict] = []

        with tracer.start_as_current_span("opus.prepare_clips_for_split_layout") as span:
            span.set_attribute("lowopscast_clips_count", len(clips))
            for clip in clips:
                full_id = clip.get("id", "")
                if not full_id:
                    continue

                entry = {"id": full_id, "projectId": clip.get("projectId", "")}
                try:
                    self._put(f"/exportable-clips/{full_id}", json={"renderPref": self._SPLIT_RENDER_PREF})
                    entry["ok"] = True
                except Exception as exc:  # noqa: BLE001 - registrar falha e seguir o lote
                    entry["ok"] = False
                    entry["error"] = str(exc)[:2048]
                    logger.error(
                        "Falha ao converter clip para split layout",
                        extra={"custom_dimensions": {"lowopscast_clip_id": full_id, "lowopscast_error": entry["error"]}},
                    )
                results.append(entry)

            ok_count = len([r for r in results if r.get("ok")])
            mark_ok(span, lowopscast_clips_updated=ok_count, lowopscast_clips_failed=len(results) - ok_count)

        return results

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def create_schedules(self, plan: dict) -> list[dict]:
        """Cria os agendamentos para cada (clip, rede, horario) no plano.

        Retorna uma lista de resultados por item, cada um no formato
        ``{"ok": bool, "clipId": str, "network": str, ...}``. Falhas individuais
        não interrompem o lote — cada erro vira um resultado com ``ok=False``.
        """
        results: list[dict] = []
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
        return results

    def _schedule_one(self, network: str, item: dict) -> dict:
        started_at = perf_counter()

        with tracer.start_as_current_span("opus.publish_schedule") as span:
            op_attrs = attrs(
                lowopscast_network=network,
                lowopscast_clip_id=item.get("clipId", ""),
                lowopscast_project_id=item.get("projectId", ""),
                lowopscast_publish_at=item.get("publishAt", ""),
            )
            for key, value in op_attrs.items():
                span.set_attribute(key, value)

            try:
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
                    "projectId": item.get("projectId", ""),
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
                    "clipId": item.get("clipId", ""),
                    "projectId": item.get("projectId", ""),
                    "network": network,
                    "error": exc.response.text,
                }
            except Exception as exc:  # noqa: BLE001 - registrar falha e seguir o lote
                elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
                publish_latency_ms.record(elapsed_ms, op_attrs)
                logger.error(
                    "Falha ao agendar clip (erro nao-HTTP)",
                    extra={
                        "custom_dimensions": {
                            **op_attrs,
                            "lowopscast_publish_latency_ms": elapsed_ms,
                            "lowopscast_error": str(exc)[:2048],
                        }
                    },
                )
                mark_error(span, exc, lowopscast_publish_latency_ms=elapsed_ms)
                return {
                    "ok": False,
                    "clipId": item.get("clipId", ""),
                    "projectId": item.get("projectId", ""),
                    "network": network,
                    "error": str(exc),
                }
