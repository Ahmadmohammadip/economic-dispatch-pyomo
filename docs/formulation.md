# Formulation

> **Provenance note:** this document was reconstructed for this repo (see
> `PROJECT_BRIEF.md` → "Provenance note") from the math discussed earlier
> in the design conversation, rather than transcribed verbatim from a
> single chat message. It matches the implementation in `src/ed_model/`.

## 1. Sets and indices

| Symbol | Description |
|---|---|
| $G$ | Conventional (dispatchable) generators, index $g$ |
| $R$ | Renewable (non-dispatchable, curtailable) units, index $r$ |
| $S$ | Storage units, index $s$ |
| $N$ | Buses, index $n$ |
| $L$ | Transmission lines, index $\ell = (n, m)$ |
| $T$ | Time periods, index $t = 1, \dots, T$ |
| $ref$ | Reference (slack) bus |

## 2. Parameters

| Symbol | Description |
|---|---|
| $c_g^2, c_g^1, c_g^0$ | Quadratic cost coefficients for generator $g$ |
| $c_{g,k}^{lin}$ | Piecewise-linear segment marginal cost, segment $k$, generator $g$ |
| $\underline{P}_g, \overline{P}_g$ | Min / max generator output |
| $RU_g, RD_g$ | Ramp-up / ramp-down limits (MW/period) |
| $D_{n,t}$ | Demand at bus $n$, period $t$ |
| $\hat{P}_{r,t}$ | Available renewable forecast, unit $r$, period $t$ |
| $B_\ell$ | Susceptance of line $\ell$ |
| $\overline{F}_\ell$ | Thermal limit of line $\ell$ |
| $\eta_s^{ch}, \eta_s^{dis}$ | Storage charge / discharge efficiency |
| $\overline{E}_s, \overline{P}_s^{ch/dis}$ | Storage energy capacity, charge/discharge power limit |
| $SOC_s^0$ | Initial state of charge |
| $\Gamma(n)$ | Generators/renewables/storage mapped to bus $n$ |

## 3. Decision variables

| Symbol | Description |
|---|---|
| $p_{g,t}$ | Generator output |
| $p_{r,t}$ | Renewable dispatch ($\le$ forecast; difference is curtailment) |
| $p_{s,t}^{ch}, p_{s,t}^{dis}$ | Storage charge / discharge power |
| $e_{s,t}$ | Storage state of charge (energy) |
| $\theta_{n,t}$ | Voltage angle at bus $n$ (DC power flow) |
| $f_{\ell,t}$ | Power flow on line $\ell$ |

## 4. Objective

$$
\min \sum_{t \in T} \sum_{g \in G} \left( c_g^2 p_{g,t}^2 + c_g^1 p_{g,t} + c_g^0 \right)
$$

For generators using the piecewise-linear cost model, the quadratic term
above is replaced by $c_g^0 + \sum_k c_{g,k}^{lin} \, p_{g,k,t}^{seg}$,
where each segment variable is bounded by its width and segment marginal
costs are required to be non-decreasing. That requirement is what makes
the LP relaxation exact without binary/SOS2 variables — a non-decreasing
marginal cost curve is convex, so the solver never has an incentive to
fill a later, cheaper-looking segment before an earlier one.

## 5. Constraints

**Nodal power balance (DC-OPF)**

$$
\sum_{g \in \Gamma(n)} p_{g,t} + \sum_{r \in \Gamma(n)} p_{r,t} + \sum_{s \in \Gamma(n)} (p_{s,t}^{dis} - p_{s,t}^{ch}) - D_{n,t} = \sum_{\ell: n \to m} f_{\ell,t} - \sum_{\ell: m \to n} f_{\ell,t} \quad \forall n, t
$$

**DC line flow**

$$
f_{\ell,t} = B_\ell (\theta_{n,t} - \theta_{m,t}), \quad -\overline{F}_\ell \le f_{\ell,t} \le \overline{F}_\ell \quad \forall \ell, t
$$

**Reference bus**

$$
\theta_{ref,t} = 0 \quad \forall t
$$

**Generator limits and ramping**

$$
\underline{P}_g \le p_{g,t} \le \overline{P}_g, \qquad -RD_g \le p_{g,t} - p_{g,t-1} \le RU_g \quad \forall g, t
$$

**Renewable dispatch (with curtailment)**

$$
0 \le p_{r,t} \le \hat{P}_{r,t}
$$

**Storage dynamics**

$$
e_{s,t} = e_{s,t-1} + \eta_s^{ch} p_{s,t}^{ch} - \frac{p_{s,t}^{dis}}{\eta_s^{dis}}, \qquad 0 \le e_{s,t} \le \overline{E}_s
$$

$$
0 \le p_{s,t}^{ch} \le \overline{P}_s^{ch}, \qquad 0 \le p_{s,t}^{dis} \le \overline{P}_s^{dis}
$$

## 6. Locational marginal prices

The dual value of the nodal power balance constraint at bus $n$, period
$t$ is the locational marginal price (LMP) — the marginal cost of serving
one additional MW of demand at that bus and period, accounting for
network congestion. In an uncongested, single-bus system this collapses
to the system marginal price. `solve.py` extracts these directly from
Pyomo's `dual` suffix after solving.

## 7. Known simplifications

- **No unit commitment.** Generators are always available; there is no
  binary on/off state, no startup cost, and no minimum up/down time.
- **No storage degradation or cycling cost.** Charging and discharging
  are only penalized through round-trip efficiency losses, not through
  any cost proportional to cycling.
- **Non-convex piecewise cost curves are not supported.** The
  non-decreasing marginal cost requirement (Section 4) rules out
  valve-point loading effects, which would require binary segment-
  selection variables (SOS2) to model correctly.
- **DC power flow approximation.** Line losses are neglected and voltage
  magnitude is assumed flat (1.0 p.u.) at every bus — standard for
  dispatch-level studies, not adequate for voltage/reactive power
  analysis.
- **Ramp and multi-period storage feasibility are not validated at
  construction.** Unlike demand-vs-capacity and bus-connectivity, which
  fail immediately and clearly in `System.__post_init__`, an infeasible
  ramp trajectory or SOC path is only discovered when the solver reports
  `infeasible`. Validating these ahead of time would require solving a
  reduced feasibility LP, which was judged not worth the added
  complexity for this project's scope.
- **No simultaneous charge/discharge exclusivity constraint.** With
  round-trip efficiency $\eta^{ch}\eta^{dis} < 1$, simultaneous
  charge/discharge to "game" the objective is self-penalizing in nearly
  all cases and is not explicitly forbidden with a binary variable —
  kept as an LP/QP rather than a MILP. Worth a targeted test case rather
  than a structural constraint.
