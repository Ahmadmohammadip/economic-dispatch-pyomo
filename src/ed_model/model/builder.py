"""
Builds a Pyomo ConcreteModel for multi-period, multi-bus DC-OPF Economic
Dispatch with ramping, renewables (curtailable), and storage.

NOTE ON PROVENANCE: this file was reconstructed from the locked spec in
PROJECT_BRIEF.md (final schema in data/schema.py, and the interface
solve.py expects) rather than transcribed from the original chat — the
final version of this file was only referenced there ("use the Phase 5
message's builder.py"), and that message's content wasn't available when
this repo was assembled. See PROJECT_BRIEF.md's "Provenance note".

Formulation summary (full derivation in docs/formulation.md):

    min   sum_t sum_g cost_g(p_g,t)
    s.t.  nodal power balance at every bus, every period
          DC line flow: f_l,t = B_l * (theta_from - theta_to), |f_l,t| <= F_l
          reference bus angle fixed at 0
          generator limits + ramp limits
          renewable dispatch bounded by forecast (curtailment = forecast - dispatch)
          storage SOC dynamics with charge/discharge efficiency

Two cost models are supported per generator, selected by `Generator.cost_type`:
  - "quadratic": c2*p^2 + c1*p + c0  (convex QP term)
  - "piecewise": c0 + sum_k marginal_cost_k * p_seg_k, non-decreasing
    marginal costs so the LP relaxation is exact without binaries/SOS2.
"""

from pyomo.environ import (
    ConcreteModel, Set, Param, Var, Objective, Constraint,
    NonNegativeReals, Reals, minimize,
)

from ed_model.data.schema import System
from ed_model.model.objective import quadratic_cost_term, piecewise_cost_term


def build_ed_model(system: System) -> ConcreteModel:
    m = ConcreteModel(name="EconomicDispatch_FullDCOPF")

    n_periods = system.n_periods
    periods = list(range(1, n_periods + 1))

    gen_by_name = {g.name: g for g in system.generators}
    ren_by_name = {r.name: r for r in system.renewables}
    sto_by_name = {s.name: s for s in system.storages}
    line_by_name = {l.name: l for l in system.lines}
    ref_bus = next(b.name for b in system.buses if b.is_reference)

    gens_quad = [g.name for g in system.generators if g.cost_type == "quadratic"]
    gens_pw = [g.name for g in system.generators if g.cost_type == "piecewise"]

    # --- Sets ---
    m.N = Set(initialize=[b.name for b in system.buses])
    m.L = Set(initialize=list(line_by_name.keys()))
    m.G = Set(initialize=list(gen_by_name.keys()))
    m.G_quad = Set(initialize=gens_quad, within=m.G)
    m.G_pw = Set(initialize=gens_pw, within=m.G)
    m.R = Set(initialize=list(ren_by_name.keys()))
    m.S = Set(initialize=list(sto_by_name.keys()))
    m.T = Set(initialize=periods, ordered=True)

    # Piecewise segment index set: (generator, segment index)
    gk_pairs = [
        (g, k)
        for g in gens_pw
        for k in range(len(gen_by_name[g].segments))
    ]
    m.GK = Set(initialize=gk_pairs, dimen=2)

    # --- Parameters ---
    m.p_min = Param(m.G, initialize={n: g.p_min for n, g in gen_by_name.items()})
    m.p_max = Param(m.G, initialize={n: g.p_max for n, g in gen_by_name.items()})
    m.c2 = Param(m.G, initialize={n: g.c2 for n, g in gen_by_name.items()})
    m.c1 = Param(m.G, initialize={n: g.c1 for n, g in gen_by_name.items()})
    m.c0 = Param(m.G, initialize={n: g.c0 for n, g in gen_by_name.items()})

    big_ramp = 1e9  # effectively unbounded when a generator has no ramp limit
    m.ramp_up = Param(m.G, initialize={
        n: (g.ramp_up if g.ramp_up is not None else big_ramp) for n, g in gen_by_name.items()
    })
    m.ramp_down = Param(m.G, initialize={
        n: (g.ramp_down if g.ramp_down is not None else big_ramp) for n, g in gen_by_name.items()
    })
    m.has_p_initial = {n: (g.p_initial is not None) for n, g in gen_by_name.items()}
    m.p_initial = Param(m.G, initialize={
        n: (g.p_initial if g.p_initial is not None else g.p_min) for n, g in gen_by_name.items()
    })

    if gk_pairs:
        m.segment_cost = Param(m.GK, initialize={
            (n, k): gen_by_name[n].segments[k].marginal_cost for (n, k) in gk_pairs
        })
        m.segment_width = Param(m.GK, initialize={
            (n, k): gen_by_name[n].segments[k].width for (n, k) in gk_pairs
        })

    m.demand = Param(m.N, m.T, initialize={
        (n, t): system.demand[n][t - 1] for n in system.demand for t in periods
    })

    if ren_by_name:
        m.forecast = Param(m.R, m.T, initialize={
            (r, t): ren_by_name[r].forecast[t - 1] for r in ren_by_name for t in periods
        })

    if line_by_name:
        m.susceptance = Param(m.L, initialize={n: l.susceptance for n, l in line_by_name.items()})
        m.flow_limit = Param(m.L, initialize={n: l.limit for n, l in line_by_name.items()})

    if sto_by_name:
        m.energy_capacity = Param(m.S, initialize={n: s.energy_capacity for n, s in sto_by_name.items()})
        m.charge_limit = Param(m.S, initialize={n: s.charge_limit for n, s in sto_by_name.items()})
        m.discharge_limit = Param(m.S, initialize={n: s.discharge_limit for n, s in sto_by_name.items()})
        m.charge_eff = Param(m.S, initialize={n: s.charge_efficiency for n, s in sto_by_name.items()})
        m.discharge_eff = Param(m.S, initialize={n: s.discharge_efficiency for n, s in sto_by_name.items()})
        m.initial_soc = Param(m.S, initialize={n: s.initial_soc for n, s in sto_by_name.items()})

    # --- Bus membership lookups (Gamma(n) from the formulation) ---
    gens_at_bus = {n: [] for n in m.N}
    for g in system.generators:
        gens_at_bus[g.bus].append(g.name)
    rens_at_bus = {n: [] for n in m.N}
    for r in system.renewables:
        rens_at_bus[r.bus].append(r.name)
    stos_at_bus = {n: [] for n in m.N}
    for s in system.storages:
        stos_at_bus[s.bus].append(s.name)
    lines_from = {n: [] for n in m.N}
    lines_to = {n: [] for n in m.N}
    for l in system.lines:
        lines_from[l.from_bus].append(l.name)
        lines_to[l.to_bus].append(l.name)

    # --- Variables ---
    def _p_bounds(m, g, t):
        return (m.p_min[g], m.p_max[g])
    m.p = Var(m.G, m.T, domain=NonNegativeReals, bounds=_p_bounds)

    if gk_pairs:
        def _p_seg_bounds(m, g, k, t):
            return (0, m.segment_width[g, k])
        m.p_seg = Var(m.GK, m.T, domain=NonNegativeReals, bounds=_p_seg_bounds)

    def _p_r_bounds(m, r, t):
        return (0, m.forecast[r, t])
    m.p_r = Var(m.R, m.T, domain=NonNegativeReals, bounds=_p_r_bounds) if ren_by_name else None

    if sto_by_name:
        def _p_ch_bounds(m, s, t):
            return (0, m.charge_limit[s])
        def _p_dis_bounds(m, s, t):
            return (0, m.discharge_limit[s])
        def _soc_bounds(m, s, t):
            return (0, m.energy_capacity[s])
        m.p_ch = Var(m.S, m.T, domain=NonNegativeReals, bounds=_p_ch_bounds)
        m.p_dis = Var(m.S, m.T, domain=NonNegativeReals, bounds=_p_dis_bounds)
        m.soc = Var(m.S, m.T, domain=NonNegativeReals, bounds=_soc_bounds)

    m.theta = Var(m.N, m.T, domain=Reals)
    if line_by_name:
        def _flow_bounds(m, l, t):
            return (-m.flow_limit[l], m.flow_limit[l])
        m.flow = Var(m.L, m.T, domain=Reals, bounds=_flow_bounds)

    # --- Objective ---
    def _cost_rule(m):
        total = 0
        for t in m.T:
            for g in m.G_quad:
                total += quadratic_cost_term(m, g, t)
            for g in m.G_pw:
                seg_idx = [k for (gg, k) in m.GK if gg == g]
                total += piecewise_cost_term(m, g, t, seg_idx)
        return total
    m.total_cost = Objective(rule=_cost_rule, sense=minimize)

    # --- Constraints ---

    # Piecewise dispatch = p_min + sum of segments
    if gk_pairs:
        def _pw_link_rule(m, g, t):
            seg_idx = [k for (gg, k) in m.GK if gg == g]
            return m.p[g, t] == m.p_min[g] + sum(m.p_seg[g, k, t] for k in seg_idx)
        m.pw_link_con = Constraint(m.G_pw, m.T, rule=_pw_link_rule)

    # Ramping (couples t and t-1; period 1 uses p_initial if provided)
    def _ramp_up_rule(m, g, t):
        if t == m.T.first():
            if not m.has_p_initial[g]:
                return Constraint.Skip
            return m.p[g, t] - m.p_initial[g] <= m.ramp_up[g]
        t_prev = m.T.prev(t)
        return m.p[g, t] - m.p[g, t_prev] <= m.ramp_up[g]
    m.ramp_up_con = Constraint(m.G, m.T, rule=_ramp_up_rule)

    def _ramp_down_rule(m, g, t):
        if t == m.T.first():
            if not m.has_p_initial[g]:
                return Constraint.Skip
            return m.p_initial[g] - m.p[g, t] <= m.ramp_down[g]
        t_prev = m.T.prev(t)
        t_prev_val = t_prev
        return m.p[g, t_prev_val] - m.p[g, t] <= m.ramp_down[g]
    m.ramp_down_con = Constraint(m.G, m.T, rule=_ramp_down_rule)

    # DC line flow
    if line_by_name:
        def _flow_def_rule(m, l, t):
            fb, tb = line_by_name[l].from_bus, line_by_name[l].to_bus
            return m.flow[l, t] == m.susceptance[l] * (m.theta[fb, t] - m.theta[tb, t])
        m.flow_def_con = Constraint(m.L, m.T, rule=_flow_def_rule)

    # Reference bus angle
    def _ref_bus_rule(m, t):
        return m.theta[ref_bus, t] == 0
    m.ref_bus_con = Constraint(m.T, rule=_ref_bus_rule)

    # Storage SOC dynamics
    if sto_by_name:
        def _soc_rule(m, s, t):
            prev_soc = m.initial_soc[s] if t == m.T.first() else m.soc[s, m.T.prev(t)]
            return m.soc[s, t] == prev_soc + m.charge_eff[s] * m.p_ch[s, t] - m.p_dis[s, t] / m.discharge_eff[s]
        m.soc_con = Constraint(m.S, m.T, rule=_soc_rule)

    # Nodal power balance (this is the constraint LMPs are extracted from)
    def _nodal_balance_rule(m, n, t):
        gen_term = sum(m.p[g, t] for g in gens_at_bus[n])
        ren_term = sum(m.p_r[r, t] for r in rens_at_bus[n]) if ren_by_name else 0
        sto_term = (
            sum(m.p_dis[s, t] - m.p_ch[s, t] for s in stos_at_bus[n]) if sto_by_name else 0
        )
        flow_out = sum(m.flow[l, t] for l in lines_from[n]) if line_by_name else 0
        flow_in = sum(m.flow[l, t] for l in lines_to[n]) if line_by_name else 0
        return gen_term + ren_term + sto_term - m.demand[n, t] == flow_out - flow_in
    m.nodal_balance_con = Constraint(m.N, m.T, rule=_nodal_balance_rule)

    return m
