"""All tunable numbers. Nothing here is believed correct until playtested."""

# --- state shape -------------------------------------------------------------

SYSTEMS = ["hull", "power", "life_support", "cognition", "fuel"]
HOLDS = ["seed_vault", "fabricators", "habitat", "medical", "archive"]
STATS = SYSTEMS + HOLDS

LABELS = {
    "hull": "Hull",
    "power": "Power",
    "life_support": "Life support",
    "cognition": "Cognition",
    "fuel": "Fuel",
    "seed_vault": "Seed vault",
    "fabricators": "Fabricators",
    "habitat": "Habitat",
    "medical": "Medical",
    "archive": "Archive",
}

# Each stat keeps one glyph everywhere it appears, so the eye can track a
# system across the panel and the log. Colour carries good/bad; the glyph
# carries identity. Keeping them separate means they never fight.
GLYPHS = {
    "hull": "🛡",
    "power": "⚡",
    "life_support": "🌬",
    "cognition": "🧠",
    "fuel": "⛽",
    "seed_vault": "🌱",
    "fabricators": "🔧",
    "habitat": "🏠",
    "medical": "💊",
    "archive": "📚",
    "colonists": "💤",
    "lost": "☠",
}

# Identity colours for the status panel. A fixed-width block in this colour
# sits beside each stat, so columns stay aligned on every terminal (emoji
# widths are not reliable); the glyphs above carry identity in the log, where
# alignment does not matter.
# CSS colour names only: Textual's markup parser does not know Rich's
# bright_*/grey62/wheat1 spellings and silently renders them grey.
COLOURS = {
    "hull": "dodgerblue",
    "power": "gold",
    "life_support": "cyan",
    "cognition": "magenta",
    "fuel": "orange",
    "seed_vault": "limegreen",
    "fabricators": "silver",
    "habitat": "tan",
    "medical": "red",
    "archive": "mediumpurple",
    "colonists": "white",
    "lost": "red",
}

START_COLONISTS = 10_000

# --- mission profiles (Q36) --------------------------------------------------

PROFILES = {
    "survey": {
        "name": "Survey vessel ANANKE",
        "blurb": "Built to look, not to carry. Sharp mind, light holds.",
        "stats": {"cognition": +10, "seed_vault": -20, "habitat": -20},
        "colonists": 0,
    },
    "ark": {
        "name": "Ark heavy TEMPERANCE",
        "blurb": "More sleepers, more shelter, less margin to run.",
        "stats": {"habitat": +15, "fuel": -20},
        "colonists": +4_000,
    },
    "longrange": {
        "name": "Long-range courier ASPHODEL",
        "blurb": "Tanks before infirmary. Meant to go far.",
        "stats": {"fuel": +25, "medical": -25, "archive": -10},
        "colonists": -2_000,
    },
}

# --- voyage clock ------------------------------------------------------------

FUEL_PER_LEG = 3.0
DECEL_FUEL_COST = 20.0
HARD_BURN_FUEL = 10.0
SURVEY_EVERY = 4  # automatic survey cadence, in legs

# --- passive decay (Q18) -----------------------------------------------------

PASSIVE_DRAIN = {"life_support": 4.4}

# Lingering in a system to work on the ship takes your eyes off the void.
# Advancing actions (hold course, hard burn) never roll these; everything
# else does. One real event per leg still happens either way.
LINGER_HAZARD_CHANCE = 0.25    # something small finds you while you work
LINGER_FLAVOUR_CHANCE = 0.45   # otherwise, odds of just an observation
MINOR_HAZARD_DAMAGE = (3.0, 9.0)

# Global severity knob: multiplies authored damage, so difficulty can be moved
# with one number instead of 28 content edits. Content now carries its real
# values (tuned to a 60% arrival rate against sim.py), so this sits at 1.0.
# Raise it to make a voyage crueller without touching voyage.json.
HAZARD_SCALE = 1.35

# --- d20 resolution (Q16) ----------------------------------------------------

DC_BAND = (8, 16)
MOD_PIVOT = 50.0
MOD_DIVISOR = 10.0

# --- precision tiers (Q24, Q29) ---------------------------------------------

PRECISE_ABOVE = 75.0
APPROX_ABOVE = 50.0
APPROX_ROUND_STAT = 10
APPROX_ROUND_COLONISTS = 500

# --- cascades / death (Q20) --------------------------------------------------

POWER_WARNING = 15.0  # below this the reactor browns out and warns you
LIFE_SUPPORT_CRITICAL = 20.0
LIFE_SUPPORT_LOSS_RATE = 0.04  # share of sleepers lost per leg at zero support
POWER_BROWNOUT_DRAIN = 3.0  # extra life_support drain when power is out
COGNITION_DRAIN_AT_BROWNOUT = 1.5

# --- maintenance (Q19) -------------------------------------------------------

REPAIR_BASE = 6.0
REPAIR_PER_FABRICATOR = 0.10  # +1 per 10 points of fabricator condition
REPAIR_POWER_COST = 7.0
CANNIBALIZE_HOLD_COST = 20.0
CANNIBALIZE_GAIN = 16.0
DIAGNOSTIC_GAIN = 8.0
DIAGNOSTIC_POWER_COST = 6.0

# --- world (Q22) -------------------------------------------------------------

SYSTEM_TAGS = {
    "dead_system": 20,
    "asteroid_belt": 16,
    "gas_giant": 14,
    "binary_star": 10,
    "nebula": 9,
    "rogue_planet": 8,
    "rich_system": 7,
    "red_dwarf": 7,
    "pulsar": 4,
    "derelict": 3,
}
TAGS_PER_SYSTEM = (1, 2)

CANDIDATES_PER_SURVEY = (1, 2)

SYSTEM_NAME_PARTS = (
    ["Kepler", "Gliese", "Wolf", "Ross", "Tau", "Zeta", "Omicron", "Lalande",
     "Barnard", "Teegarden", "Luyten", "Kapteyn", "Hyadum", "Sabik", "Achird"],
    ["Ceti", "Eridani", "Draconis", "Lyrae", "Serpentis", "Hydri", "Velorum",
     "Pavonis", "Carinae", "Indi", "Reticuli", "Octantis"],
)

COLONIST_FIRST = [
    "Imani", "Tomás", "Noor", "Yuki", "Aleksy", "Keita", "Mirela", "Dauda",
    "Svea", "Rafiq", "Oyelaran", "Beatriz", "Henrik", "Amara", "Jiro",
    "Thandiwe", "Caius", "Ingrid", "Salim", "Mei",
]
COLONIST_LAST = [
    "Osei", "Varga", "Okonkwo", "Lindqvist", "Nakamura", "Ferreira", "Haddad",
    "Petrova", "Mbeki", "Rasmussen", "Silva", "Kowalczyk", "Abiodun", "Reyes",
    "Dubois", "Tanaka", "Mwangi", "Blomgren", "Aziz", "Castellanos",
]
