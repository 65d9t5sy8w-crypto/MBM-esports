"""Analyst board assembly over canonical intake records."""

from mbm.analyst.assembly import build_dashboard_snapshot
from mbm.analyst.models import DashboardSnapshot

__all__ = ["DashboardSnapshot", "build_dashboard_snapshot"]
