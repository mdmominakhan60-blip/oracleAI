"""Справочники операторской очереди: тиры, правила Q1..Q7, плейбуки PB-1..PB-7.

Нет внешних зависимостей — импортируем из constants везде.
"""
from __future__ import annotations

# ─────────────────────────────── LTV-тиры ──────────────────────────────────────

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
TIER_D = "D"
TIER_NONE = None  # «вне тира»

TIERS_ORDER = [TIER_A, TIER_B, TIER_C, TIER_D]

# ──────────────────────────── приоритеты ──────────────────────────────────────

P1 = "p1"
P2 = "p2"
P3 = "p3"

PRIORITY_ORDER = [P1, P2, P3]

# SLA в часах/днях для overdue
P1_SLA_HOURS = 48
P2_SLA_DAYS = 7
P3_SLA_DAYS = 7

# ──────────────────────────── правила Q1..Q7 ──────────────────────────────────

RULE_Q1 = "q1"
RULE_Q2 = "q2"
RULE_Q3 = "q3"
RULE_Q4 = "q4"
RULE_Q5 = "q5"
RULE_Q6 = "q6"
RULE_Q7 = "q7"

RULES = [RULE_Q1, RULE_Q2, RULE_Q3, RULE_Q4, RULE_Q5, RULE_Q6, RULE_Q7]

# ──────────────────────────── плейбуки PB-1..PB-7 ─────────────────────────────

PB1 = "pb-1"   # VIP уснула (Q2)
PB2 = "pb-2"   # Вернулась после долгой паузы (Q7)
PB3 = "pb-3"   # Оффер не сработал (Q3)
PB4 = "pb-4"   # Тариф болит (Q4)
PB5 = "pb-5"   # Доставка сломалась (Q5)
PB6 = "pb-6"   # Не завершила онбординг (Q6)
PB7 = "pb-7"   # Возврат средств (Q1)

PLAYBOOKS = [PB1, PB2, PB3, PB4, PB5, PB6, PB7]

# Маппинг правило → плейбук (BUS-284 §2.2)
RULE_TO_PLAYBOOK = {
    RULE_Q1: PB7,
    RULE_Q2: PB1,
    RULE_Q3: PB3,
    RULE_Q4: PB4,
    RULE_Q5: PB5,
    RULE_Q6: PB6,
    RULE_Q7: PB2,
}

# ──────────────────────────── forbidden-исключение ────────────────────────────

# Правила, в которые клиентка с закрытым каналом НЕ попадает
# (Q1 не исключается — разбирательство по деньгам видно независимо от канала).
FORBIDDEN_EXCLUDE_RULES = {RULE_Q2, RULE_Q3, RULE_Q4, RULE_Q6, RULE_Q7}

# Q5 — обслуживание канала (тег no-channel), не исключается
FORBIDDEN_SERVICE_RULES = {RULE_Q5}

# ──────────────────────────── ключи reason_data по правилам ──────────────────

# Фактические имена полей, которые сервер кладёт в reason_data.
# FE использует их для подстановки в шаблоны pb_*.

REASON_Q1_KEYS = ["order_ref"]  # номер заказа (для шаблона {order})

REASON_Q2_KEYS = ["sleeping_days", "sub_expired_days"]  # что сработало

REASON_Q3_KEYS = ["offer_sent_at", "offer_expires_at", "wb2_kind"]  # WB2

REASON_Q4_KEYS = ["limit_hits_count", "plan", "next_plan", "deep_link"]

REASON_Q5_KEYS = ["delivery_status", "error_class", "delivery_kind", "delivery_created_at"]

REASON_Q6_KEYS = ["days_since_created", "o1_sent"]

REASON_Q7_KEYS = ["gap_days"]

# ──────────────────────────── risk-флаги user_card.ltv ────────────────────────

RISK_SLEEPING = "sleeping"
RISK_EXPIRING = "expiring"
RISK_LIMIT_HITS = "limit_hits"
RISK_RECENT_REFUND = "recent_refund"

RISK_FLAGS_ORDER = [RISK_SLEEPING, RISK_EXPIRING, RISK_LIMIT_HITS, RISK_RECENT_REFUND]

# ──────────────────────────── синтетика (BUS-183, BUS-387) ─────────────────────

SYNTHETIC_TG_IDS = {10001, 10002}

# Диапазон smoke/tg_id-синтетики (BUS-315): scripts/* используют 999000xxx,
# чтобы ни одна воронка/сегмент не считала их продуктовым трафиком.
# Это ЕДИНСТВЕННЫЙ допустимый диапазон для QA-проб против прода, включая
# palm-чтения и /start бота: «лёгкие» короткие tg_id вне диапазона (77777
# и т.п.) фильтр синтетики не отсекает и попадают в сегменты (BUS-1012).
SYNTHETIC_TG_ID_RANGE_LOW = 999_000_000
SYNTHETIC_TG_ID_RANGE_HIGH = 999_999_999


def not_synthetic_tg_sql(alias: str = "e") -> str:
    """SQL-фрагмент для WHERE: синтетика 999xxx и legacy 10001/10002 отсечена.

    tg_id IS NULL оставляем — web-события анонимны и легитимны.
    """
    legacy = ", ".join(str(i) for i in sorted(SYNTHETIC_TG_IDS))
    return (
        f"({alias}.tg_id IS NULL OR {alias}.tg_id < {SYNTHETIC_TG_ID_RANGE_LOW} "
        f"OR {alias}.tg_id > {SYNTHETIC_TG_ID_RANGE_HIGH}) "
        f"AND {alias}.tg_id NOT IN ({legacy})"
    )
