import logging
from datetime import datetime, time, timedelta
from urllib.parse import urlencode
from django.http import Http404, JsonResponse
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import ProtectedError
from .ai import choose_activity
from django.core.paginator import Paginator
from .forms import (
    AvailableTimeForm,
    PersonalItemForm,
    PreferencesForm,
    ProfileImageForm,
)
from .models import DrawSession, PersonalItem, UserProfile


logger = logging.getLogger(__name__)

TOKEN_SALT = "activity-timer"


# -------------------------
# دوال مساعدة للمؤقت
# -------------------------

def timer_cookie_name(draw):
    return f"draw_timer_{draw.pk}"


def activity_url(draw, token):
    url = reverse(
        "preferences:activity",
        kwargs={"pk": draw.pk},
    )

    return url + "?" + urlencode({"token": token})


def read_timer_token(request, draw):
    if request.method == "POST":
        supplied_token = request.POST.get("token")
    else:
        supplied_token = request.GET.get("token")

    token = supplied_token or request.COOKIES.get(
        timer_cookie_name(draw),
        "",
    )

    try:
        data = signing.loads(
            token,
            salt=TOKEN_SALT,
            max_age=86400,
        )

        minutes = data.get("minutes")

        if (
            data.get("draw_id") != draw.pk
            or type(minutes) is not int
            or not 5 <= minutes <= 240
        ):
            raise signing.BadSignature

    except (
        signing.BadSignature,
        AttributeError,
        TypeError,
    ):
        raise Http404(
            "رابط المؤقت غير صالح أو انتهت صلاحيته."
        )

    return token, minutes


def calculate_spent_seconds(draw, minutes, now):
    if draw.started_at is None:
        return 0

    elapsed = max(
        0,
        int(
            (now - draw.started_at)
            .total_seconds()
        ),
    )

    return min(elapsed, minutes * 60)


# -------------------------
# الرئيسية والحسابات
# -------------------------

def home(request):
    # الرئيسية لا تتطلب تسجيل الدخول.
    return render(
        request,
        "preferences/home.html",
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("preferences:suggest")

    form = UserCreationForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        user = form.save()

        login(request, user)

        return redirect("preferences:setup")

    return render(
        request,
        "registration/signup.html",
        {"form": form},
    )


# -------------------------
# إدخال الاختيارات
# -------------------------

@login_required
def setup_preferences(request):
    categories = {
        "interests": PersonalItem.Category.INTEREST,
        "learning": PersonalItem.Category.LEARNING,
        "religious": PersonalItem.Category.RELIGIOUS,
    }

    if request.method == "POST":
        form = PreferencesForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                for field_name, category in categories.items():
                    titles = form.cleaned_data[field_name]

                    # أرشفة العناصر التي أزالها المستخدم.
                    PersonalItem.objects.filter(
                        user=request.user,
                        category=category,
                        is_active=True,
                    ).exclude(
                        title__in=titles,
                    ).update(
                        is_active=False,
                    )

                    # إضافة الجديد أو إعادة تفعيل الموجود.
                    for title in titles:
                        PersonalItem.objects.update_or_create(
                            user=request.user,
                            category=category,
                            title=title,
                            defaults={"is_active": True},
                        )

            messages.success(
                request,
                "تم حفظ اختياراتك.",
            )

            return redirect("preferences:suggest")

    else:
        initial = {}

        for field_name, category in categories.items():
            titles = PersonalItem.objects.filter(
                user=request.user,
                category=category,
                is_active=True,
            ).values_list(
                "title",
                flat=True,
            )

            initial[field_name] = "\n".join(titles)

        form = PreferencesForm(initial=initial)

    return render(
        request,
        "preferences/setup.html",
        {"form": form},
    )


# -------------------------
# الملف الشخصي والبحث
# -------------------------

@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        image_form = ProfileImageForm(
            request.POST,
            request.FILES,
            instance=user_profile,
        )

        if image_form.is_valid():
            image_form.save()

            messages.success(
                request,
                "تم تحديث الصورة الشخصية بنجاح.",
            )

            return redirect("preferences:profile")

    else:
        image_form = ProfileImageForm(
            instance=user_profile
        )

    items = PersonalItem.objects.filter(
        user=request.user,
    )
    items = PersonalItem.objects.filter(
        user=request.user,
    )

    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    state = request.GET.get("state", "active")

    if state not in ("active", "archived", "all"):
        state = "active"

    if state == "active":
        items = items.filter(is_active=True)

    elif state == "archived":
        items = items.filter(is_active=False)

    if query:
        items = items.filter(
            title__icontains=query,
        )

    if category in PersonalItem.Category.values:
        items = items.filter(
            category=category,
        )
    else:
        category = ""

    # نعرض الاقتراحات التي لم تبدأ فقط.
    # الجلسة الجارية تنتهي عند مغادرة صفحة المؤقت.
    pending_sessions = DrawSession.objects.filter(
        item__user=request.user,
        status=DrawSession.Status.SUGGESTED,
    ).select_related("item")

    return render(
        request,
        "preferences/profile.html",
        {
            "items": items,
            "query": query,
            "category": category,
            "state": state,
            "categories": PersonalItem.Category.choices,
            "pending_sessions": pending_sessions,
            "user_profile": user_profile,
"image_form": image_form,
        },
    )


# -------------------------
# تعديل النشاط وأرشفته
# -------------------------

@login_required
def item_edit(request, pk):
    item = get_object_or_404(
        PersonalItem,
        pk=pk,
        user=request.user,
    )

    form = PersonalItemForm(
        request.POST if request.method == "POST" else None,
        instance=item,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(
            request,
            "تم تعديل النشاط مع الاحتفاظ بإنجازاته.",
        )

        return redirect("preferences:profile")

    return render(
        request,
        "preferences/item_edit.html",
        {"form": form},
    )


@login_required
def item_archive(request, pk):
    item = get_object_or_404(
        PersonalItem,
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        item.is_active = not item.is_active

        item.save(
            update_fields=["is_active"],
        )

        messages.success(
            request,
            "تم تحديث حالة النشاط. إنجازاته محفوظة.",
        )

        return redirect("preferences:profile")

    return render(
        request,
        "preferences/confirm.html",
        {
            "title": (
                "أرشفة النشاط"
                if item.is_active
                else "استعادة النشاط"
            ),
            "object_name": item.title,
            "description": (
                "أرشفة النشاط تمنع ظهوره في القرعة، "
                "وتبقى إنجازاته محفوظة."
            ),
        },
    )


# -------------------------
# اختيار النشاط بالذكاء
# -------------------------

@login_required
def suggest_activity(request):
    items = list(
        PersonalItem.objects.filter(
            user=request.user,
            is_active=True,
        )
    )

    if not items:
        messages.info(
            request,
            "أضف اختياراتك أولًا أو استعد نشاطًا مؤرشفًا.",
        )

        return redirect("preferences:setup")

    form = AvailableTimeForm(
        request.POST if request.method == "POST" else None,
        initial={
            "minutes": request.GET.get("minutes"),
        },
    )

    previous_draw_id = (
        request.POST.get("previous_draw")
        if request.method == "POST"
        else request.GET.get("previous_draw")
    )

    previous_draw = None

    if previous_draw_id:
        try:
            previous_draw_id = int(previous_draw_id)

        except (TypeError, ValueError):
            raise Http404("الاقتراح السابق غير صالح.")

        previous_draw = get_object_or_404(
            DrawSession,
            pk=previous_draw_id,
            item__user=request.user,
            status=DrawSession.Status.SUGGESTED,
        )

    if request.method == "POST" and form.is_valid():
        minutes = form.cleaned_data["minutes"]

        candidates = [
            item
            for item in items
            if (
                previous_draw is None
                or item.pk != previous_draw.item_id
            )
        ]

        if not candidates:
            form.add_error(
                None,
                "لا يوجد نشاط آخر. أضف اختيارًا جديدًا.",
            )

        else:
            try:
                item_id, reason = choose_activity(
                    candidates,
                    minutes,
                )

            except ValueError as error:
                form.add_error(
                    None,
                    str(error),
                )

            except Exception:
                logger.exception(
                    "Activity selection failed"
                )

                form.add_error(
                    None,
                    "تعذر تنفيذ القرعة. حاول مجددًا.",
                )

            else:
                # تأكيد أن الاختيار من قائمة المستخدم.
                selected_item = next(
                    (
                        item
                        for item in candidates
                        if item.pk == item_id
                    ),
                    None,
                )

                if selected_item is None:
                    form.add_error(
                        None,
                        "الاختيار ليس من قائمتك.",
                    )

                else:
                    with transaction.atomic():
                        draw = DrawSession.objects.create(
                            item=selected_item,
                            reason=reason,
                        )

                        if previous_draw:
                            DrawSession.objects.filter(
                                pk=previous_draw.pk,
                                status=DrawSession.Status.SUGGESTED,
                            ).update(
                                status=DrawSession.Status.CANCELLED,
                            )

                    # الوقت داخل توكن موقّع، وليس حقلًا للنشاط.
                    token = signing.dumps(
                        {
                            "draw_id": draw.pk,
                            "minutes": minutes,
                        },
                        salt=TOKEN_SALT,
                    )

                    response = redirect(
                        activity_url(draw, token)
                    )

                    # يسمح بفتح الاقتراح قبل بدء المؤقت.
                    response.set_cookie(
                        timer_cookie_name(draw),
                        token,
                        max_age=86400,
                        httponly=True,
                        samesite="Lax",
                        secure=request.is_secure(),
                    )

                    return response

    return render(
        request,
        "preferences/suggest.html",
        {
            "form": form,
            "previous_draw_id": previous_draw_id,
        },
    )


# -------------------------
# عرض النشاط والمؤقت
# -------------------------

@login_required
def activity_detail(request, pk):
    draw = get_object_or_404(
        DrawSession.objects.select_related("item"),
        pk=pk,
        item__user=request.user,
    )

    if draw.status in (
        DrawSession.Status.COMPLETED,
        DrawSession.Status.ENDED,
    ):
        return redirect("preferences:achievements")

    if draw.status == DrawSession.Status.CANCELLED:
        return redirect("preferences:profile")

    try:
        token, minutes = read_timer_token(
            request,
            draw,
        )

    except Http404:
        return render(
            request,
            "preferences/timer_unavailable.html",
            {"draw": draw},
        )

    remaining_seconds = minutes * 60

    if draw.status == DrawSession.Status.RUNNING:
        elapsed = max(
            0,
            int(
                (timezone.now() - draw.started_at)
                .total_seconds()
            ),
        )

        remaining_seconds = max(
            0,
            remaining_seconds - elapsed,
        )

    again_url = (
        reverse("preferences:suggest")
        + "?"
        + urlencode(
            {
                "minutes": minutes,
                "previous_draw": draw.pk,
            }
        )
    )

    return render(
        request,
        "preferences/activity.html",
        {
            "draw": draw,
            "token": token,
            "minutes": minutes,
            "remaining_seconds": remaining_seconds,
            "again_url": again_url,
        },
    )


# -------------------------
# بدء الجلسة
# -------------------------

@login_required
@require_POST
def start_activity(request, pk):
    draw = get_object_or_404(
        DrawSession,
        pk=pk,
        item__user=request.user,
    )

    if draw.status in (
        DrawSession.Status.COMPLETED,
        DrawSession.Status.ENDED,
        DrawSession.Status.CANCELLED,
    ):
        return redirect("preferences:achievements")

    token, minutes = read_timer_token(
        request,
        draw,
    )

    another_running = DrawSession.objects.filter(
        item__user=request.user,
        status=DrawSession.Status.RUNNING,
    ).exclude(
        pk=draw.pk,
    ).exists()

    if another_running:
        messages.info(
            request,
            "أنهِ الجلسة الجارية أو ألغها قبل بدء نشاط آخر.",
        )

        return redirect("preferences:suggest")

    if not draw.item.is_active:
        messages.info(
            request,
            "هذا النشاط مؤرشف. استعده قبل البدء.",
        )

        return redirect("preferences:profile")

    # الضغط مرتين لا يعيد وقت البداية.
    DrawSession.objects.filter(
        pk=draw.pk,
        status=DrawSession.Status.SUGGESTED,
    ).update(
        status=DrawSession.Status.RUNNING,
        started_at=timezone.now(),
    )

    return redirect(
        activity_url(draw, token)
    )


# -------------------------
# تأكيد الإنجاز
# -------------------------

@login_required
@require_POST
def complete_activity(request, pk):
    draw = get_object_or_404(
        DrawSession,
        pk=pk,
        item__user=request.user,
    )

    if draw.status != DrawSession.Status.RUNNING:
        return redirect("preferences:achievements")

    _, minutes = read_timer_token(
        request,
        draw,
    )

    now = timezone.now()

    spent_seconds = calculate_spent_seconds(
        draw,
        minutes,
        now,
    )

    updated = DrawSession.objects.filter(
        pk=draw.pk,
        status=DrawSession.Status.RUNNING,
    ).update(
        status=DrawSession.Status.COMPLETED,
        completed_at=now,
        spent_seconds=spent_seconds,
    )

    if updated:
        messages.success(
            request,
            "تم تسجيل إنجازك.",
        )

    response = redirect("preferences:achievements")

    response.delete_cookie(
        timer_cookie_name(draw)
    )

    return response


# -------------------------
# إنهاء الجلسة عند المغادرة
# -------------------------

@login_required
@require_POST
def end_activity(request, pk):
    draw = get_object_or_404(
        DrawSession,
        pk=pk,
        item__user=request.user,
    )

    if draw.status != DrawSession.Status.RUNNING:
        return JsonResponse(
            {"saved": True}
        )

    _, minutes = read_timer_token(
        request,
        draw,
    )

    now = timezone.now()

    spent_seconds = calculate_spent_seconds(
        draw,
        minutes,
        now,
    )

    updated = DrawSession.objects.filter(
        pk=draw.pk,
        status=DrawSession.Status.RUNNING,
    ).update(
        status=DrawSession.Status.ENDED,
        completed_at=now,
        spent_seconds=spent_seconds,
    )

    response = JsonResponse(
        {"saved": bool(updated)}
    )

    response.delete_cookie(
        timer_cookie_name(draw)
    )

    return response


# -------------------------
# إلغاء الجلسة بتأكيد المستخدم
# -------------------------

@login_required
def cancel_activity(request, pk):
    draw = get_object_or_404(
        DrawSession.objects.select_related("item"),
        pk=pk,
        item__user=request.user,
    )

    if request.method == "POST":
        updated = DrawSession.objects.filter(
            pk=draw.pk,
            status__in=[
                DrawSession.Status.SUGGESTED,
                DrawSession.Status.RUNNING,
            ],
        ).update(
            status=DrawSession.Status.CANCELLED,
        )

        if updated:
            messages.success(
                request,
                "أُلغيت الجلسة دون إضافة وقتها للإنجاز.",
            )

        else:
            messages.info(
                request,
                "الجلسة انتهت بالفعل؛ لم يتم تغيير وقتها المسجل.",
            )

        response = redirect("preferences:profile")

        response.delete_cookie(
            timer_cookie_name(draw)
        )

        return response

    return render(
        request,
        "preferences/confirm.html",
        {
            "title": "إلغاء الجلسة",
            "object_name": draw.item.title,
            "description": (
                "إذا كانت الجلسة لم تنتهِ، "
                "فسيتم إلغاؤها دون احتساب وقتها. "
                "الجلسات المنتهية لا تتأثر."
            ),
        },
    )


# -------------------------
# تقرير الإنجاز
# -------------------------

@login_required
def achievements(request):
    today = timezone.localdate()

    starts = {
        "week": today - timedelta(
            days=today.weekday()
        ),
        "month": today.replace(day=1),
        "year": today.replace(
            month=1,
            day=1,
        ),
    }

    period = request.GET.get("period", "week")

    if period not in starts:
        period = "week"

    start_at = timezone.make_aware(
        datetime.combine(
            starts[period],
            time.min,
        )
    )

    end_at = timezone.make_aware(
        datetime.combine(
            today + timedelta(days=1),
            time.min,
        )
    )

    sessions = DrawSession.objects.filter(
        item__user=request.user,
        status__in=[
            DrawSession.Status.COMPLETED,
            DrawSession.Status.ENDED,
        ],
        completed_at__gte=start_at,
        completed_at__lt=end_at,
    )

    query = request.GET.get("q", "").strip()[:100]

    if query:
        sessions = sessions.filter(
            item__title__icontains=query,
        )

    # Annotation: مجموع الوقت لكل نشاط.
    grouped = (
        sessions.order_by()
        .values(
            "item_id",
            "item__title",
        )
        .annotate(
            total_seconds=Sum("spent_seconds")
        )
        .order_by(
            "-total_seconds",
            "item__title",
        )
    )

    rows = [
        {
            "title": row["item__title"],
            "minutes": round(
                row["total_seconds"] / 60,
                1,
            ),
        }
        for row in grouped
    ]
    paginator = Paginator(rows, 3)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)
    # Aggregation: مجموع الوقت لجميع النتائج.
    total_seconds = (
        sessions.aggregate(
            total=Sum("spent_seconds")
        )["total"]
        or 0
    )

    return render(
        request,
        "preferences/achievements.html",
        {
            "rows": page_obj,
"page_obj": page_obj,
            "period": period,
            "query": query,
            "total_minutes": round(
                total_seconds / 60,
                1,
            ),
            "sessions_count": sessions.count(),
        },
    )
    
@login_required
def item_delete(request, pk):
    item = get_object_or_404(
        PersonalItem,
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        try:
            item.delete()

            messages.success(
                request,
                "تم حذف النشاط بنجاح.",
            )

            return redirect("preferences:profile")

        except ProtectedError:
            messages.error(
                request,
                "لا يمكن حذف هذا النشاط لأنه مرتبط بسجل إنجاز سابق. يمكنك أرشفته بدلاً من ذلك.",
            )

            return redirect("preferences:profile")

    return render(
        request,
        "preferences/confirm.html",
        {
            "title": "حذف النشاط",
            "object_name": item.title,
            "description": (
                "سيتم حذف هذا النشاط نهائيًا، "
                "ولن تتمكن من استعادته بعد الحذف."
            ),
        },
    )
    
