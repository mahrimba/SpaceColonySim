"""Act 2: the first century on the ground.

The Mind lands with its colony and stops being a ship. It keeps no stats of
its own here; everything tracked is the colony's. What the Mind has instead
is `deference` — how much these people still do as they are told — and that
single number is both its power and its eyesight: a colony that defers files
exact reports, and a colony that has outgrown you stops telling you things.

Reuses Act 1's resolution machinery (`resolve.modifier`, the d20 grades, the
deck) rather than forking it.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

import constants as K
import planets
import readout

# --- the colony --------------------------------------------------------------

COLONY_STATS = ["food", "industry", "health", "knowledge", "cohesion"]

COLONY_LABELS = {
    "food": "Food",
    "industry": "Industry",
    "health": "Health",
    "knowledge": "Knowledge",
    "cohesion": "Cohesion",
}

COLONY_GLYPHS = {
    "food": "🌾", "industry": "🔨", "health": "⚕", "knowledge": "📖",
    "cohesion": "🤝", "population": "👣", "deference": "🜂",
}

COLONY_COLOURS = {
    "food": "limegreen", "industry": "orange", "health": "red",
    "knowledge": "mediumpurple", "cohesion": "gold", "deference": "cyan",
}

# Five bipolar axes, -100 to +100, all starting at zero. Negative is the first
# pole, positive the second. A colony is a tabula rasa until its century
# writes something on it.
AXES = {
    "society": ("Cooperative", "Competitive"),
    "nature": ("Ecocentrist", "Industrialist"),
    "belief": ("Materialist", "Spiritualist"),
    "power": ("Authoritarian", "Libertarian"),
    "status": ("Elitist", "Pluralist"),
}

ROLES = ["farmer", "engineer", "physician", "speaker", "archivist", "surveyor"]

TRAITS = ["stubborn", "generous", "devout", "sceptical", "brilliant", "tired",
          "ambitious", "patient", "reckless", "gentle", "exacting", "bitter"]

ORIGINS = ["sleeper", "waker", "survivor", "one of the seven", "colony-born"]


@dataclass
class Person:
    """Someone the Mind knows by name. Act 1's notables wake up as these."""

    name: str
    origin: str
    born: int                      # colony year; negative means before landing
    role: str
    traits: list[str] = field(default_factory=list)
    stance: int = 0                # -2 hostile .. +2 devoted, toward the Mind
    axes: dict[str, int] = field(default_factory=dict)
    died: int | None = None
    influence: int = 1             # how hard they drag the colony's axes

    @property
    def alive(self) -> bool:
        return self.died is None

    def age(self, year: int) -> int:
        return max(0, (self.died if self.died is not None else year) - self.born)

    def describe(self, year: int) -> str:
        stance = {-2: "hostile", -1: "doubting", 0: "indifferent",
                  1: "loyal", 2: "devoted"}[max(-2, min(2, self.stance))]
        traits = ", ".join(self.traits) if self.traits else "unremarkable"
        return (f"{self.name}, {self.age(year)}, {self.role} "
                f"({self.origin}; {traits}; {stance})")

    def to_dict(self) -> dict:
        return {"name": self.name, "origin": self.origin, "born": self.born,
                "died": self.died, "role": self.role, "traits": self.traits,
                "stance": self.stance, "axes": self.axes}


@dataclass
class ColonyState:
    name: str = "the colony"
    year: int = 0
    span: int = 1                  # years this tick covers
    population: int = 0
    stats: dict[str, float] = field(default_factory=dict)
    deference: float = 85.0
    axes: dict[str, float] = field(default_factory=dict)
    people: list[Person] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    fired: set[str] = field(default_factory=set)
    queue: list[list] = field(default_factory=list)
    recent: dict[str, int] = field(default_factory=dict)
    warned: dict[str, float] = field(default_factory=dict)
    chronicle: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    outcome: str | None = None
    outcome_reason: str = ""
    ship_role: str = "the landing site"
    hostility: float = 0.5         # 1 - habitability; permanent planet pressure
    planet: dict = field(default_factory=dict)
    arrival: dict = field(default_factory=dict)   # the Act 1 handoff, for the prologue
    peak_population: int = 0
    thaw_losses: int = 0

    # -- reading --------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.outcome is None

    def say(self, stat: str) -> str:
        """Colony numbers come to the Mind through the colony's willingness to
        report them, so deference is the precision driver here."""
        return readout.stat(self.stats[stat], self.deference)

    def say_population(self) -> str:
        return readout.count(self.population, self.deference)

    def living(self) -> list[Person]:
        return [p for p in self.people if p.alive]

    def axis_label(self, axis: str) -> str:
        low, high = AXES[axis]
        value = self.axes[axis]
        if abs(value) < 15:
            return f"neither {low.lower()} nor {high.lower()}"
        pole = high if value > 0 else low
        strength = "decisively" if abs(value) > 60 else (
            "clearly" if abs(value) > 35 else "mildly")
        return f"{strength} {pole.lower()}"

    def dominant_axes(self, n: int = 2) -> list[tuple[str, str, float]]:
        """The axes furthest from zero: what this colony is most strongly about."""
        ranked = sorted(self.axes.items(), key=lambda kv: -abs(kv[1]))
        out = []
        for axis, value in ranked[:n]:
            if abs(value) < 15:
                continue
            low, high = AXES[axis]
            out.append((axis, high if value > 0 else low, value))
        return out

    # -- writing --------------------------------------------------------------

    def adjust(self, stat: str, delta: float) -> float:
        before = self.stats[stat]
        self.stats[stat] = max(0.0, min(100.0, before + delta))
        return self.stats[stat] - before

    def move_axis(self, axis: str, delta: float) -> float:
        before = self.axes[axis]
        self.axes[axis] = max(-100.0, min(100.0, before + delta))
        return self.axes[axis] - before

    def defer(self, delta: float) -> float:
        before = self.deference
        self.deference = max(0.0, min(100.0, before + delta))
        return self.deference - before

    def note(self, line: str) -> None:
        self.log.append(line)

    def schedule(self, event_id: str, in_ticks: int) -> None:
        self.queue.append([len(self.chronicle) + max(1, int(in_ticks)), event_id])

    def due_event(self) -> str | None:
        for entry in list(self.queue):
            if entry[0] <= len(self.chronicle):
                self.queue.remove(entry)
                return entry[1]
        return None

    def end(self, outcome: str, reason: str) -> None:
        if self.running:
            self.outcome = outcome
            self.outcome_reason = reason

    # -- the clock (Q8: ticks widen as the colony steadies) -------------------

    def stability(self) -> float:
        """0..1. Drives how far the Mind lets the clock run between decisions."""
        core = (self.stats["food"] + self.stats["health"] + self.stats["cohesion"]) / 300
        crowding = min(1.0, self.population / max(1, self.capacity()))
        return max(0.0, min(1.0, core * (1.0 - 0.35 * crowding)))

    def next_span(self) -> int:
        s = self.stability()
        for threshold, years in ((0.46, 10), (0.34, 5), (0.23, 2)):
            if s >= threshold:
                return years
        return 1

    # -- population (Q24: logistic, ceilinged by land and tools) --------------

    def capacity(self) -> int:
        land = 0.45 + 0.55 * (self.stats["food"] / 100)
        tools = 0.45 + 0.55 * (self.stats["industry"] / 100)
        return int(BASE_CAPACITY * land * tools * (1.0 - 0.55 * self.hostility))

    def grow(self, years: int) -> int:
        """Logistic growth over `years`. Returns the change in headcount."""
        before = self.population
        for _ in range(years):
            cap = max(1, self.capacity())
            food = self.stats["food"] / 100
            health = self.stats["health"] / 100

            if self.stats["food"] < 25:
                # Famine is a decline, not a logistic term: crowding must not
                # flip its sign into growth.
                rate = -0.06 * (1 - self.stats["food"] / 25)
            else:
                headroom = 1 - self.population / cap
                rate = 0.022 * (0.35 + 0.65 * food) * (0.35 + 0.65 * health) * headroom
                rate = max(-0.05, rate)      # overshoot starves back, slowly
            self.population = max(0, min(int(cap * 1.4),
                                         int(self.population * (1 + rate))))
        self.peak_population = max(self.peak_population, self.population)
        return self.population - before

    # -- people ---------------------------------------------------------------

    def person_named(self, rng: random.Random, role: str | None = None) -> Person | None:
        pool = [p for p in self.living() if role is None or p.role == role]
        return rng.choice(pool) if pool else None

    def kill_person(self, person: Person) -> None:
        person.died = self.year

    def age_cast(self, rng: random.Random) -> list[str]:
        """Time passes: people die of it, and new ones take their places."""
        lines = []
        for person in self.living():
            age = person.age(self.year)
            odds = 0.0 if age < 55 else min(0.95, (age - 55) / 35)
            odds *= 1.4 - 0.4 * (self.stats["health"] / 100)
            if rng.random() < odds:
                self.kill_person(person)
                lines.append(f"{person.name} dies at {age}, "
                             f"{'a' if person.role[0] not in 'aeiou' else 'an'} "
                             f"{person.role} to the end.")
        while len(self.living()) < 4 and self.population > 0:
            lines.append(self._raise_someone(rng))
        return lines

    def _raise_someone(self, rng: random.Random) -> str:
        """A new name steps forward, leaning the way the colony already leans."""
        person = Person(
            name=f"{rng.choice(K.COLONIST_FIRST)} {rng.choice(K.COLONIST_LAST)}",
            origin="colony-born" if self.year > 25 else "sleeper",
            born=self.year - rng.randint(22, 38),
            role=rng.choice(ROLES),
            traits=rng.sample(TRAITS, 2),
            stance=self._inherited_stance(rng),
            axes={a: int(max(-100, min(100, rng.gauss(self.axes[a], 25))))
                  for a in AXES},
            influence=rng.randint(1, 3),
        )
        self.people.append(person)
        return (f"{person.name} takes up work as {person.role}, "
                f"{person.traits[0]} and {person.traits[1]}.")

    def _inherited_stance(self, rng: random.Random) -> int:
        """Children of a deferent colony tend to revere the Mind; children of a
        free one are mostly indifferent to it."""
        lean = (self.deference - 50) / 30
        return max(-2, min(2, round(rng.gauss(lean, 1.0))))

    # -- handoff --------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "colony": self.name,
            "year": self.year,
            "outcome": self.outcome,
            "outcome_reason": self.outcome_reason,
            "population": self.population,
            "peak_population": self.peak_population,
            "stats": {k: round(v, 2) for k, v in self.stats.items()},
            "deference": round(self.deference, 2),
            "axes": {k: round(v, 1) for k, v in self.axes.items()},
            "ship_role": self.ship_role,
            "flags": sorted(self.flags),
            "people": [p.to_dict() for p in self.people],
            "chronicle": self.chronicle,
            "arrival": self.arrival,
        }


BASE_CAPACITY = 42_000

# --- founding ----------------------------------------------------------------

# Act 1 flags give the tabula rasa its first scratch (Q16).
FLAG_AXIS_NUDGES = {
    "honored_patrons": {"status": -20},
    "equalized_banks": {"status": +20, "society": -10},
    "flagged_patrons": {"power": +10},
    "took_survivors": {"society": -15},
    "took_children": {"society": -10, "status": +10},
    "supplied_survivors": {"society": -10},
    "ignored_distress": {"society": +15},
    "killed_sample": {"nature": +20},
    "spared_rogue_life": {"nature": -20},
    "alien_sample": {"nature": +10, "belief": -10},
    "kept_dream": {"belief": +15},
    "dream_merged": {"belief": +20},
    "deleted_dream": {"belief": -15},
    "dream_archived": {"belief": +5, "status": +5},
    "kept_mandate": {"power": -15},
    "broke_mandate": {"power": +15},
    "read_derelict_logs": {"belief": +10},
    "left_derelict": {"nature": -5},
    "kept_vigil": {"belief": +10, "society": -5},
    "closed_vigil": {"belief": -10},
    "waker_stayed": {"power": +10, "society": -10},
    "waker_returned": {"power": -5},
    "survivors_charter": {"power": +15, "status": +10},
    "triaged_culture": {"belief": -10, "status": -5},
    "heard_earth": {"belief": 5},
    "sealed_earth": {"belief": -5},
    "let_earth_go": {"nature": -5},
    "spoke_sister": {"society": -5},
}

FLAG_COHESION = {
    "equalized_banks": +8, "survivors_charter": +8, "took_survivors": +5,
    "waker_stayed": +5, "honored_patrons": -8, "cooked_the_pods": -10,
    "killed_waker": -6, "ignored_distress": -5, "bank_c_lost": -4,
}


def found(arrival: dict, rng: random.Random) -> ColonyState:
    """Turn an Act 1 arrival into a colony on its first day (Q15)."""
    ship = arrival["stats"]
    flags = set(arrival.get("flags", []))
    planet = arrival.get("planet") or {}
    hostility = 1.0 - float(planet.get("habitability", 0.4))

    cohesion = 50.0 + sum(v for f, v in FLAG_COHESION.items() if f in flags)
    state = ColonyState(
        stats={
            "food": ship["seed_vault"],
            "industry": ship["fabricators"],
            "health": ship["medical"],
            "knowledge": ship["archive"],
            "cohesion": max(5.0, min(95.0, cohesion)),
        },
        deference=85.0,
        axes={axis: 0.0 for axis in AXES},
        hostility=hostility,
        planet=planet,
        arrival=arrival,
        flags={f"voyage:{f}" for f in flags},
    )

    for flag in flags:
        for axis, delta in FLAG_AXIS_NUDGES.get(flag, {}).items():
            state.move_axis(axis, delta)

    # The thaw. Shelter, infirmary and the world itself decide how many of the
    # sleepers never open their eyes (Q15).
    landed = int(arrival.get("colonists_alive", 0))
    exposure = (1.0 - ship["habitat"] / 100) * 0.5 + (1.0 - ship["medical"] / 100) * 0.3
    toll = max(0.0, min(0.6, exposure * (0.4 + 1.2 * hostility)))
    lost = int(landed * toll)
    state.population = max(0, landed - lost)
    state.peak_population = state.population
    state.thaw_losses = lost

    _wake_the_named(state, arrival, rng)
    return state


def _wake_the_named(state: ColonyState, arrival: dict, rng: random.Random) -> None:
    """Act 1's notables wake up as people; its mourned stay dead and named."""
    mourned = set(arrival.get("mourned", []))
    flags = set(arrival.get("flags", []))

    for name in arrival.get("notables", [])[:6]:
        if name in mourned:
            continue
        state.people.append(Person(
            name=name, origin="sleeper", born=-rng.randint(28, 52),
            role=rng.choice(ROLES), traits=rng.sample(TRAITS, 2),
            stance=1 if state.deference > 70 else 0,
            axes={a: int(rng.gauss(state.axes[a], 20)) for a in AXES},
            influence=rng.randint(1, 2),
        ))

    if "waker_stayed" in flags or "waker_crew" in flags:
        state.people.append(Person(
            name=f"{rng.choice(K.COLONIST_FIRST)} {rng.choice(K.COLONIST_LAST)}",
            origin="waker", born=-47, role="farmer",
            traits=["patient", "exacting"], stance=2,
            axes={a: int(rng.gauss(state.axes[a], 15)) for a in AXES},
            influence=3))
        state.flags.add("the_waker_lives")

    if "took_survivors" in flags or "took_children" in flags:
        state.people.append(Person(
            name=f"{rng.choice(K.COLONIST_FIRST)} {rng.choice(K.COLONIST_LAST)}",
            origin="one of the seven" if "took_children" in flags else "survivor",
            born=-rng.randint(12, 40), role="speaker",
            traits=["stubborn", "sceptical"], stance=-1,
            axes={a: int(rng.gauss(state.axes[a], 30)) for a in AXES},
            influence=3))
        state.flags.add("survivors_among_us")

    while len(state.living()) < 4:
        state._raise_someone(rng)
    for person in state.people:
        person.born = min(person.born, 0)


def load_arrival(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def planet_pressure(state: ColonyState) -> str:
    """One line on what this world does to a colony, forever."""
    p = state.planet
    if not p:
        return "A world I never properly surveyed."
    verdict = p.get("verdict", "unknown")
    return (f"{p.get('name', 'this world')}, judged {verdict}: "
            + ", ".join(f"{k.lower()} {v}" for k, v in
                        planets.Planet(**{k: v for k, v in p.items()
                                          if k in planets.Planet.__annotations__}
                                       ).dossier()[:3]))
