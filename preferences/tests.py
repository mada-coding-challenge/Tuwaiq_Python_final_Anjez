from django.test import TestCase
from django.contrib.auth.models import User

from .models import PersonalItem


class PersonalItemTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="test12345"
        )

    def test_create_personal_item(self):
        item = PersonalItem.objects.create(
            user=self.user,
            title="تعلم بايثون",
            category=PersonalItem.Category.LEARNING,
        )

        self.assertEqual(item.title, "تعلم بايثون")
        self.assertEqual(item.user, self.user)
        self.assertTrue(item.is_active)

    def test_archive_personal_item(self):
        item = PersonalItem.objects.create(
            user=self.user,
            title="قراءة كتاب",
            category=PersonalItem.Category.INTEREST,
        )

        item.is_active = False
        item.save()

        item.refresh_from_db()

        self.assertFalse(item.is_active)