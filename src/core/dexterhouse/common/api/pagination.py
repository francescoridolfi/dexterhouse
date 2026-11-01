# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cursor pagination: `?cursor=…&limit=50` (max 200), `{results, next, previous}`."""

from rest_framework.pagination import CursorPagination


class CursorPage(CursorPagination):
    page_size = 50
    page_size_query_param = "limit"
    max_page_size = 200
    ordering = "-created_at"


class AscendingCursorPage(CursorPage):
    """Oldest first (phases, tasks, histories)."""

    ordering = "created_at"
