import re
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_GET

from catalog.models import Product
from markets.models import Market
from offers.models import Offer

from .rate_limit import rate_limit_view


def _store_link(url, host, label):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.netloc != host:
        return ""
    return f'<a href="{escape(url)}">{label}</a>'


def _absolute_image_url(request, image_field):
    if not image_field:
        return ""
    try:
        return request.build_absolute_uri(image_field.url)
    except (AttributeError, ValueError):
        return ""


def _share_landing_response(
    request,
    *,
    content_type,
    content_id,
    title,
    description,
    image_url,
    variant_id=None,
    detail="",
):
    deep_link = f"yallamarket://{content_type}/{content_id}"
    canonical_url = request.build_absolute_uri(request.path)
    if variant_id is not None:
        query = urlencode({"variant": variant_id})
        deep_link = f"{deep_link}?{query}"
        canonical_url = f"{canonical_url}?{query}"
    escaped_title = escape(title or "يلا ماركت")
    escaped_description = escape(
        description or "افتح يلا ماركت لعرض التفاصيل حسب مدينتك الحالية."
    )
    escaped_image_url = escape(image_url)
    escaped_deep_link = escape(deep_link)
    escaped_canonical_url = escape(canonical_url)
    detail_html = f'<p class="detail">{escape(detail)}</p>' if detail else ""
    store_links = _store_link(
        settings.ANDROID_APP_STORE_URL, "play.google.com", "تحميل من Google Play"
    ) + _store_link(settings.IOS_APP_STORE_URL, "apps.apple.com", "تحميل من App Store")
    download_html = (
        f"<p>التطبيق مش عندك؟ حمّله من المتجر:</p>{store_links}"
        if store_links
        else '<p class="notice">التطبيق غير متاح على المتاجر حاليًا. '
        "إذا كانت النسخة التجريبية مثبتة لديك، اضغط على «فتح في يلا ماركت».</p>"
    )
    image_meta = (
        f'<meta property="og:image" content="{escaped_image_url}">'
        if escaped_image_url
        else ""
    )
    html = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escaped_title} | يلا ماركت</title>
  <meta name="description" content="{escaped_description}">
  <link rel="canonical" href="{escaped_canonical_url}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="يلا ماركت">
  <meta property="og:title" content="{escaped_title}">
  <meta property="og:description" content="{escaped_description}">
  <meta property="og:url" content="{escaped_canonical_url}">
  <meta name="twitter:card" content="summary_large_image">
  {image_meta}
  <style>
    :root {{ color-scheme: light dark; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 20px 0;
      font-family: Arial, sans-serif; background: #111214; color: #fff; }}
    main {{ width: min(88vw, 430px); text-align: center; padding: 32px 20px;
      border: 1px solid #34363b; border-radius: 18px; background: #222326; }}
    img {{ width: 112px; height: 112px; object-fit: cover; border-radius: 14px; }}
    h1 {{ margin: 18px 0 8px; font-size: 24px; overflow-wrap: anywhere; }}
    p {{ color: #b8bac1; line-height: 1.7; overflow-wrap: anywhere; white-space: pre-line; }}
    .detail {{ color: #fff; font-weight: 700; }}
    .notice {{ font-size: 14px; }}
    a:focus-visible {{ outline: 3px solid #fff; outline-offset: 4px; }}
    a {{ display: block; margin-top: 22px; padding: 14px 18px; border-radius: 12px;
      background: #5263ff; color: #fff; text-decoration: none; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    {f'<img src="{escaped_image_url}" alt="">' if escaped_image_url else ""}
    <h1>{escaped_title}</h1>
    <p>{escaped_description}</p>
    {detail_html}
    <p>التوفر والسعر النهائي حسب مدينتك داخل التطبيق.</p>
    <a href="{escaped_deep_link}">فتح في يلا ماركت</a>
    {download_html}
  </main>
</body>
</html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src https: http: data:; "
        "style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@rate_limit_view("share_ip")
def product_share(request, product_id):
    product = get_object_or_404(
        Product.objects.select_related("market").filter(
            archived_at__isnull=True,
            is_available=True,
            market__archived_at__isnull=True,
            market__status=Market.Status.ACTIVE,
        ),
        id=product_id,
    )
    variant = None
    variant_values = request.GET.getlist("variant")
    if len(variant_values) == 1 and re.fullmatch(
        r"[1-9][0-9]{0,18}", variant_values[0]
    ):
        variant_id = int(variant_values[0])
        if variant_id <= 9223372036854775807:
            variant = product.variants.filter(pk=variant_id).first()
    detail = product.market.name
    if variant is not None:
        values = variant.attribute_values.select_related(
            "product_attribute", "product_attribute_option", "attribute", "option"
        )
        labels = []
        for value in values:
            attribute = value.product_attribute or value.attribute
            option = value.product_attribute_option or value.option
            if attribute is not None and option is not None:
                labels.append(f"{attribute.name}: {option.value}")
        if labels:
            detail += " — " + "، ".join(labels)
    return _share_landing_response(
        request,
        content_type="products",
        content_id=product.id,
        title=product.name,
        description=product.description,
        image_url=_absolute_image_url(request, product.image),
        variant_id=variant.pk if variant is not None else None,
        detail=detail,
    )


@require_GET
@rate_limit_view("share_ip")
def offer_share(request, offer_id):
    now = timezone.now()
    offer = get_object_or_404(
        Offer.objects.filter(
            archived_at__isnull=True,
            status=Offer.Status.ACTIVE,
            start_time__lte=now,
            end_time__gt=now,
        ).filter(
            Q(market__isnull=True)
            | Q(
                market__archived_at__isnull=True,
                market__status=Market.Status.ACTIVE,
            )
        ),
        id=offer_id,
    )
    return _share_landing_response(
        request,
        content_type="offers",
        content_id=offer.id,
        title=offer.title,
        description=offer.description,
        image_url=_absolute_image_url(request, offer.image),
    )


@require_GET
@rate_limit_view("share_ip")
def market_share(request, market_id):
    market = get_object_or_404(
        Market.objects.filter(
            archived_at__isnull=True,
            status=Market.Status.ACTIVE,
        ),
        id=market_id,
    )
    return _share_landing_response(
        request,
        content_type="markets",
        content_id=market.id,
        title=market.name,
        description=market.description,
        image_url=_absolute_image_url(
            request,
            market.cover_image or market.image,
        ),
    )


@require_GET
def android_asset_links(request):
    fingerprints = settings.ANDROID_APP_LINK_FINGERPRINTS
    if not fingerprints or any(
        not re.fullmatch(r"(?:[A-Fa-f0-9]{2}:){31}[A-Fa-f0-9]{2}", value)
        for value in fingerprints
    ):
        return JsonResponse([], safe=False)
    return JsonResponse(
        [
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": "com.yallamarket.app",
                    "sha256_cert_fingerprints": fingerprints,
                },
            }
        ],
        safe=False,
    )


@require_GET
def apple_app_site_association(request):
    app_ids = settings.IOS_APP_LINK_APP_IDS
    details = []
    if app_ids and all(
        re.fullmatch(r"[A-Z0-9]{10}\.com\.yallamarket\.app", value) for value in app_ids
    ):
        details = [
            {
                "appIDs": app_ids,
                "components": [
                    {"/": "/share/products/*"},
                    {"/": "/share/offers/*"},
                    {"/": "/share/markets/*"},
                ],
            }
        ]
    return JsonResponse({"applinks": {"details": details}})
