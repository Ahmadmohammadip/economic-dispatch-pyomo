"""
Phase 4 storage + renewable tests.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note").
"""

import pytest
from ed_model.data.schema import Bus, Generator, Renewable, Storage, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed


def test_storage_soc_tracks_charge_discharge():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=300, c2=0.01, c1=10, c0=0)
    storage = Storage(
        name="Batt1", bus="A",
        energy_capacity=100, charge_limit=50, discharge_limit=50,
        charge_efficiency=0.9, discharge_efficiency=0.9, initial_soc=50,
    )
    system = System(
        buses=[Bus(name="A", is_reference=True)],
        generators=[gen1],
        storages=[storage],
        demand={"A": [100, 100]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    for t in (1, 2):
        assert 0 <= result.storage_soc[("Batt1", t)] <= 100 + 1e-6
        assert 0 <= result.storage_charge[("Batt1", t)] <= 50 + 1e-6
        assert 0 <= result.storage_discharge[("Batt1", t)] <= 50 + 1e-6


def test_renewable_curtailment_when_oversupplied():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=200, c2=0.01, c1=10, c0=0)
    wind = Renewable(name="Wind1", bus="A", forecast=[100])
    system = System(
        buses=[Bus(name="A", is_reference=True)],
        generators=[gen1],
        renewables=[wind],
        demand={"A": [40]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    # Zero-marginal-cost renewable should be fully used before any thermal gen,
    # and the rest curtailed since demand (40) < forecast (100).
    assert result.renewable_dispatch[("Wind1", 1)] == pytest.approx(40, rel=1e-4)
    assert result.curtailment[("Wind1", 1)] == pytest.approx(60, rel=1e-4)
    assert result.dispatch[("G1", 1)] == pytest.approx(0, abs=1e-4)


def test_storage_capacity_bounds_respected_over_multiple_periods():
    gen1 = Generator(name="G1", bus="A", p_min=0, p_max=300, c2=0.0, c1=10, c0=0)
    storage = Storage(
        name="Batt1", bus="A",
        energy_capacity=50, charge_limit=100, discharge_limit=100,
        charge_efficiency=1.0, discharge_efficiency=1.0, initial_soc=0,
    )
    system = System(
        buses=[Bus(name="A", is_reference=True)],
        generators=[gen1],
        storages=[storage],
        demand={"A": [10, 10, 10]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name="ipopt")

    for t in (1, 2, 3):
        assert result.storage_soc[("Batt1", t)] <= 50 + 1e-6
        assert result.storage_soc[("Batt1", t)] >= -1e-6
