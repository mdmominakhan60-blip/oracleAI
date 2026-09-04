# OracleAI — incident response runbook

**Status:** prepared for staging rehearsal; **not a production approval**.  
**Last reviewed:** 25 August 2026.  
**Required before launch:** fill named owners, contact channels, SLA values and external dashboard links.

## Severity model

| Severity | Example | Immediate action | Target acknowledgement |
|---|---|---|---|
| SEV-0 | Critical safety failure, confirmed data exposure, uncontrolled payment duplication or broad outage | Disable affected feature flag, stop acquisition/traffic, preserve evidence, page primary and backup owner | 5 minutes |
| SEV-1 | Provider outage, repeated webhook/payment inconsistency, scheduler failure affecting many users or restore failure | Enable fallback/rollback, page operations and product owner, open incident channel | 15 minutes |
| SEV-2 | Degraded latency, isolated user-impacting defect, stale scheduler alert with successful recovery | Create incident ticket, assign owner, monitor until resolved | 1 hour |
| SEV-3 | Cosmetic defect or non-blocking documentation/analytics issue | Queue for normal triage | Next business day |

## Named ownership to fill before staging

| Role | Required value | Current status |
|---|---|---|
| Accountable release owner | `REQUIRED_OWNER` | OPEN |
| Primary on-call | `REQUIRED_CONTACT` | OPEN |
| Backup on-call | `REQUIRED_CONTACT` | OPEN |
| AI/safety owner | `REQUIRED_CONTACT` | OPEN |
| Billing/provider owner | `REQUIRED_CONTACT` | OPEN |
| Privacy/legal contact | `REQUIRED_CONTACT` | EXTERNAL |
| Incident channel | `REQUIRED_CHANNEL` | OPEN |

## First-response procedure

The first responder records the UTC timestamp, severity, affected surface, release ID, alert ID and the smallest safe description of impact. Do not copy chat, diary, memory, palm images, birth data, tokens or webhook payloads into the incident channel. If the incident involves safety, privacy, payment or data integrity, the responder immediately applies the relevant feature flag or rollout stop and pages the accountable owner.

The incident commander then chooses containment: disable Palm or live LLM, switch provider/fallback, stop scheduler dispatch, pause payment fulfillment, freeze writes, or roll back the release. The commander confirms whether user communication is required and uses the approved template after Product/Legal review for privacy or safety incidents.

## Scenario playbooks

### Critical safety or model-grounding failure

Disable the affected interpretation path, preserve sanitized request/response identifiers and model/config hashes, block the failing prompt or provider route, run the safety regression set, and do not re-enable until AI/Safety signs the remediation.

### Data/privacy incident

Stop the affected endpoint or feature flag, revoke exposed access, preserve audit IDs without copying private content, identify the data categories and time window, notify the privacy/legal contact and follow the approved user/regulator communication path.

### Payment/webhook inconsistency

Stop fulfillment if entitlement state is uncertain, keep the webhook idempotency record, compare provider event IDs with local orders, reconcile in sandbox/staging first, and require Billing owner approval before replay or refund action.

### Provider outage or latency breach

Confirm provider health, switch to approved fallback/offline response if safe, monitor p50/p95/p99 and error rate, display actionable status to users, and apply traffic or feature caps. Do not silently claim a live result when the provider did not return valid evidence.

### Scheduler stale/error

Use `scripts/ops_alerts.py` to confirm `scheduler_stale`, `scheduler_status_missing` or `scheduler_last_run_failed`. Verify the persistent lease owner, stop duplicate worker starts, recover the stale lease only through the scheduler lifecycle, and confirm per-delivery idempotency before re-enabling dispatch.

### Backup or restore failure

Stop destructive maintenance, preserve the last verified backup and checksum, record backup age, restore into an isolated destination, run SQLite integrity/migration/selfcheck, and do not declare recovery until the post-restore read-only smoke passes.

## Required staging tabletop

Run four synthetic scenarios: one critical safety failure, one privacy exposure, one payment/webhook inconsistency and one provider outage. For each scenario record detection source, acknowledgement time, containment action, owner, rollback/feature-flag command, communication decision and recovery time. The current local alert dry-run confirms privacy-safe detection of HTTP 5xx, webhook failure, stale backup and scheduler error signals; real alert delivery and on-call acknowledgement remain OPEN.

## Evidence checklist

A launch record must attach the severity matrix, named contact tree, tabletop minutes, alert-to-acknowledgement timeline, feature-flag or rollback output, sanitized postmortem, dashboard links, backup/restore result and the release owner’s decision. A local unit-test pass is not sufficient to close incident response.
