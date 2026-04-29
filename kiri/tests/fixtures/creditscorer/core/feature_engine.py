"""Feature engineering pipeline for the credit risk model.

Transforms raw bureau data into the normalised features consumed by RiskScorer.
All transformations are deterministic and version-locked to the model release
they were built for.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------------------
# Winsorization bounds (fitted on training set, p1/p99 percentiles)
# ---------------------------------------------------------------------------

_UTILIZATION_MIN: float = 0.0
_UTILIZATION_MAX: float = 0.975
_INCOME_FLOOR: float = 12_000.0
_INCOME_CAP: float = 500_000.0
_DEROGATORY_CAP: int = 10

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RawBureauRecord:
    """Raw fields as returned by the credit bureau API."""

    account_balances: list[float]
    credit_limits: list[float]
    payment_dates: list[str | None]
    due_dates: list[str | None]
    oldest_account_open_date: str | None
    hard_inquiry_dates: list[str]
    derogatory_marks: int
    annual_income: float


@dataclass
class EngineeredFeatures:
    utilization_ratio: float
    payment_history_rate: float
    account_age_months: int
    hard_inquiries_12m: int
    derogatory_count: int
    income_band: int


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def _months_between(earlier: date, later: date) -> int:
    return max(0, (later.year - earlier.year) * 12 + (later.month - earlier.month))


def _compute_utilization(balances: list[float], limits: list[float]) -> float:
    """Aggregate revolving utilization across all accounts."""
    total_balance = sum(b for b in balances if b > 0)
    total_limit = sum(lim for lim in limits if lim > 0)
    if total_limit == 0.0:
        return 0.0
    raw = total_balance / total_limit
    return _clip(raw, _UTILIZATION_MIN, _UTILIZATION_MAX)


def _compute_payment_rate(
    payment_dates: list[str | None],
    due_dates: list[str | None],
) -> float:
    """Fraction of payments made on or before the due date."""
    pairs = [
        (p, d)
        for p, d in zip(payment_dates, due_dates, strict=False)
        if p is not None and d is not None
    ]
    if not pairs:
        return 1.0  # no history → neutral
    on_time = sum(1 for p, d in pairs if p <= d)
    return on_time / len(pairs)


def _account_age_months(open_date_str: str | None, reference_str: str) -> int:
    """Months between the oldest account open date and the reference date."""
    if open_date_str is None:
        return 0
    try:
        ref = _parse_date(reference_str)
        opened = _parse_date(open_date_str)
        return _months_between(opened, ref)
    except (ValueError, AttributeError):
        return 0


def _count_recent_inquiries(inquiry_dates: list[str], reference_str: str) -> int:
    """Count hard inquiries within the 12 months prior to reference date."""
    try:
        ref = _parse_date(reference_str)
    except (ValueError, AttributeError):
        return 0
    count = 0
    for d_str in inquiry_dates:
        try:
            months = _months_between(_parse_date(d_str), ref)
            if 0 <= months <= 12:
                count += 1
        except (ValueError, AttributeError):
            continue
    return count


def _income_band(annual_income: float) -> int:
    """Bucket annual income into five ordinal bands (0=lowest, 4=highest)."""
    clipped = _clip(annual_income, _INCOME_FLOOR, _INCOME_CAP)
    breakpoints = [20_000.0, 50_000.0, 100_000.0, 200_000.0]
    for i, bp in enumerate(breakpoints):
        if clipped < bp:
            return i
    return len(breakpoints)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class FeatureEngine:
    """Transform a RawBureauRecord into EngineeredFeatures."""

    def __init__(self, reference_date: str) -> None:
        self._reference = reference_date

    def transform(self, record: RawBureauRecord) -> EngineeredFeatures:
        """Run all feature transformations and return the normalised feature set."""
        return EngineeredFeatures(
            utilization_ratio=_compute_utilization(
                record.account_balances, record.credit_limits
            ),
            payment_history_rate=_compute_payment_rate(
                record.payment_dates, record.due_dates
            ),
            account_age_months=_account_age_months(
                record.oldest_account_open_date, self._reference
            ),
            hard_inquiries_12m=_count_recent_inquiries(
                record.hard_inquiry_dates, self._reference
            ),
            derogatory_count=min(record.derogatory_marks, _DEROGATORY_CAP),
            income_band=_income_band(record.annual_income),
        )
