"""Приём funnel-событий (EXP-004): visit → signup → activation.

Публичный эндпоинт для лендинга и мини-лендинга: анонимные события с
клиентским session_id (sid) до первой идентификации. Никакой аутентификации —
доступ ограничен allowlist имён/props, лимитом запросов и лимитом батча;
валидация и дедупликация в app/repo/analytics.track_funnel.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...services import analytics
from ..contracts.funnel import FunnelEventIn
from ..deps import get_db, rate_limit

router = APIRouter(prefix="/api", tags=["funnel"])

#: Имена, разрешённые к приёму. Всё прочее отбрасывается на входе: клиент
#: не может создать произвольное событие в воронке.
_ALLOWED_FUNNEL_NAMES = {analytics.E_VISIT, analytics.E_SIGNUP,
                         analytics.E_ACTIVATION}


@router.post("/funnel/events", dependencies=[Depends(rate_limit("write"))])
async def accept_funnel_events(item: FunnelEventIn,
                               db=Depends(get_db)) -> dict:
    accepted = 0
    duplicates = 0
    rejected = 0
    for event in item.events:
        if event.name not in _ALLOWED_FUNNEL_NAMES:
            rejected += 1
            continue
        stored = await analytics.track_funnel(
            db, name=event.name, session_id=event.session_id,
            surface=event.surface, source=event.source, medium=event.medium,
            campaign=event.campaign, path=event.path,
            activation_action=event.activation_action,
            signup_method=event.signup_method)
        if stored:
            accepted += 1
        else:
            # И валидный дубль (индекс), и отбракованные props считаем
            # rejected'ом только по факту: дубли отдельно не различаем,
            # чтобы не подсказывать злоумышленнику содержимое индекса.
            duplicates += 1
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}
