from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class V2PageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        if not request.path.startswith("/api/v2/"):
            return None
        return super().paginate_queryset(queryset, request, view=view)


def paginated_list_response(
    request,
    queryset,
    serializer_class,
    *,
    context=None,
):
    """Paginate only v2; preserve every v1 list response exactly."""

    serializer_context = context or {"request": request}
    if not request.path.startswith("/api/v2/"):
        return Response(
            serializer_class(
                queryset,
                many=True,
                context=serializer_context,
            ).data
        )
    paginator = V2PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    data = serializer_class(
        page,
        many=True,
        context=serializer_context,
    ).data
    return paginator.get_paginated_response(data)
