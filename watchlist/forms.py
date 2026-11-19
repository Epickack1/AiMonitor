"""Формы приложения watchlist."""

from django import forms

from .models import Vendor


class VendorLogoForm(forms.ModelForm):
    """Загрузка логотипа разработчика: одно поле модели Vendor."""

    class Meta:
        model = Vendor
        fields = ["logo"]
        labels = {"logo": "Логотип"}
        widgets = {
            "logo": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
        }
