# Ikemen GO oracle harness

This harness turns a local Ikemen GO checkout into an executable behavioral
oracle for the LibSaturn Ikemen runtime.

It is intentionally external to the Saturn runtime. The only source mutation is
an idempotent hook installed into the ignored `.external/Ikemen-GO` checkout.

## What it records

One JSON object is emitted per game frame after Ikemen GO finishes
`System.action()`. Schema version 1 records:

- round/tick/RNG state;
- every root fighter and Helper;
- state number/time/type/movetype;
- ctrl, animation, animation element/time;
- position, velocity, facing, life, power and juggle;
- hitpause and move-contact state;
- current GetHitVar chain ID;
- target IDs and HitDef target IDs;
- every projectile with owner, ID, animation, transform, hit/miss timers and
  removal/contact state.

The JSONL format is deliberately simple so the Saturn host runtime can emit the
same rows and be compared frame by frame. `docs/IKEMEN_COMPAT.md` documents how
each field is normalised (local velocity, stored state/move type, juggle budget,
move-contact type) and the per-tick order both sides follow.

## Install the hook

```sh
python tools/ikemen_oracle/install.py
```

The installer:

1. copies `oracle_hook.go` to
   `.external/Ikemen-GO/src/libsaturn_oracle.go`;
2. injects one hook before `SetupCharRoundStart()` to set the deterministic
   seed;
3. injects one hook immediately after `System.action()` to capture the frame.

It refuses to patch if the expected upstream anchors changed.

To remove it:

```sh
python tools/ikemen_oracle/install.py --uninstall
```

## Run a scenario

```sh
python tools/ikemen_oracle/run.py \
  tools/ikemen_oracle/scenarios/kfm_idle_120.json \
  --install
```

The default trace is written to:

```text
build/ikemen_oracle/ikemen.jsonl
```

A scenario currently controls the native Ikemen GO quick-match CLI:

```json
{
  "p1": "../Ikemen-GO-Screenpack/chars/kfm/kfm.def",
  "p2": "../Ikemen-GO-Screenpack/chars/kfm/kfm.def",
  "stage": "../Ikemen-GO-Screenpack/stages/stage0.def",
  "frames": 120,
  "seed": 1,
  "rounds": 1,
  "round_state": 2,
  "p1_ai": 0,
  "p2_ai": 0,
  "extra_args": []
}
```

The bundled scenario addresses the sibling ignored
`.external/Ikemen-GO-Screenpack` checkout directly, so it does not require
copying KFM or Training Room into the engine checkout.

By default capture starts at the first tick in `RoundState=2`, so motif
and intro frames do not shift the gameplay trace, and then keeps going through
whatever the engine does next (KO, win pose, next round). Set `round_state` to
another value (or `-1` to capture every round state from the first tick) when a
scenario specifically targets intro/post-round behavior.

The RNG seed is applied before round character setup.

## Deterministic authored inputs

Scenarios may contain a shared logical input timeline. The same timeline is
injected into Ikemen GO before command parsing and converted to Saturn pad
states before `ik_command_update()`, so both sides exercise their real command
engines rather than forcing state numbers.

```json
{
  "inputs": [
    {"from": 10, "to": 25, "p1": ["forward"], "p2": []},
    {"frame": 30, "p1": ["x"], "p2": ["back"]}
  ]
}
```

Supported logical buttons are `forward`, `back`, `up`, `down`, `a`,
`b`, `c`, `x`, `y`, `z` and `start`. Forward/back are resolved
relative to each fighter's current facing on both engines.

An event that names only one of `p1` / `p2` leaves the other player's script
alone, so two timelines can overlap. A scenario may also give starting values
that override both engines' defaults before the first scripted tick:

```json
{"setup": {"p1_power": 1000, "p2_life": 1}}
```

(`p1_life`, `p1_power`, `p2_life`, `p2_power`.) `expect` and `pending` are
read by `suite.py` only: `expect` checks the upstream trace so a scenario whose
move never connected cannot pass silently, and `pending` names the missing
feature of a scenario that is known to diverge (reported, not failed, until it
starts matching).

`gen_scenarios.py` writes the generated matrix (normals, specials, supers
with power, combos, P2 attackers, guard/blocking variants, recovery, get-up).
Run it after editing the generator; a unit test fails when a checked-in
scenario is stale.

## Compatibility suite

```sh
make ikemen-oracle-suite
```

The suite runs the upstream oracle, the native LibSaturn host runtime, then the
JSONL comparator for each scenario. It stops at the first divergent scenario
and asks the comparator for exactly one mismatch, giving the first
frame/field that should be investigated. Use `--keep-going` directly with
`suite.py` to collect all failing scenarios.

## Run the LibSaturn host trace

The Saturn fighting runtime is also executed natively on the host with the
generated KFM CNS/AIR assets:

```sh
make ikemen-oracle-saturn
```

This generates:

```text
build/ikemen_oracle/libsaturn.jsonl
```

Coordinates are normalized from the Saturn example's 320x224 screen space to
Ikemen stage-local space: X is relative to screen center and Y is relative to
the fight floor.

## Compare traces

```sh
make ikemen-oracle-diff
```

Or run the whole oracle -> Saturn -> diff pipeline:

```sh
make ikemen-oracle-check
```

The comparator ignores engine-global `tick` and mutable `rand_seed` by
default because LibSaturn does not yet expose equivalent global clocks/RNG.
They remain in both trace schemas for later determinism work. Pass
`--strict-metadata` directly to `diff.py` when those fields become
comparable.

The comparator is strict for integer/boolean/string/state fields and uses a
small absolute tolerance for floating-point coordinates and velocities.

## CPU scenario diagnostics (not AI parity)

The original GO AI can be enabled per scenario with `p1_ai`/`p2_ai`
(level 0..8). The Saturn host trace now honors these fields **only for
KFM ZSS**. The classic KFM character still uses scripted input and
cannot silently be labeled a CPU opponent. When the CPU is enabled the
host runner selects the **same native frame driver and state bodies**
as the console. The scenario seed starts an independent local CPU PRNG,
not the original Ikemen GO global RNG.

To produce two real, independently running CPU traces plus a divergence
report:

```sh
cmake --preset host && cmake --build --preset host
python tools/ikemen_oracle/ai_compare.py
```

It creates `build/ikemen_oracle/ai_comparison/`: `upstream_ai.jsonl`,
`saturn_ai.jsonl` and `comparison.json`. The report shows the first
different state, state histogram, transition counts and observed attack
frames for both engines. It **does not assert frame-by-frame AI parity**:
the original random stream, evaluations and other AI.zss branches are not
reproduced. Non-matching decisions are measurements for porting, not a
regression of the 66 classic / 27 mixed scripted corpus.

Ordinary host CI additionally runs `zss_native_ai_smoke`, checking
that the native CPU enters active states and attacks without relying on
Go, SDL or an upstream checkout build.

## Mixed classic KFM / KFM ZSS oracle

The native trace runner accepts either original character definition
independently per player: `chars/kfm/kfm.def` or
`chars/kfm_zss/kfm_zss.def`. It loads each player's actual CNS, AIR, CMD
and State -1 tables, exactly as the Saturn demo does. Unsupported character
paths are rejected rather than running the classic KFM accidentally.

The first four ZSS scenarios passed all 720 compared frames in upstream CI
[38925902594](https://github.com/celsowm/ikemen-saturn/actions/runs/38925902594).
Eight further scenarios (throws, recovery, guard, KO, uppercut and special
moves) also matched. CI run
[38927411982](https://github.com/celsowm/ikemen-saturn/actions/runs/38927411982)
produced 12 matching ZSS traces totalling **2,420 compared frames**.
These are now strict parity regression gates. The Fast Palm test asserts the
complete original victim chain 1025->1026->1027->1028 (including wall
impact and bounce), and the throw test asserts 820->821->5100;
both sequences were observed in the original engine's exported trace.

All **13** mixed classic/ZSS scenarios now match upstream under the
configured 1.5-pixel position and 0.35-pixel-per-tick velocity tolerances.
CI run [38928274699](https://github.com/celsowm/ikemen-saturn/actions/runs/38928274699)
passed the complete matrix, including `zss_p2_timeout_win_180`.
The recorded upstream timeout immediately transitions to visible winner
state 181 and loser state 170 (state 180 is transitory, not visible in the
per-frame trace). This final case is now also a strict parity gate.
The current 13-case corpus totals **2,600 compared frames**.
Upstream run
[38981362465](https://github.com/celsowm/ikemen-saturn/actions/runs/38981362465)
matched 25/27 cases. Two aerial cases differed by one CtrlSet frame:
the original ZSS State 600 uses AnimElemTime(3)=2, while classic CNS
uses Time=17. A source-checked ZSS-only timing shim fixed the mismatch
without affecting classic KFM. Upstream run
[38982178719](https://github.com/celsowm/ikemen-saturn/actions/runs/38982178719)
then matched **all 27 scenarios / 5,340 compared frames**, including
the Strong Knee 1060->1061 continuation. Every case is now a strict
regression gate under documented Q8.8 tolerances.
This proves bounded scripted gameplay behavior, not autonomous AI parity.

The extended matrix covers
chained punches, command cancels, supers, jumping attacks, air/crouch
reversals, and native ZSS Strong Knee. The Strong Knee FF+B scenario uses
an explicit altered input timeline and requires states 1060 and 1061.
A matched exploratory trace must be promoted to a strict regression
gate; an upstream move that never occurs remains an error, not a pass.
This does **not** assert autonomous AI parity: the Saturn oracle runner
still replays scripted player inputs rather than implementing upstream AI.

Future exploratory cases must use `exploratory: true`; upstream execution
failures and vacuous inputs still fail CI.
The classic matrix remains `kfm_*.json`, so adding ZSS scenarios does not
silently redefine the previously established classic parity baseline.

Run the Saturn-only smoke test (also in every ordinary CI build):

```sh
cmake --preset host
cmake --build --preset host
ctest --test-dir build/host -R zss_trace_smoke --output-on-failure
```

To run the full upstream-vs-Saturn ZSS comparison (requires the Ikemen GO
dependencies and screenpack as described above):

```sh
xvfb-run -a python tools/ikemen_oracle/suite.py --zss-only --keep-going \
    --trace-bin build/host/ikemen_oracle_trace
```

The optional Actions workflow dispatch input `zss_oracle` runs this matrix
under Go + Xvfb and uploads both JSONL traces plus the machine-readable
`zss_report.json` for each scenario.

Each scenario compares its *own* original upstream character selection
against the corresponding Saturn port; classic-vs-ZSS outputs are **not**
supposed to be identical. Current ZSS states still use classic fallback in
many places; these cases carry an explicit `pending` reason and the first
parity difference must be investigated. The suite checks non-vacuity against
upstream before allowing pending or exploratory differences. A failing upstream runner or
vacuous scripted input is **never** treated as pending; stale traces are
deleted before each run. Reports count mismatching frames by field and side
and pinpoint the first divergence, with 1.5px position and 0.35px/tick
velocity tolerances.

## Autonomous ZSS AI: upstream observation (not Saturn parity)

The Saturn trace runner currently replays deterministic human inputs. It does
**not** execute Ikemen GO's AI decisions, including the probabilistic aerial
throw recovery in State 821. Consequently, do not count an AI-only trace as
engine parity or silently replace its commands with hand-authored controls.

An optional GitHub Actions dispatch input `zss_ai_probe`, or a commit tagged
`[zss-ai-probe]`, runs a separate **upstream-only** experiment using P2 KFM
ZSS at AI level 8 (seed 1, 360 frames). The output artifact
`ikemen-zss-ai-observation` contains `upstream_ai.jsonl` and
`ai_report.json`: per-state occupancy, frame-indexed state transitions, and
attack/reaction frame counts. No candidate Saturn trace is fabricated.

Run locally with the configured Ikemen GO dependencies:

```sh
xvfb-run -a python tools/ikemen_oracle/ai_probe.py \
  --ikemen-dir .external/Ikemen-GO \
  --out build/ikemen_oracle/ai_probe
```

The observation flags cases where no attack was seen, because upstream's
scripted-input hook and CPU command routing need separate verification before
implementing deterministic AI replay on Saturn.

## Important scope

This is a behavioral oracle, not a source-code dependency. Ikemen GO remains in
`.external/Ikemen-GO`; nothing from its Go runtime is linked into LibSaturn.

The current hook is render-independent at capture time but Ikemen GO still
performs its normal platform/window initialization. A later fully headless
backend can remove that startup dependency without changing the trace schema.

The first Saturn runner intentionally uses idle controls. It establishes the
trace contract and exposes baseline divergences. Replay/input-stream injection
is the next layer for authored attacks, throws and controller edge cases.

## CPU random trigger fidelity

`ik_zss_ai_rng_next()` mirrors the pinned upstream `Random()` Park-Miller
(16807) algorithm and `ik_zss_ai_random_trigger()` mirrors the bytecode's
`Rand(0,999)` integer scaling (not `%1000`). The host CPU uses scenario
seed + player index, with independent per-player state, and the source
guards/golden vectors test the primitive. Upstream GO still uses one global
random stream shared among many systems, and native AI only evaluates its
implemented predicates: comparison reports remain **diagnostic**, not
RNG-consumption or whole-fight AI-parity certificates.

### Post-frame CPU RNG diagnostics

CPU-enabled host traces append a `native_ai_rng` array containing each
active CPU's post-frame Park-Miller seed (`null` for a scripted player).
The strict CPU-disabled oracle schema is unchanged. The AI comparison
report separately labels native-local and upstream-global start/end seeds;
they are **not comparable streams**, even though the next-number
primitive is the same.

## Auditing global versus native RNG draw counts

Each frame is recorded **after** its engine advances. With consecutive
positive Park-Miller checkpoints, `rng_audit.py` reconstructs the number
of calls to `Random()` since the previous frame by replaying at most 4096
steps. Unresolvable gaps are reported by frame instead of inventing counts;
the first frame has no prior post-frame checkpoint and is excluded.

`ai_compare.py` saves the original global and native-local
`draws_by_frame` series in `comparison.json`, plus the first differences.
The GO stream contains draws from **the entire engine**, while the
Saturn stream currently covers **ZSS CPU only**. Similar counts cannot
establish common RNG order or exact AI parity. The comparison is
diagnostic and does not weaken any scripted combat oracle gate.

The independent `RNG audit and tools` GitHub CI job tests these routines
without fetching the large LibSaturn package. Full firmware builds and
the native CPU smoke retain their original separate CI job.

## Exact Go Random() call-site provenance (opt-in)

The oracle installer now patches the pinned `src/common.go` `Random()`
return and annotates the `OC_random` interpreter operation. These changes
are **reversible** with `python tools/ikemen_oracle/install.py --uninstall`
and checked against exact original source anchors, with idempotent reinstall.
Ordinary scripted test runs leave the sidecar disabled.

To capture original calls individually, including the consuming file,
function, source line, character side, helper index, state and state time:

```sh
python tools/ikemen_oracle/ai_compare.py --rng-events
```

The `build/ikemen_oracle/ai_comparison/upstream_rng_events.jsonl` sidecar
records one object per random draw with `frame`, `ordinal`, `value`,
`file`, `line`, `function`, `player_no`, `helper_index`,
`state_no` and `state_time`. `player_no=-1` indicates that no
interpreter character context exists. `comparison.json` adds
`upstream_rng_events` with histogram by file and player/state and first
events, plus **strict verification of every interval after frame 0**
against the GO post-frame seed. The initial frame is explicitly excluded
from replay verification, because it has no previous recorded seed.
An incomplete or corrupted call trace fails instead of passing silently.

The `[zss-ai-probe]` or `zss_ai_probe` workflow now executes this
real GO-versus-native diagnostic and uploads the raw events and summary.
This labels original RNG consumption precisely, but does not yet identify
each specific `AI.zss` expression/line within the bytecode interpreter;
that requires an interpreter expression/source-map hook. It also does not
make the global GO and local Saturn RNG streams equivalent.

### Mapping Random() to original expressions

The opt-in GO instrumentation also wraps the pinned compiler's
`typedExp` path. It registers the **original source expression text**,
compiler source filename and expression end-line (not an exact token
column), keyed by its complete compiled bytecode. When the `OC_random`
opcode executes, the oracle looks up the enclosing bytecode signature.
An event is `unique` only if exactly one registered expression matches;
otherwise it is `ambiguous` or `unresolved`. Redirected or concatenated
runtime expressions may not match their original compiled signature.

The `upstream_rng_events` report groups uniquely mapped source
expressions and provides the first observed matches with character and
state context. A unique mapping identifies the **compiled expression**
that contains the random opcode, not necessarily a separate location
for each `random` token when the expression has several. The original
GO engine remains entirely external to the Saturn firmware, and this
does not imply decision parity.

## Native ZSS CPU memory diagnostics

CPU traces now include `native_ai_memory` per frame, with one element for
each player (`null` for a human-controlled player). This exposes the
native-only `gurt`, `ai_ji` and `aij` bookkeeping without changing
the existing scripted oracle trace schema. `ai_compare.py` verifies a
complete post-frame series, reports how many frames have active
get-up cooldown, a hitstun opportunity and a jump declaration, and
**explicitly disclaims original-Go AI parity**. The ordinary CPU smoke
test checks the memory schema on the real frame driver.

## First divergent CPU frame with original source evidence

After `ai_compare.py --rng-events`, the `comparison.json` contains
`first_divergence_context`: two frames before and after the **first**
state mismatch, including both fighters' states/positions, global GO and
local Saturn RNG checkpoints, the count of GO random calls, and the
`AI.zss` expressions/rolls actually **evaluated** in GO during those
frames. The output is deliberately bounded, and the CLI prints the first
mismatch and the line numbers with observed rolls. This diagnostic
does not assert that a predicate passed, that it caused the move, or
that local/global RNG streams align. No source-attribution fields
are inferred if the optional RNG-event sidecar is absent.
