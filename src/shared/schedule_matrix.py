"""
Matriz de cadência por rede social.
Define: quantos clips por episódio (top-N), horários e dias preferidos.

Horários baseados em dados reais (Instagram analytics jul/2026) e
benchmark Hootsuite/Buffer 2025-2026. Todos em BRT (UTC-3).

Valores são ponto de partida — o script pode auto-ajustar em versões futuras.
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")  # UTC-3

# ---------------------------------------------------------------------------
# Configuração declarativa por plataforma OpusClip
# ---------------------------------------------------------------------------
# top_n      : máximo de clips a agendar por episódio nesta rede
# hours_brt  : horários preferidos para postagem (BRT, escolhe em round-robin)
# gap_hours  : intervalo mínimo (horas) entre posts na mesma rede
# days_only  : se não-vazio, só posta nesses dias da semana (0=seg, 6=dom)
# ---------------------------------------------------------------------------
NETWORK_CONFIG: dict[str, dict] = {
    "YOUTUBE": {
        "top_n": 99,          # todos os clips
        "hours_brt": [12, 19],
        "gap_hours": 12,
        "days_only": [],       # qualquer dia
    },
    "TIKTOK_BUSINESS": {
        "top_n": 99,
        "hours_brt": [12, 19],
        "gap_hours": 12,
        "days_only": [],
    },
    "INSTAGRAM_BUSINESS": {
        "top_n": 6,            # top 4-6 clips (dado real: Reels rendem pouco, curar)
        "hours_brt": [12, 15],
        "gap_hours": 24,
        "days_only": [],
    },
    "LINKEDIN": {
        "top_n": 3,            # curado: 2-3 clips/episódio
        "hours_brt": [8, 15],
        "gap_hours": 48,
        "days_only": [1, 2, 3],  # ter, qua, qui
    },
    "FACEBOOK_PAGE": {
        "top_n": 4,
        "hours_brt": [9, 12],
        "gap_hours": 24,
        "days_only": [0, 1, 2, 3, 4],  # seg-sex
    },
}

# Plataformas prioritárias primeiro (garante que todos os clips sejam agendados nelas)
PLATFORM_PRIORITY = ["YOUTUBE", "TIKTOK_BUSINESS", "INSTAGRAM_BUSINESS", "LINKEDIN", "FACEBOOK_PAGE"]


def build_schedule_plan(clips: list[dict], accounts: list[dict]) -> dict[str, list[dict]]:
    """
    Constrói o plano de agendamento para cada rede.

    Retorna dict: { "YOUTUBE": [{clipId, projectId, publishAt, postAccountId, ...}, ...], ... }
    """
    # Indexar contas por plataforma
    accounts_by_platform: dict[str, list[dict]] = {}
    for acc in accounts:
        platform = acc.get("platform", "").upper()
        accounts_by_platform.setdefault(platform, []).append(acc)

    plan: dict[str, list[dict]] = {}
    now_brt = datetime.now(BRT)

    for platform in PLATFORM_PRIORITY:
        platform_accounts = accounts_by_platform.get(platform, [])
        if not platform_accounts:
            continue  # rede não conectada, pular

        cfg = NETWORK_CONFIG.get(platform, {})
        top_n = cfg.get("top_n", 5)
        hours = cfg.get("hours_brt", [12])
        gap = cfg.get("gap_hours", 24)
        days_only = cfg.get("days_only", [])

        # Selecionar top-N clips por score de viralidade (proxy: durationMs)
        selected = sorted(clips, key=_clip_score, reverse=True)[:top_n]

        items: list[dict] = []
        publish_dt = _next_slot(now_brt, hours, days_only)

        for clip in selected:
            full_id: str = clip.get("id", "")
            # id formato: {projectId}.{clipId} — extrair clipId bare
            if "." in full_id:
                project_id, clip_id = full_id.split(".", 1)
            else:
                project_id = clip.get("projectId", "")
                clip_id = full_id

            account = platform_accounts[0]  # usa a primeira conta conectada
            item = {
                "clipId": clip_id,
                "projectId": project_id,
                "publishAt": publish_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "postAccountId": account.get("postAccountId") or account.get("id", ""),
                "subAccountId": account.get("subAccountId"),
                "title": _build_title(clip),
                "description": _build_description(clip),
            }
            items.append(item)
            publish_dt = _next_slot(publish_dt + timedelta(hours=gap), hours, days_only)

        plan[platform] = items

    return plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Campos de score de viralidade que a OpusClip pode retornar. O schema público
# do endpoint /exportable-clips não documenta um score, mas o dashboard o expõe
# e a resposta pode trazê-lo sob um destes nomes — sondamos todos e caímos para
# durationMs (proxy de qualidade) quando nenhum estiver presente.
_VIRALITY_FIELDS = ("viralityScore", "virality_score", "viralScore", "score")


def _clip_score(clip: dict) -> tuple[int, float]:
    """Chave de ordenação: (tem_score, valor).

    Clips com score de viralidade numérico vêm primeiro (ordenados pelo score);
    os demais caem para durationMs como proxy. Usado com ``sorted(reverse=True)``.
    """
    for field in _VIRALITY_FIELDS:
        val = clip.get(field)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return (1, float(val))
    return (0, float(clip.get("durationMs", 0) or 0))


def _next_slot(from_dt: datetime, hours_brt: list[int], days_only: list[int]) -> datetime:
    """Encontra o próximo slot de horário válido a partir de from_dt (em BRT)."""
    dt = from_dt.replace(second=0, microsecond=0)
    for _ in range(14 * 24):  # máximo 14 dias à frente
        if days_only and dt.weekday() not in days_only:
            dt += timedelta(hours=1)
            continue
        for h in sorted(hours_brt):
            candidate = dt.replace(hour=h, minute=0)
            if candidate > from_dt:
                return candidate
        dt = (dt + timedelta(days=1)).replace(hour=0)
    return from_dt + timedelta(hours=24)  # fallback


def _build_title(clip: dict) -> str:
    title = clip.get("title", "").strip()
    if not title:
        title = "LowOpsCast"
    return title[:100]


def _build_description(clip: dict) -> str:
    desc = clip.get("description", "").strip()
    hashtags = clip.get("hashtags", "").strip()
    cta = "\n\n🎙️ Episódio completo no YouTube @LowOps"
    parts = [p for p in [desc, hashtags] if p]
    return ("\n\n".join(parts) + cta)[:2000]
