"""Event deck: load, filter by situation, weighted draw (Q23).

Order of precedence each leg: a scheduled follow-up that has come due beats
the deck entirely. Otherwise filter the deck down to events that make sense
for the current stats, flags and system tags, then draw by weight.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import constants as K

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


def load_flavour(name: str = "flavour.json") -> dict[str, list[str]]:
    """Observations for a leg where nothing happens to you."""
    with open(CONTENT / name, encoding="utf-8") as fh:
        return json.load(fh)


def observe(flavour: dict[str, list[str]], state, rng: random.Random) -> str:
    """One observation, preferring something about the system you are sitting in."""
    tagged = [line for tag in state.system_tags for line in flavour.get(tag, [])]
    pool = tagged + flavour["any"] if tagged and rng.random() < 0.6 else flavour["any"]
    return rng.choice(pool)


def _matches(event: dict, state, scheduled: bool = False) -> bool:
    """Does this event make sense right now?

    `scheduled` is for an event coming due off the queue: it bypasses the
    chain-only gate and the cooldown, but still has to satisfy its own
    requirements, so a follow-up whose premise you already resolved never
    fires.
    """
    req = event.get("requires", {})

    if not scheduled:
        if event.get("chain_only"):
            return False  # reachable only when something schedules it
        last_drawn = state.recent.get(event["id"])
        if last_drawn is not None and state.leg - last_drawn < K.EVENT_COOLDOWN:
            return False
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
    by_id = {e["id"]: e for e in events}
    while True:
        due = state.due_event()
        if due is None:
            break
        event = by_id.get(due)
        if event and _matches(event, state, scheduled=True):
            return event
        # Premise already resolved, or the id no longer exists: drop it
        # silently and let the leg roll normally.

    pool = available(events, state)
    if not pool:
        # Cooldowns have starved the deck. Better a repeat than a dead leg.
        pool = [e for e in events if _matches(e, state, scheduled=True)
                and not e.get("chain_only")]
    if not pool:
        return None
    return rng.choices(pool, weights=[e.get("weight", 10) for e in pool])[0]
