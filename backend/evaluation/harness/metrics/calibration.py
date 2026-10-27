"""Calibración: ``confidence_score`` del validador frente a la factualidad observada.

Con pocos casos el ECE es muy ruidoso: se reporta siempre ``n`` y no se
interpreta como umbral. ``correct`` es ``factual_pass`` (todos los hechos y
ninguna afirmación prohibida).
"""

BINS = 5


def calibration(pairs) -> dict:
    """``pairs``: ``[(confidence_score en [0,1], correct bool)]``."""
    pairs = [(float(c), bool(ok)) for c, ok in pairs if c is not None]
    if not pairs:
        return {"n": 0, "ece": None, "brier": None, "na_reason": "sin casos con confidence_score y hechos exigidos"}
    brier = sum((c - ok) ** 2 for c, ok in pairs) / len(pairs)
    bins = [[] for _ in range(BINS)]
    for confidence, ok in pairs:
        bins[min(int(max(confidence, 0.0) * BINS), BINS - 1)].append((confidence, ok))
    ece = sum(
        len(b) / len(pairs) * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b))
        for b in bins
        if b
    )
    return {
        "n": len(pairs),
        "ece": ece,
        "brier": brier,
        "bins": [
            {"n": len(b), "mean_confidence": sum(c for c, _ in b) / len(b), "accuracy": sum(ok for _, ok in b) / len(b)}
            for b in bins
            if b
        ],
    }
