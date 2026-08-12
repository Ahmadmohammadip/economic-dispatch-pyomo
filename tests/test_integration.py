"""
Full-system integration test: network + ramping + renewables + storage +
mixed cost models together, checking that nodal power balance holds
exactly post-solve.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note").
"""

import pytest
from pyomo.environ import value

from ed_model.data.schema import Bus, Line, Generator, CostSegment, Renewable, Storage, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed, recommended_solver


def test_full_system_solves_and_balances():
    system = System(
        buses=[
            Bus(name="A", is_reference=True),
            Bus(name="B"),
            Bus(name="C"),
        ],
        lines=[
            Line(name="L1", from_bus="A", to_bus="B", susceptance=10.0, limit=120),
            Line(name="L2", from_bus="B", to_bus="C", susceptance=10.0, limit=80),
        ],
        generators=[
            Generator(
                name="G1", bus="A", p_min=0, p_max=250,
                c2=0.01, c1=12, c0=0,
                ramp_up=80, ramp_down=80, p_initial=100,
            ),
            Generator(
                name="G2", bus="C", p_min=0, p_max=150,
                cost_type="piecewise", c0=50,
                segments=(
                    CostSegment(width=75, marginal_cost=18),
                    CostSegment(width=75, marginal_cost=24),
                ),
                ramp_up=60, ramp_down=60, p_initial=50,
            ),
        ],
        renewables=[Renewable(name="Wind1", bus="B", forecast=[40, 70])],
        storages=[
            Storage(
                name="Batt1", bus="B",
                energy_capacity=100, charge_limit=40, discharge_limit=40,
                charge_efficiency=0.95, discharge_efficiency=0.95, initial_soc=50,
            )
        ],
        demand={"A": [120, 150], "B": [60, 90], "C": [70, 80]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name=recommended_solver(system))

    assert result.total_cost > 0

    for n in ["A", "B", "C"]:
        for t in [1, 2]:
            gen_term = sum(
                result.dispatch[(g.name, t)] for g in system.generators if g.bus == n
            )
            ren_term = sum(
                result.renewable_dispatch[(r.name, t)] for r in system.renewables if r.bus == n
            )
            sto_term = sum(
                result.storage_discharge[(s.name, t)] - result.storage_charge[(s.name, t)]
                for s in system.storages if s.bus == n
            )
            demand_t = system.demand[n][t - 1]

            flow_out = sum(
                result.flows[(l.name, t)] for l in system.lines if l.from_bus == n
            )
            flow_in = sum(
                result.flows[(l.name, t)] for l in system.lines if l.to_bus == n
            )

            lhs = gen_term + ren_term + sto_term - demand_t
            rhs = flow_out - flow_in
            assert lhs == pytest.approx(rhs, abs=1e-4), f"Power balance violated at bus {n}, t={t}"

    for g in system.generators:
        if g.ramp_up is None:
            continue
        p1 = result.dispatch[(g.name, 1)]
        p2 = result.dispatch[(g.name, 2)]
        assert p1 - g.p_initial <= g.ramp_up + 1e-4
        assert g.p_initial - p1 <= g.ramp_down + 1e-4
        assert p2 - p1 <= g.ramp_up + 1e-4
        assert p1 - p2 <= g.ramp_down + 1e-4
