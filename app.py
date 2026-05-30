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

[LinkedIn](https://linkedin.com/in/leena-adapakala/) · [GitHub](https://github.com/LeenaAdapakala17/)

---
### Pages
- 📡 **Data Collector** — live metric stream
- 🔴 **Live Monitor** — real-time risk dashboard
- 📋 **Incident Log** — all flagged events
- 🧠 **Model Insights** — feature importance

---
### Domains
| | Domain | Predicts |
|---|---|---|
| ☸️ | Kubernetes | OOMKill, CrashLoop, Eviction |
| ☁️ | Cloud | CPU/Mem exhaustion, Quota |
| 🌐 | Network | Latency, Packet loss, DNS |
| 📦 | Application | Errors, Slow P99, Leak |
""")

st.markdown("""
# 🔮 AIOps Incident Predictor

Predict infrastructure failures across **Kubernetes, Cloud, Network, and Application** — **15, 30, and 60 minutes** before they happen.

---

### Get started
1. Go to **📡 Data Collector** — start the live metric stream
2. Watch **🔴 Live Monitor** — see risk scores update in real time
3. Review **📋 Incident Log** — all flagged incidents across every domain
4. Explore **🧠 Model Insights** — understand what drives each prediction

---

### How the collector works
The app simulates a **real Prometheus scrape loop** — polling all entities every N seconds.
Each entity (pod, VM, service) has its own independent health state that drifts naturally over time.
Anomalies build up gradually and recover on their own — exactly like real infrastructure behaves.

| Layer | Entities monitored |
|---|---|
| Kubernetes | 8 pods across 3 nodes |
| Cloud (Azure) | 4 VMs |
| Network | 5 services |
| Application | 5 services |

---
*Python · Streamlit · Scikit-learn · Plotly*
""")
