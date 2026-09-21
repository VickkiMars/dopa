# Sprint Execution Plan — DOPA Platform

This document outlines the 5 sequential sprint backlogs that take the DOPA platform from zero to fully tested, bug-free delivery. Each sprint delivers an independently verifiable, shippable increment.

---

## Sprint 1: Core Foundation, Identity & Role Engine

**Goal:** Establish the modular architecture, immutable role-based authentication, and append-only audit foundation.  
**Timebox:** 1 iteration  
**Pulled from:** `PRODUCT_BACKLOG.md` items B01, B02, B03, B04, B05, B06, B25, B26  

### Committed Tasks
| Task ID | Task Description | Backlog Ref | Depends on | Status |
|---|---|---|---|---|
| **S1-01** | Initialize Django project with apps: `accounts`, `cases`, `collaboration`, `audit`. Configure PostgreSQL/SQLite settings and environment loaders. | — | ARCHITECTURE.md §1 | Not started |
| **S1-02** | Implement custom `User` model with immutable `role` field (`PRIMARY_PHYSICIAN`, `SPECIALIST`) and UUID primary keys. | B01 | S1-01 | Not started |
| **S1-03** | Create registration view and form with clear role options and server-side validation. | B01 | S1-02 | Not started |
| **S1-04** | Implement secure login view with PBKDF2 hashing, rate-limiting (5 failures/15 min), and session cookie configuration. | B02, B03 | S1-02 | Not started |
| **S1-05** | Configure 30-minute idle session timeout and unauthenticated redirect middleware. | B04, B05 | S1-04 | Not started |
| **S1-06** | Implement password reset workflow via email tokens. | B06 | S1-02 | Not started |
| **S1-07** | Implement `AuditLog` model and `audit.log_event()` service logging `LOGIN` and user events. | B25, B26 | S1-02 | Not started |
| **S1-08** | Write automated unit tests for FT01 (Registration), FT02 (Login), FT03 (Unauthenticated redirect). | B31 | S1-03, S1-04, S1-05 | Not started |

### Sprint 1 Definition of Done Check
- [ ] FT01, FT02, FT03 passing in automated test suite.
- [ ] Passwords stored only as salted PBKDF2 hashes; roles cannot be changed post-creation.
- [ ] Audit log entry created on successful login.

---

## Sprint 2: Clinical Case Management, Team Admission & Dashboards

**Goal:** Enable Primary Physicians to create cases, admit specialists, and view role-routed filtered dashboards with denial forensics.  
**Timebox:** 1 iteration  
**Pulled from:** `PRODUCT_BACKLOG.md` items B07, B08, B09, B10, B11, B12, B27  

### Committed Tasks
| Task ID | Task Description | Backlog Ref | Depends on | Status |
|---|---|---|---|---|
| **S2-01** | Implement `Case` model with fields (`title`, `clinical_summary`, `history`, `findings`, `status=OPEN`) and validation. | B07 | S1-02 | Not started |
| **S2-02** | Implement `CaseTeam` junction model with composite unique key `(case_id, specialist_id)`. | B09 | S2-01 | Not started |
| **S2-03** | Create Case Creation form & view; restrict creation to `PRIMARY_PHYSICIAN` role; log `CASE_CREATED`. | B07, B08 | S2-01, S1-07 | Not started |
| **S2-04** | Implement RBAC gatekeeper decorator `@case_owner_required` and `@case_access_required`; log `ACCESS_DENIED` on breach. | B08, B27 | S2-01, S1-07 | Not started |
| **S2-05** | Build Specialist Admission form & view; validate account existence and `SPECIALIST` role; reject Primary Physicians. | B09 | S2-02, S2-04 | Not started |
| **S2-06** | Create in-app `Notification` model and dispatch notification on specialist admission. | B12 | S2-05 | Not started |
| **S2-07** | Build role-routed Dashboard view: Primary Physician sees owned cases; Specialist sees admitted cases. | B10 | S2-01, S2-02 | Not started |
| **S2-08** | Add status filtering (`OPEN`, `UNDER_REVIEW`, `DECIDED`, `CLOSED`) and title search to dashboard. | B11 | S2-07 | Not started |
| **S2-09** | Write automated unit tests for FT04 (Case Creation) and FT05 (Specialist Creation Denial & Log). | B31 | S2-03, S2-04 | Not started |

### Sprint 2 Definition of Done Check
- [ ] FT04 and FT05 passing in automated test suite.
- [ ] Specialists attempting case creation receive HTTP 403 and generate an `ACCESS_DENIED` audit record.
- [ ] Only confirmed Specialists can be added to case teams.

---

## Sprint 3: 3-Pane Clinical Workspace, Structured Hypotheses & Discussion

**Goal:** Deliver the responsive 3-pane clinical workspace with structured hypothesis submission, withdrawal tracking, and chronological discussion.  
**Timebox:** 1 iteration  
**Pulled from:** `PRODUCT_BACKLOG.md` items B13, B14, B15, B16, B17, B18, B29, B30  

### Committed Tasks
| Task ID | Task Description | Backlog Ref | Depends on | Status |
|---|---|---|---|---|
| **S3-01** | Construct single-page 3-pane workspace template (Left: Case/Discussion, Center: Hypotheses, Right: Ranking/Decision). | B29 | S2-01 | Not started |
| **S3-02** | Optimize workspace query loader via `select_related` and `prefetch_related` (budget $\le 4$ queries). | B30 | S3-01 | Not started |
| **S3-03** | Implement `Hypothesis` model with mandatory `proposed_diagnosis`, `rationale`, and `supporting_evidence`. | B13 | S2-01 | Not started |
| **S3-04** | Implement Hypothesis Submission form & view with server-side validation and idempotency token. | B13, B18 | S3-03 | Not started |
| **S3-05** | Enforce RBAC on hypothesis submission: verify specialist is in `CaseTeam`; reject with 403 and log denial if not. | B14 | S3-04, S2-04 | Not started |
| **S3-06** | Implement hypothesis withdrawal action: set status to `WITHDRAWN`, preserve in thread with visual badge. | B16 | S3-03 | Not started |
| **S3-07** | Implement `DiscussionNote` model and post view for authorized participants; enforce template XSS escaping. | B17 | S2-01, S2-04 | Not started |
| **S3-08** | Write automated unit tests for FT06 (Admitted Specialist Hypothesis) and FT06b (Non-admitted Denial). | B31 | S3-04, S3-05 | Not started |

### Sprint 3 Definition of Done Check
- [ ] FT06 and FT06b passing in automated test suite.
- [ ] Workspace queries strictly $\le 4$ SQL roundtrips per page render.
- [ ] Withdrawn hypotheses remain visible in discussion with `[WITHDRAWN]` badge.

---

## Sprint 4: Differential Diagnosis Ranking & Decision Governance

**Goal:** Implement physician differential diagnosis ranking and the locked governance modal for the final clinical decision.  
**Timebox:** 1 iteration  
**Pulled from:** `PRODUCT_BACKLOG.md` items B19, B20, B21, B22, B23, B24  

### Committed Tasks
| Task ID | Task Description | Backlog Ref | Depends on | Status |
|---|---|---|---|---|
| **S4-01** | Implement `DiagnosisRanking` model with `(case_id, hypothesis_id)` and `(case_id, rank_position)` unique constraints. | B19 | S3-03 | Not started |
| **S4-02** | Build differential ranking reorder view (move-up / move-down); restrict write access to Case Owner; log `RANK_UPDATED`. | B19 | S4-01, S2-04 | Not started |
| **S4-03** | Render differential ranking in read-only mode for Specialists; verify server rejects specialist reorder attempts. | B20 | S4-02 | Not started |
| **S4-04** | Implement `Decision` model with `case_id` **UNIQUE** constraint and boolean `advisory_acknowledged`. | B21, B23 | S2-01 | Not started |
| **S4-05** | Build Governance Modal in Primary Physician workspace requiring explicit checkbox acknowledgement before submitting decision. | B21 | S4-04 | Not started |
| **S4-06** | Enforce RBAC on Decision recording: reject specialist attempts with HTTP 403 and log `ACCESS_DENIED`. | B22 | S4-05, S2-04 | Not started |
| **S4-07** | Implement atomic case transition to `CLOSED` upon decision submission, permanently locking all modifications. | B24 | S4-05 | Not started |
| **S4-08** | Write automated unit tests for FT07 (Ranking Update), FT08 (Specialist Decision Denial), FT09 (Checkbox Gate), FT10 (Final Decision Recorded & Case Closed). | B31 | S4-02, S4-05, S4-06, S4-07 | Not started |

### Sprint 4 Definition of Done Check
- [ ] FT07, FT08, FT09, FT10 passing in automated test suite.
- [ ] Database enforces single decision per case via UNIQUE constraint.
- [ ] Closed cases reject subsequent submissions and ranking modifications.

---

## Sprint 5: Audit Forensics, Verification Suite & Clinical Fixtures

**Goal:** Deliver the complete audit trail viewer, run full regression tests, and seed Appendix A clinical fixtures.  
**Timebox:** 1 iteration  
**Pulled from:** `PRODUCT_BACKLOG.md` items B28, B31, B32  

### Committed Tasks
| Task ID | Task Description | Backlog Ref | Depends on | Status |
|---|---|---|---|---|
| **S5-01** | Build read-only `AuditTrailView` displaying complete chronological logs for case owner and admitted team. | B28 | S1-07 | Not started |
| **S5-02** | Write automated test FT11 verifying complete audit chronology reconstruction including denied requests. | B31 | S5-01 | Not started |
| **S5-03** | Create Django management command / test fixtures for Appendix A Clinical Cases (Multi-system Fever/Rash, Chronic Anaemia, Pediatric Neurology). | B32 | All models | Not started |
| **S5-04** | Execute end-to-end automated test runner for all functional cases (FT01–FT11) with coverage report ($\ge 90\%$). | B31 | All tests | Not started |
| **S5-05** | Measure page response times under simulated broadband and 3G throttled networks to confirm NFR4 and NFR7. | B30 | S3-01 | Not started |

### Sprint 5 Definition of Done Check
- [ ] 100% of functional tests (FT01–FT11) passing.
- [ ] Complete clinical provenance verified via Audit Trail viewer for all 3 clinical test cases.
- [ ] Production-ready zero-defect signoff.
