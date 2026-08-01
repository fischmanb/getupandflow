from math import ceil

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .constants import FEED_MAX_PAGE_SIZE, FEED_PAGE_SIZE


class TranscriptFeedPagination(PageNumberPagination):
    page_size = FEED_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = FEED_MAX_PAGE_SIZE

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.get_page_size(self.request),
                "total_pages": ceil(self.page.paginator.count / self.get_page_size(self.request))
                if self.page.paginator.count
                else 0,
                "results": data,
            }
        )
