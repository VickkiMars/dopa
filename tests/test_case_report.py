import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache

from accounts.models import User, Role
from cases.models import (
    Case, CaseTeam, CaseStatus, DiagnosisRanking, Decision,
    CaseAttachment, AttachmentCategory, CaseLabResult, LabFlag
)
from collaboration.models import Hypothesis, HypothesisStatus, DiscussionNote
from audit.models import AuditLog, AuditAction, AuditStatus


class CaseReportAndDossierTests(TestCase):
    """
    Automated test suite verifying the Clinical Consultation Report & Audit Dossier Export (FT15).
    Covers:
    - HTML and JSON export formats
    - Multi-specialist consultation rendering (vitals, labs, hypotheses, notes, decision)
    - Zero-bypass RBAC access gating (@case_access_required)
    - Medico-legal governance statement verification
    - Forensic audit logging (REPORT_GENERATED and ACCESS_DENIED)
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Primary Physician (Case Owner)
        self.physician = User.objects.create_user(
            email='dr.welby@dopa.clinic',
            full_name='Marcus Welby',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Unrelated Primary Physician
        self.other_physician = User.objects.create_user(
            email='dr.house@dopa.clinic',
            full_name='Gregory House',
            role=Role.PRIMARY_PHYSICIAN,
            password='StrongPassword123!'
        )

        # Admitted Specialist
        self.admitted_specialist = User.objects.create_user(
            email='dr.cameron@dopa.clinic',
            full_name='Allison Cameron',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Unadmitted Specialist
        self.unadmitted_specialist = User.objects.create_user(
            email='dr.foreman@dopa.clinic',
            full_name='Eric Foreman',
            role=Role.SPECIALIST,
            password='StrongPassword123!'
        )

        # Create Clinical Case with Bedside Telemetry Vitals
        self.case = Case.objects.create(
            owner=self.physician,
            title='Recurrent high spiking fever with polyarthralgia and salmon rash',
            clinical_summary='31-year-old female presenting with quotidian fevers up to 39.8°C, evanescent salmon-colored rash, and bilateral knee arthralgia.',
            history='Previously healthy, no foreign travel, no tick bite history, negative ANA and RF screens.',
            findings='Physical exam reveals evanescent non-pruritic salmon macular rash over trunk during fever spikes, tender swollen carpal and knee joints.',
            temperature_c=Decimal('39.8'),
            heart_rate_bpm=114,
            bp_systolic=118,
            bp_diastolic=76,
            respiratory_rate=20,
            oxygen_saturation=98,
            status=CaseStatus.UNDER_REVIEW
        )

        # Admit Specialist to Case
        CaseTeam.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            admitted_by=self.physician
        )

        # Add Quantitative Lab Results
        self.lab1 = CaseLabResult.objects.create(
            case=self.case,
            test_name='Serum Ferritin',
            value='8450',
            unit='ng/mL',
            reference_range='15 - 200 ng/mL',
            flag=LabFlag.CRITICAL
        )
        self.lab2 = CaseLabResult.objects.create(
            case=self.case,
            test_name='C-Reactive Protein (CRP)',
            value='185',
            unit='mg/L',
            reference_range='< 5 mg/L',
            flag=LabFlag.HIGH
        )

        # Add Diagnostic Media Attachment
        self.attachment = CaseAttachment.objects.create(
            case=self.case,
            uploaded_by=self.physician,
            category=AttachmentCategory.CLINICAL_PHOTO,
            title='Evanescent macular trunk rash during evening fever spike',
            file='case_attachments/sample_rash.jpg',
            mime_type='image/jpeg',
            file_size_bytes=428900
        )

        # Formulate Active Hypothesis
        self.hypo_active = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis="Adult-Onset Still's Disease (AOSD)",
            rationale='Quotidian spiking fevers, evanescent salmon rash, and extreme hyperferritinemia (>4000 ng/mL) satisfy Yamaguchi criteria.',
            supporting_evidence='Temp 39.8°C, Ferritin 8,450 ng/mL [CRITICAL], negative infectious workup.',
            status=HypothesisStatus.ACTIVE
        )

        # Formulate Withdrawn Hypothesis (Historical Provenance)
        self.hypo_withdrawn = Hypothesis.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            proposed_diagnosis='Systemic Lupus Erythematosus (SLE)',
            rationale='Multi-system presentation with rash and inflammatory polyarthritis.',
            supporting_evidence='Elevated inflammatory markers.',
            status=HypothesisStatus.WITHDRAWN,
            withdrawal_reason='Serological workup returned negative for ANA, dsDNA, and anti-Smith antibodies; Yamaguchi criteria strongly favored.'
        )

        # Differential Diagnosis Ranking
        DiagnosisRanking.objects.create(
            case=self.case,
            hypothesis=self.hypo_active,
            rank_position=1
        )

        # Discussion Deliberation Note
        DiscussionNote.objects.create(
            case=self.case,
            author=self.admitted_specialist,
            body='Recommend ruling out acute cytomegalovirus and EBV serology before initiating high-dose methylprednisolone pulse therapy.'
        )

        self.report_url = reverse('cases:case_report', kwargs={'case_id': self.case.id})

    def tearDown(self):
        cache.clear()

    # -------------------------------------------------------------------------
    # Positive Access & HTML Rendering Tests
    # -------------------------------------------------------------------------
    def test_case_owner_can_access_report_html(self):
        """
        Case Owner (Primary Physician) accesses the HTML report:
        - Returns HTTP 200 OK.
        - Renders clinical summary, vitals telemetry, labs, hypotheses, notes, and attachments.
        - Contains print trigger button.
        """
        self.client.login(email='dr.welby@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)

        # Verify key clinical sections rendered
        self.assertContains(response, 'Clinical Consultation Report')
        self.assertContains(response, 'Recurrent high spiking fever with polyarthralgia and salmon rash')
        self.assertContains(response, '39.8 °C')
        self.assertContains(response, 'Serum Ferritin')
        self.assertContains(response, '8450')
        self.assertContains(response, 'CRITICAL')
        self.assertContains(response, "Adult-Onset Still&#x27;s Disease (AOSD)")
        self.assertContains(response, 'Yamaguchi criteria')
        self.assertContains(response, 'Systemic Lupus Erythematosus (SLE)')
        self.assertContains(response, 'Serological workup returned negative for ANA')
        self.assertContains(response, 'Evanescent macular trunk rash')
        self.assertContains(response, 'window.print()')

    def test_admitted_specialist_can_access_report_html(self):
        """
        Admitted specialist on the case team accesses the HTML report:
        - Returns HTTP 200 OK.
        - Sees full consultation dossier.
        """
        self.client.login(email='dr.cameron@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clinical Consultation Report')
        self.assertContains(response, 'dr.welby@dopa.clinic')

    # -------------------------------------------------------------------------
    # Zero-Bypass RBAC Security Tests
    # -------------------------------------------------------------------------
    def test_unadmitted_specialist_denied_from_report(self):
        """
        Specialist who has NOT been admitted to the case team attempts to view report:
        - Rejected with HTTP 403 Forbidden.
        - No case details leaked.
        - ACCESS_DENIED logged in AuditLog.
        """
        self.client.login(email='dr.foreman@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 403)

        # Verify ACCESS_DENIED audit log
        denial = AuditLog.objects.filter(
            action=AuditAction.ACCESS_DENIED,
            case_id=self.case.id,
            actor=self.unadmitted_specialist
        ).first()
        self.assertIsNotNone(denial)
        self.assertEqual(denial.status, AuditStatus.DENIED)

    def test_unrelated_physician_denied_from_report(self):
        """
        A Primary Physician who does not own the case attempts to view report:
        - Rejected with HTTP 403 Forbidden.
        - ACCESS_DENIED logged in AuditLog.
        """
        self.client.login(email='dr.house@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 403)

        denial = AuditLog.objects.filter(
            action=AuditAction.ACCESS_DENIED,
            case_id=self.case.id,
            actor=self.other_physician
        ).first()
        self.assertIsNotNone(denial)

    def test_unauthenticated_user_redirected(self):
        """
        Unauthenticated anonymous request redirects to login page.
        """
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    # -------------------------------------------------------------------------
    # Machine-Readable JSON Export Tests
    # -------------------------------------------------------------------------
    def test_json_export_format_and_schema(self):
        """
        Requesting ?format=json returns valid JSON matching the clinical consultation contract:
        - HTTP 200 with Content-Type: application/json.
        - Contains structured case, presentation, vitals, labs, hypotheses, and audit sections.
        """
        self.client.login(email='dr.welby@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url + '?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = json.loads(response.content)
        self.assertEqual(data['case_id'], str(self.case.id))
        self.assertEqual(data['title'], self.case.title)
        self.assertEqual(data['status'], CaseStatus.UNDER_REVIEW)
        self.assertEqual(data['primary_physician']['name'], 'Marcus Welby')

        # Vitals & Presentation
        self.assertTrue(data['clinical_presentation']['has_vitals'])
        vitals = data['clinical_presentation']['vitals']
        self.assertTrue(any(v['name'] == 'Temp' and '39.8' in v['value'] for v in vitals))

        # Labs
        self.assertEqual(len(data['laboratory_results']), 2)
        ferritin = next(l for l in data['laboratory_results'] if l['test_name'] == 'Serum Ferritin')
        self.assertEqual(ferritin['value'], '8450')
        self.assertEqual(ferritin['flag'], 'CRITICAL')

        # Attachments
        self.assertEqual(len(data['diagnostic_attachments']), 1)
        self.assertEqual(data['diagnostic_attachments'][0]['category'], 'CLINICAL_PHOTO')

        # Hypotheses
        self.assertEqual(len(data['differential_rankings']), 1)
        self.assertEqual(data['differential_rankings'][0]['rank'], 1)
        self.assertEqual(data['differential_rankings'][0]['proposed_diagnosis'], "Adult-Onset Still's Disease (AOSD)")

        # Withdrawn Hypotheses
        self.assertEqual(len(data['withdrawn_hypotheses']), 1)
        self.assertEqual(data['withdrawn_hypotheses'][0]['proposed_diagnosis'], 'Systemic Lupus Erythematosus (SLE)')

        # Audit Certificate
        self.assertIn('audit_certificate', data)
        self.assertGreaterEqual(data['audit_certificate']['total_events'], 1)

    # -------------------------------------------------------------------------
    # Forensic Audit Log Verification
    # -------------------------------------------------------------------------
    def test_report_generation_dispatches_audit_log(self):
        """
        Generating a report (HTML or JSON) appends a REPORT_GENERATED entry to the append-only audit trail.
        """
        self.client.login(email='dr.welby@dopa.clinic', password='StrongPassword123!')
        res1 = self.client.get(self.report_url)
        self.assertEqual(res1.status_code, 200)

        html_log = AuditLog.objects.filter(
            action=AuditAction.REPORT_GENERATED,
            case_id=self.case.id,
            actor=self.physician,
            details__format='html'
        ).first()
        self.assertIsNotNone(html_log)

        res2 = self.client.get(self.report_url + '?format=json')
        self.assertEqual(res2.status_code, 200)

        json_log = AuditLog.objects.filter(
            action=AuditAction.REPORT_GENERATED,
            case_id=self.case.id,
            actor=self.physician,
            details__format='json'
        ).first()
        self.assertIsNotNone(json_log)

    # -------------------------------------------------------------------------
    # Closed Case Governance & Final Decision Rendering
    # -------------------------------------------------------------------------
    def test_closed_case_report_includes_governance_acknowledgement(self):
        """
        On a completed case with a recorded final decision:
        - The report prominently displays the confirmed final diagnosis.
        - Displays the verbatim medico-legal advisory acknowledgement statement.
        """
        Decision.objects.create(
            case=self.case,
            decider=self.physician,
            final_diagnosis="Confirmed Adult-Onset Still's Disease (AOSD)",
            advisory_acknowledged=True,
            governance_statement='Initiating high-dose systemic corticosteroid therapy and rheumatology outpatient monitoring.'
        )
        self.case.status = CaseStatus.CLOSED
        self.case.save()

        self.client.login(email='dr.welby@dopa.clinic', password='StrongPassword123!')
        response = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "CONFIRMED FINAL DIAGNOSIS: Confirmed Adult-Onset Still&#x27;s Disease (AOSD)")
        self.assertContains(response, 'Mandatory Medico-Legal Governance Acknowledgement')
        self.assertContains(response, 'specialist advice obtained through the DOPA platform is purely advisory in nature')
        self.assertContains(response, 'CASE CLOSED')

        # Also verify JSON output includes decision
        res_json = self.client.get(self.report_url + '?format=json')
        data = json.loads(res_json.content)
        self.assertIsNotNone(data['final_decision'])
        self.assertEqual(data['final_decision']['final_diagnosis'], "Confirmed Adult-Onset Still's Disease (AOSD)")
        self.assertTrue(data['final_decision']['advisory_acknowledged'])
