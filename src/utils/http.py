"""Cached, rate-limited API access.

Every response is stored once under data/raw/<source>/ together with the request
and the collection timestamp. A request that is already cached is never sent
again, so the analysis can be rerun offline (set PIPELINE_OFFLINE=1 to forbid
any network access).

CryptoCompare calls are counted in data/raw/cryptocompare/_call_log.csv against
a monthly budget (the current key allows 100 calls per month).
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import certifi
import pandas as pd
import requests
from dotenv import dotenv_values

import config

_ENV = {**dotenv_values(config.ROOT / ".env"), **os.environ}
_LAST_CALL = {}


class OfflineError(RuntimeError):
    pass


class BudgetError(RuntimeError):
    pass


class CachedApiError(RuntimeError):
    """A deterministic API error that was cached (never requested again)."""


def _key(method, url, params, body):
    blob = json.dumps({"m": method, "u": url, "p": params or {}, "b": body or {}}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def _path(source, name, key):
    d = config.DATA_RAW / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}__{key}.json"


def _log_error(source, name, msg):
    d = config.DATA_RAW / source
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "_errors.log", "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\t{name}\t{msg[:300]}\n")


def _throttle(source, min_interval):
    wait = _LAST_CALL.get(source, 0) + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[source] = time.time()


# ---------------------------------------------------------------- CryptoCompare budget
CC_LOG = config.DATA_RAW / "cryptocompare" / "_call_log.csv"


def cc_calls_this_month():
    if not CC_LOG.exists():
        return 0
    log = pd.read_csv(CC_LOG)
    log["called_at"] = pd.to_datetime(log["called_at"], utc=True, format="ISO8601")
    now = datetime.now(timezone.utc)
    m = (log.called_at.dt.year == now.year) & (log.called_at.dt.month == now.month)
    return int(m.sum())


def _cc_log(endpoint, params, status, note=""):
    CC_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{"called_at": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint,
                         "params": json.dumps(params, sort_keys=True), "status": status, "note": note}])
    row.to_csv(CC_LOG, mode="a", header=not CC_LOG.exists(), index=False)


# ---------------------------------------------------------------- core
def cached(source, name, method, url, params=None, body=None, headers=None,
           min_interval=1.0, retries=5, validate=None):
    """Return the parsed JSON response, from cache when available.

    validate(json) -> error string or None; responses that fail validation are
    not cached (so a later run retries them) and raise RuntimeError.
    """
    key = _key(method, url, params, body)
    path = _path(source, name, key)
    if path.exists():
        cached_obj = json.loads(path.read_text())
        if cached_obj.get("is_error"):
            raise CachedApiError(f"{source}/{name}: {cached_obj.get('error')}")
        return cached_obj["response"]
    if os.environ.get("PIPELINE_OFFLINE") == "1":
        raise OfflineError(f"not cached and offline: {source}/{name}")

    is_cc = source == "cryptocompare"
    if is_cc and cc_calls_this_month() >= config.CC_MONTHLY_BUDGET:
        raise BudgetError(f"CryptoCompare monthly budget {config.CC_MONTHLY_BUDGET} used up")

    last_err = None
    for attempt in range(retries):
        _throttle(source, min_interval)
        try:
            r = requests.request(method, url, params=params, json=body, headers=headers or {},
                                 timeout=60, verify=certifi.where())
        except requests.RequestException as exc:
            last_err = str(exc)
            time.sleep(2 ** attempt)
            continue
        if is_cc:
            _cc_log(url.rsplit("/", 1)[-1], params, r.status_code)
        if r.status_code != 200:
            _log_error(source, name, f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code == 429:
            last_err = "HTTP 429"
            time.sleep(min(60, 5 * 2 ** attempt))
            if is_cc:
                break  # do not burn the monthly budget on retries
            continue
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            if is_cc or 400 <= r.status_code < 500:
                break
            time.sleep(2 ** attempt)
            continue
        data = r.json()
        err = validate(data) if validate else None
        if err:
            last_err = err
            _log_error(source, name, err)
            if is_cc:
                # cache the error so a paid call is never repeated
                path.write_text(json.dumps({
                    "source": source, "name": name, "collected_at": datetime.now(timezone.utc).isoformat(),
                    "request": {"method": method, "url": url, "params": params, "body": body},
                    "is_error": True, "error": err, "response": data}, ensure_ascii=False))
                raise CachedApiError(f"{source}/{name}: {err}")
            if "GraphQL" in err:
                break  # deterministic errors: retrying does not help
            time.sleep(2 ** attempt)
            continue
        path.write_text(json.dumps({
            "source": source, "name": name, "collected_at": datetime.now(timezone.utc).isoformat(),
            "request": {"method": method, "url": url, "params": params, "body": body},
            "response": data}, ensure_ascii=False))
        return data
    raise RuntimeError(f"{source}/{name} failed: {last_err}")


# ---------------------------------------------------------------- Tally
def _tally_validate(j):
    if j.get("errors"):
        return "GraphQL errors: " + json.dumps(j["errors"])[:400]
    return None


def tally(name, query, variables=None):
    api_key = (_ENV.get("TALLY_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("TALLY_API_KEY missing in .env")
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}
    body = {"query": query, "variables": variables or {}}
    return cached("tally", name, "POST", config.TALLY_API_URL, body=body, headers=headers,
                  min_interval=config.TALLY_MIN_INTERVAL, validate=_tally_validate)["data"]


# ---------------------------------------------------------------- CryptoCompare
def _cc_validate(j):
    if isinstance(j, dict) and j.get("Response") == "Error":
        return "CryptoCompare error: " + str(j.get("Message"))[:300]
    return None


def cryptocompare(name, path, params):
    api_key = (_ENV.get("CRYPTOCOMPARE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("CRYPTOCOMPARE_API_KEY missing in .env")
    return cached("cryptocompare", name, "GET", f"{config.CRYPTOCOMPARE_BASE}{path}", params=params,
                  headers={"authorization": f"Apikey {api_key}"},
                  min_interval=config.CC_MIN_INTERVAL, retries=1, validate=_cc_validate)
