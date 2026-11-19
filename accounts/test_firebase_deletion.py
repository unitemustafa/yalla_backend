from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from firebase_admin import auth

from .deletion import permanently_delete_client_account
from .models import FirebaseAccountDeletion, SocialIdentity, User
from .tasks import cleanup_firebase_accounts_task


class FirebaseAccountDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="deletion-test",
            email="deletion@example.com",
            role=User.Role.CLIENT,
        )
        SocialIdentity.objects.create(
            user=self.user, firebase_uid="test-firebase-uid", provider="google"
        )

    def test_permanent_deletion_records_provider_cleanup_before_unlinking(self):
        with patch("accounts.tasks.cleanup_firebase_accounts_task.delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                permanently_delete_client_account(self.user)
        self.assertFalse(self.user.social_identities.exists())
        self.assertTrue(
            FirebaseAccountDeletion.objects.filter(
                firebase_uid="test-firebase-uid"
            ).exists()
        )
        enqueue.assert_called_once_with()

    def test_broker_outage_preserves_receipt_without_failing_local_deletion(self):
        with patch(
            "accounts.tasks.cleanup_firebase_accounts_task.delay",
            side_effect=ConnectionError,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                permanently_delete_client_account(self.user)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(FirebaseAccountDeletion.objects.count(), 1)

    def test_rollback_does_not_schedule_or_persist_provider_deletion(self):
        with patch("accounts.tasks.cleanup_firebase_accounts_task.delay") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError), transaction.atomic():
                    permanently_delete_client_account(self.user)
                    raise RuntimeError("rollback")
        enqueue.assert_not_called()
        self.assertFalse(FirebaseAccountDeletion.objects.exists())
        self.assertTrue(SocialIdentity.objects.filter(user=self.user).exists())

    def _receipt(self):
        SocialIdentity.objects.all().delete()
        return FirebaseAccountDeletion.objects.create(firebase_uid="test-firebase-uid")

    @patch("config.firebase_admin.get_firebase_app", return_value="test-app")
    @patch("firebase_admin.auth.delete_user")
    def test_worker_removes_provider_identity_and_receipt(self, delete_user, _app):
        self._receipt()
        result = cleanup_firebase_accounts_task()
        delete_user.assert_called_once_with("test-firebase-uid", app="test-app")
        self.assertEqual(result, {"deleted": 1, "pending": 0})

    @patch("config.firebase_admin.get_firebase_app", return_value="test-app")
    @patch("firebase_admin.auth.delete_user", side_effect=ConnectionError)
    def test_provider_outage_keeps_receipt_for_next_periodic_attempt(self, delete, app):
        self._receipt()
        self.assertEqual(cleanup_firebase_accounts_task()["pending"], 1)
        delete.side_effect = None
        self.assertEqual(cleanup_firebase_accounts_task(), {"deleted": 1, "pending": 0})

    @patch("config.firebase_admin.get_firebase_app", return_value="test-app")
    @patch("firebase_admin.auth.delete_user")
    def test_missing_provider_identity_is_idempotent(self, delete_user, _app):
        self._receipt()
        delete_user.side_effect = auth.UserNotFoundError("Already deleted")
        self.assertEqual(cleanup_firebase_accounts_task(), {"deleted": 1, "pending": 0})

    @patch("config.firebase_admin.get_firebase_app", return_value="test-app")
    @patch("firebase_admin.auth.delete_user")
    def test_new_registration_is_not_deleted_by_an_old_receipt(self, delete_user, _app):
        FirebaseAccountDeletion.objects.create(firebase_uid="test-firebase-uid")
        cleanup_firebase_accounts_task()
        delete_user.assert_not_called()
        self.assertFalse(FirebaseAccountDeletion.objects.exists())

    @patch("config.firebase_admin.get_firebase_app", side_effect=RuntimeError)
    def test_missing_configuration_does_not_lose_pending_work(self, _app):
        self._receipt()
        with self.assertRaises(RuntimeError):
            cleanup_firebase_accounts_task()
        self.assertEqual(FirebaseAccountDeletion.objects.count(), 1)
