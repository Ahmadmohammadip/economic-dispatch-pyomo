"""
Typed, validated data structures for the Economic Dispatch model.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bus:
    name: str
    is_reference: bool = False


@dataclass(frozen=True)
class Line:
    name: str
    from_bus: str
    to_bus: str
    susceptance: float
    limit: float

    def __post_init__(self):
        if self.susceptance <= 0:
            raise ValueError(f"{self.name}: susceptance must be > 0, got {self.susceptance}")
        if self.limit <= 0:
            raise ValueError(f"{self.name}: limit must be > 0, got {self.limit}")
        if self.from_bus == self.to_bus:
            raise ValueError(f"{self.name}: from_bus and to_bus must differ")


@dataclass(frozen=True)
class CostSegment:
    """One segment of a piecewise-linear cost curve."""
    width: float          # MW
    marginal_cost: float  # $/MWh

    def __post_init__(self):
        if self.width <= 0:
            raise ValueError(f"CostSegment width must be > 0, got {self.width}")
        if self.marginal_cost < 0:
            raise ValueError(f"CostSegment marginal_cost must be >= 0, got {self.marginal_cost}")


@dataclass(frozen=True)
class Generator:
    """A dispatchable generator using either a quadratic or piecewise-linear
    cost model, selected via `cost_type`.

    Exactly one cost representation must be supplied, matching `cost_type`:
      - "quadratic": set c2, c1, c0; leave `segments` as None.
      - "piecewise": set `segments` (non-decreasing marginal_cost, summing
        to p_max - p_min in width); c2/c1 are ignored, c0 is the fixed
        no-load cost as before.
    """
    name: str
    bus: str
    p_min: float
    p_max: float
    cost_type: str = "quadratic"      # "quadratic" | "piecewise"
    c2: float = 0.0
    c1: float = 0.0
    c0: float = 0.0
    segments: tuple[CostSegment, ...] | None = None
    ramp_up: float | None = None
    ramp_down: float | None = None
    p_initial: float | None = None

    def __post_init__(self):
        if self.p_min < 0:
            raise ValueError(f"{self.name}: p_min must be >= 0, got {self.p_min}")
        if self.p_max < self.p_min:
            raise ValueError(f"{self.name}: p_max ({self.p_max}) must be >= p_min ({self.p_min})")
        if self.ramp_up is not None and self.ramp_up < 0:
            raise ValueError(f"{self.name}: ramp_up must be >= 0, got {self.ramp_up}")
        if self.ramp_down is not None and self.ramp_down < 0:
            raise ValueError(f"{self.name}: ramp_down must be >= 0, got {self.ramp_down}")
        if self.p_initial is not None and not (self.p_min <= self.p_initial <= self.p_max):
            raise ValueError(
                f"{self.name}: p_initial ({self.p_initial}) must be within "
                f"[{self.p_min}, {self.p_max}]"
            )

        if self.cost_type not in ("quadratic", "piecewise"):
            raise ValueError(
                f"{self.name}: cost_type must be 'quadratic' or 'piecewise', got '{self.cost_type}'"
            )

        if self.cost_type == "quadratic":
            if self.segments is not None:
                raise ValueError(
                    f"{self.name}: cost_type='quadratic' but segments were provided — "
                    f"set cost_type='piecewise' or remove segments"
                )
            if self.c2 < 0:
                raise ValueError(f"{self.name}: c2 must be >= 0 for a convex cost curve, got {self.c2}")

        if self.cost_type == "piecewise":
            if not self.segments:
                raise ValueError(f"{self.name}: cost_type='piecewise' requires at least one segment")

            marginal_costs = [s.marginal_cost for s in self.segments]
            if any(
                marginal_costs[i] > marginal_costs[i + 1]
                for i in range(len(marginal_costs) - 1)
            ):
                raise ValueError(
                    f"{self.name}: segment marginal_cost must be non-decreasing "
                    f"(required for the LP relaxation to be exact without binaries), "
                    f"got {marginal_costs}"
                )

            total_width = sum(s.width for s in self.segments)
            expected_width = self.p_max - self.p_min
            if abs(total_width - expected_width) > 1e-6:
                raise ValueError(
                    f"{self.name}: segment widths sum to {total_width}, but "
                    f"p_max - p_min = {expected_width} — segments must exactly "
                    f"span the generator's operating range"
                )


@dataclass(frozen=True)
class Renewable:
    """A curtailable, non-dispatchable resource (wind/solar). Dispatch is
    bounded above by a per-period forecast; the difference is curtailment.
    Zero marginal cost by default — see docs/formulation.md."""
    name: str
    bus: str
    forecast: list[float]

    def __post_init__(self):
        if not self.forecast:
            raise ValueError(f"{self.name}: forecast must have at least one period")
        if any(f < 0 for f in self.forecast):
            raise ValueError(f"{self.name}: forecast values must be >= 0")


@dataclass(frozen=True)
class Storage:
    """A storage unit (battery, pumped hydro, etc.)."""
    name: str
    bus: str
    energy_capacity: float
    charge_limit: float
    discharge_limit: float
    charge_efficiency: float
    discharge_efficiency: float
    initial_soc: float

    def __post_init__(self):
        if self.energy_capacity <= 0:
            raise ValueError(f"{self.name}: energy_capacity must be > 0, got {self.energy_capacity}")
        if self.charge_limit < 0 or self.discharge_limit < 0:
            raise ValueError(f"{self.name}: charge/discharge limits must be >= 0")
        if not (0 < self.charge_efficiency <= 1):
            raise ValueError(
                f"{self.name}: charge_efficiency must be in (0, 1], got {self.charge_efficiency}"
            )
        if not (0 < self.discharge_efficiency <= 1):
            raise ValueError(
                f"{self.name}: discharge_efficiency must be in (0, 1], got {self.discharge_efficiency}"
            )
        if not (0 <= self.initial_soc <= self.energy_capacity):
            raise ValueError(
                f"{self.name}: initial_soc ({self.initial_soc}) must be within "
                f"[0, {self.energy_capacity}]"
            )


@dataclass(frozen=True)
class System:
    buses: list[Bus] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    generators: list[Generator] = field(default_factory=list)
    renewables: list[Renewable] = field(default_factory=list)
    storages: list[Storage] = field(default_factory=list)
    demand: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.buses:
            raise ValueError("System must contain at least one bus")
        if not self.generators and not self.renewables:
            raise ValueError("System must contain at least one generator or renewable source")

        bus_names = [b.name for b in self.buses]
        if len(bus_names) != len(set(bus_names)):
            raise ValueError(f"Bus names must be unique, got: {bus_names}")
        bus_name_set = set(bus_names)

        ref_buses = [b.name for b in self.buses if b.is_reference]
        if len(ref_buses) != 1:
            raise ValueError(
                f"Exactly one bus must be marked is_reference=True, found {len(ref_buses)}: {ref_buses}"
            )

        for collection, label in [
            (self.generators, "Generator"), (self.renewables, "Renewable"), (self.storages, "Storage")
        ]:
            names = [c.name for c in collection]
            if len(names) != len(set(names)):
                raise ValueError(f"{label} names must be unique, got: {names}")
            for c in collection:
                if c.bus not in bus_name_set:
                    raise ValueError(f"{label} {c.name} references unknown bus '{c.bus}'")

        all_names = (
            [g.name for g in self.generators]
            + [r.name for r in self.renewables]
            + [s.name for s in self.storages]
        )
        if len(all_names) != len(set(all_names)):
            raise ValueError("Generator, renewable, and storage names must be globally unique")

        line_names = [l.name for l in self.lines]
        if len(line_names) != len(set(line_names)):
            raise ValueError(f"Line names must be unique, got: {line_names}")
        for l in self.lines:
            if l.from_bus not in bus_name_set:
                raise ValueError(f"Line {l.name} references unknown from_bus '{l.from_bus}'")
            if l.to_bus not in bus_name_set:
                raise ValueError(f"Line {l.name} references unknown to_bus '{l.to_bus}'")

        if set(self.demand.keys()) != bus_name_set:
            missing = bus_name_set - set(self.demand.keys())
            extra = set(self.demand.keys()) - bus_name_set
            raise ValueError(
                f"demand must have exactly one entry per bus. Missing: {missing}, unknown: {extra}"
            )

        lengths = {len(d) for d in self.demand.values()}
        lengths |= {len(r.forecast) for r in self.renewables}
        if len(lengths) != 1:
            raise ValueError(
                f"All demand series and renewable forecasts must share the same period "
                f"count, got lengths: {lengths}"
            )
        n_periods = lengths.pop()
        if n_periods == 0:
            raise ValueError("Demand/forecast series must have at least one period")
        if any(d < 0 for series in self.demand.values() for d in series):
            raise ValueError("All demand values must be >= 0")

        max_storage_discharge = sum(s.discharge_limit for s in self.storages)
        max_gen_capacity = sum(g.p_max for g in self.generators)
        for t in range(n_periods):
            total_demand_t = sum(series[t] for series in self.demand.values())
            max_renewable_t = sum(r.forecast[t] for r in self.renewables)
            available_t = max_gen_capacity + max_renewable_t + max_storage_discharge
            if total_demand_t > available_t:
                raise ValueError(
                    f"Total demand at t={t + 1} ({total_demand_t} MW) exceeds total available "
                    f"capacity ({available_t} MW: gen={max_gen_capacity}, renewable="
                    f"{max_renewable_t}, storage_discharge={max_storage_discharge})."
                )

        self._check_connectivity(bus_name_set)

    def _check_connectivity(self, bus_name_set: set[str]) -> None:
        adjacency: dict[str, set[str]] = {b: set() for b in bus_name_set}
        for l in self.lines:
            adjacency[l.from_bus].add(l.to_bus)
            adjacency[l.to_bus].add(l.from_bus)

        ref_bus = next(b.name for b in self.buses if b.is_reference)
        visited = {ref_bus}
        frontier = [ref_bus]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)

        unreachable = bus_name_set - visited
        if unreachable:
            raise ValueError(
                f"Buses unreachable from reference bus '{ref_bus}': {unreachable}. "
                f"Check line topology — an isolated bus makes angles undefined there."
            )

    @property
    def n_periods(self) -> int:
        if self.demand:
            return len(next(iter(self.demand.values())))
        return len(self.renewables[0].forecast)
