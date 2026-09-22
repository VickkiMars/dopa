import json
from decimal import Decimal
import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from cases.models import Case, CaseTeam, CaseStatus, CaseLabResult, LabFlag
from audit.models import AuditLog, AuditAction, AuditStatus


class CaseVitalsModelTests(TestCase):
    """
    Unit tests for discrete physiological vital signs validation and alert flags (FR2c, FAULT-01).
    """
    def setUp(self):
        self.physician = User.objects.create_user(
            email='physician.vitals@hospital.org',
            password='Password123!',
            full_name='Dr. Vitals Physician',
            role=Role.PRIMARY_PHYSICIAN
        )

    def test_valid_vitals_creation(self):
        case = Case.objects.create(
            owner=self.physician,
            title='Acute Febrile Illness Case',
            clinical_summary='Patient with 3-day history of high fever and tachycardia.',
            history='No prior medical history, non-smoker.',
            findings='Evanescent rash noted on torso during peak temperatures.',
            temperature_c=Decimal('39.4'),
            heart_rate_bpm=108,
            bp_systolic=120,
            bp_diastolic=80,
            respiratory_rate=22,
            oxygen_saturation=98
        )
        self.assertTrue(case.has_vitals)
        self.assertEqual(case.temperature_c, Decimal('39.4'))
        self.assertEqual(case.heart_rate_bpm, 108)

        v_list = case.vitals_list
        self.assertEqual(len(v_list), 5)

        # Check flags
        temp_item = next(item for item in v_list if item['name'] == 'Temp')
        self.assertEqual(temp_item['tag'], 'Fever')
        self.assertEqual(temp_item['flag'], 'warning')

        hr_item = next(item for item in v_list if item['name'] == 'Heart Rate')
        self.assertEqual(hr_item['tag'], 'Tachycardia')
        self.assertEqual(hr_item['flag'], 'warning')

        rr_item = next(item for item in v_list if item['name'] == 'Resp. Rate')
        self.assertEqual(rr_item['tag'], 'Tachypnea')

    def test_physiological_range_validations(self):
        # Temperature out of bounds
        case_high_temp = Case(
            owner=self.physician,
            title='Invalid Temp Case',
            clinical_summary='Summary text goes here for validation testing.',
            history='History text goes here for validation testing.',
            findings='Findings text goes here for validation testing.',
            temperature_c=Decimal('48.0')
        )
        with self.assertRaises(ValidationError) as ctx:
            case_high_temp.full_clean()
        self.assertIn('temperature_c', ctx.exception.message_dict)

        # Heart rate out of bounds
        case_neg_hr = Case(
            owner=self.physician,
            title='Invalid HR Case',
            clinical_summary='Summary text goes here for validation testing.',
            history='History text goes here for validation testing.',
            findings='Findings text goes here for validation testing.',
            heart_rate_bpm=350
        )
        with self.assertRaises(ValidationError) as ctx:
            case_neg_hr.full_clean()
        self.assertIn('heart_rate_bpm', ctx.exception.message_dict)

        # Systolic <= Diastolic
        case_bad_bp = Case(
            owner=self.physician,
            title='Invalid BP Case',
            clinical_summary='Summary text goes here for validation testing.',
            history='History text goes here for validation testing.',
            findings='Findings text goes here for validation testing.',
            bp_systolic=70,
            bp_diastolic=90
        )
        with self.assertRaises(ValidationError) as ctx:
            case_bad_bp.full_clean()
        self.assertIn('bp_systolic', ctx.exception.message_dict)

        # SpO2 > 100
        case_bad_spo2 = Case(
            owner=self.physician,
            title='Invalid SpO2 Case',
            clinical_summary='Summary text goes here for validation testing.',
            history='History text goes here for validation testing.',
            findings='Findings text goes here for validation testing.',
            oxygen_saturation=105
        )
        with self.assertRaises(ValidationError) as ctx:
            case_bad_spo2.full_clean()
        self.assertIn('oxygen_saturation', ctx.exception.message_dict)


class CaseLabResultModelTests(TestCase):
    """
    Unit tests for structured quantitative laboratory panels and citation properties.
    """
    def setUp(self):
        self.physician = User.objects.create_user(
            email='physician.labs@hospital.org',
            password='Password123!',
            full_name='Dr. Labs Physician',
            role=Role.PRIMARY_PHYSICIAN
        )
        self.case = Case.objects.create(
            owner=self.physician,
            title='Hematology Case',
            clinical_summary='Patient with refractory anemia and severe fatigue.',
            history='No family history of hemoglobinopathy.',
            findings='Marked pallor, no palpable hepatosplenomegaly.'
        )

    def test_create_lab_result_with_flags(self):
        lab = CaseLabResult.objects.create(
            case=self.case,
            test_name='Serum Ferritin',
            value='4200',
            unit='ng/mL',
            reference_range='15 - 200 ng/mL',
            flag=LabFlag.CRITICAL
        )
        self.assertEqual(lab.flag, LabFlag.CRITICAL)
        self.assertIn('Serum Ferritin: 4200 ng/mL', str(lab))
        self.assertIn('Critical', str(lab))
        self.assertIn('[CRITICAL]', lab.citation_text)
        self.assertIn('Ref: 15 - 200 ng/mL', lab.citation_text)

    def test_cascade_delete_with_case(self):
        CaseLabResult.objects.create(
            case=self.case,
            test_name='Hemoglobin',
            value='7.2',
            unit='g/dL',
            flag=LabFlag.CRITICAL
        )
        self.assertEqual(self.case.lab_results.count(), 1)
        self.case.delete()
        self.assertEqual(CaseLabResult.objects.count(), 0)


class StructuredFindingsViewTests(TestCase):
    """
    Integration tests for case creation with vitals & labs, workspace rendering, and findings updates.
    """
    def setUp(self):
        self.client = Client()
        self.physician = User.objects.create_user(
            email='dr.caseowner@hospital.org',
            password='Password123!',
            full_name='Dr. Case Owner',
            role=Role.PRIMARY_PHYSICIAN
        )
        self.specialist = User.objects.create_user(
            email='dr.specialist@hospital.org',
            password='Password123!',
            full_name='Dr. Consultant Specialist',
            role=Role.SPECIALIST
        )

    def test_create_case_with_vitals_and_structured_labs(self):
        self.client.login(email='dr.caseowner@hospital.org', password='Password123!')

        lab_payload = [
            {
                'test_name': 'Serum Ferritin',
                'value': '4200',
                'unit': 'ng/mL',
                'reference_range': '15 - 200 ng/mL',
                'flag': 'CRITICAL'
            },
            {
                'test_name': 'WBC',
                'value': '18.5',
                'unit': 'x10^9/L',
                'reference_range': '4.5 - 11.0',
                'flag': 'HIGH'
            }
        ]

        response = self.client.post(reverse('cases:case_create'), {
            'title': 'Systemic Still Disease Suspected',
            'clinical_summary': 'Quotidian spiking fevers, evanescent macular rash, arthralgias.',
            'history': 'Previous antibiotic therapy ineffective; no tick exposure or foreign travel.',
            'findings': 'Evanescent salmon-colored macular rash observed on trunk during febrile spikes.',
            'temperature_c': '39.4',
            'heart_rate_bpm': '108',
            'bp_systolic': '115',
            'bp_diastolic': '75',
            'respiratory_rate': '18',
            'oxygen_saturation': '98',
            'lab_data_json': json.dumps(lab_payload)
        })

        self.assertEqual(response.status_code, 302)
        created_case = Case.objects.get(title='Systemic Still Disease Suspected')
        self.assertEqual(created_case.temperature_c, Decimal('39.4'))
        self.assertEqual(created_case.heart_rate_bpm, 108)
        self.assertEqual(created_case.lab_results.count(), 2)

        ferritin_lab = created_case.lab_results.get(test_name='Serum Ferritin')
        self.assertEqual(ferritin_lab.value, '4200')
        self.assertEqual(ferritin_lab.flag, LabFlag.CRITICAL)

        # Verify audit log details
        audit_entry = AuditLog.objects.filter(case_id=created_case.id, action=AuditAction.CASE_CREATED).first()
        self.assertIsNotNone(audit_entry)
        self.assertTrue(audit_entry.details.get('has_vitals'))

    def test_workspace_displays_structured_findings_and_citation_actions(self):
        case = Case.objects.create(
            owner=self.physician,
            title='Workspace Display Test Case',
            clinical_summary='Patient presentation for workspace UI testing.',
            history='Past medical history for workspace UI testing.',
            findings='Palpable splenomegaly.',
            temperature_c=Decimal('38.8'),
            heart_rate_bpm=102,
            bp_systolic=130,
            bp_diastolic=85,
            respiratory_rate=18,
            oxygen_saturation=97
        )
        CaseLabResult.objects.create(
            case=case,
            test_name='C-Reactive Protein (CRP)',
            value='95',
            unit='mg/L',
            reference_range='< 5 mg/L',
            flag=LabFlag.HIGH
        )
        CaseTeam.objects.create(case=case, specialist=self.specialist, admitted_by=self.physician)

        # Login as admitted specialist
        self.client.login(email='dr.specialist@hospital.org', password='Password123!')
        response = self.client.get(reverse('cases:workspace', kwargs={'case_id': case.id}))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Bedside Vitals', content)
        self.assertIn('38.8 °C', content)
        self.assertIn('102 bpm', content)
        self.assertIn('C-Reactive Protein (CRP)', content)
        self.assertIn('95', content)
        self.assertIn('citeFinding', content)

    def test_case_owner_can_update_findings_and_append_labs(self):
        case = Case.objects.create(
            owner=self.physician,
            title='Findings Update Test Case',
            clinical_summary='Initial summary description.',
            history='Initial history details.',
            findings='Initial examination observations.',
            temperature_c=Decimal('37.2'),
            heart_rate_bpm=75
        )

        self.client.login(email='dr.caseowner@hospital.org', password='Password123!')

        new_lab_payload = [{
            'test_name': 'Blood Cultures x3',
            'value': 'Negative at 48 hours',
            'unit': '',
            'reference_range': 'No growth',
            'flag': 'NORMAL'
        }]

        response = self.client.post(
            reverse('cases:findings_update', kwargs={'case_id': case.id}),
            {
                'temperature_c': '39.2',
                'heart_rate_bpm': '112',
                'bp_systolic': '110',
                'bp_diastolic': '70',
                'respiratory_rate': '20',
                'oxygen_saturation': '96',
                'findings': 'Updated examination: fever spiked to 39.2C with recurrent trunk rash.',
                'lab_data_json': json.dumps(new_lab_payload)
            }
        )
        self.assertEqual(response.status_code, 302)

        case.refresh_from_db()
        self.assertEqual(case.temperature_c, Decimal('39.2'))
        self.assertEqual(case.heart_rate_bpm, 112)
        self.assertIn('fever spiked to 39.2C', case.findings)
        self.assertEqual(case.lab_results.count(), 1)

        # Verify audit log entry
        audit_entry = AuditLog.objects.filter(case_id=case.id, action=AuditAction.FINDINGS_UPDATED).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details.get('heart_rate_bpm'), 112)

    def test_non_owner_blocked_from_updating_findings(self):
        case = Case.objects.create(
            owner=self.physician,
            title='RBAC Findings Protection Case',
            clinical_summary='Summary for RBAC testing.',
            history='History for RBAC testing.',
            findings='Findings for RBAC testing.'
        )

        # Specialist attempts to post to findings update endpoint
        self.client.login(email='dr.specialist@hospital.org', password='Password123!')
        response = self.client.post(
            reverse('cases:findings_update', kwargs={'case_id': case.id}),
            {
                'temperature_c': '40.0',
                'findings': 'Specialist trying to overwrite findings unauthorized.'
            }
        )
        self.assertEqual(response.status_code, 403)
        case.refresh_from_db()
        self.assertIsNone(case.temperature_c)
