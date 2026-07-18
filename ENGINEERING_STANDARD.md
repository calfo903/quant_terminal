# Engineering Standard for Code Quality, Security, Reliability, and AI Integration

## Purpose

This standard defines the mandatory engineering requirements for building and
operating production systems. It is intended for engineers, reviewers, and
technical leads and serves as the practical implementation baseline for secure
and maintainable delivery.

---

## 1. Architecture Standard

### 1.1 Separation of Concerns
- Business logic must be separated from transport, presentation, and persistence layers.
- Infrastructure-specific code must be isolated from domain logic.
- Shared components must have defined ownership and stable interfaces.

### 1.2 Dependency Management
- Circular dependencies are not permitted.
- New dependencies must have a justified use case and acceptable maintenance and security profile.
- Internal interfaces must not leak infrastructure details into core logic.

### 1.3 Complexity Control
- Modules must remain understandable and bounded in scope.
- High-complexity functions must be refactored.
- Repetition should be reduced where it improves correctness and maintainability.

---

## 2. Security Standard

### 2.1 Input Validation
- All external input must be validated using explicit schemas, constraints, or equivalent mechanisms.
- Validation must occur server-side even if client-side validation exists.
- Unsafe deserialization and unbounded parsing must be avoided.

### 2.2 Authentication
- Protected resources must require verified authentication.
- Session, token, or identity controls must enforce expiration and integrity.
- Authentication logic must not be bypassable through alternate paths.

### 2.3 Authorization
- Authorization checks must be explicit for each sensitive action.
- Multi-tenant and object-level access must be enforced where relevant.
- Ownership checks must not rely solely on client-provided identifiers.

### 2.4 Secrets Management
- Secrets must be stored in approved secret management systems or controlled runtime environments.
- Secrets must not be committed to source control or written to logs.
- Secret rotation must be possible without major rework.

### 2.5 Cryptography and Data Protection
- Only approved libraries and algorithms may be used.
- Custom cryptographic implementations are not allowed.
- Sensitive data at rest and in transit must be protected according to system classification.

---

## 3. Reliability and Performance Standard

### 3.1 Error Handling
- Errors must be handled explicitly and must preserve actionable context.
- Silent failures are prohibited.
- Retries must be bounded and safe for the operation type.

### 3.2 Scalability
- Services must avoid known N+1 patterns and unbounded in-memory processing.
- Pagination, batching, and streaming must be used where appropriate.
- Long-running or high-cost operations should be moved out of synchronous request paths when possible.

### 3.3 Concurrency and State Safety
- Shared mutable state must be minimized.
- Concurrency-sensitive code must be reviewed for races, deadlocks, and resource leaks.
- Background jobs and workers must be observable and recoverable.

---

## 4. Code Quality Standard

### 4.1 Readability
- Naming must reflect intent.
- Code should be understandable without excessive commentary.
- Magic numbers and hidden assumptions must be removed or clearly defined.

### 4.2 Testing
- Unit tests must cover core logic and critical edge cases.
- Integration tests must cover external boundaries and failure behavior where applicable.
- Tests must be deterministic and suitable for CI execution.

### 4.3 Documentation
- Significant architectural or operational behavior must be documented.
- Public interfaces, service contracts, migrations, and operational runbooks must be maintained.

---

## 5. Observability Standard

### 5.1 Logging
- Production logs must be structured where supported.
- Sensitive values must be redacted or excluded.
- Log messages must support triage and incident analysis.

### 5.2 Metrics and Tracing
- Critical services must expose operational metrics.
- Latency, error rates, throughput, saturation, and dependency failures should be measurable.
- Distributed tracing should be used where system complexity warrants it.

### 5.3 Health and Alerts
- Services must expose health signals appropriate to their function.
- Alerts must map to actionable operational conditions.
- Alert noise must be minimized through sensible thresholds and ownership.

---

## 6. AI and LLM Integration Standard

### 6.1 Prompt and Context Safety
- System instructions must be isolated from user-supplied input.
- Retrieval context must be scoped to authorized data only.
- Model context must not include secrets unless explicitly required and controlled.

### 6.2 Output Validation
- AI outputs must be treated as untrusted.
- Structured outputs must be validated before use.
- Generated content must not directly trigger privileged actions without policy checks.

### 6.3 Abuse Prevention
- Rate limits, quotas, and cost controls must be in place.
- Logging and monitoring must support abuse detection and anomaly analysis.
- Human escalation paths must exist for harmful or uncertain model behavior.

---

## 7. Review and Release Standard

### 7.1 Code Review
- Every merge to a shared branch requires review by a qualified peer.
- High-risk changes require review by a senior engineer or domain owner.
- Reviewers must assess security, reliability, rollback impact, and maintainability.
- Reviewers must capture non-obvious tradeoffs for high-risk changes.

### 7.2 Deployment Readiness
- Changes must include testing evidence, rollout plan, and rollback path as appropriate to risk.
- Migrations must be backward compatible or explicitly coordinated.
- Monitoring changes must accompany high-impact feature changes.

### 7.3 Prohibited Approval Conditions
Do not approve changes that contain:
- Hardcoded credentials or secrets
- Silent exception handling
- Missing authorization for sensitive actions
- Unbounded resource consumption risks
- Production-impacting changes without rollback or observability
- AI-generated code the author cannot explain and maintain

---

## 8. Compliance Status — Quant AI Terminal

Status legend: ✅ Compliant · 🟡 Partial / minor follow-up · 🔴 Gap (recommendation)

| Clause | Status | Notes / Action taken |
|--------|--------|----------------------|
| 1.1 Separation of Concerns | ✅ | `llm.py` isolated from transport/persistence; chat service orchestrates. |
| 1.2 Dependency Management | ✅ | No circular imports; LLM plane adds no new dependency (uses `httpx`). |
| 1.3 Complexity Control | 🟡 | `chat.py` is large; acceptable, periodic refactor recommended. |
| 2.1 Input Validation | ✅ | Pydantic schemas; **added** server-side image size bound (`MAX_UPLOAD_SIZE_MB`) + `history` length/content caps. |
| 2.2 Authentication | ✅ | `app/core/auth.py` + global `require_api_key` dependency: `X-API-Key` header (or `?api_key=`) enforced on all routes except health/metrics/docs; WebSocket upgrade checked; fail-closed if enabled without a key. Disabled by default (`API_AUTH_ENABLED=false`) — enable `API_AUTH_ENABLED=true` + `API_KEY` in production. |
| 2.3 Authorization | 🟡 | No multi-tenant/object ownership in scope; N/A for current design. |
| 2.4 Secrets Management | ✅ | No hardcoded secrets found; `.env` gitignored; `.env.example` contains no secrets. |
| 2.5 Cryptography | ✅ | Only standard libraries used; no custom crypto. |
| 3.1 Error Handling | ✅ | **Fixed**: LLM backend failures now logged at WARNING (actionable), not `debug`; graceful fallback retained. |
| 3.2 Scalability | 🟡 | Redis rate limiter is shared/multi-worker; tick + candle stores are capped. Metrics endpoint still missing (see 5.2). |
| 3.3 Concurrency / State | ✅ | Async throughout; worker observable via health; mutable module state minimized. |
| 4.1 Readability | ✅ | Intent-revealing names; LLM params externalized to config. |
| 4.2 Testing | ✅ | `pytest` suite (`tests/`) covers `ratelimit`, `llm`, and `auth`/`metrics` behavioral + edge cases; runs in CI via GitHub Actions (`.github/workflows/ci.yml`) on Python 3.11/3.13. Degrades gracefully when heavy deps are absent (stubbed boundaries). |
| 4.3 Documentation | ✅ | README + this standard + deployment docs maintained. |
| 5.1 Logging | ✅ | `app/core/logging.py` enforces single-line **JSON** structured logs via `JsonFormatter`; `configure_logging()` wired into `app/main.py`; `get_logger()` adopted across `auth`/`ratelimit`/`llm`. Secrets redacted by key (`api_key`, `token`, `password`, ...) and by literal value (API key, DB DSN, Redis URL) so credentials never reach logs. |
| 5.2 Metrics & Tracing | ✅ | `GET /metrics` (Prometheus format) via `app/core/metrics.py` + middleware: request count, latency, error rate, rate-limit denials, LLM/WebSocket counters. |
| 5.3 Health & Alerts | ✅ | `/healthz`, `/readyz`, `/health` present; deploy healthchecks configured. |
| 6.1 Prompt/Context Safety | ✅ | **Enforced**: system prompt and user facts passed as **separate message roles**; user free-text never injected into the prompt; context contains only our computed market facts (no secrets). |
| 6.2 Output Validation | ✅ | **Enforced**: LLM output sanitized (control-char strip + 2000-char cap) and treated as untrusted; never triggers privileged actions. |
| 6.3 Abuse Prevention | ✅ | Redis rate limits on chat/news/predict/analyze; LLM `max_tokens` caps cost. |
| 7.1 Code Review | ✅ | Enforced as process; high-risk changes (LLM plane, rate limiter) reviewed by senior engineer. |
| 7.2 Deployment Readiness | ✅ | Healthchecks + Alembic migrations + rollback via compose/healthcheck. |
| 7.3 Prohibited Conditions | ✅ | No hardcoded secrets; no silent handling (remediated); unbounded upload eliminated. |

### Remediation completed this pass
- `app/api/v1/chat.py`: `SnapshotRequest.image` validated server-side (valid base64 + ≤ `MAX_UPLOAD_SIZE_MB`); `ChatRequest.history` bounded (≤20 messages, ≤4000 chars each).
- `app/services/ai_engine/chat.py`: `_maybe_llm` logs configured-backend failures at WARNING; added `_sanitize_llm` to treat model output as untrusted (6.2).

### Recommended follow-ups (all closed)
- ✅ **4.2 Testing** — `pytest` + GitHub Actions CI wired (`tests/`, `.github/workflows/ci.yml`).
- ✅ **5.1 Logging** — structured JSON logging enforced (`app/core/logging.py`, `JsonFormatter` + secret redaction).
