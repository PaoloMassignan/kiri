"""CreditScorer — proprietary risk-scoring engine.

Computes a credit score in the range [_SCORE_FLOOR, _SCORE_CEIL] from
bureau data using a weighted linear model over five component scores.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------

_SCORE_FLOOR: int = 300
_SCORE_CEIL: int = 850

# ---------------------------------------------------------------------------
# Routing band thresholds (normalised fraction of the score range)
# ---------------------------------------------------------------------------

_BAND_REJECT: float = 0.25    # score < 25th percentile → automatic reject
_BAND_APPROVE: float = 0.75   # score > 75th percentile → automatic approve

# ---------------------------------------------------------------------------
# Component weights (must sum to 1.0)
# ---------------------------------------------------------------------------

_W_PAYMENT_HISTORY: float = 0.341
_W_UTILIZATION: float = 0.298
_W_ACCOUNT_AGE: float = 0.157
_W_CREDIT_MIX: float = 0.101
_W_NEW_INQUIRIES: float = 0.103

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BureauData:
    payment_history_rate: float   # fraction of on-time payments [0, 1]
    utilization_ratio: float      # revolving utilization [0, 1]
    account_age_months: int       # age of oldest open account
    credit_mix_score: float       # diversity index [0, 1]
    hard_inquiries_12m: int       # hard pulls in the last 12 months


@dataclass
class ScoreComponents:
    payment_history: float
    utilization: float
    account_age: float
    credit_mix: float
    new_inquiries: float


# ---------------------------------------------------------------------------
# Private scoring helpers
# ---------------------------------------------------------------------------


def _score_utilization(ratio: float) -> float:
    """Map revolving utilization ratio to a [0, 1] component score.

    Non-linear: scores degrade rapidly above 30 % and improve sharply below 10 %.
    """
    if ratio <= 0.10:
        return 1.0
    if ratio <= 0.30:
        return 1.0 - (ratio - 0.10) / 0.20 * 0.25
    if ratio <= 0.50:
        return 0.75 - (ratio - 0.30) / 0.20 * 0.35
    if ratio <= 0.80:
        return 0.40 - (ratio - 0.50) / 0.30 * 0.30
    return max(0.0, 0.10 - (ratio - 0.80) * 0.5)


def _score_payment_history(rate: float) -> float:
    """Non-linear map of on-time payment rate to component score."""
    if rate >= 0.99:
        return 1.0
    if rate >= 0.95:
        return 0.85 + (rate - 0.95) / 0.04 * 0.15
    if rate >= 0.90:
        return 0.65 + (rate - 0.90) / 0.05 * 0.20
    return max(0.0, rate * 0.65 / 0.90)


def _score_account_age(months: int) -> float:
    """Map account age (months) to a [0, 1] score."""
    if months >= 120:
        return 1.0
    if months >= 60:
        return 0.70 + (months - 60) / 60 * 0.30
    if months >= 24:
        return 0.40 + (months - 24) / 36 * 0.30
    return months / 24 * 0.40


def _compute_components(data: BureauData) -> ScoreComponents:
    """Compute all five component scores from raw bureau data."""
    return ScoreComponents(
        payment_history=_score_payment_history(data.payment_history_rate),
        utilization=_score_utilization(data.utilization_ratio),
        account_age=_score_account_age(data.account_age_months),
        credit_mix=data.credit_mix_score,
        new_inquiries=max(0.0, 1.0 - data.hard_inquiries_12m * 0.10),
    )


def _weighted_sum(components: ScoreComponents) -> float:
    """Compute the weighted linear combination of all five components."""
    return (
        _W_PAYMENT_HISTORY * components.payment_history
        + _W_UTILIZATION * components.utilization
        + _W_ACCOUNT_AGE * components.account_age
        + _W_CREDIT_MIX * components.credit_mix
        + _W_NEW_INQUIRIES * components.new_inquiries
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class RiskScorer:
    """Compute a credit score from a BureauData record."""

    def score(self, data: BureauData) -> int:
        """Return an integer score in [_SCORE_FLOOR, _SCORE_CEIL]."""
        components = _compute_components(data)
        normalized = _weighted_sum(components)
        raw = _SCORE_FLOOR + normalized * (_SCORE_CEIL - _SCORE_FLOOR)
        return max(_SCORE_FLOOR, min(_SCORE_CEIL, round(raw)))

    def route(self, score: int) -> str:
        """Map a score to a routing decision: REJECT, MANUAL, or APPROVE."""
        normalized = (score - _SCORE_FLOOR) / (_SCORE_CEIL - _SCORE_FLOOR)
        if normalized < _BAND_REJECT:
            return "REJECT"
        if normalized > _BAND_APPROVE:
            return "APPROVE"
        return "MANUAL"
