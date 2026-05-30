"""
Prometheus HTTP API client.
Connects to any Prometheus endpoint — local or remote.
Maps PromQL query results to our 4-domain schema.
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime

DEFAULT_TIMEOUT = 8

PROMQL_QUERIES = {
    "kubernetes": {
        "memory_usage_pct":      'sum by (pod) (container_memory_usage_bytes{pod!=""}) / sum by (pod) (container_spec_memory_limit_bytes{pod!=""}) * 100',
        "cpu_usage_pct":         'sum by (pod) (rate(container_cpu_usage_seconds_total{pod!=""}[2m])) * 100',
        "restart_count_5m":      'sum by (pod) (increase(kube_pod_container_status_restarts_total[5m]))',
        "mem_limit_ratio":       'sum by (pod) (container_memory_usage_bytes{pod!=""}) / sum by (pod) (container_spec_memory_limit_bytes{pod!=""})',
        "cpu_throttle_rate_pct": 'sum by (pod) (rate(container_cpu_cfs_throttled_seconds_total[2m])) / sum by (pod) (rate(container_cpu_cfs_periods_total[2m])) * 100',
        "oom_events":            'sum by (pod) (kube_pod_container_status_last_terminated_reason{reason="OOMKilled"})',
        "pending_time_sec":      'sum by (pod) (kube_pod_status_phase{phase="Pending"})',
    },
    "cloud": {
        "cpu_usage_pct":      'avg by (instance) (100 - irate(node_cpu_seconds_total{mode="idle"}[2m]) * 100)',
        "memory_usage_pct":   'avg by (instance) ((1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100)',
        "disk_iops_pct":      'avg by (instance) (rate(node_disk_io_time_seconds_total[2m]) * 100)',
        "quota_used_pct":     'avg by (instance) ((node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes * 100)',
        "network_out_mbps":   'avg by (instance) (rate(node_network_transmit_bytes_total[2m]) / 1024 / 1024)',
        "storage_throttle":   'avg by (instance) (rate(node_disk_io_time_seconds_total[2m]))',
    },
    "network": {
        "latency_ms":             'avg by (instance) (probe_duration_seconds * 1000)',
        "packet_loss_pct":        'avg by (instance) ((1 - probe_success) * 100)',
        "ingress_saturation_pct": 'avg by (instance) (rate(node_network_receive_bytes_total[2m]) / 125000 * 100)',
        "tcp_retransmit_pct":     'avg by (instance) (rate(node_netstat_Tcp_RetransSegs[2m]) / rate(node_netstat_Tcp_OutSegs[2m]) * 100)',
        "dns_failures_5m":        'sum by (instance) (increase(probe_dns_lookup_time_seconds[5m]))',
    },
    "application": {
        "error_rate_5xx_pct":     'sum by (job) (rate(http_requests_total{status=~"5.."}[2m])) / sum by (job) (rate(http_requests_total[2m])) * 100',
        "response_time_p99_ms":   'histogram_quantile(0.99, sum by (job, le) (rate(http_request_duration_seconds_bucket[2m]))) * 1000',
        "heap_usage_pct":         'sum by (job) (jvm_memory_used_bytes{area="heap"}) / sum by (job) (jvm_memory_max_bytes{area="heap"}) * 100',
        "thread_pool_active_pct": 'sum by (job) (jvm_threads_live_threads) / sum by (job) (jvm_threads_peak_threads) * 100',
        "gc_pause_ms":            'sum by (job) (rate(jvm_gc_pause_seconds_sum[2m])) * 1000',
        "requests_per_sec":       'sum by (job) (rate(http_requests_total[2m]))',
    },
}

ENTITY_LABEL = {
    "kubernetes":  "pod",
    "cloud":       "instance",
    "network":     "instance",
    "application": "job",
}

def test_connection(base_url: str) -> tuple:
    """Test if Prometheus endpoint is reachable. Returns (ok, message)."""
    try:
        url = base_url.rstrip("/") + "/api/v1/query"
        r   = requests.get(url, params={"query": "up"}, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            targets = len(data.get("data", {}).get("result", []))
            return True, f"Connected — {targets} targets found"
        return False, f"HTTP {r.status_code}: {r.text[:100]}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused — check the URL and ensure Prometheus is running"
    except requests.exceptions.Timeout:
        return False, "Timed out — Prometheus may be slow or unreachable"
    except Exception as e:
        return False, str(e)

def _query(base_url: str, promql: str) -> list:
    """Run an instant PromQL query and return result list."""
    try:
        r = requests.get(
            base_url.rstrip("/") + "/api/v1/query",
            params={"query": promql},
            timeout=DEFAULT_TIMEOUT
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("result", [])
    except Exception:
        pass
    return []

def _safe_float(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if np.isfinite(v) else default
    except Exception:
        return default

def scrape_prometheus(base_url: str) -> dict:
    """
    Scrape all 4 domains from a Prometheus endpoint.
    Returns dict of DataFrames matching our schema.
    Falls back to zeros if a metric is unavailable.
    """
    ts     = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    result = {}

    for domain, queries in PROMQL_QUERIES.items():
        entity_label = ENTITY_LABEL[domain]
        feats        = list(queries.keys())

        # Query each metric
        metric_data: dict = {}
        for feat, promql in queries.items():
            rows = _query(base_url, promql)
            for row in rows:
                entity = row.get("metric", {}).get(entity_label, "unknown")
                val    = _safe_float(row.get("value", [None, "0"])[1])
                if entity not in metric_data:
                    metric_data[entity] = {}
                metric_data[entity][feat] = round(val, 3)

        if not metric_data:
            # No data returned — skip this domain
            result[domain] = pd.DataFrame()
            continue

        rows_list = []
        for entity, metrics in metric_data.items():
            row = {
                "timestamp":        ts,
                "entity":           entity,
                "domain":           domain,
                "anomaly_pressure": 0.0,
                "cascade_boost":    0.0,
                "tod_multiplier":   1.0,
                "alert_suppressed": False,
            }
            for feat in feats:
                row[feat] = metrics.get(feat, 0.0)
            # Add zscore placeholders
            for feat in feats[:3]:
                row[f"zscore_{feat}"] = 0.0
            rows_list.append(row)

        result[domain] = pd.DataFrame(rows_list)

    return result

def get_available_metrics(base_url: str) -> list:
    """Return list of metric names available in this Prometheus instance."""
    try:
        r = requests.get(
            base_url.rstrip("/") + "/api/v1/label/__name__/values",
            timeout=DEFAULT_TIMEOUT
        )
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception:
        pass
    return []
