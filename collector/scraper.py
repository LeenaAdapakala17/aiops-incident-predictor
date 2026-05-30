"""
Simulated Prometheus scraper.
Each entity (pod / vm / service) has independent state that drifts
over time, builds toward anomalies, and self-recovers — mimicking
real infrastructure behaviour.
"""
import numpy as np
import pandas as pd
from datetime import datetime

# ── Entity registry ────────────────────────────────────────────────
PODS      = ["payment-svc", "auth-api", "order-processor", "notification-svc",
             "gateway-proxy", "data-pipeline", "cache-manager", "reporting-svc"]
NODES     = ["aks-nodepool-001", "aks-nodepool-002", "aks-nodepool-003"]
NAMESPACES= ["production", "staging", "monitoring"]
VMS       = ["vm-prod-001", "vm-prod-002", "vm-bastion"]
SERVICES  = ["frontend", "backend-api", "database-proxy", "message-broker"]


class EntityState:
    """Tracks the health trajectory of a single entity."""

    def __init__(self, name, rng):
        self.name   = name
        self.rng    = rng
        # base levels (stable operating point)
        self.cpu_base  = rng.uniform(20, 60)
        self.mem_base  = rng.uniform(30, 65)
        # current values
        self.cpu  = self.cpu_base
        self.mem  = self.mem_base
        self.restarts   = 0
        self.oom        = 0
        self.anomaly_countdown = int(rng.exponential(40))   # steps until next anomaly
        self.recovering = False
        self.recovery_steps = 0

    def step(self):
        """Advance one scrape tick."""
        r = self.rng

        if self.recovering:
            # gradual recovery toward base
            self.cpu = self.cpu * 0.85 + self.cpu_base * 0.15 + r.normal(0, 1)
            self.mem = self.mem * 0.85 + self.mem_base * 0.15 + r.normal(0, 1)
            self.restarts = max(0, self.restarts - 1)
            self.oom      = max(0, self.oom - 1)
            self.recovery_steps -= 1
            if self.recovery_steps <= 0:
                self.recovering = False
                self.anomaly_countdown = int(r.exponential(40))
            return

        self.anomaly_countdown -= 1

        if self.anomaly_countdown <= 0:
            # inject an anomaly — gradual build-up
            severity = r.choice(["mild", "moderate", "severe"], p=[0.5, 0.35, 0.15])
            if severity == "mild":
                self.cpu += r.uniform(15, 30)
                self.mem += r.uniform(10, 20)
            elif severity == "moderate":
                self.cpu += r.uniform(30, 50)
                self.mem += r.uniform(25, 40)
                self.restarts += r.integers(1, 4)
            else:
                self.cpu += r.uniform(50, 80)
                self.mem += r.uniform(45, 60)
                self.restarts += r.integers(3, 8)
                self.oom   += r.integers(1, 3)
            # start recovery after 3-8 ticks
            self.recovering     = True
            self.recovery_steps = int(r.uniform(3, 9))
        else:
            # normal drift
            self.cpu = np.clip(self.cpu + r.normal(0, 2), 1, 99)
            self.mem = np.clip(self.mem + r.normal(0, 1.5), 1, 99)
            self.restarts = max(0, self.restarts + r.integers(-1, 2))
            self.oom      = max(0, self.oom + int(r.random() < 0.03))

        self.cpu = np.clip(self.cpu, 1, 99)
        self.mem = np.clip(self.mem, 1, 99)


class PrometheusSimulator:
    """
    Simulates a Prometheus scrape endpoint.
    Call .scrape() every N seconds to get a new batch of rows.
    """

    def __init__(self, seed=0):
        self.rng   = np.random.default_rng(seed)
        self._init_states()
        self.tick  = 0

    def _init_states(self):
        self._k_states  = {p: EntityState(p, np.random.default_rng(self.rng.integers(0, 99999))) for p in PODS}
        self._c_states  = {v: EntityState(v, np.random.default_rng(self.rng.integers(0, 99999))) for v in VMS}
        self._n_states  = {s: EntityState(s, np.random.default_rng(self.rng.integers(0, 99999))) for s in SERVICES}
        self._a_states  = {s: EntityState(s, np.random.default_rng(self.rng.integers(0, 99999))) for s in SERVICES}

    def reset(self, seed=0):
        self.rng  = np.random.default_rng(seed)
        self.tick = 0
        self._init_states()

    # ── domain scrapers ────────────────────────────────────────────

    def _scrape_kubernetes(self, ts):
        rows = []
        for pod, st in self._k_states.items():
            st.step()
            mem_limit_ratio = np.clip(st.mem / 100 + self.rng.normal(0, 0.05), 0.01, 1.6)
            cpu_throttle    = np.clip(self.rng.beta(1 + st.cpu / 50, 5) * 100, 0, 100)
            pending_sec     = int(self.rng.exponential(3) if st.restarts > 2 else 0)
            rows.append({
                "timestamp":           ts,
                "pod":                 pod,
                "namespace":           self.rng.choice(NAMESPACES),
                "node":                self.rng.choice(NODES),
                "memory_usage_pct":    round(st.mem, 2),
                "cpu_usage_pct":       round(st.cpu, 2),
                "restart_count_5m":    int(st.restarts),
                "oom_events":          int(st.oom),
                "mem_limit_ratio":     round(mem_limit_ratio, 3),
                "cpu_throttle_rate_pct": round(cpu_throttle, 2),
                "pending_time_sec":    pending_sec,
            })
        return pd.DataFrame(rows)

    def _scrape_cloud(self, ts):
        rows = []
        for vm, st in self._c_states.items():
            st.step()
            disk_iops   = np.clip(self.rng.normal(40 + st.cpu * 0.3, 8), 0, 100)
            quota_used  = np.clip(self.rng.normal(55 + st.mem * 0.2, 6), 10, 100)
            net_out     = np.clip(self.rng.normal(200 + st.cpu * 2, 40), 10, 1000)
            rows.append({
                "timestamp":          ts,
                "vm":                 vm,
                "cpu_usage_pct":      round(st.cpu, 2),
                "memory_usage_pct":   round(st.mem, 2),
                "disk_iops_pct":      round(disk_iops, 2),
                "storage_throttle":   int(disk_iops > 85),
                "quota_used_pct":     round(quota_used, 2),
                "network_out_mbps":   round(net_out, 2),
            })
        return pd.DataFrame(rows)

    def _scrape_network(self, ts):
        rows = []
        for svc, st in self._n_states.items():
            st.step()
            latency     = np.clip(self.rng.lognormal(4 + st.cpu * 0.02, 0.4), 10, 5000)
            pkt_loss    = np.clip(self.rng.exponential(0.3 + st.mem * 0.005), 0, 30)
            dns_fail    = int(self.rng.poisson(0.1 + st.restarts * 0.3))
            ingress_sat = np.clip(self.rng.normal(40 + st.cpu * 0.4, 8), 0, 100)
            tcp_retrans = np.clip(self.rng.exponential(0.5 + pkt_loss * 0.2), 0, 20)
            rows.append({
                "timestamp":               ts,
                "service":                 svc,
                "latency_ms":              round(latency, 2),
                "packet_loss_pct":         round(pkt_loss, 3),
                "dns_failures_5m":         dns_fail,
                "ingress_saturation_pct":  round(ingress_sat, 2),
                "tcp_retransmit_pct":      round(tcp_retrans, 3),
            })
        return pd.DataFrame(rows)

    def _scrape_application(self, ts):
        rows = []
        for svc, st in self._a_states.items():
            st.step()
            error_rate  = np.clip(self.rng.exponential(0.5 + st.oom * 3 + st.restarts * 1.5), 0, 50)
            p99         = np.clip(self.rng.lognormal(5 + st.cpu * 0.015, 0.5), 50, 10000)
            heap        = np.clip(st.mem + self.rng.normal(0, 3), 5, 100)
            threads     = np.clip(self.rng.normal(45 + st.cpu * 0.3, 10), 0, 100)
            gc_pause    = np.clip(self.rng.exponential(20 + heap * 0.5), 0, 2000)
            rps         = np.clip(self.rng.normal(500 - st.cpu * 2, 50), 10, 2000)
            rows.append({
                "timestamp":              ts,
                "service":                svc,
                "error_rate_5xx_pct":     round(error_rate, 3),
                "response_time_p99_ms":   round(p99, 2),
                "heap_usage_pct":         round(heap, 2),
                "thread_pool_active_pct": round(threads, 2),
                "gc_pause_ms":            round(gc_pause, 2),
                "requests_per_sec":       round(rps, 2),
            })
        return pd.DataFrame(rows)

    # ── public API ─────────────────────────────────────────────────

    def scrape(self):
        """Return one scrape batch across all 4 domains."""
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self.tick += 1
        return {
            "kubernetes":  self._scrape_kubernetes(ts),
            "cloud":       self._scrape_cloud(ts),
            "network":     self._scrape_network(ts),
            "application": self._scrape_application(ts),
        }
