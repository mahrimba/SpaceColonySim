"""Headless runner for Act 2: determinism harness and balance tooling.

    python colony_sim.py --runs 300          # outcome spread over synthetic arrivals
    python colony_sim.py --seed 7 --verbose  # read one century
    python colony_sim.py --from arrival_12.json --verbose

Synthetic arrivals matter: balancing the century against real voyages alone
would mean playing Act 1 three hundred times, and would couple Act 2's tuning
to Act 1's.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter

import century
import colony as C
import constants as K
import deck
import planets
import sim


# -- arrivals -----------------------------------------------------------------

def synthetic_arrival(seed: int) -> dict:
    """An Act 1 handoff drawn from the spread real voyages actually produce."""
    rng = random.Random(seed)
    planet = planets.generate(rng, set(), 100.0)
    # Voyages that reach a world arrive worn, not wrecked.
    stats = {name: round(min(100.0, max(5.0, rng.gauss(58, 22))), 1)
             for name in K.STATS}
    stats["fuel"] = round(rng.uniform(20, 60), 1)
    flags = rng.sample(sorted(C.FLAG_AXIS_NUDGES), rng.randint(0, 5))
    alive = rng.randint(5_000, 13_500)
    return {
        "profile": "synthetic",
        "ship": "synthetic hull",
        "legs_flown": rng.randint(9, 22),
        "outcome": "colonized",
        "stats": stats,
        "colonists_alive": alive,
        "colonists_lost": rng.randint(0, 2_000),
        "flags": flags,
        "notables": [f"{rng.choice(K.COLONIST_FIRST)} {rng.choice(K.COLONIST_LAST)}"
                     for _ in range(rng.randint(2, 6))],
        "mourned": [],
        "planet": planet.to_dict(),
        "seed": seed,
    }


def arrival_from_voyage(seed: int) -> dict | None:
    game = sim.play(seed, events=deck.load())
    return game.state.to_dict() if game.state.outcome == "colonized" else None


# -- policy -------------------------------------------------------------------

FIXES = {"food": "fields", "industry": "build", "health": "tend",
         "knowledge": "teach", "cohesion": "hold"}


def autocrat(game: century.Century) -> str:
    """Keeps hold of everything. Patches the worst stat, never stands aside."""
    s = game.state
    options = {d["id"] for d in game.directive_options()}
    worst, value = min(((k, s.stats[k]) for k in C.COLONY_STATS), key=lambda kv: kv[1])
    if value < 60 and FIXES[worst] in options:
        return FIXES[worst]
    return "hold" if "hold" in options else "record"


def steward(game: century.Century) -> str:
    """Patches real crises and otherwise hands decisions back, aiming for a
    colony that can run itself. The baseline the targets are measured against."""
    s = game.state
    options = {d["id"] for d in game.directive_options()}
    worst, value = min(((k, s.stats[k]) for k in C.COLONY_STATS), key=lambda kv: kv[1])
    if value < 40 and FIXES[worst] in options:
        return FIXES[worst]
    if s.deference > 35 and "let_them" in options:
        return "let_them"
    return "record" if "record" in options else FIXES[worst]


POLICIES = {"steward": steward, "autocrat": autocrat}


def play(arrival: dict, seed: int = 0, events=None, verbose: bool = False,
         choices: list[int] | None = None, policy=None) -> century.Century:
    game = century.Century(arrival, seed=seed, events=events)
    picker = random.Random(seed ^ 0xA2)
    script = list(choices or [])

    guard = 0
    while game.phase != century.DONE:
        guard += 1
        assert guard < 400, "century did not terminate"
        if game.phase == century.DIRECTIVE:
            game.do_directive((policy or steward)(game))
        elif game.phase == century.EVENT:
            n = len(game.choices())
            pick = script.pop(0) % n if script else picker.randrange(n)
            game.resolve_choice(pick)

    if verbose:
        print("\n".join(game.state.log))
        print()
        print("\n".join(game.document()))
    return game


# -- balance ------------------------------------------------------------------

def survey(n: int, use_voyages: bool = False, policy_name: str = "steward") -> None:
    events = century.load("colony.json")
    outcomes: Counter[str] = Counter()
    pops, years, defer, ticks = [], [], [], []
    axes_touched: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    skipped = 0

    for seed in range(n):
        arrival = arrival_from_voyage(seed) if use_voyages else synthetic_arrival(seed)
        if arrival is None:
            skipped += 1
            continue
        game = play(arrival, seed=seed, events=events,
                    policy=POLICIES[policy_name])
        s = game.state
        outcomes[s.outcome] += 1
        pops.append(s.population)
        years.append(s.year)
        defer.append(s.deference)
        ticks.append(len(s.chronicle))
        roles[s.ship_role] += 1
        for axis, value in s.axes.items():
            if abs(value) >= 25:
                axes_touched[axis] += 1

    total = sum(outcomes.values())
    print(f"[{policy_name}] {total} centuries" + (f" ({skipped} voyages never arrived)" if skipped else ""))
    for outcome, count in outcomes.most_common():
        print(f"  {outcome:<12} {count/total:6.1%}")
    print(f"  median population {sorted(pops)[len(pops)//2]:,}")
    print(f"  median deference  {sorted(defer)[len(defer)//2]:.0f}")
    print(f"  median ticks      {sorted(ticks)[len(ticks)//2]}")
    print(f"  ship became       {dict(roles.most_common(4))}")
    print(f"  axes moved past 25: "
          f"{ {a: f'{c/total:.0%}' for a, c in axes_touched.most_common()} }")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--runs", type=int)
    ap.add_argument("--from", dest="path")
    ap.add_argument("--voyages", action="store_true",
                    help="use real Act 1 runs instead of synthetic arrivals")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--policy", default="both", choices=["both", *POLICIES])
    args = ap.parse_args()

    if args.runs:
        for name in (POLICIES if args.policy == "both" else [args.policy]):
            survey(args.runs, use_voyages=args.voyages, policy_name=name)
            print()
        return
    seed = args.seed if args.seed is not None else random.randrange(1, 2**31)
    if args.path:
        with open(args.path, encoding="utf-8") as fh:
            arrival = json.load(fh)
    else:
        arrival = synthetic_arrival(seed)
    play(arrival, seed=seed, verbose=args.verbose or True)


if __name__ == "__main__":
    main()
