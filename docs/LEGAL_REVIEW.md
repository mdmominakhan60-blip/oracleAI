# OracleAI — legal and trust launch gate

Публичные рабочие тексты доступны через `/privacy`, `/terms`, `/privacy/en` и `/terms/en`. Они намеренно не выдумывают юридическое лицо, адрес, контакт, юрисдикцию или сроки, которые не были предоставлены владельцем продукта. Перед коммерческим запуском эти placeholders должны быть заменены и проверены профильным юристом.

## Обязательные проверки до public launch

| Область | Что подтвердить |
|---|---|
| Оператор | Юридическое лицо/ИП, адрес, privacy contact, support contact и ответственное лицо за запросы. |
| Юрисдикция | Применимое право, порядок разрешения споров, трансграничные передачи и обязательные уведомления. |
| Возраст | Самоподтверждение 16+ удалено как продуктовая граница (GAUNTLET v2); сервис не собирает возрастное согласие. Если возрастной оверлей возвращается, 16+ следует вводить как явный самоаттестационный шаг, а не как identity/age verification. |
| Privacy | Категории данных, LLM subprocessors, retention по каждой категории, deletion/export process, backup retention и incident notification. |
| Payments | Актуальные цены, trial, renewal, cancellation, refund, tax/VAT wording и условия Paddle/другого PSP. |
| Safety | Crisis/medical/legal/financial escalation copy и локальные emergency resources для стран присутствия. |
| Marketing | Landing promises, Telegram bot description и рекламные тексты не должны обещать гарантию результата или диагностику. |

## Инженерная сверка обещаний

`memory_enabled=false` должен означать отсутствие извлечения новых фактов, передачи сохранённой памяти агенту и показа списка памяти. События analytics не должны содержать сообщения, дневник, память, birth data, payment details или ответы модели. Логи должны использовать redaction и request/release identifiers без PII. Платёжное право выдаётся только после server-side pending-order binding, подписанного webhook и idempotent processing.

Этот файл является release checklist, а не юридической консультацией. Удаление placeholders — отдельный обязательный пункт принятия v1.0.
