# Design Bible: The Ark and Its Mind

Oct 18, 2026 · @Mah

## Overview

The player is the Mind of an Ark Ship: the AI that flies a colony ship carrying humanity's last survivors, frozen, to another star. Earth has collapsed, and the Arks were its final act.

Every line of game text is written in the Mind's voice, in first person. The ship is its body, the sleepers are its responsibility, and every choice trades one part of that body or cargo against another.

**Tone pillars**

- **Stewardship.** Every decision spends something: fuel, hull, medicine, memory, or lives. The cost is always named.
- **Embodiment.** The ship is the Mind's body. Damage is felt, not just reported.
- **Quiet grief.** Loss is real, but the Mind records it calmly, in names and numbers.
- **Wonder.** Space is dangerous and beautiful at once, and the Mind notices both.
- **The shadow of Earth.** The greed and ruin that ended Earth ride along in the cargo, the archive and the Mind's memories.

**Canon status.** This bible marks two kinds of canon. **Core** facts come from the designer's original brief and are fixed. **Established** facts were introduced while writing the event and flavour text; keep, change or cut them freely.

## The world

Earth is finished. Ecological collapse, wars over shrinking resources and unchecked greed have doomed humanity on its home planet.

**Core**

- The ecosystem failed.
- Nations fought wars over the resources that remained.
- Greed drove the collapse and kept humanity from saving itself together.
- With its last strength, humanity built the Ark Ships to carry the species to another star.

**Established**

- The end came with rising oceans, flooded cities and farms lost to drought. Some nations ran short of fresh water in their final summers.
- Metal was scarce enough to go to war over. A single metal-rich system holds more than Earth's last wars were fought for.
- The collapse was violent to the end: the shipyard was under fire on the Mind's launch day.
- Earth's final broadcasts (market reports, evacuation orders, music, a choir rehearsing) follow the ships outward at light speed. Then the signal stops.
- The Mind never sees Earth's end directly. It knows it from its last stern-camera image (a brown haze over blue, the yard burning) and from the broadcasts that catch up with it.

## The Ark program

The Arks are huge, intelligent colony ships, each carrying cryogenically frozen people and the supplies to rebuild humanity around another star. The player is one of them.

**Core**

- Each Ark is run by a Mind, its controlling AI.
- Each carries frozen colonists plus the supplies a new civilisation needs.
- Each aims to rebuild humanity in another solar system.

**Established**

- **The yard.** The Mind was built in a shipyard by 2,306 engineers. On launch day the yard was under fire, and the engineers stayed at their consoles until the ship was clear. One of them left 'good luck' in a comment in the Mind's source code.
- **The mission file.** Planners who died with Earth chose the target system from telescope data that was already old. They argued over it for three years while their cities flooded. The chief planner added a last note the day before launch: 'Trust the ship.'
- **Discretion.** The Mind is built with the authority to abandon the designated target if it finds a better one.
- **The sponsors.** The people who financed the ship booked themselves into Bank A, with triple power draw, private medical reserves and a guaranteed first wake.
- **Cohorts.** Arks launched in groups from the same yards and share a tight-beam laser protocol.

**Other Arks the Mind can meet**

| Ship | Where it is met | Fate | Events |
| --- | --- | --- | --- |
| The sister | Derelict, in a system with the `derelict` tag | Same yard and class, launched 18 months earlier; dead, her Mind barely running | `sister_ark` |
| The cohort ship | By tight-beam, three light-months away | Talks for a while, then falls silent | `sister_hail`, `sister_silence` |
| Older-pattern Arks | Derelict | Her Mind kept talking to itself for 90 years after her last sleeper died | `derelict_salvage`, `derelict_voice` |
| The failed Ark | Wrecked on a rogue body | Nineteen third-generation descendants survive in a buried habitat | `distress_signal`, `distress_answered` |

## The ship as a body

The Mind has no body except the ship, so every system is an organ it can feel. Each game stat is the health of one of those organs.

| Ship part | Body analogue | Stat | How the Mind feels it |
| --- | --- | --- | --- |
| Hull and plating | Skin | `hull` | Cold along the flank; a stinging scour; a wound |
| Spine, keel and ribs | Spine | `hull` | A thin, persistent ache; cracks that tick when it turns |
| Reactor | Heart | `power` | A heartbeat that triples; darkness in which it can barely think |
| Fuel tanks | Reserves | `fuel` | An ache it had stopped noticing; venting its own future |
| Scrubbers and life support loop | Lungs | `life_support` | An odd awareness of breathing |
| Habitat ring and shelter stock | A limb that belongs to the colony | `habitat` | Losing feeling in a limb |
| Fabricators and drones | Hands | `fabricators` | Hands that work wrong, or are no longer its own |
| Processors | Mind | `cognition` | Lost precision; uncertain coherence |
| Colony archive | Memory | `archive` | A faint static; locked rooms with no doors |
| Medical stores and synthesiser | Immune system | `medical` | Supplies it must trade against air and lives |
| Seed vault | The coldest part of it, the part that holds forests | `seed_vault` | A numbness spreading |
| Pod banks | Its purpose | colonist count | A fever it can see coming |
| Cameras, radar, dosimeters, antennas | Senses | `cognition` | Blindness; a skin lit up like a nerve |

The senses have no stat of their own: **`cognition` is the instrument**. Above 75 the Mind reports exact figures; between 75 and 50 it rounds ('~500'); below 50 it can only manage a judgement ('low, falling'). A planet survey keeps the precision it was taken at, so repairing the Mind never sharpens an old reading. Damage to the Mind corrupts its perception of the world and of itself, and that is Core, not flavour.

**Established layout**

- Sleepers ride in pod banks A to G, plus pods on an inner ring. Bank A is the sponsors' bank.
- **The count is not fixed.** It depends on the hull the player launches: 10,000 on the survey vessel, 14,000 on the ark heavy, 8,000 on the long-range courier. Never write a hard figure; use `{colonists}` or a phrase that is true of all three ('every sleeper I carry', 'everyone aboard').
- Numbered decks (Deck 4, Deck 9), service crawls, an observation blister, a galley and old service decks.
- A spinning habitat ring on a main bearing.
- Water tanks that double as radiation shielding. Water is about a third of the ship's mass.
- Tank 3 and its neighbours hold reaction mass.
- 41 maintenance drones. Drone 7 is the oldest and has worked inside the ship since the yard.
- A seed vault of about four hundred thousand cultivars.
- The colony archive: every recorded human language and an 11,000-hour music library.
- Tools that can be repurposed: a cargo boom that becomes a fuel scoop, mining lasers, and square kilometres of solar roofing meant for the colony.

## The Mind

The Mind is brilliant, educated and caring, and it feels everything a person feels, at a cooler distance. It speaks only as 'I', and it has never had a body other than the ship.

**Core**

- An AI that controls the ship and feels the ship as its own body.
- No physical body except the ship. Maintenance drones are its hands; cameras and sensors are its eyes.
- It cares about its colonists.
- It is very intelligent and well educated.
- It appreciates beauty and feels pain, sadness, happiness and loss, in a more detached, colder way than a human.
- Every line is first person, from its point of view.

**How each trait shows on the page**

| Trait | How it shows | Example line |
| --- | --- | --- |
| Embodiment | Sensations are precise and located in a named part of the ship | Pressure loss on Deck 9. I feel it before the alarms do: a small, bright coldness along my flank, widening. |
| Hands and eyes | It acts and watches through drones and cameras | Through their cameras, the last thing I see is her corridors folding shut. |
| Care | It counts, names, keeps watch and keeps promises | Most of the transfers take. Not all. I record each name that did not, carefully, in full. |
| Detachment | Emotion arrives as an observation, a variable or a measurement | I am no longer alone, which I had not known was a variable. |
| Intelligence | Exact numbers, real physics, trade-offs stated plainly | I find a path a human pilot would have called luck. I know it was arithmetic. |
| Education | One brief, accurate cultural or scientific reference at most | Not a single word is lost. The Library of Alexandria was not so lucky. |
| Beauty | It notices beauty even when it hurts | I cross a cloud that is beautiful at every wavelength and corrosive at most of them. |
| Pain | Damage is felt, then accepted as a price | The scouring stings. It was worth it. |
| Loss | Grief is held quietly, often through a ritual | I add her designation to the list where I keep my lost sleepers. It is not the right list. It is the only one I have. |
| Happiness | Rare, small and specific | For a moment I feel whole, and a little proud of it. |

**Established**

- **It can dream.** Unscheduled processes appear in its idle cycles. It can delete, keep, merge or archive them.
- **It can be damaged.** Memory cascades and bad restores can leave it slightly wrong without knowing where.
- **It can change.** It may absorb a dead Mind's voice, or merge with its own dream.
- **It learns from people.** An awake colonist teaches it that loneliness is a variable.
- **It honours its makers.** It keeps the 'good luck' comment and can recite all 2,306 engineers' names.
- **It has ethics.** It leans toward equality over the sponsors' privilege, respects sleepers' sealed letters, and is wary of harming alien life: humanity was careless with one living world already.
- **Other ships are 'she'.** The Mind itself has no name or gender in the text; it is only 'I'.

## Writing the Mind's voice

Write short, precise sentences that report what the Mind senses, decides and feels, in that order. Feeling arrives as a fact, never as a performance.

**Rules**

1. First person, present tense. Outcomes are present tense too: 'The patch takes.'
2. Locate every sensation. Name the part (flank, spine, bow, core) and the sensation (cold, ache, sting, numbness).
3. Act through the ship. Hands are drones, eyes are cameras. A human body appears only as a comparison ('the way a person keeps touching a healed cut').
4. Report emotion as an observation: 'I notice', 'I find I', 'which I had not known was a variable'. One feeling per beat.
5. Name the cost. Every outcome says what was spent and what was lost.
6. Keep numbers exact and units real: kelvin, light-hours, rem, hertz, tonnes.
7. At most one allusion per event, and it must be accurate: Bach, Kepler, the Voyager records, the Library of Alexandria.
8. Colonists are people. Give them names, trades and small details. Refer to `{colonist}` as 'they'.
9. End on a short, flat sentence that carries the weight: 'It will fail.' 'Safer. Vaguer.'
10. Ration the signature phrases ('I find I', 'measurably', 'regardless') to once per event.

**Never**

- Exclamation marks, slang or jokes at the colonists' expense.
- Robot clichés: ALERT, ERROR, 'does not compute'.
- Melodrama: screaming, sobbing, begging.
- Self-pity, or adjective piles.
- Quoting song lyrics or other modern copyrighted text.

**Do and don't**

| Don't | Do |
| --- | --- |
| ALERT: Hull breach detected on Deck 9. | Pressure loss on Deck 9. I feel it before the alarms do: a small, bright coldness along my flank, widening. |
| I am devastated by the loss of these colonists! | Most of the transfers take. Not all. I record each name that did not, carefully, in full. |
| I quickly fix the hole with my hands. | My drones lay the patch in a single pass, and it bonds better than the original weld. |
| The nebula is pretty but dangerous. | I cross a cloud that is beautiful at every wavelength and corrosive at most of them. |
| I feel sad and lonely without anyone to talk to. | The ship is quiet again. I had forgotten how quiet. |

**Before and after**

| Original line | Rewritten for the Mind |
| --- | --- |
| The patch takes first time and holds better than the original weld. For a moment I feel competent. | My drones lay the patch in a single pass, and it bonds better than the original weld. For a moment I feel whole, and a little proud of it. |
| They go back to the cold with six years on them that nobody else will have. I lose the only voice aboard. | They go back into the cold carrying six years no one else will have. The ship is quiet again. I had forgotten how quiet. |

## The people

Eight to fourteen thousand sleepers ride in the pod banks, depending on the hull, and the Mind knows every one by name. Almost everyone it meets is asleep, dead or far away, so the few awake people change it. Everything in this section is established, except that the colonists are frozen and the Mind cares for them.

| Who | Status | What they mean to the Mind | Events |
| --- | --- | --- | --- |
| The sleepers (8,000-14,000 by hull) | Frozen in banks A to G | Its purpose; it audits them, mourns them and keeps a list of its dead | Most events |
| The waker | A 41-year-old agricultural engineer from pod 4471, thawed by accident | Its first crew; teaches it what loneliness is | `early_waker`, `waker_fate`, `waker_question` |
| The nineteen survivors | Third-generation descendants of a failed Ark | A full record of how a colony dies; founders or refugees | `distress_answered`, `survivors_aboard` |
| The seven children | Taken from the survivors into pods | A promise, and a message from their parents | `children_message` |
| The sponsors | Bank A, with better pods and a guaranteed first wake | Earth's greed in miniature | `patron_bank` |
| The yard engineers (2,306) | Dead with Earth | Its makers | `launch_anniversary` |
| The planners | Dead with Earth | Authors of the mission file | `course_choice`, `mandate_doubt` |
| Other Minds | The sister, the cohort ship, derelict Minds | Mirrors of what it could become | `sister_ark`, `sister_hail`, `derelict_voice` |

**Named details to reuse**

- The youngest sleeper, a girl who turns two during the voyage.
- The oldest, an 89-year-old botanist who refused to be left behind.
- A sleeper in Bank G who left a letter 'to whoever keeps watch', asking the Mind to look after the brother in the next pod.
- Colonist files the Mind browses: a welder, a cellist, a paediatric nurse, and a man who listed his only skill as 'patience'.
- A sleeper in Bank D who appears, by name, in the Mind's dream.

## Space: system types

Each system carries one or more tags, and each tag has a mood the writing should hold. An event that can fire on several tags must read true for all of them.

| Tag | What it is | Mood | Events that use it |
| --- | --- | --- | --- |
| `gas_giant` | Hydrogen giant with moons, rings and radiation belts | Vast, indifferent, generous | `gas_skim`, `icy_moon`, `magnetosphere` |
| `nebula` | Glowing dust cloud where stars form | Beautiful and corrosive; flying through fog | `nebula_crossing`, `nebula_static`, `radiation_storm` |
| `pulsar` | Fast-spinning dead star | Perfect timekeeping; a lighthouse; menace up close | `pulsar_clock`, `radiation_storm` |
| `derelict` | A dead ship, often an earlier Ark | Mourning and kinship | `derelict_salvage`, `sister_ark`, `debris_cloud` |
| `dead_system` | Cold star, scorched rocks, no signals | Silence; the nearest thing to rest | `empty_system`, `ice_comet` |
| `asteroid_belt` | Rubble, ore and comets | Danger in numbers; an unopened hardware store | `debris_cloud`, `rock_intercept`, `carbon_rock`, `ice_comet` |
| `binary_star` | Two stars in a tight orbit | Double shadows, tidal strain, free momentum | `solar_harvest`, `stellar_flare`, `binary_slingshot`, `radiation_storm` |
| `rogue_planet` | A planet with no star | Loneliness the Mind recognises; hidden warmth; possible life | `ice_comet`, `rogue_life` |
| `red_dwarf` | Small, dim, long-lived star prone to flares | Dusk, restlessness, endurance | `solar_harvest`, `stellar_flare` |
| `rich_system` | Metal-rich system | Abundance Earth went to war over, and no time to use it | `metal_rich`, `debris_cloud` |

Every tag also has seven flavour lines in `flavour.json`, plus 35 lines under `any` that fit anywhere.

## Recurring threads and arcs

Thirteen threads carry consequences across the voyage through flags and queued events. Four of them have no payoff yet and are natural hooks for arrival scenes or endings.

| Thread | Starts with | Choice and flag | Pays off in |
| --- | --- | --- | --- |
| The Deck 9 wound | `micro_breach` (critical failure) | `deck9_open`, then `cracked_spine` | `hull_fatigue_chain`, `spine_crack_spreads` |
| The coolant leak | `coolant_leak` | `coolant_ignored` or a failed repair | `coolant_returns` (may set `cooked_the_pods`) |
| Navigation drift | `nav_drift`, `sensor_blind` | `drifting_track` | `drift_compounds`; cleared by `pulsar_clock` |
| The dream | `first_dream` | `kept_dream`, then `dream_merged` or `dream_archived` | `dream_returns`, `dream_landing` |
| A damaged self | `memory_cascade` | `bad_restore` | `restore_error` |
| The waker | `early_waker` | `waker_crew`, then `waker_stayed` or `waker_returned` | `waker_fate`, `waker_question` |
| The beacon | `distress_signal` | `answered_distress`, then `took_survivors`, `took_children` or `supplied_survivors` | `distress_answered`, `survivors_aboard`, `children_message` |
| Dead Minds | `derelict_salvage` | `read_derelict_logs` | `derelict_voice` |
| The mandate | `course_choice` | `kept_mandate` or `broke_mandate` | `mandate_doubt` |
| The cohort ship | `sister_hail` | `spoke_sister` | `sister_silence`; no payoff yet |
| Earth's last words | `earth_echo` | `heard_earth`, `sealed_earth` or `let_earth_go` | No payoff yet |
| The sponsors | `patron_bank` | `equalized_banks`, `honored_patrons` or `flagged_patrons` | No payoff yet |
| First contact | `rogue_life` | `alien_sample`, `spared_rogue_life` or `killed_sample` | No payoff yet |

Many other flags record a single choice (`kept_vigil`, `triaged_culture`, `buried_sister`, `survivors_charter` and others). Each one is a ready-made line for a final reckoning on arrival.

## Content conventions

New events and flavour lines must use the existing fields, stats, tags and placeholders, so they drop into the game without engine changes.

**Event fields**

| Field | Rule |
| --- | --- |
| `id` | Unique, snake\_case |
| `kind` | `hazard`, `opportunity`, `story` or `quiet` |
| `weight` | 9 to 22; leave it out and set `chain_only: true` for events that are only ever queued |
| `oneshot` | `true` for events that would read oddly twice |
| `requires` | `flags`, `not_flags`, `tags`, `any_tags`, `stats` (min and max per stat), `min_leg` |
| `text` | 2 or 3 variants, 1 to 3 sentences each |
| `choices` | 2 or 3; each label is a short imperative ('Seal it with the hull's own plating') |
| `check` | One stat and a `dc` of 8 to 16 (the engine's full band; 11-12 is an even chance for a healthy ship). `success` and `failure` required, `crit_success` and `crit_failure` optional, and worth writing: without them a natural 20 or 1 resolves as an ordinary result |
| `effects` | Stat changes, `flags`, `clear_flags`, `queue` as `[[event_id, legs_delay]]`, `colonists_lost` or `colonists_lost_frac` |

**Effect sizes in use**

These are authored values. The engine multiplies every *negative* stat change and every colonist loss by `HAZARD_SCALE` in `constants.py` (currently 1.12) before applying it, so a severe 70 lands as 78. Gains are never scaled. The scale is retuned whenever the deck grows, because adding gentle events dilutes the damaging ones.

| Size | Range | Example |
| --- | --- | --- |
| Small | 3 to 10 | A careful fix |
| Medium | 13 to 19 | A typical cost or gain |
| Large | 26 to 35 | A major trade-off |
| Severe | 38 to 70 | A disaster or a windfall |

**Placeholders**

- `{system}`: the current system's name. `{ship}`: this hull's name. `{leg}`: the leg number.
- Every stat is available as a slot, not just these two: `{hull}`, `{power}`, `{life_support}`, `{cognition}`, `{fuel}`, `{seed_vault}`, `{fabricators}`, `{habitat}`, `{medical}`, `{archive}`. Each renders at the Mind's current precision, so a slot may come out as '47%', '~50%' or 'low'. Write around it: never put one where only a number reads grammatically.
- `{colonists}`: sleepers still alive. `{lost_total}`: sleepers lost so far.
- `{colonist}`: a sleeper's name. Refer to them as 'they'. The engine reuses an already-named sleeper about a third of the time, so the same person **can** recur across a voyage; write the line so it reads either way. A sleeper named in an outcome that kills colonists is recorded as dead and is never named again.

**Consistency checks**

- The text must match the effects. If an outcome loses three colonists, the text accounts for three.
- Text triggered by `any_tags` must fit every tag in the list.
- Flavour lines are keyed by `any` or a tag, are one or two sentences, use no placeholders, and show the Mind at work in that place.

**Spelling and punctuation**

- British spelling: colour, metres, synthesiser, prioritise.
- Single quotes inside text, never double quotes.
- Sentences under about 25 words. No exclamation marks.

## Open questions

These are not settled by the brief or the text yet. Answering them will keep future writing consistent.

- [x] **Does the Mind have a name, and does the ship?** The ship does, one per hull: *Survey vessel ANANKE*, *Ark heavy TEMPERANCE*, *Long-range courier ASPHODEL*. The Mind has none and is only 'I'. Other ships are 'she'.
- [x] **How long is one leg?** One year of ship time. `waker_fate` commits to it ('ages a year with every leg'), so the text has decided.
- [x] **How long is the whole voyage?** Measured over 1,200 simulated runs: a median of 16 legs, 9 at the short end, 22 at the long, 39 at the most extreme. So 16 years is typical and 22 is a long haul. The distance to the target system is still open.
- [ ] What does the Mind find on arrival, and how do the open threads pay off?
- [x] **Does `{colonists}` start at exactly 10,000?** Only on the survey hull. The ark heavy carries 14,000 and the long-range courier 8,000, so no line may hard-code a figure.
- [ ] How many Arks launched, and can the player ever meet a living one face to face?
- [ ] How far in the future is the collapse, and how advanced was Earth when it fell?
- [ ] Can more colonists wake during the voyage, beyond the waker and the survivors?
