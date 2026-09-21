# Product Backlog — DOPA (Clinical Collaboration Platform)

**Assumption:** Python 3.11 / Django 4.2 LTS / PostgreSQL 15 modular monolith, developed in 5 sequential iterations by an agile engineering pair/team, targeting zero-defect execution.

---

## Epic 1: Identity, Role Binding & Authentication Engine
*Foundation for least-privilege security and governance asymmetry.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B01** | As a clinician, I want to register an account by providing my full name, email, password, and declared role (`PRIMARY_PHYSICIAN` or `SPECIALIST`), so that the system establishes my professional identity. | High | M | ARCHITECTURE.md §2.1 | **FR1, C-01, FT01**. Role choices explicit; role is bound immutably upon account creation and cannot be changed. Passwords validated against complexity rules. |
| **B02** | As a clinician, I want to log in using my email and password over HTTPS, so that I can establish a secure authenticated session. | High | S | B01 | **FR1, NFR1, NFR2, C-02, FT02**. Passwords hashed via salted PBKDF2-SHA256; session stored in HttpOnly + Secure + SameSite=Lax cookie. |
| **B03** | As the system, I want to throttle repeated failed login attempts from the same IP address, so that credential stuffing and brute-force attacks are mitigated. | High | S | B02 | **C-04**. Lockout or rate-limiting enforced at view/middleware level (5 failed attempts per 15 minutes). |
| **B04** | As a security auditor, I want unauthenticated requests to protected endpoints redirected to the login page without leaking clinical data, so that case confidentiality is preserved. | High | S | B02 | **NFR3, C-05, FT03**. Standard `@login_required` enforcement on all clinical dashboards and workspace routes. |
| **B05** | As a clinician, I want my active session to automatically expire after 30 minutes of inactivity, so that unattended workstations cannot be hijacked. | Medium | S | B02 | **GAP-03, NFR-SEC-01**. Configured via `SESSION_COOKIE_AGE=1800` with rolling extension on request activity. |
| **B06** | As a clinician, I want a secure password reset workflow via email token, so that I can recover my account without administrative intervention. | Medium | M | B02 | **GAP-06, FR-AUTH-02**. Standard Django token generator; token expires in 24 hours. |

---

## Epic 2: Clinical Case Management & Team Admission
*Primary Physician case creation, team curation, and role-routed dashboards.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B07** | As a Primary Physician, I want to create a new clinical case with title, clinical summary, patient history, and structured findings, so that I can initiate collaborative reasoning. | High | M | B01, B04 | **FR2, C-13, FT04, FAULT-01**. All 4 fields mandatory; findings structured with subheadings; `owner_id` set to creator; `status` initialized to `OPEN`. |
| **B08** | As the system, I want to block Specialists from creating cases with an HTTP 403 response, so that case ownership is reserved exclusively for Primary Physicians. | High | S | B07 | **NFR3, C-07, FT05**. Server-side RBAC decorator check; dispatches `ACCESS_DENIED` audit log. |
| **B09** | As a Primary Physician, I want to admit Specialists to my case team by their registered email address, so that advisory access is restricted to invited clinicians. | High | M | B07 | **FR2, C-14, FAULT-02**. System verifies target account exists and holds `SPECIALIST` role; rejects Primary Physicians; creates `CaseTeam` record. |
| **B10** | As a clinician, I want to view a personalized dashboard showing my cases upon login, so that I see only cases I own (if Primary Physician) or cases I am admitted to (if Specialist). | High | M | B07, B09 | **US-SY-02, C-15, FT02**. Strict query scoping (`Case.objects.filter(owner=request.user)` vs `Case.objects.filter(caseteam__specialist=request.user)`). |
| **B11** | As a clinician, I want to filter cases on my dashboard by status (`OPEN`, `UNDER_REVIEW`, `DECIDED`, `CLOSED`) and search by title, so that I can manage large case volumes efficiently. | Medium | S | B10 | **GAP-07, FR-CASE-01**. Server-side query parameter filtering and search. |
| **B12** | As an admitted Specialist, I want to receive an in-app notification when I am admitted to a case team, so that I know my expertise has been requested without polling. | Medium | S | B09 | **GAP-05, FAULT-07, FR-NOTIFY-01**. Notification record generated with direct link to case workspace. |

---

## Epic 3: Asynchronous Collaboration & Hypothesis Formulation
*Multi-specialist structured reasoning and narrative discussion.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B13** | As an admitted Specialist, I want to submit a structured hypothesis with proposed diagnosis, clinical rationale, and supporting evidence, so that my reasoning is rigorously documented. | High | M | B09, ARCHITECTURE.md §2.4 | **FR3, C-16, FT06**. All 3 fields mandatory (min 20 chars); validated server-side; stored with specialist ID and UTC timestamp; transitions case from `OPEN` to `UNDER_REVIEW`. |
| **B14** | As the system, I want to block non-admitted Specialists or unauthorized actors from submitting hypotheses with an HTTP 403 response, so that team boundaries are inviolable. | High | S | B13 | **NFR3, C-08, FT06b**. Evaluates `CaseTeam` membership; logs `ACCESS_DENIED` to audit table on failure. |
| **B15** | As an admitted Specialist, I want to submit multiple distinct hypotheses for the same case, so that I can explore multiple diagnostic possibilities. | High | S | B13 | **C-17**. Allows repeated submissions by same specialist; each assigned unique `hypothesis_id`. |
| **B16** | As a Specialist, I want to mark an earlier hypothesis as withdrawn with an explanatory note, so that my evolving judgment is documented while preserving historical provenance. | High | M | B13 | **C-18, FAULT-03, FAULT-06**. Hypothesis status changed to `WITHDRAWN`; permanently visible in workspace with `[WITHDRAWN]` badge; excluded from active ranking list. |
| **B17** | As an authorized case participant, I want to post narrative notes in a chronological discussion thread, so that we can ask clarifying questions across timezones. | High | M | B09, B13 | **FR4, C-19**. Open to owner and admitted specialists; server UTC timestamp; ordered chronologically; XSS escaping via Django templates. |
| **B18** | As a clinician on an intermittent 3G connection, I want form submissions to be idempotent, so that network re-transmissions do not create duplicate hypotheses or notes. | Medium | S | B13, B17 | **US-SY-04, NFR5**. Synchronizer token in hidden form field; prevents duplicate POST writes. |

---

## Epic 4: Differential Diagnosis Ranking & Decision Governance
*Physician-led differential prioritisation and legally binding final decision.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B19** | As a Primary Physician, I want to view all active hypotheses in a ranked differential list and reorder them using move-up and move-down controls, so that I reflect clinical priority. | High | M | B13, ARCHITECTURE.md §2.6 | **FR5, C-20, FT07**. Swap operations update `rank_position` atomically; dispatches `RANK_UPDATED` audit entry. |
| **B20** | As an admitted Specialist, I want to view the differential ranking list in read-only mode, so that I can see the physician's prioritisation without possessing write access. | High | S | B19 | **C-21**. UI omits reorder controls; server-side view handler rejects non-owner POST with HTTP 403. |
| **B21** | As a Primary Physician, I want to record the final clinical decision only after acknowledging a mandatory governance statement, so that legal responsibility remains unambiguous. | High | M | B19, ARCHITECTURE.md §2.7 | **FR6, FR8, C-22, FT09, FT10**. Modal prompt states specialist advice is advisory and physician retains full responsibility; decision field disabled until checkbox ticked. |
| **B22** | As the system, I want to block Specialists from recording a final clinical decision with an HTTP 403 response, so that advisory specialists cannot finalize cases. | High | S | B21 | **NFR3, C-09, FT08**. Server-side RBAC check; dispatches `ACCESS_DENIED` audit log. |
| **B23** | As the system, I want to enforce database-level singularity on final decisions, so that no case can ever receive more than one final decision. | High | S | B21 | **NFR8, C-28, G-03**. `UNIQUE` constraint on `cases_decision(case_id)`. Re-submission rejected by ORM and database. |
| **B24** | As the system, I want case status to transition to `CLOSED` upon final decision recording, so that no further hypotheses, rankings, or notes can be submitted. | High | S | B21, B23 | **C-23, FAULT-04, FAULT-05**. Case status locked; workspace switches to permanent read-only archive mode. |

---

## Epic 5: Forensic Audit Logging & Access Forensics
*Append-only non-repudiation audit trail and denial forensics.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B25** | As the system, I want a centralized audit service that logs every clinical and security event with actor, action, entity, case ID, IP address, and UTC timestamp, so that an immutable record is maintained. | High | M | ARCHITECTURE.md §2.8 | **FR7, NFR8, C-26, C-27, US-SY-01**. Logs `LOGIN`, `CASE_CREATED`, `SPECIALIST_ADMITTED`, `HYPOTHESIS_SUBMITTED`, `HYPOTHESIS_WITHDRAWN`, `RANK_UPDATED`, `DECISION_RECORDED`, `ACCESS_DENIED`. |
| **B26** | As a security officer, I want database privileges configured so that ordinary application users cannot UPDATE or DELETE audit records, ensuring append-only durability. | High | S | B25 | **NFR8, C-26, C-30**. Django model omits update/delete views; PostgreSQL grant restricts app user to `INSERT` and `SELECT` on audit table. |
| **B27** | As the system, I want every blocked RBAC authorization attempt logged as `ACCESS_DENIED` with actor and context, so that malicious probing or permission drift is auditable. | High | S | B25 | **C-31, G-04**. Triggered directly from RBAC decorators upon HTTP 403 generation. |
| **B28** | As an authorized case participant, I want to view the chronological audit trail for my cases in a dedicated read-only viewer, so that decision provenance is verifiable. | Medium | M | B25, B27 | **US-PP-10, C-29, FT11**. Shows complete sequence of events including timestamps, actor names, and denied actions. |

---

## Epic 6: Low-Bandwidth Usability, Responsive Workspace & Quality Verification
*Low-latency 3-pane interface, query optimization, and test automation.*

| ID | Story | Priority | Est. | Depends on | Notes / Acceptance Criteria |
|---|---|---|---|---|---|
| **B29** | As a clinician, I want a unified 3-pane clinical workspace (presentation/thread, hypotheses, differential ranking) on a single screen, so that I can reason without context-switching. | High | M | B07, B13, B19 | **NFR7, C-24**. Semantic HTML grid/flex layout; responsive collapse on mobile viewports (< 768px). |
| **B30** | As a clinician on a slow/throttled 3G connection in an LMIC setting, I want pages to load in under 2.5 seconds, so that low bandwidth does not hinder clinical care. | High | M | B29 | **NFR4, NFR5, C-25, C-37**. Capped to $\le 4$ SQL queries per page via `select_related` and `prefetch_related`; zero heavy client JS bundles. |
| **B31** | As a developer, I want an automated test suite executing functional test cases FT01 through FT11, so that regressions are detected prior to release. | High | M | All Epics | **Table 4.2**. Automated Django test suite verifying all positive and negative security/governance paths with 100% pass rate. |
| **B32** | As a test engineer, I want seed fixtures for the 3 clinical test cases from Appendix A, so that end-to-end multi-specialist clinical workflows can be fully validated. | Medium | S | B31 | **Appendix A**. Fixtures covering Multi-system Fever/Rash, Chronic Microcytic Anaemia, and Pediatric Neurological Presentation. |
