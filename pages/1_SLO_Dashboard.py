import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import init_session

SLO_TARGET = 99.5   # % availability target
ERROR_BUDGET = 100 - SLO_TARGET  # 0.5% allowed downtime

def availability(tracker: dict) -> float:
    if tracker["total"] == 0:
        return 100.0
    return round(tracker["healthy"] / tracker["total"] * 100, 3)

def error_budget_remaining(avail: float) -> float:
    """% of error budget remaining. 100% = full budget, 0% = exhausted."""
    burned = max(0, SLO_TARGET - avail)
    return round(max(0, (ERROR_BUDGET - burned) / ERROR_BUDGET * 100), 1)

def burn_rate(avail: float) -> float:
    """How fast error budget is burning vs target. >1 = burning too fast."""
    if avail >= 100:
        return 0.0
    error_rate = (100 - avail) / 100
    target_error_rate = (100 - SLO_TARGET) / 100
    return round(error_rate / (target_error_rate + 1e-9), 2)

def render():
    init_session()
    st.markdown("## 📊 SLO Dashboard")
    st.caption(f"Service Level Objectives — target availability: **{SLO_TARGET}%** · Error budget: **{ERROR_BUDGET}%**")

    total_rows = sum(len(v) for v in st.session_state.history.values())
    if total_rows == 0:
        st.warning("No data yet — start the collector on **📡 Data Collector** first.")
        if st.session_state.collector_running:
            time.sleep(2)
            st.rerun()
        return

    tracker = st.session_state.slo_tracker
    alert_log = st.session_state.get("alert_log", [])

    # ── Overall SLO health ────────────────────────────────────────────────────
    avails = {svc: availability(t) for svc, t in tracker.items() if t["total"] > 0}
    if not avails:
        st.info("Collecting baseline data... keep the collector running.")
        return

    overall_avail  = round(sum(avails.values()) / len(avails), 3)
    slo_met        = overall_avail >= SLO_TARGET
    budget_left    = error_budget_remaining(overall_avail)
    overall_burn   = burn_rate(overall_avail)

    banner_bg     = "#F0FDF4" if slo_met else "#FEF2F2"
    banner_border = "#10B981" if slo_met else "#EF4444"
    banner_icon   = "✅" if slo_met else "🚨"
    banner_msg    = (f"{banner_icon} SLO Met — Overall availability {overall_avail}%"
                     if slo_met else
                     f"{banner_icon} SLO BREACH — Overall availability {overall_avail}% (target {SLO_TARGET}%)")

    st.markdown(
        f"<div style='background:{banner_bg};border-left:5px solid {banner_border};"
        f"padding:12px 18px;border-radius:8px;font-size:16px;font-weight:600;margin-bottom:16px'>"
        f"{banner_msg}</div>", unsafe_allow_html=True
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Overall availability",  f"{overall_avail}%",
              delta=f"{overall_avail - SLO_TARGET:+.2f}% vs SLO")
    m2.metric("Error budget remaining", f"{budget_left}%",
              delta="OK" if budget_left > 50 else "⚠️ Low")
    m3.metric("Burn rate",             f"{overall_burn}x",
              delta="normal" if overall_burn <= 1 else "🔥 fast")
    m4.metric("Services tracked",      len(avails))
    m5.metric("Alerts fired",          len(alert_log))

    st.markdown("---")

    # ── Per-service availability table ────────────────────────────────────────
    st.markdown("### Per-service SLO status")
    rows = []
    for svc, avail in sorted(avails.items(), key=lambda x: x[1]):
        br   = burn_rate(avail)
        budget = error_budget_remaining(avail)
        status = "✅ Met" if avail >= SLO_TARGET else "🚨 Breach"
        rows.append({
            "Service":            svc,
            "Availability %":     avail,
            "SLO Status":         status,
            "Error Budget Left %":budget,
            "Burn Rate":          br,
            "Scrapes":            tracker[svc]["total"],
        })
    slo_df = pd.DataFrame(rows).sort_values("Availability %")
    st.dataframe(slo_df, use_container_width=True, hide_index=True)

    # ── Availability gauge chart ──────────────────────────────────────────────
    st.markdown("### Availability by service")
    fig = go.Figure()
    colors = ["#EF4444" if a < SLO_TARGET else "#10B981" for a in slo_df["Availability %"]]
    fig.add_trace(go.Bar(
        x=slo_df["Service"], y=slo_df["Availability %"],
        marker_color=colors,
        text=slo_df["Availability %"].apply(lambda v: f"{v:.2f}%"),
        textposition="outside"
    ))
    fig.add_hline(y=SLO_TARGET, line_dash="dash", line_color="#F59E0B",
                  annotation_text=f"SLO target ({SLO_TARGET}%)")
    fig.update_layout(
        yaxis=dict(range=[max(0, min(avails.values())-2), 100.5], title="Availability %"),
        height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Error budget burn gauge ───────────────────────────────────────────────
    st.markdown("### Error budget remaining")
    fig2 = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=budget_left,
        title={"text": "Error budget remaining (%)"},
        delta={"reference": 100, "suffix": "%"},
        gauge={
            "axis":  {"range": [0, 100]},
            "bar":   {"color": "#10B981" if budget_left > 50 else "#F59E0B" if budget_left > 20 else "#EF4444"},
            "steps": [
                {"range": [0, 20],   "color": "#FEF2F2"},
                {"range": [20, 50],  "color": "#FFFBEB"},
                {"range": [50, 100], "color": "#F0FDF4"},
            ],
            "threshold": {"line": {"color": "#EF4444", "width": 4}, "thickness": 0.75, "value": 20}
        }
    ))
    fig2.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, use_container_width=True)

    # ── Cascade dependency map ─────────────────────────────────────────────────
    st.markdown("### Cascade dependency map")
    st.caption("Shows which services impact others when they fail.")
    cascade_rows = [
        {"Upstream (failing)": "database-proxy", "Downstream (impacted)": "backend-api, frontend",      "Effect": "Error rate ↑, Response time ↑"},
        {"Upstream (failing)": "message-broker",  "Downstream (impacted)": "order-processor, notification-svc", "Effect": "Thread pool ↑, Error rate ↑"},
        {"Upstream (failing)": "auth-api",         "Downstream (impacted)": "gateway-proxy",             "Effect": "Latency ↑, Pending pods ↑"},
        {"Upstream (failing)": "auth-service",     "Downstream (impacted)": "frontend, backend-api",     "Effect": "Error rate ↑, Response time ↑"},
        {"Upstream (failing)": "cache-mgr",        "Downstream (impacted)": "data-pipeline",             "Effect": "Memory ↑, CPU ↑"},
        {"Upstream (failing)": "vm-prod-001",      "Downstream (impacted)": "payment-svc, auth-api",     "Effect": "OOMKill risk ↑, CPU throttle ↑"},
        {"Upstream (failing)": "vm-prod-002",      "Downstream (impacted)": "order-processor, gateway-proxy", "Effect": "Restart count ↑, Pending ↑"},
    ]
    st.dataframe(pd.DataFrame(cascade_rows), use_container_width=True, hide_index=True)

    # ── Deduplicated alert log ────────────────────────────────────────────────
    if alert_log:
        st.markdown("---")
        st.markdown("### 🔔 Deduplicated alert log")
        st.caption("Repeated alerts for the same entity+type are suppressed. Only first occurrence shown.")
        alert_df = pd.DataFrame(alert_log[-50:]).sort_values("timestamp", ascending=False)
        st.dataframe(alert_df, use_container_width=True, hide_index=True)

    if st.session_state.collector_running:
        time.sleep(st.session_state.get("interval", 10))
        st.rerun()

render()
