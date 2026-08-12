# Economic Dispatch with Pyomo — Project Brief

## Goal
Public GitHub repo: multi-period DC-OPF Economic Dispatch model in Pyomo,
built and committed phase-by-phase, each phase tested and working before
moving to the next. Repo is public from the first commit.

## Scope (locked decisions)
- Full DC-OPF: network constraints, ramping, renewables, storage
- Cost model: both quadratic and piecewise-linear, selectable per generator
- Repo structure: installable package (src/ed_model) + notebook + Streamlit demo

## Architecture
```
economic-dispatch-pyomo/
├── src/ed_model/
│   ├── data/schema.py      # Bus, Line, Generator, Renewable, Storage, System (validated dataclasses)
│   ├── data/loaders.py     # JSON loading
│   ├── model/builder.py    # Pyomo ConcreteModel construction
│   ├── model/objective.py  # quadratic_cost_term / piecewise_cost_term strategies
│   ├── solve.py            # solver interface, DispatchResult, recommended_solver()
│   └── viz.py               # matplotlib plots: dispatch stack, LMP heatmap, SOC, line loading
├── notebooks/01_walkthrough.ipynb
├── app/streamlit_app.py
├── tests/                   # one file per feature + test_integration.py
├── docs/formulation.md      # full math writeup
└── .github/workflows/ci.yml # conda (ipopt+highspy) + pytest + ruff
```

## Phase history (commit-by-commit rationale)

**Phase 1** — Single-bus, single-period QP (quadratic cost, gen limits).
Validates data at construction (fail loud, not at solve time).

**Phase 2** — Multi-period + ramping. `demand` becomes list-valued;
ramp constraints couple t and t-1; `p_initial` optional for period-1 ramp.
Decision: ramp *feasibility* is NOT validated at construction (unlike
demand-vs-capacity) — would require solving a mini-LP to check exactly;
left to solver's infeasibility report instead.

**Phase 3** — DC-OPF network layer. Adds `Bus`, `Line`, nodal (not
system-wide) power balance, `theta`/`flow` variables, LMP = dual of nodal
balance. Connectivity to reference bus IS validated at construction
(cheap graph traversal, no false negatives — contrast with ramp
feasibility above). Sign convention: `generation - demand = outflow - inflow`.
Key test: congestion must create LMP divergence between buses — this is
the test that proves the network layer does something.

**Phase 4** — Renewables (curtailable, zero marginal cost, bounded by
forecast) and storage (SOC dynamics with charge/discharge efficiency).
Both enter the nodal balance. Feasibility check extended to include
renewable forecast + storage discharge capacity.
Known simplification: no storage degradation/cycling cost (flagged, not fixed).

**Phase 5** — Selectable piecewise-linear cost model per generator.
Segments require non-decreasing marginal cost (this is what makes the LP
relaxation exact without binaries/SOS2 — validated at construction).
Segment widths must sum exactly to `p_max - p_min` (validated — silent
under-dispatch otherwise). `recommended_solver(system)`: "highs" if all
generators piecewise (pure LP), else "ipopt" (any quadratic term = QP).
Known simplification: non-convex cost curves (valve-point effects) not
supported — would need binaries.

**Phase 6** — `viz.py` (dispatch stack, LMP heatmap, storage SOC, line
loading plots), narrated notebook, Streamlit demo (fixed 2-bus topology,
not a general network editor — deliberate scope limit). Streamlit app is
the first user-facing (not just dev-facing) surface — wrapped in
try/except for ValueError/RuntimeError so bad slider combos don't crash
to a raw traceback.

**Phase 7** — `docs/formulation.md` (full sets/params/variables/
constraints tables + known simplifications section), reconciled test
suite (all tests updated to final schema — multi-bus even for
single-bus tests, via a `_single_bus_system` helper), `test_integration.py`
(full system, all features combined, checks nodal balance holds exactly
post-solve), CI hardened (conda caching, viz extras, Streamlit syntax
smoke test).

## Known simplifications (deliberate, documented in docs/formulation.md)
- No unit commitment (on/off, startup costs, min up/down time)
- No storage degradation/cycling cost
- Non-convex piecewise costs unsupported (would need binaries/SOS2)
- DC power flow approximation (no losses, flat voltage magnitude)
- Ramp and multi-period storage feasibility not validated at construction
  (left to solver), unlike demand-capacity and bus-connectivity which are

## Possible next steps (not yet started)
- Phase 8 candidate: unit commitment (binary on/off + startup costs) — MILP
- Streamlit network editor (currently fixed 2-bus topology by design)
- Storage degradation cost modeling
- IEEE 14-bus test case in data/ieee_case_examples/

## Git conventions used
- One phase per commit (or a few commits per phase if it's large/split
  by concern), each commit leaves `main` green (tests pass)
- Commit message prefixes: feat / test / docs / ci / chore / fix
- Public repo from commit 1

## Provenance note
This brief and the files listed as "verbatim from chat" were transcribed
from a prior Claude.ai conversation. Several files referenced in that
conversation (builder.py final version, viz.py, streamlit_app.py, README.md,
docs/formulation.md, ci.yml, the notebook, and most of the test suite)
were only *referred to* in that conversation's reconciliation summary —
their actual code was shown in earlier messages that were not available
when this repo was assembled. Those files were reconstructed from scratch,
consistent with the final schema and the design decisions documented above,
rather than copied from the original chat. See each file's module docstring
for anything file-specific worth knowing.
