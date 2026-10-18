"""The game's flow, for any front end: what to show, what to offer, what each
option does. No rules live here (those are resolve.Game and century.Century),
and no widgets either: a front end passes three callables and renders
whatever markup comes back. app.py is the terminal; web/ is the browser.

Lines and labels carry Rich-style markup ([b], [dim], [i], a colour name).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

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


def style(line: str) -> str:
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
                        f"[{S[key]}]{verdict}[/{S[key]}]")
        return f"[{S['roll']}]{line}[/{S['roll']}]"

    # The closing document: headings stand out, quoted records indent.
    # Spaces go inside the tag; Textual's markup eats them outside it.
    if line.isupper() and 0 < len(line) < 70:
        return f"[{S['leg']}]{line}[/{S['leg']}]"
    if line.startswith("  Decision: "):
        return f"[{S['choice']}]    {line.strip()}[/{S['choice']}]"
    if line.startswith("  "):
        return f"[i]    {line.strip()}[/i]"

    return line


class Session:
    """One sitting at the game: a voyage, perhaps a century, and the ways out.

    show(lines) appends styled lines to the log; clear() empties it;
    offer(options, prompt) replaces the choices, each a {"label", "do"};
    quit() ends the program.
    """

    HELP = "Number keys choose. p reads the surveyed worlds. m steps back. q quits."

    def __init__(self, show, clear, offer, quit, seed: int | None = None,
                 arrival: dict | None = None, saves: Path | None = None):
        self._show, self._clear, self._offer, self.quit = show, clear, offer, quit
        self.seed = seed
        self.arrival = arrival
        self.saves = saves or Path.cwd()
        self.century: CY.Century | None = None
        self.game: Game | None = None
        self.options: list[dict] = []
        self.prompt = ""
        self.profile: str | None = None      # what to retry, if asked
        self.landed: dict | None = None

    def start(self) -> None:
        self.intro()
        if self.arrival is not None:
            self.begin_century(self.arrival)
        else:
            self.offer_profiles()

    def intro(self) -> None:
        self.show("[b]COLONY MISSION — INTELLIGENCE ONLINE[/b]",
                  "",
                  "Ten thousand people are asleep behind me. I am the only thing "
                  "awake, and the only thing that decides.",
                  "",
                  f"[dim]{self.HELP}[/dim]")

    def reset(self) -> None:
        """A clean slate: no ship, no colony, an empty log."""
        self.game = None
        self.century = None
        self._clear()
        self.intro()

    def end_options(self, retry_label: str, retry) -> list[dict]:
        """Every end screen offers the same three ways out."""
        return [{"label": f"[b]Retry[/b] — {retry_label}", "do": retry},
                {"label": "[b]New game[/b] — a new hull, a new sky", "do": self.new_game},
                {"label": "Quit", "do": self.quit}]

    def new_game(self) -> None:
        self.seed = None        # a fresh voyage, not a replay of the last one
        self.reset()
        self.offer_profiles()

    def retry_voyage(self, profile: str, seed: int) -> None:
        self.seed = seed
        self.reset()
        self.launch(profile)

    def retry_century(self, arrival: dict, seed: int) -> None:
        self.seed = seed
        self.reset()
        self.begin_century(arrival)

    # -- option plumbing ------------------------------------------------------

    def show(self, *lines: str) -> None:
        self._show([style(line) for line in lines] + [""])

    def set_options(self, options: list[dict], prompt: str = "") -> None:
        self.options, self.prompt = options, prompt
        self._offer(options, prompt)

    def choose(self, index: int) -> bool:
        if 0 <= index < len(self.options):
            self.options[index]["do"]()
            return True
        return False

    def panel(self) -> str:
        """Persistent telemetry, as markup. Precision is the ship's problem,
        not the view's."""
        if self.century is not None:
            return self._panel_colony(self.century)
        return self._panel_voyage(self.game)

    @staticmethod
    def _panel_colony(century_game) -> str:
        s = century_game.state
        rows = [f"[b]{s.name}[/b]", f"[dim]{s.ship_role}[/dim]"]
        features = [planets.MODIFIERS[m].name for m in C.planet_features(s.planet)]
        if features:
            rows.append(f"[dim]{', '.join(features)}[/dim]")
        rows.append("")
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
        return "\n".join(rows)

    @staticmethod
    def _panel_voyage(game: Game | None) -> str:
        if game is None:
            return "[dim]No ship underway.[/dim]"
        s = game.state
        rows = [f"[b]{s.name}[/b]", f"[dim]seed {game.seed}[/dim]", ""]
        rows.append(f"Leg [b]{s.leg}[/b]")
        if s.system_name:
            tags = ", ".join(sorted(t.replace("_", " ") for t in s.system_tags))
            rows.append(f"{s.system_name}")
            rows.append(f"[dim]{tags}[/dim]")
        rows.append("")
        for stat in K.SYSTEMS:
            rows.append(Session._row(s, stat))
        rows.append("")
        rows.append("[dim]HOLDS[/dim]")
        for hold in K.HOLDS:
            rows.append(Session._row(s, hold))
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
        return "\n".join(rows)

    @staticmethod
    def _row(s, stat: str) -> str:
        """Identity colour in the block, condition colour in the number."""
        colour = K.COLOURS[stat]
        value = s.stats[stat]
        tone = "green" if value > 60 else ("yellow" if value > 30 else "red")
        return (f"[{colour}]█ [/{colour}]{K.LABELS[stat]:<13}"
                f"[{tone}]{s.say(stat)}[/{tone}]")

    # -- launch ---------------------------------------------------------------

    def offer_profiles(self) -> None:
        options = []
        for key, spec in K.PROFILES.items():
            options.append({
                "label": f"{spec['name']} — {spec['blurb']}",
                "do": (lambda k=key: self.launch(k)),
            })
        # Previous voyages that actually reached a world can be landed again.
        for path in sorted(self.saves.glob("arrival_*.json"))[-4:]:
            arrival = C.load_arrival(path)
            if arrival.get("outcome") != "colonized":
                continue
            world = (arrival.get("planet") or {}).get("name", "a world")
            options.append({
                "label": f"[b]Begin a century on {world}[/b] — "
                         f"{arrival.get('colonists_alive', 0):,} asleep, "
                         f"from {path.name}",
                "do": (lambda a=arrival: self.begin_century(a)),
            })
        self.set_options(options, "Which hull am I?")

    def launch(self, profile: str) -> None:
        self.profile = profile
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
            if opt["action"] in ("repair", "cannibalize"):
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

    def planets(self) -> None:
        game = self.game
        if not game or not game.state.candidates:
            self.show("[dim]Nothing surveyed yet.[/dim]")
            return
        self.show("Everything I have surveyed so far:",
                  *(f"{resolve.TABLE} {row}"
                    for row in planets.table(game.state.candidates)))

    def back(self) -> None:
        if self.game and self.game.phase == MAINTENANCE and self.century is None:
            self.offer_maintenance()

    def finish(self) -> None:
        game = self.game
        assert game
        path = self.saves / f"arrival_{game.seed}.json"
        game.state.dump(str(path))
        self.show("", "[b]— END OF VOYAGE —[/b]", *game.report(), "",
                  f"[dim]State written to {path.name}.[/dim]")
        options = []
        if game.state.outcome == "colonized":
            options.append({"label": "[b]Begin the first century[/b]",
                            "do": lambda: self.begin_century(game.state.to_dict())})
        profile, seed = self.profile, game.seed
        options += self.end_options("the same hull, the same voyage",
                                    lambda: self.retry_voyage(profile, seed))
        self.set_options(options, "")

    # -- act two ---------------------------------------------------------------

    def begin_century(self, arrival: dict) -> None:
        self.landed = copy.deepcopy(arrival)
        self.century = CY.Century(arrival, seed=self.seed)
        self.show("", "[b]— THE FIRST CENTURY —[/b]", *self.century.state.log)
        self.refresh_century()

    def refresh_century(self) -> None:
        c = self.century
        assert c
        if c.phase == CY.DONE:
            self.finish_century()
            return
        options = [{"label": c.choice_label(ch), "do": (lambda i=i: self.decide(i))}
                   for i, ch in enumerate(c.choices())]
        self.set_options(options, "")

    def decide(self, index: int) -> None:
        self.show(*self.century.resolve_choice(index))
        self.refresh_century()

    def finish_century(self) -> None:
        c = self.century
        assert c
        path = self.saves / f"colony_{c.seed}.json"
        path.write_text(json.dumps(c.state.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        header = ("— THE HUNDREDTH YEAR —" if c.state.year >= CY.CENTURY
                  else f"— YEAR {c.state.year}: THE END OF IT —")
        self.show("", f"[b]{header}[/b]", "")
        self.show(*c.document())
        self.show("", f"[dim]Chronicle written to {path.name}.[/dim]")
        arrival, seed = self.landed, c.seed
        self.set_options(self.end_options("the same landing, the same world",
                                          lambda: self.retry_century(arrival, seed)), "")

    def cast(self) -> None:
        c = self.century
        if not c:
            self.show("[dim]Nobody is awake yet.[/dim]")
            return
        self.show("Alive, and known to me:",
                  *(f"{resolve.TABLE} {p.describe(c.state.year)}"
                    for p in c.state.living()))
