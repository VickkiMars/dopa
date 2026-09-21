# API & Data Contracts Specification — DOPA Platform

This document defines the interface boundaries, URL routing tables, view contracts, form schemas, validation constraints, and audit event definitions for the DOPA platform.

---

## 1. URL Routing Table

All URLs use standard Django namespaced routing.

| URL Pattern | Route Name | HTTP Method | View Handler | Auth / RBAC Decorators |
|---|---|---|---|---|
| `/accounts/register/` | `accounts:register` | `GET`, `POST` | `RegisterView` | `@anonymous_required` |
| `/accounts/login/` | `accounts:login` | `GET`, `POST` | `LoginView` | `@rate_limited(5/15m)` |
| `/accounts/logout/` | `accounts:logout` | `POST` | `LogoutView` | `@login_required` |
| `/accounts/password-reset/` | `accounts:password_reset` | `GET`, `POST` | `PasswordResetView` | Public |
| `/dashboard/` | `cases:dashboard` | `GET` | `DashboardView` | `@login_required` |
| `/cases/create/` | `cases:create` | `GET`, `POST` | `CaseCreateView` | `@login_required`, `@role_required('PRIMARY_PHYSICIAN')` |
| `/cases/<uuid:case_id>/team/admit/` | `cases:team_admit` | `POST` | `TeamAdmitView` | `@login_required`, `@case_owner_required` |
| `/cases/<uuid:case_id>/workspace/` | `cases:workspace` | `GET` | `WorkspaceView` | `@login_required`, `@case_access_required` |
| `/cases/<uuid:case_id>/notes/create/` | `collaboration:note_create`| `POST` | `DiscussionNoteCreateView`| `@login_required`, `@case_access_required` |
| `/cases/<uuid:case_id>/hypotheses/create/` | `collaboration:hypothesis_create` | `POST` | `HypothesisCreateView` | `@login_required`, `@specialist_team_required` |
| `/cases/<uuid:case_id>/hypotheses/<uuid:hypo_id>/withdraw/` | `collaboration:hypothesis_withdraw` | `POST` | `HypothesisWithdrawView` | `@login_required`, `@hypothesis_author_required` |
| `/cases/<uuid:case_id>/ranking/reorder/` | `cases:ranking_reorder` | `POST` | `RankingReorderView` | `@login_required`, `@case_owner_required` |
| `/cases/<uuid:case_id>/decision/record/` | `cases:decision_record` | `POST` | `DecisionRecordView` | `@login_required`, `@case_owner_required` |
| `/cases/<uuid:case_id>/audit/` | `audit:trail_view` | `GET` | `AuditTrailView` | `@login_required`, `@case_access_required` |

---

## 2. Form Contracts & Validation Rules

### 2.1 User Registration Form (`accounts:register`)
```json
{
  "full_name": { "type": "string", "required": true, "max_length": 150, "strip": true },
  "email": { "type": "email", "required": true, "max_length": 254, "unique": true },
  "role": { "type": "choice", "choices": ["PRIMARY_PHYSICIAN", "SPECIALIST"], "required": true },
  "password": { "type": "string", "required": true, "min_length": 8 },
  "password_confirm": { "type": "string", "required": true, "matches": "password" }
}
```
- **Validation Rules**:
  - `email` must be a valid email format and case-insensitively unique in `accounts_user`.
  - `role` must be strictly one of `PRIMARY_PHYSICIAN` or `SPECIALIST`. Bound immutably on creation.

### 2.2 Case Creation Form (`cases:create`)
```json
{
  "title": { "type": "string", "required": true, "max_length": 200, "strip": true },
  "clinical_summary": { "type": "string", "required": true, "min_length": 30, "max_length": 5000 },
  "history": { "type": "string", "required": true, "min_length": 30, "max_length": 5000 },
  "findings": { "type": "string", "required": true, "min_length": 20, "max_length": 5000 }
}
```
- **Validation Rules**:
  - All four fields are mandatory (resolving FAULT-01).
  - Submitting user must have role `PRIMARY_PHYSICIAN`. If a specialist attempts POST, intercept with `HTTP 403` and dispatch `ACCESS_DENIED` audit log.

### 2.3 Specialist Team Admission Form (`cases:team_admit`)
```json
{
  "specialist_email": { "type": "email", "required": true }
}
```
- **Validation Rules**:
  - Target account must exist in `accounts_user`.
  - Target account role must be `SPECIALIST`. If target user is a `PRIMARY_PHYSICIAN`, reject with validation error: *"Only accounts with the Specialist role can be admitted to a case team."*
  - Cannot admit the same specialist twice (`CaseTeam` composite unique key).

### 2.4 Structured Hypothesis Form (`collaboration:hypothesis_create`)
```json
{
  "proposed_diagnosis": { "type": "string", "required": true, "max_length": 250, "strip": true },
  "rationale": { "type": "string", "required": true, "min_length": 20, "max_length": 3000 },
  "supporting_evidence": { "type": "string", "required": true, "min_length": 20, "max_length": 3000 },
  "idempotency_token": { "type": "uuid", "required": true }
}
```
- **Validation Rules**:
  - All three clinical fields are mandatory (FR3). Missing fields return `HTTP 400` with form field errors.
  - Submitting user must be in `cases_caseteam` for this `case_id`. Non-team members receive `HTTP 403` + `ACCESS_DENIED` audit log.
  - Case status must be `OPEN` or `UNDER_REVIEW`. If `CLOSED` or `DECIDED`, return `HTTP 403`.
  - On first successful hypothesis, case transitions from `OPEN` to `UNDER_REVIEW`.

### 2.5 Differential Diagnosis Reorder Contract (`cases:ranking_reorder`)
```json
{
  "hypothesis_id": { "type": "uuid", "required": true },
  "direction": { "type": "choice", "choices": ["UP", "DOWN"], "required": true }
}
```
- **Validation Rules**:
  - Only the case owner (`PRIMARY_PHYSICIAN`) can reorder. Specialists receive `HTTP 403` + `ACCESS_DENIED` log.
  - Swaps `rank_position` with the adjacent active hypothesis atomically inside a database transaction.
  - Dispatches `RANK_UPDATED` audit log.

### 2.6 Final Clinical Decision Form (`cases:decision_record`)
```json
{
  "final_diagnosis": { "type": "string", "required": true, "max_length": 250, "strip": true },
  "advisory_acknowledged": { "type": "boolean", "required": true, "must_be": true },
  "governance_statement": { "type": "string", "required": true },
  "idempotency_token": { "type": "uuid", "required": true }
}
```
- **Validation Rules**:
  - Only the case owner can submit. Specialists receive `HTTP 403` + `ACCESS_DENIED` log.
  - If `advisory_acknowledged` is not checked (`False`), submission fails validation with: *"You must acknowledge that specialist advice is advisory and you retain sole clinical responsibility before recording the decision."*
  - Enforces database singularity: if `cases_decision` already exists for this `case_id`, rejects with error.
  - Upon save:
    1. Writes to `cases_decision`.
    2. Updates `cases_case.status` to `CLOSED`.
    3. Dispatches `DECISION_RECORDED` audit log.

---

## 3. Audit Action Taxonomy

Every event logged to `audit_auditlog` adheres to the following strict taxonomy:

| Action Code | Trigger Event | Primary Actor | Target Entity | Context Payload (`details`) |
|---|---|---|---|---|
| `LOGIN_SUCCESS` | Successful user authentication | User | `accounts_user` | `{ "ip": "...", "role": "..." }` |
| `LOGIN_FAILED` | Failed password check / rate limited | Null / User | `accounts_user` | `{ "ip": "...", "attempted_email": "..." }` |
| `CASE_CREATED` | New case created | Primary Phys | `cases_case` | `{ "case_title": "..." }` |
| `SPECIALIST_ADMITTED` | Specialist added to case team | Primary Phys | `cases_caseteam` | `{ "specialist_email": "...", "specialist_name": "..." }` |
| `HYPOTHESIS_SUBMITTED`| Structured hypothesis submitted | Specialist | `collaboration_hypothesis` | `{ "proposed_diagnosis": "..." }` |
| `HYPOTHESIS_WITHDRAWN`| Hypothesis marked withdrawn | Specialist | `collaboration_hypothesis` | `{ "withdrawal_reason": "..." }` |
| `DISCUSSION_POSTED` | Narrative note posted to thread | Any member | `collaboration_discussionnote`| `{ "note_length": 140 }` |
| `RANK_UPDATED` | Differential ranking reordered | Primary Phys | `cases_diagnosisranking` | `{ "hypothesis_id": "...", "new_rank": 1 }` |
| `DECISION_RECORDED` | Final decision submitted & case closed | Primary Phys | `cases_decision` | `{ "final_diagnosis": "...", "advisory_acknowledged": true }` |
| `ACCESS_DENIED` | Blocked authorization check (RBAC) | Any | Context Model | `{ "attempted_action": "...", "reason": "..." }` |

---

## 4. HTTP Status Code Conventions

- `200 OK`: Successful `GET` view rendering or synchronous JSON inquiry.
- `201 Created`: Resource successfully created (via API endpoint).
- `302 Found`: Standard Post/Redirect/Get (PRG) pattern for form submissions, redirecting to destination view upon valid POST.
- `400 Bad Request`: Form validation failure (rendered back to user with inline field error alerts).
- `403 Forbidden`: RBAC access violation or governance breach (renders standard security error page and creates `ACCESS_DENIED` audit entry).
- `404 Not Found`: Target entity UUID does not exist or user has zero visibility.
