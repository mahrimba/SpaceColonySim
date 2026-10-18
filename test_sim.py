"""The smallest set of checks that fail if the engine or the content breaks.

    python test_sim.py

No framework. Each check is an assert over real runs of the real engine.
"""

from __future__ import annotations

import random

import constants as K
import deck
import planets
import readout
import resolve
import sim

EVENTS = deck.load()
SCRIPT = [0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 0]


def test_determinism() -> None:
    """Q14: same seed plus the same choices must replay exactly."""
    for seed in (1, 17, 404, 90210):
        a = sim.play(seed, events=EVENTS, choices=list(SCRIPT))
        b = sim.play(seed, events=EVENTS, choices=list(SCRIPT))
        assert a.state.to_dict() == b.state.to_dict(), f"seed {seed} diverged"
        assert a.state.log == b.state.log, f"seed {seed} log diverged"

    # ...and different seeds must actually produce different voyages.
    distinct = {sim.play(s, events=EVENTS, choices=list(SCRIPT)).state.log[1]
                for s in range(8)}
    assert len(distinct) > 1, "seeding has no effect on the world"


def test_runs_terminate_in_a_legal_state() -> None:
    """No run may end mid-air, out of range, or in an unreachable state."""
    legal = {"colonized", "adrift", "destroyed", "extinct", "incoherent", "dark"}
    for seed in range(200):
        g = sim.play(seed, profile=["survey", "ark", "longrange"][seed % 3],
                     events=EVENTS)
        s = g.state
        assert g.phase == resolve.DONE, f"seed {seed} stopped mid-phase"
        assert s.outcome in legal, f"seed {seed}: outcome {s.outcome!r}"
        assert s.outcome_reason, f"seed {seed}: death without a reason"
        for stat, value in s.stats.items():
            assert 0.0 <= value <= 100.0, f"seed {seed}: {stat} = {value}"
        assert s.colonists_alive >= 0 and s.colonists_lost >= 0
        assert 1 <= s.leg <= sim.MAX_LEGS
        # One event per leg. Lingering adds a nick or an observation, never
        # a second thing to answer.
        assert g.events_drawn <= s.leg, (
            f"seed {seed}: {g.events_drawn} events over {s.leg} legs")
        if s.outcome == "colonized":
            assert s.chosen_planet is not None, "colonised nothing"
        else:
            assert s.chosen_planet is None, "died but kept a planet"


def test_zero_power_ends_the_run() -> None:
    """The reactor going out is an ending, not a penalty."""
    g = resolve.Game(seed=1, events=EVENTS)
    g.state.stats["power"] = 2.0
    g.state.adjust("power", -2.0)
    g.state._check_death()
    assert g.state.outcome == "dark", f"power hit zero and the run continued: {g.state.outcome}"
    assert not g.state.flying

    # ...and the UI must never offer an action that spends power it lacks.
    g2 = resolve.Game(seed=2, events=EVENTS)
    g2.state.stats["power"] = 3.0
    costs = {"diagnostics": K.DIAGNOSTIC_POWER_COST, "repair": K.REPAIR_POWER_COST}
    for opt in g2.maintenance_options():
        cost = costs.get(opt["action"], 0.0)
        assert cost < g2.state.stats["power"], (
            f"{opt['action']} offered at {g2.state.stats['power']} power, costs {cost}")


def test_flavour_pool_is_wired_up() -> None:
    """Observations must exist, and must not be keyed on tags that never occur."""
    flavour = deck.load_flavour()
    assert flavour["any"], "no generic observations"
    for tag in flavour:
        assert tag == "any" or tag in K.SYSTEM_TAGS, f"flavour keyed on unknown tag {tag}"
        assert flavour[tag], f"empty flavour pool for {tag}"


def test_content_is_wired_up() -> None:
    """Every effect, check and chain in voyage.json must mean something."""
    ids = {e["id"] for e in EVENTS}
    scheduled: set[str] = set()

    for event in EVENTS:
        assert event["text"], f"{event['id']}: no text"
        for stat in event.get("requires", {}).get("stats", {}):
            assert stat in K.STATS, f"{event['id']}: gated on unknown {stat}"
        for tag in (event.get("requires", {}).get("tags", [])
                    + event.get("requires", {}).get("any_tags", [])):
            assert tag in K.SYSTEM_TAGS, f"{event['id']}: unknown tag {tag}"

        for choice in event["choices"]:
            assert choice.get("label"), f"{event['id']}: unlabelled choice"
            check = choice.get("check")
            if check:
                assert check["stat"] in K.STATS, f"{event['id']}: bad check stat"
                assert K.DC_BAND[0] <= check["dc"] <= K.DC_BAND[1], (
                    f"{event['id']}: DC {check['dc']} outside {K.DC_BAND}")
                assert choice.get("success") and choice.get("failure"), (
                    f"{event['id']}: a check needs success and failure")
                outcomes = [choice[g] for g in
                            ("crit_success", "success", "failure", "crit_failure")
                            if g in choice]
            else:
                outcomes = [choice]

            for outcome in outcomes:
                for key, value in outcome.get("effects", {}).items():
                    assert key in resolve.EFFECT_KEYS, (
                        f"{event['id']}: unknown effect {key!r}")
                    if key == "queue":
                        scheduled.update(target for target, _ in value)

    assert scheduled <= ids, f"scheduled events that do not exist: {scheduled - ids}"
    for event in EVENTS:
        if event.get("chain_only"):
            assert event["id"] in scheduled, (
                f"{event['id']} is chain_only but nothing ever schedules it")


def test_nat20_always_wins_and_nat1_always_loses() -> None:
    """The modifier curve leaves DC 16 unreachable at zero stat, so the natural
    20 rule is what keeps every check winnable. It must not be bypassable."""
    assert resolve.modifier(0) == -5 and resolve.modifier(100) == 5
    assert 20 + resolve.modifier(0) < K.DC_BAND[1], (
        "curve changed: re-check that nat 20 is still load-bearing")

    event = {"id": "t", "text": ["t"], "choices": [{
        "label": "t", "check": {"stat": "hull", "dc": 16},
        "success": {"text": "ok"}, "failure": {"text": "no"},
        "crit_success": {"text": "CRIT", "effects": {"hull": 1}},
        "crit_failure": {"text": "RUIN", "effects": {"hull": -1}}}]}

    crits, ruins = 0, 0
    for seed in range(400):
        g = resolve.Game(seed=seed, events=[event])
        g.state.stats["hull"] = 1.0  # modifier -5: DC 16 is arithmetically out of reach
        g.phase = resolve.EVENT
        g.current = event
        lines = " ".join(g.resolve_choice(0))
        crits += "CRIT" in lines
        ruins += "RUIN" in lines
    assert crits > 0, "natural 20 never fired; checks are unwinnable at low stats"
    assert ruins > 0, "natural 1 never fired"


def test_readout_degrades_without_leaking() -> None:
    """Q24/Q29: precision drops in tiers, and the vague tier must not leak digits."""
    assert readout.stat(55.0, 90) == "55%"
    assert readout.stat(55.0, 60).startswith("~")
    vague = readout.stat(55.0, 20)
    assert not any(ch.isdigit() for ch in vague), f"vague tier leaked: {vague}"
    assert not any(ch.isdigit() for ch in readout.count(9_432, 10))
    assert readout.count(9_432, 90) == "9,432"

    # An old survey keeps the precision it was taken at, even after repairs.
    rng = random.Random(3)
    p = planets.generate(rng, {"gas_giant"}, cognition=30.0)
    assert not any(ch.isdigit() for v in dict(p.dossier()).values() for ch in v), (
        "a survey taken while incoherent reported hard numbers")


def test_habitability_is_demanding() -> None:
    """A world that fails one axis is lethal, not half-good."""
    rng = random.Random(11)
    sample = [planets.generate(rng, set(), 100.0) for _ in range(3000)]
    gardens = sum(p.habitability() >= 0.60 for p in sample) / len(sample)
    settleable = sum(p.habitability() >= 0.30 for p in sample) / len(sample)
    assert 0.005 <= gardens <= 0.08, f"garden share drifted to {gardens:.3f}"
    assert 0.08 <= settleable <= 0.35, f"settleable share drifted to {settleable:.3f}"

    airless = planets.Planet("X", 1.0, 0.0, 15.0, 0.0, "none", 1.0)
    assert airless.habitability() == 0.0 and airless.verdict() == "lethal"


def test_arrival_rate_near_target() -> None:
    """Q33: ~60% of competent runs should reach a world alive."""
    arrived = sum(sim.play(seed, events=EVENTS).state.outcome == "colonized"
                  for seed in range(250)) / 250
    assert 0.45 <= arrived <= 0.75, f"arrival rate is {arrived:.1%}, retune constants"


def test_app_plays_through() -> None:
    """The TUI must survive a whole voyage. Skipped when textual is absent."""
    try:
        import asyncio

        from app import Voyage
    except ImportError:
        print("skip test_app_plays_through (textual not installed)")
        return

    async def drive() -> None:
        app = Voyage(seed=1234)
        async with app.run_test() as pilot:
            await pilot.press("1")
            panel = app.query_one("#panel").last
            assert "Hull" in panel and "Sleepers" in panel, (
                "status panel is not rendering telemetry")
            assert app.options, "no choices offered after launch"
            for _ in range(400):
                if app.game.phase == resolve.DONE:
                    break
                await pilot.press("1")
            assert app.game.phase == resolve.DONE, "voyage never ended"
            await pilot.press("p")  # dossier view must not explode either

    asyncio.run(drive())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall checks passed")
