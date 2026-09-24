from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class YallaPageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        if not request.path.startswith("/api/v2/"):
            if (
                "page" not in request.query_params
                and "page_size" not in request.query_params
            ):
                return None
        return super().paginate_queryset(queryset, request, view=view)


# Backward compatibility alias.
V2PageNumberPagination = YallaPageNumberPagination


def paginated_list_response(
    request,
    queryset,
    serializer_class,
    *,
    context=None,
):
    serializer_context = context or {"request": request}
    if not request.path.startswith("/api/v2/"):
        if (
            "page" not in request.query_params
            and "page_size" not in request.query_params
        ):
            return Response(
                serializer_class(
                    queryset,
                    many=True,
                    context=serializer_context,
                ).data
            )
    paginator = YallaPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    data = serializer_class(
        page,
        many=True,
        context=serializer_context,
    ).data
    return paginator.get_paginated_response(data)
