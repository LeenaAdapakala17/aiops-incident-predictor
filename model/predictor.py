import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

DOMAIN_FEATURES = {
    "kubernetes":  ["memory_usage_pct", "cpu_usage_pct", "restart_count_5m", "oom_events", "mem_limit_ratio", "cpu_throttle_rate_pct", "pending_time_sec"],
    "cloud":       ["cpu_usage_pct", "memory_usage_pct", "disk_iops_pct", "storage_throttle", "quota_used_pct", "network_out_mbps"],
    "network":     ["latency_ms", "packet_loss_pct", "dns_failures_5m", "ingress_saturation_pct", "tcp_retransmit_pct"],
    "application": ["error_rate_5xx_pct", "response_time_p99_ms", "heap_usage_pct", "thread_pool_active_pct", "gc_pause_ms", "requests_per_sec"],
}

INCIDENT_THRESHOLDS = {
    "kubernetes":  lambda r: r["mem_limit_ratio"] > 0.88 or r["oom_events"] > 0 or r["restart_count_5m"] > 4,
    "cloud":       lambda r: r["cpu_usage_pct"] > 88 or r["memory_usage_pct"] > 90 or r["disk_iops_pct"] > 85 or r["quota_used_pct"] > 93,
    "network":     lambda r: r["latency_ms"] > 900 or r["packet_loss_pct"] > 4 or r["dns_failures_5m"] > 2 or r["ingress_saturation_pct"] > 88,
    "application": lambda r: r["error_rate_5xx_pct"] > 8 or r["response_time_p99_ms"] > 2500 or r["heap_usage_pct"] > 88 or r["thread_pool_active_pct"] > 87,
}

_models: dict = {}
_model_meta: dict = {}
_risk_history: dict = {}

def _synthetic_training_data(domain: str, n=800) -> pd.DataFrame:
    from collector.streamer import init_all_states, scrape
    states = init_all_states()
    domain_states = states[domain]
    rows = []
    for tick in range(n // len(domain_states) + 1):
        for s in domain_states:
            if np.random.random() < 0.3:
                s.anomaly_pressure = np.random.uniform(0, 1)
                s.anomaly_ttl = np.random.randint(1, 8)
        df = scrape(domain_states)
        rows.append(df)
    df = pd.concat(rows, ignore_index=True).head(n)
    thresh = INCIDENT_THRESHOLDS[domain]
    df["incident"] = df.apply(thresh, axis=1).astype(int)
    return df

def _train_pipe(X, y):
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(n_estimators=80, max_depth=8,
                                       random_state=42, class_weight="balanced")),
    ])
    pipe.fit(X, y)
    return pipe

def get_models() -> dict:
    global _models, _model_meta
    if not _models:
        for domain in DOMAIN_FEATURES:
            df = _synthetic_training_data(domain, n=800)
            feats = DOMAIN_FEATURES[domain]
            X = df[feats].fillna(0)
            y = df["incident"]
            _models[domain] = _train_pipe(X, y)
            _model_meta[domain] = {
                "source": "Synthetic (startup)",
                "rows": len(df),
                "live_rows": 0,
                "synthetic_rows": len(df),
                "trained_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "incident_rate": f"{y.mean()*100:.1f}%",
            }
    return _models

def retrain_on_live_data(domain: str, live_df: pd.DataFrame) -> dict:
    global _models, _model_meta
    feats  = DOMAIN_FEATURES[domain]
    thresh = INCIDENT_THRESHOLDS[domain]
    live = live_df.copy()
    live["incident"] = live.apply(thresh, axis=1).astype(int)
    synthetic = _synthetic_training_data(domain, n=500)
    combined  = pd.concat([live, synthetic], ignore_index=True)
    X = combined[[f for f in feats if f in combined.columns]].fillna(0)
    for f in feats:
        if f not in X.columns:
            X[f] = 0
    X = X[feats]
    y = combined["incident"]
    _models[domain] = _train_pipe(X, y)
    meta = {
        "source": "Live + Synthetic blend",
        "rows": len(combined),
        "live_rows": len(live),
        "synthetic_rows": len(synthetic),
        "trained_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "incident_rate": f"{y.mean()*100:.1f}%",
    }
    _model_meta[domain] = meta
    return meta

def get_model_meta() -> dict:
    get_models()
    return _model_meta

def smooth_risk(entity: str, raw_risk: float, window: int = 3) -> float:
    from collections import deque
    if entity not in _risk_history:
        _risk_history[entity] = deque(maxlen=window)
    _risk_history[entity].append(raw_risk)
    weights = np.exp(np.linspace(-1, 0, len(_risk_history[entity])))
    weights /= weights.sum()
    return round(float(np.dot(weights, list(_risk_history[entity]))), 1)

def predict(domain: str, df: pd.DataFrame) -> pd.DataFrame:
    models = get_models()
    feats  = DOMAIN_FEATURES[domain]
    X = df[[f for f in feats if f in df.columns]].fillna(0)
    for f in feats:
        if f not in X.columns:
            X[f] = 0
    X = X[feats]

    # Safe predict_proba — handles case where model only saw one class
    proba = models[domain].predict_proba(X)
    if proba.shape[1] > 1:
        raw_probs = proba[:, 1]
    else:
        raw_probs = np.zeros(len(X))

    result = df.copy()
    rng    = np.random.default_rng(int(datetime.utcnow().timestamp()) % 10000)

    entities = df["entity"].tolist() if "entity" in df.columns else [str(i) for i in range(len(df))]
    smoothed = np.array([
        smooth_risk(f"{domain}:{e}", r * 100)
        for e, r in zip(entities, raw_probs)
    ])

    result["risk_15m"] = np.clip(smoothed, 0, 100).round(1)
    result["risk_30m"] = np.clip(smoothed * rng.uniform(0.90, 1.08, len(smoothed)), 0, 100).round(1)
    result["risk_60m"] = np.clip(smoothed * rng.uniform(0.78, 1.14, len(smoothed)), 0, 100).round(1)
    result["severity"] = result["risk_15m"].apply(_sev)
    return result

def _sev(score):
    if score >= 70: return "Critical"
    if score >= 40: return "Warning"
    return "Healthy"

def feature_importance(domain: str) -> pd.DataFrame:
    models = get_models()
    clf    = models[domain].named_steps["clf"]
    feats  = DOMAIN_FEATURES[domain]
    return pd.DataFrame({"feature": feats, "importance": clf.feature_importances_}).sort_values("importance", ascending=False)
