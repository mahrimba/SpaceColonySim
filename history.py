"""The colony's account of its century, written at the end (Q27).

A history, not a log. Each era is told the way a historian would tell it:
the state of things, then the few decisions and events that changed the
colony for good, as prose, then everything else abstracted into the shape of
those years (what kind of trouble came, whether the plans held, who made the
calls, which way the culture drifted). One passage from the Mind's own
record stands at the front as an epigraph. Then the Mind's afterword:
closure for the dead, or a glimpse of what comes next for the living.

The voice is the document form's (charter, scripture, museum catalogue,
survival log). Prose lives in content/history.json and documents.json; this
module only decides what to say.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import colony as C
from state import SafeDict

CONTENT = Path(__file__).parent / "content"
HISTORY = json.loads((CONTENT / "history.json").read_text(encoding="utf-8"))

ERAS = ((0, 20), (21, 70), (71, 100))
MAJOR_PER_ERA = 3
FUTURE_LINES = 6
GRADES = ("crit_success", "success", "failure", "crit_failure")

# Every entry in history.json may be a list of alternatives. One is chosen per
# document, seeded by the colony, so a Retry reads the same and another
# colony reads differently.
# ponytail: module-level rng, set per compose(); pass it down if two
# documents ever need composing at once.
_rng = random.Random(0)


def _one(value):
    return _rng.choice(value) if isinstance(value, list) else value


# Endings in which the colony did not survive the century.
DEATHS = {"extinct", "starved", "pestilence", "sundered", "derelict", "unlettered"}

# What a hazard is about: the stat it harms most, as the history names it.
THEME_OF_STAT = {"food": "hunger", "health": "sickness", "industry": "breakdown",
                 "cohesion": "quarrel", "knowledge": "loss"}


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
    global _rng
    rng = _rng = random.Random(game.seed ^ 0x415)
    events = {e["id"]: e for e in game.events}

    out = [form["title"].format_map(ctx).upper(), ""]
    out += _epigraph(game, form, events)
    out += [line.format_map(ctx) for line in form["prologue"]]
    for index, (lo, hi) in enumerate(ERAS):
        if lo > s.year:
            break
        out += ["", form["eras"][index].upper(), ""]
        out += _era(s, events, rng, index, lo, min(hi, s.year))
    out += _remembered(s)
    out += [""] + [line.format_map(ctx) for line in form["closing"]]
    out += ["", "AFTERWORD", ""] + _afterword(s)
    return out


# --- the eras --------------------------------------------------------------------

def _era(s, events: dict, rng: random.Random, index: int, lo: int, hi: int) -> list[str]:
    entries = [e for e in s.chronicle if lo <= e["year"] <= hi and e.get("event")]

    # The state of things.
    setting = _landing(s) if index == 0 else []
    setting += _population(s, index, entries)
    setting += _roles(s, lo, hi)
    setting += _founders_lost(s, lo, hi, index)

    # What changed them for good, as prose, in the order it happened.
    told = _major(s, entries, rng, lo, hi)
    told_events = {event_id for event_id, _ in told}

    # Everything else, abstracted.
    rest = [e for e in entries if e["event"] not in told_events]
    shape = _shape(rest, events, rng, s, index, lo, hi)

    paragraphs = [" ".join(setting), " ".join(text for _, text in told), " ".join(shape)]
    out: list[str] = []
    for paragraph in paragraphs:
        if paragraph:
            out += [paragraph, ""]
    return out[:-1]


def _landing(s) -> list[str]:
    planet = s.planet or {}
    traits = C.world_traits(planet)
    features = C.planet_features(planet)
    words = HISTORY["world_adjectives"]
    adjectives = [_one(words[t]) for t in traits + features if t in words]
    phrases = [_one(HISTORY["feature_phrases"][f]) for f in features
               if f in HISTORY["feature_phrases"]]
    line = f"They came down on {planet.get('name', 'this world')}"
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
    if "the_waker_lives" in s.flags:
        out.append("The waker, the first person the Mind ever spoke with, was one of them.")
    if "survivors_among_us" in s.flags:
        out.append("So were survivors of another Ark's failure, who knew how a colony dies.")
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


def _founders_lost(s, lo: int, hi: int, index: int) -> list[str]:
    if index == 0:
        return []
    gone = [p for p in s.people if p.born < 0 and p.died is not None and lo <= p.died <= hi]
    if not gone:
        return []
    line = _one(HISTORY["founders_lost"]).format(count=_count_word(len(gone)),
                                                 name=gone[0].name)
    return [line[0].upper() + line[1:]]


def _major(s, entries: list[dict], rng: random.Random, lo: int, hi: int) -> list[tuple]:
    """The decisions and events that changed them for good: flags they set and
    memorable events they lived, weighted, at most a few per era. Returns
    (event id or None, sentence) in the order they happened."""
    major, memorable = HISTORY["major"], HISTORY["memorable"]
    candidates = []
    seen_edit = False
    for i, (flag, year) in enumerate(s.flag_years.items()):
        if not (lo <= year <= hi) or flag not in major:
            continue
        # Editing for several traits is one story, told once.
        if flag.startswith("edited_for_"):
            if seen_edit:
                continue
            seen_edit = True
        candidates.append((major[flag]["weight"], year, i, None, _one(major[flag]["text"])))
    for i, entry in enumerate(entries):
        event_id = entry["event"]
        if event_id in memorable:
            candidates.append((memorable[event_id]["weight"], entry["year"], 1000 + i,
                               event_id, _one(memorable[event_id]["text"])))
    chosen = sorted(candidates, key=lambda c: -c[0])[:MAJOR_PER_ERA]
    chosen.sort(key=lambda c: (c[1], c[2]))
    out = []
    lead_ins = HISTORY["lead_ins"]
    offset = rng.randrange(len(lead_ins))       # varied, and never twice running
    for n, (_, year, _, event_id, text) in enumerate(chosen):
        lead = lead_ins[(offset + n) % len(lead_ins)]
        sentence = lead.format(year=year, nth=_ordinal(year), text=text)
        out.append((event_id, sentence[0].upper() + sentence[1:]))
    return out


def _shape(rest: list[dict], events: dict, rng: random.Random, s, index: int,
           lo: int, hi: int) -> list[str]:
    """The minor decisions, abstracted: what kind of years these were."""
    themes: Counter[str] = Counter()
    mind = them = 0
    held = failed = 0
    for entry in rest:
        event = events.get(entry["event"], {})
        theme = _theme(event)
        if theme:
            themes[theme] += 1
        defer = _defer_of(event, entry)
        if defer > 0:
            mind += 1
        elif defer < 0:
            them += 1
        if entry.get("grade") in ("success", "crit_success"):
            held += 1
        elif entry.get("grade") in ("failure", "crit_failure"):
            failed += 1

    out = []
    if themes:
        phrases = []
        for theme, n in themes.most_common(3):
            options = HISTORY["themes"][theme]
            phrases.append(_one(options[min(n, 3) - 1]))
        # One opening per era, never the same twice in a document.
        leads = HISTORY["themes_lead"][:]
        rng.shuffle(leads)
        lead = leads[index % len(leads)]
        out.append(lead.format(list=_join(phrases)))
    if held + failed >= 2:
        ratio = held / (held + failed)
        out.append(_one(HISTORY["results"]["good" if ratio > 0.65 else
                                           "bad" if ratio < 0.4 else "mixed"]))
    if mind + them >= 2:
        if mind > them * 1.8:
            out.append(_one(HISTORY["deciders"]["mind"]))
        elif them > mind * 1.8:
            out.append(_one(HISTORY["deciders"]["them"]))
        else:
            out.append(_one(HISTORY["deciders"]["shared"]))
    out += _drift(s, index, lo, hi)
    return out


def _theme(event: dict) -> str | None:
    kind = event.get("kind")
    if kind == "opportunity":
        return "windfall"
    if kind == "story":
        return "question"
    if kind != "hazard":
        return None
    harm: Counter[str] = Counter()
    for choice in event.get("choices", []):
        for outcome in [choice[g] for g in GRADES if g in choice] or [choice]:
            for stat, value in outcome.get("effects", {}).items():
                if stat in THEME_OF_STAT and isinstance(value, (int, float)) and value < 0:
                    harm[stat] -= value
    if not harm:
        return "question"
    return THEME_OF_STAT[harm.most_common(1)[0][0]]


def _defer_of(event: dict, entry: dict) -> float:
    """Whose call it was: the deference the chosen answer moved."""
    choice = next((c for c in event.get("choices", []) if c["label"] == entry.get("choice")), None)
    if not choice:
        return 0.0
    grade = entry.get("grade")
    outcome = choice.get(grade, choice) if grade else choice
    return float(outcome.get("defer", 0))


def _drift(s, index: int, lo: int, hi: int) -> list[str]:
    inside = [e for e in s.chronicle if lo <= e["year"] <= hi]
    if not inside:
        return []
    before = [e for e in s.chronicle if e["year"] < lo]
    start = before[-1]["axes"] if before else {a: 0 for a in C.AXES}
    end = inside[-1]["axes"]
    axis = max(C.AXES, key=lambda a: abs(end[a] - start[a]))
    moved = end[axis] - start[axis]
    if abs(moved) < 15:
        return []
    low, high = C.AXES[axis]
    return [_one(HISTORY["drift"]).format(pole=(high if moved > 0 else low).lower())]


def _epigraph(game, form: dict, events: dict) -> list[str]:
    """One passage from the Mind's own record, from the moment that moved the
    colony most, as a history might open on a quotation."""
    s = game.state
    best, best_score = None, -1.0
    for i, entry in enumerate(s.chronicle):
        if not entry.get("outcome") or not i:
            continue
        before = s.chronicle[i - 1]
        score = sum(abs(entry["stats"][k] - before["stats"][k]) for k in entry["stats"])
        if before["population"]:
            score += 100 * abs(entry["population"] - before["population"]) / before["population"]
        event = events.get(entry["event"], {})
        if event.get("chain_only") or event.get("signature"):
            score += 15
        score += 6 * HISTORY["memorable"].get(entry["event"], {}).get("weight", 0)
        # The moment behind a lasting decision: a major flag set by this choice.
        score += 6 * max((HISTORY["major"][f]["weight"]
                          for f, y in s.flag_years.items()
                          if y == entry["year"] and f in HISTORY["major"]), default=0)
        if score > best_score:
            best, best_score = entry, score
    if not best:
        return []
    quote = form["quote"].format(year=best["year"], nth=_ordinal(best["year"]))
    return [quote, f"  {_first_sentence(best['situation'])} {best['outcome']}", ""]


def _remembered(s) -> list[str]:
    dead = sorted((p for p in s.people if not p.alive), key=lambda p: p.died)
    if not dead:
        return []
    names = _join([f"the {p.role} {p.name}" for p in dead[:3]])
    return ["", _one(HISTORY["remembered"]).format(count=_count_word(len(dead)), names=names)]


def _count_word(n: int) -> str:
    words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
             "nine", "ten", "eleven", "twelve"]
    return words[n] if n < len(words) else str(n)


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


# --- the afterword ---------------------------------------------------------------

def _afterword(s) -> list[str]:
    out = [_one(HISTORY["afterword"].get(s.outcome, "That is their account."))]
    if s.outcome in DEATHS:
        out.append(_one(HISTORY["closure"].get(s.outcome, "")))
        out += _secrets(s)
        return [line for line in out if line]

    out += _secrets(s)
    future = [_one(HISTORY["future"][f]) for f in HISTORY["future"] if f in s.flags]
    stats = s.stats
    weakest = min(C.COLONY_STATS, key=lambda k: stats[k])
    strongest = max(C.COLONY_STATS, key=lambda k: stats[k])
    if stats[weakest] < 35:
        future.append(_one(HISTORY["future_weak"][weakest]))
    if stats[strongest] > 65:
        future.append(_one(HISTORY["future_strong"][strongest]))
    start = 1.0 - float((s.planet or {}).get("habitability", 1.0 - s.hostility))
    eased = start - s.hostility
    world = HISTORY["future_world"]
    future.append(_one(world["eased"] if eased >= 0.08 else
                       world["hard"] if s.hostility > 0.6 else world["held"]))
    growing = s.population >= s.peak_population * 0.9
    future.append(_one(HISTORY["future_population"]["growing" if growing else "shrinking"]))
    band = "high" if s.deference > 65 else ("middle" if s.deference > 30 else "low")
    future.append(_one(HISTORY["future_deference"][band]))
    out += future[:FUTURE_LINES]
    return out


def _secrets(s) -> list[str]:
    return [_one(line) for flag, line in HISTORY["secrets"].items() if flag in s.flags][:2]


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
