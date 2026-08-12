"""
Cost-model strategies for the Economic Dispatch objective.
"""

from pyomo.core.base.var import IndexedVar


def quadratic_cost_term(m, g: str, t: int) -> object:
    """c2 * p^2 + c1 * p + c0 for generator g at period t."""
    return m.c2[g] * m.p[g, t] ** 2 + m.c1[g] * m.p[g, t] + m.c0[g]


def piecewise_cost_term(m, g: str, t: int, segment_indices: list[int]) -> object:
    """c0 + sum_k marginal_cost[g,k] * p_seg[g,k,t] for generator g at period t."""
    return m.c0[g] + sum(
        m.segment_cost[g, k] * m.p_seg[g, k, t] for k in segment_indices
    )
