"""Phase 2 ramping tests, adapted to the current System schema."""

import pytest
from pyomo.opt import TerminationCondition
from ed_model.data.schema import Bus, Generator, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed


def _single_bus_system(generators, demand):
    return System(
        buses=[Bus(name="A", is_reference=True)],
        lines=[],
        generators=generators,
        demand={"A": demand},
    )


def test_ramp_constraint_binds():
    gen1 = Generator(
        name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=5, c0=0,
        ramp_up=30, ramp_down=30, p_initial=20,
    )
    gen2 = Generator(name="G2", bus="A", p_min=0, p_max=200, c2=0.03, c1=15, c0=0)
    system = _single_bus_system([gen1, gen2], demand=[100, 180])

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert result.dispatch[("G1", 1)] <= 50 + 1e-4
    p1_g1 = result.dispatch[("G1", 1)]
    assert result.dispatch[("G1", 2)] <= p1_g1 + 30 + 1e-4

    assert result.dispatch[("G1", 1)] + result.dispatch[("G2", 1)] == pytest.approx(100, rel=1e-4)
    assert result.dispatch[("G1", 2)] + result.dispatch[("G2", 2)] == pytest.approx(180, rel=1e-4)


def test_no_ramp_limit_behaves_as_phase1():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0)
    gen2 = Generator(name="G2", bus="A", p_min=0, p_max=200, c2=0.02, c1=8, c0=0)
    system = _single_bus_system([gen1, gen2], demand=[150, 50])

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    for t, d in [(1, 150), (2, 50)]:
        p1, p2 = result.dispatch[("G1", t)], result.dispatch[("G2", t)]
        assert p1 + p2 == pytest.approx(d, rel=1e-4)
        mc1 = 2 * 0.01 * p1 + 10
        mc2 = 2 * 0.02 * p2 + 8
        assert mc1 == pytest.approx(mc2, rel=1e-3)


def test_infeasible_ramp_trajectory_reported_by_solver():
    gen1 = Generator(
        name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=5, c0=0,
        ramp_up=5, ramp_down=5, p_initial=0,
    )
    system = _single_bus_system([gen1], demand=[10, 150])

    model = build_ed_model(system)

    from pyomo.environ import SolverFactory
    solver = SolverFactory("ipopt")
    result = solver.solve(model, tee=False)

    assert result.solver.termination_condition in (
        TerminationCondition.infeasible,
        TerminationCondition.infeasibleOrUnbounded,
    )
