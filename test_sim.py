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
import state

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
    """~75% of competent runs should reach a world alive."""
    arrived = sum(sim.play(seed, events=EVENTS).state.outcome == "colonized"
                  for seed in range(250)) / 250
    assert 0.62 <= arrived <= 0.88, f"arrival rate is {arrived:.1%}, retune constants"


def test_events_do_not_repeat_inside_the_cooldown() -> None:
    """The same crisis must not arrive three legs running."""
    for seed in range(120):
        g = sim.play(seed, events=EVENTS)
        last: dict[str, int] = {}
        for leg, event_id in g.draw_history:
            previous = last.get(event_id)
            assert previous is None or leg - previous >= K.EVENT_COOLDOWN, (
                f"seed {seed}: {event_id} repeated at legs {previous} and {leg}")
            last[event_id] = leg


def test_scheduled_follow_up_dies_with_its_premise() -> None:
    """A queued chain event whose premise you already resolved must not fire."""
    g = resolve.Game(seed=4, events=EVENTS)
    g.state.flags.add("coolant_fixed")          # you repaired the loop properly
    g.state.schedule("coolant_returns", 1)
    g.state.leg += 1
    drawn = deck.draw(EVENTS, g.state, g.rng)
    assert drawn is None or drawn["id"] != "coolant_returns", (
        "the repaired coolant line failed anyway")
    assert not g.state.queue, "stale queue entry was left behind"

    # ...but it does fire while the premise still stands.
    g2 = resolve.Game(seed=4, events=EVENTS)
    g2.state.schedule("coolant_returns", 1)
    g2.state.leg += 1
    assert deck.draw(EVENTS, g2.state, g2.rng)["id"] == "coolant_returns"


def test_threshold_warnings_fire_once_and_rearm() -> None:
    """One line per crossing, and again if you lose the ground you regained."""
    s = state.ShipState.launch("survey")
    s.stats["hull"] = 47.0
    assert len(s.threshold_warnings()) == 1, "no warning on crossing 50"
    s.stats["hull"] = 44.0
    assert s.threshold_warnings() == [], "warned twice for the same level"
    s.stats["hull"] = 28.0
    assert "Critical" in s.threshold_warnings()[0]
    s.stats["hull"] = 70.0
    assert s.threshold_warnings() == [], "recovery is not an event"
    s.stats["hull"] = 48.0
    assert len(s.threshold_warnings()) == 1, "did not re-arm after recovering"


def test_no_line_hard_codes_a_headcount() -> None:
    """The sleeper count depends on the hull (8k/10k/14k), so no line may name it."""
    import json
    import re

    texts: list[tuple[str, str]] = []
    for event in EVENTS:
        for t in event["text"]:
            texts.append((event["id"], t))
        for choice in event["choices"]:
            for slot in ("crit_success", "success", "failure", "crit_failure"):
                if slot in choice:
                    texts.append((event["id"], choice[slot].get("text", "")))
            texts.append((event["id"], choice.get("text", "")))
    for pool, lines in deck.load_flavour().items():
        texts += [(f"flavour/{pool}", line) for line in lines]

    people = r"(people|sleepers?|bodies|colonists?|hearts?|shapes|lives|souls|names)"
    bad = [(src, t) for src, t in texts
           if re.search(rf"(ten thousand|10,000)\s+\w*\s*{people}", t, re.I)]
    assert not bad, f"hard-coded headcount in {[b[0] for b in bad]}"


def test_the_dead_are_not_named_again() -> None:
    """A sleeper mourned by name must not turn up alive later."""
    s = state.ShipState.launch("survey")
    rng = random.Random(0)
    names = {s.colonist(rng, reuse=0.0) for _ in range(12)}
    for name in list(names)[:6]:
        s.mourn(name)
    for _ in range(400):
        assert s.colonist(rng, reuse=1.0) not in s.mourned, "the Mind resurrected someone"

    # ...and it happens for real: some runs mourn, none re-mention.
    mourning_runs = 0
    for seed in range(120):
        g = sim.play(seed, events=EVENTS)
        if not g.state.mourned:
            continue
        mourning_runs += 1
        for dead in g.state.mourned:
            mentions = [line for line in g.state.log if dead in line]
            assert len(mentions) == 1, f"seed {seed}: {dead} named {len(mentions)} times"
    assert mourning_runs > 0, "no run mourned anyone; this check proved nothing"


def test_every_stat_has_a_glyph_and_a_parsable_colour() -> None:
    """A colour name Textual cannot parse renders grey with no error, so the
    only way to catch a typo is to parse them here."""
    for stat in K.STATS + ["colonists", "lost"]:
        assert stat in K.GLYPHS, f"{stat} has no glyph"
        assert stat in K.COLOURS, f"{stat} has no colour"
    try:
        from textual.color import Color
    except ImportError:
        print("skip colour parsing (textual not installed)")
        return
    for stat, name in K.COLOURS.items():
        Color.parse(name)  # raises on anything Textual cannot render


def test_the_mind_has_no_human_body() -> None:
    """The Mind acts through drones and cameras and has no body but the ship.

    'my hands', 'my eyes' and 'my skin' are deliberately allowed: the bible
    makes drones its hands, cameras its eyes and the hull its skin. What is
    banned is anatomy with no ship analogue, and physical work done in first
    person without a drone doing it.
    """
    import re
    from pathlib import Path

    # 'I crawl' is not banned: a ship crawls while light overtakes it, which
    # is the ship's motion, not a body's.
    banned = re.compile(
        r"\b(my (fingers?|face|arms?|legs?|feet|mouth|teeth|shoulders?|chest|"
        r"stomach|knees?|hair|lungs|throat)"
        r"|I (weld|welded|walk|walked|kneel|knelt|grip|gripped))\b",
        re.I)

    lines: list[tuple[str, str]] = []
    for event in EVENTS:
        lines += [(event["id"], t) for t in event["text"]]
        for choice in event["choices"]:
            lines.append((event["id"], choice["label"]))
            for slot in ("crit_success", "success", "failure", "crit_failure"):
                if slot in choice:
                    lines.append((event["id"], choice[slot].get("text", "")))
            lines.append((event["id"], choice.get("text", "")))
    for pool, pool_lines in deck.load_flavour().items():
        lines += [(f"flavour/{pool}", line) for line in pool_lines]
    for module in ("resolve.py", "state.py"):
        source = Path(__file__).with_name(module).read_text(encoding="utf-8")
        lines += [(module, lit) for lit in re.findall(r'"([^"\\]+)"', source)]

    bad = [(src, m.group(0), text[:70]) for src, text in lines
           if (m := banned.search(text))]
    assert not bad, f"the Mind grew a body: {bad}"


def test_markup_colours_in_the_view_are_real() -> None:
    """Textual renders an unknown colour name as grey and raises nothing, so
    every literal colour in session.py has to be parsed here or typos ship."""
    try:
        from textual.color import Color
    except ImportError:
        print("skip markup colour check (textual not installed)")
        return
    import session as app

    styles = {"b", "i", "u", "bold", "italic", "underline", "dim", "strike",
              "reverse", "blink", "on", "not"}
    for name, markup in app.STYLES.items():
        for token in markup.split():
            if token in styles:
                continue
            Color.parse(token)  # raises on a Rich-only or misspelled name


def test_survey_reports_what_it_found() -> None:
    """Sweeping must produce a readable table, at the Mind's own precision."""
    game = resolve.Game(profile="survey", seed=12, events=EVENTS)
    lines = game.do_maintenance("survey")
    rows = [ln for ln in lines if ln.startswith(resolve.TABLE)]
    assert game.state.candidates, "the sweep found nothing"
    assert rows, "the sweep reported no table"
    for label, _ in game.state.candidates[0].dossier():
        assert any(label in r for r in rows), f"{label} missing from the table"
    assert all(w.name in rows[0] for w in game.state.candidates[:3]), "no world names"

    # A blind ship must not report hard numbers in that table.
    blind = resolve.Game(profile="survey", seed=12, events=EVENTS)
    blind.state.stats["cognition"] = 20.0
    rows = [ln for ln in blind.do_maintenance("survey") if ln.startswith(resolve.TABLE)]
    body = "".join(rows[1:])  # row 0 is the names, which carry digits legitimately
    assert not any(ch.isdigit() for ch in body), f"vague survey leaked numbers: {body}"


def test_the_log_records_the_choice() -> None:
    """A playthrough must show what the player picked, not just what happened."""
    game = resolve.Game(profile="survey", seed=3, events=EVENTS)
    while game.phase != resolve.EVENT:
        game.do_maintenance("hold")
    label = game.choices()[0]["label"]
    lines = game.resolve_choice(0)
    assert lines[0] == f"{resolve.CHOICE} {label}", f"choice not logged: {lines[0]!r}"
    assert any(ln.startswith(resolve.CHOICE) for ln in game.state.log)


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


def test_web_bridge_plays_through() -> None:
    """The browser's bridge must turn every line into HTML, with no markup
    left over, and survive a voyage and its century."""
    import json
    import re
    import sys
    import tempfile
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "web"))
    import bridge

    assert bridge.to_html("[b cyan]1) [/b cyan]a [Hull check, DC 12, +3]") == (
        '<span class="b accent">1) </span>a [Hull check, DC 12, +3]')
    update = json.loads(bridge.boot(tempfile.mkdtemp()))
    for _ in range(3000):
        labels = update["options"]
        if "Retry" in labels[0] and update["landed"]:
            break
        pick = next((i for i, l in enumerate(labels)
                     if "commit" in l or "first century" in l or "New game" in l), 0)
        update = json.loads(bridge.choose(pick))
        for block in update["blocks"]:
            for _, line in block["lines"]:
                assert not re.search(r"\[/?[a-z]", line), f"markup leaked: {line}"
    assert update["landed"] and "Retry" in update["options"][0], "never reached the end"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall checks passed")
