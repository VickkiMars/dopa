import io
import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from accounts.models import Role
from cases.models import Case, CaseTeam, CaseStatus, CaseAttachment, AttachmentCategory
from audit.models import AuditLog, AuditAction, AuditStatus

User = get_user_model()


class CaseAttachmentTests(TestCase):
    """
    Automated test suite for Case Diagnostic Media & File Attachments (FR2b, FR2d, NFR9, FT12, FT13):
    - FT12: Primary physician uploads valid clinical photo, radiology imaging, and PDF reports.
    - FT12b: File validation rejects disallowed MIME types and oversized files.
    - FT13: Admitted specialist accesses and streams diagnostic media inline.
    - FT13b: Unadmitted specialist / physician IDOR attempt blocked with HTTP 403 and ACCESS_DENIED.
    - Closed case immutability: upload rejected on closed cases.
    """

    def setUp(self):
        self.client = Client()

        # Primary Physicians
        self.physician = User.objects.create_user(
            email='dr.welby@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Marcus Welby',
            role=Role.PRIMARY_PHYSICIAN
        )
        self.other_physician = User.objects.create_user(
            email='dr.house@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Gregory House',
            role=Role.PRIMARY_PHYSICIAN
        )

        # Specialists
        self.admitted_specialist = User.objects.create_user(
            email='dr.sanders@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Lisa Sanders',
            role=Role.SPECIALIST
        )
        self.unadmitted_specialist = User.objects.create_user(
            email='dr.foreman@clinic.org',
            password='StrongPassword123!',
            full_name='Dr. Eric Foreman',
            role=Role.SPECIALIST
        )

        # Clinical Case
        self.case = Case.objects.create(
            owner=self.physician,
            title='Adult-Onset Still Disease Case Presentation',
            clinical_summary='Recurrent high fevers, arthralgia, and salmon-pink rash over 4 weeks.',
            history='No prior autoimmune disease, negative ANA/RF.',
            findings='Ferritin 4,200 ng/mL, WBC 18.5, hepatosplenomegaly on ultrasound.',
            status=CaseStatus.UNDER_REVIEW
        )

        # Team Admission
        self.membership = CaseTeam.objects.create(
            case=self.case,
            specialist=self.admitted_specialist,
            admitted_by=self.physician
        )

    # -------------------------------------------------------------------------
    # FT12: Primary Physician Uploads Diagnostic Media
    # -------------------------------------------------------------------------
    def test_ft12_case_owner_uploads_valid_clinical_photo(self):
        """
        FT12: Case owner uploads a JPEG clinical photo of the rash.
        File is persisted, size recorded, and ATTACHMENT_UPLOADED is logged.
        """
        self.client.login(email='dr.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        dummy_image = SimpleUploadedFile(
            name='salmon_rash.jpg',
            content=b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00' + b'A' * 200,
            content_type='image/jpeg'
        )

        payload = {
            'title': 'Evanescent Trunk Macular Rash at Peak Fever Spike',
            'category': AttachmentCategory.CLINICAL_PHOTO,
            'file': dummy_image
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Verify database record
        att = CaseAttachment.objects.filter(case=self.case, title=payload['title']).first()
        self.assertIsNotNone(att)
        self.assertEqual(att.uploaded_by, self.physician)
        self.assertEqual(att.category, AttachmentCategory.CLINICAL_PHOTO)
        self.assertEqual(att.mime_type, 'image/jpeg')
        self.assertGreater(att.file_size_bytes, 0)

        # Verify audit log
        audit = AuditLog.objects.filter(case_id=self.case.id, action=AuditAction.ATTACHMENT_UPLOADED).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.physician)
        self.assertEqual(audit.status, AuditStatus.ALLOWED)
        self.assertIn('salmon', att.file.name)

    def test_ft12_case_owner_uploads_pdf_report(self):
        """
        FT12: Case owner uploads a PDF pathology/lab report.
        """
        self.client.login(email='dr.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        dummy_pdf = SimpleUploadedFile(
            name='pathology_report.pdf',
            content=b'%PDF-1.4\n%...\n%%EOF',
            content_type='application/pdf'
        )

        payload = {
            'title': 'Formal Bone Marrow Biopsy Pathology Report',
            'category': AttachmentCategory.LAB_PDF,
            'file': dummy_pdf
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CaseAttachment.objects.filter(case=self.case, category=AttachmentCategory.LAB_PDF).exists())

    # -------------------------------------------------------------------------
    # FT12b: Rejection of Disallowed Formats & Malicious Payloads
    # -------------------------------------------------------------------------
    def test_ft12b_disallowed_file_extension_rejected(self):
        """
        FT12b: Attempted upload of an executable or scriptable file (.exe, .svg) is rejected with 400.
        """
        self.client.login(email='dr.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        malicious_file = SimpleUploadedFile(
            name='malicious_script.svg',
            content=b'<svg><script>alert("xss")</script></svg>',
            content_type='image/svg+xml'
        )

        payload = {
            'title': 'Vector Diagram',
            'category': AttachmentCategory.OTHER,
            'file': malicious_file
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CaseAttachment.objects.filter(case=self.case, title='Vector Diagram').exists())

    def test_ft12b_oversized_file_rejected(self):
        """
        FT12b: Files exceeding 10 MB limit are rejected with 400.
        """
        self.client.login(email='dr.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        # Simulate 11 MB file
        huge_file = SimpleUploadedFile(
            name='huge_scan.jpg',
            content=b'A' * (11 * 1024 * 1024),
            content_type='image/jpeg'
        )

        payload = {
            'title': 'Massive Raw Scan',
            'category': AttachmentCategory.RADIOLOGY,
            'file': huge_file
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CaseAttachment.objects.filter(case=self.case, title='Massive Raw Scan').exists())

    # -------------------------------------------------------------------------
    # FT13: Streaming & Access Gating for Admitted Specialists
    # -------------------------------------------------------------------------
    def test_ft13_admitted_specialist_streams_attachment(self):
        """
        FT13: Admitted specialist streams attachment inline; ATTACHMENT_ACCESSED is logged.
        """
        # Create attachment first
        attachment = CaseAttachment.objects.create(
            case=self.case,
            uploaded_by=self.physician,
            category=AttachmentCategory.WAVEFORM,
            title='20-Minute Routine EEG Waveform',
            file=SimpleUploadedFile('eeg.png', b'\x89PNG\r\n\x1a\n' + b'0' * 50, content_type='image/png'),
            mime_type='image/png',
            file_size_bytes=58
        )

        self.client.login(email='dr.sanders@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_download', kwargs={'case_id': self.case.id, 'attachment_id': attachment.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('inline', response['Content-Disposition'])

        # Verify audit log
        audit = AuditLog.objects.filter(case_id=self.case.id, action=AuditAction.ATTACHMENT_ACCESSED).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.admitted_specialist)
        self.assertEqual(audit.status, AuditStatus.ALLOWED)

    def test_ft13b_unadmitted_specialist_denied_from_attachment(self):
        """
        FT13b: Unadmitted specialist attempting to download attachment receives 403 Forbidden
        and triggers ACCESS_DENIED in the audit log.
        """
        attachment = CaseAttachment.objects.create(
            case=self.case,
            uploaded_by=self.physician,
            category=AttachmentCategory.RADIOLOGY,
            title='Pelvic MRI DICOM Export',
            file=SimpleUploadedFile('mri.jpg', b'\xFF\xD8\xFF' + b'0' * 50, content_type='image/jpeg'),
            mime_type='image/jpeg',
            file_size_bytes=53
        )

        self.client.login(email='dr.foreman@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_download', kwargs={'case_id': self.case.id, 'attachment_id': attachment.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Verify ACCESS_DENIED logged
        audit = AuditLog.objects.filter(case_id=self.case.id, action=AuditAction.ACCESS_DENIED, actor=self.unadmitted_specialist).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status, AuditStatus.DENIED)

    def test_non_owner_physician_cannot_upload_attachment(self):
        """
        A primary physician who does not own the case cannot upload attachments to it.
        """
        self.client.login(email='dr.house@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        dummy_image = SimpleUploadedFile('intruder.jpg', b'\xFF\xD8\xFF', content_type='image/jpeg')
        response = self.client.post(url, {
            'title': 'Intruder Diagnostic File',
            'category': AttachmentCategory.OTHER,
            'file': dummy_image
        })
        self.assertEqual(response.status_code, 403)

    def test_cannot_upload_attachment_to_closed_case(self):
        """
        Uploading attachments to a closed case is rejected with 403.
        """
        self.case.status = CaseStatus.CLOSED
        self.case.save()

        self.client.login(email='dr.welby@clinic.org', password='StrongPassword123!')
        url = reverse('cases:attachment_upload', kwargs={'case_id': self.case.id})

        dummy_image = SimpleUploadedFile('closed_test.jpg', b'\xFF\xD8\xFF', content_type='image/jpeg')
        response = self.client.post(url, {
            'title': 'Late Diagnostic File',
            'category': AttachmentCategory.OTHER,
            'file': dummy_image
        })
        self.assertEqual(response.status_code, 403)

    def test_case_attachment_str_representation(self):
        """
        Verify __str__ on CaseAttachment model.
        """
        att = CaseAttachment(
            case=self.case,
            uploaded_by=self.physician,
            category=AttachmentCategory.CLINICAL_PHOTO,
            title='Facial Rash',
            mime_type='image/jpeg',
            file_size_bytes=100
        )
        self.assertIn('Clinical Photo', str(att))
        self.assertIn('Facial Rash', str(att))
