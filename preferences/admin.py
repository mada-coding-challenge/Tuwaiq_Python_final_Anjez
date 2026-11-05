from django.contrib import admin

from .models import PersonalItem


@admin.register(PersonalItem)
class PersonalItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "user",
        "is_active",
    )

    list_filter = ("category", "is_active")

    search_fields = ("title", "user__username")
    
from .models import DrawSession


@admin.register(DrawSession)
class DrawSessionAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "status",
        "started_at",
        "spent_seconds",
    )

    list_filter = ("status",)

    search_fields = ("item__title", "item__user__username")