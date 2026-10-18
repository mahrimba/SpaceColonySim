"""Textual front end. A view onto resolve.Game — no rules live here.

    python app.py            # a new voyage
    python app.py --seed 42  # replay a specific one
"""

from __future__ import annotations

import argparse

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

import century as CY
import colony as C
import constants as K
import planets
import resolve
import state
from resolve import DONE, EVENT, MAINTENANCE, Game

KEYS = "123456789abcdefghij"  # option index -> keycap

# Every colour the log uses, in one place. Textual renders an unknown colour
# name as grey and raises nothing, so these are parsed in test_sim.py; a name
# that only Rich knows (bright_blue, grey54) would otherwise ship silently.
STYLES = {
    "rule": "dim",
    "leg": "b",
    "choice": "darkgray",      # what the player picked: present, not loud
    "table": "dim cyan",       # instrument output
    "warn": "b yellow",
    "warn_bad": "b red",
    "roll": "dim",
    "gain": "green",
    "loss": "red",
    "crit_success": "b green",
    "crit_failure": "b red",
    "success": "green",
    "failure": "red",
}


class Panel(Static):
    """Persistent telemetry. Precision is the ship's problem, not the UI's."""

    last = ""  # plain text of the most recent render, for the smoke test

    def render_colony(self, century_game) -> None:
        s = century_game.state
        rows = [f"[b]{s.name}[/b]", f"[dim]{s.ship_role}[/dim]", ""]
        rows.append(f"Year [b]{s.year}[/b]" + (f"  [dim](+{s.span})[/dim]"
                                               if s.span > 1 else ""))
        rows.append("")
        rows.append(f"[white]█ [/white]{'People':<13}{s.say_population()}")
        for stat in C.COLONY_STATS:
            colour = C.COLONY_COLOURS[stat]
            value = s.stats[stat]
            tone = "green" if value > 60 else ("yellow" if value > 30 else "red")
            rows.append(f"[{colour}]█ [/{colour}]{C.COLONY_LABELS[stat]:<13}"
                        f"[{tone}]{s.say(stat)}[/{tone}]")
        rows.append("")
        tone = "green" if s.deference > 60 else ("yellow" if s.deference > 25 else "red")
        rows.append(f"[cyan]█ [/cyan]{'Deference':<13}[{tone}]{s.deference:.0f}%[/{tone}]")

        shown = [(a, v) for a, v in s.axes.items() if abs(v) >= 10]
        if shown:
            rows.append("")
            rows.append("[dim]WHAT THEY ARE[/dim]")
            for axis, value in shown:
                low, high = C.AXES[axis]
                pos = int(round((value + 100) / 200 * 8))
                bar = "─" * pos + "●" + "─" * (8 - pos)
                pole = high if value > 0 else low
                rows.append(f"[dim]{bar}[/dim] {pole}")
        rows.append("")
        rows.append(f"  [dim]{len(s.living())} named alive — press c[/dim]")
        self.last = "\n".join(rows)
        self.update(self.last)

    def render_state(self, game: Game | None) -> None:
        if game is None:
            self.last = "No ship underway."
            self.update("[dim]No ship underway.[/dim]")
            return
        s = game.state
        rows = [f"[b]{s.name}[/b]", f"[dim]seed {game.seed}[/dim]", ""]
        rows.append(f"Leg [b]{s.leg}[/b]")
        if s.system_name:
            tags = ", ".join(sorted(t.replace("_", " ") for t in s.system_tags))
            rows.append(f"{s.system_name}")
            rows.append(f"[dim]{tags}[/dim]")
        rows.append("")
        for stat in K.SYSTEMS:
            rows.append(self._row(s, stat))
        rows.append("")
        rows.append("[dim]HOLDS[/dim]")
        for hold in K.HOLDS:
            rows.append(self._row(s, hold))
        rows.append("")
        rows.append(f"[white]█ [/white]{'Sleepers':<13}"
                    f"{s.say_count(s.colonists_alive)}")
        if s.colonists_lost:
            rows.append(f"[red]█ {'Lost':<13}"
                        f"{s.say_count(s.colonists_lost)}[/red]")
        rows.append("")
        rows.append(f"  {'Range':<13}{s.legs_of_fuel():.0f} legs")
        rows.append(f"  {'Candidates':<13}{len(s.candidates)}")
        rows.append("")
        self.last = "\n".join(rows)
        self.update(self.last)

    def _row(self, state, stat: str) -> str:
        """Identity colour in the block, condition colour in the number."""
        colour = K.COLOURS[stat]
        return (f"[{colour}]█ [/{colour}]{K.LABELS[stat]:<13}"
                f"{self._bar(state, stat)}")

    def _bar(self, state, stat: str) -> str:
        value = state.stats[stat]
        colour = "green" if value > 60 else ("yellow" if value > 30 else "red")
        return f"[{colour}]{state.say(stat)}[/{colour}]"


class Voyage(App):
    CSS = """
    Screen { layout: horizontal; }
    #panel { width: 32; padding: 1 2; border-right: solid $accent; }
    /* The log is a plain Static inside a scroller, not a RichLog: RichLog
       renders each line at the width it had when written, so earlier lines
       crop mid-sentence once the scrollbar appears. A Static re-wraps. */
    #logbox { height: 1fr; }
    #log { padding: 1 2; }
    #choices { padding: 1 2; height: auto; max-height: 50%;
               border-top: solid $accent; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("p", "planets", "Planet dossiers"),
                ("c", "cast", "Who is alive"), ("m", "back", "Back")]

    def __init__(self, seed: int | None = None, arrival: dict | None = None):
        super().__init__()
        self.seed = seed
        self.arrival = arrival
        self.century: CY.Century | None = None
        self.game: Game | None = None
        self.options: list[dict] = []
        self.lines: list[str] = []

    # -- layout ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Panel(id="panel")
        with Vertical():
            with VerticalScroll(id="logbox"):
                yield Static(id="log", markup=True)
            yield Static(id="choices")

    def on_mount(self) -> None:
        self.title = "Space Colony Sim"
        self.show("[b]COLONY MISSION — INTELLIGENCE ONLINE[/b]",
                  "",
                  "Ten thousand people are asleep behind me. I am the only thing "
                  "awake, and the only thing that decides.",
                  "",
                  "[dim]Number keys choose. p reads the surveyed worlds. "
                  "m steps back. q quits.[/dim]")
        if self.arrival is not None:
            self.begin_century(self.arrival)
        else:
            self.offer_profiles()

    # -- option plumbing ------------------------------------------------------

    def show(self, *lines: str) -> None:
        for line in lines:
            self.lines.append(self._style(line))
        self.lines.append("")
        self.query_one("#log", Static).update("\n".join(self.lines))
        self.call_after_refresh(
            self.query_one("#logbox", VerticalScroll).scroll_end, animate=False)

    @staticmethod
    def _style(line: str) -> str:
        """Give the log a hierarchy: prose reads plain, mechanics stand apart."""
        S = STYLES
        # A rule before each leg, so one leg reads as one scene.
        if line.startswith("— Leg "):
            return (f"[{S['rule']}]" + "─" * 48 + f"[/{S['rule']}]"
                    f"\n[{S['leg']}]{line}[/{S['leg']}]")

        # The option the player took, quieter than the prose around it.
        if line.startswith(resolve.CHOICE + " "):
            return f"[{S['choice']}]{line}[/{S['choice']}]"

        # Survey data reads as instrument output, not narration.
        if line.startswith(resolve.TABLE + " "):
            return f"[{S['table']}]{line[2:]}[/{S['table']}]"

        # Warnings: the one thing in the log that should interrupt reading.
        if line.startswith(state.WARN + " "):
            key = "warn_bad" if ("Failing" in line or "Critical" in line) else "warn"
            return f"[{S[key]}]{line}[/{S[key]}]"

        # Stat changes: one colour per sign, so a glance says won or lost.
        if line.startswith(resolve.DELTA + " "):
            parts = []
            for token in line[2:].split("   "):
                # Losses read red whether they are a negative number or a
                # body count, which carries no minus sign.
                lowered = token.lower()
                bad = ("lost" in lowered or "dead" in lowered
                       or token.rsplit(" ", 1)[-1].startswith("-"))
                colour = S["loss"] if bad else S["gain"]
                parts.append(f"[{colour}]{token}[/{colour}]")
            return f"[{S['rule']}]{resolve.DELTA}[/{S['rule']}] " + "  ".join(parts)

        # Dice: dim the arithmetic, colour the verdict.
        if line.startswith("› "):
            for verdict, key in (("Critical success.", "crit_success"),
                                 ("Critical failure.", "crit_failure"),
                                 ("Success.", "success"),
                                 ("Failed.", "failure")):
                if line.endswith(verdict):
                    body = line[:-len(verdict)]
                    return (f"[{S['roll']}]{body}[/{S['roll']}]"
                            f"[{S[verdict and key]}]{verdict}[/{S[key]}]")
            return f"[{S['roll']}]{line}[/{S['roll']}]"

        return line

    def set_options(self, options: list[dict], prompt: str = "") -> None:
        self.options = options
        body = [f"[b]{prompt}[/b]"] if prompt else []
        for i, opt in enumerate(options):
            body.append(f"[b cyan]{KEYS[i]}) [/b cyan]{opt['label']}")
        self.query_one("#choices", Static).update("\n".join(body))
        panel = self.query_one("#panel", Panel)
        if self.century is not None:
            panel.render_colony(self.century)
        else:
            panel.render_state(self.game)

    def on_key(self, event) -> None:
        if event.key not in KEYS:
            return
        index = KEYS.index(event.key)
        if index < len(self.options):
            event.stop()
            self.options[index]["do"]()

    # -- launch ---------------------------------------------------------------

    def offer_profiles(self) -> None:
        options = []
        for key, spec in K.PROFILES.items():
            options.append({
                "label": f"{spec['name']} — {spec['blurb']}",
                "do": (lambda k=key: self.launch(k)),
            })
        self.set_options(options, "Which hull am I?")

    def launch(self, profile: str) -> None:
        self.game = Game(profile=profile, seed=self.seed)
        self.show(f"[b]{self.game.state.name}[/b] underway. "
                  f"[dim]Seed {self.game.seed}.[/dim]")
        self.show(*self.game.state.log[1:])
        self.refresh_phase()

    # -- the loop -------------------------------------------------------------

    def refresh_phase(self) -> None:
        game = self.game
        assert game
        if game.phase == DONE:
            self.finish()
        elif game.phase == MAINTENANCE:
            self.offer_maintenance()
        elif game.phase == EVENT:
            self.offer_event_choices()

    def offer_maintenance(self) -> None:
        game = self.game
        assert game
        options: list[dict] = []
        for opt in game.maintenance_options():
            if opt["action"] == "repair":
                continue
            if opt["action"] == "cannibalize":
                continue
            options.append({"label": opt["label"],
                            "do": (lambda o=opt: self.act(**{
                                k: v for k, v in o.items() if k != "label"}))})
        options.append({"label": "Repair a system…", "do": self.offer_repairs})
        options.append({"label": "Strip a hold for parts…",
                        "do": self.offer_cannibalize})
        if game.can_commit():
            options.append({"label": "[b]Decelerate and commit to a world…[/b]",
                            "do": self.offer_commit})
        elif game.state.candidates:
            options.append({"label": f"[dim]Commit (needs "
                                     f"{K.DECEL_FUEL_COST:.0f} fuel to "
                                     f"decelerate)[/dim]",
                            "do": lambda: self.show(
                                "Not enough reaction mass left to stop. I would "
                                "fly straight past it.")})
        self.set_options(options, f"Leg {game.state.leg} — one action before "
                                  "whatever is out here finds me.")

    def offer_repairs(self) -> None:
        game = self.game
        assert game
        options = [{"label": f"{K.LABELS[stat]} ({game.state.say(stat)})",
                    "do": (lambda st=stat: self.act("repair", target=st))}
                   for stat in resolve.REPAIRABLE]
        options.append({"label": "[dim]back[/dim]", "do": self.offer_maintenance})
        self.set_options(options, "Repair what?")

    def offer_cannibalize(self) -> None:
        options = [{"label": f"Strip {K.LABELS[hold].lower()}",
                    "do": (lambda h=hold: self.offer_scrap_target(h))}
                   for hold in K.HOLDS]
        options.append({"label": "[dim]back[/dim]", "do": self.offer_maintenance})
        self.set_options(options, "Take apart which hold?")

    def offer_scrap_target(self, hold: str) -> None:
        options = [{"label": f"Into {K.LABELS[stat].lower()}",
                    "do": (lambda st=stat: self.act(
                        "cannibalize", hold=hold, target=st))}
                   for stat in resolve.SCRAP_TARGETS]
        options.append({"label": "[dim]back[/dim]", "do": self.offer_cannibalize})
        self.set_options(options, f"Feed {K.LABELS[hold].lower()} into what?")

    def offer_commit(self) -> None:
        game = self.game
        assert game
        options = []
        for planet in game.state.candidates:
            summary = ", ".join(f"{k.lower()} {v}" for k, v in planet.dossier()[:3])
            options.append({"label": f"{planet.name} — {summary}",
                            "do": (lambda p=planet: self.commit(p))})
        options.append({"label": "[dim]back[/dim]", "do": self.offer_maintenance})
        self.set_options(options, "Commit to which world? This ends the voyage.")

    def act(self, action: str, **kwargs) -> None:
        game = self.game
        assert game
        self.show(*game.do_maintenance(action, **kwargs))
        self.refresh_phase()

    def offer_event_choices(self) -> None:
        game = self.game
        assert game
        options = [{"label": game.choice_label(choice),
                    "do": (lambda i=i: self.pick(i))}
                   for i, choice in enumerate(game.choices())]
        self.set_options(options, "")

    def pick(self, index: int) -> None:
        game = self.game
        assert game
        self.show(*game.resolve_choice(index))
        self.refresh_phase()

    def commit(self, planet) -> None:
        game = self.game
        assert game
        self.show(*game.commit(planet))
        self.refresh_phase()

    # -- endings --------------------------------------------------------------

    def action_planets(self) -> None:
        game = self.game
        if not game or not game.state.candidates:
            self.show("[dim]Nothing surveyed yet.[/dim]")
            return
        self.show("Everything I have surveyed so far:",
                  *(f"{resolve.TABLE} {row}"
                    for row in planets.table(game.state.candidates)))

    def action_back(self) -> None:
        if self.game and self.game.phase == MAINTENANCE:
            self.offer_maintenance()

    def finish(self) -> None:
        game = self.game
        assert game
        path = f"arrival_{game.seed}.json"
        game.state.dump(path)
        self.show("", "[b]— END OF VOYAGE —[/b]", *game.report(), "",
                  f"[dim]State written to {path}.[/dim]")
        options = []
        if game.state.outcome == "colonized":
            options.append({"label": "[b]Begin the first century[/b]",
                            "do": lambda: self.begin_century(game.state.to_dict())})
        options.append({"label": "Quit", "do": self.exit})
        self.set_options(options, "")

    # -- act two ---------------------------------------------------------------

    def begin_century(self, arrival: dict) -> None:
        self.century = CY.Century(arrival, seed=self.seed)
        self.lines.append("")
        self.show("[b]— THE FIRST CENTURY —[/b]", *self.century.state.log)
        self.refresh_century()

    def refresh_century(self) -> None:
        c = self.century
        assert c
        if c.phase == CY.DONE:
            self.finish_century()
        elif c.phase == CY.DIRECTIVE:
            options = [{"label": d["label"], "do": (lambda i=d["id"]: self.direct(i))}
                       for d in c.directive_options()]
            self.set_options(options, f"Year {c.state.year} — one word from me.")
        else:
            options = [{"label": c.choice_label(ch), "do": (lambda i=i: self.decide(i))}
                       for i, ch in enumerate(c.choices())]
            self.set_options(options, "")

    def direct(self, directive_id: str) -> None:
        self.show(*self.century.do_directive(directive_id))
        self.refresh_century()

    def decide(self, index: int) -> None:
        self.show(*self.century.resolve_choice(index))
        self.refresh_century()

    def finish_century(self) -> None:
        c = self.century
        assert c
        path = f"colony_{c.seed}.json"
        with open(path, "w", encoding="utf-8") as fh:
            import json
            json.dump(c.state.to_dict(), fh, indent=2, ensure_ascii=False)
        self.show("", "[b]— THE HUNDREDTH YEAR —[/b]", "")
        self.show(*c.document())
        self.show("", f"[dim]Chronicle written to {path}.[/dim]")
        self.set_options([{"label": "Quit", "do": self.exit}], "")

    def action_cast(self) -> None:
        c = self.century
        if not c:
            self.show("[dim]Nobody is awake yet.[/dim]")
            return
        self.show("Alive, and known to me:",
                  *(f"{resolve.TABLE} {p.describe(c.state.year)}"
                    for p in c.state.living()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--arrival", help="skip the voyage: play the century from "
                                      "an arrival_<seed>.json")
    args = ap.parse_args()
    arrival = None
    if args.arrival:
        import json
        with open(args.arrival, encoding="utf-8") as fh:
            arrival = json.load(fh)
    Voyage(seed=args.seed, arrival=arrival).run()


if __name__ == "__main__":
    main()
