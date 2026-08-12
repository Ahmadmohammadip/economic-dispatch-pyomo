"""
Phase 3 DC-OPF network tests.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note").
"""

import pytest
from ed_model.data.schema import Bus, Line, Generator, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed


def test_two_bus_uncongested_lmps_converge():
    """With enough line capacity, both buses should clear at the same LMP."""
    system = System(
        buses=[Bus(name="A", is_reference=True), Bus(name="B")],
        lines=[Line(name="L1", from_bus="A", to_bus="B", susceptance=10.0, limit=500)],
        generators=[
            Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0),
            Generator(name="G2", bus="B", p_min=0, p_max=200, c2=0.02, c1=8, c0=0),
        ],
        demand={"A": [150], "B": [0]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert result.lmp[("A", 1)] == pytest.approx(result.lmp[("B", 1)], rel=1e-3)


def test_congestion_creates_lmp_divergence():
    """A tight line limit should force local generation to serve local
    demand at a different marginal cost, splitting the LMPs — this is the
    test that proves the network layer actually does something."""
    system = System(
        buses=[Bus(name="A", is_reference=True), Bus(name="B")],
        lines=[Line(name="L1", from_bus="A", to_bus="B", susceptance=10.0, limit=20)],
        generators=[
            Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.0, c1=10, c0=0),
            Generator(name="G2", bus="B", p_min=0, p_max=200, c2=0.0, c1=30, c0=0),
        ],
        demand={"A": [20], "B": [100]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    assert abs(result.lmp[("A", 1)] - result.lmp[("B", 1)]) > 1.0
    assert abs(result.flows[("L1", 1)]) == pytest.approx(20, abs=1e-3)


def test_unreachable_bus_rejected_at_construction():
    with pytest.raises(ValueError, match="unreachable"):
        System(
            buses=[Bus(name="A", is_reference=True), Bus(name="Island")],
            lines=[],
            generators=[Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0)],
            demand={"A": [50], "Island": [0]},
        )


def test_reference_bus_angle_is_zero():
    system = System(
        buses=[Bus(name="A", is_reference=True), Bus(name="B")],
        lines=[Line(name="L1", from_bus="A", to_bus="B", susceptance=10.0, limit=500)],
        generators=[
            Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0),
            Generator(name="G2", bus="B", p_min=0, p_max=200, c2=0.02, c1=8, c0=0),
        ],
        demand={"A": [100], "B": [50]},
    )

    model = build_ed_model(system)
    solve_ed(model, solver_name="ipopt")

    from pyomo.environ import value
    assert value(model.theta["A", 1]) == pytest.approx(0.0, abs=1e-6)
