"""
Live metric streamer — simulates Prometheus scrape behaviour.
Each entity has its own health state with:
- Time-of-day traffic patterns (sinusoidal business hours curve)
- Cascade effects (failing services impact downstream entities)
- Rolling baseline learning (anomaly detection relative to each entity's own normal)
- Natural drift, gradual anomaly build-up, and self-healing recovery
"""
import numpy as np
import pandas as pd
from datetime import datetime
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque

PODS       = ["payment-svc", "auth-api", "order-processor", "notification-svc", "gateway-proxy", "data-pipeline", "cache-mgr", "reporting-svc"]
NODES      = ["aks-nodepool-001", "aks-nodepool-002", "aks-nodepool-003"]
VMS        = ["vm-prod-001", "vm-prod-002", "vm-bastion", "vm-worker-001"]
SERVICES   = ["frontend", "backend-api", "database-proxy", "message-broker", "auth-service"]

# ── Cascade dependency map ────────────────────────────────────────────────────
# If source entity has high anomaly_pressure, it increases pressure on targets
CASCADE_MAP = {
    # DB proxy failure → backend-api and frontend degrade
    "database-proxy": ["backend-api", "frontend"],
    # message-broker failure → order-processor and notification-svc degrade
    "message-broker": ["order-processor", "notification-svc"],
    # auth-api failure → gateway-proxy degrades
    "auth-api":        ["gateway-proxy"],
    # auth-service failure → frontend and backend-api degrade
    "auth-service":    ["frontend", "backend-api"],
    # cache-mgr failure → data-pipeline degrades
    "cache-mgr":       ["data-pipeline"],
    # vm-prod-001 high CPU → hosted pods degrade
    "vm-prod-001":     ["payment-svc", "auth-api"],
    "vm-prod-002":     ["order-processor", "gateway-proxy"],
}

def _time_of_day_multiplier() -> float:
    hour     = datetime.utcnow().hour
    weekday  = datetime.utcnow().weekday()
    base     = 0.35 + 0.65 * max(0, math.sin(math.pi * (hour - 6) / 14))
    weekend  = 0.75 if weekday >= 5 else 1.0
    jitter   = np.random.uniform(0.97, 1.03)
    return round(base * weekend * jitter, 3)

def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))

# ── Entity health state ───────────────────────────────────────────────────────
@dataclass
class EntityState:
    name:             str
    domain:           str
    base:             Dict[str, float] = field(default_factory=dict)
    current:          Dict[str, float] = field(default_factory=dict)
    anomaly_pressure: float = 0.0
    anomaly_ttl:      int   = 0
    recovering:       bool  = False
    cascade_boost:    float = 0.0   # extra pressure from upstream failures
    # Rolling baseline: last 20 readings per metric
    history:          Dict[str, deque] = field(default_factory=dict)
    baseline_mean:    Dict[str, float] = field(default_factory=dict)
    baseline_std:     Dict[str, float] = field(default_factory=dict)
    # Alert dedup: track last alert time per incident type
    last_alert:       Dict[str, int]   = field(default_factory=dict)
    tick_count:       int = 0

    def update_baseline(self):
        """Update rolling mean/std for each metric (last 20 readings)."""
        for metric, val in self.current.items():
            if metric not in self.history:
                self.history[metric] = deque(maxlen=20)
            self.history[metric].append(val)
            if len(self.history[metric]) >= 5:
                arr = np.array(self.history[metric])
                self.baseline_mean[metric] = float(np.mean(arr))
                self.baseline_std[metric]  = float(np.std(arr)) + 1e-6

    def zscore(self, metric: str) -> float:
        """Return how many std devs current value is above its own baseline."""
        if metric not in self.baseline_mean or metric not in self.current:
            return 0.0
        return (self.current[metric] - self.baseline_mean[metric]) / self.baseline_std[metric]

    def should_alert(self, incident_type: str, cooldown_ticks: int = 5) -> bool:
        """Dedup: only alert if we haven't alerted for this type recently."""
        last = self.last_alert.get(incident_type, -999)
        if self.tick_count - last >= cooldown_ticks:
            self.last_alert[incident_type] = self.tick_count
            return True
        return False

# ── State initialisation ──────────────────────────────────────────────────────
def init_kubernetes_states() -> List[EntityState]:
    states = []
    for pod in PODS:
        base = {
            "memory_usage_pct":      np.random.uniform(30, 60),
            "cpu_usage_pct":         np.random.uniform(20, 50),
            "restart_count_5m":      0.0,
            "oom_events":            0.0,
            "mem_limit_ratio":       np.random.uniform(0.3, 0.6),
            "cpu_throttle_rate_pct": np.random.uniform(2, 15),
            "pending_time_sec":      0.0,
        }
        s = EntityState(name=pod, domain="kubernetes", base=base.copy(), current=base.copy())
        states.append(s)
    return states

def init_cloud_states() -> List[EntityState]:
    states = []
    for vm in VMS:
        base = {
            "cpu_usage_pct":    np.random.uniform(25, 55),
            "memory_usage_pct": np.random.uniform(30, 60),
            "disk_iops_pct":    np.random.uniform(20, 50),
            "storage_throttle": 0.0,
            "quota_used_pct":   np.random.uniform(40, 70),
            "network_out_mbps": np.random.uniform(80, 300),
        }
        s = EntityState(name=vm, domain="cloud", base=base.copy(), current=base.copy())
        states.append(s)
    return states

def init_network_states() -> List[EntityState]:
    states = []
    for svc in SERVICES:
        base = {
            "latency_ms":             np.random.uniform(50, 200),
            "packet_loss_pct":        np.random.uniform(0, 0.5),
            "dns_failures_5m":        0.0,
            "ingress_saturation_pct": np.random.uniform(20, 50),
            "tcp_retransmit_pct":     np.random.uniform(0, 1.5),
        }
        s = EntityState(name=svc, domain="network", base=base.copy(), current=base.copy())
        states.append(s)
    return states

def init_application_states() -> List[EntityState]:
    states = []
    for svc in SERVICES:
        base = {
            "error_rate_5xx_pct":     np.random.uniform(0, 2),
            "response_time_p99_ms":   np.random.uniform(80, 400),
            "heap_usage_pct":         np.random.uniform(30, 55),
            "thread_pool_active_pct": np.random.uniform(20, 50),
            "gc_pause_ms":            np.random.uniform(10, 80),
            "requests_per_sec":       np.random.uniform(200, 600),
        }
        s = EntityState(name=svc, domain="application", base=base.copy(), current=base.copy())
        states.append(s)
    return states

# ── Cascade propagation ───────────────────────────────────────────────────────
def _apply_cascades(all_states: Dict[str, List[EntityState]]):
    """Propagate anomaly pressure from failing upstream to downstream entities."""
    # Build name→state lookup
    name_map: Dict[str, EntityState] = {}
    for domain_states in all_states.values():
        for s in domain_states:
            name_map[s.name] = s

    for source_name, targets in CASCADE_MAP.items():
        source = name_map.get(source_name)
        if source is None or source.anomaly_pressure < 0.4:
            continue
        cascade_strength = source.anomaly_pressure * 0.4   # 40% bleed-through
        for target_name in targets:
            target = name_map.get(target_name)
            if target:
                target.cascade_boost = min(0.6, target.cascade_boost + cascade_strength * 0.3)

    # Decay cascade boost over time
    for s in name_map.values():
        s.cascade_boost = max(0.0, s.cascade_boost - 0.05)

# ── Metric tick ───────────────────────────────────────────────────────────────
def _tick_state(s: EntityState, anomaly_inject_prob=0.10):
    s.tick_count += 1

    # Anomaly injection (natural + cascade)
    effective_prob = anomaly_inject_prob + s.cascade_boost * 0.3
    if s.anomaly_pressure == 0 and np.random.random() < effective_prob:
        s.anomaly_ttl  = np.random.randint(8, 30)
        s.recovering   = False

    if s.anomaly_ttl > 0:
        if not s.recovering:
            s.anomaly_pressure = min(1.0, s.anomaly_pressure + np.random.uniform(0.12, 0.28) + s.cascade_boost * 0.1)
            if s.anomaly_ttl <= 3:
                s.recovering = True
        else:
            s.anomaly_pressure = max(0.0, s.anomaly_pressure - np.random.uniform(0.08, 0.2))
        s.anomaly_ttl -= 1
    else:
        s.anomaly_pressure = max(0.0, s.anomaly_pressure - 0.05)

    p   = s.anomaly_pressure
    tod = _time_of_day_multiplier()

    if s.domain == "kubernetes":
        s.current["memory_usage_pct"]      = _clamp(s.base["memory_usage_pct"] * tod + p * 45 + np.random.normal(0, 2))
        s.current["cpu_usage_pct"]         = _clamp(s.base["cpu_usage_pct"]    * tod + p * 40 + np.random.normal(0, 3))
        s.current["mem_limit_ratio"]       = _clamp(s.base["mem_limit_ratio"]       + p * 0.7  + np.random.normal(0, 0.02), 0, 2.0)
        s.current["cpu_throttle_rate_pct"] = _clamp(s.base["cpu_throttle_rate_pct"] + p * 60   + np.random.normal(0, 1))
        s.current["restart_count_5m"]      = int(_clamp(p * 8 + np.random.exponential(0.2), 0, 20))
        s.current["oom_events"]            = int(_clamp(p * 4 + np.random.exponential(0.05), 0, 10))
        s.current["pending_time_sec"]      = int(_clamp(p * 120 + s.cascade_boost * 60 + np.random.exponential(1), 0, 600))

    elif s.domain == "cloud":
        s.current["cpu_usage_pct"]      = _clamp(s.base["cpu_usage_pct"]    * tod + p * 48 + np.random.normal(0, 2))
        s.current["memory_usage_pct"]   = _clamp(s.base["memory_usage_pct"] * tod + p * 42 + np.random.normal(0, 2))
        s.current["disk_iops_pct"]      = _clamp(s.base["disk_iops_pct"]    * tod + p * 55 + np.random.normal(0, 3))
        s.current["quota_used_pct"]     = _clamp(s.base["quota_used_pct"]        + p * 35  + np.random.normal(0, 1))
        s.current["network_out_mbps"]   = _clamp(s.base["network_out_mbps"]      + p * 500 + np.random.normal(0, 10), 0, 1000)
        s.current["storage_throttle"]   = float(s.current["disk_iops_pct"] > 85)

    elif s.domain == "network":
        # Cascade from app/k8s failures increases latency
        cascade_latency = s.cascade_boost * 300
        s.current["latency_ms"]             = _clamp(s.base["latency_ms"]            * tod + p * 2500 + cascade_latency + np.random.normal(0, 10), 5, 8000)
        s.current["packet_loss_pct"]        = _clamp(s.base["packet_loss_pct"]             + p * 20   + np.random.exponential(0.05), 0, 30)
        s.current["ingress_saturation_pct"] = _clamp(s.base["ingress_saturation_pct"] * tod + p * 55   + np.random.normal(0, 2))
        s.current["tcp_retransmit_pct"]     = _clamp(s.base["tcp_retransmit_pct"]         + p * 15   + s.cascade_boost * 5 + np.random.exponential(0.1), 0, 25)
        s.current["dns_failures_5m"]        = int(_clamp(p * 6 + np.random.poisson(0.1), 0, 20))

    elif s.domain == "application":
        # Cascade from DB/broker failures increases error rate and response time
        cascade_errors = s.cascade_boost * 15
        s.current["error_rate_5xx_pct"]     = _clamp(s.base["error_rate_5xx_pct"]        + p * 35  + cascade_errors + np.random.exponential(0.3), 0, 80)
        s.current["response_time_p99_ms"]   = _clamp(s.base["response_time_p99_ms"] * tod + p * 4000 + s.cascade_boost * 500 + np.random.normal(0, 20), 30, 12000)
        s.current["heap_usage_pct"]         = _clamp(s.base["heap_usage_pct"]        * tod + p * 45  + np.random.normal(0, 1.5))
        s.current["thread_pool_active_pct"] = _clamp(s.base["thread_pool_active_pct"] * tod + p * 50  + s.cascade_boost * 20 + np.random.normal(0, 2))
        s.current["gc_pause_ms"]            = _clamp(s.base["gc_pause_ms"]           * tod + p * 800 + np.random.exponential(5), 0, 3000)
        s.current["requests_per_sec"]       = _clamp(s.base["requests_per_sec"]      * tod - p * 300 + np.random.normal(0, 15), 0, 2000)

    # Update rolling baseline after each tick
    s.update_baseline()
    return s

# ── Smooth risk scores ────────────────────────────────────────────────────────
_risk_history: Dict[str, deque] = {}

def smooth_risk(entity: str, raw_risk: float, window: int = 3) -> float:
    """Exponential moving average to prevent risk score jumping."""
    if entity not in _risk_history:
        _risk_history[entity] = deque(maxlen=window)
    _risk_history[entity].append(raw_risk)
    weights = np.exp(np.linspace(-1, 0, len(_risk_history[entity])))
    weights /= weights.sum()
    return round(float(np.dot(weights, list(_risk_history[entity]))), 1)

# ── Public scrape ─────────────────────────────────────────────────────────────
def scrape(states: List[EntityState], all_states: Optional[Dict] = None) -> pd.DataFrame:
    rows = []
    ts   = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    tod  = _time_of_day_multiplier()
    for s in states:
        _tick_state(s)
        row = {
            "timestamp":        ts,
            "entity":           s.name,
            "domain":           s.domain,
            "anomaly_pressure": round(s.anomaly_pressure, 3),
            "cascade_boost":    round(s.cascade_boost, 3),
            "tod_multiplier":   tod,
            "alert_suppressed": False,   # filled by dedup layer
        }
        row.update({k: round(v, 3) for k, v in s.current.items()})
        # Z-score anomaly signals relative to entity's own baseline
        for metric in list(s.current.keys())[:3]:   # top 3 metrics
            row[f"zscore_{metric}"] = round(s.zscore(metric), 2)
        rows.append(row)
    return pd.DataFrame(rows)

def init_all_states():
    return {
        "kubernetes":  init_kubernetes_states(),
        "cloud":       init_cloud_states(),
        "network":     init_network_states(),
        "application": init_application_states(),
    }

def apply_cascades(all_states: Dict[str, List[EntityState]]):
    _apply_cascades(all_states)
