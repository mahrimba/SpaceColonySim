"""Precision tiers (Q24/Q29).

The engine always knows exact values. What the ship can *say* about them
degrades with cognition alone: above 75 exact, above 50 rounded, below 50
qualitative only. Repairing the mind does not retroactively sharpen an old
survey, so planet readings carry the cognition they were taken at.
"""

from constants import (
    APPROX_ABOVE,
    APPROX_ROUND_COLONISTS,
    APPROX_ROUND_STAT,
    PRECISE_ABOVE,
)

PRECISE, APPROX, VAGUE = "precise", "approx", "vague"


def tier(cognition: float) -> str:
    if cognition >= PRECISE_ABOVE:
        return PRECISE
    if cognition >= APPROX_ABOVE:
        return APPROX
    return VAGUE


def _qualitative(value: float, lo: float, hi: float) -> str:
    span = hi - lo
    frac = 0.0 if span <= 0 else (value - lo) / span
    for threshold, word in (
        (0.02, "gone"),
        (0.15, "critical"),
        (0.35, "low"),
        (0.55, "around half"),
        (0.80, "sound"),
        (1.01, "nominal"),
    ):
        if frac < threshold:
            return word
    return "nominal"


def stat(value: float, cognition: float) -> str:
    """Render a 0-100 shipboard stat as the ship would report it."""
    t = tier(cognition)
    if t == PRECISE:
        return f"{value:.0f}%"
    if t == APPROX:
        return f"~{round(value / APPROX_ROUND_STAT) * APPROX_ROUND_STAT:.0f}%"
    return _qualitative(value, 0, 100)


def count(value: int, cognition: float) -> str:
    """Render a colonist headcount."""
    t = tier(cognition)
    if t == PRECISE:
        return f"{value:,}"
    if t == APPROX:
        rounded = round(value / APPROX_ROUND_COLONISTS) * APPROX_ROUND_COLONISTS
        return f"~{rounded:,}" if value else "none"
    if value <= 0:
        return "none"
    return "most of them" if value > 5_000 else "a fraction of them"


def measure(value: float, cognition: float, unit: str, lo: float, hi: float,
            words: list[str] | None = None) -> str:
    """Render an external sensor reading with a unit (gravity, temperature...).

    `words` is the qualitative ladder used once cognition is too low for
    numbers: lowest band first, evenly spread across lo..hi.
    """
    t = tier(cognition)
    if t == PRECISE:
        return f"{value:.2f}{unit}" if abs(value) < 10 else f"{value:.0f}{unit}"
    if t == APPROX:
        step = (hi - lo) / 10 or 1
        return f"~{round(value / step) * step:.1f}{unit}".replace(".0", "")
    if not words:
        return _qualitative(value, lo, hi)
    span = (hi - lo) / len(words)
    idx = min(len(words) - 1, max(0, int((value - lo) / span)))
    return words[idx]
