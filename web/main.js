// Loads the Python engine into Pyodide and draws whatever bridge.py returns.
// No game logic here: every click goes to session.Session and back.

const ENGINE = ["century", "colony", "constants", "deck", "history", "planets",
                "readout", "resolve", "session", "state"];
const CONTENT = ["colony", "colony_flavour", "documents", "endings", "flavour",
                 "history", "voyage"];
const KEYS = "123456789abcdefghij";      // the same keycaps as the terminal
const SAVES = "/saves";                  // arrivals and chronicles, kept in IndexedDB

const $ = (id) => document.getElementById(id);
const quiet = matchMedia("(prefers-reduced-motion: reduce)");
let py, bridge, optionCount = 0;

async function boot() {
  const status = $("boot-status");
  try {
    py = await loadPyodide();
    status.textContent = "Reading the archive.";
    await install("/app", "../", ENGINE.map((m) => `${m}.py`));
    await install("/app/content", "../content/", CONTENT.map((c) => `${c}.json`));
    await install("/app", "./", ["bridge.py"]);

    py.FS.mkdirTree(SAVES);
    py.FS.mount(py.FS.filesystems.IDBFS, {}, SAVES);
    await new Promise((done) => py.FS.syncfs(true, done));

    py.runPython("import sys; sys.path.insert(0, '/app')");
    bridge = py.pyimport("bridge");
    $("boot").remove();
    draw(bridge.boot(SAVES));
  } catch (err) {
    status.textContent = `The engine did not load: ${err.message}. ` +
      "Serve the repository root over HTTP (python -m http.server) and open /web/.";
    status.className = "bad";
    throw err;
  }
}

async function install(dir, base, names) {
  py.FS.mkdirTree(dir);
  await Promise.all(names.map(async (name) => {
    const response = await fetch(base + name);
    if (!response.ok) throw new Error(`${base}${name} answered ${response.status}`);
    py.FS.writeFile(`${dir}/${name}`, await response.text());
  }));
}

function draw(json) {
  const update = JSON.parse(json);
  const log = $("log");
  if (update.clear) log.replaceChildren();

  let first = null;
  for (const block of update.blocks) {
    if (!block.lines.some(([, html]) => html)) continue;
    const section = place(log, block.kind);
    for (const [kind, html] of block.lines) {
      if (!html) continue;
      const p = document.createElement(
        kind === "heading" ? "h2" : kind === "survey" ? "div" : "p");
      if (kind) p.className = kind;
      p.innerHTML = html;
      section.append(p);
      first ??= p;
    }
  }

  document.body.dataset.act = update.act;
  $("telemetry").innerHTML = update.rail;
  $("vitals").innerHTML = update.vitals;
  $("cmd-planets").hidden = !update.surveyed || update.landed;
  $("cmd-cast").hidden = !update.landed;
  $("prompt").innerHTML = update.prompt;
  $("prompt").hidden = !update.prompt;

  const list = $("choices");
  list.replaceChildren(...update.options.map((label, i) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.index = i;
    button.innerHTML = `<kbd>${KEYS[i]}</kbd><span>${label}</span>`;
    item.append(button);
    return item;
  }));
  optionCount = update.options.length;

  // New text is read from its top, not its bottom.
  first?.scrollIntoView({ block: "start", behavior: quiet.matches ? "auto" : "smooth" });
  if (update.saved) py.FS.syncfs(false, () => {});
}

// The closing document reads as one sheet, however many blocks it arrives in.
function place(log, kind) {
  const last = log.lastElementChild;
  if (kind === "document" && last?.classList.contains("document")) return last;
  const section = document.createElement(kind === "document" ? "article" : "section");
  section.className = `block ${kind}`;
  log.append(section);
  return section;
}

function choose(index) {
  if (!bridge || index >= optionCount) return false;
  draw(bridge.choose(index));
  return true;
}

function command(name) {
  if (bridge) draw(bridge.command(name));
}

$("choices").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) choose(Number(button.dataset.index));
});

document.querySelector(".commands").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button) command(button.dataset.command);
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest("input, textarea")) return;
  const index = KEYS.indexOf(event.key);
  if (index >= 0 && choose(index)) return event.preventDefault();
  if (event.key === "p" && !$("cmd-planets").hidden) command("planets");
  if (event.key === "c" && !$("cmd-cast").hidden) command("cast");
});

// On a narrow screen the rail folds into the vitals strip; on a wide one it
// must be open, since its toggle is hidden there. Follows resizes and zoom.
const narrow = matchMedia("(max-width: 52rem)");
const fit = () => { $("rail").open = !narrow.matches; };
narrow.addEventListener("change", fit);
fit();

boot();
