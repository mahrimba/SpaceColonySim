"""The engine: leg cadence, maintenance, d20 checks, effects, commitment.

Headless and UI-agnostic. `app.py` is a view onto this; `sim.py` drives it
with a scripted policy.
"""

from __future__ import annotations

import random

import constants as K
import deck
import planets
from state import SafeDict, ShipState

# Markers let a front end style mechanics apart from prose without parsing it.
DELTA = "·"    # a line of stat changes
CHOICE = "»"   # the option the player took
TABLE = "│"    # a row of survey data

MAINTENANCE = "maintenance"
EVENT = "event"
DONE = "done"

CRIT_SUCCESS, SUCCESS, FAILURE, CRIT_FAILURE = (
    "crit_success", "success", "failure", "crit_failure")

EFFECT_KEYS = set(K.STATS) | {
    "colonists_lost", "colonists_lost_frac", "flags", "clear_flags", "queue", "end"}

# Actions that keep the ship moving. Everything else is lingering, and
# lingering rolls for a nick or an observation (Q19 follow-up).
ADVANCING = {"hold", "hard_burn"}

REPAIRABLE = ["hull", "power", "life_support"] + K.HOLDS
SCRAP_TARGETS = ["hull", "power", "life_support"]


def modifier(stat_value: float) -> int:
    """(stat - 50) // 10, so -5..+4. Checked: every DC stays winnable."""
    return int((stat_value - K.MOD_PIVOT) // K.MOD_DIVISOR)


class Game:
    def __init__(self, profile: str = "survey", seed: int | None = None,
                 events: list[dict] | None = None):
        self.seed = random.randrange(1, 2**31) if seed is None else seed
        self.rng = random.Random(self.seed)
        self.events = events if events is not None else deck.load()
        self.flavour = deck.load_flavour()
        self.state = ShipState.launch(profile)
        self.phase = MAINTENANCE
        self.current: dict | None = None
        self.current_text = ""
        self.events_drawn = 0  # must never exceed legs flown: one event per leg
        self.draw_history: list[tuple[int, str]] = []
        self.state.note(f"{self.state.name} underway. Seed {self.seed}.")
        self._enter_system()

    # -- system / leg bookkeeping --------------------------------------------

    def _enter_system(self) -> list[str]:
        s = self.state
        s.leg += 1
        s.adjust("fuel", -K.FUEL_PER_LEG)

        a, b = K.SYSTEM_NAME_PARTS
        s.system_name = f"{self.rng.choice(a)} {self.rng.choice(b)}"
        tag_names = list(K.SYSTEM_TAGS)
        weights = [K.SYSTEM_TAGS[t] for t in tag_names]
        n_tags = self.rng.randint(*K.TAGS_PER_SYSTEM)
        tags: set[str] = set()
        while len(tags) < n_tags:
            tags.add(self.rng.choices(tag_names, weights=weights)[0])
        s.system_tags = tags

        lines = [f"— Leg {s.leg}. {s.system_name}: {', '.join(sorted(tags)).replace('_', ' ')}."]
        lines += s.passive_tick(self.rng)
        lines += s.threshold_warnings()

        if s.flying and s.leg % K.SURVEY_EVERY == 0:
            found = s.survey(self.rng)
            lines += self._survey_report(found, "A scheduled sweep completes.")

        if not s.flying:
            self.phase = DONE
        else:
            self.phase = MAINTENANCE
        for line in lines:
            s.note(line)
        return lines

    def _survey_report(self, found: list[planets.Planet], opening: str) -> list[str]:
        """What a sweep actually tells the player: the worlds, and how well it
        can see them. The table reads at the cognition it was taken at."""
        s = self.state
        if not found:
            return [f"{opening} Nothing out here holds together into a world."]
        count = "One world resolves" if len(found) == 1 else f"{len(found)} worlds resolve"
        lines = [f"{opening} {count} out of the dark."]
        lines += [f"{TABLE} {row}" for row in planets.table(found)]
        if s.cognition < K.APPROX_ABOVE:
            lines.append("The readings come back soft at the edges. I am reading "
                         "them through myself, and I am not well.")
        elif s.cognition < K.PRECISE_ABOVE:
            lines.append("Close enough to act on. Not close enough to be sure.")
        return lines

    # -- maintenance (Q19) ----------------------------------------------------

    def maintenance_options(self) -> list[dict]:
        """Concrete actions available right now, as data the UI can render."""
        s = self.state
        opts: list[dict] = [{"action": "hold", "label": "Hold course (do nothing)"}]
        if s.stats["power"] > K.DIAGNOSTIC_POWER_COST:
            opts.append({"action": "diagnostics",
                         "label": f"Run self-diagnostics (+cognition, "
                                  f"-{K.DIAGNOSTIC_POWER_COST:.0f} power)"})
        opts.append({"action": "survey", "label": "Sweep this system for worlds"})
        if s.stats["power"] > K.REPAIR_POWER_COST:
            for stat in REPAIRABLE:
                opts.append({"action": "repair", "target": stat,
                             "label": f"Repair {K.LABELS[stat].lower()} "
                                      f"(-{K.REPAIR_POWER_COST:.0f} power)"})
        for hold in K.HOLDS:
            opts.append({"action": "cannibalize", "hold": hold,
                         "label": f"Strip {K.LABELS[hold].lower()} for parts"})
        if s.stats["fuel"] >= K.HARD_BURN_FUEL:
            opts.append({"action": "hard_burn",
                         "label": f"Hard burn through (-{K.HARD_BURN_FUEL:.0f} fuel, "
                                  "skip what waits here)"})
        return opts

    def do_maintenance(self, action: str, target: str | None = None,
                       hold: str | None = None) -> list[str]:
        s = self.state
        assert self.phase == MAINTENANCE, "not the maintenance phase"
        lines: list[str] = []
        skip_event = False

        if action == "hold":
            lines.append("I keep my hands still and listen to the hull.")

        elif action == "diagnostics":
            s.adjust("power", -K.DIAGNOSTIC_POWER_COST)
            gained = s.adjust("cognition", K.DIAGNOSTIC_GAIN)
            lines.append(f"I walk my own corridors, sector by sector. "
                         f"{gained:+.0f} to coherence. Some of what I find, I had "
                         "forgotten I had lost.")

        elif action == "survey":
            found = s.survey(self.rng)
            lines += self._survey_report(found, "I turn the long instruments outward.")

        elif action == "repair":
            assert target in REPAIRABLE, target
            s.adjust("power", -K.REPAIR_POWER_COST)
            amount = K.REPAIR_BASE + s.stats["fabricators"] * K.REPAIR_PER_FABRICATOR
            gained = s.adjust(target, amount)
            lines.append(f"Fabricators run hot for a shift. " + (
                f"{K.LABELS[target]} {gained:+.0f}." if gained >= 0.5
                else f"{K.LABELS[target]} was already as good as I can make it."))

        elif action == "cannibalize":
            assert hold in K.HOLDS, hold
            target = target or min(SCRAP_TARGETS, key=lambda st: s.stats[st])
            s.adjust(hold, -K.CANNIBALIZE_HOLD_COST)
            gained = s.adjust(target, K.CANNIBALIZE_GAIN)
            lines.append(f"I take apart {K.LABELS[hold].lower()} to keep "
                         f"{K.LABELS[target].lower()} alive. {gained:+.0f} there, "
                         f"-{K.CANNIBALIZE_HOLD_COST:.0f} to a thing the colony "
                         "was going to need.")

        elif action == "hard_burn":
            s.adjust("fuel", -K.HARD_BURN_FUEL)
            skip_event = True
            lines.append("I do not slow down for this system. Whatever was here, "
                         "we are already past it.")
        else:
            raise ValueError(f"unknown maintenance action {action!r}")

        if action not in ADVANCING and s.flying:
            roll = self.rng.random()
            if roll < K.LINGER_HAZARD_CHANCE:
                lines.append(s.minor_hazard(self.rng))
            elif roll < K.LINGER_HAZARD_CHANCE + K.LINGER_FLAVOUR_CHANCE:
                lines.append(deck.observe(self.flavour, s, self.rng))

        lines += s.threshold_warnings()
        for line in lines:
            s.note(line)
        s._check_death()
        if not s.flying:
            self.phase = DONE
            return lines

        if skip_event:
            lines += self._enter_system()
        else:
            self.phase = EVENT
            lines += self._draw_event()
        return lines

    # -- events ---------------------------------------------------------------

    def _context(self) -> SafeDict:
        s = self.state
        ctx = {
            "system": s.system_name,
            "ship": s.name,
            "colonist": s.colonist(self.rng),
            "colonists": s.say_count(s.colonists_alive),
            "lost_total": s.say_count(s.colonists_lost),
            "leg": s.leg,
        }
        for stat in K.STATS:
            ctx[stat] = s.say(stat)
        return SafeDict(ctx)

    def _draw_event(self) -> list[str]:
        event = deck.draw(self.events, self.state, self.rng)
        if event is None:
            self.current = None
            self.current_text = ""
            line = "Nothing out here but the sound of my own pumps."
            self.state.note(line)
            return [line] + self._enter_system()

        self.current = event
        self.events_drawn += 1
        self.state.recent[event["id"]] = self.state.leg
        self.draw_history.append((self.state.leg, event["id"]))
        variants = event["text"]
        self.current_text = self.rng.choice(variants).format_map(self._context())
        self.state.note(self.current_text)
        return [self.current_text]

    def choices(self) -> list[dict]:
        return self.current["choices"] if self.current else []

    def choice_label(self, choice: dict) -> str:
        label = choice["label"]
        check = choice.get("check")
        if not check:
            return label
        mod = modifier(self.state.stats[check["stat"]])
        return (f"{label}  [{K.LABELS[check['stat']]} check, DC {check['dc']}, "
                f"{mod:+d}]")

    def resolve_choice(self, index: int) -> list[str]:
        s = self.state
        assert self.phase == EVENT and self.current, "no event on the table"
        choice = self.current["choices"][index]
        lines: list[str] = [f"{CHOICE} {choice['label']}"]

        if self.current.get("oneshot"):
            s.fired.add(self.current["id"])

        check = choice.get("check")
        if check:
            roll = self.rng.randint(1, 20)
            mod = modifier(s.stats[check["stat"]])
            total = roll + mod
            dc = check["dc"]
            if roll == 20:
                grade = CRIT_SUCCESS
            elif roll == 1:
                grade = CRIT_FAILURE
            elif total >= dc:
                grade = SUCCESS
            else:
                grade = FAILURE
            lines.append(
                # No square brackets: these lines pass through Textual
                # markup on the way to the screen.
                f"› {K.LABELS[check['stat']]} check, DC {dc} — rolled {roll} "
                f"{mod:+d} = {total}. "
                + {CRIT_SUCCESS: "Critical success.", SUCCESS: "Success.",
                   FAILURE: "Failed.", CRIT_FAILURE: "Critical failure."}[grade]
            )
            outcome = choice.get(grade) or choice.get(
                SUCCESS if grade == CRIT_SUCCESS else FAILURE) or {}
        else:
            outcome = choice

        ctx = self._context()
        applied = self._apply(outcome.get("effects", {}), ctx)
        text = outcome.get("text", "")
        if text:
            lines.append(text.format_map(ctx))
            # If this outcome killed sleepers and named one, that name is a
            # death, not a character the Mind can mention again later.
            if "{colonist}" in text and "lost" in ctx:
                s.mourn(ctx["colonist"])
        if applied:
            lines.append(f"{DELTA} " + "   ".join(applied))
        lines += s.threshold_warnings()

        for line in lines:
            s.note(line)

        s._check_death()
        if not s.flying:
            self.phase = DONE
            return lines
        lines += self._enter_system()
        return lines

    def _apply(self, effects: dict, ctx: SafeDict) -> list[str]:
        """Mutate state from an effects dict; return short deltas for the log."""
        s = self.state
        notes: list[str] = []

        for key, value in effects.items():
            if key in K.STATS:
                amount = float(value)
                if amount < 0:
                    amount *= K.HAZARD_SCALE
                delta = s.adjust(key, amount)
                if abs(delta) >= 0.5:
                    notes.append(f"{K.GLYPHS[key]} {K.LABELS[key]} {delta:+.0f}")
            elif key == "colonists_lost":
                lost = s.kill(int(value) * K.HAZARD_SCALE)
                ctx["lost"] = s.say_count(lost)
                if lost:
                    notes.append(f"{K.GLYPHS['lost']} Sleepers lost {s.say_count(lost)}")
            elif key == "colonists_lost_frac":
                lost = s.kill(s.colonists_alive * float(value) * K.HAZARD_SCALE)
                ctx["lost"] = s.say_count(lost)
                if lost:
                    notes.append(f"{K.GLYPHS['lost']} Sleepers lost {s.say_count(lost)}")
            elif key == "flags":
                s.flags.update(value)
            elif key == "clear_flags":
                s.flags.difference_update(value)
            elif key == "queue":
                for event_id, in_legs in value:
                    s.schedule(event_id, in_legs)
            elif key == "end":
                s.end(value["outcome"], value["reason"])
            elif key not in EFFECT_KEYS:
                raise ValueError(f"unknown effect {key!r}")
        return notes

    # -- commitment (Q35) -----------------------------------------------------

    def can_commit(self) -> bool:
        return bool(self.state.candidates) and self.state.stats["fuel"] >= K.DECEL_FUEL_COST

    def commit(self, planet: planets.Planet) -> list[str]:
        s = self.state
        assert self.can_commit(), "cannot commit from here"
        s.adjust("fuel", -K.DECEL_FUEL_COST)
        s.chosen_planet = planet
        s.end("colonized", f"Committed to {planet.name}.")
        self.phase = DONE
        lines = [
            f"I turn the ship around and burn against our own momentum. "
            f"{planet.name} grows in the forward instruments.",
            "Thaw sequence armed. Whatever this world is, it is ours now.",
        ]
        for line in lines:
            s.note(line)
        return lines

    # -- arrival report (Q15) -------------------------------------------------

    def report(self) -> list[str]:
        s = self.state
        out = [f"Outcome: {s.outcome}. {s.outcome_reason}",
               f"Legs flown: {s.leg}.  Seed: {self.seed}.  Profile: {s.profile}.",
               f"Sleepers alive: {s.colonists_alive:,} "
               f"(lost {s.colonists_lost:,})."]
        out.append("Condition at arrival: " + ", ".join(
            f"{K.LABELS[k]} {s.stats[k]:.0f}" for k in K.STATS))
        if s.chosen_planet:
            p = s.chosen_planet
            out.append(f"World: {p.name} — judged {p.verdict()} once the "
                       "instruments stopped guessing.")
            out += [f"  {k}: {v}" for k, v in p.dossier()]
        if s.flags:
            out.append("Carried into the colony: " + ", ".join(sorted(s.flags)))
        if s.notables:
            out.append("Named in the log: " + ", ".join(s.notables[:8]))
        return out
