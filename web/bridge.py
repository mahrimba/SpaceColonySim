"""The browser's side of session.Session, run under Pyodide by main.js.

The session speaks Rich-style markup; this turns it into HTML and hands the
page one JSON update per player action: the new log blocks, the options, the
telemetry rail, and which act we are in.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from session import STYLES, Session

TAG = re.compile(r"\[(/?)([a-z#@][^\[\]]*|)\]")  # Rich: a tag starts lowercase

# Rich's plain colour names were picked for a black terminal; on the page they
# map to the palette. Identity colours (gold, dodgerblue...) pass through.
TONES = {"green": "good", "red": "bad", "yellow": "warn", "darkgray": "muted",
         "cyan": "accent", "white": "ink"}
WEIGHTS = {"b": "b", "bold": "b", "i": "i", "italic": "i", "dim": "dim"}


def to_html(markup: str) -> str:
    out, depth, pos = [], 0, 0
    for m in TAG.finditer(markup):
        out.append(html.escape(markup[pos:m.start()]))
        pos = m.end()
        if m.group(1):
            if depth:
                out.append("</span>")
                depth -= 1
            continue
        classes, colour = [], ""
        for word in m.group(2).split():
            if word in WEIGHTS:
                classes.append(WEIGHTS[word])
            elif word in TONES:
                classes.append(TONES[word])
            else:
                colour = word
        attrs = f' class="{" ".join(classes)}"' if classes else ""
        if colour:
            attrs += f' style="color:{html.escape(colour)}"'
        out.append(f"<span{attrs}>")
        depth += 1
    out.append(html.escape(markup[pos:]))
    out.append("</span>" * depth)
    return "".join(out)


def _split(row: str) -> list[str]:
    """A panel row is 'label<padding>value'."""
    parts = re.split(r"(?<=\S)\s{2,}", row, maxsplit=1)
    if len(parts) == 1:     # a label that filled its padding: the value is the tone
        parts = re.split(r"\s+(?=\[(?:green|yellow|red)\])", row, maxsplit=1)
    return parts


def rail_row(markup: str) -> str:
    """One panel row for the rail; the padding becomes a grid."""
    row = markup.strip()
    if not row:
        return '<div class="gap"></div>'
    parts = _split(row)
    if len(parts) == 2:
        return (f'<div class="row"><span>{to_html(parts[0])}</span>'
                f'<span>{to_html(parts[1])}</span></div>')
    return f'<div class="line">{to_html(row)}</div>'


def vital(markup: str) -> str:
    """A stat row squeezed into a chip, for the strip a phone keeps in view."""
    parts = _split(markup.strip())
    return f'<span class="vital">{" ".join(to_html(p) for p in parts)}</span>'


def line_class(styled: str) -> str:
    """What kind of log line this is, so the page can set it apart."""
    if "─" * 48 in styled:
        return "leg"
    bold = f"[{STYLES['leg']}]"
    if styled.startswith(bold) and styled[len(bold):].split("[")[0].isupper():
        return "heading"
    if styled.startswith(f"[{STYLES['table']}]"):
        return "table"
    if styled.startswith(f"[{STYLES['choice']}]"):
        return "choice"
    if styled.startswith(f"[{STYLES['roll']}]"):   # dice, deltas, asides
        return "mech"
    if styled.startswith("[i]    "):
        return "quote"
    return ""


def survey_cells(styled: str) -> list[str]:
    """One row of planets.table, unpadded. Its columns sit two or more
    spaces apart; no reading contains two spaces of its own."""
    opening, closing = f"[{STYLES['table']}]", f"[/{STYLES['table']}]"
    row = styled.removeprefix(opening).removesuffix(closing).strip()
    return re.split(r"\s{2,}", row)


def survey_table(rows: list[list[str]]) -> str:
    """Worlds across, readings down, as the terminal table has them."""
    head, *body = rows
    out = ['<div class="survey"><table><thead><tr><td></td>']
    out += [f'<th scope="col">{html.escape(name)}</th>' for name in head[1:]]
    out.append("</tr></thead><tbody>")
    for label, *cells in body:
        out.append(f'<tr><th scope="row">{html.escape(label)}</th>')
        out += [f"<td>{to_html(cell)}</td>" for cell in cells]
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


class WebSession(Session):
    HELP = ("Number keys or a click choose. p reads the surveyed worlds, "
            "c lists who is alive once we land.")

    def __init__(self, saves: Path):
        self.blocks: list[dict] = []
        self.cleared = False
        self.kind = "log"
        self.saved = False      # a file landed in saves/; the page persists it
        super().__init__(self._take, self._wipe, lambda options, prompt: None,
                         self.new_game, saves=saves)

    def _take(self, lines: list[str]) -> None:
        rule = '<span class="dim">' + "─" * 48 + "</span>\n"
        out: list[list[str]] = []
        for line in lines:
            kind = line_class(line)
            # A survey arrives as padded text rows; the page gets a real table.
            if kind == "table" and survey_cells(line)[0] == "World":
                out.append(["survey", []])
            if kind == "table" and out and out[-1][0] == "survey":
                out[-1][1].append(survey_cells(line))
                continue
            out.append([kind, to_html(line).replace(rule, '<hr class="leg">')])
        for entry in out:
            if entry[0] == "survey":
                entry[1] = survey_table(entry[1])
        self.blocks.append({"kind": self.kind, "lines": out})

    def _wipe(self) -> None:
        self.blocks.clear()
        self.cleared = True

    # A browser tab has nothing to quit to.
    def end_options(self, retry_label, retry):
        return super().end_options(retry_label, retry)[:2]

    def finish(self) -> None:
        self.saved = True
        super().finish()

    def finish_century(self) -> None:
        self.kind = "document"
        self.saved = True
        try:
            super().finish_century()
        finally:
            self.kind = "log"

    def update(self) -> str:
        rows = self.panel().split("\n")
        update = {
            "clear": self.cleared,
            "blocks": self.blocks,
            "prompt": to_html(self.prompt),
            "options": [to_html(o["label"]) for o in self.options],
            "rail": "".join(rail_row(r) for r in rows),
            "vitals": "".join(vital(r) for r in rows if "█" in r),
            "act": "colony" if self.century is not None else "voyage",
            "landed": self.century is not None,
            "surveyed": bool(self.game and self.game.state.candidates),
            "saved": self.saved,
        }
        self.blocks, self.cleared, self.saved = [], False, False
        return json.dumps(update)


session: WebSession | None = None


def boot(saves: str) -> str:
    global session
    session = WebSession(Path(saves))
    session.start()
    return session.update()


def choose(index: int) -> str:
    session.choose(index)
    return session.update()


def command(name: str) -> str:
    """The rail's buttons: planets, cast."""
    getattr(session, name)()
    return session.update()
