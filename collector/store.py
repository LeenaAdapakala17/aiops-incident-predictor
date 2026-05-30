"""
In-memory time-series store.
Keeps the last MAX_ROWS rows per domain as a rolling buffer.
All pages read from this shared store via st.session_state.
"""
import pandas as pd

MAX_ROWS = 500   # ~8 hrs at 15s interval per entity

DOMAINS = ["kubernetes", "cloud", "network", "application"]


def init_store(state):
    """Initialise store in Streamlit session state if not present."""
    if "ts_store" not in state:
        state["ts_store"] = {d: pd.DataFrame() for d in DOMAINS}
    if "scrape_count" not in state:
        state["scrape_count"] = 0
    if "collecting" not in state:
        state["collecting"] = False


def append_scrape(state, batch: dict):
    """Append one scrape batch to the store."""
    for domain, df in batch.items():
        existing = state["ts_store"][domain]
        combined = pd.concat([existing, df], ignore_index=True)
        # keep last MAX_ROWS rows
        if len(combined) > MAX_ROWS:
            combined = combined.iloc[-MAX_ROWS:]
        state["ts_store"][domain] = combined
    state["scrape_count"] = state.get("scrape_count", 0) + 1


def get_domain(state, domain: str) -> pd.DataFrame:
    return state["ts_store"].get(domain, pd.DataFrame())


def get_latest(state, domain: str) -> pd.DataFrame:
    """Return the most recent scrape per entity."""
    df = get_domain(state, domain)
    if df.empty:
        return df
    entity_col = _entity_col(domain)
    if entity_col not in df.columns:
        return df.tail(20)
    return df.groupby(entity_col).last().reset_index()


def reset_store(state):
    state["ts_store"]    = {d: pd.DataFrame() for d in DOMAINS}
    state["scrape_count"] = 0


def _entity_col(domain):
    return {"kubernetes": "pod", "cloud": "vm",
            "network": "service", "application": "service"}.get(domain, "entity")
