from django.views.generic import TemplateView


class LegalPageView(TemplateView):
    extra_context = {
        "support_whatsapp_url": (
            "https://wa.me/201016487371"
            "?text=I%20need%20help%20with%20my%20Yalla%20Market%20account"
        ),
    }


class PrivacyPolicyView(LegalPageView):
    template_name = "legal/privacy.html"


class TermsOfUseView(LegalPageView):
    template_name = "legal/terms.html"


class AccountDeletionView(LegalPageView):
    template_name = "legal/account_deletion.html"
    extra_context = {
        **LegalPageView.extra_context,
        "support_whatsapp_url": (
            "https://wa.me/201016487371"
            "?text=I%20want%20to%20request%20deletion%20of%20my"
            "%20Yalla%20Market%20account"
        ),
    }
