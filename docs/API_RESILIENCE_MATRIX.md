# API resilience matrix

**Дата:** 26 августа 2026

Этот документ фиксирует локально исполняемый negative-path smoke matrix. Все user routes выполняются через owner-scoped dependency; production-only Telegram session, real provider timeout and deployment rollback checks are not implied by a local pass.

| Сценарий | Проверка | Ожидаемый результат | Evidence |
|---|---|---|---|
| Missing identity | `GET /api/memories` without `dev_user` or signed Telegram session | `401`, no mutation | `tests/test_api_resilience.py` |
| Invalid profile | Unsupported `lang` in `POST /api/profile` | `400`, validation message only | `tests/test_api_resilience.py` |
| Invalid payload | Too-short manual memory fact | `422` | `tests/test_api_resilience.py` |
| Privacy pause | Save/read memory after `memory_enabled=false` | `409` for write, empty AI-facing list | `tests/test_api_resilience.py`, `tests/test_memory_evaluation.py` |
| Missing owner resource | Foreign/nonexistent Tarot and diary entries | Neutral `404` | `tests/test_api_resilience.py` |
| Rate limit | Repeated profile writes | `429` without retry-loop contract | `tests/test_api_resilience.py` |
| Backend failure | Synthetic health-check exception | `500`, request ID and response time, no traceback or secret | `tests/test_api_resilience.py` |
| Account deletion | Missing confirmation, confirmed deletion, repeated deletion | `400`, then idempotent `200` | `tests/test_api.py` |

**Still required before production:** complete every route in the API inventory, inject real provider timeouts/cancellation, exercise expired Telegram sessions and signed `initData`, run multi-process contention checks, and verify frontend retry/loading/error states in deployed observability. These checks require staging credentials or a real deployment and are deliberately not marked complete by this local matrix.
