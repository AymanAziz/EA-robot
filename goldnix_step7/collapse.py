"""The predeclared Step 7 collapse criterion; this is not an edge test."""

import math

import numpy as np


def collapse_check(returns, *, in_sample_mean, in_sample_se):
    """Compare mean R using the in-sample block SE and holdout sample SE."""
    values = np.asarray(returns, dtype=float)
    if (values.ndim != 1 or not np.isfinite(values).all()
            or not math.isfinite(in_sample_mean) or not math.isfinite(in_sample_se)
            or in_sample_se < 0):
        raise ValueError("Returns and means must be finite; SE must be finite and nonnegative")
    if len(values) < 2:
        return {
            "baskets": len(values), "in_sample_mean_r": float(in_sample_mean),
            "in_sample_se": float(in_sample_se),
            "holdout_mean_r": float(values.mean()) if len(values) else None,
            "holdout_se": None, "threshold_r": None, "verdict": "INSUFFICIENT_DATA",
        }
    holdout_se = float(values.std(ddof=1) / math.sqrt(len(values)))
    threshold = float(in_sample_mean - 2 * math.hypot(in_sample_se, holdout_se))
    mean = float(values.mean())
    if not all(math.isfinite(x) for x in (mean, holdout_se, threshold)):
        raise ValueError("Nonfinite collapse statistics")
    return {
        "baskets": len(values), "in_sample_mean_r": float(in_sample_mean),
        "in_sample_se": float(in_sample_se), "holdout_mean_r": mean,
        "holdout_se": holdout_se, "threshold_r": threshold,
        "verdict": "PASS" if mean >= threshold else "FAIL_DISCARD",
    }
