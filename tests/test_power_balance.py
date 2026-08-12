"""
Single-bus sanity tests against a hand-verifiable solution, using the
current (multi-bus-capable) schema via a `_single_bus_system` helper.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note") — the original chat's "reconciled" version of this
file was referenced but not shown in the transcript that was pasted in.
"""

import pytest
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


def test_two_generator_equal_marginal_cost():
    """Hand solution: 0.02*p1 + 10 = 0.04*p2 + 8, p1 + p2 = 150
    => p1 = 2*p2 - 100, and (2*p2 - 100) + p2 = 150 => p2 = 250/3, p1 = 200/3
    """
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0)
    gen2 = Generator(name="G2", bus="A", p_min=0, p_max=200, c2=0.02, c1=8, c0=0)
    system = _single_bus_system([gen1, gen2], demand=[150])

    expected_p1 = 200 / 3
    expected_p2 = 250 / 3
    expected_lambda = 0.02 * expected_p1 + 10

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert result.dispatch[("G1", 1)] == pytest.approx(expected_p1, rel=1e-4)
    assert result.dispatch[("G2", 1)] == pytest.approx(expected_p2, rel=1e-4)
    assert result.lmp[("A", 1)] == pytest.approx(expected_lambda, rel=1e-3)


def test_infeasible_demand_rejected_at_construction():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=100, c2=0.01, c1=10, c0=0)
    with pytest.raises(ValueError, match="exceeds total available"):
        _single_bus_system([gen1], demand=[150])


def test_binding_generator_limit():
    """Demand pushes G1 to its p_max — checks bound enforcement, not just
    the unconstrained algebra above."""
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=50, c2=0.01, c1=5, c0=0)
    gen2 = Generator(name="G2", bus="A", p_min=0, p_max=200, c2=0.05, c1=20, c0=0)
    system = _single_bus_system([gen1, gen2], demand=[180])

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert result.dispatch[("G1", 1)] == pytest.approx(50, rel=1e-4)
    assert result.dispatch[("G2", 1)] == pytest.approx(130, rel=1e-4)


def test_power_balance_holds_exactly():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0)
    system = _single_bus_system([gen1], demand=[120])

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert result.dispatch[("G1", 1)] == pytest.approx(120, rel=1e-4)
