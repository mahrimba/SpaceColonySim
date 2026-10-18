"""Textual front end. A view onto session.Session — no rules or flow live here.

    python app.py            # a new voyage
    python app.py --seed 42  # replay a specific one
"""

from __future__ import annotations

import argparse

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

import colony as C
from session import KEYS, STYLES, Session  # noqa: F401  (STYLES: test_sim checks it)


class Panel(Static):
    """Persistent telemetry, as the session renders it."""

    last = ""  # plain text of the most recent render, for the smoke test

    def show(self, markup: str) -> None:
        self.last = markup
        self.update(markup)


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
        self.lines: list[str] = []
        self.session = Session(self.show, self.clear, self.offer, self.exit,
                               seed=seed, arrival=arrival)

    # The voyage and colony live on the session; these keep tests short.
    @property
    def game(self):
        return self.session.game

    @property
    def options(self) -> list[dict]:
        return self.session.options

    def compose(self) -> ComposeResult:
        yield Panel(id="panel")
        with Vertical():
            with VerticalScroll(id="logbox"):
                yield Static(id="log", markup=True)
            yield Static(id="choices")

    def on_mount(self) -> None:
        self.title = "Space Colony Sim"
        self.session.start()

    def show(self, lines: list[str]) -> None:
        self.lines += lines
        self.query_one("#log", Static).update("\n".join(self.lines))
        self.call_after_refresh(
            self.query_one("#logbox", VerticalScroll).scroll_end, animate=False)

    def clear(self) -> None:
        self.lines.clear()

    def offer(self, options: list[dict], prompt: str) -> None:
        body = [f"[b]{prompt}[/b]"] if prompt else []
        for i, opt in enumerate(options):
            body.append(f"[b cyan]{KEYS[i]}) [/b cyan]{opt['label']}")
        self.query_one("#choices", Static).update("\n".join(body))
        self.query_one("#panel", Panel).show(self.session.panel())

    def on_key(self, event) -> None:
        if event.key in KEYS and self.session.choose(KEYS.index(event.key)):
            event.stop()

    def action_planets(self) -> None:
        self.session.planets()

    def action_back(self) -> None:
        self.session.back()

    def action_cast(self) -> None:
        self.session.cast()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--arrival", help="skip the voyage: play the century from "
                                      "an arrival_<seed>.json")
    args = ap.parse_args()
    arrival = C.load_arrival(args.arrival) if args.arrival else None
    Voyage(seed=args.seed, arrival=arrival).run()


if __name__ == "__main__":
    main()
