"""
Streamlit demo for the Economic Dispatch model.

NOTE ON PROVENANCE: reconstructed for this repo (see PROJECT_BRIEF.md
"Provenance note"). Scope is deliberately a fixed 2-bus, 2-generator,
1-line topology with sliders for the values worth exploring interactively
(demand, line limit, ramp limits) — this is a demo of the model's
behavior, not a general network editor. A network editor is listed as a
possible next step in PROJECT_BRIEF.md.

Run with:  streamlit run app/streamlit_app.py
"""

import streamlit as st

from ed_model.data.schema import Bus, Line, Generator, System
from ed_model.model.builder import build_ed_model
from ed_model.solve import solve_ed, recommended_solver
from ed_model.viz import plot_dispatch_stack, plot_lmp_heatmap, plot_line_loading

st.set_page_config(page_title="Economic Dispatch (DC-OPF) Demo", layout="wide")

st.title("Economic Dispatch — DC-OPF Demo")
st.caption(
    "A fixed 2-bus, 2-generator, single-line system. Adjust the sliders to see how "
    "demand, ramping, and line capacity change dispatch, cost, and locational marginal prices."
)

with st.sidebar:
    st.header("System parameters")

    st.subheader("Demand (MW)")
    demand_a_t1 = st.slider("Bus A demand, period 1", 0, 300, 120)
    demand_a_t2 = st.slider("Bus A demand, period 2", 0, 300, 150)
    demand_b_t1 = st.slider("Bus B demand, period 1", 0, 300, 60)
    demand_b_t2 = st.slider("Bus B demand, period 2", 0, 300, 90)

    st.subheader("Line A-B")
    line_limit = st.slider("Thermal limit (MW)", 10, 300, 100)
    susceptance = st.slider("Susceptance (p.u.)", 1.0, 50.0, 10.0)

    st.subheader("Generator G1 (Bus A)")
    g1_p_max = st.slider("G1 p_max (MW)", 50, 400, 250)
    g1_ramp = st.slider("G1 ramp up/down (MW/period)", 5, 400, 100)
    g1_c1 = st.slider("G1 linear cost ($/MWh)", 5, 50, 12)

    st.subheader("Generator G2 (Bus B)")
    g2_p_max = st.slider("G2 p_max (MW)", 50, 400, 200)
    g2_ramp = st.slider("G2 ramp up/down (MW/period)", 5, 400, 100)
    g2_c1 = st.slider("G2 linear cost ($/MWh)", 5, 50, 20)

try:
    system = System(
        buses=[Bus(name="A", is_reference=True), Bus(name="B")],
        lines=[Line(name="L1", from_bus="A", to_bus="B", susceptance=susceptance, limit=line_limit)],
        generators=[
            Generator(
                name="G1", bus="A", p_min=0, p_max=g1_p_max,
                c2=0.01, c1=g1_c1, c0=0,
                ramp_up=g1_ramp, ramp_down=g1_ramp, p_initial=g1_p_max / 2,
            ),
            Generator(
                name="G2", bus="B", p_min=0, p_max=g2_p_max,
                c2=0.02, c1=g2_c1, c0=0,
                ramp_up=g2_ramp, ramp_down=g2_ramp, p_initial=g2_p_max / 2,
            ),
        ],
        demand={"A": [demand_a_t1, demand_a_t2], "B": [demand_b_t1, demand_b_t2]},
    )

    model = build_ed_model(system)
    result = solve_ed(model, solver_name=recommended_solver(system))

    col1, col2, col3 = st.columns(3)
    col1.metric("Total cost", f"${result.total_cost:,.2f}")
    col2.metric("LMP, Bus A (period 1)", f"${result.lmp[('A', 1)]:.2f}/MWh")
    col3.metric("LMP, Bus B (period 1)", f"${result.lmp[('B', 1)]:.2f}/MWh")

    if abs(result.lmp[("A", 1)] - result.lmp[("B", 1)]) > 1e-3:
        st.info("Line is congested in period 1 — LMPs diverge between buses.")

    st.subheader("Dispatch")
    st.pyplot(plot_dispatch_stack(system, result))

    col4, col5 = st.columns(2)
    with col4:
        st.subheader("Locational marginal prices")
        st.pyplot(plot_lmp_heatmap(system, result))
    with col5:
        st.subheader("Line loading")
        st.pyplot(plot_line_loading(system, result))

except ValueError as e:
    st.error(f"Invalid system configuration: {e}")
except RuntimeError as e:
    st.error(f"Solve failed: {e}")
