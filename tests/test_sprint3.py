import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache

from accounts.models import User, Role
from cases.models import Case, CaseTeam, CaseStatus
from cases.views import get_workspace_case
from collaboration.models import Hypothesis, DiscussionNote, HypothesisStatus
from audit.models import AuditLog, AuditAction, AuditStatus


class Sprint3WorkspaceAndCollaborationTests(TestCase):
    """
    Automated test suite verifying Sprint 3 deliverables:
    - Responsive 3-pane clinical workspace
    - Structured hypothesis submission (FT06, B13) & RBAC gating (FT06b, B14)
    - Hypothesis withdrawal with provenance preservation (B16, FAULT-03, FAULT-06)
    - Chronological discussion notes with XSS sanitization (B17)
    - Intermittent network idempotency tokens (B18)
    - Query budget optimization <= 4 queries (S3-02, B30)
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Primary Physician 1 (Case Owner)
        self.physician = User.objects.create_user(
            email='attending.physician@clinic.org',
            full_name='Marcus Welby',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Primary Physician 2 (Unrelated Physician)
        self.other_physician = User.objects.create_user(
            email='other.physician@clinic.org',
            full_name='Gregory House',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Specialist 1 (Admitted)
        self.admitted_specialist = User.objects.create_user(
            email='neuro.specialist@clinic.org',
            full_name='Allison Cameron',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Specialist 2 (Not admitted)
        self.unadmitted_specialist = User.objects.create_user(
            email='cardio.specialist@clinic.org',
            full_name='Robert Chase',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Clinical Case initiated by Dr. Welby
        self.case = Case.objects.create(
            owner=self.physician,
            title='Acute progressive encephalopathy with refractory seizures',
            clinical_summary='34-year-old female presenting with rapid cognitive decline, visual hallucinations, and faciobrachial dystonic seizures over 14 days.',
            history='Previously healthy, no prior neuropsychiatric history. No travel history or toxic exposures.',
            findings='CSF: 42 WBCs (95% lymphocytes), normal glucose, elevated protein (85 mg/dL). EEG: Extreme delta brush pattern. MRI brain: bilateral medial temporal hyperintensity.',
            status=CaseStatus.OPEN
        )

        # Admit Specialist 1
        self.team_membership = CaseTeam.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            admitted_by=self.physician
        )

    def tear_down(self):
        cache.clear()

    # -------------------------------------------------------------------------
    # FT06: Admitted Specialist Structured Hypothesis Submission
    # -------------------------------------------------------------------------
    def test_ft06_admitted_specialist_submits_structured_hypothesis(self):
        """
        FT06: Admitted specialist submits structured diagnosis with rationale and evidence.
        - Case status transitions from OPEN to UNDER_REVIEW.
        - AuditLog records HYPOTHESIS_SUBMITTED.
        - Hypothesis card renders in workspace.
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        token = str(uuid.uuid4())

        payload = {
            'proposed_diagnosis': 'Anti-NMDA Receptor Encephalitis',
            'rationale': 'Rapid neurological deterioration with psychosis, seizures, and characteristic CSF lymphocytic pleocytosis indicates autoimmune etiology rather than infectious viral encephalitis.',
            'supporting_evidence': 'Presence of faciobrachial dystonic seizures, extreme delta brush on EEG, and elevated CSF protein without viral DNA on PCR panel.',
            'idempotency_token': token
        }

        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})
        response = self.client.post(url, payload)

        # Must redirect to workspace
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Verify Hypothesis entity in database
        hypothesis = Hypothesis.objects.get(case=self.case, proposed_diagnosis='Anti-NMDA Receptor Encephalitis')
        self.assertEqual(hypothesis.specialist, self.admitted_specialist)
        self.assertEqual(hypothesis.status, HypothesisStatus.ACTIVE)

        # Verify Case status transition from OPEN -> UNDER_REVIEW
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseStatus.UNDER_REVIEW)

        # Verify Audit Log
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.HYPOTHESIS_SUBMITTED,
            case_id=self.case.id,
            actor=self.admitted_specialist
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details['proposed_diagnosis'], 'Anti-NMDA Receptor Encephalitis')
        self.assertEqual(audit_entry.status, AuditStatus.ALLOWED)

        # Verify rendered card in workspace
        workspace_response = self.client.get(reverse('cases:workspace', kwargs={'case_id': self.case.id}))
        self.assertEqual(workspace_response.status_code, 200)
        self.assertContains(workspace_response, 'Anti-NMDA Receptor Encephalitis')
        self.assertContains(workspace_response, 'Allison Cameron')
        self.assertContains(workspace_response, 'extreme delta brush on EEG')

    # -------------------------------------------------------------------------
    # FT06b: Non-admitted Specialist Hypothesis Submission Denied
    # -------------------------------------------------------------------------
    def test_ft06b_unadmitted_specialist_denied_with_403_and_audit(self):
        """
        FT06b: Specialist not in CaseTeam attempts to submit hypothesis.
        - Rejected with HTTP 403 Forbidden.
        - Zero hypothesis rows created.
        - ACCESS_DENIED logged in audit trail.
        """
        self.client.login(email='cardio.specialist@clinic.org', password='StrongPassword123!')
        token = str(uuid.uuid4())

        payload = {
            'proposed_diagnosis': 'Cardiac Encephalopathy',
            'rationale': 'Hypoxic injury secondary to occult transient cardiac arrhythmia.',
            'supporting_evidence': 'Syncope-like presentation preceding cognitive decompensation.',
            'idempotency_token': token
        }

        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Hypothesis.objects.filter(case=self.case).count(), 0)

        # Verify ACCESS_DENIED audit entry
        denial_audit = AuditLog.objects.filter(
            action=AuditAction.ACCESS_DENIED,
            actor=self.unadmitted_specialist,
            case_id=self.case.id
        ).first()
        self.assertIsNotNone(denial_audit)
        self.assertEqual(denial_audit.status, AuditStatus.DENIED)

    def test_primary_physician_cannot_submit_hypotheses(self):
        """
        Primary physicians cannot submit specialist hypotheses (role asymmetry C-08).
        """
        self.client.login(email='attending.physician@clinic.org', password='StrongPassword123!')
        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})
        payload = {
            'proposed_diagnosis': 'Physician Hypothesis',
            'rationale': 'Attending physician attempting specialist contribution.',
            'supporting_evidence': 'Initial hospital intake examination findings.',
            'idempotency_token': str(uuid.uuid4())
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Hypothesis.objects.filter(case=self.case).count(), 0)

    # -------------------------------------------------------------------------
    # Mandatory Fields Validation
    # -------------------------------------------------------------------------
    def test_hypothesis_submission_validation_errors(self):
        """
        Test mandatory field constraints (min 20 characters for rationale and evidence).
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})

        # Test rationale too short (< 20 chars)
        payload = {
            'proposed_diagnosis': 'Viral Encephalitis',
            'rationale': 'Too short.',  # 10 chars
            'supporting_evidence': 'Sufficient length evidence text over twenty characters.',
            'idempotency_token': str(uuid.uuid4())
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Hypothesis.objects.count(), 0)

        # Test supporting evidence too short (< 20 chars)
        payload['rationale'] = 'Sufficient length rationale text over twenty characters.'
        payload['supporting_evidence'] = 'Too brief.'
        payload['idempotency_token'] = str(uuid.uuid4())
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Hypothesis.objects.count(), 0)

        # Test blank diagnosis
        payload['proposed_diagnosis'] = ''
        payload['supporting_evidence'] = 'Sufficient length evidence text over twenty characters.'
        payload['idempotency_token'] = str(uuid.uuid4())
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Hypothesis.objects.count(), 0)

    # -------------------------------------------------------------------------
    # Multiple Hypotheses Submission (B15)
    # -------------------------------------------------------------------------
    def test_multiple_hypotheses_submission_by_same_specialist(self):
        """
        Admitted specialist can submit multiple distinct diagnostic hypotheses (B15).
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})

        # Submission 1
        self.client.post(url, {
            'proposed_diagnosis': 'Anti-NMDA Receptor Encephalitis',
            'rationale': 'Subacute cognitive decline with psychiatric symptoms and seizures in young female.',
            'supporting_evidence': 'CSF pleocytosis and extreme delta brush pattern on continuous EEG.',
            'idempotency_token': str(uuid.uuid4())
        })

        # Submission 2
        self.client.post(url, {
            'proposed_diagnosis': 'Herpes Simplex Virus 1 (HSV-1) Encephalitis',
            'rationale': 'Acute temporal lobe involvement with seizures and lymphocytic CSF findings.',
            'supporting_evidence': 'Bilateral medial temporal hyperintensities on FLAIR sequences.',
            'idempotency_token': str(uuid.uuid4())
        })

        self.assertEqual(Hypothesis.objects.filter(case=self.case).count(), 2)

    # -------------------------------------------------------------------------
    # Hypothesis Withdrawal & Provenance (B16, FAULT-03, FAULT-06)
    # -------------------------------------------------------------------------
    def test_hypothesis_withdrawal_flow_preserves_provenance(self):
        """
        Authoring specialist marks hypothesis withdrawn with explanatory rationale (B16).
        - Status becomes WITHDRAWN.
        - Preserved in workspace with [WITHDRAWN] badge and reason.
        - HYPOTHESIS_WITHDRAWN logged in audit trail.
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')

        # Create active hypothesis
        hypo = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='HSV-1 Viral Encephalitis',
            rationale='Acute temporal lobe inflammation with febrile seizures.',
            supporting_evidence='Medial temporal FLAIR hyperintensities on initial MRI.',
            status=HypothesisStatus.ACTIVE
        )

        withdraw_url = reverse('collaboration:hypothesis_withdraw', kwargs={'case_id': self.case.id, 'hypo_id': hypo.id})

        # Withdraw with reason
        reason_text = 'Negative CSF multiplex PCR for HSV-1/2 on repeat tap rules out acute viral infection.'
        response = self.client.post(withdraw_url, {
            'withdrawal_reason': reason_text,
            'idempotency_token': str(uuid.uuid4())
        })

        self.assertEqual(response.status_code, 302)
        hypo.refresh_from_db()
        self.assertEqual(hypo.status, HypothesisStatus.WITHDRAWN)
        self.assertEqual(hypo.withdrawal_reason, reason_text)
        self.assertIsNotNone(hypo.withdrawn_at)

        # Verify audit log
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.HYPOTHESIS_WITHDRAWN,
            entity_id=str(hypo.id)
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details['withdrawal_reason'], reason_text)

        # Verify rendered in workspace with [WITHDRAWN] badge
        workspace_res = self.client.get(reverse('cases:workspace', kwargs={'case_id': self.case.id}))
        self.assertContains(workspace_res, '[WITHDRAWN]')
        self.assertContains(workspace_res, 'Negative CSF multiplex PCR')

    def test_unauthorized_user_cannot_withdraw_others_hypothesis(self):
        """
        A specialist or physician who did not author the hypothesis cannot withdraw it.
        """
        hypo = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Anti-LGI1 Encephalitis',
            rationale='Faciobrachial dystonic seizures with hyponatremia.',
            supporting_evidence='Specific seizure semiology observed on video telemetry.',
            status=HypothesisStatus.ACTIVE
        )

        # Attending physician attempts to withdraw specialist's hypothesis
        self.client.login(email='attending.physician@clinic.org', password='StrongPassword123!')
        withdraw_url = reverse('collaboration:hypothesis_withdraw', kwargs={'case_id': self.case.id, 'hypo_id': hypo.id})
        response = self.client.post(withdraw_url, {
            'withdrawal_reason': 'Attending physician disagrees with this hypothesis.',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(response.status_code, 403)
        hypo.refresh_from_db()
        self.assertEqual(hypo.status, HypothesisStatus.ACTIVE)

    # -------------------------------------------------------------------------
    # Chronological Discussion Thread (FR4, C-19, B17) & XSS Protection
    # -------------------------------------------------------------------------
    def test_chronological_discussion_notes_and_xss_protection(self):
        """
        Case Owner and admitted Specialist exchange discussion notes.
        Verifies chronological order, role badge display, and XSS sanitization.
        """
        note_url = reverse('collaboration:note_create', kwargs={'case_id': self.case.id})

        # 1. Primary physician posts note
        self.client.login(email='attending.physician@clinic.org', password='StrongPassword123!')
        res1 = self.client.post(note_url, {
            'body': 'Sending serum and CSF autoimmune encephalopathy panel to reference lab this morning.',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(res1.status_code, 302)

        # 2. Specialist responds with XSS payload to verify escaping
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        xss_payload = "<script>alert('XSS_ATTACK');</script> Please also check serum sodium levels for SIADH."
        res2 = self.client.post(note_url, {
            'body': xss_payload,
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(res2.status_code, 302)

        self.assertEqual(DiscussionNote.objects.filter(case=self.case).count(), 2)

        # Verify DISCUSSION_POSTED audit logs
        notes_audits = AuditLog.objects.filter(action=AuditAction.DISCUSSION_POSTED, case_id=self.case.id)
        self.assertEqual(notes_audits.count(), 2)

        # View workspace and verify safe rendering
        workspace_res = self.client.get(reverse('cases:workspace', kwargs={'case_id': self.case.id}))
        self.assertEqual(workspace_res.status_code, 200)
        self.assertContains(workspace_res, 'autoimmune encephalopathy panel')
        self.assertContains(workspace_res, 'Primary Phys')
        self.assertContains(workspace_res, 'Specialist')

        # Verify XSS is escaped: raw tag must NOT be present
        self.assertNotContains(workspace_res, "<script>alert('XSS_ATTACK');</script>")
        self.assertContains(workspace_res, "&lt;script&gt;alert(&#x27;XSS_ATTACK&#x27;);&lt;/script&gt;")

    def test_unadmitted_user_cannot_post_discussion_notes(self):
        """
        Non-admitted specialist cannot post to discussion thread.
        """
        self.client.login(email='cardio.specialist@clinic.org', password='StrongPassword123!')
        note_url = reverse('collaboration:note_create', kwargs={'case_id': self.case.id})
        response = self.client.post(note_url, {
            'body': 'Unadmitted note attempt.',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(DiscussionNote.objects.count(), 0)

    # -------------------------------------------------------------------------
    # Idempotency Protection (B18 / NFR5)
    # -------------------------------------------------------------------------
    def test_idempotent_hypothesis_submission_prevents_duplicates(self):
        """
        Simulate 3G network re-transmission: duplicate submission with same token is ignored.
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})
        token = str(uuid.uuid4())

        payload = {
            'proposed_diagnosis': 'Hashimoto Encephalopathy',
            'rationale': 'Steroid-responsive encephalopathy associated with autoimmune thyroiditis.',
            'supporting_evidence': 'Elevated anti-thyroperoxidase antibodies and diffuse slowing on EEG.',
            'idempotency_token': token
        }

        # First POST
        res1 = self.client.post(url, payload)
        self.assertEqual(res1.status_code, 302)
        self.assertEqual(Hypothesis.objects.filter(case=self.case).count(), 1)

        # Second POST with IDENTICAL token (network retry)
        res2 = self.client.post(url, payload)
        self.assertEqual(res2.status_code, 302)

        # Still strictly 1 hypothesis
        self.assertEqual(Hypothesis.objects.filter(case=self.case).count(), 1)

    # -------------------------------------------------------------------------
    # Terminal Case State Protection
    # -------------------------------------------------------------------------
    def test_terminal_case_state_locks_modifications(self):
        """
        When case is DECIDED or CLOSED, hypotheses submissions and notes are blocked.
        """
        self.case.status = CaseStatus.CLOSED
        self.case.save()

        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')

        # Attempt hypothesis create
        h_res = self.client.post(reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id}), {
            'proposed_diagnosis': 'Late Hypothesis',
            'rationale': 'Attempting submission after case closure.',
            'supporting_evidence': 'Valid length supporting clinical evidence text.',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(h_res.status_code, 403)

        # Attempt note create
        n_res = self.client.post(reverse('collaboration:note_create', kwargs={'case_id': self.case.id}), {
            'body': 'Attempting note after case closure.',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(n_res.status_code, 403)

    # -------------------------------------------------------------------------
    # S3-02 & B30: Query Budget Optimization (<= 4 Queries)
    # -------------------------------------------------------------------------
    def test_workspace_bounded_query_budget_strictly_4_queries(self):
        """
        Verify that get_workspace_case executes strictly <= 4 SQL queries to load
        the entire case presentation, owner, team members, hypotheses, and notes.
        """
        # Create multiple hypotheses and notes to test prefetching scalability
        for i in range(5):
            Hypothesis.objects.create(
                case=self.case,
                specialist=self.admitted_specialist,
                proposed_diagnosis=f'Differential Hypothesis {i}',
                rationale='Detailed pathophysiological reasoning exceeding minimum threshold.',
                supporting_evidence='Sufficient laboratory and physical diagnostic indicators.',
                status=HypothesisStatus.ACTIVE if i % 2 == 0 else HypothesisStatus.WITHDRAWN,
                withdrawal_reason='Rule-out reasoning' if i % 2 != 0 else ''
            )
            DiscussionNote.objects.create(
                case=self.case,
                author=self.physician if i % 2 == 0 else self.admitted_specialist,
                body=f'Clinical discussion deliberative message number {i}'
            )

        # Bounded query test: strictly 4 queries
        with self.assertNumQueries(4):
            workspace_case = get_workspace_case(self.case.id)
            # Evaluate all prefetched sets without generating extra database roundtrips
            team = list(workspace_case.team_memberships.all())
            for tm in team:
                _ = tm.specialist.full_name

            hypos = list(workspace_case.hypotheses.all())
            for h in hypos:
                _ = h.specialist.full_name

            notes = list(workspace_case.discussion_notes.all())
            for n in notes:
                _ = n.author.full_name

        self.assertEqual(len(hypos), 5)
        self.assertEqual(len(notes), 5)

    def test_workspace_full_page_load_query_count(self):
        """
        Verify that a full HTTP GET request to the workspace executes in <= 9 total queries
        including session, auth, and the bounded 4-query workspace prefetch batch.
        """
        self.client.login(email='attending.physician@clinic.org', password='StrongPassword123!')
        url = reverse('cases:workspace', kwargs={'case_id': self.case.id})

        # Request cycle total queries
        with self.assertNumQueries(9):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------------------
    # Workspace Access Gating
    # -------------------------------------------------------------------------
    def test_unauthenticated_user_redirected_from_workspace(self):
        """
        Unauthenticated user is redirected to login.
        """
        url = reverse('cases:workspace', kwargs={'case_id': self.case.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_unauthorized_physician_denied_from_workspace(self):
        """
        A physician who is not the case owner cannot access the workspace.
        """
        self.client.login(email='other.physician@clinic.org', password='StrongPassword123!')
        url = reverse('cases:workspace', kwargs={'case_id': self.case.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # Model-Level Clean Validations & String Representations
    # -------------------------------------------------------------------------
    def test_hypothesis_model_clean_validation(self):
        """
        Direct model clean() assertions for Hypothesis entity.
        """
        from django.core.exceptions import ValidationError

        # 1. Non-specialist role validation
        h1 = Hypothesis(
            case=self.case,
            specialist=self.physician,
            proposed_diagnosis='Test Diagnosis',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.'
        )
        with self.assertRaises(ValidationError):
            h1.clean()

        # 2. Unadmitted specialist validation
        h2 = Hypothesis(
            case=self.case,
            specialist=self.unadmitted_specialist,
            proposed_diagnosis='Test Diagnosis',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.'
        )
        with self.assertRaises(ValidationError):
            h2.clean()

        # 3. Supporting evidence too short
        h3 = Hypothesis(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Test Diagnosis',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Too short.'
        )
        with self.assertRaises(ValidationError):
            h3.clean()

        # 4. Rationale too short
        h4 = Hypothesis(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Test Diagnosis',
            rationale='Too short.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.'
        )
        with self.assertRaises(ValidationError):
            h4.clean()

        # 5. Withdrawn without withdrawal_reason
        h5 = Hypothesis(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Test Diagnosis',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.',
            status=HypothesisStatus.WITHDRAWN,
            withdrawal_reason=''
        )
        with self.assertRaises(ValidationError):
            h5.clean()

        # 6. Valid hypothesis clean & string representation
        h_valid = Hypothesis(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Valid Diagnosis Label',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.'
        )
        h_valid.clean()
        self.assertIn('Valid Diagnosis Label', str(h_valid))

        # 7. Withdraw method with reason too short
        h_valid.save()
        with self.assertRaises(ValidationError):
            h_valid.withdraw('short')

    def test_discussion_note_model_clean_validation(self):
        """
        Direct model clean() assertions for DiscussionNote entity.
        """
        from django.core.exceptions import ValidationError

        # 1. Blank body
        note_blank = DiscussionNote(
            case=self.case,
            author=self.physician,
            body='   '
        )
        with self.assertRaises(ValidationError):
            note_blank.clean()

        # 2. Unauthorized author
        note_unauth = DiscussionNote(
            case=self.case,
            author=self.unadmitted_specialist,
            body='Valid deliberation note content.'
        )
        with self.assertRaises(ValidationError):
            note_unauth.clean()

        # 3. Valid note clean & string representation
        note_valid = DiscussionNote(
            case=self.case,
            author=self.physician,
            body='Valid clinical deliberation comment.'
        )
        note_valid.clean()
        note_valid.save()
        self.assertIn(self.physician.full_name, str(note_valid))

    def test_withdraw_view_invalid_form_handling(self):
        """
        Verify that submitting an invalid withdrawal form (e.g. reason too short) returns 400.
        """
        self.client.login(email='neuro.specialist@clinic.org', password='StrongPassword123!')
        hypo = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Anti-GABA Encephalitis',
            rationale='Valid length clinical rationale exceeding twenty characters.',
            supporting_evidence='Valid length clinical supporting evidence exceeding twenty characters.'
        )
        withdraw_url = reverse('collaboration:hypothesis_withdraw', kwargs={'case_id': self.case.id, 'hypo_id': hypo.id})
        response = self.client.post(withdraw_url, {
            'withdrawal_reason': 'short',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(response.status_code, 400)
        hypo.refresh_from_db()
        self.assertEqual(hypo.status, HypothesisStatus.ACTIVE)

    def test_discussion_note_invalid_form_handling(self):
        """
        Verify that posting an empty discussion note returns 400.
        """
        self.client.login(email='attending.physician@clinic.org', password='StrongPassword123!')
        note_url = reverse('collaboration:note_create', kwargs={'case_id': self.case.id})
        response = self.client.post(note_url, {
            'body': '',
            'idempotency_token': str(uuid.uuid4())
        })
        self.assertEqual(response.status_code, 400)

