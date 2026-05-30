import streamlit as st

st.set_page_config(
    page_title="AIOps Incident Predictor",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.sidebar.markdown("""
# 🔮 AIOps Incident Predictor
**Predict before it breaks.**

---
Built by **Leena Adapakala**
Senior DevOps & Cloud Platform Engineer

[LinkedIn](https://linkedin.com/in/leena-adapakala/) · [GitHub](https://github.com/LeenaAdapakala17/aiops-incident-predictor)

---
### Pages
- 📡 **Data Collector** — live metric stream
- 📊 **SLO Dashboard** — error budget tracking
- 🔴 **Live Monitor** — real-time risk dashboard
- 🔍 **RCA & Solutions** — root cause + remediation
- 📋 **Incident Log** — all flagged events
- 🧠 **Model Insights** — feature importance

---
### Predicts 17 incident types
| | Domain |
|---|---|
| ☸️ | Kubernetes |
| ☁️ | Azure Cloud |
| 🌐 | Network |
| 📦 | Application |
""")

st.markdown("""
# 🔮 AIOps Incident Predictor

Predict infrastructure failures across **Kubernetes, Cloud, Network, and Application** —
**15, 30, and 60 minutes** before they happen.

---

### Get started
1. Go to **📡 Data Collector** — choose your data source and start collecting
2. Watch **🔴 Live Monitor** — risk scores update automatically every scrape
3. Review **🔍 RCA & Solutions** — root cause, business impact, and remediation commands
4. Track **📊 SLO Dashboard** — availability % and error budget burn rate
5. Explore **🧠 Model Insights** — see what drives each prediction

---

### Data sources

| Mode | What it collects |
|---|---|
| ☸️ **AKS Simulation** | Realistic Azure Kubernetes cluster — 8 pods, 4 VMs, 5 network services, 5 application services. Anomalies build gradually, cascade across services, and self-heal. |
| 🔥 **Prometheus Endpoint** | Connect your own Prometheus instance — paste your URL and the app scrapes your real infrastructure every N seconds. |

---

### What it predicts

| Domain | Incident types |
|---|---|
| ☸️ Kubernetes | OOMKill · CrashLoopBackOff · CPU Throttling · Memory Pressure · Pod Stuck Pending |
| ☁️ Azure Cloud | CPU Exhaustion · Memory Exhaustion · Disk IOPS Throttling · Quota Breach |
| 🌐 Network | High Latency · Packet Loss · DNS Failures · Ingress Saturation |
| 📦 Application | High Error Rate · Slow P99 · Memory Leak · Thread Pool Exhaustion |

---

### How predictions work

- **ML model** (Random Forest) trained on realistic infrastructure patterns
- **3 prediction horizons** — 15 min, 30 min, and 60 min ahead
- **Smoothed risk scores** — no sudden jumps, trends build naturally
- **Live retraining** — model adapts to your data every 50 scrapes
- **Severity labels** — 🔴 Critical ≥ 70% · 🟡 Warning ≥ 40% · 🟢 Healthy < 40%

---

*Python · Streamlit · Scikit-learn · Plotly · psutil*
""")