"""Solver interface and result extraction."""

from dataclasses import dataclass

from pyomo.environ import ConcreteModel, Suffix, SolverFactory, value
from pyomo.opt import SolverStatus, TerminationCondition


@dataclass
class DispatchResult:
    dispatch: dict[tuple[str, int], float]
    renewable_dispatch: dict[tuple[str, int], float]
    curtailment: dict[tuple[str, int], float]
    storage_charge: dict[tuple[str, int], float]
    storage_discharge: dict[tuple[str, int], float]
    storage_soc: dict[tuple[str, int], float]
    flows: dict[tuple[str, int], float]
    angles: dict[tuple[str, int], float]
    total_cost: float
    lmp: dict[tuple[str, int], float]

    def dispatch_for_period(self, t: int) -> dict[str, float]:
        return {g: p for (g, tt), p in self.dispatch.items() if tt == t}

    def lmp_for_period(self, t: int) -> dict[str, float]:
        return {n: price for (n, tt), price in self.lmp.items() if tt == t}


def solve_ed(model: ConcreteModel, solver_name: str = "ipopt") -> DispatchResult:
    if not hasattr(model, "dual"):
        model.dual = Suffix(direction=Suffix.IMPORT)

    solver = SolverFactory(solver_name)
    result = solver.solve(model, tee=False)

    if (result.solver.status != SolverStatus.ok or
            result.solver.termination_condition != TerminationCondition.optimal):
        raise RuntimeError(
            f"Solve failed: status={result.solver.status}, "
            f"termination={result.solver.termination_condition}"
        )

    dispatch = {(g, t): value(model.p[g, t]) for g in model.G for t in model.T}
    renewable_dispatch = {(r, t): value(model.p_r[r, t]) for r in model.R for t in model.T}
    curtailment = {
        (r, t): value(model.forecast[r, t]) - value(model.p_r[r, t])
        for r in model.R for t in model.T
    }
    storage_charge = {(s, t): value(model.p_ch[s, t]) for s in model.S for t in model.T}
    storage_discharge = {(s, t): value(model.p_dis[s, t]) for s in model.S for t in model.T}
    storage_soc = {(s, t): value(model.soc[s, t]) for s in model.S for t in model.T}
    flows = {(l, t): value(model.flow[l, t]) for l in model.L for t in model.T}
    angles = {(n, t): value(model.theta[n, t]) for n in model.N for t in model.T}
    total_cost = value(model.total_cost)

    lmp = {
        (n, t): model.dual[model.nodal_balance_con[n, t]]
        for n in model.N for t in model.T
    }

    return DispatchResult(
        dispatch=dispatch, renewable_dispatch=renewable_dispatch, curtailment=curtailment,
        storage_charge=storage_charge, storage_discharge=storage_discharge, storage_soc=storage_soc,
        flows=flows, angles=angles, total_cost=total_cost, lmp=lmp,
    )


def recommended_solver(system) -> str:
    """Returns 'highs' if every generator uses the piecewise-linear cost
    model (pure LP — HiGHS is fast and free), else 'ipopt' (needed for any
    quadratic-cost generator, which makes the problem a QP)."""
    if all(g.cost_type == "piecewise" for g in system.generators):
        return "highs"
    return "ipopt"
