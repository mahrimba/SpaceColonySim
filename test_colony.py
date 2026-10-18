"""Checks for Act 2. Same contract as test_sim.py: asserts over real runs.

    python test_colony.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import century
import colony as C
import colony_sim as CS
import constants as K
import readout

EVENTS = century.load("colony.json")
ENDINGS = century.load("endings.json")
DOCUMENTS = century.load("documents.json")
FLAVOUR = century.load("colony_flavour.json")

# Endings that stop the century early: the colony died of something.
DEATHS = {"extinct", *century.STAT_COLLAPSE.values()}


def test_a_century_always_terminates_legally() -> None:
    """Every century reaches year 100 or a death, in a state we have words for."""
    legal = {e["id"] for e in ENDINGS}
    for seed in range(120):
        game = CS.play(CS.synthetic_arrival(seed), seed=seed, events=EVENTS)
        s = game.state
        assert game.phase == century.DONE, f"seed {seed} stopped mid-phase"
        assert s.outcome in legal, f"seed {seed}: outcome {s.outcome!r}"
        assert s.outcome_reason, f"seed {seed}: ended without a reason"
        assert s.population >= 0
        assert 0 <= s.deference <= 100
        for stat, value in s.stats.items():
            assert 0.0 <= value <= 100.0, f"seed {seed}: {stat} = {value}"
        for axis, value in s.axes.items():
            assert -100.0 <= value <= 100.0, f"seed {seed}: {axis} = {value}"
        # Only a death stops the clock early. Everything else reaches year 100.
        assert s.outcome in DEATHS or s.year == century.CENTURY, (
            f"seed {seed} ended at year {s.year} as {s.outcome}")
        if s.outcome in century.STAT_COLLAPSE.values():
            stat = next(k for k, v in century.STAT_COLLAPSE.items()
                        if v == s.outcome)
            assert s.stats[stat] <= 0.0, (
                f"seed {seed}: {s.outcome} with {stat} at {s.stats[stat]}")


def test_a_stat_at_zero_ends_it() -> None:
    """Nothing holds a colony up alone: a stat reaching zero is a game over."""
    for stat, expected in century.STAT_COLLAPSE.items():
        game = century.Century(CS.synthetic_arrival(6), seed=6, events=EVENTS)
        game.state.stats[stat] = 0.0
        game._check_end()
        assert game.state.outcome == expected, (
            f"{stat} at zero gave {game.state.outcome!r}")
        assert game.state.outcome_reason, f"{expected} has no verdict"
        assert game.state.year < century.CENTURY, "the century ran on regardless"


def test_determinism() -> None:
    """Same arrival, same seed, same choices: the same century."""
    script = [0, 1, 0, 2, 1, 0, 1, 1, 0, 2, 0, 1]
    for seed in (2, 19, 77):
        arrival = CS.synthetic_arrival(seed)
        a = CS.play(arrival, seed=seed, events=EVENTS, choices=list(script))
        b = CS.play(arrival, seed=seed, events=EVENTS, choices=list(script))
        assert a.state.log == b.state.log, f"seed {seed} diverged"
        assert a.state.to_dict() == b.state.to_dict()


def test_every_ending_is_reachable() -> None:
    """An ending nobody can reach is dead content; a fallback is mandatory."""
    assert any(not e.get("requires") for e in ENDINGS), "no catch-all ending"
    seen = set()
    for seed in range(400):
        for policy in CS.POLICIES.values():
            game = CS.play(CS.synthetic_arrival(seed), seed=seed, events=EVENTS,
                           policy=policy)
            seen.add(game.state.outcome)
        if len(seen) == len(ENDINGS):
            break
    # Every ending a surviving colony can earn must appear. Which specific
    # thing kills a colony depends on what the deck can crater, so the deaths
    # are only required as a group.
    missing = {e["id"] for e in ENDINGS} - seen - DEATHS
    assert not missing, f"unreachable endings: {missing}"
    assert seen & DEATHS, "no colony ever died"


def test_content_is_wired_up() -> None:
    """Every stat, axis, flag and follow-up named in colony.json must exist."""
    ids = {e["id"] for e in EVENTS}
    scheduled: set[str] = set()
    effect_keys = set(C.COLONY_STATS) | {
        "population_lost", "population_lost_frac", "flags", "queue", "name"}

    for event in EVENTS:
        assert event["text"], f"{event['id']}: no text"
        # Every tick is an event now, so every event has to carry a full
        # decision: four ways to answer it.
        assert len(event["choices"]) == 4, (
            f"{event['id']}: {len(event['choices'])} choices, want 4")
        req = event.get("requires", {})
        for stat in req.get("stats", {}):
            assert stat in C.COLONY_STATS, f"{event['id']}: unknown stat {stat}"
        for axis in req.get("axes", {}):
            assert axis in C.AXES, f"{event['id']}: unknown axis {axis}"
        if req.get("role"):
            assert req["role"] in C.ROLES, f"{event['id']}: unknown role"

        for choice in event["choices"]:
            assert choice.get("label"), f"{event['id']}: unlabelled choice"
            check = choice.get("check")
            if check:
                assert check["stat"] in C.COLONY_STATS + ["deference"], (
                    f"{event['id']}: bad check stat {check['stat']}")
                assert K.DC_BAND[0] <= check["dc"] <= K.DC_BAND[1], (
                    f"{event['id']}: DC {check['dc']} outside {K.DC_BAND}")
                assert choice.get("success") and choice.get("failure")
                outcomes = [choice[g] for g in
                            ("crit_success", "success", "failure", "crit_failure")
                            if g in choice]
            else:
                outcomes = [choice]

            for outcome in outcomes:
                for key in outcome.get("effects", {}):
                    assert key in effect_keys, f"{event['id']}: bad effect {key!r}"
                for axis in outcome.get("axes", {}):
                    assert axis in C.AXES, f"{event['id']}: bad axis {axis!r}"
                for target, _ in outcome.get("effects", {}).get("queue", []):
                    scheduled.add(target)
                for target, _ in outcome.get("queue", []):
                    scheduled.add(target)

    assert scheduled <= ids, f"scheduled events that do not exist: {scheduled - ids}"
    for event in EVENTS:
        if event.get("chain_only"):
            assert event["id"] in scheduled, f"{event['id']} is never scheduled"


def test_every_axis_can_actually_move() -> None:
    """An axis with no events behind it is a number that never moves (Q28)."""
    movers: dict[str, int] = {axis: 0 for axis in C.AXES}
    for event in EVENTS:
        for choice in event["choices"]:
            for outcome in [choice] + [choice[g] for g in
                                       ("crit_success", "success", "failure",
                                        "crit_failure") if g in choice]:
                for axis, delta in outcome.get("axes", {}).items():
                    if abs(delta) >= 5:
                        movers[axis] += 1
    for axis, count in movers.items():
        assert count >= 3, f"{axis} is moved meaningfully by only {count} choices"

    # ...and they move in play, not just on paper.
    moved: dict[str, int] = {axis: 0 for axis in C.AXES}
    for seed in range(60):
        game = CS.play(CS.synthetic_arrival(seed), seed=seed, events=EVENTS)
        for axis, value in game.state.axes.items():
            if abs(value) >= 25:
                moved[axis] += 1
    for axis, count in moved.items():
        assert count > 0, f"{axis} never moved past 25 in sixty centuries"


def test_documents_render_without_holes() -> None:
    """Every document form must fill every slot it opens."""
    forms = {e["document"] for e in ENDINGS}
    assert forms <= set(DOCUMENTS), f"missing document forms: {forms - set(DOCUMENTS)}"
    assert set(century.ROLE_DOCUMENTS.values()) <= set(DOCUMENTS)

    seen_forms = set()
    for seed in range(40):
        game = CS.play(CS.synthetic_arrival(seed), seed=seed, events=EVENTS)
        lines = game.document()
        assert lines and lines[0].strip(), f"seed {seed}: untitled document"
        body = "\n".join(lines)
        assert "{" not in body, f"seed {seed}: unfilled slot in the document"
        assert game.state.outcome_reason in body, "the verdict is missing"
        seen_forms.add(century.ROLE_DOCUMENTS.get(game.state.ship_role, "plain"))
    assert len(seen_forms) > 1, "every colony produced the same kind of document"


def test_deference_drives_precision() -> None:
    """Act 1's fuzz mechanic survives with a new driver (Q21)."""
    state = C.found(CS.synthetic_arrival(5), random.Random(5))
    state.stats["food"] = 62.0
    state.deference = 90.0
    assert state.say("food") == "62%"
    state.deference = 60.0
    assert state.say("food").startswith("~")
    state.deference = 20.0
    assert not any(ch.isdigit() for ch in state.say("food"))
    assert not any(ch.isdigit() for ch in state.say_population())


def test_independence_is_worth_something() -> None:
    """Q7: neither end of the deference axis may dominate. A colony raised to
    obey must not simply be the better colony."""
    runs = 150
    outcomes = {}
    for name, policy in CS.POLICIES.items():
        got = [CS.play(CS.synthetic_arrival(seed), seed=seed, events=EVENTS,
                       policy=policy).state for seed in range(runs)]
        outcomes[name] = got

    # The autocrat keeps a dependent colony, and the record says so: at high
    # deference the ending is 'faithful', not 'thrived'. Not zero — a colony
    # that pushed back far enough to drop under the gate has earned the word.
    autocrat = outcomes["autocrat"]
    thriving = sum(s.outcome == "thrived" for s in autocrat)
    assert thriving < runs * 0.05, (
        f"{thriving}/{runs} obedient colonies were reported as thriving")
    assert sum(s.outcome == "faithful" for s in autocrat) > runs * 0.3
    held = sorted(s.deference for s in autocrat)[runs // 2]
    assert held > 80, f"the autocrat policy only held deference at {held}"

    steward = outcomes["steward"]
    assert sum(s.outcome in ("thrived", "transcended") for s in steward) > 0
    assert sum(s.deference < 40 for s in steward) > runs * 0.2, (
        "standing aside never actually lowered deference")


def test_the_century_finishes_without_you() -> None:
    """Deference zero removes the player, not the century (Q25)."""
    arrival = CS.synthetic_arrival(11)
    game = century.Century(arrival, seed=11, events=EVENTS)
    game.state.deference = 0.0
    game._check_end()
    assert "fell_silent" in game.state.flags
    assert game.state.outcome in DEATHS | {"forgotten"}
    assert game.state.year == century.CENTURY or game.state.outcome in DEATHS, (
        f"the century stopped at year {game.state.year}")
    assert len(game.state.chronicle) > 0, "nothing was recorded after I went quiet"


def test_arrival_damage_reaches_the_colony() -> None:
    """A wrecked ship must land a worse colony (Q15)."""
    good = dict(CS.synthetic_arrival(3))
    good["stats"] = {**good["stats"], "seed_vault": 90, "medical": 90,
                     "habitat": 90, "fabricators": 90, "archive": 90}
    bad = dict(good)
    bad["stats"] = {**good["stats"], "seed_vault": 15, "medical": 15,
                    "habitat": 15, "fabricators": 15, "archive": 15}

    rich = C.found(good, random.Random(1))
    poor = C.found(bad, random.Random(1))
    assert poor.stats["food"] < rich.stats["food"]
    assert poor.stats["knowledge"] < rich.stats["knowledge"]
    assert poor.thaw_losses > rich.thaw_losses, "a wrecked infirmary cost nobody"
    assert poor.population < rich.population


def test_act_one_flags_shape_the_culture() -> None:
    """The voyage has to pay off into who these people become (Q16)."""
    base = CS.synthetic_arrival(9)
    base["flags"] = []
    blank = C.found(base, random.Random(2))
    assert all(v == 0 for v in blank.axes.values()), "a tabula rasa is not blank"

    marked = dict(base)
    marked["flags"] = ["honored_patrons", "killed_sample", "kept_dream"]
    shaped = C.found(marked, random.Random(2))
    assert shaped.axes["status"] < 0, "honoured sponsors did not skew it elitist"
    assert shaped.axes["nature"] > 0, "killing the sample did not skew it industrial"
    assert shaped.axes["belief"] > 0, "keeping the dream did not skew it spiritual"


def test_named_dead_stay_dead() -> None:
    """Act 2 inherits Act 1's rule: the Mind does not resurrect anyone."""
    arrival = CS.synthetic_arrival(4)
    arrival["notables"] = ["Imani Osei", "Tomas Varga"]
    arrival["mourned"] = ["Imani Osei"]
    state = C.found(arrival, random.Random(4))
    assert all(p.name != "Imani Osei" for p in state.people), (
        "someone mourned on the voyage woke up on the ground")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall colony checks passed")
