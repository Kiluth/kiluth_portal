"""Portal menu items API.

Serves the tiled-menu data that renders on the /welcome landing page. Source
of truth is `data/portal_menu_items.json` in this app — not an external
service. Replaces the prior kiluth-api `/portal-menu-items` endpoint.

Contract (preserved from the prior external API so the welcome-page JS keeps
working with a minimal URL swap):

  GET /api/method/kiluth_portal.api.portal.get_portal_menu
      ?page=<int>&limit=<int>&sort=<title|category|id|order>
      &search=<str>&category=<str>

  response = {
    success:   True,
    data:      [ {id, title, description, icon, iconColor, category, order, links}, ... ],
    pagination: {currentPage, totalPages, totalItems, itemsPerPage, hasNextPage, hasPrevPage},
    filters:   {category, search, sort},
    categories: [ ...all distinct categories ],
  }
"""

from __future__ import annotations

import json
import os

import frappe

DATA_PATH = os.path.join(
	os.path.dirname(os.path.dirname(__file__)),
	"data",
	"portal_menu_items.json",
)


def _load_items() -> list[dict]:
	with open(DATA_PATH, encoding="utf-8") as f:
		return json.load(f)


def _to_int(value, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_portal_menu(
	page: str | int = 1,
	limit: str | int = 12,
	sort: str = "title",
	search: str | None = None,
	category: str | None = None,
):
	items = _load_items()
	all_categories = sorted({i.get("category") for i in items if i.get("category")})

	# Filter
	if category:
		items = [i for i in items if i.get("category") == category]
	if search:
		term = search.lower()
		items = [
			i
			for i in items
			if term in (i.get("title") or "").lower()
			or term in (i.get("description") or "").lower()
			or term in (i.get("category") or "").lower()
		]

	# Sort
	sort_key = sort if sort in ("title", "category", "id", "order") else "title"
	if sort_key == "order":
		items.sort(key=lambda i: i.get("order") if i.get("order") is not None else 999)
	else:
		items.sort(key=lambda i: (i.get(sort_key) or "").lower())

	# Paginate
	page_num = max(1, _to_int(page, 1))
	limit_num = min(50, max(1, _to_int(limit, 12)))
	offset = (page_num - 1) * limit_num
	total_items = len(items)
	total_pages = (total_items + limit_num - 1) // limit_num if total_items else 0

	return {
		"success": True,
		"data": items[offset : offset + limit_num],
		"pagination": {
			"currentPage": page_num,
			"totalPages": total_pages,
			"totalItems": total_items,
			"itemsPerPage": limit_num,
			"hasNextPage": page_num < total_pages,
			"hasPrevPage": page_num > 1,
			"nextPage": page_num + 1 if page_num < total_pages else None,
			"prevPage": page_num - 1 if page_num > 1 else None,
		},
		"filters": {
			"category": category or None,
			"search": search or None,
			"sort": sort_key,
		},
		"categories": all_categories,
	}
