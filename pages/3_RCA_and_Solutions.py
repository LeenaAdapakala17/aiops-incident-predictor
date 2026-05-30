import streamlit as st
import pandas as pd
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from collector.session import init_session
from model.predictor import DOMAIN_FEATURES

DOMAIN_ICONS = {"kubernetes": "☸️", "cloud": "☁️", "network": "🌐", "application": "📦"}
SEV_COLOR    = {"Critical": "#EF4444", "Warning": "#F59E0B"}
SEV_BG       = {"Critical": "#FEF2F2", "Warning": "#FFFBEB"}

SKIP_COLS = {"entity","domain","timestamp","severity","rca_type","rca_cause",
             "rca_impact","rca_solutions","rca_commands","risk_15m","risk_30m",
             "risk_60m","anomaly_pressure"}

def render():
    init_session()
    st.markdown("## 🔍 RCA & Solutions")
    st.caption("Root cause, business impact, and step-by-step remediation — updated live every scrape cycle.")

    total = sum(len(v) for v in st.session_state.history.values())
    if total == 0:
        st.warning("No data yet — go to **📡 Data Collector** and press **▶️ Start collector**.")
        if st.session_state.collector_running:
            time.sleep(2)
            st.rerun()
        return

    # Collect latest incident per entity
    parts = []
    for domain, df in st.session_state.history.items():
        if df.empty or "rca_type" not in df.columns:
            continue
        flagged = df[df["severity"].isin(["Critical", "Warning"])].copy()
        flagged["domain"] = domain
        parts.append(flagged)

    if not parts:
        st.success("✅ All systems healthy — no incidents detected across any domain.")
        if st.session_state.collector_running:
            time.sleep(st.session_state.get("interval", 10))
            st.rerun()
        return

    all_inc = pd.concat(parts, ignore_index=True)
    all_inc["timestamp"] = pd.to_datetime(all_inc["timestamp"])
    latest = (all_inc.sort_values("timestamp")
                     .groupby(["domain", "entity"]).last()
                     .reset_index()
                     .sort_values("risk_15m", ascending=False)
                     .reset_index(drop=True))

    # ── Summary ───────────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active incidents",  len(latest))
    c2.metric("🔴 Critical",       (latest["severity"] == "Critical").sum())
    c3.metric("🟡 Warning",        (latest["severity"] == "Warning").sum())
    c4.metric("Domains affected",  latest["domain"].nunique())
    c5.metric("Entities affected", latest["entity"].nunique())

    st.markdown("---")

    # ── Filters ───────────────────────────────────────────────────────────────────
    all_domains  = sorted(latest["domain"].unique().tolist())
    all_sevs     = ["Critical", "Warning"]
    all_types    = sorted(latest["rca_type"].unique().tolist())

    f1, f2, f3 = st.columns(3)
    with f1:
        dom_filter  = st.multiselect("Domain",        all_domains, default=all_domains)
    with f2:
        sev_filter  = st.multiselect("Severity",      all_sevs,    default=all_sevs)
    with f3:
        type_filter = st.multiselect("Incident type", all_types,   default=all_types)

    filtered = latest[
        latest["domain"].isin(dom_filter) &
        latest["severity"].isin(sev_filter) &
        latest["rca_type"].isin(type_filter)
    ]

    if filtered.empty:
        st.info("No incidents match the current filters.")
    else:
        st.markdown(f"### {len(filtered)} active incident(s)")

        for _, row in filtered.iterrows():
            sev   = row["severity"]
            domain = row["domain"]
            icon  = DOMAIN_ICONS.get(domain, "🔧")
            color = SEV_COLOR.get(sev, "#6B7280")
            bg    = SEV_BG.get(sev, "#F9FAFB")

            with st.expander(
                f"{icon} **{row['entity']}** — {row['rca_type']} — "
                f"Risk {row['risk_15m']:.0f}% · {sev}",
                expanded=(sev == "Critical")
            ):
                # Header band
                st.markdown(
                    f"<div style='background:{bg};border-left:4px solid {color};"
                    f"padding:10px 16px;border-radius:6px;margin-bottom:12px'>"
                    f"<b style='color:{color}'>{sev} — {row['rca_type']}</b> &nbsp;|&nbsp; "
                    f"<b>{domain.capitalize()}</b> · {row['entity']}"
                    f"</div>", unsafe_allow_html=True
                )

                # Risk horizons
                h1, h2, h3 = st.columns(3)
                h1.metric("Risk in 15 min", f"{row['risk_15m']:.0f}%")
                h2.metric("Risk in 30 min", f"{row['risk_30m']:.0f}%")
                h3.metric("Risk in 60 min", f"{row['risk_60m']:.0f}%")

                st.markdown("---")

                # Root cause
                st.markdown("#### 🔎 Root Cause")
                st.info(row["rca_cause"])

                # Business impact
                st.markdown("#### ⚡ Business Impact")
                st.warning(row["rca_impact"])

                # Remediation steps
                st.markdown("#### ✅ Remediation Steps")
                solutions = [s.strip() for s in str(row["rca_solutions"]).split("§§§") if s.strip()]
                for i, sol in enumerate(solutions, 1):
                    st.markdown(f"**{i}.** {sol}")

                # Commands — each on its own line, joined cleanly
                raw_cmds = str(row.get("rca_commands", ""))
                commands = [c.strip() for c in raw_cmds.split("§§§") if c.strip()]
                if commands:
                    st.markdown("#### 💻 Commands to run")
                    st.code("\n".join(commands), language="bash")

                # ── Triggering metrics — properly extracted ──────────────────────
                st.markdown("#### 📊 Triggering metrics")
                domain_feats = DOMAIN_FEATURES.get(domain, [])
                metric_dict = {}
                for feat in domain_feats:
                    if feat in row.index:
                        val = row[feat]
                        metric_dict[feat] = round(float(val), 3) if isinstance(val, (int, float)) else val

                if metric_dict:
                    # Display as colour-coded metric cards
                    feat_cols = st.columns(min(len(metric_dict), 4))
                    for i, (feat, val) in enumerate(metric_dict.items()):
                        col_idx = i % len(feat_cols)
                        feat_cols[col_idx].metric(feat.replace("_", " "), val)
                else:
                    st.caption("No metric data available for this row.")

                st.caption(f"Last detected: {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} UTC")

        # Export
        st.markdown("---")
        export_cols = ["timestamp","domain","entity","severity","rca_type",
                       "risk_15m","risk_30m","risk_60m",
                       "rca_cause","rca_impact","rca_solutions","rca_commands"]
        export_cols = [c for c in export_cols if c in filtered.columns]
        csv = filtered[export_cols].to_csv(index=False).encode()
        st.download_button("⬇️ Export RCA report CSV", csv, "rca_report.csv", "text/csv")

    # ── Auto-refresh ──────────────────────────────────────────────────────────────
    if st.session_state.collector_running:
        time.sleep(st.session_state.get("interval", 10))
        st.rerun()

render()
