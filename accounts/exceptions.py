from rest_framework.exceptions import APIException


ACCOUNT_INACTIVE_MESSAGE = "تم إيقاف حسابك. تواصل مع الدعم."


class AccountInactive(APIException):
    status_code = 403
    default_code = "account_inactive"

    def __init__(self):
        self.detail = {
            "code": self.default_code,
            "detail": ACCOUNT_INACTIVE_MESSAGE,
        }
