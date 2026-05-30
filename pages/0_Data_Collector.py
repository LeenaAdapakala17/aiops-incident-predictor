import streamlit as st
import pandas as pd
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import (init_session, append_history, reset_session,
                                update_slo, log_alert, propagate_cascades)
from collector.real_metrics     import scrape_real_metrics, get_system_summary
from collector.streamer         import scrape as sim_scrape
from collector.prometheus_client import (scrape_prometheus, test_connection,
                                         get_available_metrics)
from model.predictor            import predict, retrain_on_live_data, get_models
from model.rca_engine           import enrich_with_rca

DOMAINS       = ["kubernetes", "cloud", "network", "application"]
DOMAIN_ICONS  = {"kubernetes": "☸️", "cloud": "☁️", "network": "🌐", "application": "📦"}
RETRAIN_EVERY = 50

@st.cache_resource(show_spinner=False)
def warmup_models():
    get_models()
    return True

def highlight(val):
    if isinstance(val, float) and val > 0.6:
        return "background-color:#FEE2E2"
    if isinstance(val, float) and val > 0.3:
        return "background-color:#FEF9C3"
    return ""

def _do_scrape():
    mode = st.session_state.get("mode", "simulation")

    if mode == "prometheus":
        url  = st.session_state.get("prometheus_url", "")
        data = scrape_prometheus(url)
        for domain in DOMAINS:
            df = data.get(domain, pd.DataFrame())
            if df.empty:
                continue
            df["domain"] = domain
            scored   = predict(domain, df)
            enriched = enrich_with_rca(domain, scored)
            append_history(domain, enriched)
            update_slo(enriched)
            for _, row in enriched[enriched["severity"].isin(["Critical","Warning"])].iterrows():
                log_alert(domain, row["entity"], row.get("rca_type","Unknown"),
                          row["severity"], float(row["risk_15m"]))


    else:  # simulation
        propagate_cascades()
        for domain in DOMAINS:
            raw = sim_scrape(st.session_state.states[domain])
            raw["domain"] = domain
            scored   = predict(domain, raw)
            enriched = enrich_with_rca(domain, scored)
            append_history(domain, enriched)
            update_slo(enriched)
            for _, row in enriched[enriched["severity"].isin(["Critical","Warning"])].iterrows():
                log_alert(domain, row["entity"], row.get("rca_type","Unknown"),
                          row["severity"], float(row["risk_15m"]))

    st.session_state.scrape_count += 1
    count = st.session_state.scrape_count
    if count > 0 and count % RETRAIN_EVERY == 0:
        for domain in DOMAINS:
            live_df = st.session_state.history.get(domain, pd.DataFrame())
            if len(live_df) >= 50:
                retrain_on_live_data(domain, live_df)
        st.toast(f"🧠 Models retrained on {count} scrapes of live data!", icon="✅")

def _switch_mode(new_mode: str):
    current_mode = st.session_state.mode
    if current_mode != new_mode:
        st.session_state.mode = new_mode
        reset_session()
        st.session_state.mode = new_mode

def render():
    init_session()

    if "models_ready" not in st.session_state:
        with st.spinner("⚙️ Initialising ML models... (~3 seconds)"):
            warmup_models()
        st.session_state.models_ready = True

    st.markdown("## 📡 Data Collector")
    st.caption("Choose a data source, then start the collector. All other pages update automatically.")

    # ── Mode selector ─────────────────────────────────────────────────────────
    st.markdown("### Data source")
    mode = st.session_state.get("mode", "simulation")

    col1, col2 = st.columns(2)
    with col1:
        sim_type   = "primary"   if mode == "simulation" else "secondary"
        sim_label  = "✅ AKS Simulation — ACTIVE" if mode == "simulation" else "☸️ AKS Simulation"
        if st.button(sim_label, use_container_width=True, type=sim_type):
            _switch_mode("simulation")
            st.rerun()
    with col2:
        prom_type  = "primary"   if mode == "prometheus" else "secondary"
        prom_label = "✅ Prometheus — ACTIVE" if mode == "prometheus" else "🔥 Prometheus Endpoint"
        if st.button(prom_label, use_container_width=True, type=prom_type):
            _switch_mode("prometheus")
            st.rerun()

    # ── Mode banners ──────────────────────────────────────────────────────────
    if mode == "simulation":
        st.markdown(
            "<div style='background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;"
            "padding:10px 16px;font-size:13px;color:#166534;margin:8px 0'>"
            "☸️ <b>AKS Simulation Mode</b> — Realistic Azure Kubernetes cluster with real pod names, "
            "Azure VMs, and microservices. Anomalies build gradually, cascade across services, "
            "and self-heal. Full RCA with accurate kubectl and az commands. <b>Best for demos.</b>"
            "</div>", unsafe_allow_html=True
        )


    elif mode == "prometheus":
        st.markdown(
            "<div style='background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;"
            "padding:10px 16px;font-size:13px;color:#9A3412;margin:8px 0'>"
            "🔥 <b>Prometheus Mode</b> — Connect to any Prometheus endpoint. "
            "Paste your URL below. Works with local Prometheus, Grafana Agent, "
            "Azure Monitor, or any Prometheus-compatible endpoint."
            "</div>", unsafe_allow_html=True
        )

        # URL input
        prom_url = st.text_input(
            "Prometheus URL",
            value=st.session_state.get("prometheus_url", ""),
            placeholder="http://localhost:9090  or  http://your-prometheus:9090",
            help="The base URL of your Prometheus instance"
        )

        col_test, col_metrics = st.columns([2, 3])
        with col_test:
            if st.button("🔌 Test connection", use_container_width=True):
                if prom_url:
                    with st.spinner("Testing..."):
                        ok, msg = test_connection(prom_url)
                    st.session_state.prometheus_url = prom_url
                    st.session_state.prometheus_ok  = ok
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.warning("Please enter a Prometheus URL first.")

        with col_metrics:
            if st.session_state.get("prometheus_ok") and prom_url:
                if st.button("📋 List available metrics", use_container_width=True):
                    with st.spinner("Fetching metrics..."):
                        metrics = get_available_metrics(prom_url)
                    if metrics:
                        st.info(f"Found {len(metrics)} metrics. Samples: {', '.join(metrics[:8])}")
                    else:
                        st.warning("No metrics found — check your Prometheus is scraping targets.")

        # Save URL to session
        if prom_url:
            st.session_state.prometheus_url = prom_url

        # Show connection status
        if st.session_state.get("prometheus_ok"):
            st.success(f"🟢 Connected to: {st.session_state.prometheus_url}")
        elif st.session_state.get("prometheus_url"):
            st.warning("⚠️ Not tested yet — click **Test connection** before starting the collector.")

        # Example URLs
        with st.expander("📖 Example Prometheus URLs"):
            st.markdown("""
| Setup | URL |
|---|---|
| Local Prometheus | `http://localhost:9090` |
| Docker Compose | `http://prometheus:9090` |
| Kubernetes (port-forward) | `http://localhost:9090` after `kubectl port-forward svc/prometheus 9090` |
| Grafana Cloud | `https://<stack>.grafana.net/prometheus` (needs auth) |
| Azure Monitor | Not directly supported — use Grafana Agent |
            """)

    st.markdown("---")

    # ── Controls ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        interval = st.selectbox("Scrape interval", [5, 10, 15, 30], index=1,
                                format_func=lambda x: f"Every {x}s")
        st.session_state.interval = interval
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        # Disable start if prometheus mode but not connected
        prom_not_ready = (mode == "prometheus" and
                          not st.session_state.get("prometheus_ok") and
                          not st.session_state.get("prometheus_url"))
        if not st.session_state.collector_running:
            if st.button("▶️ Start collector", use_container_width=True,
                         disabled=prom_not_ready):
                st.session_state.collector_running = True
                st.rerun()
        else:
            if st.button("⏹ Stop collector", use_container_width=True):
                st.session_state.collector_running = False
                st.rerun()
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset all data", use_container_width=True):
            current_mode = st.session_state.mode
            prom_url     = st.session_state.get("prometheus_url", "")
            prom_ok      = st.session_state.get("prometheus_ok", False)
            reset_session()
            st.session_state.mode           = current_mode
            st.session_state.prometheus_url = prom_url
            st.session_state.prometheus_ok  = prom_ok
            st.rerun()
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📸 Scrape once", use_container_width=True):
            _do_scrape()
            st.rerun()

    # ── Status bar ────────────────────────────────────────────────────────────
    st.markdown("---")
    total_rows   = sum(len(v) for v in st.session_state.history.values())
    all_critical = sum(
        (v["severity"] == "Critical").sum()
        for v in st.session_state.history.values()
        if not v.empty and "severity" in v.columns
    )
    mode_label   = {"simulation": "simulation", "prometheus": "Prometheus"}
    status_color = "#10B981" if st.session_state.collector_running else "#6B7280"
    status_label = (f"🟢 Collecting ({mode_label.get(mode,'?')})"
                    if st.session_state.collector_running else "⚫ Stopped")

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.markdown(f"**Status**<br><span style='color:{status_color};font-weight:700'>{status_label}</span>",
                unsafe_allow_html=True)
    s2.metric("Scrapes completed",  st.session_state.scrape_count)
    s3.metric("Total rows",         total_rows)
    s4.metric("🔴 Critical",        int(all_critical))
    s5.metric("Next retrain",
              f"scrape {((st.session_state.scrape_count // RETRAIN_EVERY) + 1) * RETRAIN_EVERY}")

    # ── Live stream ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Live metric stream")
    src_label = {"simulation": "AKS simulation", "real": "real host metrics",
                 "prometheus": f"Prometheus ({st.session_state.get('prometheus_url','')})"}
    st.caption(f"Most recent 8 rows per domain — {src_label.get(mode, '')}.")

    if total_rows == 0:
        st.info("No data yet. Press **▶️ Start collector** or **📸 Scrape once** to begin.")
    else:
        tabs = st.tabs([f"{DOMAIN_ICONS[d]} {d.capitalize()}" for d in DOMAINS])
        for tab, domain in zip(tabs, DOMAINS):
            with tab:
                df = st.session_state.history[domain]
                if df.empty:
                    st.info("No data for this domain yet.")
                    continue
                latest = df.tail(8).reset_index(drop=True)
                crit   = int((df["severity"] == "Critical").sum()) if "severity" in df.columns else 0
                warn   = int((df["severity"] == "Warning").sum())  if "severity" in df.columns else 0
                heal   = int((df["severity"] == "Healthy").sum())  if "severity" in df.columns else 0
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Rows collected", len(df))
                m2.metric("🔴 Critical",    crit)
                m3.metric("🟡 Warning",     warn)
                m4.metric("🟢 Healthy",     heal)
                if "anomaly_pressure" in latest.columns:
                    st.dataframe(
                        latest.style.map(highlight, subset=["anomaly_pressure"]),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.dataframe(latest, use_container_width=True, hide_index=True)

    # ── Auto-loop ─────────────────────────────────────────────────────────────
    if st.session_state.collector_running:
        _do_scrape()
        time.sleep(st.session_state.interval)
        st.rerun()

render()
