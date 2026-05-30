# 🔮 AIOps Incident Predictor

> Predict infrastructure failures across Kubernetes, Cloud, Network, and Application — **15, 30, and 60 minutes before they happen** — using a live metric collection loop.

Built by **Leena Adapakala** — Senior DevOps & Cloud Platform Engineer  
[LinkedIn](https://linkedin.com/in/leena-adapakala/) · [GitHub](https://github.com/LeenaAdapakala17/)

---

## 🚀 Quick start

```bash
git clone https://github.com/LeenaAdapakala17/aiops-incident-predictor
cd aiops-incident-predictor
pip install -r requirements.txt
streamlit run app.py
```

Then go to **📡 Data Collector** and press **▶️ Start collector**.

---

## 📡 How data collection works

The app simulates a real **Prometheus scrape loop** — no real infrastructure required.

- Each entity (pod, VM, service) has its own independent health state
- The collector polls every N seconds (5 / 10 / 15 / 30s — your choice)
- Metrics **drift naturally** over time — memory creeps up, latency spikes gradually
- **Anomalies inject and recover** on their own, just like real infra
- History accumulates as a rolling time-series (last 500 rows per domain)

| Domain | Entities | Key signals |
|---|---|---|
| ☸️ Kubernetes | 8 pods, 3 nodes | OOMKill, CrashLoop, Eviction, Pending |
| ☁️ Cloud (Azure) | 4 VMs | CPU/Mem exhaustion, Disk IOPS, Quota breach |
| 🌐 Network | 5 services | Latency, Packet loss, DNS failures, Ingress saturation |
| 📦 Application | 5 services | 5xx errors, Slow P99, Memory leak, Thread exhaustion |

---

## 📱 App pages

### 📡 Data Collector
- Start / Stop / Reset the scrape loop
- Configure scrape interval (5s–30s)
- One-shot manual scrape button
- Live raw metric stream preview per domain (last 8 rows, anomaly pressure highlighted)

### 🔴 Live Monitor
- Risk scores per entity at 15 / 30 / 60 min horizons
- Time-series trend for any entity
- Anomaly pressure area chart
- Cross-entity risk bar chart with severity colouring

### 📋 Incident Log
- All Critical and Warning events across every domain
- Filter by domain, severity, minimum risk score
- Incident timeline scatter chart
- Domain breakdown bar chart
- Export to CSV

### 🧠 Model Insights
- Feature importance per domain
- Live risk score distribution from collected data
- Plain-English metric reference
- Model card (algorithm, training size, thresholds)

---

## 🧠 ML architecture

- **Algorithm:** Random Forest (150 estimators, balanced class weights)
- **Training:** 3,000 synthetic rows per domain, generated from the same streamer so distribution matches
- **Pipeline:** StandardScaler → RandomForestClassifier
- **Horizons:** 15 min (direct output) · 30 min & 60 min (probabilistic extrapolation)
- **Severity thresholds:** Critical ≥ 70% · Warning ≥ 40% · Healthy < 40%

---

## 📁 Project structure

```
aiops-incident-predictor/
├── app.py                        # Entry point + sidebar
├── requirements.txt
├── collector/
│   ├── streamer.py               # Live metric streamer — entity states, drift, anomaly injection
│   └── session.py                # Streamlit session state helpers
├── model/
│   └── predictor.py              # ML training, prediction engine, feature importance
└── pages/
    ├── 1_Data_Collector.py       # Scrape loop UI — start/stop/reset/preview
    ├── 2_Live_Monitor.py         # Real-time risk dashboard + trend charts
    ├── 3_Incident_Log.py         # Aggregated incident history + export
    └── 4_Model_Insights.py       # Feature importance + model card
```

---

## ☁️ Deploy free on Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, set `app.py` as the entry point
4. Deploy — done
