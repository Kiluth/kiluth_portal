"""External liveness probe. Port of prod's `health_check` Server Script.

Callable at `/api/method/kiluth_portal.utils.health.health_check`.
Returns HTTP 200 with a payload even on failure (status: "unhealthy") so the
caller can distinguish a reachable-but-broken site from an unreachable one.
"""

import frappe


@frappe.whitelist(allow_guest=True, methods=["GET"])
def health_check():
	try:
		frappe.db.sql("SELECT 1")
		return {
			"status": "healthy",
			"message": "All systems operational",
			"site": frappe.local.site,
			"timestamp": frappe.utils.now(),
			"version": frappe.__version__,
		}
	except Exception as e:
		return {
			"status": "unhealthy",
			"message": str(e),
			"timestamp": frappe.utils.now(),
		}
