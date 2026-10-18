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
#
# With the directive phase gone, a playstyle is nothing but a way of ranking
# the four options on the table. Deference is what the two ends of Q7 disagree
# about, so these sort on it and break ties on whatever helps the worst stat.

GRADES = ("crit_success", "success", "failure", "crit_failure")


def _expected(choice: dict, key: str, stat: str | None = None) -> float:
    """What a choice is worth on average across its outcomes."""
    outcomes = [choice[g] for g in GRADES if g in choice] or [choice]
    total = 0.0
    for outcome in outcomes:
        total += (float(outcome.get("defer", 0)) if key == "defer"
                  else float(outcome.get("effects", {}).get(stat, 0)))
    return total / len(outcomes)


def _rank(game: century.Century, sign: int) -> int:
    s = game.state
    worst = min(C.COLONY_STATS, key=lambda k: s.stats[k])
    choices = game.choices()
    # A colony about to die of one stat takes the option that feeds it, whoever
    # is holding the reins.
    if s.stats[worst] < 25:
        best = max(range(len(choices)),
                   key=lambda i: _expected(choices[i], "stat", worst))
        if _expected(choices[best], "stat", worst) > 0:
            return best
    if sign < 0 and s.deference < 35:
        # A steward keeps a voice. It does not hand itself out of existence.
        return min(range(len(choices)),
                   key=lambda i: abs(_expected(choices[i], "defer")))
    return max(range(len(choices)),
               key=lambda i: sign * _expected(choices[i], "defer"))


def autocrat(game: century.Century) -> int:
    """Takes every decision it can. The colony never learns to decide."""
    return _rank(game, +1)


def steward(game: century.Century) -> int:
    """Hands decisions back wherever handing them back is on offer."""
    return _rank(game, -1)


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
        n = len(game.choices())
        if script:
            pick = script.pop(0) % n
        elif policy:
            pick = policy(game) % n
        else:
            pick = picker.randrange(n)
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
