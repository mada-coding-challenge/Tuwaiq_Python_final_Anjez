from django.conf import settings
from django.db import models


class PersonalItem(models.Model):

    class Category(models.TextChoices):
        INTEREST = "interest", "اهتمام"
        LEARNING = "learning", "شيء أريد تعلّمه"
        RELIGIOUS = "religious", "عادة دينية"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_items",
    )

    title = models.CharField(max_length=100)

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "title"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "category", "title"],
                name="unique_user_category_title",
            )
        ]

    def __str__(self):
        return self.title


class DrawSession(models.Model):

    class Status(models.TextChoices):
        SUGGESTED = "suggested", "تم اختياره"
        RUNNING = "running", "قيد التنفيذ"
        COMPLETED = "completed", "منجز"
        CANCELLED = "cancelled", "ملغى"
        ENDED = "ended", "انتهت بمغادرة الصفحة"

    item = models.ForeignKey(
        PersonalItem,
        on_delete=models.PROTECT,
        related_name="draw_sessions",
    )

    reason = models.TextField(max_length=600)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUGGESTED,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    spent_seconds = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.item.title
    
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    image = models.ImageField(
        upload_to="profile_images/",
        default="profile_images/default.jpg"
    )

    def __str__(self):
        return self.user.username