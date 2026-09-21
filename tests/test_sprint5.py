import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.models import Role
from cases.models import Case, CaseTeam, CaseStatus, DiagnosisRanking, Decision
from collaboration.models import Hypothesis, HypothesisStatus, DiscussionNote
from audit.models import AuditLog, AuditAction, AuditStatus
from audit.services import log_event

User = get_user_model()


class Sprint5AuditTrailAndFixturesTests(TestCase):
    """
    Automated test suite for Sprint 5:
    - FT11: Forensic Audit Trail View (/cases/<case_id>/audit/)
    - RBAC & Access Gating for Audit Trail (Case Owner & Admitted Specialists allowed, others 403 + ACCESS_DENIED)
    - Forensic Integrity: Chronological ordering, payload preservation, and inclusion of ACCESS_DENIED attempts
    - Read-Only Enforcement (HTTP 405 on POST/PUT/DELETE)
    - Clinical Data Fixture Seeding (Appendix A Scenarios 1, 2, 3)
    """

    def setUp(self):
        self.client = Client()

        # Primary Physicians
        self.physician_owner = User.objects.create_user(
            email='attending.owner@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Marcus Welby',
            role=Role.PRIMARY_PHYSICIAN
        )
        self.physician_other = User.objects.create_user(
            email='physician.intruder@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Gregory House',
            role=Role.PRIMARY_PHYSICIAN
        )

        # Specialists
        self.specialist_admitted = User.objects.create_user(
            email='neuro.specialist@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Lisa Sanders',
            role=Role.SPECIALIST
        )
        self.specialist_unadmitted = User.objects.create_user(
            email='unadmitted.specialist@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Eric Foreman',
            role=Role.SPECIALIST
        )

        # Create Test Case
        self.case = Case.objects.create(
            owner=self.physician_owner,
            title='Rapid Neuro-Cognitive Decline in 48-Year-Old Male',
            clinical_summary='Subacute cognitive impairment, myoclonus, ataxia over 6 weeks.',
            history='Previously healthy, no toxic exposure, no infectious prodrome.',
            findings='Periodic sharp-wave complexes on EEG, elevated 14-3-3 protein in CSF.',
            status=CaseStatus.UNDER_REVIEW
        )
        log_event(
            action=AuditAction.CASE_CREATED,
            actor=self.physician_owner,
            case_id=self.case.id,
            entity_type='cases_case',
            entity_id=str(self.case.id),
            details={'title': self.case.title}
        )

        # Admit Specialist
        self.membership = CaseTeam.objects.create(
            case=self.case,
            specialist=self.specialist_admitted,
            admitted_by=self.physician_owner
        )
        log_event(
            action=AuditAction.SPECIALIST_ADMITTED,
            actor=self.physician_owner,
            case_id=self.case.id,
            entity_type='cases_caseteam',
            entity_id=str(self.membership.id),
            details={'specialist_email': self.specialist_admitted.email}
        )

        # Submit Hypothesis
        self.hypothesis = Hypothesis.objects.create(
            case=self.case,
            specialist=self.specialist_admitted,
            proposed_diagnosis='Sporadic Creutzfeldt-Jakob Disease (sCJD)',
            rationale='Rapidly progressive dementia with myoclonus and periodic sharp wave complexes on EEG.',
            supporting_evidence='CSF 14-3-3 positive, cortical ribboning on diffusion-weighted MRI.',
            status=HypothesisStatus.ACTIVE
        )
        log_event(
            action=AuditAction.HYPOTHESIS_SUBMITTED,
            actor=self.specialist_admitted,
            case_id=self.case.id,
            entity_type='collaboration_hypothesis',
            entity_id=str(self.hypothesis.id),
            details={'proposed_diagnosis': self.hypothesis.proposed_diagnosis}
        )

        # Discussion Note
        self.note = DiscussionNote.objects.create(
            case=self.case,
            author=self.physician_owner,
            body='Has an RT-QuIC CSF assay been dispatched to the national prion laboratory?'
        )
        log_event(
            action=AuditAction.DISCUSSION_POSTED,
            actor=self.physician_owner,
            case_id=self.case.id,
            entity_type='collaboration_discussionnote',
            entity_id=str(self.note.id),
            details={'snippet': self.note.body[:50]}
        )

    # -------------------------------------------------------------------------
    # FT11: Authorized Audit Trail Reviews
    # -------------------------------------------------------------------------
    def test_ft11_case_owner_views_chronological_audit_trail(self):
        """
        FT11: Primary Physician (Case Owner) accesses /cases/<case_id>/audit/
        and views the chronological forensic log of all events.
        """
        self.client.login(email='attending.owner@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cases/audit_trail.html')

        # Check case title and key metrics
        self.assertContains(response, self.case.title)
        self.assertContains(response, 'Forensic Audit Trail')
        self.assertContains(response, 'Append-Only Forensic Integrity Guaranteed')
        self.assertContains(response, 'Dr. Marcus Welby')

        # Verify all chronological action badges are rendered
        self.assertContains(response, 'Case Created')
        self.assertContains(response, 'Specialist Admitted')
        self.assertContains(response, 'Hypothesis Submitted')
        self.assertContains(response, 'Discussion Posted')

        # Verify context variables
        self.assertTrue(response.context['is_case_owner'])
        self.assertFalse(response.context['is_team_member'])
        self.assertGreaterEqual(response.context['total_events'], 4)
        self.assertGreaterEqual(response.context['allowed_count'], 4)
        self.assertEqual(response.context['denied_count'], 0)

    def test_ft11_admitted_specialist_views_audit_trail(self):
        """
        FT11: Admitted specialist on the CaseTeam accesses /cases/<case_id>/audit/
        and views the audit trail.
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cases/audit_trail.html')

        # Context assertions
        self.assertFalse(response.context['is_case_owner'])
        self.assertTrue(response.context['is_team_member'])
        self.assertContains(response, 'neuro.specialist@clinic.org')
        self.assertContains(response, 'Sporadic Creutzfeldt-Jakob Disease (sCJD)')

    # -------------------------------------------------------------------------
    # Negative Security Assertions: Unauthorized Access Denials & Audit Logging
    # -------------------------------------------------------------------------
    def test_unadmitted_specialist_denied_from_audit_trail_with_403_and_audit(self):
        """
        Non-admitted specialist attempts to access /cases/<case_id>/audit/:
        Returns HTTP 403 Forbidden and logs an ACCESS_DENIED audit record.
        """
        self.client.login(email='unadmitted.specialist@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})

        denials_before = AuditLog.objects.filter(
            case_id=self.case.id,
            action=AuditAction.ACCESS_DENIED,
            actor=self.specialist_unadmitted
        ).count()

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        denials_after = AuditLog.objects.filter(
            case_id=self.case.id,
            action=AuditAction.ACCESS_DENIED,
            actor=self.specialist_unadmitted
        ).count()

        self.assertEqual(denials_after, denials_before + 1)
        latest_log = AuditLog.objects.filter(case_id=self.case.id).latest('timestamp')
        self.assertEqual(latest_log.action, AuditAction.ACCESS_DENIED)
        self.assertEqual(latest_log.status, AuditStatus.DENIED)

    def test_non_owner_physician_denied_from_audit_trail_with_403_and_audit(self):
        """
        Physician who does NOT own the case attempts to access /cases/<case_id>/audit/:
        Returns HTTP 403 Forbidden and logs an ACCESS_DENIED audit record.
        """
        self.client.login(email='physician.intruder@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        latest_log = AuditLog.objects.filter(case_id=self.case.id).latest('timestamp')
        self.assertEqual(latest_log.action, AuditAction.ACCESS_DENIED)
        self.assertEqual(latest_log.actor, self.physician_other)
        self.assertEqual(latest_log.status, AuditStatus.DENIED)

    def test_unauthenticated_user_redirected_to_login(self):
        """
        Anonymous user is redirected to login page.
        """
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    # -------------------------------------------------------------------------
    # Forensic Integrity: Audit Trail Shows Both Successes and Security Denials
    # -------------------------------------------------------------------------
    def test_audit_trail_renders_access_denied_security_attempts(self):
        """
        Verifies that when an unauthorized user is rejected, that ACCESS_DENIED attempt
        is visibly presented in the audit trail when viewed by the Case Owner (FT11).
        """
        # 1. Trigger unauthorized attempt by Dr. House
        self.client.login(email='physician.intruder@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})
        res_intruder = self.client.get(url)
        self.assertEqual(res_intruder.status_code, 403)

        # 2. Case Owner logs in and checks audit trail
        self.client.login(email='attending.owner@clinic.org', password='StrongPassword123!')
        res_owner = self.client.get(url)
        self.assertEqual(res_owner.status_code, 200)

        # 3. Assert ACCESS_DENIED badge and violator info are rendered in the table
        self.assertContains(res_owner, 'Access Denied')
        self.assertContains(res_owner, 'DENIED')
        self.assertContains(res_owner, 'physician.intruder@clinic.org')
        self.assertEqual(res_owner.context['denied_count'], 1)

    # -------------------------------------------------------------------------
    # Read-Only Enforcement (FR7, NFR8)
    # -------------------------------------------------------------------------
    def test_audit_trail_endpoint_is_strictly_read_only(self):
        """
        Audit trail does not accept POST, PUT, or DELETE mutations.
        Returns HTTP 405 Method Not Allowed.
        """
        self.client.login(email='attending.owner@clinic.org', password='StrongPassword123!')
        url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})

        post_res = self.client.post(url, {'some': 'tamper'})
        self.assertEqual(post_res.status_code, 405)

        delete_res = self.client.delete(url)
        self.assertEqual(delete_res.status_code, 405)

    # -------------------------------------------------------------------------
    # UI Links Integration
    # -------------------------------------------------------------------------
    def test_workspace_and_case_detail_contain_audit_trail_links(self):
        """
        Verifies that workspace.html and case_detail.html provide clickable links to audit trail.
        """
        self.client.login(email='attending.owner@clinic.org', password='StrongPassword123!')

        ws_url = reverse('cases:workspace', kwargs={'case_id': self.case.id})
        ws_res = self.client.get(ws_url)
        self.assertEqual(ws_res.status_code, 200)
        audit_url = reverse('cases:audit_trail', kwargs={'case_id': self.case.id})
        self.assertContains(ws_res, audit_url)
        self.assertContains(ws_res, 'Forensic Audit Trail')

        detail_url = reverse('cases:case_detail', kwargs={'case_id': self.case.id})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, audit_url)

    # -------------------------------------------------------------------------
    # Clinical Fixture Seeding Command Validation
    # -------------------------------------------------------------------------
    def test_seed_clinical_cases_management_command(self):
        """
        Executes 'python manage.py seed_clinical_cases' and verifies all 3 Appendix A
        scenarios are populated with users, teams, hypotheses, rankings, and decisions.
        """
        call_command('seed_clinical_cases', '--password', 'CustomTestPass123!')

        # Verify Users
        self.assertTrue(User.objects.filter(email='dr.bassey@clinic.org', role=Role.PRIMARY_PHYSICIAN).exists())
        self.assertTrue(User.objects.filter(email='dr.adeyemi@clinic.org', role=Role.PRIMARY_PHYSICIAN).exists())
        self.assertTrue(User.objects.filter(email='dr.danjuma@clinic.org', role=Role.PRIMARY_PHYSICIAN).exists())
        self.assertTrue(User.objects.filter(email='dr.bello@clinic.org', role=Role.SPECIALIST).exists())
        self.assertTrue(User.objects.filter(email='dr.okafor@clinic.org', role=Role.SPECIALIST).exists())
        self.assertTrue(User.objects.filter(email='dr.ibrahim@clinic.org', role=Role.SPECIALIST).exists())
        self.assertTrue(User.objects.filter(email='dr.nwosu@clinic.org', role=Role.SPECIALIST).exists())
        self.assertTrue(User.objects.filter(email='dr.taiwo@clinic.org', role=Role.SPECIALIST).exists())

        # Verify Scenario 1 (AOSD)
        c1 = Case.objects.get(title__startswith="Multi-system Presentation")
        self.assertEqual(c1.status, CaseStatus.CLOSED)
        self.assertEqual(c1.team_memberships.count(), 2)
        self.assertEqual(c1.hypotheses.count(), 2)
        self.assertEqual(c1.rankings.count(), 2)
        self.assertTrue(hasattr(c1, 'decision'))
        self.assertIn("Adult-Onset Still's Disease", c1.decision.final_diagnosis)

        # Verify Scenario 2 (Occult Angiodysplasia)
        c2 = Case.objects.get(title__startswith="Refractory Severe Microcytic")
        self.assertEqual(c2.status, CaseStatus.CLOSED)
        self.assertEqual(c2.team_memberships.count(), 2)
        self.assertEqual(c2.hypotheses.count(), 2)
        self.assertTrue(hasattr(c2, 'decision'))
        self.assertIn("angiodysplasia", c2.decision.final_diagnosis.lower())

        # Verify Scenario 3 (Childhood Absence Epilepsy)
        c3 = Case.objects.get(title__startswith="Episodic Staring and Unresponsiveness")
        self.assertEqual(c3.status, CaseStatus.CLOSED)
        self.assertEqual(c3.team_memberships.count(), 1)
        self.assertEqual(c3.hypotheses.count(), 2)
        self.assertTrue(hasattr(c3, 'decision'))
        self.assertIn("Childhood Absence Epilepsy", c3.decision.final_diagnosis)

        # Verify audit records exist for all cases
        self.assertGreaterEqual(AuditLog.objects.filter(case_id=c1.id).count(), 5)
        self.assertGreaterEqual(AuditLog.objects.filter(case_id=c2.id).count(), 5)
        self.assertGreaterEqual(AuditLog.objects.filter(case_id=c3.id).count(), 5)
