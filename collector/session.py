import streamlit as st
import pandas as pd
from collector.streamer import init_all_states, apply_cascades, smooth_risk

MAX_HISTORY = 500

def init_session():
    if "mode" not in st.session_state:
        st.session_state.mode = "simulation"  # "simulation", "real", or "prometheus"
    if "prometheus_url" not in st.session_state:
        st.session_state.prometheus_url = ""
    if "prometheus_ok" not in st.session_state:
        st.session_state.prometheus_ok = False
    if "collector_running" not in st.session_state:
        st.session_state.collector_running = False
    if "states" not in st.session_state:
        st.session_state.states = init_all_states()
    if "history" not in st.session_state:
        st.session_state.history = {d: pd.DataFrame() for d in ["kubernetes","cloud","network","application"]}
    if "scrape_count" not in st.session_state:
        st.session_state.scrape_count = 0
    if "interval" not in st.session_state:
        st.session_state.interval = 10
    if "slo_tracker" not in st.session_state:
        # SLO tracking: availability and error budget per service
        st.session_state.slo_tracker = {svc: {"total": 0, "healthy": 0} for svc in
            ["frontend","backend-api","database-proxy","message-broker","auth-service",
             "payment-svc","auth-api","order-processor","notification-svc","gateway-proxy"]}
    if "alert_log" not in st.session_state:
        st.session_state.alert_log = []   # deduped alert history

def append_history(domain: str, df: pd.DataFrame):
    existing = st.session_state.history[domain]
    combined = pd.concat([existing, df], ignore_index=True)
    if len(combined) > MAX_HISTORY:
        combined = combined.tail(MAX_HISTORY).reset_index(drop=True)
    st.session_state.history[domain] = combined

def update_slo(df: pd.DataFrame):
    """Track availability per entity for SLO dashboard."""
    if "severity" not in df.columns:
        return
    for _, row in df.iterrows():
        entity = row.get("entity","")
        if entity in st.session_state.slo_tracker:
            st.session_state.slo_tracker[entity]["total"] += 1
            if row["severity"] == "Healthy":
                st.session_state.slo_tracker[entity]["healthy"] += 1

def log_alert(domain: str, entity: str, rca_type: str, severity: str, risk: float):
    """Append to deduplicated alert log — skip if same entity+type alerted recently."""
    from datetime import datetime
    log = st.session_state.alert_log
    # Dedup: check last 10 alerts for same entity+type
    recent = [a for a in log[-10:] if a["entity"] == entity and a["rca_type"] == rca_type]
    if recent:
        return  # suppressed
    log.append({
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "domain":    domain,
        "entity":    entity,
        "rca_type":  rca_type,
        "severity":  severity,
        "risk_15m":  risk,
    })
    # Keep last 200 alerts
    st.session_state.alert_log = log[-200:]

def propagate_cascades():
    """Call cascade propagation across all domain states."""
    apply_cascades(st.session_state.states)

def reset_session():
    st.session_state.states            = init_all_states()
    st.session_state.history           = {d: pd.DataFrame() for d in ["kubernetes","cloud","network","application"]}
    st.session_state.scrape_count      = 0
    st.session_state.collector_running = False
    st.session_state.slo_tracker       = {svc: {"total": 0, "healthy": 0} for svc in
        ["frontend","backend-api","database-proxy","message-broker","auth-service",
         "payment-svc","auth-api","order-processor","notification-svc","gateway-proxy"]}
    st.session_state.alert_log         = []
