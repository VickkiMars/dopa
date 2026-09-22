from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from django.core.cache import cache

from accounts.models import User, Role
from cases.models import Case, CaseTeam, CaseStatus, Notification
from cases.services.notification_service import notify_user, notify_case_team
from collaboration.models import Hypothesis


class NotificationServiceTests(TestCase):
    """
    Unit tests for the notification service core functions and email generation.
    """

    def setUp(self):
        cache.clear()
        mail.outbox = []

        self.physician = User.objects.create_user(
            email='lead.physician@hospital.org',
            full_name='Dr. Lead Physician',
            role=Role.PRIMARY_PHYSICIAN,
            password='ValidPassword123!'
        )
        self.specialist1 = User.objects.create_user(
            email='spec1@hospital.org',
            full_name='Dr. Spec One',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )
        self.specialist2 = User.objects.create_user(
            email='spec2@hospital.org',
            full_name='Dr. Spec Two',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )

        self.case = Case.objects.create(
            owner=self.physician,
            title='Complex Inflammatory Presentation',
            clinical_summary='Patient with systemic fever and arthralgia.',
            history='Previous episodes of pleurisy.',
            findings='Elevated inflammatory markers.',
            status=CaseStatus.OPEN
        )

    def test_notify_user_creates_record_and_delivers_email(self):
        """notify_user persists in-app notification and dispatches formatted email."""
        notif = notify_user(
            recipient=self.specialist1,
            verb='TEAM_ADMISSION',
            title='Admitted to Clinical Team',
            message='You have been invited to consult on this case.',
            case=self.case,
            action_url='/cases/test-url/',
            send_email=True
        )

        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(notif.recipient, self.specialist1)
        self.assertEqual(notif.verb, 'TEAM_ADMISSION')
        self.assertEqual(notif.title, 'Admitted to Clinical Team')
        self.assertEqual(notif.action_url, '/cases/test-url/')
        self.assertFalse(notif.is_read)

        # Email verification
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn('[DOPA] Admitted to Clinical Team', sent_email.subject)
        self.assertIn(self.specialist1.email, sent_email.to)
        self.assertIn('Dr. Spec One', sent_email.body)
        self.assertIn('Complex Inflammatory Presentation', sent_email.body)

    def test_notify_user_email_failure_is_non_blocking(self):
        """If email dispatch throws an exception, the in-app notification is still saved."""
        with patch('cases.services.notification_service.send_mail', side_effect=Exception("SMTP Connection Refused")):
            notif = notify_user(
                recipient=self.specialist1,
                verb='SYSTEM_ALERT',
                title='System Alert',
                message='Test alert.',
                send_email=True
            )
            # Notification is safely created without raising an exception
            self.assertIsNotNone(notif.id)
            self.assertEqual(Notification.objects.filter(id=notif.id).count(), 1)

    def test_notify_case_team_broadcasts_and_excludes_actor(self):
        """notify_case_team alerts all team participants while excluding the triggering user."""
        CaseTeam.objects.create(case=self.case, specialist=self.specialist1, admitted_by=self.physician)
        CaseTeam.objects.create(case=self.case, specialist=self.specialist2, admitted_by=self.physician)

        # Physician broadcasts an update; physician should be excluded
        dispatched = notify_case_team(
            case=self.case,
            verb='RANK_UPDATED',
            title='Ranking Updated',
            message='Differential rankings updated.',
            exclude_user=self.physician,
            send_email=False
        )

        self.assertEqual(len(dispatched), 2)
        recipients = {n.recipient for n in dispatched}
        self.assertEqual(recipients, {self.specialist1, self.specialist2})
        self.assertNotIn(self.physician, recipients)


class ClinicalLifecycleNotificationTests(TestCase):
    """
    Integration tests verifying notification & email triggers across case lifecycle events.
    """

    def setUp(self):
        self.client = Client()
        cache.clear()
        mail.outbox = []

        self.physician = User.objects.create_user(
            email='physician.life@hospital.org',
            full_name='Dr. Amina Bello',
            role=Role.PRIMARY_PHYSICIAN,
            password='ValidPassword123!'
        )
        self.specialist = User.objects.create_user(
            email='specialist.life@hospital.org',
            full_name='Dr. Kofi Mensah',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )

        self.case = Case.objects.create(
            owner=self.physician,
            title='Atypical Progressive Ataxia',
            clinical_summary='Subacute onset cerebellar symptoms.',
            history='No toxic exposures.',
            findings='Normal CSF cell count.',
            status=CaseStatus.OPEN
        )

    def test_team_admission_triggers_notification_and_email(self):
        """Primary Physician admitting Specialist triggers in-app alert and email (FAULT-07, B12)."""
        self.client.force_login(self.physician)
        admit_url = reverse('cases:team_admit', kwargs={'case_id': self.case.id})

        response = self.client.post(admit_url, {'specialist_email': self.specialist.email})
        self.assertRedirects(response, admit_url)

        # In-app notification created for Specialist
        notif = Notification.objects.filter(recipient=self.specialist, verb='TEAM_ADMISSION').first()
        self.assertIsNotNone(notif)
        self.assertIn('Dr. Amina Bello has admitted you', notif.message)
        self.assertIn(str(self.case.id), notif.action_url)

        # Email delivered
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.specialist.email])
        self.assertIn('Admitted to Clinical Case Team', mail.outbox[0].subject)

    def test_hypothesis_submission_triggers_notification_and_email(self):
        """Admitted Specialist submitting hypothesis alerts Case Owner (FR-NOTIFY-01)."""
        CaseTeam.objects.create(case=self.case, specialist=self.specialist, admitted_by=self.physician)
        self.client.force_login(self.specialist)

        hypo_url = reverse('collaboration:hypothesis_create', kwargs={'case_id': self.case.id})
        payload = {
            'proposed_diagnosis': 'Paraneoplastic Cerebellar Degeneration',
            'rationale': 'Rapid progression warrants searching for occult malignancy.',
            'supporting_evidence': 'Presence of anti-Yo on paraneoplastic autoantibody panel.',
            'idempotency_token': 'test-token-hypo-1'
        }
        response = self.client.post(hypo_url, payload)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # In-app notification for Physician
        notif = Notification.objects.filter(recipient=self.physician, verb='HYPOTHESIS_SUBMITTED').first()
        self.assertIsNotNone(notif)
        self.assertIn('Paraneoplastic Cerebellar Degeneration', notif.message)

        # Email delivered
        self.assertTrue(len(mail.outbox) >= 1)
        self.assertEqual(mail.outbox[-1].to, [self.physician.email])

    def test_discussion_note_triggers_notification(self):
        """Posting a discussion note alerts other team members (FR-NOTIFY-01)."""
        CaseTeam.objects.create(case=self.case, specialist=self.specialist, admitted_by=self.physician)
        self.client.force_login(self.specialist)

        note_url = reverse('collaboration:note_create', kwargs={'case_id': self.case.id})
        payload = {
            'body': 'Consider ordering a full-body PET/CT scan.',
            'idempotency_token': 'test-token-note-1'
        }
        response = self.client.post(note_url, payload)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Notification created for Physician
        notif = Notification.objects.filter(recipient=self.physician, verb='DISCUSSION_POSTED').first()
        self.assertIsNotNone(notif)
        self.assertIn('Dr. Kofi Mensah', notif.message)

    def test_decision_record_triggers_notification_and_email(self):
        """Recording final decision notifies all admitted Specialists with case closed alert."""
        CaseTeam.objects.create(case=self.case, specialist=self.specialist, admitted_by=self.physician)
        self.case.status = CaseStatus.UNDER_REVIEW
        self.case.save()

        self.client.force_login(self.physician)
        decision_url = reverse('cases:decision_record', kwargs={'case_id': self.case.id})
        payload = {
            'final_diagnosis': 'Paraneoplastic Cerebellar Degeneration (Anti-Yo Positive)',
            'treatment_plan': 'High-dose methylprednisolone pulse therapy followed by IVIG.',
            'diagnostic_justification': 'Autoantibodies confirmed; CT identified pelvic mass.',
            'advisory_acknowledged': True,
            'idempotency_token': 'test-token-dec-1'
        }
        response = self.client.post(decision_url, payload)
        self.assertRedirects(response, reverse('cases:workspace', kwargs={'case_id': self.case.id}))

        # Notification for Specialist
        notif = Notification.objects.filter(recipient=self.specialist, verb='DECISION_RECORDED').first()
        self.assertIsNotNone(notif)
        self.assertIn('Case Closed', notif.title)
        self.assertIn('Paraneoplastic Cerebellar Degeneration', notif.message)

        # Email delivered to Specialist
        self.assertTrue(len(mail.outbox) >= 1)
        self.assertEqual(mail.outbox[-1].to, [self.specialist.email])


class NotificationInboxAndContextTests(TestCase):
    """
    Tests for the notification center list, mark-as-read actions, IDOR security, and context processor.
    """

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            email='user1@hospital.org',
            full_name='Dr. User One',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )
        self.user2 = User.objects.create_user(
            email='user2@hospital.org',
            full_name='Dr. User Two',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )

        self.notif1 = Notification.objects.create(
            recipient=self.user1,
            verb='ALERT',
            title='Alert 1',
            message='Message 1',
            action_url='/dashboard/',
            is_read=False
        )
        self.notif2 = Notification.objects.create(
            recipient=self.user1,
            verb='ALERT',
            title='Alert 2',
            message='Message 2',
            is_read=False
        )
        self.notif_other = Notification.objects.create(
            recipient=self.user2,
            verb='ALERT',
            title='Alert Other',
            message='Message Other',
            is_read=False
        )

    def test_notifications_list_view_renders_user_alerts(self):
        """Notification list displays user's notifications and unread counter."""
        self.client.force_login(self.user1)
        response = self.client.get(reverse('cases:notifications_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alert 1')
        self.assertContains(response, 'Alert 2')
        self.assertNotContains(response, 'Alert Other')

    def test_notification_mark_read_navigates_to_action_url(self):
        """Mark read view flags notification as read and redirects to action_url."""
        self.client.force_login(self.user1)
        read_url = reverse('cases:notification_read', kwargs={'notification_id': self.notif1.id})

        response = self.client.get(read_url)
        self.assertRedirects(response, '/dashboard/')

        self.notif1.refresh_from_db()
        self.assertTrue(self.notif1.is_read)
        self.assertIsNotNone(self.notif1.read_at)

    def test_notification_mark_read_idor_rejection(self):
        """Users cannot access or mark read another user's notifications."""
        self.client.force_login(self.user1)
        # Attempt to mark read user2's notification
        read_url = reverse('cases:notification_read', kwargs={'notification_id': self.notif_other.id})
        response = self.client.get(read_url)
        self.assertEqual(response.status_code, 404)

        self.notif_other.refresh_from_db()
        self.assertFalse(self.notif_other.is_read)

    def test_notification_mark_all_read(self):
        """Bulk mark all read endpoint marks all unread notifications for authenticated user."""
        self.client.force_login(self.user1)
        response = self.client.post(reverse('cases:notification_mark_all_read'), follow=True)
        self.assertEqual(response.status_code, 200)

        self.notif1.refresh_from_db()
        self.notif2.refresh_from_db()
        self.assertTrue(self.notif1.is_read)
        self.assertTrue(self.notif2.is_read)

        # Other user's notification remains unread
        self.notif_other.refresh_from_db()
        self.assertFalse(self.notif_other.is_read)

    def test_context_processor_injects_unread_count(self):
        """Global context processor accurately injects unread_notifications_count in templates."""
        self.client.force_login(self.user1)
        response = self.client.get(reverse('cases:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['unread_notifications_count'], 2)

        # Unauthenticated returns 0
        self.client.logout()
        res_anon = self.client.get(reverse('accounts:login'))
        self.assertEqual(res_anon.context['unread_notifications_count'], 0)
