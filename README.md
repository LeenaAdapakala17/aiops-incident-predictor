# 🔮 AIOps Incident Predictor

> **Predict infrastructure failures 15, 30, and 60 minutes before they happen — across Kubernetes, Azure Cloud, Network, and Application layers.**

[![Live App](https://img.shields.io/badge/🚀%20Live%20App-Click%20Here-FF4B4B?style=for-the-badge)](https://aiops-incident-predictor.streamlit.app)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-black?style=for-the-badge&logo=github)](https://github.com/LeenaAdapakala17/aiops-incident-predictor)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32%2B-FF4B4B?style=for-the-badge&logo=streamlit)](https://streamlit.io)

---

Built by **Leena Adapakala** — Senior DevOps & Cloud Platform Engineer with 7+ years in Azure and Kubernetes.

[🔗 LinkedIn](https://linkedin.com/in/leena-adapakala/) · [🐙 GitHub](https://github.com/LeenaAdapakala17/) · [🌐 Live App](https://aiops-incident-predictor.streamlit.app)

---

## 📋 Table of Contents

- [What it does](#-what-it-does)
- [17 incident types predicted](#-17-incident-types-predicted)
- [App pages](#-app-pages)
- [Data sources](#-data-sources)
- [How the ML works](#-how-the-ml-works)
- [Quick start](#-quick-start)
- [Project structure](#-project-structure)
- [Connect your Prometheus](#-connect-your-prometheus)
- [Tech stack](#-tech-stack)

---

## 🎯 What it does

AIOps Incident Predictor is a real-time machine learning platform that:

- **Collects** infrastructure metrics every N seconds (simulation or your real Prometheus)
- **Predicts** the probability of incidents at 15, 30, and 60 minute horizons
- **Explains** the root cause and business impact of every detected incident
- **Recommends** exact `kubectl` and `az` CLI commands to fix each issue
- **Tracks** SLO availability and error budget burn rate across all services
- **Retrains** the ML model automatically on your live data every 50 scrapes

---

## 🚨 17 incident types predicted

### ☸️ Kubernetes (5 types)
| Incident | Trigger condition |
|---|---|
| OOMKill | Pod memory exceeds limit — OOM killer terminates container |
| CrashLoopBackOff | Container restarting > 4 times in 5 minutes |
| Memory Pressure | mem_limit_ratio > 88% — OOMKill imminent |
| CPU Throttling | cgroup CPU throttle rate > 60% |
| Pod Stuck Pending | Pod cannot be scheduled for > 60 seconds |

### ☁️ Azure Cloud (4 types)
| Incident | Trigger condition |
|---|---|
| CPU Exhaustion | VM CPU > 88% sustained |
| Memory Exhaustion | VM memory > 90% |
| Disk IOPS Throttling | IOPS > 85% of provisioned limit |
| Quota Breach | Subscription quota > 93% consumed |

### 🌐 Network (4 types)
| Incident | Trigger condition |
|---|---|
| High Latency | End-to-end latency > 900ms |
| Packet Loss | Packet loss > 4% |
| DNS Failures | > 2 DNS failures in 5 minutes |
| Ingress Saturation | AKS Ingress > 88% capacity |

### 📦 Application (4 types)
| Incident | Trigger condition |
|---|---|
| High Error Rate | 5xx error rate > 8% |
| Slow Response (P99) | 99th percentile response time > 2500ms |
| Memory Leak | Heap usage > 88% |
| Thread Pool Exhaustion | Thread pool > 87% active |

---

## 📱 App pages

### 📡 Data Collector
The starting point for the entire app. Choose your data source and start collecting.

**What you can do:**
- Switch between **AKS Simulation** and **Prometheus Endpoint** modes
- Set scrape interval: every 5, 10, 15, or 30 seconds
- Start / Stop the collector loop
- Reset all collected data
- Trigger a single manual scrape
- Watch the live metric stream update in real time per domain
- Anomaly pressure is highlighted — red = high, yellow = moderate

**Auto-retrain:** Every 50 scrapes, all 4 ML models automatically retrain on your live data. A toast notification confirms when retraining completes.

---

### 📊 SLO Dashboard
Tracks service reliability against a 99.5% availability target — exactly how Google SRE teams measure production health.

**What you see:**
- Overall availability % vs SLO target
- Error budget remaining (gauge chart)
- Burn rate — how fast the error budget is being consumed
- Per-service availability table with SLO status (Met / Breach)
- Cascade dependency map — which services impact others when they fail
- Deduplicated alert log — same entity + incident type suppressed until resolved

---

### 🔴 Live Monitor
Real-time risk dashboard that updates automatically every scrape cycle.

**What you see:**
- Global health banner — green (all healthy), amber (warnings), red (critical incidents)
- Time-of-day traffic load indicator — business hours vs off-peak
- Risk score bar chart per entity at your chosen horizon (15 / 30 / 60 min)
- Entity drill-down — click any entity to see its full risk trend over time
- Anomaly pressure area chart — raw signal driving the ML prediction
- Latest metric readings table for all entities

---

### 🔍 RCA & Solutions
The most valuable page — explains every incident in plain English and tells you exactly what to do.

**For every detected incident you get:**
- 🔎 **Root Cause** — why this is happening in plain English
- ⚡ **Business Impact** — what breaks if not fixed
- ✅ **Remediation Steps** — numbered action list
- 💻 **Commands to run** — real `kubectl` / `az` CLI commands with your actual entity names auto-filled (e.g. `kubectl describe pod payment-svc -n production`)
- 📊 **Triggering metrics** — the exact values that fired the alert
- Risk scores at 15 / 30 / 60 min horizons

**Filters:** Domain, Severity, Incident type
**Export:** Full RCA report as CSV

---

### 📋 Incident Log
Complete history of all Critical and Warning events since the collector started.

**What you see:**
- Total incidents, critical count, warning count, domains and entities affected
- Incident timeline scatter chart — all events plotted over time
- Incident rate over time chart — spikes show problem periods
- Domain breakdown bar chart
- Full filterable incident table
- CSV export

---

### 🧠 Model Insights
Understand what drives each prediction — updates live as the model retrains.

**What you see:**
- Training source banner — shows whether model is using synthetic or live data
- Feature importance chart — which metrics matter most per domain
- Risk score distribution — built from your actual collected data
- Live metric trend charts — any metric, any entity, over time
- Manual retrain button — retrain on demand once you have 50+ rows
- Metric reference — plain-English explanation of every metric
- Model card — algorithm, training rows, features, thresholds

---

## 📡 Data sources

### ☸️ AKS Simulation Mode (default)

A realistic Azure Kubernetes cluster simulation with:

**Entities monitored:**
| Domain | Entities |
|---|---|
| Kubernetes | payment-svc, auth-api, order-processor, notification-svc, gateway-proxy, data-pipeline, cache-mgr, reporting-svc |
| Cloud (Azure) | vm-prod-001, vm-prod-002, vm-bastion, vm-worker-001 |
| Network | frontend, backend-api, database-proxy, message-broker, auth-service |
| Application | frontend, backend-api, database-proxy, message-broker, auth-service |

**Realism features:**
- **Time-of-day patterns** — CPU, memory, and latency peak at 1pm UTC, drop to 35% at night. Weekends are 25% quieter than weekdays
- **Gradual anomaly injection** — pressure builds over 8–30 ticks, not instant spikes
- **Self-healing** — anomalies recover naturally without manual intervention
- **Cascade effects** — upstream failures propagate to downstream services:
  - `database-proxy` failure → `backend-api` and `frontend` error rates rise
  - `message-broker` failure → `order-processor` and `notification-svc` degrade
  - `auth-api` failure → `gateway-proxy` latency increases
  - VM failures → hosted pods experience OOMKill risk
- **Baseline learning** — each entity tracks its own rolling mean and std dev over 20 readings. Anomaly scoring is relative to that entity's own normal, not global thresholds
- **Alert deduplication** — same entity + incident type suppressed for 5 ticks after first alert
- **Risk smoothing** — exponential moving average prevents risk scores from jumping

### 🔥 Prometheus Endpoint Mode

Connect to any real Prometheus instance and get predictions on your actual infrastructure.

See [Connect your Prometheus](#-connect-your-prometheus) below.

---

## 🧠 How the ML works

### Training
- **Algorithm:** Random Forest Classifier
- **Estimators:** 80 trees, max depth 8, balanced class weights
- **Training data:** 800 synthetic samples per domain at startup
- **Features:** 5–7 metrics per domain (see table below)

### Features per domain

| Domain | Features used |
|---|---|
| Kubernetes | memory_usage_pct, cpu_usage_pct, restart_count_5m, oom_events, mem_limit_ratio, cpu_throttle_rate_pct, pending_time_sec |
| Cloud | cpu_usage_pct, memory_usage_pct, disk_iops_pct, storage_throttle, quota_used_pct, network_out_mbps |
| Network | latency_ms, packet_loss_pct, dns_failures_5m, ingress_saturation_pct, tcp_retransmit_pct |
| Application | error_rate_5xx_pct, response_time_p99_ms, heap_usage_pct, thread_pool_active_pct, gc_pause_ms, requests_per_sec |

### Prediction pipeline
1. Raw metrics scraped every N seconds
2. Features extracted and normalised (StandardScaler)
3. Random Forest outputs probability of incident (0–1)
4. Exponential moving average smoothing applied
5. Risk scores calculated at 15 / 30 / 60 min horizons
6. Severity label assigned: Critical ≥ 70% · Warning ≥ 40% · Healthy < 40%
7. RCA engine matches metric values against 17 rule sets
8. Remediation commands generated with real entity names

### Live retraining
Every 50 scrapes the model retrains by blending:
- Your live collected data (labelled using the same threshold rules)
- 500 synthetic samples (to maintain class balance)

After retraining, feature importance updates in Model Insights.

---

## ⚡ Quick start

### Prerequisites
- Python 3.9 or higher
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/LeenaAdapakala17/aiops-incident-predictor
cd aiops-incident-predictor

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501`

### First run
1. The app trains ML models on startup (~3 seconds — shown with a spinner)
2. Go to **📡 Data Collector**
3. Select **☸️ AKS Simulation** (default)
4. Press **▶️ Start collector**
5. Watch all pages come alive

### Dependencies

```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
plotly>=5.18.0
psutil>=5.9.0
requests>=2.28.0
```

---

## 🔥 Connect your Prometheus

If you have a running Prometheus instance, you can point the app at it and get predictions on your real infrastructure.

### Step 1 — Go to Data Collector
Select **🔥 Prometheus Endpoint** mode.

### Step 2 — Enter your URL
Paste your Prometheus base URL:

| Setup | URL |
|---|---|
| Local Prometheus | `http://localhost:9090` |
| Docker Compose | `http://prometheus:9090` |
| Kubernetes (port-forward) | `http://localhost:9090` |
| Remote server | `http://your-server-ip:9090` |

To port-forward from Kubernetes:
```bash
kubectl port-forward svc/prometheus-operated 9090:9090 -n monitoring
```

### Step 3 — Test the connection
Click **🔌 Test connection**. The app checks:
- Prometheus is reachable
- API returns valid data
- Reports how many targets are being scraped

### Step 4 — Start collecting
Click **▶️ Start collector**. The app runs PromQL queries against your Prometheus every N seconds and scores your real pods, VMs, and services with ML predictions.

### What metrics are queried
The app queries standard Prometheus metrics:
- `container_memory_usage_bytes` — pod memory
- `container_cpu_usage_seconds_total` — pod CPU
- `kube_pod_container_status_restarts_total` — restart count
- `node_cpu_seconds_total` — node CPU
- `node_memory_MemAvailable_bytes` — node memory
- `http_requests_total` — application error rate and throughput
- `http_request_duration_seconds_bucket` — P99 response time
- And more — see `collector/prometheus_client.py` for full list

---

## 📁 Project structure

```
aiops-incident-predictor/
│
├── app.py                          # Main entry point — homepage + sidebar
├── requirements.txt                # Python dependencies
├── README.md
│
├── collector/
│   ├── streamer.py                 # AKS simulation engine
│   │                               # Entity states, drift, anomaly injection,
│   │                               # cascade effects, baseline learning
│   ├── real_metrics.py             # Host metrics via psutil (CPU, memory, disk, net)
│   ├── prometheus_client.py        # Prometheus HTTP API client
│   │                               # PromQL queries for all 4 domains
│   └── session.py                  # Streamlit session state management
│                                   # SLO tracker, alert dedup, cascade propagation
│
├── model/
│   ├── predictor.py                # ML pipeline
│   │                               # Training, prediction, smoothing, live retraining
│   └── rca_engine.py               # RCA rules engine
│                                   # 17 incident types, remediation steps,
│                                   # kubectl/az commands with entity name filling
│
└── pages/
    ├── 0_Data_Collector.py         # Data source selector + scrape loop UI
    ├── 1_SLO_Dashboard.py          # Availability, error budget, burn rate
    ├── 2_Live_Monitor.py           # Real-time risk dashboard
    ├── 3_RCA_and_Solutions.py      # Root cause + remediation
    ├── 4_Incident_Log.py           # Incident history + timeline
    └── 5_Model_Insights.py         # Feature importance + model card
```

---

## 🛠️ Tech stack

| Technology | Purpose |
|---|---|
| **Python 3.9+** | Core language |
| **Streamlit** | Web UI and real-time updates |
| **Scikit-learn** | Random Forest ML pipeline |
| **Pandas / NumPy** | Data processing |
| **Plotly** | Interactive charts |
| **psutil** | Host system metrics |
| **Requests** | Prometheus HTTP API client |

---

## 👩‍💻 About the author

**Leena Adapakala** — Senior DevOps & Cloud Platform Engineer

7+ years experience in Microsoft Azure, Kubernetes (AKS), Terraform, CI/CD pipelines, and financial services infrastructure. Based in the Netherlands.

- 🔗 [LinkedIn](https://linkedin.com/in/leena-adapakala/)
- 🐙 [GitHub](https://github.com/LeenaAdapakala17/)
- 🌐 [Live App](https://aiops-incident-predictor.streamlit.app)