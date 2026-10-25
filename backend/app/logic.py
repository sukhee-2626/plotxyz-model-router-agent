"""Original deterministic implementation for Model Router (plotxyz-model-router-agent)."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'will', 'they', 'was', 'your', 'than', 'that', 'on', 'be', 'then', 'do', 'our', 'with', 'he', 'is', 'about', 'had', 'were', 'as', 'may', 'we', 'their', 'are', 'did', 'at', 'she', 'a', 'by', 'the', 'if', 'might', 'it', 'into', 'have', 'from', 'should', 'not', 'over', 'can', 'for', 'and', 'an', 'you', 'does', 'to', 'this', 'could', 'would', 'under', 'of', 'no', 'its', 'in', 'i', 'or', 'has'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_model_router(payload):
    models = _json(payload, "models", list)
    if not models or len(models) > 50:
        raise LogicError("'models' must contain 1-50 model entries")
    task = str(payload.get("task", "balanced")).lower()
    max_latency = _num(payload, "max_latency_ms", default=None, lo=1, hi=600000)
    max_cost = _num(payload, "max_cost_per_1k", default=None, lo=0, hi=10000)
    clean = []
    for item in models:
        if not isinstance(item, dict) or not item.get("name"):
            raise LogicError("each model needs a name")
        try:
            clean.append({
                "name": str(item["name"]),
                "capability": float(item.get("capability", 50)),
                "latency_ms": float(item.get("latency_ms", 1000)),
                "cost": float(item.get("cost_per_1k", 0)),
            })
        except (TypeError, ValueError):
            raise LogicError("model capability, latency_ms, and cost_per_1k must be numeric")
    weights = {"coding": (0.65, 0.15, 0.20), "chat": (0.45, 0.35, 0.20), "cheap": (0.30, 0.20, 0.50), "balanced": (0.50, 0.30, 0.20)}.get(task, (0.50, 0.30, 0.20))
    lat_max = max(m["latency_ms"] for m in clean) or 1
    cost_max = max(m["cost"] for m in clean) or 1
    rows = []
    for model in clean:
        if max_latency is not None and model["latency_ms"] > max_latency:
            continue
        if max_cost is not None and model["cost"] > max_cost:
            continue
        score = (
            model["capability"] * weights[0]
            + (1 - model["latency_ms"] / lat_max) * 100 * weights[1]
            + (1 - model["cost"] / cost_max) * 100 * weights[2]
        )
        rows.append([model["name"], model["capability"], model["latency_ms"], model["cost"], round(score, 1)])
    rows.sort(key=lambda row: row[4], reverse=True)
    findings = []
    if not rows:
        findings.append({"title": "No model satisfies the constraints", "severity": "high", "detail": "Relax latency or cost limits, or add another configured model."})
    chosen = rows[0][0] if rows else None
    if rows:
        findings.append({"title": "Routing decision", "severity": "info", "detail": f"Selected {chosen} using {task} weights. Scores combine capability, normalized latency, and normalized cost."})
    return _result(
        f"Selected {chosen or 'no model'} from {len(clean)} candidate(s).",
        {
            "metrics": {"selected": chosen, "eligible": len(rows), "task": task},
            "table": {"columns": ["Model", "Capability", "Latency (ms)", "Cost / 1k", "Score"], "rows": rows},
            "findings": findings,
        },
        ["Cost values are user-supplied; verify current provider pricing before production routing."],
    )


run = agent_model_router
