import streamlit as st
import pandas as pd
import plotly.express as px
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import init_session

DOMAIN_ICONS = {"kubernetes": "☸️", "cloud": "☁️", "network": "🌐", "application": "📦"}

def render():
    init_session()
    st.markdown("## 📋 Incident Log")
    st.caption("Full history of all Critical and Warning events since collection started — auto-updates every scrape.")

    total = sum(len(v) for v in st.session_state.history.values())
    if total == 0:
        st.warning("No data yet — start the collector on **📡 Data Collector**.")
        if st.session_state.collector_running:
            time.sleep(2)
            st.rerun()
        return

    parts = []
    for domain, df in st.session_state.history.items():
        if df.empty or "severity" not in df.columns:
            continue
        flagged = df[df["severity"].isin(["Critical", "Warning"])].copy()
        flagged["domain"] = domain.capitalize()
        parts.append(flagged)

    if not parts:
        st.success("✅ No incidents in history yet. All systems have been healthy.")
        if st.session_state.collector_running:
            time.sleep(st.session_state.get("interval", 10))
            st.rerun()
        return

    log = pd.concat(parts, ignore_index=True)
    log["timestamp"] = pd.to_datetime(log["timestamp"])
    log = log.sort_values("timestamp", ascending=False).reset_index(drop=True)

    # ── Summary ───────────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total incidents",   len(log))
    c2.metric("🔴 Critical",       (log["severity"] == "Critical").sum())
    c3.metric("🟡 Warning",        (log["severity"] == "Warning").sum())
    c4.metric("Domains affected",  log["domain"].nunique())
    c5.metric("Entities affected", log["entity"].nunique() if "entity" in log else "—")

    st.markdown("---")

    # ── Filters ───────────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns(3)
    with f1:
        dom_filter = st.multiselect("Domain", sorted(log["domain"].unique()),
                                    default=sorted(log["domain"].unique()))
    with f2:
        sev_filter = st.multiselect("Severity", ["Critical","Warning"], default=["Critical","Warning"])
    with f3:
        min_risk = st.slider("Min risk score (15m)", 0, 100, 40)

    filtered = log[
        log["domain"].isin(dom_filter) &
        log["severity"].isin(sev_filter) &
        (log["risk_15m"] >= min_risk)
    ]

    st.markdown(f"**{len(filtered)} events** match filters.")

    if not filtered.empty:
        # Timeline
        fig = px.scatter(filtered, x="timestamp", y="risk_15m",
                         color="severity", symbol="domain", size="risk_15m",
                         color_discrete_map={"Critical":"#EF4444","Warning":"#F59E0B"},
                         hover_data=["entity","rca_type","risk_30m","risk_60m"] if "rca_type" in filtered.columns else ["entity"],
                         title="Incident timeline", height=360,
                         labels={"risk_15m":"Risk (15m %)","timestamp":"Time"})
        fig.add_hline(y=70, line_dash="dash", line_color="#EF4444")
        fig.add_hline(y=40, line_dash="dash", line_color="#F59E0B")
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

        # Domain breakdown
        breakdown = filtered.groupby(["domain","severity"]).size().reset_index(name="count")
        fig2 = px.bar(breakdown, x="domain", y="count", color="severity",
                      color_discrete_map={"Critical":"#EF4444","Warning":"#F59E0B"},
                      title="Incidents by domain", barmode="stack", height=280)
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)

        # Incident rate over time
        filtered_time = filtered.set_index("timestamp").resample("1min").size().reset_index(name="count")
        if len(filtered_time) > 1:
            fig3 = px.area(filtered_time, x="timestamp", y="count",
                           title="Incident rate over time (per minute)",
                           color_discrete_sequence=["#EF4444"], height=220)
            fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig3, use_container_width=True)

        # Full log
        st.markdown("### Full incident log")
        show_cols = ["timestamp","domain","entity","severity","risk_15m","risk_30m","risk_60m"]
        if "rca_type" in filtered.columns:
            show_cols.append("rca_type")
        show_cols = [c for c in show_cols if c in filtered.columns]
        st.dataframe(filtered[show_cols].reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        csv = filtered.to_csv(index=False).encode()
        st.download_button("⬇️ Export incident log CSV", csv, "incident_log.csv", "text/csv")

    # ── Auto-refresh ──────────────────────────────────────────────────────────────
    if st.session_state.collector_running:
        time.sleep(st.session_state.get("interval", 10))
        st.rerun()

render()
