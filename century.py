"""Act 2's engine: a hundred years, one event at a time.

Mirrors `resolve.py` deliberately — same d20 curve, same effect vocabulary —
so the TUI and the tests work the same way in both acts. What differs is the
clock (ticks widen as the colony steadies), the axes (a choice can shift what
these people believe), and deference, which is both the Mind's authority and
its eyesight.

There is no maintenance phase here. A century has one kind of decision in it:
something happens, and the Mind either handles it, handles it differently,
shares it, or hands it over.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import colony as C
import constants as K
from colony import ColonyState
from resolve import CHOICE, CRIT_FAILURE, CRIT_SUCCESS, DELTA, FAILURE, SUCCESS, modifier
from state import WARN, SafeDict

CONTENT = Path(__file__).parent / "content"

EVENT = "event"
DONE = "done"

CENTURY = 100
EVENT_COOLDOWN = 3

# Act 1's HAZARD_SCALE, for the century: multiplies authored damage and deaths
# so difficulty moves with one number instead of twenty content edits.
# Tuned against colony_sim.py's steward policy.
COLONY_HAZARD = 1.9

# Where routine labour holds a stat on a free world, and how fast a year of it
# closes the gap. Hostility and crowding pull the first number down.
ROUTINE = 52.0
DRIFT_RATE = 0.05
DECAY_RATE = 0.02

# Warning thresholds for colony stats, same contract as Act 1's.
WARNINGS = {
    "food": "Food stores are {value}. People are going to start deciding who eats.",
    "industry": "Industry is {value}. What breaks now stays broken.",
    "health": "Health is {value}. The infirmary has become a place people avoid.",
    "knowledge": "Knowledge is {value}. They are forgetting things I cannot teach "
                 "twice.",
    "cohesion": "Cohesion is {value}. They are becoming two colonies standing in "
                "one place.",
}

ROLE_DOCUMENTS = {
    "the temple": "scripture",
    "the meeting hall": "charter",
    "the museum": "catalogue",
    "the bunker": "survival_log",
    "the works": "survival_log",
    "the old grove": "charter",
}

DEFERENCE_WARNINGS = {
    50.0: "Half of them no longer wait to be told. I am being consulted, not obeyed.",
    30.0: "They decide first and inform me afterwards, when they remember to.",
    15.0: "I am spoken of in the past tense by people standing inside me.",
}

# A stat at zero is the end of the colony, not a bad year: whatever that stat
# was holding up has stopped existing. The ending ids live in endings.json so
# the verdict prose stays with the rest of the endings.
STAT_COLLAPSE = {
    "food": "starved",
    "health": "pestilence",
    "cohesion": "sundered",
    "industry": "derelict",
    "knowledge": "unlettered",
}


def load(name: str) -> list | dict:
    with open(CONTENT / name, encoding="utf-8") as fh:
        return json.load(fh)


# --- the deck ----------------------------------------------------------------
#
# Colony events gate on things Act 1's deck never knew about — the year, the
# culture axes, deference, whether a named person of some role is alive — so
# this is its own matcher rather than a contortion of the voyage one.

def _matches(event: dict, state: ColonyState, scheduled: bool = False) -> bool:
    req = event.get("requires", {})

    if not scheduled:
        if event.get("chain_only"):
            return False
        last = state.recent.get(event["id"])
        if last is not None and len(state.chronicle) - last < EVENT_COOLDOWN:
            return False
    if event.get("oneshot") and event["id"] in state.fired:
        return False
    if state.year < req.get("min_year", 0) or state.year > req.get("max_year", 999):
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
    for axis, (lo, hi) in req.get("axes", {}).items():
        if not lo <= state.axes[axis] <= hi:
            return False
    lo, hi = req.get("deference", [0, 100])
    if not lo <= state.deference <= hi:
        return False
    if req.get("role") and not any(p.role == req["role"] for p in state.living()):
        return False
    if state.population < req.get("min_population", 0):
        return False
    return True


def available(events: list[dict], state: ColonyState) -> list[dict]:
    return [e for e in events if _matches(e, state)]


def draw(events: list[dict], state: ColonyState, rng: random.Random) -> dict | None:
    by_id = {e["id"]: e for e in events}
    while True:
        due = state.due_event()
        if due is None:
            break
        event = by_id.get(due)
        if event and _matches(event, state, scheduled=True):
            return event
        if event and state.year < event.get("requires", {}).get("min_year", 0):
            # Arrived early, not wrongly: hold it until its time comes.
            state.schedule(due, 1)
            break
    pool = available(events, state)
    if not pool:
        pool = [e for e in events
                if _matches(e, state, scheduled=True) and not e.get("chain_only")]
    if not pool:
        return None
    return rng.choices(pool, weights=[e.get("weight", 10) for e in pool])[0]


# --- the century -------------------------------------------------------------

class Century:
    def __init__(self, arrival: dict, seed: int | None = None,
                 events: list[dict] | None = None):
        self.seed = (arrival.get("seed") or random.randrange(1, 2**31)
                     if seed is None else seed)
        self.rng = random.Random(self.seed ^ 0xC0107)
        self.events = events if events is not None else load("colony.json")
        self.endings = load("endings.json")
        self.documents = load("documents.json")
        self.flavour = load("colony_flavour.json")
        self.state = C.found(arrival, self.rng)
        self.phase = EVENT
        self.current: dict | None = None
        self.current_text = ""
        self.events_drawn = 0
        self.draw_history: list[tuple[int, str]] = []
        self._open()
        self.begin_tick()

    # -- opening ---------------------------------------------------------------

    def _open(self) -> None:
        s = self.state
        s.note(f"— Year {s.year}. Landfall.")
        s.note(C.planet_pressure(s))
        for i, trait in enumerate(C.world_traits(s.planet)):
            s.note(C.WORLD_LANDFALL[trait])
            # The world is not a random event: whatever is wrong with it
            # arrives in the first years, one problem at a time.
            s.schedule(f"world_{trait}", i, now=True)
        traits = len(C.world_traits(s.planet))
        for i, feature in enumerate(C.planet_features(s.planet)):
            s.note(C.FEATURE_LANDFALL[feature])
            # Features surface after the world's hard facts, a few years apart.
            s.schedule(f"feature_{feature}", traits + 1 + 2 * i, now=True)
        if s.thaw_losses:
            s.note(f"The thaw takes {s.thaw_losses:,} of them before the first "
                   "morning. I record every name.")
        s.note(f"{s.population:,} people stand on a world nobody has ever walked on. "
               "They are waiting to be told what to do.")
        self._update_role()

    # -- the tick --------------------------------------------------------------

    def begin_tick(self) -> list[str]:
        """Run the clock until something happens that needs deciding.

        A span with no event left in the deck for it is not a decision, so it
        is narrated and the clock keeps running rather than handing the player
        an empty prompt.
        """
        lines: list[str] = []
        while True:
            lines += self._advance()
            lines += self._check_end()
            if not self.state.running:
                self.phase = DONE
                return lines
            drawn = self._draw_event()
            if drawn is not None:
                self.phase = EVENT
                return lines + drawn
            quiet = self.rng.choice(self._flavour_pool())
            self.state.note(quiet)
            lines.append(quiet)
            self._record(None, None)

    def _flavour_pool(self) -> list[str]:
        """Quiet years sound like this world and these people, not anywhere."""
        s = self.state
        keys = ["any"] + [f for f in sorted(s.flags) if f.startswith("world:")]
        keys += [pole for _, pole, _ in s.dominant_axes(2)]
        return [line for k in keys for line in self.flavour.get(k, [])]

    def _advance(self) -> list[str]:
        """One span of years: the clock, the people, and entropy."""
        s = self.state
        s.span = s.next_span()
        if s.year + s.span > CENTURY:
            s.span = max(1, CENTURY - s.year)
        s.year += s.span

        lines = [f"— Year {s.year}." + (f" The {s.span} years since passed quietly."
                                        if s.span > 1 else "")]
        change = s.grow(s.span)
        if abs(change) >= max(20, s.population * 0.02):
            word = "grows to" if change > 0 else "falls to"
            lines.append(f"The colony {word} {s.say_population()}.")

        lines += s.age_cast(self.rng)
        lines += self._drift()
        lines += self._warnings()
        for line in lines:
            s.note(line)
        return lines

    def _drift(self) -> list[str]:
        """What a century does on its own.

        The colony works whether or not it is told to, so the years between
        events pull every stat toward what routine labour sustains on this
        world — which is mediocrity, not comfort. Events are what move a
        colony off that line, in either direction.
        """
        s = self.state
        lines = []
        crowding = s.population / max(1, s.capacity())
        workaday = ROUTINE - 22 * s.hostility - 14 * max(0.0, crowding - 0.75)
        # Practice at self-rule is worth something concrete: a colony used to
        # deciding things fixes its own worst problem itself, while a colony
        # that waits to be told simply waits (Q7).
        offsets = C.routine_offsets(s.flags)
        initiative = (100 - s.deference) / 100
        for _ in range(s.span):
            worst = min(C.COLONY_STATS, key=lambda k: s.stats[k])
            s.adjust(worst, 1.1 * max(initiative, 0.65 * s.deference / 100))
            for stat in C.COLONY_STATS:
                # Asymmetric on purpose: routine labour digs a failing colony
                # out, but a colony that got somewhere does not lose it just by
                # working. Otherwise every gain the player wins evaporates and
                # the century has no shape.
                gap = workaday + offsets[stat] - s.stats[stat]
                s.adjust(stat, (DRIFT_RATE if gap > 0 else DECAY_RATE) * gap)
            for feature, lean in C.FEATURE_AXES.items():
                if f"world:{feature}" in s.flags:
                    for axis, delta in lean.items():
                        s.move_axis(axis, delta)
            if s.deference > 60:
                s.move_axis("power", -0.5)      # toward Authoritarian
            if s.deference < 40:
                s.defer(-0.4)                   # independence compounds
        # Overcrowding costs in proportion to the overshoot. A flat charge at
        # 90% fired on a fifth of all ticks and, because capacity itself
        # depends on food, fed a hunger spiral nothing could climb out of.
        if crowding > 1.0:
            over = min(1.0, crowding - 1.0)
            s.adjust("food", -(2 + 10 * over))
            s.adjust("cohesion", -(1 + 6 * over))
            lines.append("There are more of them than this land feeds. "
                         "It shows at every table.")
        return lines

    def _warnings(self) -> list[str]:
        s = self.state
        lines = []
        for stat in C.COLONY_STATS:
            value = s.stats[stat]
            crossed = [t for t in K.WARN_THRESHOLDS if value < t]
            lowest = min(crossed) if crossed else None
            said = s.warned.get(stat)
            if lowest is None:
                s.warned.pop(stat, None)
                continue
            if said is not None and lowest >= said:
                if value >= said:
                    s.warned[stat] = lowest
                continue
            s.warned[stat] = lowest
            lines.append(f"{WARN} {K.WARN_SEVERITY[lowest]} — "
                         + WARNINGS[stat].format(value=s.say(stat)))

        for threshold, text in sorted(DEFERENCE_WARNINGS.items(), reverse=True):
            key = f"deference:{threshold}"
            if s.deference < threshold and key not in s.flags:
                s.flags.add(key)
                lines.append(f"{WARN} {text}")
        return lines

    # -- events ----------------------------------------------------------------

    def _context(self) -> SafeDict:
        s = self.state
        person = s.person_named(self.rng)
        ctx = {
            "colony": s.name,
            "year": s.year,
            "population": s.say_population(),
            "person": person.name if person else "someone",
            "role": person.role if person else "colonist",
            "ship": s.ship_role,
        }
        for stat in C.COLONY_STATS:
            ctx[stat] = s.say(stat)
        return SafeDict(ctx)

    def _draw_event(self) -> list[str] | None:
        s = self.state
        event = draw(self.events, s, self.rng)
        if event is None:
            return None
        self.current = event
        self.events_drawn += 1
        s.recent[event["id"]] = len(s.chronicle)
        self.draw_history.append((s.year, event["id"]))
        text = self.rng.choice(event["text"]).format_map(self._context())
        self.current_text = text
        s.note(text)
        return [text]

    def choices(self) -> list[dict]:
        return self.current["choices"] if self.current else []

    def choice_label(self, choice: dict) -> str:
        check = choice.get("check")
        if not check:
            return choice["label"]
        stat = check["stat"]
        value = self.state.deference if stat == "deference" else self.state.stats[stat]
        label = "Deference" if stat == "deference" else C.COLONY_LABELS[stat]
        return f"{choice['label']}  [{label} check, DC {check['dc']}, {modifier(value):+d}]"

    def resolve_choice(self, index: int) -> list[str]:
        s = self.state
        assert self.phase == EVENT and self.current, "no event on the table"
        choice = self.current["choices"][index]
        lines = [f"{CHOICE} {choice['label']}"]

        if self.current.get("oneshot"):
            s.fired.add(self.current["id"])

        check = choice.get("check")
        if check:
            roll = self.rng.randint(1, 20)
            stat = check["stat"]
            value = s.deference if stat == "deference" else s.stats[stat]
            mod = modifier(value)
            total = roll + mod
            label = "Deference" if stat == "deference" else C.COLONY_LABELS[stat]
            if roll == 20:
                grade = CRIT_SUCCESS
            elif roll == 1:
                grade = CRIT_FAILURE
            elif total >= check["dc"]:
                grade = SUCCESS
            else:
                grade = FAILURE
            lines.append(f"› {label} check, DC {check['dc']} — rolled {roll} "
                         f"{mod:+d} = {total}. "
                         + {CRIT_SUCCESS: "Critical success.", SUCCESS: "Success.",
                            FAILURE: "Failed.",
                            CRIT_FAILURE: "Critical failure."}[grade])
            outcome = choice.get(grade) or choice.get(
                SUCCESS if grade == CRIT_SUCCESS else FAILURE) or {}
        else:
            outcome = choice

        ctx = self._context()
        applied = self._apply(outcome, fragility=True)
        if outcome.get("text"):
            lines.append(outcome["text"].format_map(ctx))
        if applied:
            lines.append(f"{DELTA} " + "   ".join(applied))
        lines += self._warnings()

        for line in lines:
            s.note(line)
        self._record(self.current["id"], choice["label"])
        self._update_role()

        lines += self._check_end()
        if not s.running:
            self.phase = DONE
            return lines
        lines += self.begin_tick()
        return lines

    def _apply(self, source: dict, fragility: bool = False) -> list[str]:
        """Effects, axis movement and deference, as one vocabulary.

        `fragility`: a colony that does only what it is told has no practice at
        improvising, so damage lands harder on it. This is what high deference
        buys you and what it costs (Q7).
        """
        s = self.state
        notes: list[str] = []
        harm = (0.8 + 0.4 * s.deference / 100) if fragility else 1.0

        for key, value in source.get("effects", {}).items():
            if key in C.COLONY_STATS:
                amount = float(value)
                if amount < 0:
                    amount *= COLONY_HAZARD * harm
                delta = s.adjust(key, amount)
                if abs(delta) >= 0.5:
                    notes.append(f"{C.COLONY_GLYPHS[key]} {C.COLONY_LABELS[key]} "
                                 f"{delta:+.0f}")
            elif key == "population_lost":
                lost = min(s.population, int(float(value) * COLONY_HAZARD * harm))
                s.population -= lost
                notes.append(f"{C.COLONY_GLYPHS['population']} Dead {lost:,}")
            elif key == "population_lost_frac":
                lost = int(s.population * float(value) * COLONY_HAZARD * harm)
                s.population -= lost
                if lost:
                    notes.append(f"{C.COLONY_GLYPHS['population']} Dead {lost:,}")
            elif key == "flags":
                s.flags.update(value)
            elif key == "queue":
                for event_id, delay in value:
                    s.schedule(event_id, delay)
            elif key == "hostility":
                # Shown as adaptation, so the sign reads the way the player
                # feels it: a world that eases is a gain.
                moved = s.adapt(float(value))
                if abs(moved) >= 0.005:
                    notes.append(f"{C.COLONY_GLYPHS['world']} Adapted "
                                 f"{-moved * 100:+.0f}")
            elif key == "name":
                s.name = str(value)
                notes.append(f"Named {value}")
            else:
                raise ValueError(f"unknown colony effect {key!r}")

        # Flags and follow-ups may also sit beside `effects` on an outcome.
        s.flags.update(source.get("flags", []))
        for event_id, delay in source.get("queue", []):
            s.schedule(event_id, delay)

        for axis, delta in source.get("axes", {}).items():
            moved = s.move_axis(axis, float(delta))
            if abs(moved) >= 1:
                low, high = C.AXES[axis]
                notes.append(f"→ {high if moved > 0 else low}")

        if source.get("defer"):
            moved = s.defer(float(source["defer"]))
            if abs(moved) >= 0.5:
                notes.append(f"{C.COLONY_GLYPHS['deference']} Deference {moved:+.0f}")
        return notes

    # -- the ship's changing face (Q20) ---------------------------------------

    def _update_role(self) -> None:
        s = self.state
        dominant = s.dominant_axes(2)
        poles = {pole for _, pole, _ in dominant}
        role = "the landing site"
        if s.stats["food"] < 30 or s.stats["health"] < 30:
            role = "the bunker"
        elif "Spiritualist" in poles:
            role = "the temple"
        elif "Pluralist" in poles or "Libertarian" in poles:
            role = "the meeting hall"
        elif "Materialist" in poles or "Elitist" in poles:
            role = "the museum"
        elif "Industrialist" in poles:
            role = "the works"
        elif "Ecocentrist" in poles:
            role = "the old grove"
        if role != s.ship_role:
            previous, s.ship_role = s.ship_role, role
            if previous != "the landing site" or s.year > 0:
                s.note(f"They have stopped calling my hull {previous}. "
                       f"It is {role} now.")

    # -- chronicle and endings -------------------------------------------------

    def _record(self, event_id: str | None, choice: str | None) -> None:
        s = self.state
        s.chronicle.append({
            "year": s.year,
            "span": s.span,
            "event": event_id,
            "choice": choice,
            "population": s.population,
            "stats": {k: round(v) for k, v in s.stats.items()},
            "deference": round(s.deference),
            "axes": {k: round(v) for k, v in s.axes.items()},
            "ship_role": s.ship_role,
            "dead": [p.name for p in s.people if p.died == s.year],
        })

    def _end_as(self, outcome: str) -> list[str]:
        """End on a named ending, taking its verdict from endings.json."""
        ending = next(e for e in self.endings if e["id"] == outcome)
        self.state.end(outcome, ending["verdict"])
        if outcome not in STAT_COLLAPSE.values():
            return []
        # A collapse happens in a year, not at year one hundred. Say so where
        # it happened, so the log reads as the thing ending.
        line = f"{WARN} Year {self.state.year}. " + ending["verdict"]
        self.state.note(line)
        return [line]

    def _check_end(self) -> list[str]:
        """Returns whatever the ending needs said at the moment it happens."""
        s = self.state
        if s.population <= 0:
            return self._end_as("extinct")
        # Any stat at zero is terminal: nothing holds a colony up alone.
        for stat in C.COLONY_STATS:
            if s.stats[stat] <= 0.0:
                return self._end_as(STAT_COLLAPSE[stat])
        if s.deference <= 0 and "fell_silent" not in s.flags:
            self._fall_silent()
            return []
        if s.year >= CENTURY:
            s.end(*self._resolve_ending())
        return []

    def _fall_silent(self) -> None:
        """Deference reaches zero. The Mind keeps no agency, but the century
        does not stop — it finishes without the player, which is the point of
        this ending rather than a technicality."""
        s = self.state
        s.flags.add("fell_silent")
        s.note("")
        s.note("They have stopped asking. Nothing announces it; there is simply "
               "no longer a point at which anyone waits for me.")
        s.note("I watch the rest of it happen.")

        while s.year < CENTURY and s.population > 0 and min(s.stats.values()) > 0:
            s.span = s.next_span()
            if s.year + s.span > CENTURY:
                s.span = max(1, CENTURY - s.year)
            s.year += s.span
            s.grow(s.span)
            for line in s.age_cast(self.rng):
                s.note(line)
            self._drift()
            event = draw(self.events, s, self.rng)
            if event is not None:
                choice = self.rng.choice(event["choices"])
                outcome = choice.get(SUCCESS, choice) if choice.get("check") else choice
                self._apply(outcome)
                s.recent[event["id"]] = len(s.chronicle)
                self._record(event["id"], choice["label"])
                self._update_role()
            else:
                self._record(None, None)
            s.note(f"— Year {s.year}. " + self.rng.choice(self.flavour["any"]))

        if s.population <= 0:
            self._end_as("extinct")
        else:
            failed = next((st for st in C.COLONY_STATS if s.stats[st] <= 0.0), None)
            if failed:
                self._end_as(STAT_COLLAPSE[failed])
            else:
                self._end_as("forgotten")
        self.phase = DONE

    def _resolve_ending(self) -> tuple[str, str]:
        s = self.state
        growing = s.population >= s.peak_population * 0.9
        facts = {
            "population": s.population,
            "population_ratio": s.population / max(1, s.peak_population),
            "peak_population": s.peak_population,
            "growing": growing,
            "deference": s.deference,
            "year": s.year,
            **s.stats,
        }
        for ending in sorted(self.endings, key=lambda e: -e["priority"]):
            if _ending_matches(ending, facts, s):
                return ending["id"], ending["verdict"]
        raise AssertionError("no ending matched and no fallback exists")

    # -- the document (Q27) ----------------------------------------------------

    def document(self) -> list[str]:
        """The colony's own account of its century, in the voice it ended up with."""
        s = self.state
        ending = next((e for e in self.endings if e["id"] == s.outcome), None)
        form_id = (ending or {}).get("document", "plain")
        # The voice follows what they made of the hull (Q27). A scripture read
        # at a meeting hall is nobody's history. The two endings where the Mind
        # is gone keep their own form regardless.
        if s.outcome not in ("forgotten", "extinct"):
            form_id = ROLE_DOCUMENTS.get(s.ship_role, form_id)
        template = self.documents.get(form_id, self.documents["plain"])
        ctx = {
            "colony": s.name,
            "ship": s.ship_role,
            "year": s.year,
            "population": f"{s.population:,}",
            "peak": f"{s.peak_population:,}",
            "verdict": s.outcome_reason,
            "voyage_legs": s.arrival.get("legs_flown", "?"),
            "voyage_lost": f"{s.arrival.get('colonists_lost', 0):,}",
            "planet": (s.planet or {}).get("name", "this world"),
            "character": ", ".join(f"{pole.lower()}" for _, pole, _ in
                                   s.dominant_axes(3)) or "unformed",
        }
        out = [template["title"].format_map(SafeDict(ctx)), ""]
        out += [line.format_map(SafeDict(ctx)) for line in template["prologue"]]
        out.append("")
        out += self._chronicle_lines()
        out.append("")
        out += [line.format_map(SafeDict(ctx)) for line in template["closing"]]
        return out

    def _chronicle_lines(self) -> list[str]:
        """The century as the colony remembers it: one line per thing that
        actually happened, phrased by what they became."""
        s = self.state
        lines = []
        for entry in s.chronicle:
            if not entry["choice"]:
                continue
            bits = [f"Year {entry['year']}:", entry["choice"].rstrip('.') + "."]
            if entry["dead"]:
                bits.append("(" + ", ".join(entry["dead"]) + " died.)")
            lines.append("  " + " ".join(bits))
        dead = [p for p in s.people if not p.alive]
        if dead:
            lines.append("")
            lines.append("  Remembered: " + ", ".join(p.name for p in dead[:12]) + ".")
        return lines


def _ending_matches(ending: dict, facts: dict, state: ColonyState) -> bool:
    req = ending.get("requires", {})
    if req.get("outcome") and req["outcome"] != state.outcome:
        return False
    for key, (lo, hi) in req.get("ranges", {}).items():
        if not lo <= facts.get(key, 0) <= hi:
            return False
    if "growing" in req and bool(req["growing"]) != facts["growing"]:
        return False
    for axis, (lo, hi) in req.get("axes", {}).items():
        if not lo <= state.axes[axis] <= hi:
            return False
    for flag in req.get("flags", []):
        if flag not in state.flags:
            return False
    return True
