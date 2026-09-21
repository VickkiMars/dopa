# DOPA — High-Density Requirements Analysis
**Document:** DOPA COMPLETE.docx  
**System:** Secure Cloud-Based Platform for Global Specialist Collaboration in Complex Clinical Case Management  
**Author of Document:** Ifeanyichukwu James Ugwu (21/SC/CO/1022), University of Uyo  
**Analysis performed by:** Senior Requirements Analyst (AI)  
**Analysis date:** 2026-09-21  

---

> [!IMPORTANT]
> This is an **institution-grade** requirements analysis. It documents every pre-development requirement, every post-development (delivered) capability, all user stories, and — critically — all **gaps, faults, and contradictions** found in the specification.

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Pre-Development Requirements](#2-pre-development-requirements)
   - 2.1 [Dataset & Domain Knowledge Requirements](#21-dataset--domain-knowledge-requirements)
   - 2.2 [Infrastructure & Environment Requirements](#22-infrastructure--environment-requirements)
   - 2.3 [Regulatory & Compliance Requirements](#23-regulatory--compliance-requirements)
   - 2.4 [Functional Requirements (FR1–FR8)](#24-functional-requirements-fr1fr8)
   - 2.5 [Non-Functional Requirements (NFR1–NFR8)](#25-non-functional-requirements-nfr1nfr8)
   - 2.6 [Governance & Ethical Requirements](#26-governance--ethical-requirements)
   - 2.7 [Toolchain & Technology Requirements](#27-toolchain--technology-requirements)
3. [Post-Development Capabilities](#3-post-development-capabilities)
   - 3.1 [Security & Access Control](#31-security--access-control)
   - 3.2 [Clinical Collaboration Features](#32-clinical-collaboration-features)
   - 3.3 [Governance & Audit Features](#33-governance--audit-features)
   - 3.4 [Deployment & Operational Features](#34-deployment--operational-features)
   - 3.5 [Measured Performance Benchmarks](#35-measured-performance-benchmarks)
4. [User Stories](#4-user-stories)
   - 4.1 [Primary Physician (Case Owner)](#41-primary-physician-case-owner)
   - 4.2 [Specialist (Advisory Role)](#42-specialist-advisory-role)
   - 4.3 [System / Cross-Cutting](#43-system--cross-cutting)
5. [Gaps, Faults, and Contradictions](#5-gaps-faults-and-contradictions)
   - 5.1 [Critical Gaps](#51-critical-gaps)
   - 5.2 [Functional Faults & Under-specifications](#52-functional-faults--under-specifications)
   - 5.3 [Contradictions](#53-contradictions)
   - 5.4 [Non-Functional Under-specifications](#54-non-functional-under-specifications)
   - 5.5 [Governance & Ethical Gaps](#55-governance--ethical-gaps)
6. [Traceability Matrix](#6-traceability-matrix)
7. [Risk Register (derived)](#7-risk-register-derived)

---

## 1. System Overview

| Field | Value |
|---|---|
| **System name** | DOPA (inferred — not explicitly stated in document) |
| **Type** | Web-based SaaS prototype |
| **Purpose** | Enable structured, asynchronous, multi-specialist clinical reasoning for complex cases with enforceable governance boundaries |
| **Primary users** | Primary Physicians (case owners), Specialists (advisory) |
| **Scope boundary** | Non-emergency complex cases; no real patient data; no HIPAA/GDPR compliance claimed |
| **Deployment target** | Free-tier PaaS (Render) + managed PostgreSQL (Supabase) |
| **Technology stack** | Python 3.11, Django 4.2 LTS, PostgreSQL 15, Git/GitHub, Django Templates + Tailwind CSS 5.x, Gunicorn |
| **SDLC model** | Agile/Scrum, 5 iterative increments |

---

## 2. Pre-Development Requirements

### 2.1 Dataset & Domain Knowledge Requirements

These are the knowledge inputs, domain artefacts, and reference datasets that had to exist **before** development could be started or justified:

| ID | Requirement | Source in doc |
|---|---|---|
| D-01 | **Literature corpus on e-consultation systems** — systematic reviews from Liddy et al. (2013, 2016, 2019), Vimalananda et al. (2015, 2020) establishing that asynchronous consultation reduces referrals and improves PCP knowledge | Ch.1–2 |
| D-02 | **VMTB evidence base** — Blasi et al. (2021), Gebbia et al. (2021), Hopkins et al. (2022), Rao et al. (2020) establishing structured multi-specialist collaboration improves diagnostic confidence | Ch.2 |
| D-03 | **LMIC healthcare context data** — Miah et al. (2017), Daniels (2024), Kruse et al. (2020) establishing connectivity/infrastructure constraints that shape NFRs | Ch.2 |
| D-04 | **Security breach statistics** — IBM Security (2024), Metomic (2024), Cloud Security Alliance (2024) quantifying healthcare cloud threat landscape | §2.2.2, §2.5 |
| D-05 | **Mock clinical scenarios (3 cases)** — fictitious case data (multi-system fever/rash; chronic microcytic anaemia; episodic unresponsiveness in children) used as test fixtures | Appendix A |
| D-06 | **RBAC reference model** — theoretical grounding in least-privilege principle for healthcare IS | §2.5.2 |
| D-07 | **CDSS taxonomy** — Gen 1/2/3 human-AI interaction framework (MDPI 2026) framing the system as human-expertise-enhancing, not AI-replacing | §2.6.1 |
| D-08 | **Telemedicine regulatory landscape** — HIPAA, GDPR, HITECH, HITRUST, SOC 2, ISO 27001 context as background (even though not enforced) | §2.5.4 |

> [!NOTE]
> The document does not require any **real patient dataset** — all data is synthetic. The requirement for a dataset is entirely epistemic (literature-based) and testing-fixture-based (mock scenarios). This is a scope decision, not a gap; it is explicitly stated.

---

### 2.2 Infrastructure & Environment Requirements

Requirements that must be provisioned **before** the system can be built or run:

| ID | Requirement | Detail |
|---|---|---|
| I-01 | **Development machine** | Intel Core i7, 16 GB RAM, 256 GB SSD (or equivalent) |
| I-02 | **PaaS cloud account** | Render free tier: 512 MB managed web runtime, automatic HTTPS/TLS |
| I-03 | **Managed PostgreSQL account** | Supabase free tier: 256 MB storage, automated backups, encryption at rest |
| I-04 | **Version control repository** | Git + GitHub, configured as the continuous deployment trigger |
| I-05 | **TLS certificate provisioning** | Handled automatically by Render edge; no manual cert management required |
| I-06 | **Static asset hosting** | Platform's built-in static serving mechanism within free-tier quota |
| I-07 | **Python runtime** | Python 3.11 |
| I-08 | **IDE** | Visual Studio Code (or equivalent) |

---

### 2.3 Regulatory & Compliance Requirements

> [!WARNING]
> The document **explicitly scopes out** formal regulatory compliance. The following represents the **minimum acknowledged** regulatory context, not a compliance target.

| ID | Requirement | Status in document |
|---|---|---|
| R-01 | HIPAA compliance | ❌ Out of scope for prototype — acknowledged as future work (§5.3) |
| R-02 | GDPR compliance | ❌ Out of scope for prototype — acknowledged as future work (§5.3) |
| R-03 | HITECH compliance | ❌ Not addressed |
| R-04 | HITRUST / SOC 2 / ISO 27001 accreditation | ❌ Not addressed |
| R-05 | Business Associate Agreements (BAAs) | ❌ Not signed — noted as requirement for production (§5.3) |
| R-06 | Data-retention and breach-notification procedures | ❌ Deferred to production phase |
| R-07 | Formal risk assessment | ❌ Deferred to production phase |
| R-08 | Penetration testing | ❌ Deferred — recommended pre-production (§5.3) |
| R-09 | No real patient data — all cases synthetic | ✅ Enforced throughout |

---

### 2.4 Functional Requirements (FR1–FR8)

As formally stated in §3.2.2 of the document:

| ID | Requirement | Verification condition |
|---|---|---|
| **FR1** | **Role-based registration & authentication** — user must register declaring role (Primary Physician or Specialist); session authenticated via password over encrypted connection | Role stored immutably at registration; HTTPS enforced |
| **FR2** | **Case creation & ownership** — logged-in Primary Physician creates a case with structured fields: title, clinical summary, patient history, relevant findings; creating physician becomes owner | Case persists with owner_id; audit entry created |
| **FR3** | **Structured hypothesis submission** — Specialist with case access submits a hypothesis with three mandatory fields: proposed diagnosis, clinical rationale, supporting evidence | All three fields server-validated; hypothesis stored with author + UTC timestamp |
| **FR4** | **Asynchronous case discussion** — all authorised participants post narrative notes in a chronological thread; supports cross-timezone, intermittent-connectivity usage | Thread ordered by server-side timestamp; stateless request/response |
| **FR5** | **Differential diagnosis ranking** — Primary Physician sees all submitted hypotheses in a ranked list and can reorder them | Ranking persisted; visible to specialists in read-only mode |
| **FR6** | **Final decision recording** — Primary Physician records the final clinical decision; requires explicit advisory acknowledgement before submission | Decision persists; case status transitions to closed; uniqueness enforced |
| **FR7** | **Audit logging** — system auto-generates an audit record for every security-relevant or clinically-relevant action (LOGIN, CASE_CREATED, HYPOTHESIS_SUBMITTED, RANK_UPDATED, DECISION_RECORDED, ACCESS_DENIED) including actor name, action description, UTC timestamp, case ID | Append-only; ordinary users cannot update or delete |
| **FR8** | **Advisory governance notice** — when Primary Physician records final decision, a governance message is displayed making clear that specialist input is advisory and clinical responsibility remains with the physician | Modal shown; acknowledgement checkbox required before submission |

---

### 2.5 Non-Functional Requirements (NFR1–NFR8)

As formally stated in §3.2.3:

| ID | Requirement | Metric / Test |
|---|---|---|
| **NFR1** | **Confidentiality in transit** — all client-server comms use HTTPS (TLS) | TLS enforced at platform edge; HSTS enabled |
| **NFR2** | **Confidentiality at rest** — case data, credentials, audit logs stored encrypted; passwords stored as salted PBKDF2 hashes only | Managed DB encryption; no plaintext passwords |
| **NFR3** | **Least-privilege authorisation** — all case resource access mediated by RBAC engine; no direct role-to-data bypass | Server-side enforcement on every request; HTTP 403 on denial |
| **NFR4** | **Low-latency global access** — hosted on geographically distributed cloud infrastructure | Render global distribution; warm response times < 1 s |
| **NFR5** | **Elastic scalability within free-tier constraints** — architecture scales with concurrent consultations and fits within free-tier memory/compute | Modular monolith; connection pooling managed within Supabase quota |
| **NFR6** | **Availability & data durability** — managed services with automated backup | Supabase automated backup; no data loss in testing |
| **NFR7** | **Usability & workflow integration** — discussion thread, hypothesis form, and ranking view presented in a single coherent interface | Single-page 3-pane workspace; task-completion < 10 min |
| **NFR8** | **Non-repudiation & auditability** — audit log append-only for ordinary users; specialist advice and final decisions cannot be altered post-record | DB-level privilege restriction; tamper confirmed absent in testing |

---

### 2.6 Governance & Ethical Requirements

These are structural requirements that must be designed-in, not bolted on:

| ID | Requirement |
|---|---|
| G-01 | The Specialist role **must** have no pathway — either through the UI or a direct API call — to record a final clinical decision |
| G-02 | The Primary Physician **must** acknowledge the advisory nature of specialist input before a decision is recorded |
| G-03 | The final decision **must** be unique per case — enforced both at application level and via DB UNIQUE constraint |
| G-04 | All denied access attempts **must** be recorded in the audit log (not just successful actions) |
| G-05 | Withdrawn hypotheses **must** remain visible in thread history — the reasoning record must be complete |
| G-06 | The audit log **must** be accessible for reading by both roles (for their own cases) but modifiable by no ordinary user |
| G-07 | Role assignment must be **immutable** after registration — a Specialist account cannot self-elevate to Primary Physician |
| G-08 | Only users with a registered Specialist role can be admitted to a case team; Primary Physicians cannot be admitted as advisory specialists |

---

### 2.7 Toolchain & Technology Requirements

Specific technology decisions locked before or during development:

| Component | Technology | Version | Justification |
|---|---|---|---|
| Language | Python | 3.11 | Server-side logic |
| Framework | Django | 4.2 LTS | Built-in auth (PBKDF2), XSS escaping, CSRF protection, ORM, admin |
| Database | PostgreSQL | 15 | Managed relational DB; ACID guarantees; FK integrity |
| DB Host | Supabase | Free tier | Serverless PostgreSQL; encryption at rest; automated backups |
| App Host | Render | Free tier | PaaS with automatic TLS 1.2+; Git-triggered CI/CD |
| Version control | Git + GitHub | — | CI/CD trigger; rollback capability |
| Front-end | Django Templates + Tailwind CSS | 5.x | Low-bandwidth; no heavy JS framework |
| WSGI server | Gunicorn | 21.x | Production-grade app server |
| IDE | VS Code | — | Development environment |

---

## 3. Post-Development Capabilities

These are the **verified, delivered capabilities** of the system after development and testing.

### 3.1 Security & Access Control

| Cap ID | Capability | Evidence |
|---|---|---|
| C-01 | Role-based registration with **immutable role binding** — role cannot change post-registration | FT01 pass |
| C-02 | Password-based authentication with **salted PBKDF2 hashing** — no plaintext passwords stored | Implemented via Django auth; FT02 pass |
| C-03 | **Session management** via HttpOnly + Secure cookies — session token not accessible to browser scripts; sent only over HTTPS | Implementation §4.2.2 |
| C-04 | **Account lockout & rate limiting** on login — multiple failed attempts from same IP throttled | §4.2.2 |
| C-05 | **HTTPS-only communication** — plain HTTP redirected to HTTPS at platform edge; HSTS enabled | FT03: unauthenticated access redirects; NFR1 satisfied |
| C-06 | **RBAC engine as gateway** — operates before any view handler, checks role + case relationship + case status on every request | FT05, FT08 pass (HTTP 403 on denial) |
| C-07 | **Specialist blocked from case creation** — HTTP 403, denial logged | FT05 pass |
| C-08 | **Non-admitted specialist blocked from hypothesis submission** | FT06b pass |
| C-09 | **Specialist blocked from final decision recording** — HTTP 403, denial logged | FT08 pass |
| C-10 | **Decision blocked without advisory acknowledgement** | FT09 pass |
| C-11 | **CSRF protection** on all state-changing forms — Django middleware | §4.2.2 |
| C-12 | **XSS escaping** on all user-submitted content — Django template engine | §4.3.4 |

---

### 3.2 Clinical Collaboration Features

| Cap ID | Capability |
|---|---|
| C-13 | **Case creation** with structured form: title, clinical summary, patient history, relevant findings; owner auto-assigned |
| C-14 | **Team admission** — Primary Physician admits Specialists by email address; only Specialist-role accounts eligible |
| C-15 | **Role-based dashboard routing** — Primary Physician sees their owned cases with status; Specialist sees only admitted cases |
| C-16 | **Structured hypothesis submission** with three mandatory fields (proposed diagnosis, rationale, supporting evidence); server-validated |
| C-17 | **Multi-hypothesis support** — Specialist may submit more than one hypothesis per case |
| C-18 | **Follow-up notes on hypotheses** — Specialist can add notes to modify or withdraw a prior hypothesis; withdrawn hypotheses remain visible |
| C-19 | **Asynchronous discussion thread** — chronological, timestamped, cross-timezone, intermittent-connection-safe |
| C-20 | **Differential diagnosis ranking** — Primary Physician reorders hypotheses via move-up/move-down; saves immediately |
| C-21 | **Read-only ranking view for Specialists** — advisory boundary visible in UI, not just enforced server-side |
| C-22 | **Final decision recording** — modal with governance notice, acknowledgement checkbox, decision closes case |
| C-23 | **Case lifecycle status tracking** — open → under_review → decided → closed |
| C-24 | **Single-page 3-pane workspace** — discussion thread (left), hypothesis form + list (centre), ranking (right) in one coherent interface |
| C-25 | **Mobile-responsive interface** — textual, low-bandwidth design for intermittent connectivity (LMIC context) |

---

### 3.3 Governance & Audit Features

| Cap ID | Capability |
|---|---|
| C-26 | **Append-only audit log** — ordinary users have no DB privilege to UPDATE or DELETE audit rows |
| C-27 | **Full event coverage** — LOGIN, CASE_CREATED, HYPOTHESIS_SUBMITTED, RANK_UPDATED, DECISION_RECORDED, ACCESS_DENIED all logged |
| C-28 | **Decision singularity enforced** — UNIQUE constraint on Decision.case_id at DB level; one decision per case ever |
| C-29 | **Advisory provenance** — every hypothesis and note attributable to author; decision traceable to evidence and advice |
| C-30 | **Tamper evidence confirmed** — no audit row altered during entire test period; verified by direct DB inspection |
| C-31 | **Denied-action forensics** — forged or replayed requests produce DENIED audit entries, not silent failures |
| C-32 | **Complete reasoning record** — withdrawn hypotheses remain in thread; no erasure of advisory history |

---

### 3.4 Deployment & Operational Features

| Cap ID | Capability |
|---|---|
| C-33 | **Zero-cost infrastructure** — entire system runs on free-tier PaaS + free-tier managed DB |
| C-34 | **Automated CI/CD** — Git push triggers clean rebuild, DB migration, static asset collection, service restart |
| C-35 | **One-click rollback** — any earlier commit can be restored via hosting platform |
| C-36 | **Connection pooling** — configured to stay within Supabase free-tier connection limit |
| C-37 | **Query-optimised pages** — all 3-pane workspace served by a small constant number of DB queries (cold-start mitigation) |
| C-38 | **Known limitation documented** — free-tier cold-start delay (avg 6.6–8.1 s first request) noted as hosting-tier characteristic, not application fault |

---

### 3.5 Measured Performance Benchmarks

All values from §4.4.3–4.4.4 (controlled test environment, developer testing only):

| Metric | Value |
|---|---|
| Login / dashboard warm response | 0.45 s |
| Case creation form submission warm | 0.61 s |
| Full workspace (3-pane) warm | 0.92 s |
| Hypothesis submission warm | 0.58 s |
| Ranking update warm | 0.44 s |
| Final decision recording warm | 0.63 s |
| Throttled 3G warm page loads | avg 2.3 s |
| Cold-start first request range | 6.6–8.1 s |
| Task error rate (60 executions) | 3.3% (2 of 60) |
| Governance breach in testing | 0 |
| Data loss in testing | 0 |

---

## 4. User Stories

Extracted and synthesised from §3.3, §4.3, and use-case descriptions. Written in standard **As a… I want to… So that…** format with acceptance criteria.

### 4.1 Primary Physician (Case Owner)

---

**US-PP-01 — Registration**  
*As a Primary Physician, I want to register an account declaring my role, so that the system knows I am a case owner and grants me appropriate permissions.*

**Acceptance Criteria:**
- [ ] Registration form collects full name, email, password, and role selection
- [ ] Role selection shows exactly two options: Primary Physician, Specialist, with plain-language descriptions
- [ ] Role is bound immutably at registration and cannot be changed later
- [ ] On successful registration, I am directed to my case dashboard
- [ ] If I attempt to re-register with the same email, the system rejects the attempt

---

**US-PP-02 — Login**  
*As a Primary Physician, I want to log in securely, so that I can access only my own cases and no one else's.*

**Acceptance Criteria:**
- [ ] Login form requires email and password
- [ ] All login traffic is transmitted over HTTPS
- [ ] On success, I am redirected to my case dashboard (list of owned cases with statuses)
- [ ] On failure, I receive an error message; multiple failures from same IP are rate-limited
- [ ] My session is managed via an HttpOnly + Secure cookie

---

**US-PP-03 — Case Creation**  
*As a Primary Physician, I want to create a new clinical case with structured fields, so that specialists have all the clinical context they need to formulate hypotheses.*

**Acceptance Criteria:**
- [ ] Case form includes: case title, clinical summary, patient history, relevant findings
- [ ] All fields are required
- [ ] On submission, I am designated as the case owner
- [ ] An audit entry (CASE_CREATED) is created immediately
- [ ] I am redirected to the case team management page after creation
- [ ] Case status begins as "open"

---

**US-PP-04 — Team Admission**  
*As a Primary Physician, I want to invite Specialists to my case by email address, so that only relevant and verified specialists can contribute.*

**Acceptance Criteria:**
- [ ] I can enter a Specialist's email address to admit them
- [ ] The system checks that the account exists and has the Specialist role before admitting
- [ ] Attempting to admit a Primary Physician account is rejected
- [ ] Admitted specialists appear in the case team list
- [ ] An audit entry is created for each team admission

---

**US-PP-05 — Read Case & Discussion**  
*As a Primary Physician, I want to read the full case record and the chronological discussion thread, so that I can follow the specialists' reasoning.*

**Acceptance Criteria:**
- [ ] I can view the complete clinical summary, history, findings, and all discussion notes for my own cases
- [ ] Discussion notes are displayed in chronological order with author name and timestamp
- [ ] I cannot view cases that I do not own

---

**US-PP-06 — Post Discussion Notes**  
*As a Primary Physician, I want to post narrative notes to the discussion thread, so that I can ask specialists for clarification or additional hypotheses.*

**Acceptance Criteria:**
- [ ] I can compose and post a note to any case I own
- [ ] The note is stored with my identity and a server-side UTC timestamp
- [ ] The note is visible to all case participants on their next page load
- [ ] Content is XSS-escaped by the server
- [ ] An audit entry is created

---

**US-PP-07 — View Submitted Hypotheses**  
*As a Primary Physician, I want to see all submitted diagnostic hypotheses in a single ranked list, so that I can evaluate the differential diagnosis across all specialists.*

**Acceptance Criteria:**
- [ ] All active hypotheses are displayed with author name, submission time, proposed diagnosis, rationale, evidence, and current rank
- [ ] Withdrawn hypotheses remain visible in the thread history
- [ ] The list is ordered by my current ranking preference

---

**US-PP-08 — Reorder Differential Diagnosis**  
*As a Primary Physician, I want to reorder the list of hypotheses, so that I can reflect my clinical prioritisation of the differential.*

**Acceptance Criteria:**
- [ ] Move-up and move-down controls exist next to each hypothesis
- [ ] Each reorder saves immediately and is recorded in the audit log (RANK_UPDATED)
- [ ] The updated order is reflected in the read-only view for Specialists on their next page load

---

**US-PP-09 — Record Final Decision**  
*As a Primary Physician, I want to record the final clinical decision for a case I own, so that the collaborative process has a definitive, legally attributable outcome.*

**Acceptance Criteria:**
- [ ] The final decision control is only visible in my workspace, not a Specialist's
- [ ] A modal governance notice appears when I activate the control, making clear: specialist input is advisory; I hold final clinical responsibility; the decision and full reasoning record will be permanently logged
- [ ] The decision field is disabled until I tick an acknowledgement checkbox
- [ ] Once submitted, the case is closed to further hypothesis submissions or ranking changes
- [ ] Exactly one final decision can ever be recorded per case (enforced at both application and DB level)
- [ ] The decision is recorded with my identity and a UTC timestamp
- [ ] Appropriate audit entries are written (DECISION_RECORDED)
- [ ] Attempting to access the decision control again on a decided case is rejected by both the interface and the server

---

**US-PP-10 — View Audit Trail**  
*As a Primary Physician, I want to review the audit trail for cases I own, so that I can demonstrate the provenance of any clinical decision if challenged.*

**Acceptance Criteria:**
- [ ] I can view a chronological log of all events related to my cases
- [ ] Each entry shows: actor name, action type, entity affected, case ID, UTC timestamp
- [ ] Denied-access attempts by unauthorised actors are also visible
- [ ] I cannot modify or delete any audit entry

---

### 4.2 Specialist (Advisory Role)

---

**US-SP-01 — Registration**  
*As a Specialist, I want to register an account declaring my role, so that the system identifies me as an advisory contributor.*

**Acceptance Criteria:**
- [ ] Same form as Primary Physician (full name, email, password, role)
- [ ] Role "Specialist" is immutably assigned
- [ ] On successful registration, I am directed to my case list (empty until admitted to a case)
- [ ] My account cannot admit me to cases; only a Primary Physician can do that

---

**US-SP-02 — Login**  
*As a Specialist, I want to log in securely, so that I can access only the cases to which I have been admitted.*

**Acceptance Criteria:**
- [ ] On success, I am redirected to a case list containing only my admitted cases
- [ ] I cannot access cases to which I have not been admitted, even by guessing URLs
- [ ] All same security controls apply as for Primary Physician login

---

**US-SP-03 — View Case Details**  
*As a Specialist, I want to read the clinical summary, history, findings, and discussion thread for a case I have been admitted to, so that I have the full clinical context to formulate a hypothesis.*

**Acceptance Criteria:**
- [ ] I have read access to: clinical summary, patient history, findings, all discussion notes, all hypotheses, and the current ranking
- [ ] I cannot view or access cases I have not been admitted to

---

**US-SP-04 — Submit Structured Hypothesis**  
*As a Specialist, I want to submit a structured diagnostic hypothesis, so that my clinical reasoning is formally recorded with full attribution.*

**Acceptance Criteria:**
- [ ] Hypothesis form has exactly three required fields: proposed diagnosis, clinical rationale, supporting evidence from the case data
- [ ] All three fields are validated server-side; submission with any missing field is rejected
- [ ] Submitted hypothesis is stored with my identity and a server-side UTC timestamp
- [ ] An audit entry (HYPOTHESIS_SUBMITTED) is created
- [ ] Hypothesis appears immediately in the thread visible to all case participants
- [ ] I can submit more than one hypothesis for the same case

---

**US-SP-05 — Add Follow-Up Notes to Hypotheses**  
*As a Specialist, I want to add follow-up notes to my prior hypotheses to modify or withdraw them, so that my evolving clinical reasoning is traceable.*

**Acceptance Criteria:**
- [ ] I can post a follow-up note against a hypothesis
- [ ] A "withdrawn" hypothesis remains visible in the thread history; it is not deleted
- [ ] The note is stored with my identity and a UTC timestamp

---

**US-SP-06 — Post Discussion Notes**  
*As a Specialist, I want to post narrative notes to the case discussion thread, so that I can collaborate asynchronously with other participants.*

**Acceptance Criteria:**
- [ ] I can post to the discussion thread of any case I have been admitted to
- [ ] Notes are displayed with my name and timestamp
- [ ] I cannot post to cases I have not been admitted to

---

**US-SP-07 — View Differential Diagnosis Ranking**  
*As a Specialist, I want to see how the Primary Physician has ranked the submitted hypotheses, so that I understand how my advice has been incorporated.*

**Acceptance Criteria:**
- [ ] I see the ranking pane in read-only mode — no reorder controls available
- [ ] The ranking reflects the latest order set by the Primary Physician
- [ ] My inability to reorder is enforced server-side, not just hidden in the UI

---

**US-SP-08 — Cannot Record Final Decision**  
*As a Specialist, I must be prevented from recording a final clinical decision, so that the advisory boundary is structurally enforced.*

**Acceptance Criteria:**
- [ ] The final decision control is not present in my interface
- [ ] Any direct API/server request to record a decision while logged in as a Specialist is rejected with HTTP 403
- [ ] The rejection is logged in the audit trail as ACCESS_DENIED

---

### 4.3 System / Cross-Cutting

---

**US-SY-01 — Audit on Every Action**  
*As the system, every clinically or security-relevant action must be automatically logged so that no action — including denied ones — is unrecorded.*

**Acceptance Criteria:**
- [ ] Audit entries created for: LOGIN, CASE_CREATED, HYPOTHESIS_SUBMITTED, RANK_UPDATED, DECISION_RECORDED, ACCESS_DENIED
- [ ] Each entry includes: actor_id, action, entity_type, entity_id, case_id, UTC timestamp
- [ ] Ordinary users cannot UPDATE or DELETE audit rows
- [ ] The append-only nature is enforced at DB privilege level, not only at application level

---

**US-SY-02 — Role-Aware Routing**  
*As the system, upon login I must route users to the correct dashboard based on their role, so that each actor sees only what they are permitted to see.*

**Acceptance Criteria:**
- [ ] Primary Physician → owned case dashboard (statuses: open, under review, decided, closed)
- [ ] Specialist → admitted case list

---

**US-SY-03 — LMIC Accessibility**  
*As the system, I must remain usable on low-bandwidth and intermittent connections, so that clinicians in resource-limited settings can participate.*

**Acceptance Criteria:**
- [ ] Page loads < 2.3 s average on throttled 3G
- [ ] No real-time connection assumed; all operations are stateless request/response
- [ ] Interface is textual and low-bandwidth; no heavy client-side JS framework
- [ ] Interface is mobile-responsive

---

**US-SY-04 — Idempotent State-Changing Operations**  
*As the system, state-changing operations must be idempotent so that unreliable connections do not produce duplicate records.*

**Acceptance Criteria:**
- [ ] Re-submitting a hypothesis over an unreliable connection does not produce duplicate hypotheses
- [ ] Discussion notes cannot be silently duplicated by re-submission
- [ ] Each submission is confirmed by an updated page state

---

---

## 5. Gaps, Faults, and Contradictions

> [!CAUTION]
> This section is the most critical for institution-grade software. Items are rated by **Severity**: 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low

---

### 5.1 Critical Gaps

These are missing requirements or design omissions with direct **safety, legal, or governance consequences**.

---

**GAP-01 — No Identity Verification for Clinical Roles** 🔴  
*Location: §1.4, §5.3*

The system takes role declarations at face value. A malicious or mistaken user can register as a "Specialist" or "Primary Physician" with no professional credential check. For an institution-grade clinical governance system, this breaks the entire trust model.

> The document acknowledges this (§5.3) but frames it only as a future recommendation. For a production clinical system this is a **blocking gap**, not a nicety. The governance model (advisee vs. advisor) is meaningless if clinical roles are self-declared and unverified.

**Impact:** Clinical decisions may be recorded by non-physicians; specialist hypotheses may be submitted by unqualified individuals.  
**Missing requirement:** `FR-IDENT-01: The system SHALL verify professional registration/licensure (via licensure databases or institutional SSO) before granting role-based access.`

---

**GAP-02 — No Multi-Factor Authentication (MFA)** 🔴  
*Location: §4.2.2, §2.5.3*

The document references MFA as a key security component for healthcare cloud (§2.5.3: "strictest access controls and multifactor authentication") but the implemented system uses only password-based authentication. MFA is not implemented, not deferred explicitly, and not listed in the requirements gap.

**Impact:** Single-factor compromise = full account takeover = governance falsification.  
**Missing requirement:** `NFR-AUTH-01: The system SHALL support MFA for all user accounts, with enforced MFA for Primary Physician accounts.`

---

**GAP-03 — No Session Timeout / Idle Logout** 🟠  
*Location: §4.2.2*

The document states sessions are managed via HttpOnly + Secure cookies but provides no session expiry mechanism. For a shared or clinical workstation scenario, this allows session hijacking after a clinician walks away.

**Missing requirement:** `NFR-SEC-01: Active sessions SHALL expire after [configurable] minutes of inactivity, requiring re-authentication.`

---

**GAP-04 — No Data Retention or Purge Policy** 🟠  
*Location: §5.3*

Case data, audit logs, and user records accumulate indefinitely with no stated retention or deletion policy. GDPR's right to erasure and HIPAA data retention policies both require explicit policies. The document defers this to "data-retention procedures" in §5.3 without specifying any requirement.

**Missing requirement:** `R-RETENTION-01: The system SHALL implement configurable data-retention schedules per data category (user PII, case records, audit logs) with automated archival or deletion.`

---

**GAP-05 — No Notification or Alerting Mechanism** 🟠  
*Location: §3.2.2, §3.3*

The workflow assumes participants check the platform manually. There is **no requirement** for any email notification, push alert, or in-app notification when:
- A Specialist is admitted to a case
- A new hypothesis is submitted
- A discussion note is posted
- A final decision is recorded

For an **asynchronous** platform serving participants across timezones, this is a critical usability gap. The document's own definition of the problem (reducing delays in complex case diagnosis) is undermined by a design that requires manual polling.

**Missing requirement:** `FR-NOTIFY-01: The system SHALL send notification (at minimum email) to relevant participants upon: case team admission, hypothesis submission, new discussion note, ranking update, and final decision recording.`

---

**GAP-06 — No Password Reset / Recovery Flow** 🟠  
*Location: §4.2.2*

The document describes registration and login but is entirely silent on password recovery. For any multi-user system, the absence of a password reset flow makes accounts permanently inaccessible on forgotten credentials — especially problematic in an asynchronous collaborative system where specialists may access it infrequently.

**Missing requirement:** `FR-AUTH-02: The system SHALL provide a secure password reset mechanism via verified email.`

---

**GAP-07 — No Case Search or Filter** 🟡  
*Location: §4.3.1, §4.3.2*

The dashboard lists cases but no search, filter, or sort capability is described. As case volume grows (even within a prototype evaluation), a flat list becomes unusable.

**Missing requirement:** `FR-CASE-01: The case dashboard SHALL support search by case title and filter by case status.`

---

**GAP-08 — No File/Image Attachment Capability** 🟡  
*Location: §3.2.2, §2.4.2*

The document explicitly mentions that VMTB platforms integrate with PACS (picture archiving) and EHR systems as a barrier. The proposed system ignores all clinical attachments (imaging, lab reports, ECG, pathology). For "complex clinical cases" — the stated target use case — text-only case data is a severe clinical limitation.

**Acknowledged but not tracked:** §2.4.2 notes PACS/EHR integration as a deployment barrier but does not specify even a basic file-upload FR.

**Missing requirement:** `FR-ATTACH-01: The system SHOULD allow Primary Physicians to attach supporting clinical documents (PDF, images) to a case record.`

---

**GAP-09 — No Account Deactivation or Role Management by Admin** 🟡  
*Location: §3.3, §4.2.1*

The document mentions a Django admin interface but provides no requirements for:
- Deactivating a compromised account
- Reassigning case ownership if a physician becomes unavailable
- An administrator role distinct from Primary Physician

**Missing requirement:** `FR-ADMIN-01: An administrator role SHALL be able to deactivate user accounts and reassign case ownership without altering the audit trail.`

---

### 5.2 Functional Faults & Under-specifications

These are requirements stated in the document that are **incomplete, ambiguous, or internally inconsistent** at the level of specification.

---

**FAULT-01 — FR2 "Relevant Findings" field undefined** 🟠  
*Location: §3.2.2 FR2, §4.3.2*

The case creation form includes a "relevant findings" field. The document never specifies what this field contains — is it free text? Is it structured (lab values, vital signs, imaging results)? Is it mandatory? The hypothesis submission (FR3) requires "supporting evidence derived from the case data" but if the case data's "findings" are vague free text, the hypothesis evidence field has nothing structured to reference.

**Correction needed:** FR2 must specify whether `findings` is free-text or structured, its character limits, and whether it is mandatory.

---

**FAULT-02 — FR4 "Authorised participants" ambiguity** 🟠  
*Location: §3.2.2 FR4*

FR4 states "all authorised participants should be able to post narrative notes." In §3.3.1 the Primary Physician "takes part in the discussion thread." In §3.3.2 Specialists add notes. But the RBAC matrix (§3.6.3) scopes discussion posting as:
> "Primary Physician may post about **their own cases** OR the Specialist may post about **admitted cases**."

This is consistent but FR4's "authorised participants" is never explicitly enumerated — the FR should state roles explicitly.

**Correction needed:** FR4 should read: "The Primary Physician (for cases they own) and admitted Specialists (for admitted cases) shall be able to post narrative notes…"

---

**FAULT-03 — FR5 ranking and hypothesis lifecycle mismatch** 🟠  
*Location: §3.2.2 FR5, §4.3.3, §4.3.5*

FR5 says the Primary Physician ranks "all hypotheses submitted." But §4.3.3 says "Specialists are allowed to submit more than one hypothesis" and §4.3.5 refers to "active hypotheses." What happens to a withdrawn hypothesis in the ranking list? Is a withdrawn hypothesis still ranked? Still reorderable? Does it appear in the final differential? This is unspecified.

**Correction needed:** The lifecycle states of a hypothesis (active, withdrawn, superseded) must be defined, and the ranking view must specify how each state is displayed.

---

**FAULT-04 — FR6 "advisory acknowledgement" is one-time but reasoning evolves** 🟡  
*Location: §3.2.2 FR6, §4.3.6*

FR6 requires the Primary Physician to acknowledge the advisory nature of specialist input at the point of recording the final decision. However, if a physician has already submitted a decision and the case is "closed," there is no mechanism for re-opening. The document says this correctly (case cannot be reopened). But what if the Primary Physician prematurely closes a case? There is no requirement for a case re-opening flow or a multi-step review before final decision.

**Missing requirement:** `FR-CASE-02: The Primary Physician SHOULD be able to request that specialists submit additional hypotheses before recording a final decision, without requiring case closure and reopening.`

---

**FAULT-05 — No explicit requirement for case status transitions** 🟡  
*Location: §3.6.2*

The DB model defines four case statuses: `open`, `under_review`, `decided`, `closed`. The document never specifies:
- What triggers the transition from `open` to `under_review`
- Whether `under_review` is automatic (e.g., first hypothesis submitted) or manual
- Whether `decided` and `closed` are the same or distinct states
- Whether the Primary Physician can manually set a status

**Correction needed:** A state machine for case lifecycle transitions must be formally specified.

---

**FAULT-06 — Hypothesis "withdrawal" mechanism never formally specified** 🟡  
*Location: §4.3.3*

§4.3.3 says Specialists can "add follow-up notes to modify or withdraw a previous hypothesis; even withdrawn hypotheses stay visible in the thread history." But the document never formally specifies:
- Whether withdrawal is a distinct action (a "Withdraw" button) or merely a note convention
- Whether a withdrawn hypothesis is marked visually as "WITHDRAWN" in the UI
- Whether the ranking engine treats withdrawn hypotheses differently

This is a functional under-specification that leads to inconsistent implementation.

---

**FAULT-07 — Team admission: no requirement for notification to admitted Specialist** 🟡  
*Location: §4.3.2*

The Primary Physician admits Specialists "by email address" but the system only adds a CaseTeam row. There is no specified mechanism to inform the Specialist that they have been admitted. The admitted Specialist would only discover their admission by manually logging in and checking their case list. This directly undermines the asynchronous collaboration objective.

*(See also GAP-05 — the notification gap)*

---

### 5.3 Contradictions

Directly contradictory statements found between sections of the document:

---

**CONTRA-01 — MFA mentioned as required in literature review, absent in requirements** 🔴  
*Location: §2.5.3 vs. §3.2.3, §4.2.2*

§2.5.3 explicitly lists "multifactor authentication" as a key component of healthcare cloud security: *"Key components involve encrypting transmitted and stored data, the strictest access controls and **multifactor authentication**, audit trails…"*

Yet §3.2.3 (NFR1–NFR8) contains no MFA requirement. §4.2.2 implements only single-factor password auth. The document cites the requirement and then ignores it with no explanation or explicit de-scoping decision.

---

**CONTRA-02 — RBAC described as "de facto standard" but standard RBAC declared insufficient** 🟡  
*Location: §2.5.2 vs. §3.6.3*

§2.5.2 states: *"RBAC has been a de-facto standard method of management of privileges in Healthcare information systems"* but then says: *"Standard role access control models can't meet these needs as it needs more information beyond roles that vary over context of case collaboration."*

§3.6.3 then implements what it calls "case-scoped RBAC" which is essentially an attribute-based element. The document never commits to whether this is RBAC, ABAC, or a hybrid. The term is used inconsistently and the chosen model is never formally named. This is a specification ambiguity that matters for security auditing.

---

**CONTRA-03 — Scope says no HIPAA/GDPR; literature review argues they are essential** 🟡  
*Location: §1.4 vs. §2.5.4, §2.2.2*

§1.4 explicitly states: *"There are no formal arrangements or attempts to reach healthcare regulatory compliance (HIPAA, GDPR)."*  
§2.5.4 states: *"When laws like the United States' HIPAA and Europe's GDPR aren't adhered to, huge sums can be lost, along with patients' confidence."*  
§2.2.2 argues HIPAA compliance must be built in "from first principles."

This is not a contradiction that disqualifies the prototype, but it means the prototype's literature review argues **against** its own implementation choices. A requirements document should either explicitly justify the de-scoping or not cite the regulatory risks as if they are unsolved.

---

**CONTRA-04 — "Global platform" in title vs. explicit LMIC/free-tier constraints** 🟡  
*Location: Title vs. §1.4, NFR5*

The system title is "Secure Cloud-Based Platform for **Global Specialist Collaboration**." NFR5 however explicitly scopes deployment to free-tier infrastructure with memory and compute constraints suitable for "tens of concurrent users." A platform for global specialist collaboration must handle concurrent users at scale; the free-tier spec is appropriate for a prototype but contradicts the "global" claim without explicit qualification.

---

**CONTRA-05 — Testing conducted by developer only, described as "usability" testing** 🟠  
*Location: §1.3, §4.4.4*

Objective 4 of §1.3 states: *"gather and examine… task-completion times, and error rates to assess whether the system… is also usable in practice."* The usability testing (§4.4.4) was performed by the developer/testers themselves on mock clinical scenarios, with no actual clinicians involved (explicitly confirmed in §1.4: *"Practicing clinicians or healthcare organisations do not take part in the evaluation process."*). Calling this "usability testing" is misleading — it is functional verification by the author. True usability testing requires external users.

**Impact on evidence quality:** All performance metrics and error rates are measured by the system builder, not independent clinical users. This significantly reduces the evidential value of the testing claims.

---

**CONTRA-06 — "Idempotent operations" claimed but no formal mechanism specified** 🟡  
*Location: §5.2 (Problems) vs. §3.2.2*

§5.2 (problems encountered) states: *"all operations which changed the state idempotent and subject to server verification."* But there is no FR or NFR that specifies idempotency. It is resolved as an implementation decision only after the problem manifested — this should have been a pre-development NFR.

---

### 5.4 Non-Functional Under-specifications

| ID | Gap | Severity |
|---|---|---|
| NFR-GAP-01 | **No defined SLA or uptime target** — NFR6 (availability) says "managed services with automated backup" but no % availability target is stated | 🟡 |
| NFR-GAP-02 | **No throughput ceiling defined** — NFR5 mentions "tens of concurrent users" but no maximum concurrent session count is tested or formally specified | 🟡 |
| NFR-GAP-03 | **No input field length limits specified** — clinical summaries, rationale, and supporting evidence fields have no stated character limits; no DB column size constraints documented | 🟠 |
| NFR-GAP-04 | **No content moderation or abuse controls** — discussion thread has XSS escaping but no content policy, no moderation, no block/report mechanism | 🟢 |
| NFR-GAP-05 | **No defined backup recovery time objective (RTO) / recovery point objective (RPO)** — NFR6 cites "automated backups" but no RTO/RPO is defined | 🟡 |
| NFR-GAP-06 | **No accessibility (a11y) requirement** — no mention of WCAG compliance; in a clinical system used by professionals this is a regulatory and ethical gap | 🟠 |
| NFR-GAP-07 | **No API rate limiting beyond login** — rate limiting is mentioned for login (§4.2.2) but no rate-limiting on hypothesis submission, discussion posting, or ranking updates | 🟡 |

---

### 5.5 Governance & Ethical Gaps

| ID | Gap | Severity |
|---|---|---|
| ETH-01 | **No consent mechanism for information sharing** — the governance model is silent on whether the Primary Physician must obtain consent from the patient (even synthetic) before sharing case data with multiple specialists | 🔴 |
| ETH-02 | **Specialist participation is voluntary with no tracking of responsiveness** — there is no SLA or timeout for specialist hypothesis submission; a case could remain indefinitely "under review" with no response | 🟠 |
| ETH-03 | **No second-opinion or appeal pathway** — once the Primary Physician records a final decision and closes the case, there is no mechanism for a specialist to flag disagreement or for an error to be corrected | 🟠 |
| ETH-04 | **No safeguard against premature case closure** — nothing prevents a Primary Physician from closing a case with zero specialist hypotheses submitted and the advisory acknowledgement is merely a checkbox | 🟡 |
| ETH-05 | **No conflict-of-interest declaration by Specialists** — a Specialist admitted to a case has no requirement to declare any conflict of interest with the case or patient | 🟡 |
| ETH-06 | **No maximum number of Specialists per case** — theoretically a Primary Physician could admit an unlimited number of Specialists, creating an unmanageable hypothesis set with no governance on team size | 🟢 |

---

## 6. Traceability Matrix

Cross-references between Functional Requirements, User Stories, and System Capabilities:

| FR / NFR | User Stories | Capabilities Delivered |
|---|---|---|
| FR1 | US-PP-01, US-PP-02, US-SP-01, US-SP-02 | C-01, C-02, C-03, C-04, C-05 |
| FR2 | US-PP-03 | C-13 |
| FR2 (team admission) | US-PP-04 | C-14 |
| FR3 | US-SP-04, US-SP-05 | C-16, C-17, C-18 |
| FR4 | US-PP-06, US-SP-06 | C-19 |
| FR5 | US-PP-07, US-PP-08, US-SP-07 | C-20, C-21 |
| FR6 | US-PP-09 | C-22 |
| FR7 | US-SY-01 | C-26, C-27, C-31 |
| FR8 | US-PP-09 | C-22 (modal governance notice) |
| NFR1 | US-PP-02, US-SP-02 | C-05 |
| NFR2 | — | C-02 (PBKDF2), Supabase encryption |
| NFR3 | US-SP-08, US-SY-01 | C-06, C-07, C-08, C-09 |
| NFR4 | US-SY-03 | C-33 (Render distribution) |
| NFR5 | US-SY-03 | C-36, C-37, C-38 |
| NFR6 | — | C-35, C-36 |
| NFR7 | US-SY-03 | C-24, C-25 |
| NFR8 | US-SY-01 | C-26, C-28, C-29, C-30, C-32 |

---

## 7. Risk Register (derived)

| Risk ID | Risk | Likelihood | Impact | Mitigation in doc | Gap |
|---|---|---|---|---|---|
| RISK-01 | Unverified credentials — non-clinician registers as Specialist | High (prototype) | Critical | None | GAP-01 |
| RISK-02 | Account takeover via single-factor auth | Medium | Critical | Rate-limiting only | GAP-02 |
| RISK-03 | Cold-start latency creates poor UX in time-sensitive scenarios | High (free tier) | Medium | Documented as known limitation | Acceptable for prototype |
| RISK-04 | Free-tier connection limit causes DB errors under concurrent load | Medium | High | Connection pooling | NFR-GAP-02 |
| RISK-05 | Audit log overflow — no retention policy | Low (prototype scale) | Medium | None | GAP-04 |
| RISK-06 | Case permanently stuck in "under review" — no Specialist responds | Medium | High | None | ETH-02 |
| RISK-07 | Premature case closure by Primary Physician | Low | Medium | Advisory acknowledgement checkbox only | ETH-04 |
| RISK-08 | Penetration of governance boundary via forged requests | Low (tested) | Critical | Server-side RBAC, denial logging | Tested (FT05, FT08) — penetration test deferred |
| RISK-09 | GDPR/HIPAA regulatory exposure when real data used | High (future) | Critical | Out of scope | GAP entire compliance stack |
| RISK-10 | SQL injection via hypothesis/discussion text fields | Low (Django ORM) | High | Django ORM parameterised queries | Not explicitly tested or stated as a requirement |

---

*End of Requirements Analysis*  
*Document cross-referenced against: DOPA COMPLETE.docx (537 lines, 121,864 characters)*
