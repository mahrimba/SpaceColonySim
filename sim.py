"""Headless runner: determinism harness and balance tooling.

  python sim.py --runs 500            # arrival rate under competent play
  python sim.py --seed 42 --verbose   # replay one run move by move
"""

from __future__ import annotations

import argparse
import random
from collections import Counter

import constants as K
import deck
from resolve import DONE, EVENT, MAINTENANCE, Game

MAX_LEGS = 60  # a run must terminate; tripping this is a bug, not a result


# -- policies -----------------------------------------------------------------

def competent_policy(game: Game) -> dict:
    """A reasonable player: patch the worst system, keep your mind, settle
    before the tanks run dry. The baseline the 75% arrival target is measured
    against.
    """
    s = game.state
    richest = max(K.HOLDS, key=lambda h: s.stats[h])
    power = s.stats["power"]
    can_repair = power > K.REPAIR_POWER_COST + 6

    # Zero power ends the run outright, and power buys every other repair, so
    # a competent player defends it before anything else.
    if power < 30:
        if can_repair and s.stats["fabricators"] > 40:
            return {"action": "repair", "target": "power"}
        return {"action": "cannibalize", "hold": richest, "target": "power"}

    if s.cognition < 55 and power > K.DIAGNOSTIC_POWER_COST + 10:
        return {"action": "diagnostics"}

    worst = min(["hull", "life_support"], key=lambda st: s.stats[st])
    if s.stats[worst] < 55:
        if not can_repair:
            return {"action": "cannibalize", "hold": richest, "target": worst}
        return {"action": "repair", "target": worst}

    if not s.candidates:
        return {"action": "survey"}
    return {"action": "hold"}


def should_commit(game: Game) -> bool:
    s = game.state
    if not game.can_commit():
        return False
    best = max(s.candidates, key=lambda p: p.habitability())
    legs_left = (s.stats["fuel"] - K.DECEL_FUEL_COST) / K.FUEL_PER_LEG
    if legs_left <= 1:
        return True                      # settle now or drift
    # A patient player holds out for a garden while the tanks allow it, and
    # lowers their standards as the fuel goes. 0.70 with range to burn, 0.30
    # when nearly dry.
    bar = 0.30 + 0.40 * min(1.0, legs_left / 15.0)
    return best.habitability() >= bar


# -- the loop -----------------------------------------------------------------

def play(seed: int, profile: str = "survey", events=None,
         choices: list[int] | None = None, verbose: bool = False) -> Game:
    """Run one voyage to its end. `choices` replays fixed event picks."""
    game = Game(profile=profile, seed=seed, events=events)
    picker = random.Random(seed ^ 0x5EED)  # choices are policy, not world
    script = list(choices or [])

    while game.phase != DONE:
        if game.state.leg > MAX_LEGS:
            raise AssertionError(f"run did not terminate (seed {seed})")

        if game.phase == MAINTENANCE:
            if should_commit(game):
                best = max(game.state.candidates, key=lambda p: p.habitability())
                game.commit(best)
                break
            game.do_maintenance(**competent_policy(game))
        elif game.phase == EVENT:
            n = len(game.choices())
            pick = script.pop(0) % n if script else picker.randrange(n)
            game.resolve_choice(pick)

    if verbose:
        for line in game.state.log:
            print(line)
        print()
        for line in game.report():
            print(line)
    return game


# -- balance ------------------------------------------------------------------

def survey_runs(n: int, profile: str) -> None:
    events = deck.load()
    outcomes: Counter[str] = Counter()
    legs: list[int] = []
    alive: list[int] = []
    habit: list[float] = []
    for seed in range(n):
        g = play(seed, profile=profile, events=events)
        outcomes[g.state.outcome] += 1
        legs.append(g.state.leg)
        if g.state.outcome == "colonized":
            alive.append(g.state.colonists_alive)
            habit.append(g.state.chosen_planet.habitability())

    arrived = outcomes["colonized"] / n
    print(f"profile {profile}: {n} runs")
    for outcome, count in outcomes.most_common():
        print(f"  {outcome:<12} {count/n:6.1%}")
    print(f"  arrival rate  {arrived:6.1%}   (target ~75%)")
    print(f"  median legs   {sorted(legs)[n//2]}")
    if alive:
        print(f"  median alive  {sorted(alive)[len(alive)//2]:,} "
              f"of {K.START_COLONISTS:,}")
        print(f"  median world  habitability {sorted(habit)[len(habit)//2]:.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--profile", default="survey", choices=list(K.PROFILES))
    ap.add_argument("--runs", type=int)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.runs:
        for profile in ([args.profile] if args.seed is not None else K.PROFILES):
            survey_runs(args.runs, profile)
        return
    seed = args.seed if args.seed is not None else random.randrange(1, 2**31)
    play(seed, profile=args.profile, verbose=True)


if __name__ == "__main__":
    main()
