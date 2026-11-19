"""Формы истории проверок: фильтр списка и создание/изменение проверки."""

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import F

from watchlist.models import AIModel, Vendor

from .models import Check
from .validators import validate_not_in_future

# Ключ из ?sort= → подпись и поля order_by(). Префикс «-» — по убыванию,
# второе поле упорядочивает записи с одинаковым первым.
SORT_OPTIONS = {
    "new": ("сначала новые", ("-checked_at", "-id")),
    "old": ("сначала старые", ("checked_at", "id")),
    "model": ("по модели", ("model__name", "-checked_at")),
    "uptime": (
        "по аптайму",
        (F("uptime").desc(nulls_last=True), "-checked_at"),
    ),
}


class CheckFilterForm(forms.Form):
    """Фильтр истории проверок. Данные приходят GET-параметрами адреса.

    Обычная форма (forms.Form), а не ModelForm: она не создаёт объект,
    а только проверяет и преобразует параметры запроса. Все поля
    необязательны: пустое поле — фильтр не применяется.
    """

    day = forms.DateField(
        label="День",
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}
        ),
    )
    status = forms.ChoiceField(
        label="Статус",
        required=False,
        choices=[("", "любой статус"), *Check.Status.choices],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    vendor = forms.ModelChoiceField(
        label="Разработчик",
        required=False,
        queryset=Vendor.objects.filter(models__isnull=False).distinct(),
        to_field_name="slug",
        empty_label="все разработчики",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    q = forms.CharField(
        label="Модель",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            "type": "search",
            "class": "form-control",
            "placeholder": "Модель: название или id",
        }),
    )
    sort = forms.ChoiceField(
        label="Сортировка",
        required=False,
        choices=[(key, label) for key, (label, _) in SORT_OPTIONS.items()],
        widget=forms.HiddenInput,
    )


class CheckForm(forms.ModelForm):
    """Создание и изменение проверки вручную.

    Поля формы строятся по полям модели Check из списка Meta.fields.
    Проверки: тип и диапазон значений — валидаторы полей, время —
    clean_checked_at(), согласованность полей и повтор проверки — clean().
    """

    class Meta:
        model = Check
        fields = ["model", "checked_at", "status", "uptime"]
        labels = {
            "model": "Модель",
            "checked_at": "Время проверки",
            "status": "Статус",
            "uptime": "Аптайм, %",
        }
        help_texts = {
            "uptime": "От 0 до 100. Оставьте пустым, если OpenRouter "
                      "не сообщил аптайм.",
            "checked_at": "Время по Москве, не позже текущего момента.",
        }
        widgets = {
            "model": forms.Select(attrs={"class": "form-select"}),
            "checked_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "status": forms.Select(attrs={"class": "form-select"}),
            "uptime": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.1",
                "min": "0",
                "max": "100",
                "placeholder": "например, 99.5",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Новые проверки — только для отслеживаемых моделей. Модель уже
        # сохранённой проверки остаётся в списке, даже если её убрали
        # из отслеживания.
        models = AIModel.objects.filter(is_tracked=True)
        if self.instance.pk:
            models = models | AIModel.objects.filter(
                pk=self.instance.model_id
            )
        self.fields["model"].queryset = models.select_related("vendor")
        self.fields["uptime"].validators += [
            MinValueValidator(0), MaxValueValidator(100),
        ]

    def clean_checked_at(self):
        """Проверка одного поля: время не в будущем и без секунд."""
        checked_at = self.cleaned_data["checked_at"]
        validate_not_in_future(checked_at)
        return checked_at.replace(second=0, microsecond=0)

    def clean(self):
        """Проверки, в которых участвуют несколько полей."""
        cleaned = super().clean()
        status = cleaned.get("status")
        uptime = cleaned.get("uptime")
        model = cleaned.get("model")
        checked_at = cleaned.get("checked_at")

        if status == Check.Status.NOT_FOUND and uptime is not None:
            self.add_error(
                "uptime",
                "У модели, которой нет в OpenRouter, аптайма быть не может.",
            )

        if model and checked_at:
            # Повтор: у модели уже есть проверка на это время. Сама
            # изменяемая проверка не считается повтором — exclude(pk=...).
            duplicate = Check.objects.filter(
                model=model, checked_at=checked_at
            ).exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError(
                    "У этой модели уже есть проверка на это время.",
                    code="duplicate",
                )
        return cleaned
