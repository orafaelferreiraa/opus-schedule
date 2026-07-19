"""
Store de idempotência em Azure Table Storage.

Evita reagendar o mesmo (projectId, clipId, rede) em execuções repetidas — sem
isso, reprocessar uma coleção cria agendamentos duplicados na OpusClip.

Degrada para no-op quando o storage não está configurado (dev local sem
STORAGE_ACCOUNT_NAME/connection string): comporta-se como se nada tivesse sido
agendado antes, para nunca bloquear o fluxo por causa de telemetria de estado.
Autentica via connection string (se fornecida) ou Managed Identity
(DefaultAzureCredential) usando o endpoint de tabela do storage account.
"""

from __future__ import annotations

import os

from shared.telemetry import logger

_TABLE_NAME = os.environ.get("STATE_TABLE_NAME", "lowopscaststate")


def _sanitize_key(value: str) -> str:
    """PartitionKey/RowKey não aceitam / \\ # ? nem controle. Substitui por '_'."""
    cleaned = value or ""
    for bad in ("/", "\\", "#", "?", "\t", "\n", "\r"):
        cleaned = cleaned.replace(bad, "_")
    return cleaned or "_"


def _row_key(network: str, clip_id: str) -> str:
    return _sanitize_key(f"{network}__{clip_id}")


class ScheduleStateStore:
    """Rastreia agendamentos já criados em Table Storage (idempotência)."""

    def __init__(self) -> None:
        self._table = None
        account = os.environ.get("STORAGE_ACCOUNT_NAME", "").strip()
        conn = os.environ.get("STATE_STORAGE_CONNECTION_STRING", "").strip()

        if not account and not conn:
            logger.warning(
                "State store desabilitado (STORAGE_ACCOUNT_NAME/connection string ausentes); "
                "sem deduplicação de agendamentos."
            )
            return

        try:
            from azure.core.exceptions import ResourceExistsError
            from azure.data.tables import TableClient

            if conn:
                table = TableClient.from_connection_string(conn, table_name=_TABLE_NAME)
            else:
                from azure.identity import DefaultAzureCredential

                endpoint = f"https://{account}.table.core.windows.net"
                table = TableClient(
                    endpoint=endpoint,
                    table_name=_TABLE_NAME,
                    credential=DefaultAzureCredential(),
                )

            try:
                table.create_table()
            except ResourceExistsError:
                pass

            self._table = table
        except Exception as exc:  # noqa: BLE001 - falha de storage não deve derrubar a função
            logger.warning(
                "State store indisponível (%s); seguindo sem deduplicação.", type(exc).__name__
            )
            self._table = None

    @property
    def enabled(self) -> bool:
        return self._table is not None

    def already_scheduled(self, project_id: str, clip_id: str, network: str) -> bool:
        """True se (projectId, clipId, rede) já foi agendado. Fail-open em erro."""
        if not self._table:
            return False
        try:
            from azure.core.exceptions import ResourceNotFoundError

            try:
                self._table.get_entity(
                    partition_key=_sanitize_key(project_id or "noproject"),
                    row_key=_row_key(network, clip_id),
                )
                return True
            except ResourceNotFoundError:
                return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao consultar state store (%s); tratando como novo.", type(exc).__name__)
            return False

    def mark_scheduled(
        self,
        project_id: str,
        clip_id: str,
        network: str,
        publish_at: str = "",
        schedule_id: str = "",
    ) -> None:
        """Registra um agendamento criado. Erros são logados e ignorados."""
        if not self._table:
            return
        try:
            from azure.data.tables import UpdateMode

            entity = {
                "PartitionKey": _sanitize_key(project_id or "noproject"),
                "RowKey": _row_key(network, clip_id),
                "projectId": project_id,
                "clipId": clip_id,
                "network": network,
                "publishAt": publish_at,
                "scheduleId": schedule_id,
            }
            self._table.upsert_entity(entity, mode=UpdateMode.REPLACE)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao gravar state store (%s); dedupe futuro pode falhar.", type(exc).__name__)

    def filter_plan(self, plan: dict[str, list[dict]]) -> tuple[dict[str, list[dict]], int]:
        """Remove do plano os itens já agendados. Retorna (plano_novo, qtd_removida)."""
        if not self._table:
            return plan, 0

        new_plan: dict[str, list[dict]] = {}
        skipped = 0
        for network, items in plan.items():
            kept: list[dict] = []
            for item in items:
                project_id = str(item.get("projectId", ""))
                clip_id = str(item.get("clipId", ""))
                if clip_id and self.already_scheduled(project_id, clip_id, network):
                    skipped += 1
                    continue
                kept.append(item)
            if kept:
                new_plan[network] = kept
        return new_plan, skipped
