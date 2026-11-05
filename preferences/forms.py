from django import forms


class PreferencesForm(forms.Form):
    interests = forms.CharField(
        label="ما اهتماماتك وهواياتك؟",
        required=False,
        max_length=3000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "الرسم\nالقراءة\nالتصوير",
            }
        ),
    )

    learning = forms.CharField(
        label="ما الأشياء التي تريد تعلّمها؟",
        required=False,
        max_length=3000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Python\nاللغة الإنجليزية\nالتصميم",
            }
        ),
    )

    religious = forms.CharField(
        label="ما العادات الدينية التي تريد متابعتها؟",
        required=False,
        max_length=3000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "قراءة القرآن\nأذكار الصباح",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        field_names = ("interests", "learning", "religious")

        has_items = False

        for field_name in field_names:
            text = cleaned_data.get(field_name, "")

            items = []

            for line in text.splitlines():
                title = line.strip()

                if not title:
                    continue

                if len(title) > 100:
                    self.add_error(
                        field_name,
                        "كل عنصر يجب ألا يتجاوز 100 حرف.",
                    )
                    continue

                if title not in items:
                    items.append(title)

            if len(items) > 20:
                self.add_error(
                    field_name,
                    "يمكنك إضافة 20 عنصرًا كحد أقصى في كل قسم.",
                )

            cleaned_data[field_name] = items

            if items:
                has_items = True

        if not has_items:
            raise forms.ValidationError(
                "أضف عنصرًا واحدًا على الأقل في أي قسم."
            )

        return cleaned_data
    
class AvailableTimeForm(forms.Form):
    minutes = forms.IntegerField(
        label="كم دقيقة متاحة لك؟",
        min_value=5,
        max_value=240,
        error_messages={
            "required": "أدخل الوقت المتاح لك.",
            "invalid": "أدخل عددًا صحيحًا من الدقائق.",
            "min_value": "أقل مدة هي 5 دقائق.",
            "max_value": "أكبر مدة هي 240 دقيقة.",
        },
        widget=forms.NumberInput(
            attrs={
                "placeholder": "مثلاً: 20",
                "min": 5,
                "max": 240,
                "step": 1,
            }
        ),
    )
from .models import PersonalItem


class PersonalItemForm(forms.ModelForm):
    class Meta:
        model = PersonalItem

        fields = ["title", "category"]

        labels = {
            "title": "اسم النشاط",
            "category": "القسم",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_title(self):
        title = self.cleaned_data["title"].strip()

        if not title:
            raise forms.ValidationError(
                "أدخل اسم النشاط."
            )

        return title

    def clean(self):
        cleaned_data = super().clean()

        title = cleaned_data.get("title")
        category = cleaned_data.get("category")

        if title and category:
            duplicate = PersonalItem.objects.filter(
                user=self.user,
                title=title,
                category=category,
            ).exclude(
                pk=self.instance.pk,
            )

            if duplicate.exists():
                self.add_error(
                    "title",
                    "هذا النشاط موجود بالفعل، وقد يكون مؤرشفًا.",
                )

        return cleaned_data
    
from .models import UserProfile


class ProfileImageForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["image"]
        labels = {
            "image": "الصورة الشخصية",
        }