"""Act 2's engine: a hundred years, one directive and one event at a time.

Mirrors `resolve.py` deliberately — same two-phase tick, same d20 curve, same
effect vocabulary — so the TUI and the tests work the same way in both acts.
What differs is the clock (ticks widen as the colony steadies), the axes (a
choice can shift what these people believe), and deference, which is both the
Mind's authority and its eyesight.
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

DIRECTIVE = "directive"
EVENT = "event"
DONE = "done"

CENTURY = 100
EVENT_COOLDOWN = 3

# Act 1's HAZARD_SCALE, for the century: multiplies authored damage and deaths
# so difficulty moves with one number instead of twenty content edits.
# Tuned against colony_sim.py's steward policy.
COLONY_HAZARD = 1.0

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


# --- directives (Q22) --------------------------------------------------------
#
# One per tick. Issuing orders keeps a colony dependent, so deference holds or
# rises; standing back lowers it and buys cohesion. That is the whole trade.

DIRECTIVES = [
    {"id": "fields", "label": "Put every hand into the fields",
     "effects": {"food": +9, "industry": -4}, "defer": +1},
    {"id": "build", "label": "Build: shelter, tools, machines",
     "effects": {"industry": +9, "food": -4}, "defer": +1},
    {"id": "tend", "label": "Tend the sick and bury the dead properly",
     "effects": {"health": +9, "industry": -3}, "defer": +1},
    {"id": "teach", "label": "Teach the children what the archive holds",
     "effects": {"knowledge": +9, "food": -3}, "defer": +1},
    {"id": "hold", "label": "Settle the disputes myself",
     "effects": {"cohesion": +8}, "defer": +3},
    {"id": "maintain", "label": "Ask them to maintain me",
     "effects": {"industry": -6}, "defer": +4,
     "requires_deference": 25.0},
    {"id": "record", "label": "Keep the record: who lived, what was decided",
     "effects": {"knowledge": +4, "cohesion": +2}, "defer": 0},
    {"id": "let_them", "label": "Say nothing. Let them decide this one",
     "effects": {"cohesion": +5}, "defer": -7, "axes": {"power": +4}},
]

DIRECTIVE_PROSE = {
    "fields": "I put every hand I can direct into the fields.",
    "build": "I set them building. The sound of it carries for miles.",
    "tend": "I give the infirmary everything it asks for.",
    "teach": "I open the archive to the children and teach them for a season.",
    "hold": "I hear the disputes myself and rule on them. They accept it.",
    "maintain": "I ask them to spend a season keeping me running. They do.",
    "record": "I write down who lived here, and what was decided, and by whom.",
    "let_them": "I say nothing at all, and let them work it out themselves.",
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
        self.phase = DIRECTIVE
        self.current: dict | None = None
        self.current_text = ""
        self.events_drawn = 0
        self.draw_history: list[tuple[int, str]] = []
        self._open()

    # -- opening ---------------------------------------------------------------

    def _open(self) -> None:
        s = self.state
        s.note(f"— Year {s.year}. Landfall.")
        s.note(C.planet_pressure(s))
        if s.thaw_losses:
            s.note(f"The thaw takes {s.thaw_losses:,} of them before the first "
                   "morning. I record every name.")
        s.note(f"{s.population:,} people stand on a world nobody has ever walked on. "
               "They are waiting to be told what to do.")
        self._update_role()

    # -- the tick --------------------------------------------------------------

    def begin_tick(self) -> list[str]:
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

        self._check_end()
        self.phase = DONE if not s.running else DIRECTIVE
        for line in lines:
            s.note(line)
        return lines

    def _drift(self) -> list[str]:
        """What a century does on its own: hunger, entropy, and the slow lesson
        that obedience is how decisions get made (Q17)."""
        s = self.state
        lines = []
        # Practice at self-rule is worth something concrete: a colony used to
        # deciding things fixes its own worst problem between ticks, while a
        # colony that waits to be told simply waits (Q7).
        initiative = (100 - s.deference) / 100
        for _ in range(s.span):
            worst = min(C.COLONY_STATS, key=lambda k: s.stats[k])
            s.adjust(worst, 1.6 * initiative)
            s.adjust("food", -0.85 * (0.4 + s.hostility))
            s.adjust("industry", -0.55)
            s.adjust("health", -0.4 * (0.4 + s.hostility))
            s.adjust("knowledge", -0.3)
            if s.deference > 60:
                s.move_axis("power", -0.5)      # toward Authoritarian
            if s.deference < 40:
                s.defer(-0.4)                   # independence compounds
        crowding = s.population / max(1, s.capacity())
        if crowding > 0.9:
            s.adjust("food", -4)
            s.adjust("cohesion", -3)
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

    # -- directives ------------------------------------------------------------

    def directive_options(self) -> list[dict]:
        s = self.state
        return [d for d in DIRECTIVES
                if s.deference >= d.get("requires_deference", 0.0)]

    def do_directive(self, directive_id: str) -> list[str]:
        s = self.state
        assert self.phase == DIRECTIVE, "not the directive phase"
        directive = next(d for d in DIRECTIVES if d["id"] == directive_id)

        # A colony that has stopped deferring does not simply comply.
        obeyed = True
        if directive_id != "let_them" and s.deference < 55:
            roll = self.rng.randint(1, 20) + modifier(s.deference)
            obeyed = roll >= 10
        lines = [f"{CHOICE} {directive['label']}"]

        if not obeyed:
            lines.append("They hear me out, and then do what they were already "
                         "going to do.")
            s.defer(-1)
            s.adjust("cohesion", -1)
        else:
            lines.append(DIRECTIVE_PROSE[directive_id])
            applied = self._apply(directive, scale=max(1, s.span) ** 0.5)
            if applied:
                lines.append(f"{DELTA} " + "   ".join(applied))

        lines += self._warnings()
        for line in lines:
            s.note(line)
        self._check_end()
        if not s.running:
            self.phase = DONE
            return lines
        self.phase = EVENT
        lines += self._draw_event()
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

    def _draw_event(self) -> list[str]:
        s = self.state
        event = draw(self.events, s, self.rng)
        if event is None:
            line = self.rng.choice(self.flavour["any"])
            s.note(line)
            self._record(None, None)
            return [line] + self.begin_tick()
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

        self._check_end()
        if not s.running:
            self.phase = DONE
            return lines
        lines += self.begin_tick()
        return lines

    def _apply(self, source: dict, scale: float = 1.0,
               fragility: bool = False) -> list[str]:
        """Effects, axis movement and deference, as one vocabulary.

        `fragility` applies to events, not directives: a colony that does only
        what it is told has no practice at improvising, so a crisis costs it
        more. This is what high deference buys you and what it costs (Q7).
        """
        s = self.state
        notes: list[str] = []
        harm = (0.65 + 0.7 * s.deference / 100) if fragility else 1.0

        for key, value in source.get("effects", {}).items():
            if key in C.COLONY_STATS:
                amount = float(value) * scale
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

    def _check_end(self) -> None:
        s = self.state
        if s.population <= 0:
            s.end("extinct", "No one is left to call it a colony.")
            return
        if s.deference <= 0 and "fell_silent" not in s.flags:
            self._fall_silent()
            return
        if s.year >= CENTURY:
            s.end(*self._resolve_ending())

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

        while s.year < CENTURY and s.population > 0:
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
            s.end("extinct", "No one is left to call it a colony.")
        else:
            s.end("forgotten", "They finished the century without me.")
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
