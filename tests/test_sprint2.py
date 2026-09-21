import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from cases.models import Case, CaseTeam, CaseStatus, Notification
from audit.models import AuditLog, AuditAction, AuditStatus


class Sprint2CaseManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Primary Physicians
        self.physician = User.objects.create_user(
            email='dr.owner@hospital.org',
            full_name='Dr. Olivia Owner',
            role=Role.PRIMARY_PHYSICIAN,
            password='PhysicianPassword123!'
        )
        self.other_physician = User.objects.create_user(
            email='dr.other@hospital.org',
            full_name='Dr. Other Doctor',
            role=Role.PRIMARY_PHYSICIAN,
            password='PhysicianPassword123!'
        )

        # Specialists
        self.specialist1 = User.objects.create_user(
            email='dr.rheum@specialist.org',
            full_name='Dr. Rachel Rheum',
            role=Role.SPECIALIST,
            password='SpecialistPassword123!'
        )
        self.specialist2 = User.objects.create_user(
            email='dr.derm@specialist.org',
            full_name='Dr. David Derm',
            role=Role.SPECIALIST,
            password='SpecialistPassword123!'
        )
        self.unadmitted_specialist = User.objects.create_user(
            email='dr.unadmitted@specialist.org',
            full_name='Dr. Unknown Specialist',
            role=Role.SPECIALIST,
            password='SpecialistPassword123!'
        )

        self.valid_case_payload = {
            'title': 'Undifferentiated Autoimmune Presentation with Quotidian Fever',
            'clinical_summary': 'A 34-year-old female presents with 3 weeks of high spiking fevers, evanescent salmon rash, and polyarthralgia.',
            'history': 'Previously healthy with no significant family history. No tick bite, no foreign travel, unresponsive to empirical amoxicillin.',
            'findings': '### Vitals: Temp 39.2C, HR 105, BP 118/74\n### Labs: WBC 18.2, Ferritin 4500 ng/mL, CRP 115 mg/L\n### Imaging: Mild splenomegaly'
        }

    # -------------------------------------------------------------------------
    # FT04: Primary Physician creates a case
    # -------------------------------------------------------------------------
    def test_ft04_primary_physician_creates_case_and_audit(self):
        """
        FT04: Primary physician creates a case.
        Case persisted with owner recorded; status initialized to OPEN; audit entry written.
        """
        self.client.force_login(self.physician)
        create_url = reverse('cases:case_create')

        response = self.client.post(create_url, self.valid_case_payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify case created in database
        case = Case.objects.filter(title=self.valid_case_payload['title']).first()
        self.assertIsNotNone(case)
        self.assertEqual(case.owner, self.physician)
        self.assertEqual(case.status, CaseStatus.OPEN)
        self.assertTrue(case.is_open)

        # Verify redirected to team admission
        expected_team_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        self.assertRedirects(response, expected_team_url)

        # Verify CASE_CREATED audit log
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.CASE_CREATED,
            actor=self.physician,
            case_id=case.id,
            status=AuditStatus.ALLOWED
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.entity_type, 'cases_case')
        self.assertEqual(audit_entry.entity_id, str(case.id))

    # -------------------------------------------------------------------------
    # FT05: Specialist attempts case creation (HTTP 403 Denial)
    # -------------------------------------------------------------------------
    def test_ft05_specialist_attempts_case_creation_denied_and_logged(self):
        """
        FT05: Specialist attempts case creation.
        Action denied (HTTP 403); zero cases created; denial logged as ACCESS_DENIED.
        """
        self.client.force_login(self.specialist1)
        create_url = reverse('cases:case_create')

        response = self.client.post(create_url, self.valid_case_payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Case.objects.count(), 0)

        # Verify ACCESS_DENIED audit log
        audit_denial = AuditLog.objects.filter(
            action=AuditAction.ACCESS_DENIED,
            actor=self.specialist1,
            status=AuditStatus.DENIED
        ).first()
        self.assertIsNotNone(audit_denial)
        self.assertIn('Role SPECIALIST not in allowed roles', audit_denial.details.get('reason', ''))

    # -------------------------------------------------------------------------
    # Specialist Team Admission Workflow
    # -------------------------------------------------------------------------
    def test_specialist_team_admission_valid_flow(self):
        """Primary Physician admits Specialist by email: creates CaseTeam, Notification, and AuditLog."""
        self.client.force_login(self.physician)
        case = Case.objects.create(
            owner=self.physician,
            title='Chronic Refractory Microcytic Anaemia',
            clinical_summary='Elderly male with iron deficiency refractory to supplementation.',
            history='No overt melena or hematochezia.',
            findings='Hb 7.5 g/dL, Ferritin 8 ng/mL, FOBT positive.'
        )

        admit_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        payload = {'specialist_email': self.specialist1.email}

        response = self.client.post(admit_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify CaseTeam membership persisted
        membership = CaseTeam.objects.filter(case=case, specialist=self.specialist1).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.admitted_by, self.physician)

        # Verify Notification dispatched to specialist
        notif = Notification.objects.filter(recipient=self.specialist1, case=case).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.verb, 'TEAM_ADMISSION')
        self.assertIn(case.title, notif.message)
        self.assertFalse(notif.is_read)

        # Verify SPECIALIST_ADMITTED audit entry
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.SPECIALIST_ADMITTED,
            actor=self.physician,
            case_id=case.id,
            status=AuditStatus.ALLOWED
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details.get('specialist_email'), self.specialist1.email)

    def test_admitting_primary_physician_as_specialist_rejected(self):
        """Attempting to admit a Primary Physician as an advisory specialist is rejected (G-08)."""
        self.client.force_login(self.physician)
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)

        admit_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        # Attempt to admit another Primary Physician
        payload = {'specialist_email': self.other_physician.email}

        response = self.client.post(admit_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response,
            'form',
            'specialist_email',
            f"Account '{self.other_physician.full_name}' is registered as a Primary Physician. "
            "Only clinicians with the Specialist role can be admitted to advisory case teams (G-08)."
        )
        self.assertEqual(CaseTeam.objects.count(), 0)

    def test_admitting_non_existent_email_rejected(self):
        """Attempting to admit an unregistered email returns an error."""
        self.client.force_login(self.physician)
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)

        admit_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        payload = {'specialist_email': 'ghost.clinician@notfound.org'}

        response = self.client.post(admit_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'specialist_email', 'No registered clinician account found with this email address.')

    def test_duplicate_specialist_admission_rejected(self):
        """Cannot admit the same specialist twice to the same case."""
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)
        CaseTeam.objects.create(case=case, specialist=self.specialist1, admitted_by=self.physician)

        self.client.force_login(self.physician)
        admit_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        payload = {'specialist_email': self.specialist1.email}

        response = self.client.post(admit_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'specialist_email', f"Dr. {self.specialist1.full_name} is already an admitted member of this case team.")

    # -------------------------------------------------------------------------
    # RBAC Enforcement on Case Ownership & Detail
    # -------------------------------------------------------------------------
    def test_non_owner_physician_cannot_admit_team(self):
        """A physician cannot admit team members to a case they do not own."""
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)

        self.client.force_login(self.other_physician)
        admit_url = reverse('cases:team_admit', kwargs={'case_id': case.id})
        response = self.client.post(admit_url, {'specialist_email': self.specialist1.email})
        self.assertEqual(response.status_code, 403)

        # Audit denial logged
        denial = AuditLog.objects.filter(action=AuditAction.ACCESS_DENIED, actor=self.other_physician).first()
        self.assertIsNotNone(denial)

    def test_unadmitted_specialist_cannot_view_case_detail(self):
        """A specialist who is NOT admitted to a case cannot view its details."""
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)

        self.client.force_login(self.unadmitted_specialist)
        detail_url = reverse('cases:case_detail', kwargs={'case_id': case.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 403)

        # Denial logged
        denial = AuditLog.objects.filter(action=AuditAction.ACCESS_DENIED, actor=self.unadmitted_specialist).first()
        self.assertIsNotNone(denial)

    def test_admitted_specialist_can_view_case_detail(self):
        """An admitted specialist can access case details."""
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)
        CaseTeam.objects.create(case=case, specialist=self.specialist1, admitted_by=self.physician)

        self.client.force_login(self.specialist1)
        detail_url = reverse('cases:case_detail', kwargs={'case_id': case.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, case.title)

    # -------------------------------------------------------------------------
    # Dashboard Role Scoping, Filtering & Search
    # -------------------------------------------------------------------------
    def test_dashboard_query_scoping_by_role(self):
        """Primary Physician sees only owned cases; Specialist sees only admitted cases."""
        # Case 1: Owned by physician, specialist1 admitted
        case1 = Case.objects.create(owner=self.physician, title='Case 1 - Rheumatology', **{k: v for k, v in self.valid_case_payload.items() if k != 'title'})
        CaseTeam.objects.create(case=case1, specialist=self.specialist1, admitted_by=self.physician)

        # Case 2: Owned by other_physician, specialist2 admitted
        case2 = Case.objects.create(owner=self.other_physician, title='Case 2 - Dermatology', **{k: v for k, v in self.valid_case_payload.items() if k != 'title'})
        CaseTeam.objects.create(case=case2, specialist=self.specialist2, admitted_by=self.other_physician)

        # 1. Check Primary Physician view
        self.client.force_login(self.physician)
        response = self.client.get(reverse('cases:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Case 1 - Rheumatology')
        self.assertNotContains(response, 'Case 2 - Dermatology')

        # 2. Check Specialist 1 view
        self.client.force_login(self.specialist1)
        response = self.client.get(reverse('cases:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Case 1 - Rheumatology')
        self.assertNotContains(response, 'Case 2 - Dermatology')

        # 3. Check Specialist 2 view
        self.client.force_login(self.specialist2)
        response = self.client.get(reverse('cases:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Case 2 - Dermatology')
        self.assertNotContains(response, 'Case 1 - Rheumatology')

    def test_dashboard_status_filtering_and_keyword_search(self):
        """Test status filtering and title/summary keyword search."""
        c_open = Case.objects.create(owner=self.physician, title='Lupus Diagnostic Quandary', status=CaseStatus.OPEN, **{k: v for k, v in self.valid_case_payload.items() if k != 'title'})
        c_review = Case.objects.create(owner=self.physician, title='Still Disease Under Deliberation', status=CaseStatus.UNDER_REVIEW, **{k: v for k, v in self.valid_case_payload.items() if k != 'title'})

        self.client.force_login(self.physician)

        # Status filter = OPEN
        res_open = self.client.get(f"{reverse('cases:dashboard')}?status=OPEN")
        self.assertContains(res_open, 'Lupus Diagnostic Quandary')
        self.assertNotContains(res_open, 'Still Disease Under Deliberation')

        # Status filter = UNDER_REVIEW
        res_review = self.client.get(f"{reverse('cases:dashboard')}?status=UNDER_REVIEW")
        self.assertContains(res_review, 'Still Disease Under Deliberation')
        self.assertNotContains(res_review, 'Lupus Diagnostic Quandary')

        # Keyword search = 'Lupus'
        res_search = self.client.get(f"{reverse('cases:dashboard')}?q=Lupus")
        self.assertContains(res_search, 'Lupus Diagnostic Quandary')
        self.assertNotContains(res_search, 'Still Disease Under Deliberation')

    # -------------------------------------------------------------------------
    # Model Constraint Checks
    # -------------------------------------------------------------------------
    def test_specialist_cannot_own_case_model_validation(self):
        """Model clean() rejects a specialist as owner."""
        case = Case(owner=self.specialist1, **self.valid_case_payload)
        with self.assertRaises(ValidationError):
            case.full_clean()

    def test_physician_cannot_be_in_caseteam_model_validation(self):
        """Model clean() rejects a primary physician in CaseTeam."""
        case = Case.objects.create(owner=self.physician, **self.valid_case_payload)
        membership = CaseTeam(case=case, specialist=self.other_physician)
        with self.assertRaises(ValidationError):
            membership.full_clean()
