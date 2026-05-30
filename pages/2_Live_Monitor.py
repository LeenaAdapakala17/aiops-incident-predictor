import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import sys, os, math
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import init_session

DOMAIN_ICONS = {"kubernetes": "☸️", "cloud": "☁️", "network": "🌐", "application": "📦"}
SEV_COLOR    = {"Critical": "#EF4444", "Warning": "#F59E0B", "Healthy": "#10B981"}

def render():
    init_session()
    st.markdown("## 🔴 Live Monitor")
    st.caption("Risk scores update automatically every scrape cycle. No manual refresh needed.")

    total = sum(len(v) for v in st.session_state.history.values())
    if total == 0:
        st.warning("No data yet — go to **📡 Data Collector** and press **▶️ Start collector** first.")
        if st.session_state.collector_running:
            time.sleep(2)
            st.rerun()
        return

    # ── Global health banner ──────────────────────────────────────────────────────
    all_dfs = [df for df in st.session_state.history.values() if not df.empty and "severity" in df.columns]
    latest_rows = pd.concat([df.groupby("entity").last().reset_index() for df in all_dfs], ignore_index=True)

    total_entities = len(latest_rows)
    crit = (latest_rows["severity"] == "Critical").sum()
    warn = (latest_rows["severity"] == "Warning").sum()
    heal = (latest_rows["severity"] == "Healthy").sum()
    avg_risk = latest_rows["risk_15m"].mean() if "risk_15m" in latest_rows else 0

    # Health banner colour
    if crit > 0:
        banner_bg, banner_border, banner_msg = "#FEF2F2", "#EF4444", f"🔴 {int(crit)} CRITICAL incident(s) detected across your infrastructure"
    elif warn > 0:
        banner_bg, banner_border, banner_msg = "#FFFBEB", "#F59E0B", f"🟡 {int(warn)} warning(s) detected — monitor closely"
    else:
        banner_bg, banner_border, banner_msg = "#F0FDF4", "#10B981", "🟢 All systems healthy"

    # Time-of-day load indicator
    hour = datetime.utcnow().hour
    tod_pct = round((0.35 + 0.65 * max(0, math.sin(math.pi * (hour - 6) / 14))) * 100)
    is_business = 8 <= hour <= 18
    tod_label = f"🌞 Business hours (UTC {hour:02d}:00)" if is_business else f"🌙 Off-peak (UTC {hour:02d}:00)"
    tod_color = "#F59E0B" if is_business else "#3B82F6"

    st.markdown(
        f"<div style='background:{banner_bg};border-left:5px solid {banner_border};"
        f"padding:12px 18px;border-radius:8px;font-size:16px;font-weight:600;margin-bottom:8px'>"
        f"{banner_msg}</div>", unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"
        f"padding:8px 16px;margin-bottom:16px;font-size:13px;color:#475569'>"
        f"{tod_label} &nbsp;·&nbsp; "
        f"<b style='color:{tod_color}'>Traffic load: {tod_pct}% of peak</b> &nbsp;·&nbsp; "
        f"Metrics scale automatically with time-of-day patterns"
        f"</div>", unsafe_allow_html=True
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total entities",   total_entities)
    m2.metric("🔴 Critical",      int(crit))
    m3.metric("🟡 Warning",       int(warn))
    m4.metric("🟢 Healthy",       int(heal))
    m5.metric("Avg risk (15m)",   f"{avg_risk:.1f}%")

    st.markdown("---")

    # ── Domain tabs ───────────────────────────────────────────────────────────────
    domain = st.selectbox("Domain", ["kubernetes", "cloud", "network", "application"],
                          format_func=lambda d: f"{DOMAIN_ICONS[d]} {d.capitalize()}")
    horizon = st.radio("Prediction horizon", ["15m", "30m", "60m"], horizontal=True)
    risk_col = f"risk_{horizon}"

    df = st.session_state.history[domain]
    if df.empty:
        st.info(f"No data yet for {domain}. Keep the collector running.")
    else:
        latest_by_entity = df.groupby("entity").last().reset_index()

        # ── Risk bar chart ────────────────────────────────────────────────────────
        fig = go.Figure()
        for sev, grp in latest_by_entity.groupby("severity"):
            fig.add_trace(go.Bar(
                x=grp["entity"], y=grp[risk_col],
                name=sev, marker_color=SEV_COLOR.get(sev, "#9CA3AF"),
                text=grp[risk_col].apply(lambda v: f"{v:.0f}%"),
                textposition="outside"
            ))
        fig.update_layout(
            title=f"Current risk per entity — next {horizon}",
            yaxis=dict(range=[0, 115], title="Risk score (%)"),
            xaxis_title="Entity", barmode="group", height=360,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend_title="Severity"
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Entity drill-down ─────────────────────────────────────────────────────
        st.markdown("### Entity drill-down")
        col_e, col_h = st.columns([3, 2])
        with col_e:
            entity = st.selectbox("Select entity", sorted(df["entity"].unique()))
        with col_h:
            show_metric = st.selectbox("Overlay metric", [c for c in df.columns if df[c].dtype in ['float64','int64']
                                        and c not in ["risk_15m","risk_30m","risk_60m","anomaly_pressure"]][:8])

        entity_df = df[df["entity"] == entity].copy()
        entity_df["timestamp"] = pd.to_datetime(entity_df["timestamp"])

        # Risk trend
        fig2 = go.Figure()
        colors = {"risk_15m": "#3B82F6", "risk_30m": "#8B5CF6", "risk_60m": "#F59E0B"}
        for col, label in [("risk_15m","15 min"),("risk_30m","30 min"),("risk_60m","60 min")]:
            if col in entity_df.columns:
                fig2.add_trace(go.Scatter(x=entity_df["timestamp"], y=entity_df[col],
                                          mode="lines", name=label,
                                          line=dict(color=colors[col], width=2)))
        fig2.add_hrect(y0=70, y1=115, fillcolor="#EF4444", opacity=0.06, line_width=0)
        fig2.add_hrect(y0=40, y1=70,  fillcolor="#F59E0B", opacity=0.06, line_width=0)
        fig2.add_hline(y=70, line_dash="dash", line_color="#EF4444", annotation_text="Critical (70%)")
        fig2.add_hline(y=40, line_dash="dash", line_color="#F59E0B", annotation_text="Warning (40%)")
        fig2.update_layout(title=f"Risk trend — {entity}", height=300,
                           yaxis=dict(range=[0, 110], title="Risk (%)"), xaxis_title="Time",
                           plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

        # Metric overlay
        if show_metric in entity_df.columns:
            fig3 = px.area(entity_df, x="timestamp", y=show_metric,
                           title=f"{show_metric} — {entity}",
                           color_discrete_sequence=["#3B82F6"], height=220)
            fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig3, use_container_width=True)

        # Latest readings table
        st.markdown("### Latest readings — all entities")
        show_cols = ["entity", risk_col, "severity"] + [
            c for c in latest_by_entity.columns
            if c not in ["entity","risk_15m","risk_30m","risk_60m","severity","domain",
                         "timestamp","anomaly_pressure","rca_type","rca_cause",
                         "rca_impact","rca_solutions","rca_commands"]
        ]
        show_cols = list(dict.fromkeys(show_cols))
        available = [c for c in show_cols if c in latest_by_entity.columns]
        st.dataframe(latest_by_entity[available].sort_values(risk_col, ascending=False),
                     use_container_width=True, hide_index=True)

    # ── Auto-refresh when collector is running ────────────────────────────────────
    if st.session_state.collector_running:
        time.sleep(st.session_state.get("interval", 10))
        st.rerun()

render()
