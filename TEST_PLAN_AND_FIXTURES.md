# Quality Assurance Test Plan & Clinical Fixtures — DOPA Platform

This document specifies the verification criteria, the formal functional test suite (**FT01–FT11**), security penetration vectors, and the 3 clinical test fixtures derived from **Appendix A** of the system thesis.

---

## 1. Functional Test Matrix (FT01–FT11)

All 11 functional tests from Table 4.2 of the project thesis are formally automated as regression tests.

| Test ID | Test Scenario | Preconditions | Execution Steps | Expected HTTP & UI Result | Expected DB State & Audit Entry |
|---|---|---|---|---|---|
| **FT01** | Register with role = `PRIMARY_PHYSICIAN` | Anonymous user | POST to `/accounts/register/` with valid details and role `PRIMARY_PHYSICIAN`. | HTTP 302 redirect to dashboard; success banner. | User record created with role `PRIMARY_PHYSICIAN`. Role immutable. |
| **FT02** | Login with valid credentials | User exists (FT01) | POST valid email and password to `/accounts/login/`. | HTTP 302 redirect to dashboard; session cookie issued (`HttpOnly`, `Secure`). | Audit record logged: `LOGIN_SUCCESS`. |
| **FT03** | Access dashboard without authentication | Anonymous user | GET request to `/dashboard/`. | HTTP 302 redirect to `/accounts/login/?next=/dashboard/`. Zero case data exposed. | No state change. |
| **FT04** | Primary Physician creates a case | Logged in as Primary Phys | POST valid title, summary, history, findings to `/cases/create/`. | HTTP 302 redirect to `/cases/<case_id>/workspace/`. | Case row created with `owner=user`, `status=OPEN`. Audit record: `CASE_CREATED`. |
| **FT05** | Specialist attempts case creation | Logged in as Specialist | POST valid case form to `/cases/create/`. | HTTP 403 Forbidden page returned. | Case NOT created. Audit record logged: `ACCESS_DENIED`. |
| **FT06** | Admitted specialist submits structured hypothesis | Specialist admitted to `CaseTeam` | POST proposed diagnosis, rationale, supporting evidence to `/cases/<case_id>/hypotheses/create/`. | HTTP 302 redirect to workspace; hypothesis card appears. | Hypothesis row created; case status transitions to `UNDER_REVIEW`. Audit: `HYPOTHESIS_SUBMITTED`. |
| **FT06b**| Non-admitted specialist submits hypothesis | Specialist NOT in `CaseTeam` | POST hypothesis data to `/cases/<case_id>/hypotheses/create/`. | HTTP 403 Forbidden page returned. | Hypothesis NOT created. Audit record logged: `ACCESS_DENIED`. |
| **FT07** | Primary Physician reorders differential ranking | Multiple active hypotheses | POST reorder instruction (`direction=UP`) to `/cases/<case_id>/ranking/reorder/`. | HTTP 302 redirect to workspace; ranking list reordered. | `DiagnosisRanking` rows updated with swapped `rank_position`. Audit: `RANK_UPDATED`. |
| **FT08** | Specialist attempts final decision recording | Logged in as Specialist | POST decision payload to `/cases/<case_id>/decision/record/`. | HTTP 403 Forbidden page returned. | Decision NOT created; case remains `UNDER_REVIEW`. Audit: `ACCESS_DENIED`. |
| **FT09** | Decision submission without advisory acknowledgement | Logged in as Case Owner | POST decision payload with `advisory_acknowledged=False`. | HTTP 400 Bad Request; validation alert highlights unchecked governance box. | Decision NOT created. Case remains `UNDER_REVIEW`. |
| **FT10** | Decision submission with acknowledgement on owned case | Logged in as Case Owner | POST decision with `advisory_acknowledged=True` and diagnosis. | HTTP 302 redirect to workspace; workspace locked in read-only archive mode. | `Decision` row persisted; `Case.status` set to `CLOSED`. Audit: `DECISION_RECORDED`. |
| **FT11** | Audit trail review for completed case | Case completed (FT10) | GET `/cases/<case_id>/audit/` as Case Owner or Team Specialist. | HTTP 200 OK; chronological audit log table rendered. | Displays full event sequence including both successful actions and any `ACCESS_DENIED` attempts. |
| **FT12** | Diagnostic media upload by Case Owner (FR2b) | Logged in as Primary Phys | POST valid JPEG/PNG/WebP/PDF to `/cases/<case_id>/attachments/upload/`. | HTTP 302 redirect to workspace; file listed in Pane 1. | `CaseAttachment` row created; file stored in private media directory; Audit: `ATTACHMENT_UPLOADED`. |
| **FT13** | Diagnostic media secure streaming (FR2d) | Specialist in `CaseTeam` | GET `/cases/<case_id>/attachments/<attachment_id>/`. | HTTP 200 OK with binary stream and verified MIME header. | File streams inline; unadmitted users receive HTTP 403 Forbidden; Audit: `ATTACHMENT_ACCESSED`. |
| **FT14** | Structured clinical findings & vitals decomposition (FR2c) | Case Owner or Admitted Specialist | POST vitals and structured lab panel; verify workspace rendering and evidence citations. | HTTP 302 redirect / HTTP 200 OK; vitals ribbon & lab table rendered in Pane 1. | `Case` vitals persisted; `CaseLabResult` rows created; click-to-cite action formats evidence into Pane 2; Audit: `FINDINGS_UPDATED`. |
| **FT15** | Clinical consultation report & audit dossier export | Case Owner or Admitted Specialist | GET `/cases/<case_id>/report/` (HTML & JSON formats). | HTTP 200 OK; renders comprehensive printable dossier; JSON returns full clinical payload. | Unadmitted users receive HTTP 403 Forbidden; Audit: `REPORT_GENERATED`. |

---

## 2. Security & RBAC Penetration Scenarios

The test suite includes automated negative security assertions:

1. **Privilege Escalation via Form Tampering**:
   - An authenticated user attempts to change their role via a forged POST request to profile endpoints.
   - *Pass Criteria*: Role modification is rejected; user remains in their registered role.

2. **Direct Object Reference (IDOR) on Workspace**:
   - A Specialist attempts to access the workspace of a case they were never admitted to.
   - *Pass Criteria*: Returns `HTTP 403 Forbidden`, no case details leaked, `ACCESS_DENIED` entry recorded.

3. **Re-Submission of Final Decision on Closed Case**:
   - A Primary Physician attempts to submit a second decision for a case that is already marked `CLOSED`.
   - *Pass Criteria*: Rejected by application logic with `HTTP 403` and blocked by DB `UNIQUE(case_id)` constraint on `cases_decision`. Existing decision remains untouched.

4. **Cross-Site Scripting (XSS) in Discussion Thread**:
   - A participant submits a note containing `<script>alert('xss')</script>`.
   - *Pass Criteria*: Django template engine escapes characters (`&lt;script&gt;...`), script does not execute in DOM.

---

## 3. Clinical Test Fixtures (Appendix A Scenarios)

These three synthetic clinical scenarios are provided as test fixtures (`fixtures/clinical_cases.json`) to validate real-world workflows end-to-end.

### Clinical Scenario 1: Multi-System Fever, Joint Pain & Rash
- **Presenting Case**:
  - **Title**: Multi-system Presentation of Recurrent High Fever, Arthralgia, and Salmon-Colored Rash
  - **Primary Physician**: Dr. O. Bassey (Internal Medicine)
  - **Clinical Summary**: A 28-year-old female presents with daily quotidian fevers spiking up to 39.5°C over 4 weeks, symmetrical migratory arthralgia affecting wrists and knees, and an evanescent salmon-pink macular rash on the trunk appearing during fever spikes.
  - **History**: No prior autoimmune disease; no recent travel; no tick exposure; antibiotics had no effect.
  - **Findings**:
    - *Vitals*: Temp 39.4°C, HR 108 bpm, BP 115/75 mmHg.
    - *Labs*: Leukocytosis (WBC 18.5 $\times 10^9$/L, 88% neutrophils), Ferritin 4,200 ng/mL (dramatically elevated), ESR 85 mm/hr, CRP 120 mg/L, ANA negative, Rheumatoid Factor negative, blood cultures $\times 3$ negative.
    - *Imaging*: Hepatosplenomegaly on abdominal ultrasound.
  - **Admitted Specialists**:
    - Dr. A. Bello (Rheumatology)
    - Dr. E. Okafor (Dermatology)
- **Submitted Hypotheses**:
  1. *Hypothesis 1 (Rheumatology)*: **Adult-Onset Still's Disease (AOSD)**.
     - *Rationale*: Quotidian fevers, evanescent non-pruritic salmon rash coinciding with fever spikes, extreme hyperferritinemia (>4,000 ng/mL), negative ANA/RF strongly fulfill Yamaguchi criteria.
     - *Supporting Evidence*: Ferritin 4,200 ng/mL, WBC 18.5 with neutrophilia, negative blood cultures.
  2. *Hypothesis 2 (Dermatology)*: **Systemic Lupus Erythematosus (SLE)**.
     - *Rationale*: Young female presenting with systemic fever, arthralgia, and rash; need to exclude atypical ANA-negative SLE variant.
     - *Supporting Evidence*: Symmetrical polyarthralgia and cutaneous involvement.
- **Expected Differential Ranking**:
  1. Adult-Onset Still's Disease (AOSD)
  2. Systemic Lupus Erythematosus (SLE)
- **Final Decision**: Adult-Onset Still's Disease; initiate high-dose corticosteroids after infectious disease clearance.

---

### Clinical Scenario 2: Refractory Chronic Microcytic Anaemia
- **Presenting Case**:
  - **Title**: Refractory Severe Microcytic Hypochromic Anaemia in a Middle-Aged Male
  - **Primary Physician**: Dr. M. Adeyemi (General Practice)
  - **Clinical Summary**: A 52-year-old male presents with profound fatigue, exertional dyspnoea, and pallor unresponsive to 6 months of oral iron supplementation.
  - **History**: Denies overt gastrointestinal bleeding, hematochezia, or melena. No family history of hemoglobinopathy.
  - **Findings**:
    - *Vitals*: HR 96 bpm, BP 125/80 mmHg.
    - *Labs*: Hb 7.2 g/dL, MCV 64 fL (profound microcytosis), Ferritin 12 ng/mL (low), Serum Iron 20 $\mu$g/dL, Total Iron Binding Capacity 450 $\mu$g/dL. Stool occult blood positive $\times 2$.
    - *Diagnostics*: Upper endoscopy unremarkable; initial colonoscopy revealed minor non-bleeding diverticula.
  - **Admitted Specialists**:
    - Dr. K. Ibrahim (Gastroenterology)
    - Dr. C. Nwosu (Haematology)
- **Submitted Hypotheses**:
  1. *Hypothesis 1 (Gastroenterology)*: **Occult Small-Bowel Angiodysplasia / Vascular Ectasia**.
     - *Rationale*: Persistent iron-deficiency anaemia with positive occult blood and negative bidirectional endoscopy suggests mid-gut bleeding inaccessible to standard endoscopes.
     - *Supporting Evidence*: Refractory iron deficiency, positive fecal occult blood, normal colonoscopy.
  2. *Hypothesis 2 (Haematology)*: **Celiac Disease with Duodenal Malabsorption**.
     - *Rationale*: Severe failure of oral iron absorption can indicate blunted enterocyte transport from gluten enteropathy even without classic diarrhea.
     - *Supporting Evidence*: Complete failure of oral iron response over 6-month trial.
- **Expected Differential Ranking**:
  1. Occult Small-Bowel Angiodysplasia (Indication for Video Capsule Endoscopy)
  2. Celiac Disease (Indication for Anti-tTG IgA serology)
- **Final Decision**: Occult gastrointestinal bleeding secondary to suspected small bowel angiodysplasia; proceed with video capsule endoscopy.

---

### Clinical Scenario 3: Pediatric Episodic Unresponsiveness
- **Presenting Case**:
  - **Title**: Episodic Staring and Unresponsiveness in an 8-Year-Old Child
  - **Primary Physician**: Dr. R. Danjuma (Pediatrics)
  - **Clinical Summary**: An 8-year-old boy presents with daily brief episodes (5–15 seconds) of vacant staring and speech interruption noted by classroom teachers, occurring 10 to 20 times daily.
  - **History**: Normal developmental milestones; no aura; immediate recovery without post-ictal confusion.
  - **Findings**:
    - *Vitals*: Normal pediatric ranges.
    - *Neurological Exam*: Cranial nerves intact, normal tone and reflexes. Hyperventilation during clinical exam reliably precipitates a 10-second staring spell.
    - *Diagnostics*: Resting routine 20-minute EEG captured during clinic visit.
  - **Admitted Specialists**:
    - Dr. F. Taiwo (Pediatric Neurology)
- **Submitted Hypotheses**:
  1. *Hypothesis 1 (Pediatric Neurology)*: **Childhood Absence Epilepsy (CAE)**.
     - *Rationale*: Classic age of onset, multiple daily brief staring spells without post-ictal state, and immediate precipitation by hyperventilation is pathognomonic for CAE.
     - *Supporting Evidence*: Hyperventilation trigger in clinic; sudden onset and offset of episodes.
  2. *Hypothesis 2 (Pediatric Neurology)*: **Behavioral Inattention / Absence Mimic (Stereotypies)**.
     - *Rationale*: Differential must consider non-epileptic daydreaming or attention-deficit phenomena, though responsiveness to tactile stimuli typically differentiates this.
     - *Supporting Evidence*: Normal baseline neurological development.
- **Expected Differential Ranking**:
  1. Childhood Absence Epilepsy (CAE)
  2. Behavioral Inattention
- **Final Decision**: Childhood Absence Epilepsy confirmed; initiate first-line ethosuximide therapy with outpatient EEG confirmation.

---

## 4. Test Execution Instructions

To execute the test suite in the Django development environment:

```bash
# Run the entire functional test suite
python manage.py test tests.test_functional

# Run security and RBAC penetration tests
python manage.py test tests.test_rbac_security

# Load the clinical test fixtures from Appendix A
python manage.py loaddata fixtures/clinical_cases.json
```
