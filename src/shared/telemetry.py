"""
Bootstrap de telemetria OpenTelemetry para Azure Functions Python v2.

Centraliza logs, traces e metricas para Azure Monitor/Application Insights.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.trace import Status, StatusCode

LOGGER_NAMESPACE = "lowopscast"
SERVICE_NAME = "func-lowopscast-prod"
_BOOTSTRAPPED = False

logger = logging.getLogger(f"{LOGGER_NAMESPACE}.app")
tracer = trace.get_tracer(LOGGER_NAMESPACE, "1.0.0")
meter = metrics.get_meter(LOGGER_NAMESPACE, "1.0.0")

invocation_counter = meter.create_counter(
    name="lowopscast.function.invocations",
    unit="1",
    description="Total de invocacoes da function schedule-existing-clips",
)
clips_found_counter = meter.create_counter(
    name="lowopscast.clips.found",
    unit="1",
    description="Quantidade de clips encontrados por execucao",
)
schedules_planned_counter = meter.create_counter(
    name="lowopscast.schedules.planned",
    unit="1",
    description="Quantidade de agendamentos planejados",
)
schedules_created_counter = meter.create_counter(
    name="lowopscast.schedules.created",
    unit="1",
    description="Quantidade de agendamentos criados com sucesso",
)
schedules_failed_counter = meter.create_counter(
    name="lowopscast.schedules.failed",
    unit="1",
    description="Quantidade de falhas de agendamento",
)
judge_clips_total_counter = meter.create_counter(
    name="lowopscast.judge.clips.total",
    unit="1",
    description="Quantidade de clips avaliados pela Judge",
)
judge_clips_approved_counter = meter.create_counter(
    name="lowopscast.judge.clips.approved",
    unit="1",
    description="Quantidade de clips aprovados pela Judge",
)
judge_clips_review_counter = meter.create_counter(
    name="lowopscast.judge.clips.review",
    unit="1",
    description="Quantidade de clips em revisao pela Judge",
)
judge_clips_rejected_counter = meter.create_counter(
    name="lowopscast.judge.clips.rejected",
    unit="1",
    description="Quantidade de clips rejeitados pela Judge",
)
execution_duration_ms = meter.create_histogram(
    name="lowopscast.execution.duration",
    unit="ms",
    description="Duracao total da execucao da function",
)
judge_latency_ms = meter.create_histogram(
    name="lowopscast.judge.latency",
    unit="ms",
    description="Latencia da etapa Judge",
)
publish_latency_ms = meter.create_histogram(
    name="lowopscast.opus.publish.latency",
    unit="ms",
    description="Latencia das chamadas de publish para OpusClip",
)


def init_telemetry() -> None:
    global _BOOTSTRAPPED

    if _BOOTSTRAPPED:
        return

    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        try:
            configure_azure_monitor(logger_name=LOGGER_NAMESPACE)
            HTTPXClientInstrumentor().instrument()
            logger.info(
                "OpenTelemetry inicializado",
                extra={
                    "custom_dimensions": {
                        "service.name": os.environ.get("OTEL_SERVICE_NAME", SERVICE_NAME),
                        "service.namespace": LOGGER_NAMESPACE,
                        "deployment.environment": os.environ.get("AZURE_FUNCTIONS_ENVIRONMENT", "Development"),
                    }
                },
            )
        except Exception as exc:  # pragma: no cover - dependente do ambiente
            logging.getLogger(LOGGER_NAMESPACE).warning(
                "Falha ao inicializar exportacao OTEL; seguindo com telemetria local: %s",
                exc,
            )
    else:
        logging.getLogger(LOGGER_NAMESPACE).warning(
            "APPLICATIONINSIGHTS_CONNECTION_STRING ausente; telemetria OTEL sem exportacao remota"
        )

    _BOOTSTRAPPED = True


def attrs(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def mark_ok(span: Any, **attributes: Any) -> None:
    for key, value in attrs(**attributes).items():
        span.set_attribute(key, value)
    span.set_status(Status(StatusCode.OK))


def mark_error(span: Any, exc: Exception, **attributes: Any) -> None:
    for key, value in attrs(**attributes).items():
        span.set_attribute(key, value)
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))