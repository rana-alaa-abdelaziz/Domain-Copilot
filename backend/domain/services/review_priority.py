"""
Priority and SLA computation for the review queue — pure logic, no I/O.
Per ADR-004: priority is driven by how confident the auto-validation/gap
analysis was, not FIFO — an unverified, critical-severity gap is exactly
where a human catching a plausible-but-wrong item matters most (D3's
named risk), so it should queue-jump ahead of routine, well-grounded items.
"""
from datetime import datetime, timedelta, timezone

from backend.domain.entities.competency_gap_report import CompetencyGapReport

_SLA_HOURS = {"high": 4, "medium": 24, "low": 72}


def compute_priority(gap_report: CompetencyGapReport) -> str:
    has_unverified_critical = any(
        g.severity == "critical" and g.coverage_source == "unverified"
        for g in gap_report.gaps
    )
    has_any_critical = any(g.severity == "critical" for g in gap_report.gaps)

    if has_unverified_critical:
        return "high"
    if has_any_critical:
        return "medium"
    return "low"


def compute_sla_due_at(priority: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now + timedelta(hours=_SLA_HOURS[priority])