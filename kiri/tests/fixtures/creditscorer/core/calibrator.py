"""Platt scaling calibrator: credit score → probability of default.

Converts an integer credit score [300, 850] to a probability of default [0, 1]
using a logistic function with parameters fitted on the 2023-Q4 training set.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Fitted Platt scaling parameters
# Do not update these without re-running calibration/fit_platt.py and
# passing a calibration review (see docs/adr/ADR-006-redact-vs-block.md).
# ---------------------------------------------------------------------------

_A: float = -0.01247
_B: float = 3.9821


# ---------------------------------------------------------------------------
# Module-level functions (used by downstream pipeline stages)
# ---------------------------------------------------------------------------


def score_to_probability(score: int) -> float:
    """Convert a credit score to a probability of default.

    p = 1 / (1 + exp(-(A * score + B)))

    Higher score → lower probability of default (sign convention matches
    the logistic regression fit where score is the negative log-odds).
    """
    logit = _A * score + _B
    return 1.0 / (1.0 + math.exp(-logit))


def probability_to_expected_loss(probability: float, lgd: float = 0.45) -> float:
    """Compute expected loss from probability of default and loss-given-default.

    EL = PD × LGD

    LGD defaults to 0.45 (Basel II regulatory floor for unsecured retail).
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {probability}")
    if not 0.0 <= lgd <= 1.0:
        raise ValueError(f"lgd must be in [0, 1], got {lgd}")
    return probability * lgd


# ---------------------------------------------------------------------------
# Stateful wrapper (used by the scoring service)
# ---------------------------------------------------------------------------


class Calibrator:
    """Stateful wrapper around the Platt scaling functions."""

    def __init__(self, a: float = _A, b: float = _B) -> None:
        self._a = a
        self._b = b

    def calibrate(self, score: int) -> float:
        """Return probability of default for the given score."""
        logit = self._a * score + self._b
        return 1.0 / (1.0 + math.exp(-logit))

    def expected_loss(self, score: int, lgd: float = 0.45) -> float:
        """Return expected loss fraction for the given score and LGD."""
        pd = self.calibrate(score)
        return probability_to_expected_loss(pd, lgd)
