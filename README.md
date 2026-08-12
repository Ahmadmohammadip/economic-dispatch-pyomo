# Economic Dispatch with Pyomo

Multi-period, multi-bus DC-OPF Economic Dispatch, built with
[Pyomo](https://www.pyomo.org/). Supports transmission-constrained
dispatch, generator ramping, curtailable renewables, and storage, with a
selectable quadratic or piecewise-linear cost model per generator.

> Built incrementally, phase by phase — see `PROJECT_BRIEF.md` for the
> design rationale behind each phase and `docs/formulation.md` for the
> full mathematical formulation.

## Features

- **DC-OPF network layer** — nodal power balance, line flow via bus
  angles, thermal line limits, and locational marginal prices (LMPs)
  extracted directly from constraint duals.
- **Multi-period dispatch with ramping** — inter-temporal ramp-up /
  ramp-down limits per generator.
- **Renewables** — curtailable, forecast-bounded dispatch.
- **Storage** — state-of-charge dynamics with charge/discharge
  efficiency.
- **Two cost models, selectable per generator** — quadratic (QP, solved
  with Ipopt) or piecewise-linear with non-decreasing marginal cost (LP,
  solved with HiGHS). `recommended_solver()` picks the right one
  automatically based on the system's generator mix.
- **Validated data model** — a `System` fails loudly at construction
  time (unreachable buses, demand exceeding capacity, malformed cost
  segments, etc.) rather than surfacing as an opaque solver infeasibility.

## Install

```bash
pip install -e ".[dev,solvers,viz]"
```

Requires a solver: [HiGHS](https://highs.dev/) (installed via the
`solvers` extra, `highspy`) for LP-only systems, and
[Ipopt](https://coin-or.github.io/Ipopt/) for any system with a
quadratic-cost generator. Ipopt is not available via pip on all
platforms — see `.github/workflows/ci.yml` for a conda-based install.

## Quickstart

```python
from ed_model.data.schema import Bus, Generator, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed, recommended_solver

system = System(
    buses=[Bus(name="A", is_reference=True)],
    generators=[
        Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0),
        Generator(name="G2", bus="A", p_min=0, p_max=200, c2=0.02, c1=8, c0=0),
    ],
    demand={"A": [150]},
)

model = build_ed_model(system)
result = solve_ed(model, solver_name=recommended_solver(system))

print(result.dispatch_for_period(1))
print(result.total_cost)
```

## Repo layout

```
economic-dispatch-pyomo/
├── src/ed_model/
│   ├── data/schema.py      # Bus, Line, Generator, Renewable, Storage, System
│   ├── data/loaders.py     # JSON loading
│   ├── model/builder.py    # Pyomo ConcreteModel construction
│   ├── model/objective.py  # quadratic / piecewise cost strategies
│   ├── solve.py            # solver interface, DispatchResult, recommended_solver()
│   └── viz.py               # dispatch stack, LMP heatmap, SOC, line loading plots
├── notebooks/01_walkthrough.ipynb
├── app/streamlit_app.py    # interactive 2-bus demo
├── tests/
├── docs/formulation.md
└── .github/workflows/ci.yml
```

## Interactive demo

```bash
streamlit run app/streamlit_app.py
```

## Tests

```bash
pytest -v
```

## Known simplifications

No unit commitment, no storage degradation cost, no non-convex
(valve-point) cost curves, DC (lossless) power flow only. Full list with
rationale in `docs/formulation.md`.

## License

MIT — see `LICENSE`.
