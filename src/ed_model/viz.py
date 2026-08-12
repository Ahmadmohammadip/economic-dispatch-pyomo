"""
Plotting helpers for a solved Economic Dispatch case.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note") rather than transcribed verbatim from the original
chat. Uses matplotlib only, kept dependency-light so it also works headless
in CI (Agg backend) and inside the Streamlit app.

Each function takes a `System` and a `DispatchResult` (see solve.py) and
returns a matplotlib Figure — callers decide whether to show(), save(), or
hand it to st.pyplot() in the Streamlit app.
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from ed_model.data.schema import System
from ed_model.solve import DispatchResult


def plot_dispatch_stack(system: System, result: DispatchResult):
    """Stacked area chart of generator + renewable dispatch over time,
    with total demand overlaid as a line."""
    periods = list(range(1, system.n_periods + 1))

    fig, ax = plt.subplots(figsize=(9, 5))

    stack_labels = []
    stack_values = []
    for g in system.generators:
        stack_labels.append(g.name)
        stack_values.append([result.dispatch[(g.name, t)] for t in periods])
    for r in system.renewables:
        stack_labels.append(f"{r.name} (renewable)")
        stack_values.append([result.renewable_dispatch[(r.name, t)] for t in periods])

    if stack_values:
        ax.stackplot(periods, *stack_values, labels=stack_labels, alpha=0.85)

    total_demand = [sum(series[t - 1] for series in system.demand.values()) for t in periods]
    ax.plot(periods, total_demand, color="black", linewidth=2, linestyle="--", label="Total demand")

    ax.set_xlabel("Period")
    ax.set_ylabel("Power (MW)")
    ax.set_title("Dispatch stack vs. demand")
    ax.legend(loc="upper left", fontsize="small", ncol=2)
    fig.tight_layout()
    return fig


def plot_lmp_heatmap(system: System, result: DispatchResult):
    """Heatmap of locational marginal price (bus x period)."""
    buses = [b.name for b in system.buses]
    periods = list(range(1, system.n_periods + 1))

    matrix = np.array([[result.lmp[(n, t)] for t in periods] for n in buses])

    fig, ax = plt.subplots(figsize=(max(6, len(periods) * 0.6), max(3, len(buses) * 0.6)))
    im = ax.imshow(matrix, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(periods)))
    ax.set_xticklabels(periods)
    ax.set_yticks(range(len(buses)))
    ax.set_yticklabels(buses)
    ax.set_xlabel("Period")
    ax.set_ylabel("Bus")
    ax.set_title("Locational marginal price ($/MWh)")
    fig.colorbar(im, ax=ax, label="$/MWh")
    fig.tight_layout()
    return fig


def plot_storage_soc(system: System, result: DispatchResult):
    """Line plot of state of charge for each storage unit over time."""
    periods = list(range(1, system.n_periods + 1))

    fig, ax = plt.subplots(figsize=(9, 4))
    for s in system.storages:
        soc_series = [result.storage_soc[(s.name, t)] for t in periods]
        ax.plot(periods, soc_series, marker="o", label=s.name)

    ax.set_xlabel("Period")
    ax.set_ylabel("State of charge (MWh)")
    ax.set_title("Storage state of charge")
    if system.storages:
        ax.legend(loc="best", fontsize="small")
    fig.tight_layout()
    return fig


def plot_line_loading(system: System, result: DispatchResult):
    """Bar chart of peak line loading (|flow| / limit) across all periods,
    per line — a quick way to spot which lines are binding constraints."""
    lines = system.lines
    periods = list(range(1, system.n_periods + 1))

    peak_loading = []
    for l in lines:
        flows = [abs(result.flows[(l.name, t)]) for t in periods]
        peak_loading.append(max(flows) / l.limit if l.limit else 0.0)

    fig, ax = plt.subplots(figsize=(max(6, len(lines) * 0.8), 4))
    colors = ["crimson" if v >= 0.99 else "steelblue" for v in peak_loading]
    ax.bar([l.name for l in lines], peak_loading, color=colors)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("Peak loading (fraction of thermal limit)")
    ax.set_title("Peak transmission line loading")
    fig.tight_layout()
    return fig
