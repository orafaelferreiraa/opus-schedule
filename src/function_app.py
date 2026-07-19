"""
LowOpsCast — Automação de Cortes e Distribuição Multi-Rede
Etapa 1 MVP: agendamento de clips existentes no OpusClip.
"""

from __future__ import annotations

import json
import time
import azure.functions as func

from shared.judge import JudgeSettings, judge_clips, summarize_judge
from shared.opus_client import OpusClient
from shared.schedule_matrix import build_schedule_plan
from shared.email_notify import send_summary_email
from shared.library_report import build_library_report
from shared.state_store import ScheduleStateStore
from shared.telemetry import (
    attrs,
    clips_found_counter,
    execution_duration_ms,
    init_telemetry,
    invocation_counter,
    judge_clips_approved_counter,
    judge_clips_rejected_counter,
    judge_clips_review_counter,
    judge_clips_total_counter,
    judge_latency_ms,
    logger,
    mark_error,
    mark_ok,
    schedules_created_counter,
    schedules_failed_counter,
    schedules_planned_counter,
    schedules_skipped_counter,
    tracer,
)

init_telemetry()

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="schedule-existing-clips", methods=["POST"])
def schedule_existing_clips(req: func.HttpRequest) -> func.HttpResponse:
    """
    Etapa 1 MVP — Lê clips já processados e cria agendamentos.

    Body JSON (ao menos um dos campos é obrigatório):
    {
        "collection_id": "xmAwhhFi0IJt",      # ID da coleção "Clipes favoritos"
        "project_ids": ["P0000000xxx", ...],   # ou lista de project IDs diretos
        "full_clip_ids": ["P0000000xxx.CUexample1"], # opcional: agenda apenas clips especificos
        "clip_ids": ["CUexample1"],            # opcional: ids curtos (sem projectId)
        "dry_run": false,                       # true = só mostra o plano, sem agendar
        "target_networks": ["TIKTOK_BUSINESS"],
        "max_per_network": 1,
        "split_layout_only": true,             # opcional: agenda só clips já salvos com layout dividido
        "auto_prepare_split_layout": false,     # opcional: true força PUT em renderPref antes de agendar
        "judge_mode": "off",                  # off | rules_only | hybrid
        "judge_threshold": 70,
        "judge_include_review_in_dry_run": true
    }
    """
    started_at = time.perf_counter()

    with tracer.start_as_current_span("lowopscast.schedule_existing_clips") as span:
        base_attrs = attrs(
            faas_name="schedule-existing-clips",
            faas_trigger="http",
            http_method=req.method,
        )
        for key, value in base_attrs.items():
            span.set_attribute(key, value)

        invocation_counter.add(1, base_attrs)
        logger.info("schedule_existing_clips triggered", extra={"custom_dimensions": base_attrs})

        try:
            try:
                body = req.get_json()
            except ValueError:
                logger.warning("Body JSON invalido", extra={"custom_dimensions": base_attrs})
                mark_ok(span, http_status_code=400, error_type="invalid_json")
                return func.HttpResponse(
                    json.dumps({"error": "Body JSON inválido"}),
                    status_code=400,
                    mimetype="application/json",
                )

            collection_id: str | None = body.get("collection_id")
            project_ids: list[str] = body.get("project_ids", [])
            full_clip_ids: list[str] = [str(value) for value in body.get("full_clip_ids", []) if value]
            clip_ids: list[str] = [str(value) for value in body.get("clip_ids", []) if value]
            dry_run: bool = body.get("dry_run", False)
            target_networks: list[str] = [str(network).upper() for network in body.get("target_networks", [])]
            max_per_network = body.get("max_per_network")
            split_layout_only: bool = bool(body.get("split_layout_only", False))
            auto_prepare_split_layout: bool = bool(body.get("auto_prepare_split_layout", False))
            judge_settings = JudgeSettings.from_request(body)

            request_attrs = attrs(
                **base_attrs,
                lowopscast_collection_id=collection_id,
                lowopscast_project_ids_count=len(project_ids),
                lowopscast_full_clip_ids_count=len(full_clip_ids),
                lowopscast_clip_ids_count=len(clip_ids),
                lowopscast_dry_run=dry_run,
                lowopscast_target_networks=",".join(target_networks) if target_networks else None,
                lowopscast_max_per_network=max_per_network,
                lowopscast_split_layout_only=split_layout_only,
                lowopscast_auto_prepare_split_layout=auto_prepare_split_layout,
                lowopscast_judge_mode=judge_settings.mode,
                lowopscast_judge_threshold=judge_settings.threshold,
            )
            for key, value in request_attrs.items():
                span.set_attribute(key, value)

            if not collection_id and not project_ids:
                logger.warning("collection_id ou project_ids ausentes", extra={"custom_dimensions": request_attrs})
                mark_ok(span, http_status_code=400, error_type="missing_inputs")
                return func.HttpResponse(
                    json.dumps({"error": "Informe 'collection_id' ou 'project_ids'"}),
                    status_code=400,
                    mimetype="application/json",
                )

            client = OpusClient()

            with tracer.start_as_current_span("lowopscast.get_social_accounts") as child_span:
                accounts = client.get_social_accounts()
                mark_ok(child_span, lowopscast_accounts_count=len(accounts))

            if not accounts:
                logger.warning("Nenhuma conta social conectada no OpusClip", extra={"custom_dimensions": request_attrs})
                mark_ok(span, http_status_code=422, lowopscast_accounts_count=0)
                return func.HttpResponse(
                    json.dumps({"error": "Nenhuma conta social conectada no OpusClip"}),
                    status_code=422,
                    mimetype="application/json",
                )
            logger.info(
                "Contas sociais encontradas",
                extra={"custom_dimensions": {**request_attrs, "lowopscast_accounts_count": len(accounts)}},
            )

            clips: list[dict] = []
            if collection_id:
                with tracer.start_as_current_span("lowopscast.get_clips_by_collection") as child_span:
                    clips = client.get_clips_by_collection(collection_id)
                    mark_ok(
                        child_span,
                        lowopscast_collection_id=collection_id,
                        lowopscast_clips_count=len(clips),
                    )
            else:
                with tracer.start_as_current_span("lowopscast.get_clips_by_projects") as child_span:
                    for pid in project_ids:
                        clips.extend(client.get_clips_by_project(pid))
                    mark_ok(
                        child_span,
                        lowopscast_project_ids_count=len(project_ids),
                        lowopscast_clips_count=len(clips),
                    )

            clips_found_counter.add(len(clips), request_attrs)

            if not clips:
                logger.info("Nenhum clip encontrado", extra={"custom_dimensions": request_attrs})
                mark_ok(span, http_status_code=200, lowopscast_clips_count=0)
                return func.HttpResponse(
                    json.dumps(
                        {"message": "Nenhum clip encontrado", "collection_id": collection_id, "project_ids": project_ids}
                    ),
                    status_code=200,
                    mimetype="application/json",
                )
            logger.info(
                "Clips encontrados",
                extra={"custom_dimensions": {**request_attrs, "lowopscast_clips_count": len(clips)}},
            )

            if full_clip_ids or clip_ids:
                requested_full = {value.strip() for value in full_clip_ids if value.strip()}
                requested_short = {value.strip() for value in clip_ids if value.strip()}

                filtered: list[dict] = []
                for clip in clips:
                    full_id = str(clip.get("id", ""))
                    short_id = full_id.split(".", 1)[1] if "." in full_id else full_id
                    if full_id in requested_full or short_id in requested_short:
                        filtered.append(clip)

                clips = filtered
                logger.info(
                    "Filtro de clips aplicado",
                    extra={
                        "custom_dimensions": {
                            **request_attrs,
                            "lowopscast_requested_full_clip_ids_count": len(requested_full),
                            "lowopscast_requested_clip_ids_count": len(requested_short),
                            "lowopscast_clips_after_filter": len(clips),
                        }
                    },
                )

                if not clips:
                    mark_ok(span, http_status_code=422, error_type="clip_filter_no_match")
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Nenhum clip encontrado para os IDs informados",
                                "requested_full_clip_ids": full_clip_ids,
                                "requested_clip_ids": clip_ids,
                            }
                        ),
                        status_code=422,
                        mimetype="application/json",
                    )

            if split_layout_only:
                split_clips = [
                    clip
                    for clip in clips
                    if bool((clip.get("renderPref") or {}).get("enableSplitLayout"))
                    and not bool((clip.get("renderPref") or {}).get("enableFillLayout"))
                    and not bool((clip.get("renderPref") or {}).get("enableFitLayout"))
                ]
                clips = split_clips
                logger.info(
                    "Filtro split layout aplicado",
                    extra={
                        "custom_dimensions": {
                            **request_attrs,
                            "lowopscast_clips_after_split_filter": len(clips),
                        }
                    },
                )

                if not clips:
                    mark_ok(span, http_status_code=422, error_type="split_layout_filter_no_match")
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": "Nenhum clip com layout dividido encontrado para os filtros informados"
                            }
                        ),
                        status_code=422,
                        mimetype="application/json",
                    )

            judge_results: list[dict] = []
            judge_summary: dict = {}
            if judge_settings.mode in {"rules_only", "hybrid"}:
                judge_started = time.perf_counter()
                with tracer.start_as_current_span("lowopscast.judge_clips") as child_span:
                    judge_results = judge_clips(clips, judge_settings)
                    judge_summary = summarize_judge(judge_results)
                    judge_total = int(judge_summary.get("total", 0))
                    judge_approved = int(judge_summary.get("approved", 0))
                    judge_review = int(judge_summary.get("review", 0))
                    judge_rejected = int(judge_summary.get("rejected", 0))

                    judge_clips_total_counter.add(judge_total, request_attrs)
                    judge_clips_approved_counter.add(judge_approved, request_attrs)
                    judge_clips_review_counter.add(judge_review, request_attrs)
                    judge_clips_rejected_counter.add(judge_rejected, request_attrs)

                    judge_elapsed_ms = round((time.perf_counter() - judge_started) * 1000, 2)
                    judge_latency_ms.record(judge_elapsed_ms, request_attrs)
                    mark_ok(
                        child_span,
                        lowopscast_judge_total=judge_total,
                        lowopscast_judge_approved=judge_approved,
                        lowopscast_judge_review=judge_review,
                        lowopscast_judge_rejected=judge_rejected,
                        lowopscast_judge_latency_ms=judge_elapsed_ms,
                    )

                decision_by_id = {str(result.get("id", "")): str(result.get("decision", "REJECT")) for result in judge_results}
                if dry_run and judge_settings.include_review_in_dry_run:
                    allowed = {"APPROVE", "REVIEW"}
                else:
                    allowed = {"APPROVE"}
                clips = [clip for clip in clips if decision_by_id.get(str(clip.get("id", ""))) in allowed]

                logger.info(
                    "Judge aplicada aos clips",
                    extra={
                        "custom_dimensions": {
                            **request_attrs,
                            "lowopscast_judge_total": judge_summary.get("total", 0),
                            "lowopscast_judge_approved": judge_summary.get("approved", 0),
                            "lowopscast_judge_review": judge_summary.get("review", 0),
                            "lowopscast_judge_rejected": judge_summary.get("rejected", 0),
                            "lowopscast_clips_after_judge": len(clips),
                        }
                    },
                )

                if not clips:
                    mark_ok(span, http_status_code=200, lowopscast_clips_count=0, error_type="judge_no_approved")
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "message": "Nenhum clip aprovado pela Judge para agendamento",
                                "judge": {
                                    "mode": judge_settings.mode,
                                    "threshold": judge_settings.threshold,
                                    "summary": judge_summary,
                                    "results": judge_results,
                                },
                            },
                            default=str,
                        ),
                        status_code=200,
                        mimetype="application/json",
                    )

            with tracer.start_as_current_span("lowopscast.build_schedule_plan") as child_span:
                plan = build_schedule_plan(clips, accounts)
                if target_networks:
                    plan = {network: items for network, items in plan.items() if network in target_networks}
                if isinstance(max_per_network, int) and max_per_network > 0:
                    plan = {network: items[:max_per_network] for network, items in plan.items()}
                total_schedules = sum(len(v) for v in plan.values())
                schedules_planned_counter.add(total_schedules, request_attrs)
                mark_ok(
                    child_span,
                    lowopscast_network_count=len(plan),
                    lowopscast_schedules_planned=total_schedules,
                )

            # Idempotência: remove do plano itens já agendados em execuções anteriores.
            state_store = ScheduleStateStore()
            skipped_duplicates = 0
            if state_store.enabled:
                with tracer.start_as_current_span("lowopscast.dedupe_plan") as child_span:
                    plan, skipped_duplicates = state_store.filter_plan(plan)
                    total_schedules = sum(len(v) for v in plan.values())
                    if skipped_duplicates:
                        schedules_skipped_counter.add(skipped_duplicates, request_attrs)
                    mark_ok(
                        child_span,
                        lowopscast_skipped_duplicates=skipped_duplicates,
                        lowopscast_schedules_after_dedupe=total_schedules,
                    )

            logger.info(
                "Plano gerado",
                extra={
                    "custom_dimensions": {
                        **request_attrs,
                        "lowopscast_network_count": len(plan),
                        "lowopscast_schedules_planned": total_schedules,
                        "lowopscast_skipped_duplicates": skipped_duplicates,
                    }
                },
            )

            if not plan:
                logger.info("Nenhum agendamento restou apos filtros", extra={"custom_dimensions": request_attrs})
                mark_ok(span, http_status_code=200, lowopscast_schedules_planned=0)
                return func.HttpResponse(
                    json.dumps(
                        {
                            "message": "Nenhum agendamento disponivel para os filtros informados",
                            "total_clips": len(clips),
                            "schedule_plan": plan,
                        },
                        default=str,
                    ),
                    status_code=200,
                    mimetype="application/json",
                )

            if dry_run:
                mark_ok(
                    span,
                    http_status_code=200,
                    lowopscast_clips_count=len(clips),
                    lowopscast_schedules_planned=total_schedules,
                    lowopscast_dry_run=True,
                )
                return func.HttpResponse(
                    json.dumps(
                        {
                            "dry_run": True,
                            "total_clips": len(clips),
                            "skipped_duplicates": skipped_duplicates,
                            "schedule_plan": plan,
                            "judge": {
                                "mode": judge_settings.mode,
                                "threshold": judge_settings.threshold,
                                "summary": judge_summary,
                                "results": judge_results,
                            },
                        },
                        default=str,
                    ),
                    status_code=200,
                    mimetype="application/json",
                )

            split_layout_updates: list[dict] = []
            if auto_prepare_split_layout:
                with tracer.start_as_current_span("lowopscast.prepare_split_layout") as child_span:
                    planned_keys = {
                        (str(item.get("projectId", "")), str(item.get("clipId", "")))
                        for items in plan.values()
                        for item in items
                        if item.get("projectId") and item.get("clipId")
                    }

                    clips_to_prepare: list[dict] = []
                    for clip in clips:
                        full_id = str(clip.get("id", ""))
                        clip_project_id = str(clip.get("projectId", ""))
                        clip_short_id = ""
                        if "." in full_id:
                            possible_project, possible_short = full_id.split(".", 1)
                            clip_project_id = clip_project_id or possible_project
                            clip_short_id = possible_short

                        if (clip_project_id, clip_short_id) in planned_keys:
                            clips_to_prepare.append(clip)

                    prepare_results = client.prepare_clips_for_split_layout(clips_to_prepare)
                    split_layout_updates = [r for r in prepare_results if r.get("ok")]
                    mark_ok(
                        child_span,
                        lowopscast_clips_in_plan=len(planned_keys),
                        lowopscast_clips_updated=len(split_layout_updates),
                    )
                logger.info(
                    "Clips preparados para split layout",
                    extra={
                        "custom_dimensions": {
                            **request_attrs,
                            "lowopscast_clips_in_plan": len(planned_keys),
                            "lowopscast_clips_updated": len(split_layout_updates),
                        }
                    },
                )

                if split_layout_updates:
                    # Evita condicao de corrida: o publish pode acontecer antes da atualizacao refletir no backend.
                    time.sleep(2.0)

            with tracer.start_as_current_span("lowopscast.create_schedules") as child_span:
                results = client.create_schedules(plan)
                scheduled = [r for r in results if r.get("ok")]
                failed = [r for r in results if not r.get("ok")]
                schedules_created_counter.add(len(scheduled), request_attrs)
                schedules_failed_counter.add(len(failed), request_attrs)
                mark_ok(
                    child_span,
                    lowopscast_scheduled_count=len(scheduled),
                    lowopscast_failed_count=len(failed),
                )

            # Persiste os agendamentos criados para deduplicar execuções futuras.
            if state_store.enabled and scheduled:
                for result in scheduled:
                    state_store.mark_scheduled(
                        project_id=str(result.get("projectId", "")),
                        clip_id=str(result.get("clipId", "")),
                        network=str(result.get("network", "")),
                        publish_at=str(result.get("publishAt", "")),
                        schedule_id=str(result.get("scheduleId", "")),
                    )

            logger.info(
                "Agendamentos processados",
                extra={
                    "custom_dimensions": {
                        **request_attrs,
                        "lowopscast_scheduled_count": len(scheduled),
                        "lowopscast_failed_count": len(failed),
                    }
                },
            )

            with tracer.start_as_current_span("lowopscast.send_summary_email") as child_span:
                send_summary_email(
                    total_clips=len(clips),
                    scheduled=len(scheduled),
                    failed=len(failed),
                    plan_summary=plan,
                )
                mark_ok(
                    child_span,
                    lowopscast_total_clips=len(clips),
                    lowopscast_scheduled_count=len(scheduled),
                    lowopscast_failed_count=len(failed),
                )

            mark_ok(
                span,
                http_status_code=200,
                lowopscast_total_clips=len(clips),
                lowopscast_scheduled_count=len(scheduled),
                lowopscast_failed_count=len(failed),
            )
            return func.HttpResponse(
                json.dumps(
                    {
                        "total_clips": len(clips),
                        "skipped_duplicates": skipped_duplicates,
                        "clips_updated_for_split_layout": len(split_layout_updates),
                        "updated_clip_ids": [item.get("id") for item in split_layout_updates],
                        "scheduled": len(scheduled),
                        "failed": len(failed),
                        "failures": failed,
                        "judge": {
                            "mode": judge_settings.mode,
                            "threshold": judge_settings.threshold,
                            "summary": judge_summary,
                        },
                    },
                    default=str,
                ),
                status_code=200,
                mimetype="application/json",
            )
        except Exception as exc:
            logger.exception("Falha nao tratada na execucao", extra={"custom_dimensions": base_attrs})
            mark_error(span, exc, http_status_code=500)
            return func.HttpResponse(
                json.dumps({"error": "Falha interna ao processar agendamento"}),
                status_code=500,
                mimetype="application/json",
            )
        finally:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            execution_duration_ms.record(elapsed_ms, base_attrs)
            span.set_attribute("lowopscast_execution_duration_ms", elapsed_ms)


@app.route(route="analyze-library", methods=["POST"])
def analyze_library(req: func.HttpRequest) -> func.HttpResponse:
    """Relatório de qualidade dos cortes da biblioteca (quais valem postar).

    Usa os sinais nativos da OpusClip (score + judgeResult.hookScore/hookComment)
    e regras de duração — sem LLM, independente do layout. Body JSON (opcional):
    {
        "project_ids": ["P..."],        # default: todos (menos os vídeos pessoais)
        "exclude_project_ids": ["P..."],
        "min_score": 85, "min_hook": 6,
        "min_duration_s": 15, "max_duration_s": 100,
        "top_n_per_project": 5           # limita cortes retornados por projeto
    }
    """
    started_at = time.perf_counter()

    with tracer.start_as_current_span("lowopscast.analyze_library") as span:
        base_attrs = attrs(faas_name="analyze-library", faas_trigger="http", http_method=req.method)
        for key, value in base_attrs.items():
            span.set_attribute(key, value)
        invocation_counter.add(1, base_attrs)

        try:
            try:
                body = req.get_json()
            except ValueError:
                body = {}

            report = build_library_report(
                OpusClient(),
                project_ids=body.get("project_ids") or None,
                exclude_project_ids=body.get("exclude_project_ids"),
                min_score=float(body.get("min_score", 85)),
                min_hook=float(body.get("min_hook", 6)),
                min_dur_s=int(body.get("min_duration_s", 15)),
                max_dur_s=int(body.get("max_duration_s", 100)),
                top_n_per_project=body.get("top_n_per_project"),
            )
            mark_ok(
                span,
                http_status_code=200,
                lowopscast_projects_analyzed=report["projects_analyzed"],
                lowopscast_total_clips=report["total_clips"],
                lowopscast_recommended_total=report["recommended_total"],
            )
            return func.HttpResponse(json.dumps(report, default=str), status_code=200, mimetype="application/json")
        except Exception as exc:
            logger.exception("Falha nao tratada em analyze_library", extra={"custom_dimensions": base_attrs})
            mark_error(span, exc, http_status_code=500)
            return func.HttpResponse(
                json.dumps({"error": "Falha interna ao gerar relatorio da biblioteca"}),
                status_code=500,
                mimetype="application/json",
            )
        finally:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            execution_duration_ms.record(elapsed_ms, base_attrs)
            span.set_attribute("lowopscast_execution_duration_ms", elapsed_ms)
