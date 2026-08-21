import re

from rest_framework import serializers


def contains_whitespace(value):
    return bool(re.search(r"\s", value or ""))


def reject_whitespace(value):
    if contains_whitespace((value or "").strip()):
        raise serializers.ValidationError("Spaces are not allowed in this field.")
    return value


def no_whitespace_validator(value):
    reject_whitespace(value)


def normalize_egyptian_phone(value):
    phone = (value or "").strip()
    egypt_pattern = r"(?:01[0125]\d{8}|1[0125]\d{8}|201[0125]\d{8}|\+201[0125]\d{8})"
    algeria_pattern = r"(?:0[567]\d{8}|[567]\d{8}|213[567]\d{8}|\+213[567]\d{8})"
    pattern = rf"(?:{egypt_pattern}|{algeria_pattern})"
    if not re.fullmatch(pattern, phone):
        raise serializers.ValidationError("Enter a valid mobile number.")

    if phone.startswith("+213"):
        return phone
    if phone.startswith("213"):
        return f"+{phone}"
    if re.fullmatch(r"0[567]\d{8}", phone):
        return f"+213{phone[1:]}"
    if re.fullmatch(r"[567]\d{8}", phone):
        return f"+213{phone}"
    if phone.startswith("+20"):
        return phone
    if phone.startswith("20"):
        return f"+{phone}"
    if phone.startswith("0"):
        return f"+20{phone[1:]}"
    return f"+20{phone}"


def phone_candidates(value):
    try:
        normalized = normalize_egyptian_phone(value)
    except serializers.ValidationError:
        return []

    if normalized.startswith("+213"):
        national = normalized[4:]
    else:
        national = normalized[3:]
    return list(
        {
            normalized,
            normalized[1:],
            national,
            f"0{national}",
        }
    )


class RequiredFieldMessagesMixin:
    def get_fields(self):
        fields = super().get_fields()
        for name, field in fields.items():
            if field.required:
                label = field.label or name.replace("_", " ").capitalize()
                message = f"{label} is required."
                field.error_messages["required"] = message
                field.error_messages["blank"] = message
        return fields
