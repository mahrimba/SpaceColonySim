"""Event deck: load, filter by situation, weighted draw (Q23).

Order of precedence each leg: a scheduled follow-up that has come due beats
the deck entirely. Otherwise filter the deck down to events that make sense
for the current stats, flags and system tags, then draw by weight.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

CONTENT = Path(__file__).parent / "content"


def load(*files: str) -> list[dict]:
    events: list[dict] = []
    for name in files or ("voyage.json",):
        with open(CONTENT / name, encoding="utf-8") as fh:
            events.extend(json.load(fh))
    ids = [e["id"] for e in events]
    assert len(ids) == len(set(ids)), f"duplicate event ids: {ids}"
    for e in events:
        assert e.get("choices"), f"{e['id']} has no choices"
    return events


def _matches(event: dict, state) -> bool:
    req = event.get("requires", {})

    if event.get("chain_only"):
        return False  # reachable only when something schedules it
    if event.get("oneshot") and event["id"] in state.fired:
        return False
    if state.leg < req.get("min_leg", 0):
        return False
    for tag in req.get("tags", []):
        if tag not in state.system_tags:
            return False
    if req.get("any_tags") and not (set(req["any_tags"]) & state.system_tags):
        return False
    for flag in req.get("flags", []):
        if flag not in state.flags:
            return False
    for flag in req.get("not_flags", []):
        if flag in state.flags:
            return False
    for stat, (lo, hi) in req.get("stats", {}).items():
        if not lo <= state.stats[stat] <= hi:
            return False
    if req.get("needs_candidate") and not state.candidates:
        return False
    return True


def available(events: list[dict], state) -> list[dict]:
    return [e for e in events if _matches(e, state)]


def draw(events: list[dict], state, rng: random.Random) -> dict | None:
    """The scheduled queue first, then a weighted draw from what fits."""
    due = state.due_event()
    if due:
        for e in events:
            if e["id"] == due:
                return e

    pool = available(events, state)
    if not pool:
        return None
    return rng.choices(pool, weights=[e.get("weight", 10) for e in pool])[0]
