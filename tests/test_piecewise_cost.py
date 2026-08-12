"""
Phase 5 piecewise-linear cost model tests.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note").
"""

import pytest
from ed_model.data.schema import Bus, CostSegment, Generator, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed, recommended_solver


def test_piecewise_generator_fills_cheaper_segment_first():
    gen1 = Generator(
        name="G1", bus="A", p_min=0, p_max=100,
        cost_type="piecewise", c0=0,
        segments=(
            CostSegment(width=50, marginal_cost=10),
            CostSegment(width=50, marginal_cost=30),
        ),
    )
    system = System(
        buses=[Bus(name="A", is_reference=True)],
        generators=[gen1],
        demand={"A": [30]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="highs")

    assert result.dispatch[("G1", 1)] == pytest.approx(30, rel=1e-4)
    from pyomo.environ import value
    assert value(model.p_seg["G1", 0, 1]) == pytest.approx(30, rel=1e-4)
    assert value(model.p_seg["G1", 1, 1]) == pytest.approx(0, abs=1e-4)


def test_segment_widths_must_span_operating_range():
    with pytest.raises(ValueError, match="segments must exactly span"):
        Generator(
            name="G1", bus="A", p_min=0, p_max=100,
            cost_type="piecewise", c0=0,
            segments=(CostSegment(width=50, marginal_cost=10),),
        )


def test_non_decreasing_marginal_cost_required():
    with pytest.raises(ValueError, match="non-decreasing"):
        Generator(
            name="G1", bus="A", p_min=0, p_max=100,
            cost_type="piecewise", c0=0,
            segments=(
                CostSegment(width=50, marginal_cost=30),
                CostSegment(width=50, marginal_cost=10),
            ),
        )


def test_recommended_solver_picks_highs_for_all_piecewise():
    gen1 = Generator(
        name="G1", bus="A", p_min=0, p_max=100,
        cost_type="piecewise", c0=0,
        segments=(CostSegment(width=100, marginal_cost=10),),
    )
    system = System(buses=[Bus(name="A", is_reference=True)], generators=[gen1], demand={"A": [50]})
    assert recommended_solver(system) == "highs"


def test_recommended_solver_picks_ipopt_when_any_quadratic():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=100, c2=0.01, c1=10, c0=0)
    gen2 = Generator(
        name="G2", bus="A", p_min=0, p_max=100,
        cost_type="piecewise", c0=0,
        segments=(CostSegment(width=100, marginal_cost=10),),
    )
    system = System(buses=[Bus(name="A", is_reference=True)], generators=[gen1, gen2], demand={"A": [50]})
    assert recommended_solver(system) == "ipopt"
