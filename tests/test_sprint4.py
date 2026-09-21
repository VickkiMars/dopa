import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from cases.models import Case, CaseTeam, CaseStatus, DiagnosisRanking, Decision
from cases.views import sync_case_rankings
from collaboration.models import Hypothesis, HypothesisStatus
from audit.models import AuditLog, AuditAction, AuditStatus


class Sprint4RankingAndDecisionTests(TestCase):
    """
    Automated test suite verifying Sprint 4 deliverables:
    - Differential diagnosis ranking and atomic priority reorder (FT07)
    - RBAC enforcement restricting ranking reorders to Primary Physician (FT08 / B20)
    - Final clinical decision governance requiring legal advisory acknowledgment (FT09, FT10, B21, B23)
    - Case lifecycle transition to CLOSED upon decision recording (S4-06)
    - Database singularity (1 decision per case) and model clean constraints
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Primary Physician 1 (Case Owner)
        self.physician = User.objects.create_user(
            email='attending.welby@clinic.org',
            full_name='Marcus Welby',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Primary Physician 2 (Unrelated Physician)
        self.other_physician = User.objects.create_user(
            email='other.house@clinic.org',
            full_name='Gregory House',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Specialist 1 (Admitted)
        self.admitted_specialist = User.objects.create_user(
            email='specialist.cameron@clinic.org',
            full_name='Allison Cameron',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Specialist 2 (Admitted)
        self.admitted_specialist_2 = User.objects.create_user(
            email='specialist.foreman@clinic.org',
            full_name='Eric Foreman',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Clinical Case initiated by Dr. Welby
        self.case = Case.objects.create(
            owner=self.physician,
            title='Subacute progressive ataxia and cognitive fluctuation',
            clinical_summary='58-year-old male with 6-week history of rapidly progressive cerebellar ataxia, myoclonus, and periodic sharp wave complexes on EEG.',
            history='Hypertension, no family history of neurodegenerative disease. No heavy metal exposures.',
            findings='MRI: Bilateral cortical ribboning and striatal hyperintensity on DWI. CSF: 14-3-3 protein elevated, RT-QuIC positive.',
            status=CaseStatus.UNDER_REVIEW
        )

        # Admit Specialists
        CaseTeam.objects.create(case=self.case, specialist=self.admitted_specialist, admitted_by=self.physician)
        CaseTeam.objects.create(case=self.case, specialist=self.admitted_specialist_2, admitted_by=self.physician)

        # Create 3 Active Hypotheses
        self.hypo1 = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Sporadic Creutzfeldt-Jakob Disease (sCJD)',
            rationale='Rapid cognitive decline with prominent ataxia, myoclonus, and periodic sharp wave complexes.',
            supporting_evidence='Positive CSF RT-QuIC and characteristic cortical ribboning on brain MRI DWI.',
            status=HypothesisStatus.ACTIVE
        )

        self.hypo2 = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist_2,
            proposed_diagnosis='Autoimmune Encephalitis (Voltage-Gated Potassium Channel Complex)',
            rationale='Subacute onset ataxia and myoclonus can mimic prion disease in autoimmune mimics.',
            supporting_evidence='Response to empirical high-dose corticosteroids and pleocytosis.',
            status=HypothesisStatus.ACTIVE
        )

        self.hypo3 = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Paraneoplastic Cerebellar Degeneration',
            rationale='Rapid cerebellar syndrome in late adulthood may be triggered by occult malignancy.',
            supporting_evidence='Age, smoking history, and elevated nonspecific inflammatory markers.',
            status=HypothesisStatus.ACTIVE
        )

        # Synchronize rankings
        sync_case_rankings(self.case)

    def tearDown(self):
        cache.clear()

    # -------------------------------------------------------------------------
    # FT07: Primary Physician Reorders Differential Ranking (Atomic Swap)
    # -------------------------------------------------------------------------
    def test_ft07_primary_physician_reorders_differential_ranking_up_and_down(self):
        """
        FT07: Primary Physician reorders differential ranking.
        - Moving rank 2 UP swaps positions 1 and 2 atomically.
        - Dispatches RANK_UPDATED audit log.
        - Rank numbers in database and workspace reflect the swap.
        """
        self.client.login(email='attending.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:ranking_reorder', kwargs={'case_id': self.case.id})

        # Initial ranks: hypo1 -> 1, hypo2 -> 2, hypo3 -> 3
        rank_h1 = DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo1).rank_position
        rank_h2 = DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo2).rank_position
        self.assertEqual(rank_h1, 1)
        self.assertEqual(rank_h2, 2)

        # Move hypo2 UP (should become rank 1, hypo1 becomes rank 2)
        response = self.client.post(url, {
            'hypothesis_id': str(self.hypo2.id),
            'direction': 'UP'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Verify atomic swap in DB
        rank_h1_after = DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo1).rank_position
        rank_h2_after = DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo2).rank_position
        self.assertEqual(rank_h2_after, 1)
        self.assertEqual(rank_h1_after, 2)

        # Verify RANK_UPDATED audit log
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.RANK_UPDATED,
            case_id=self.case.id,
            actor=self.physician
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details['hypothesis_id'], str(self.hypo2.id))
        self.assertEqual(audit_entry.details['new_rank'], 1)

        # Move hypo2 DOWN (should return hypo2 to rank 2, hypo1 to rank 1)
        response_down = self.client.post(url, {
            'hypothesis_id': str(self.hypo2.id),
            'direction': 'DOWN'
        })
        self.assertEqual(response_down.status_code, 302)
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo1).rank_position, 1)
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo2).rank_position, 2)

    def test_ranking_reorder_boundary_conditions(self):
        """
        Moving UP on rank 1 or DOWN on the lowest rank does nothing gracefully.
        """
        self.client.login(email='attending.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:ranking_reorder', kwargs={'case_id': self.case.id})

        # Move rank 1 UP
        res1 = self.client.post(url, {'hypothesis_id': str(self.hypo1.id), 'direction': 'UP'})
        self.assertEqual(res1.status_code, 302)
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo1).rank_position, 1)

        # Move rank 3 DOWN
        res2 = self.client.post(url, {'hypothesis_id': str(self.hypo3.id), 'direction': 'DOWN'})
        self.assertEqual(res2.status_code, 302)
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo3).rank_position, 3)

    # -------------------------------------------------------------------------
    # FT08: Specialist Reorder Attempt Denied & Read-Only Display
    # -------------------------------------------------------------------------
    def test_ft08_specialist_cannot_reorder_differential_ranking(self):
        """
        Specialist attempts POST to reorder ranking:
        - Rejected with HTTP 403 Forbidden.
        - Ranks remain unchanged.
        - ACCESS_DENIED logged in audit trail.
        """
        self.client.login(email='specialist.cameron@clinic.org', password='StrongPassword123!')
        url = reverse('cases:ranking_reorder', kwargs={'case_id': self.case.id})

        response = self.client.post(url, {
            'hypothesis_id': str(self.hypo2.id),
            'direction': 'UP'
        })
        self.assertEqual(response.status_code, 403)

        # Verify rankings unchanged
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo1).rank_position, 1)
        self.assertEqual(DiagnosisRanking.objects.get(case=self.case, hypothesis=self.hypo2).rank_position, 2)

        # Verify ACCESS_DENIED audit log
        denial_audit = AuditLog.objects.filter(
            action=AuditAction.ACCESS_DENIED,
            case_id=self.case.id,
            actor=self.admitted_specialist
        ).first()
        self.assertIsNotNone(denial_audit)
        self.assertEqual(denial_audit.status, AuditStatus.DENIED)

    def test_specialist_views_differential_ranking_in_read_only_mode(self):
        """
        Workspace GET for specialist renders differential ranking without reorder action buttons.
        """
        self.client.login(email='specialist.cameron@clinic.org', password='StrongPassword123!')
        workspace_res = self.client.get(reverse('cases:workspace', kwargs={'case_id': self.case.id}))
        self.assertEqual(workspace_res.status_code, 200)
        self.assertContains(workspace_res, 'Specialists view differential ranking in read-only mode')
        # Does not contain action buttons with direction=UP
        self.assertNotContains(workspace_res, 'name="direction" value="UP"')

    # -------------------------------------------------------------------------
    # FT09: Decision Submission Without Advisory Acknowledgment Rejected
    # -------------------------------------------------------------------------
    def test_ft09_decision_submission_without_advisory_acknowledgement_rejected(self):
        """
        FT09: Primary physician attempts to submit final decision without checking the advisory acknowledgement.
        - Rejected with HTTP 400 Bad Request.
        - Inline validation alert displayed.
        - Decision row NOT created.
        - Case status remains UNDER_REVIEW.
        """
        self.client.login(email='attending.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:decision_record', kwargs={'case_id': self.case.id})

        payload = {
            'final_diagnosis': 'Definitive sCJD confirmed by RT-QuIC',
            'advisory_acknowledged': False,  # Unchecked
            'idempotency_token': str(uuid.uuid4())
        }
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'You must acknowledge that specialist advice is advisory', status_code=400)

        # Verify Decision entity was NOT created
        self.assertFalse(Decision.objects.filter(case=self.case).exists())

        # Verify Case status is still UNDER_REVIEW
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseStatus.UNDER_REVIEW)

    # -------------------------------------------------------------------------
    # FT10: Decision Submission With Acknowledgment Closes Case & Locks Workspace
    # -------------------------------------------------------------------------
    def test_ft10_decision_submission_with_acknowledgement_closes_case_and_locks(self):
        """
        FT10: Primary physician submits decision with advisory acknowledgment:
        - HTTP 302 redirect to workspace.
        - Decision row persisted with decider, final_diagnosis, and legal acknowledgment.
        - Case status transitions to CLOSED.
        - DECISION_RECORDED audit log dispatched.
        - Workspace displays final decision banner and locks subsequent modifications.
        """
        self.client.login(email='attending.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:decision_record', kwargs={'case_id': self.case.id})

        token = str(uuid.uuid4())
        payload = {
            'final_diagnosis': 'Probable Sporadic Creutzfeldt-Jakob Disease (sCJD)',
            'advisory_acknowledged': True,
            'idempotency_token': token
        }
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Verify Decision row
        decision = Decision.objects.get(case=self.case)
        self.assertEqual(decision.decider, self.physician)
        self.assertEqual(decision.final_diagnosis, 'Probable Sporadic Creutzfeldt-Jakob Disease (sCJD)')
        self.assertTrue(decision.advisory_acknowledged)
        self.assertIn('advisory in nature', decision.governance_statement)

        # Verify Case status is now CLOSED
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseStatus.CLOSED)

        # Verify DECISION_RECORDED audit log
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.DECISION_RECORDED,
            case_id=self.case.id,
            actor=self.physician
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details['final_diagnosis'], 'Probable Sporadic Creutzfeldt-Jakob Disease (sCJD)')
        self.assertTrue(audit_entry.details['advisory_acknowledged'])

        # Verify workspace rendering has definitive decision card and locked status
        workspace_res = self.client.get(reverse('cases:workspace', kwargs={'case_id': self.case.id}))
        self.assertEqual(workspace_res.status_code, 200)
        self.assertContains(workspace_res, 'Definitive Diagnosis')
        self.assertContains(workspace_res, 'Probable Sporadic Creutzfeldt-Jakob Disease (sCJD)')
        self.assertContains(workspace_res, 'Consultation closed and archived')

        # Verify workspace is locked: subsequent reorder rejected with 403
        reorder_res = self.client.post(reverse('cases:ranking_reorder', kwargs={'case_id': self.case.id}), {
            'hypothesis_id': str(self.hypo1.id),
            'direction': 'DOWN'
        })
        self.assertEqual(reorder_res.status_code, 403)

    def test_specialist_cannot_record_decision(self):
        """
        Specialists receive HTTP 403 and ACCESS_DENIED when attempting decision recording.
        """
        self.client.login(email='specialist.cameron@clinic.org', password='StrongPassword123!')
        url = reverse('cases:decision_record', kwargs={'case_id': self.case.id})
        response = self.client.post(url, {
            'final_diagnosis': 'Specialist Unauthorized Decision',
            'advisory_acknowledged': True,
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Decision.objects.filter(case=self.case).exists())

    def test_cannot_record_duplicate_decision(self):
        """
        Attempting to record a second decision on an already closed case is rejected with 403.
        """
        self.client.login(email='attending.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:decision_record', kwargs={'case_id': self.case.id})

        # First valid decision
        self.client.post(url, {
            'final_diagnosis': 'Initial Diagnosis',
            'advisory_acknowledged': True,
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(Decision.objects.filter(case=self.case).count(), 1)

        # Attempt second decision
        res2 = self.client.post(url, {
            'final_diagnosis': 'Second Duplicate Diagnosis',
            'advisory_acknowledged': True,
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(res2.status_code, 403)
        self.assertEqual(Decision.objects.filter(case=self.case).count(), 1)

    # -------------------------------------------------------------------------
    # Model-Level Clean & Entity Constraints
    # -------------------------------------------------------------------------
    def test_decision_model_clean_validation(self):
        """
        Direct model clean() assertions for Decision entity.
        """
        # 1. Unacknowledged advisory
        d1 = Decision(
            case=self.case,
            decider=self.physician,
            final_diagnosis='Test Diagnosis',
            advisory_acknowledged=False,
            governance_statement='Test statement'
        )
        with self.assertRaises(ValidationError):
            d1.clean()

        # 2. Non-owner decider
        d2 = Decision(
            case=self.case,
            decider=self.other_physician,
            final_diagnosis='Test Diagnosis',
            advisory_acknowledged=True,
            governance_statement='Test statement'
        )
        with self.assertRaises(ValidationError):
            d2.clean()

        # 3. Valid decision clean & string representation
        d_valid = Decision(
            case=self.case,
            decider=self.physician,
            final_diagnosis='Definitive Diagnosis Label',
            advisory_acknowledged=True,
            governance_statement='Test statement'
        )
        d_valid.clean()
        self.assertIn('Definitive Diagnosis Label', str(d_valid))

    def test_diagnosis_ranking_string_representation(self):
        """
        Verify DiagnosisRanking __str__ representation.
        """
        ranking = DiagnosisRanking.objects.filter(case=self.case).first()
        self.assertIn('Rank 1', str(ranking))
