"""The colony's account of its century, written at the end (Q27).

A history, not a log. Three eras, each told from what actually changed: the
world they met, how many of them there were, what they made of the hull, the
decisions that marked them, and a few turning points quoted from the Mind's
own record. The voice is the document form's (a charter, a scripture, a
museum catalogue, a survival log). Then the Mind's afterword: closure for
the dead, or a glimpse of what comes next for the living, built from what
is unfinished at year one hundred.

Prose lives in content/history.json and content/documents.json; this module
only decides what to say.
"""

from __future__ import annotations

import json
from pathlib import Path

import colony as C
from state import SafeDict

CONTENT = Path(__file__).parent / "content"
HISTORY = json.loads((CONTENT / "history.json").read_text(encoding="utf-8"))

ERAS = ((0, 20), (21, 70), (71, 100))
TURNING_POINTS = 3          # quoted moments per era
LEGACY_PER_ERA = 5
FUTURE_LINES = 6

# Endings in which the colony did not survive the century.
DEATHS = {"extinct", "starved", "pestilence", "sundered", "derelict", "unlettered"}


def compose(game) -> list[str]:
    s = game.state
    ending = next((e for e in game.endings if e["id"] == s.outcome), None)
    form_id = (ending or {}).get("document", "plain")
    # The voice follows what they made of the hull (Q27). The endings where
    # the Mind is gone keep their own form regardless.
    if s.outcome not in ("forgotten", "extinct"):
        form_id = game.ROLE_DOCUMENTS.get(s.ship_role, form_id)
    form = game.documents.get(form_id, game.documents["plain"])
    ctx = SafeDict(_context(s))

    out = [form["title"].format_map(ctx).upper(), ""]
    out += [line.format_map(ctx) for line in form["prologue"]]
    for index, (lo, hi) in enumerate(ERAS):
        if lo > s.year:
            break
        out += ["", form["eras"][index].upper(), ""]
        out += _era(game, form, index, lo, min(hi, s.year))
    out += _remembered(s)
    out += [""] + [line.format_map(ctx) for line in form["closing"]]
    out += ["", "AFTERWORD", ""] + _afterword(s)
    return out


# --- the eras -------------------------------------------------------------------

def _era(game, form: dict, index: int, lo: int, hi: int) -> list[str]:
    s = game.state
    entries = [e for e in s.chronicle if lo <= e["year"] <= hi]
    story: list[str] = []
    if index == 0:
        story += _landing(s)
    story += _population(s, index, entries)
    story += _roles(s, lo, hi)
    story += _legacy(s, lo, hi)
    if index > 0 and entries:
        story += _character(entries[-1])

    out = [" ".join(story)] if story else []
    for entry in _turning_points(game, entries):
        out += ["", form["quote"].format(year=entry["year"], nth=_ordinal(entry["year"])),
                f"  {_first_sentence(entry['situation'])}",
                f"  Decision: {entry['choice'].rstrip('.')}.",
                f"  {entry['outcome']}"]
    return out


def _landing(s) -> list[str]:
    planet = s.planet or {}
    traits = C.world_traits(planet)
    features = C.planet_features(planet)
    words = HISTORY["world_adjectives"]
    adjectives = [words[t] for t in traits + features if t in words]
    phrases = [HISTORY["feature_phrases"][f] for f in features
               if f in HISTORY["feature_phrases"]]
    name = planet.get("name", "this world")
    line = f"They came down on {name}"
    if adjectives:
        line += f", a {_join(adjectives)} world"
    if phrases:
        line += f", with {_join(phrases)}"
    out = [line + "."]
    if s.thaw_losses:
        out.append(f"The thaw took {s.thaw_losses:,} of them before the first morning.")
    founders = [p.name for p in s.people if p.born < 0][:3]
    if founders:
        out.append(f"Among the first awake were {_join(founders)}.")
    return out


def _population(s, index: int, entries: list[dict]) -> list[str]:
    if not entries:
        return []
    if index == 0:
        start = s.arrival.get("colonists_alive", 0) - s.thaw_losses
    else:
        earlier = [e for e in s.chronicle if e["year"] < entries[0]["year"]]
        start = earlier[-1]["population"] if earlier else entries[0]["population"]
    end = entries[-1]["population"]
    if start <= 0:
        return []
    change = (end - start) / start
    if change > 0.1:
        return [f"They grew from {start:,} to {end:,}."]
    if change < -0.1:
        return [f"They fell from {start:,} to {end:,}."]
    return [f"They held at about {end:,}."]


def _roles(s, lo: int, hi: int) -> list[str]:
    """What they called the hull, as one sentence however often it changed."""
    changes = [(y, r) for y, r in s.role_history if lo <= y <= hi]
    if not changes:
        return []
    parts = [f"{role} by year {year}" for year, role in changes[:3]]
    return [f"They called the hull {_join(parts)}."]


def _legacy(s, lo: int, hi: int) -> list[str]:
    """What they did that stayed done, in the order they did it. Secrets the
    Mind kept are not the colony's to write; they wait for the afterword."""
    lines = HISTORY["legacy"]
    # flag_years keeps insertion order: within a year, the order they happened.
    marked = sorted(((year, i, flag) for i, (flag, year) in enumerate(s.flag_years.items())
                     if lo <= year <= hi and flag in lines))
    marked = [(year, flag) for year, _, flag in marked]
    if lo == 0:
        marked = [(0, f) for f in ("the_waker_lives", "survivors_among_us")
                  if f in s.flags] + marked
    return [lines[flag] for _, flag in marked[:LEGACY_PER_ERA]]


def _character(entry: dict) -> list[str]:
    poles = []
    for axis, value in sorted(entry["axes"].items(), key=lambda kv: -abs(kv[1])):
        if abs(value) < 25:
            continue
        low, high = C.AXES[axis]
        strength = "deeply " if abs(value) > 60 else ""
        poles.append(strength + (high if value > 0 else low).lower())
    if not poles:
        return [f"By year {entry['year']} they had not yet decided what kind of people they were."]
    return [f"By year {entry['year']} they were {_join(poles[:3])}."]


def _turning_points(game, entries: list[dict]) -> list[dict]:
    """The moments that changed the most, with the stories only this colony
    lived weighted up: chains, world events, signatures."""
    s = game.state
    by_id = {e["id"]: e for e in game.events}
    scored = []
    for entry in entries:
        if not entry.get("outcome") or not entry.get("event"):
            continue
        i = s.chronicle.index(entry)
        before = s.chronicle[i - 1] if i else None
        score = 0.0
        if before:
            score += sum(abs(entry["stats"][k] - before["stats"][k]) for k in entry["stats"])
            score += abs(entry["deference"] - before["deference"])
            score += 0.3 * sum(abs(entry["axes"][k] - before["axes"][k]) for k in entry["axes"])
            if before["population"]:
                score += 100 * abs(entry["population"] - before["population"]) / before["population"]
        event = by_id.get(entry["event"], {})
        if event.get("chain_only") or event.get("signature") or \
                event.get("requires", {}).get("flags"):
            score += 25
        if entry.get("grade") in ("crit_success", "crit_failure"):
            score += 10
        scored.append((score, entry))
    best = sorted(scored, key=lambda se: -se[0])[:TURNING_POINTS]
    return sorted((entry for _, entry in best), key=lambda e: e["year"])


def _remembered(s) -> list[str]:
    dead = sorted((p for p in s.people if not p.alive), key=lambda p: p.died)
    if not dead:
        return []
    lines = [f"{p.name}, {p.role}, who died in year {p.died}" for p in dead[:12]]
    return ["", "REMEMBERED", ""] + [f"  {line}." for line in lines]


# --- the afterword ---------------------------------------------------------------

def _afterword(s) -> list[str]:
    out = [HISTORY["afterword"].get(s.outcome, "That is their account.")]
    if s.outcome in DEATHS:
        out.append(HISTORY["closure"].get(s.outcome, ""))
        out += _secrets(s)
        return [line for line in out if line]

    out += _secrets(s)
    future = [HISTORY["future"][f] for f in HISTORY["future"] if f in s.flags]
    stats = s.stats
    weakest = min(C.COLONY_STATS, key=lambda k: stats[k])
    strongest = max(C.COLONY_STATS, key=lambda k: stats[k])
    if stats[weakest] < 35:
        future.append(HISTORY["future_weak"][weakest])
    if stats[strongest] > 65:
        future.append(HISTORY["future_strong"][strongest])
    start = 1.0 - float((s.planet or {}).get("habitability", 1.0 - s.hostility))
    eased = start - s.hostility
    world = HISTORY["future_world"]
    future.append(world["eased"] if eased >= 0.08 else
                  world["hard"] if s.hostility > 0.6 else world["held"])
    growing = s.population >= s.peak_population * 0.9
    future.append(HISTORY["future_population"]["growing" if growing else "shrinking"])
    band = "high" if s.deference > 65 else ("middle" if s.deference > 30 else "low")
    future.append(HISTORY["future_deference"][band])
    out += future[:FUTURE_LINES]
    return out


def _secrets(s) -> list[str]:
    return [line for flag, line in HISTORY["secrets"].items() if flag in s.flags][:2]


# --- small things ----------------------------------------------------------------

def _context(s) -> dict:
    return {
        "colony": s.name,
        "ship": s.ship_role,
        "year": s.year,
        "population": f"{s.population:,}",
        "peak": f"{s.peak_population:,}",
        "verdict": s.outcome_reason,
        "voyage_legs": s.arrival.get("legs_flown", "?"),
        "voyage_lost": f"{s.arrival.get('colonists_lost', 0):,}",
        "planet": (s.planet or {}).get("name", "this world"),
        "character": ", ".join(pole.lower() for _, pole, _ in s.dominant_axes(3))
                     or "unformed",
    }


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    cut = text.find(". ")
    return text if cut < 0 else text[:cut + 1]


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
