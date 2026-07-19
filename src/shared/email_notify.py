"""
Notificação por e-mail via Azure Communication Services (ACS).
Usa o domínio orafaelferreira.com já configurado em acsemail-jobfinder-prod.
"""

import os
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_summary_email(
    total_clips: int,
    scheduled: int,
    failed: int,
    plan_summary: dict,
) -> None:
    """Envia e-mail de resumo após execução do pipeline."""
    connection_string = os.environ.get("ACS_CONNECTION_STRING", "")
    if not connection_string:
        logger.warning("ACS_CONNECTION_STRING não configurado — e-mail não enviado")
        return

    from_addr = os.environ.get("NOTIFICATION_EMAIL_FROM", "noreply@orafaelferreira.com")
    to_addr = os.environ.get("NOTIFICATION_EMAIL_TO", "")
    if not to_addr:
        logger.warning("NOTIFICATION_EMAIL_TO não configurado — e-mail não enviado")
        return

    try:
        from azure.communication.email import EmailClient

        client = EmailClient.from_connection_string(connection_string)

        # Montar resumo por rede
        lines = []
        for network, items in plan_summary.items():
            lines.append(f"  • {network}: {len(items)} clip(s)")
        network_summary = "\n".join(lines) if lines else "  (sem agendamentos)"

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        subject = f"[LowOpsCast] Pipeline executado — {scheduled}/{total_clips} agendados"
        body_html = f"""
<h2>LowOpsCast — Pipeline de Agendamento</h2>
<p><strong>Execução:</strong> {timestamp}</p>
<table>
  <tr><td>Clips encontrados</td><td><strong>{total_clips}</strong></td></tr>
  <tr><td>Agendados com sucesso</td><td><strong style="color:green">{scheduled}</strong></td></tr>
  <tr><td>Falhas</td><td><strong style="color:{'red' if failed else 'green'}">{failed}</strong></td></tr>
</table>
<h3>Por rede:</h3>
<pre>{network_summary}</pre>
<hr/>
<p style="color:gray;font-size:12px">LowOpsCast automation · func-lowopscast-prod</p>
"""
        message = {
            "senderAddress": from_addr,
            "recipients": {"to": [{"address": to_addr}]},
            "content": {"subject": subject, "html": body_html},
        }

        poller = client.begin_send(message)
        poller.result()  # aguarda confirmação
        logger.info("E-mail de resumo enviado para %s", to_addr)

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Falha ao enviar e-mail de resumo: %s", exc)
