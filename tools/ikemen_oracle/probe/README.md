# Exploratory upstream probes

These scenarios are *not* part of the parity corpus (nothing under
`tools/ikemen_oracle/scenarios/` globs this directory). They exist to answer
"which states does upstream actually visit for behaviour X?" before a state
is lowered, so the lowering and its proof scenario are designed from
observed upstream traces instead of guessed ones.

They are driven exactly like a corpus scenario:

```sh
caffeinate -d -i -s -w $$ &
NSAppSleepDisabled=1 python tools/ikemen_oracle/run.py \
    tools/ikemen_oracle/probe/probe_walk_120.json \
    --install --trace build/ikemen_oracle/probe/walk/upstream.jsonl
kill %1
```

`caffeinate` (or any other way of keeping the display awake) is required on
macOS: a sleeping display parks Cocoa's GL present in `SDL_GL_SwapWindow`,
so the engine never advances a frame and the run appears to hang.

`run.py` fails unless the trace length is exactly `frames`, so adjust the
scenario's `frames` to match what the behaviour actually produces. Probe
results feed the native lowering loop: observe upstream, lower the body,
prove it with a strict scenario under `scenarios/`.

| probe | question it answers |
| --- | --- |
| `probe_walk_120` | which states walking visits (20/21 anim switch) |
| `probe_run_140` | which states the forward double-tap run visits (100/105) |
| `probe_throw_160` | where the command throw lands the victim (800/810) |
| `probe_intro_240` | the full pre-round intro path from `RoundState -1` (191) |
