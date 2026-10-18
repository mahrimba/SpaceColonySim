"""Ship state: the numbers, the memory, and how a leg grinds them down."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

import constants as K
import planets
import readout


class SafeDict(dict):
    """Missing template slots render as themselves instead of crashing a run."""

    def __missing__(self, key):
        return "{" + key + "}"


@dataclass
class ShipState:
    profile: str = "survey"
    name: str = "unnamed hull"
    leg: int = 0
    stats: dict[str, float] = field(default_factory=dict)
    colonists_alive: int = K.START_COLONISTS
    colonists_lost: int = 0
    flags: set[str] = field(default_factory=set)
    fired: set[str] = field(default_factory=set)      # one-shot events spent
    queue: list[list] = field(default_factory=list)   # [leg_due, event_id]
    system_name: str = ""
    system_tags: set[str] = field(default_factory=set)
    candidates: list[planets.Planet] = field(default_factory=list)
    notables: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    outcome: str | None = None       # None while flying
    outcome_reason: str = ""
    chosen_planet: planets.Planet | None = None

    # -- construction ---------------------------------------------------------

    @classmethod
    def launch(cls, profile: str) -> ShipState:
        spec = K.PROFILES[profile]
        stats = {s: 100.0 for s in K.STATS}
        stats["cognition"] = 90.0
        for stat, delta in spec["stats"].items():
            stats[stat] = max(0.0, min(100.0, stats[stat] + delta))
        return cls(
            profile=profile,
            name=spec["name"],
            stats=stats,
            colonists_alive=K.START_COLONISTS + spec["colonists"],
        )

    # -- reading --------------------------------------------------------------

    @property
    def cognition(self) -> float:
        return self.stats["cognition"]

    @property
    def flying(self) -> bool:
        return self.outcome is None

    def say(self, stat: str) -> str:
        return readout.stat(self.stats[stat], self.cognition)

    def say_count(self, value: int) -> str:
        return readout.count(value, self.cognition)

    def legs_of_fuel(self) -> float:
        return self.stats["fuel"] / K.FUEL_PER_LEG

    # -- writing --------------------------------------------------------------

    def adjust(self, stat: str, delta: float) -> float:
        """Move a 0-100 stat, returning the change actually applied."""
        before = self.stats[stat]
        self.stats[stat] = max(0.0, min(100.0, before + delta))
        return self.stats[stat] - before

    def kill(self, n: int) -> int:
        n = max(0, min(self.colonists_alive, int(n)))
        self.colonists_alive -= n
        self.colonists_lost += n
        return n

    def note(self, line: str) -> None:
        self.log.append(line)

    def schedule(self, event_id: str, in_legs: int) -> None:
        self.queue.append([self.leg + max(1, int(in_legs)), event_id])

    def due_event(self) -> str | None:
        for entry in list(self.queue):
            if entry[0] <= self.leg:
                self.queue.remove(entry)
                return entry[1]
        return None

    def end(self, outcome: str, reason: str) -> None:
        if self.flying:
            self.outcome = outcome
            self.outcome_reason = reason

    # -- people ---------------------------------------------------------------

    def colonist(self, rng: random.Random, reuse: float = 0.35) -> str:
        """A name for a sleeper an event needs. Sometimes recalls an old one."""
        if self.notables and rng.random() < reuse:
            return rng.choice(self.notables)
        name = f"{rng.choice(K.COLONIST_FIRST)} {rng.choice(K.COLONIST_LAST)}"
        self.notables.append(name)
        return name

    # -- the physics that happens whether you act or not (Q18, Q20) -----------

    def passive_tick(self, rng: random.Random) -> list[str]:
        lines: list[str] = []
        for stat, rate in K.PASSIVE_DRAIN.items():
            self.adjust(stat, -rate)

        if 0 < self.stats["power"] <= K.POWER_WARNING:
            self.adjust("life_support", -K.POWER_BROWNOUT_DRAIN)
            self.adjust("cognition", -K.COGNITION_DRAIN_AT_BROWNOUT)
            lines.append("Reactor output is marginal. Scrubbers are coasting and "
                         "I am thinking slower than I should be. If it goes out, "
                         "everything goes out.")

        ls = self.stats["life_support"]
        if ls < K.LIFE_SUPPORT_CRITICAL:
            severity = 1.0 - (ls / K.LIFE_SUPPORT_CRITICAL)
            lost = self.kill(self.colonists_alive * K.LIFE_SUPPORT_LOSS_RATE * severity)
            if lost:
                lines.append(
                    f"Cryo bank temperatures out of tolerance. {self.say_count(lost)} "
                    "did not come back from the cold."
                )

        self._check_death()
        return lines

    def _check_death(self) -> None:
        if self.stats["hull"] <= 0:
            self.end("destroyed", "Hull failure. The ship came apart around its sleepers.")
        elif self.stats["power"] <= 0:
            # Nothing aboard works without the reactor: no scrubbers, no
            # heaters, no thaw. Zero power is an ending, not a penalty.
            self.end("dark", "The reactor went out. Heaters, scrubbers, pod "
                             "controllers, me — all of it ran down together. Ten "
                             "thousand people froze without ever waking up.")
        elif self.colonists_alive <= 0:
            self.end("extinct", "Every pod is dark. I am carrying a cemetery.")
        elif self.stats["cognition"] <= 0:
            self.end("incoherent", "I lost the thread of myself. The ship still flies, "
                                   "but no one is steering it.")
        elif self.stats["fuel"] <= 0:
            # Deceleration costs fuel, so empty tanks end the voyage whether or
            # not a world is in sight. Dry with a garden below is still dry.
            self.end("adrift", "Tanks dry. Whatever is out there, we pass it at "
                               "speed and keep going forever.")

    def minor_hazard(self, rng: random.Random) -> str:
        """An unannounced nick. Rolled when the ship lingers, not every leg."""
        stat = rng.choice(["hull", "power", "cognition"] + K.HOLDS)
        dmg = rng.uniform(*K.MINOR_HAZARD_DAMAGE)
        self.adjust(stat, -dmg)
        self._check_death()
        return MINOR_HAZARD_FLAVOUR.get(stat, "Something small took a bite.").format_map(
            SafeDict(amount=f"{dmg:.1f}"))

    # -- survey ---------------------------------------------------------------

    def survey(self, rng: random.Random) -> list[planets.Planet]:
        n = rng.randint(*K.CANDIDATES_PER_SURVEY)
        found = [planets.generate(rng, self.system_tags, self.cognition) for _ in range(n)]
        self.candidates.extend(found)
        return found

    # -- Act 2 handoff (Q15) --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "ship": self.name,
            "legs_flown": self.leg,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "stats": {k: round(v, 2) for k, v in self.stats.items()},
            "colonists_alive": self.colonists_alive,
            "colonists_lost": self.colonists_lost,
            "flags": sorted(self.flags),
            "notables": self.notables,
            "planet": self.chosen_planet.to_dict() if self.chosen_planet else None,
            "log": self.log,
        }

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)


MINOR_HAZARD_FLAVOUR = {
    "hull": "A micrometeoroid finds plating. {amount} points of skin, gone quietly.",
    "power": "A bus fault trips and resets itself. Something is wearing out.",
    "cognition": "A memory sector fails parity. I do not know what was in it.",
    "seed_vault": "Condensation in the seed racks. A little of the future spoils.",
    "fabricators": "A tool head seizes. I log it and move on.",
    "habitat": "Shelter panels flex in the cold and craze.",
    "medical": "A refrigerant line weeps. Some ampoules are no longer medicine.",
    "archive": "Bit rot in the archive. A language loses a few of its poems.",
}
