# Definition of Done (DoD) — DOPA Platform

A backlog item or task is considered **DONE** and eligible for release only when all checkable criteria below have been satisfied and verified without exception.

---

## 1. Architectural & Code Integrity
- [ ] **PEP 8 & Formatting**: Code conforms to PEP 8 standards with zero critical lint errors.
- [ ] **Modularity**: Code is partitioned strictly into its designated app domain (`accounts`, `cases`, `collaboration`, `audit`) without circular dependencies.
- [ ] **No Hardcoded Secrets**: Secret keys, database credentials, and debug flags are loaded strictly from environment variables (`.env`).
- [ ] **Typing & Clean Interfaces**: View handlers and domain services include type annotations for all public functions.

---

## 2. Security & Clinical Governance (Zero-Tolerance Gates)
- [ ] **Immutable Role Assignment**: User role (`PRIMARY_PHYSICIAN` or `SPECIALIST`) is validated upon registration and cannot be modified via profile edit or direct POST parameters.
- [ ] **Case-Scoped RBAC Enforcement**:
  - Every case endpoint verifies the authorization tuple: `(Actor Role, Case Ownership/Team Membership, Case Status)`.
  - Zero authorization checks rely solely on UI component hiding; all gates are verified server-side.
  - Unauthorized access attempts abort immediately with `HTTP 403 Forbidden`.
- [ ] **Singularity of Clinical Decision**:
  - `Decision.case_id` is guarded by a database-level `UNIQUE` constraint.
  - An attempt to post a second decision for a case returns an HTTP error and cannot alter existing records.
- [ ] **Mandatory Advisory Acknowledgement Gate**:
  - Final decision submission requires explicit boolean confirmation (`advisory_acknowledged=True`).
  - Submitting without the acknowledgement checkbox is rejected with a validation error before hitting database logic.
- [ ] **CSRF & XSS Protection**:
  - 100% of state-changing forms include Django's `{% csrf_token %}`.
  - Narrative discussion notes and clinical findings are escaped through Django's template engine; raw HTML injection is impossible.
- [ ] **Session & Transport Hardening**:
  - Cookies configured as `HttpOnly=True`, `Secure=True`, `SameSite='Lax'`.
  - Inactive sessions expire after 30 minutes of idle time.

---

## 3. Database & Data Integrity
- [ ] **3NF Compliance**: No non-key attribute depends on another non-key attribute; zero update/deletion anomalies.
- [ ] **Referential Integrity**:
  - Hypotheses and Decisions reference users with `on_delete=models.PROTECT` or clean cascade where appropriate, ensuring historical clinical audit trails are never orphaned.
  - Junction table `CaseTeam` enforces composite uniqueness `(case_id, specialist_id)`.
- [ ] **Migration Cleanliness**:
  - All migrations run cleanly forward and backward (`python manage.py migrate`).
  - No default values that corrupt existing rows or leave nullable fields unhandled.

---

## 4. Append-Only Audit Logging & Forensics
- [ ] **Comprehensive Event Coverage**: Every state change triggers an audit entry:
  - `LOGIN`, `CASE_CREATED`, `SPECIALIST_ADMITTED`, `HYPOTHESIS_SUBMITTED`, `HYPOTHESIS_WITHDRAWN`, `RANK_UPDATED`, `DECISION_RECORDED`.
- [ ] **Denial Forensics**: Every blocked authorization attempt produces an `ACCESS_DENIED` audit entry capturing the actor, target case, IP address, and server UTC timestamp.
- [ ] **Tamper Resistance**: Application user role has no SQL `UPDATE` or `DELETE` privileges on the `audit_auditlog` table.

---

## 5. Performance & LMIC (Low-Bandwidth) Optimization
- [ ] **Bounded Query Count**: Workspace page render executes **$\le 4$ SQL queries** (verified via `django.test.utils.CaptureQueriesContext`).
- [ ] **Warm Latency Target**: Workspace page loads in $< 1.0\text{ s}$ in standard broadband environment.
- [ ] **Simulated 3G Latency**: Page loads in $< 2.5\text{ s}$ on throttled 3G network simulation.
- [ ] **Mobile Responsiveness**: Clean, non-overlapping layout on viewports down to 375px width (tested on mobile browser).
- [ ] **Stateless Request/Response**: Zero persistent WebSocket or long-polling dependencies; all functionality operational over intermittent connections.

---

## 6. Automated Testing & Verification Gates
- [ ] **Functional Tests Pass**: 100% pass rate on formal test cases **FT01 through FT11** (Table 4.2).
- [ ] **Negative & Penetration Tests**: Automated tests verify:
  - Unauthenticated access redirects (FT03).
  - Specialist case creation blocked (FT05).
  - Unadmitted specialist hypothesis submission blocked (FT06b).
  - Specialist decision recording blocked (FT08).
  - Decision submission without checkbox blocked (FT09).
- [ ] **Code Coverage**: Test suite achieves $\ge 90\%$ branch/statement coverage across all domain apps.
- [ ] **Clinical Test Data**: Appendix A test fixtures (Scenarios 1, 2, and 3) load and execute to case closure without runtime errors.
