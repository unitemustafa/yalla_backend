from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.html import escape
from django.views.decorators.http import require_GET

from catalog.models import Product
from offers.models import Offer


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
):
    deep_link = f"yallamarket://{content_type}/{content_id}"
    escaped_title = escape(title or "يلا ماركت")
    escaped_description = escape(
        description or "افتح يلا ماركت لعرض التفاصيل حسب مدينتك الحالية."
    )
    escaped_image_url = escape(image_url)
    escaped_deep_link = escape(deep_link)
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
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="يلا ماركت">
  <meta property="og:title" content="{escaped_title}">
  <meta property="og:description" content="{escaped_description}">
  {image_meta}
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      font-family: Arial, sans-serif; background: #111214; color: #fff; }}
    main {{ width: min(88vw, 430px); text-align: center; padding: 32px 20px;
      border: 1px solid #34363b; border-radius: 18px; background: #222326; }}
    img {{ width: 112px; height: 112px; object-fit: cover; border-radius: 14px; }}
    h1 {{ margin: 18px 0 8px; font-size: 24px; }}
    p {{ color: #b8bac1; line-height: 1.7; }}
    a {{ display: block; margin-top: 22px; padding: 14px 18px; border-radius: 12px;
      background: #5263ff; color: #fff; text-decoration: none; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    {f'<img src="{escaped_image_url}" alt="">' if escaped_image_url else ''}
    <h1>{escaped_title}</h1>
    <p>افتح يلا ماركت لعرض التفاصيل حسب مدينتك الحالية.</p>
    <a href="{escaped_deep_link}">فتح في يلا ماركت</a>
  </main>
  <script>window.location.replace("{escaped_deep_link}");</script>
</body>
</html>"""
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src https: http: data:; "
        "style-src 'unsafe-inline'; script-src 'unsafe-inline'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def product_share(request, product_id):
    product = get_object_or_404(
        Product.objects.select_related("market"),
        id=product_id,
    )
    return _share_landing_response(
        request,
        content_type="products",
        content_id=product.id,
        title=product.name,
        description=product.description,
        image_url=_absolute_image_url(request, product.image),
    )


@require_GET
def offer_share(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    return _share_landing_response(
        request,
        content_type="offers",
        content_id=offer.id,
        title=offer.title,
        description=offer.description,
        image_url=_absolute_image_url(request, offer.image),
    )
