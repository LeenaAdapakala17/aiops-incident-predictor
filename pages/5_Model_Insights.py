import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import init_session
from model.predictor import feature_importance, DOMAIN_FEATURES, get_model_meta, retrain_on_live_data

DOMAIN_ICONS = {"kubernetes": "☸️", "cloud": "☁️", "network": "🌐", "application": "📦"}

METRIC_EXPLANATIONS = {
    "kubernetes": {
        "memory_usage_pct":       "Pod memory as % of node allocatable. Above 85% signals pressure.",
        "cpu_usage_pct":          "Pod CPU utilisation. Sustained spikes precede throttling.",
        "restart_count_5m":       "Container restarts in last 5 minutes. High = instability.",
        "oom_events":             "Out-of-memory kills. Any value > 0 is a strong incident signal.",
        "mem_limit_ratio":        "Memory used vs memory limit. >1.0 means the pod exceeded its limit.",
        "cpu_throttle_rate_pct":  "% of CPU cycles being throttled by cgroup limits.",
        "pending_time_sec":       "Seconds the pod has been stuck in Pending — scheduling pressure.",
    },
    "cloud": {
        "cpu_usage_pct":      "Azure VM CPU. Sustained >90% triggers scale and throttle warnings.",
        "memory_usage_pct":   "VM memory. >92% risks host-level OOM.",
        "disk_iops_pct":      "IOPS used as % of provisioned limit. Azure throttles at ~85%.",
        "storage_throttle":   "Binary: 1 if Azure Storage throttling is currently active.",
        "quota_used_pct":     "Subscription quota consumed. >95% blocks new resource creation.",
        "network_out_mbps":   "Outbound throughput in Mbps. Spikes signal traffic anomalies.",
    },
    "network": {
        "latency_ms":              "End-to-end latency in ms. >1000ms is critical for most services.",
        "packet_loss_pct":         "% packets dropped. Even 1–2% degrades TCP significantly.",
        "dns_failures_5m":         "DNS resolution failures in last 5 minutes.",
        "ingress_saturation_pct":  "AKS Ingress / Load Balancer capacity used. >90% queues requests.",
        "tcp_retransmit_pct":      "TCP retransmissions as % of total. High = network instability.",
    },
    "application": {
        "error_rate_5xx_pct":     "Server error rate. >5% warning, >10% critical.",
        "response_time_p99_ms":   "99th percentile response time — worst-case user experience.",
        "heap_usage_pct":         "JVM/app heap. Sustained >85% indicates a memory leak.",
        "thread_pool_active_pct": "% of thread pool in use. >90% causes request queuing.",
        "gc_pause_ms":            "GC pause time. High values freeze application threads.",
        "requests_per_sec":       "Throughput. Sudden drops or spikes often precede incidents.",
    },
}

def render():
    init_session()
    st.markdown("## 🧠 Model Insights")
    st.caption("Feature importance, risk distributions, and model behaviour — updated live as the collector accumulates data.")

    domain = st.selectbox("Domain", ["kubernetes", "cloud", "network", "application"],
                          format_func=lambda d: f"{DOMAIN_ICONS[d]} {d.capitalize()}")

    df = st.session_state.history.get(domain, pd.DataFrame())
    meta = get_model_meta().get(domain, {})

    # ── Training status banner ──────────────────────────────────────────────────
    source = meta.get("source", "Synthetic (startup)")
    is_live = "Live" in source
    banner_color = "#D1FAE5" if is_live else "#FEF9C3"
    banner_border = "#10B981" if is_live else "#F59E0B"
    banner_icon   = "🟢" if is_live else "🟡"
    st.markdown(
        f"<div style='background:{banner_color};border-left:4px solid {banner_border};"
        f"padding:10px 16px;border-radius:6px;margin-bottom:16px'>"
        f"{banner_icon} <b>Model training source:</b> {source} &nbsp;|&nbsp; "
        f"<b>Last trained:</b> {meta.get('trained_at','—')} &nbsp;|&nbsp; "
        f"<b>Incident rate in training data:</b> {meta.get('incident_rate','—')}"
        f"</div>", unsafe_allow_html=True
    )

    # Manual retrain button
    col_btn, col_info = st.columns([2, 5])
    with col_btn:
        can_retrain = not df.empty and len(df) >= 50
        if st.button("🔁 Retrain on live data now", disabled=not can_retrain, use_container_width=True):
            with st.spinner("Retraining..."):
                new_meta = retrain_on_live_data(domain, df)
            st.success(f"✅ Retrained on {new_meta['live_rows']} live + {new_meta['synthetic_rows']} synthetic rows.")
            st.rerun()
    with col_info:
        if not can_retrain:
            st.caption("⚠️ Need at least 50 live rows to retrain. Keep the collector running.")
        else:
            st.caption(f"✅ {len(df)} live rows available. Auto-retrain triggers every 50 scrapes.")

    st.markdown("---")

    # ── Feature importance + risk distribution ──────────────────────────────────
    with st.spinner("Computing feature importance..."):
        imp_df = feature_importance(domain)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Feature importance")
        st.caption("Recalculated from the current model — updates after every retrain.")
        fig = px.bar(imp_df, x="importance", y="feature", orientation="h",
                     color="importance", color_continuous_scale="Blues",
                     labels={"importance": "Importance", "feature": "Metric"}, height=360)
        fig.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### Risk score distribution")
        st.caption("Built from your live collected data — updates every scrape.")
        if not df.empty and "risk_15m" in df.columns:
            fig2 = px.histogram(df, x="risk_15m", color="severity", nbins=25,
                                color_discrete_map={"Critical": "#EF4444", "Warning": "#F59E0B", "Healthy": "#10B981"},
                                labels={"risk_15m": "Risk score (15m %)", "severity": "Severity"}, height=360)
            fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Start the collector to see your live risk distribution here.")

    # ── Live metric trends ───────────────────────────────────────────────────────
    if not df.empty:
        st.markdown("---")
        st.markdown("### Live metric trends")
        st.caption("Select any metric to see how it has evolved across all entities since collection started.")
        feats = DOMAIN_FEATURES[domain]
        available_feats = [f for f in feats if f in df.columns]
        selected_feat = st.selectbox("Metric", available_feats,
                                     format_func=lambda f: f"{f}  —  {METRIC_EXPLANATIONS[domain].get(f,'')[:50]}")
        df_plot = df[["timestamp", "entity", selected_feat]].copy()
        df_plot["timestamp"] = pd.to_datetime(df_plot["timestamp"])
        fig3 = px.line(df_plot, x="timestamp", y=selected_feat, color="entity",
                       title=f"{selected_feat} over time — all entities",
                       labels={"timestamp": "Time", selected_feat: selected_feat}, height=340)
        fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig3, use_container_width=True)

    # ── Metric reference ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Metric reference")
    for feat, desc in METRIC_EXPLANATIONS.get(domain, {}).items():
        st.markdown(f"**`{feat}`** — {desc}")

    # ── Model card ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Model card")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Algorithm",        "Random Forest")
    c2.metric("Estimators",       "150")
    c3.metric("Training rows",    meta.get("rows", "3,000"))
    c4.metric("Live rows used",   meta.get("live_rows", 0))
    c5.metric("Features",         len(DOMAIN_FEATURES[domain]))

    st.markdown("""
**Severity thresholds:** 🔴 Critical ≥ 70% · 🟡 Warning 40–69% · 🟢 Healthy < 40%

**Horizons:** 15 min (direct model output) · 30 min · 60 min (probabilistic extrapolation)

**Auto-retrain:** Every 50 scrapes the model retrains on your live data blended with synthetic samples to maintain class balance.
    """)

render()
