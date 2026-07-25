# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001033#repo.paths.outputs-must-be-repo-relative
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""MCP latency sample aggregation helpers.

Boundary contract:
- Owns: deterministic latency aggregation for MCP tool samples.
- Must not: collect live telemetry, execute tools, write reports, or perform IO.
- Allows: median, p95, max, success, and threshold summaries from samples.
- Split when: latency handling needs persistence, streaming, or dashboards.
- Merge when: another module computes the same MCP latency summary.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from mcp.models import McpLatencySample, McpLatencySummary

if TYPE_CHECKING:
    from collections.abc import Iterable


def summarize_tool_latency_samples(
    samples: Iterable[McpLatencySample],
    *,
    threshold_ms: float,
) -> tuple[McpLatencySummary, ...]:
    """Aggregate tool latency samples into sorted median and p95 summaries.

    Returns:
        The result produced by aggregating tool latency samples into
        median and p95 summaries.
    """
    grouped: dict[str, list[McpLatencySample]] = {}
    for sample in samples:
        grouped.setdefault(sample.tool_name, []).append(sample)
    summaries = tuple(
        _summarize_group(
            tool_name=tool_name,
            samples=tuple(grouped[tool_name]),
            threshold_ms=threshold_ms,
        )
        for tool_name in sorted(grouped)
    )
    return tuple(sorted(summaries, key=_summary_sort_key, reverse=True))


def _summarize_group(
    *,
    tool_name: str,
    samples: tuple[McpLatencySample, ...],
    threshold_ms: float,
) -> McpLatencySummary:
    """Return one tool summary."""
    latencies = tuple(sorted(sample.latency_ms for sample in samples))
    p95 = _percentile_ms(latencies, 0.95)
    return McpLatencySummary(
        tool_name=tool_name,
        sample_count=len(samples),
        success_count=sum(1 for sample in samples if sample.ok),
        failure_count=sum(1 for sample in samples if not sample.ok),
        median_latency_ms=_percentile_ms(latencies, 0.5),
        p95_latency_ms=p95,
        max_latency_ms=round(max(latencies), 3) if latencies else 0.0,
        exceeds_threshold=p95 > threshold_ms,
    )


def _summary_sort_key(summary: McpLatencySummary) -> tuple[float, float, str]:
    """Return the latency sorting key."""
    return (
        summary.p95_latency_ms,
        summary.median_latency_ms,
        summary.tool_name,
    )


def _percentile_ms(latencies: tuple[float, ...], percentile: float) -> float:
    """Return one rounded percentile using nearest-rank semantics."""
    if not latencies:
        return 0.0
    if len(latencies) == 1:
        return round(latencies[0], 3)
    rank = max(0, math.ceil(percentile * len(latencies)) - 1)
    return round(latencies[min(rank, len(latencies) - 1)], 3)
