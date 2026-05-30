"""
Shared Kernel — 可观测性 (plan.md §4.6.3)。

Prometheus metrics、结构化日志、健康检查端点。
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Prometheus Metrics (轻量实现，无第三方依赖)
# ---------------------------------------------------------------------------


@dataclass
class MetricSample:
    """单个指标采样。"""

    name: str = ""
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsRegistry:
    """轻量 Prometheus 兼容指标注册表。

    支持 Counter、Gauge、Histogram 三种类型，
    可输出 Prometheus text exposition format。
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, *, description: str = "", metric_type: str = "gauge") -> None:
        """注册指标描述。"""
        self._descriptions[name] = description

    def inc_counter(self, name: str, *, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """递增 Counter。"""
        key = self._make_key(name, labels)
        self._counters[key] += value

    def set_gauge(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        """设置 Gauge 值。"""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        """观察 Histogram 值。"""
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        # Keep max 1000 observations per bucket
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-500:]

    def get_counter(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0.0)

    def get_histogram_stats(self, name: str, *, labels: dict[str, str] | None = None) -> dict[str, float]:
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def export_prometheus_text(self) -> str:
        """Export metrics in Prometheus text exposition format."""
        lines: list[str] = []

        # Counters
        for key, value in sorted(self._counters.items()):
            name, label_str = self._parse_key(key)
            desc = self._descriptions.get(name, "")
            if desc and f"# HELP {name}" not in "\n".join(lines):
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{label_str} {value}")

        # Gauges
        for key, value in sorted(self._gauges.items()):
            name, label_str = self._parse_key(key)
            desc = self._descriptions.get(name, "")
            if desc and f"# HELP {name}" not in "\n".join(lines):
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{label_str} {value}")

        # Histograms
        seen_names: set[str] = set()
        for key, values in sorted(self._histograms.items()):
            name, label_str = self._parse_key(key)
            if name in seen_names:
                continue
            seen_names.add(name)
            desc = self._descriptions.get(name, "")
            if desc and f"# HELP {name}" not in "\n".join(lines):
                lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} histogram")
            if values:
                lines.append(f"{name}_count{label_str} {len(values)}")
                lines.append(f"{name}_sum{label_str} {sum(values):.6f}")

        return "\n".join(lines) + "\n" if lines else ""

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        label_parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_parts}}}"

    def _parse_key(self, key: str) -> tuple[str, str]:
        if "{" in key:
            idx = key.index("{")
            return key[:idx], key[idx:]
        return key, ""


# ---------------------------------------------------------------------------
# Application Metrics — 预定义指标
# ---------------------------------------------------------------------------


class AppMetrics:
    """应用级预定义指标。"""

    API_REQUEST_DURATION = "aiteamos_api_request_duration_seconds"
    API_REQUEST_TOTAL = "aiteamos_api_requests_total"
    EVENT_CONSUMPTION_LAG = "aiteamos_event_consumption_lag_seconds"
    OUTBOX_BACKLOG = "aiteamos_outbox_backlog"
    TASK_FIRST_PASS = "aiteamos_task_first_pass_total"
    TASK_FAILED = "aiteamos_task_failed_total"

    def __init__(self, registry: MetricsRegistry | None = None):
        self.registry = registry or MetricsRegistry()
        self._register_all()

    def _register_all(self) -> None:
        self.registry.register(
            self.API_REQUEST_DURATION,
            description="API request duration in seconds",
            metric_type="histogram",
        )
        self.registry.register(
            self.API_REQUEST_TOTAL,
            description="Total API requests",
            metric_type="counter",
        )
        self.registry.register(
            self.EVENT_CONSUMPTION_LAG,
            description="Event consumption lag in seconds",
            metric_type="gauge",
        )
        self.registry.register(
            self.OUTBOX_BACKLOG,
            description="Number of unpublished outbox entries",
            metric_type="gauge",
        )
        self.registry.register(
            self.TASK_FIRST_PASS,
            description="Tasks passed on first attempt",
            metric_type="counter",
        )
        self.registry.register(
            self.TASK_FAILED,
            description="Tasks failed",
            metric_type="counter",
        )

    def record_api_request(
        self,
        *,
        method: str,
        path: str,
        duration: float,
        status_code: int = 200,
    ) -> None:
        """记录 API 请求。"""
        labels = {"method": method, "path": path, "status": str(status_code)}
        self.registry.observe_histogram(self.API_REQUEST_DURATION, duration, labels=labels)
        self.registry.inc_counter(self.API_REQUEST_TOTAL, labels=labels)

    def set_event_consumption_lag(self, lag_seconds: float) -> None:
        """设置事件消费延迟。"""
        self.registry.set_gauge(self.EVENT_CONSUMPTION_LAG, lag_seconds)

    def set_outbox_backlog(self, count: int) -> None:
        """设置 Outbox 积压数。"""
        self.registry.set_gauge(self.OUTBOX_BACKLOG, float(count))


# ---------------------------------------------------------------------------
# Structured Logger (JSON)
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """JSON 结构化日志格式。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        # Include extra fields
        for key in ("request_id", "task_id", "event_type", "duration_ms", "shard_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, ensure_ascii=False)


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Configure root logger with JSON structured output."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


@dataclass
class HealthCheckResult:
    """健康检查结果。"""

    status: str = "ok"  # ok | degraded | unhealthy
    checks: dict[str, str] = field(default_factory=dict)
    version: str = ""
    uptime_seconds: float = 0.0


class HealthChecker:
    """健康检查聚合器。"""

    def __init__(self, *, version: str = "0.1.0"):
        self._version = version
        self._start_time = time.time()
        self._checks: dict[str, Any] = {}

    def register_check(self, name: str, checker: Any) -> None:
        """注册一个健康检查项。

        checker 必须实现 async def check() -> bool
        """
        self._checks[name] = checker

    async def check(self) -> HealthCheckResult:
        """执行所有健康检查。"""
        results: dict[str, str] = {}
        all_ok = True

        for name, checker in self._checks.items():
            try:
                ok = await checker.check()
                results[name] = "ok" if ok else "failed"
                if not ok:
                    all_ok = False
            except Exception as e:
                results[name] = f"error: {e}"
                all_ok = False

        return HealthCheckResult(
            status="ok" if (all_ok and results) else ("degraded" if results else "unhealthy"),
            checks=results,
            version=self._version,
            uptime_seconds=round(time.time() - self._start_time, 2),
        )

    def to_dict(self, result: HealthCheckResult) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "status": result.status,
            "version": result.version,
            "uptime_seconds": result.uptime_seconds,
            "checks": result.checks,
        }
