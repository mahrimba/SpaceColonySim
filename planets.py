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
    modifiers: list[str] = field(default_factory=list)

    # -- derived, never displayed as a number ---------------------------------

    def habitability(self) -> float:
        """0..1. Used by Act 2 and by balance tooling, never shown to the player.

        Multiplicative, not a weighted sum: a world that fails on any one axis
        is not half-habitable, it is lethal. The square root keeps the usable
        range legible without forgiving a failed axis.
        """
        product = 1.0
        for fit in self.fits().values():
            product *= fit
        for mod in self.modifiers:
            product *= MODIFIERS[mod].habitability
        return round(min(1.0, product) ** 0.5, 3)

    def fits(self) -> dict[str, float]:
        """How close each reading is to what people can live with, 0..1 (1 is
        Earth's), keyed by dossier label. The terms of habitability()."""
        def band(value, ideal, tolerance):
            return max(0.0, 1.0 - abs(value - ideal) / tolerance)

        return {
            "Gravity": band(self.gravity, 1.0, 0.85),
            "Pressure": band(self.pressure, 1.0, 1.4),
            "Mean surface": band(self.temperature, 14.0, 55.0),
            "Hydrosphere": min(1.0, self.water * 4.0),
            "Radiation": max(0.0, 1.0 - self.radiation / 7.0),
            "Biosphere": {"none": 0.75, "microbial": 1.0, "complex": 0.9,
                          "hostile": 0.55}[self.biosphere],
        }

    def toned_dossier(self) -> list[tuple[str, str, int]]:
        """The dossier with a colour per reading: green near Earth's, yellow,
        then red as it strays either way. Features colour one by one, by
        whether each helps or hurts. A survey too vague for numbers is too
        vague to judge, so it stays uncoloured."""
        judged = readout.tier(self.surveyed_at_cognition) != readout.VAGUE
        fits = self.fits()
        out = []
        for label, value in self.dossier():
            plain = len(value)
            if not judged:
                pass
            elif label in fits:
                fit = fits[label]
                tone = "green" if fit >= 0.8 else ("yellow" if fit >= 0.4 else "red")
                value = f"[{tone}]{value}[/{tone}]"
            elif label == "Features":
                value = ", ".join(_tone_feature(name) for name in value.split(", "))
            out.append((label, value, plain))
        return out

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
            ("Features", self._features_readout()),
        ]

    def _features_readout(self) -> str:
        """Odd worlds read as odd before they read as anything specific: at
        middling precision the rarer features blur into 'anomalous readings'."""
        if not self.modifiers:
            return "none noted"
        t = readout.tier(self.surveyed_at_cognition)
        if t == readout.PRECISE:
            return ", ".join(MODIFIERS[m].name for m in self.modifiers)
        if t == readout.APPROX:
            names = [MODIFIERS[m].name for m in self.modifiers
                     if MODIFIERS[m].weight >= 5]
            if len(names) < len(self.modifiers):
                names.append("anomalous readings")
            return ", ".join(names)
        return "unresolved"

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


def _tone_feature(name: str) -> str:
    mod = next((m for m in MODIFIERS.values() if m.name == name), None)
    if mod is None or mod.habitability == 1.0:
        return name
    tone = "green" if mod.habitability > 1.0 else "red"
    return f"[{tone}]{name}[/{tone}]"


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
        width = max(22, max(len(cell) for w in group
                            for cell in [w.name, *(v for _, v in w.dossier())]) + 2)
        # Labelled rather than indented: a line that starts with spaces loses
        # them to Textual's markup, which breaks the column alignment.
        rows.append(f"{'World':<15}" + "".join(f"{w.name:<{width}}" for w in group))
        # Colour markup takes no room on screen, so pad by the plain length.
        toned = [w.toned_dossier() for w in group]
        for i, (label, _) in enumerate(group[0].dossier()):
            cells = "".join(d[i][1] + " " * (width - d[i][2]) for d in toned)
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

    planet = Planet(
        name=_name(rng),
        gravity=gravity,
        pressure=pressure,
        temperature=temperature,
        water=water,
        biosphere=biosphere,
        radiation=radiation,
        surveyed_at_cognition=cognition,
    )
    planet.modifiers = roll_modifiers(rng, planet, tags)
    if "strong_magnetic" in planet.modifiers:
        planet.radiation = round(max(0.0, planet.radiation - 1.5), 1)
    if "weak_magnetic" in planet.modifiers:
        planet.radiation = round(min(10.0, planet.radiation + 1.0), 1)
    return planet


# --- planet modifiers ---------------------------------------------------------
#
# After Stellaris's planet modifiers, cut to the ones that mean something to a
# colony with no economy but food, tools, health, knowledge and each other.
# Weights set rarity (10 common, 4 uncommon, 1.5 rare, 0.4 very rare; doubled
# for the ones that need complex life, which is itself uncommon) and are
# multiplied by the world's conditions, Stellaris-style: geothermal likes
# heavy worlds, fauna needs a biosphere, and so on. `habitability` multiplies
# the world's habitability product, so a modifier is felt in both acts.

@dataclass(frozen=True)
class Modifier:
    name: str
    weight: float
    habitability: float = 1.0
    group: str = "random"           # random (up to two), flora or minerals (one each)


MODIFIERS = {
    # random: common
    "tidally_locked": Modifier("Tidally locked", 10, 0.90),
    "storms": Modifier("Hazardous weather", 10, 0.92),
    "weak_magnetic": Modifier("Weak magnetic field", 8, 0.95),
    "strong_magnetic": Modifier("Strong magnetic field", 8, 1.0),
    "geothermal": Modifier("Abundant geothermal activity", 8, 1.0),
    "tectonics": Modifier("Unstable tectonics", 8, 0.90),
    "asteroid_impacts": Modifier("Asteroid impacts", 6, 0.95),
    "hostile_fauna": Modifier("Hostile fauna", 16, 0.90),
    # random: uncommon
    "docile_fauna": Modifier("Docile fauna", 8, 1.10),
    "natural_beauty": Modifier("Natural beauty", 4, 1.0),
    "subterranean": Modifier("Subterranean wildlife", 4, 1.0),
    "aphrodisiac": Modifier("Atmospheric aphrodisiac", 3, 1.05),
    "hallucinogen": Modifier("Atmospheric hallucinogen", 3, 1.0),
    # random: rare and very rare
    "hyper_ecosystem": Modifier("Hyper ecosystem", 3, 1.15),
    "titanic_life": Modifier("Titanic life", 3, 1.0),
    "ship_graveyard": Modifier("Ship graveyard", 1.0, 1.0),
    "terraformed": Modifier("Previously terraformed", 0.4, 1.20),
    # flora
    "lush": Modifier("Lush", 10, 1.10, "flora"),
    "bleak": Modifier("Bleak", 7, 0.92, "flora"),
    "rich_microflora": Modifier("Rich microflora", 5, 1.05, "flora"),
    # minerals
    "poor_minerals": Modifier("Poor minerals", 12, 1.0, "minerals"),
    "rich_minerals": Modifier("Rich minerals", 10, 1.0, "minerals"),
    "exceptional_minerals": Modifier("Exceptional minerals", 2, 1.0, "minerals"),
}

# Chance of no modifier at all from each one-of group.
GROUP_NONE = {"flora": 25.0, "minerals": 25.0}
RANDOM_COUNT = ((0, 45), (1, 40), (2, 15))


def _conditions(mod: str, p: Planet, tags: set[str], have: list[str]) -> float:
    """Stellaris-style weight multipliers. Zero means impossible here."""
    heavy, light = p.gravity >= 1.25, p.gravity <= 0.75
    alive = p.biosphere != "none"
    complex_life = p.biosphere in ("complex", "hostile")
    breathable = 0.4 <= p.pressure <= 3.0
    x = 1.0
    if mod == "tidally_locked":
        x *= 3 if "red_dwarf" in tags else 1
    elif mod == "storms":
        x *= 0 if p.pressure < 0.3 else (2 if p.pressure > 1.5 else 1)
    elif mod == "weak_magnetic":
        x *= (2 if light else 1) * (0 if {"strong_magnetic", "geothermal"} & set(have) else 1)
    elif mod == "strong_magnetic":
        x *= (2 if heavy else 1) * (0 if {"weak_magnetic", "geothermal"} & set(have) else 1)
    elif mod == "geothermal":
        x *= (2 if heavy else 1) * (0 if {"weak_magnetic", "strong_magnetic"} & set(have) else 1)
    elif mod == "tectonics":
        x *= 4 if heavy else 1
    elif mod == "asteroid_impacts":
        x *= 2 if "asteroid_belt" in tags else 1
    elif mod in ("hostile_fauna", "docile_fauna", "hyper_ecosystem", "titanic_life"):
        x *= 1 if complex_life else 0
        if mod == "hostile_fauna":
            x *= (2 if heavy else 1) * (0 if {"docile_fauna", "titanic_life"} & set(have) else 1)
        if mod == "docile_fauna":
            x *= (0 if p.biosphere == "hostile" else 1) * (0 if "hostile_fauna" in have else 1)
        if mod == "titanic_life":
            x *= (2 if heavy else 1) * (0 if "hostile_fauna" in have else 1)
    elif mod == "subterranean":
        x *= (2 if light else 1) * (1 if alive else 0)
    elif mod in ("aphrodisiac", "hallucinogen"):
        x *= 1 if (alive and breathable) else 0
    elif mod in ("lush", "rich_microflora"):
        x *= (1 if alive else 0) * (2 if light and mod == "lush" else 1)
    elif mod == "bleak":
        x *= 2 if p.biosphere == "none" else 1
    elif mod == "poor_minerals":
        x *= 4 if light else 1
    elif mod in ("rich_minerals", "exceptional_minerals"):
        x *= 4 if heavy else 1
    return x


def roll_modifiers(rng: random.Random, p: Planet, tags: set[str]) -> list[str]:
    have: list[str] = []
    for group in ("flora", "minerals"):
        pool = {m: d.weight * _conditions(m, p, tags, have)
                for m, d in MODIFIERS.items() if d.group == group}
        pool = {m: w for m, w in pool.items() if w > 0}
        pick = rng.choices([None, *pool], weights=[GROUP_NONE[group], *pool.values()])[0]
        if pick:
            have.append(pick)
    count = rng.choices([n for n, _ in RANDOM_COUNT], weights=[w for _, w in RANDOM_COUNT])[0]
    for _ in range(count):
        pool = {m: d.weight * _conditions(m, p, tags, have)
                for m, d in MODIFIERS.items() if d.group == "random" and m not in have}
        pool = {m: w for m, w in pool.items() if w > 0}
        if not pool:
            break
        have.append(rng.choices(list(pool), weights=list(pool.values()))[0])
    return have
