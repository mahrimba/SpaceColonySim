"""Procedural worlds.

Axes are rolled with correlation, not independently (Q30): thin air lets the
surface swing to extremes, heavy gravity holds a thick envelope, complex life
needs liquid water. Habitability is *derived* from the axes and never shown as
a number — the player reads the world and judges it.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

import readout

BIOSPHERES = ["none", "microbial", "complex", "hostile"]

GRAVITY_WORDS = ["feather", "light", "earthlike", "heavy", "crushing"]
PRESSURE_WORDS = ["vacuum", "thin", "breathable density", "thick", "crushing"]
TEMP_WORDS = ["frozen", "cold", "temperate", "hot", "furnace"]
WATER_WORDS = ["bone dry", "traces", "seas", "ocean world"]
RAD_WORDS = ["shielded", "tolerable", "harsh", "lethal"]


@dataclass
class Planet:
    name: str
    gravity: float          # g
    pressure: float         # atm
    temperature: float      # degrees C, mean surface
    water: float            # 0-1 surface fraction
    biosphere: str
    radiation: float        # 0-10 arbitrary dose index
    surveyed_at_cognition: float = 100.0
    notes: list[str] = field(default_factory=list)

    # -- derived, never displayed as a number ---------------------------------

    def habitability(self) -> float:
        """0..1. Used by Act 2 and by balance tooling, never shown to the player.

        Multiplicative, not a weighted sum: a world that fails on any one axis
        is not half-habitable, it is lethal. The square root keeps the usable
        range legible without forgiving a failed axis.
        """
        def band(value, ideal, tolerance):
            return max(0.0, 1.0 - abs(value - ideal) / tolerance)

        product = (
            band(self.gravity, 1.0, 0.85)
            * band(self.pressure, 1.0, 1.4)
            * band(self.temperature, 14.0, 55.0)
            * min(1.0, self.water * 4.0)
            * max(0.0, 1.0 - self.radiation / 7.0)
            * {"none": 0.75, "microbial": 1.0, "complex": 0.9, "hostile": 0.55}[
                self.biosphere]
        )
        return round(min(1.0, product) ** 0.5, 3)

    def verdict(self) -> str:
        """Coarse word for the arrival report only."""
        h = self.habitability()
        for threshold, word in (
            (0.15, "lethal"), (0.30, "marginal"), (0.45, "survivable"),
            (0.60, "promising"), (1.01, "a garden"),
        ):
            if h < threshold:
                return word
        return "a garden"

    # -- what the ship can actually say about it ------------------------------

    def dossier(self) -> list[tuple[str, str]]:
        c = self.surveyed_at_cognition
        return [
            ("Gravity", readout.measure(self.gravity, c, " g", 0.1, 3.0, GRAVITY_WORDS)),
            ("Pressure", readout.measure(self.pressure, c, " atm", 0.0, 6.0, PRESSURE_WORDS)),
            ("Mean surface", readout.measure(self.temperature, c, " C", -120, 160,
                                             TEMP_WORDS, decimals=0)),
            ("Hydrosphere", readout.measure(self.water, c, "", 0.0, 1.0, WATER_WORDS)),
            ("Radiation", readout.measure(self.radiation, c, "", 0.0, 10.0, RAD_WORDS)),
            ("Biosphere", self._biosphere_readout()),
        ]

    def _biosphere_readout(self) -> str:
        t = readout.tier(self.surveyed_at_cognition)
        if t == readout.PRECISE:
            return self.biosphere
        if t == readout.APPROX:
            return {"none": "sterile", "microbial": "signs of life",
                    "complex": "signs of life", "hostile": "signs of life"}[self.biosphere]
        return "unresolved"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["habitability"] = self.habitability()
        d["verdict"] = self.verdict()
        return d


def table(worlds: list["Planet"], per_table: int = 3) -> list[str]:
    """Render worlds as a transposed table: one column each, one row per axis.

    Transposed because a row-per-world table is far too wide for a terminal
    column once the readings go qualitative ('breathable density' is 18
    characters). With one axis per row it fits even at the vaguest tier.
    Each column reports at the cognition the survey was taken at.
    """
    if not worlds:
        return []
    rows: list[str] = []
    for start in range(0, len(worlds), per_table):
        group = worlds[start:start + per_table]
        width = max(22, max(len(w.name) for w in group) + 2)
        # Labelled rather than indented: a line that starts with spaces loses
        # them to Textual's markup, which breaks the column alignment.
        rows.append(f"{'World':<15}" + "".join(f"{w.name:<{width}}" for w in group))
        for i, (label, _) in enumerate(group[0].dossier()):
            cells = "".join(f"{w.dossier()[i][1]:<{width}}" for w in group)
            rows.append(f"{label:<15}{cells}".rstrip())
    return rows


def _name(rng: random.Random) -> str:
    import constants
    a, b = constants.SYSTEM_NAME_PARTS
    return f"{rng.choice(a)} {rng.choice(b)} {rng.randint(2, 9)}{rng.choice('bcdef')}"


def generate(rng: random.Random, tags: set[str], cognition: float) -> Planet:
    """Roll one candidate world, biased by the system it sits in."""
    gravity = round(max(0.08, rng.gauss(1.0, 0.45)), 2)

    # Heavy worlds hold their air; light ones leak it.
    pressure_mean = max(0.0, gravity * 1.1 - 0.25)
    pressure = round(max(0.0, rng.gauss(pressure_mean, 0.6)), 2)

    # Thin air means no thermal blanket: swings wide from the stellar baseline.
    baseline = rng.gauss(10, 45)
    if "red_dwarf" in tags:
        baseline -= 25
    if "binary_star" in tags:
        baseline += 30
    if "rogue_planet" in tags:
        baseline -= 90
    swing = 1.9 if pressure < 0.4 else (1.0 if pressure < 2.0 else 0.55)
    temperature = round(baseline * swing + (12 if pressure > 3 else 0), 1)

    # Liquid water needs a temperate band and real pressure.
    liquid_ok = -5 < temperature < 95 and pressure > 0.25
    water = round(abs(rng.gauss(0.35, 0.25)), 2) if liquid_ok else round(
        abs(rng.gauss(0.0, 0.04)), 2)
    water = min(1.0, water)

    radiation = round(max(0.0, rng.gauss(2.5, 1.6)), 1)
    if "pulsar" in tags:
        radiation += 4.5
    if "nebula" in tags:
        radiation += 1.2
    if pressure > 1.5:
        radiation = max(0.0, radiation - 1.0)  # the atmosphere is the shield
    radiation = round(min(10.0, radiation), 1)

    # Complex life is gated on water; hostile biospheres like warm and wet too.
    if water < 0.05 or radiation > 7.5:
        biosphere = "none"
    else:
        biosphere = rng.choices(
            BIOSPHERES,
            weights=[30, 40, 18 if water > 0.2 else 4, 12 if water > 0.15 else 3],
        )[0]

    return Planet(
        name=_name(rng),
        gravity=gravity,
        pressure=pressure,
        temperature=temperature,
        water=water,
        biosphere=biosphere,
        radiation=radiation,
        surveyed_at_cognition=cognition,
    )
