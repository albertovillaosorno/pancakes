# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make operation estimation.

Boundary contract:
- Owns: tests for Make operation estimation behavior.
- Must not: test catalog compilation, blueprint repair, or repository tools.
- Allows: compact blueprint inputs and deterministic estimate assertions.
- Split when: estimator inputs and report formatting diverge.
- Merge when: another operation estimator test duplicates these cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import parse_make_ast_json_text
from blueprints.ast.operation_estimator import estimate_blueprint_operations

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstRoot
    from blueprints.ast.operation_estimator import (
        EstimateExecutionMode,
        OperationEstimate,
        OperationSafetyProfile,
    )

THIRTY_MINUTE_RUNS_PER_DAY = 48
ENABLED_BRANCH_OPERATIONS = 2
STRING_FLAG_ENABLED_BRANCH_OPERATIONS = 1
STRING_FLAG_DISABLED_BRANCH_WARNINGS = 2
FRACTIONAL_SEVEN_AND_HALF_MINUTE_RUNS_PER_HOUR = 8
NINE_HUNDRED_SECOND_RUNS_PER_DAY = 96
FIFTEEN_MINUTE_RUNS_PER_DAY = 96
TWO_HOUR_RUNS_PER_DAY = 12
FLOW_WITH_ERROR_HANDLER_OPERATIONS = 2
CONFIGURED_RETRY_OVERHEAD = 2
WORST_REASONABLE_SAFETY_OVERHEAD = 2
WORST_REASONABLE_OPERATIONS_PER_RUN = 4


def test_operation_estimator_calculates_every_thirty_minutes_over_day() -> None:
    """A 30-minute schedule over 24 hours produces 48 static runs."""
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "thirty-minute",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"every": 30, "unit": "minutes"}},
                }
            )
        ),
        horizon_hours=24,
    )

    assert estimate.run_count == THIRTY_MINUTE_RUNS_PER_DAY, (
        f"Expected 48 runs, got: {estimate}"
    )
    assert estimate.estimated_operations == THIRTY_MINUTE_RUNS_PER_DAY, (
        f"Expected 48 operations, got: {estimate}"
    )
    assert estimate.confidence_label == "conservative_planning", (
        f"Estimate confidence label is missing: {estimate}"
    )
    assert estimate.source_label == "static_ast_no_live_run_evidence", (
        f"Estimate source label is missing: {estimate}"
    )
    assert estimate.safety_profile == "minimum_known", (
        f"Default safety profile drifted: {estimate}"
    )
    assert estimate.minimum_operations_per_run == 1, (
        f"Minimum known estimate should have no safety overhead: {estimate}"
    )
    assert estimate.safety_overhead_per_run == 0, (
        f"Minimum known estimate should have no safety overhead: {estimate}"
    )
    assert estimate.precision_label == "exact_static_model", (
        f"Complete local model should have exact static precision: {estimate}"
    )
    assert not (estimate.evidence_gap_codes), (
        f"Complete local model should have no evidence gaps: {estimate}"
    )


def test_operation_estimator_rejects_unsupported_safety_profile() -> None:
    """Operation estimates reject unknown safety profiles at runtime."""
    with pytest.raises(
        ValueError, match="Unsupported operation estimate safety profile"
    ):
        _ = estimate_blueprint_operations(
            root=blueprint_with_schedule("day"),
            safety_profile=cast("OperationSafetyProfile", "shortcut"),
        )


def test_operation_estimator_rejects_non_positive_horizon() -> None:
    """Operation estimates require a positive planning horizon."""
    with pytest.raises(
        ValueError, match="horizon_hours must be a positive integer"
    ):
        _ = estimate_blueprint_operations(
            root=blueprint_with_schedule("day"),
            horizon_hours=0,
        )


def test_operation_estimator_rejects_non_integer_horizon() -> None:
    """Operation estimate horizons must be positive integers."""
    with pytest.raises(
        ValueError, match="horizon_hours must be a positive integer"
    ):
        _ = estimate_blueprint_operations(
            root=blueprint_with_schedule("day"),
            horizon_hours=cast("int", 1.5),
        )


def test_operation_estimator_rejects_unsupported_execution_mode() -> None:
    """Operation estimates reject unknown execution modes at runtime."""
    with pytest.raises(
        ValueError, match="Unsupported operation estimate execution mode"
    ):
        _ = estimate_blueprint_operations(
            root=blueprint_with_schedule("day"),
            execution_mode=cast("EstimateExecutionMode", "preview"),
        )


def test_operation_estimator_models_daily_weekly_and_run_once_modes() -> None:
    """Daily, weekly, run-once, and module-only modes are deterministic."""
    daily = estimate_blueprint_operations(
        root=blueprint_with_schedule("day"), horizon_hours=24
    )
    weekly = estimate_blueprint_operations(
        root=blueprint_with_schedule("week"), horizon_hours=168
    )
    run_once = estimate_blueprint_operations(
        root=blueprint_with_schedule("day"),
        execution_mode="run_once",
    )
    module_only = estimate_blueprint_operations(
        root=blueprint_with_schedule("day"),
        execution_mode="module_only",
        module_only_node_id="1",
    )

    assert daily.run_count == 1, (
        f"Daily and weekly estimates should each run once: {daily}, {weekly}"
    )
    assert weekly.run_count == 1, (
        f"Daily and weekly estimates should each run once: {daily}, {weekly}"
    )
    assert run_once.estimated_operations == 1, (
        f"Run-once estimate should execute one operation: {run_once}"
    )
    assert module_only.estimated_operations == 1, (
        f"Module-only estimate should execute one operation: {module_only}"
    )


def test_operation_estimator_counts_branches_and_skips_disabled_routes() -> (
    None
):
    """Enabled route flows count while disabled routes produce warnings."""
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "branches",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {"id": 2, "module": "http:MakeRequest"},
                                        {"id": 3, "module": "http:MakeRequest"},
                                    ]
                                },
                                {
                                    "disabled": True,
                                    "flow": [
                                        {"id": 4, "module": "http:MakeRequest"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    assert estimate.operations_per_run == ENABLED_BRANCH_OPERATIONS, (
        f"Disabled branch should be skipped: {estimate}"
    )
    assert not (
        "estimate.disabled_route_skipped" not in warning_codes(estimate)
    ), f"Disabled route warning is missing: {estimate.warnings}"


def test_operation_estimator_skips_string_disabled_route_flags() -> None:
    """String route flags from JSON-like intermediates disable route.

    estimates.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "string-disabled-branches",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "flow": [
                                        {"id": 2, "module": "http:MakeRequest"}
                                    ]
                                },
                                {
                                    "disabled": "true",
                                    "flow": [
                                        {"id": 3, "module": "http:MakeRequest"}
                                    ],
                                },
                                {
                                    "enabled": "false",
                                    "flow": [
                                        {"id": 4, "module": "http:MakeRequest"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    assert (
        estimate.operations_per_run == STRING_FLAG_ENABLED_BRANCH_OPERATIONS
    ), f"String-disabled routes should be skipped: {estimate}"
    assert (
        warning_codes(estimate).count("estimate.disabled_route_skipped")
        == STRING_FLAG_DISABLED_BRANCH_WARNINGS
    ), f"String-disabled routes should both warn: {estimate.warnings}"


def test_operation_estimator_counts_filtered_branches_conservatively() -> None:
    """Enabled filtered route flows count because static analysis cannot pick.

    one.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "filtered-branches",
                    "flow": [
                        {
                            "id": 1,
                            "module": "builtin:BasicRouter",
                            "routes": [
                                {
                                    "filter": {"condition": "{{1.score}} > 80"},
                                    "flow": [
                                        {"id": 2, "module": "http:MakeRequest"}
                                    ],
                                },
                                {
                                    "filter": {
                                        "condition": "{{1.score}} <= 80"
                                    },
                                    "flow": [
                                        {"id": 3, "module": "http:MakeRequest"}
                                    ],
                                },
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    assert estimate.operations_per_run == ENABLED_BRANCH_OPERATIONS, (
        f"Filtered branches should count conservatively: {estimate}"
    )


def test_operation_estimator_rejects_boolean_schedule_intervals() -> None:
    """Boolean schedule values are not valid numeric cadence evidence."""
    unsafe_schedule_secret = "sk-" + ("T" * 24)
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "boolean-interval",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {
                        "schedule": {
                            "interval": True,
                            "unit": "minutes",
                            "private_token": unsafe_schedule_secret,
                        }
                    },
                }
            )
        ),
        horizon_hours=24,
    )

    assert estimate.run_count == 1, (
        f"Boolean interval should fall back to one run: {estimate}"
    )
    assert not ("estimate.schedule_unknown" not in warning_codes(estimate)), (
        f"Boolean interval warning is missing: {estimate.warnings}"
    )
    leaked_messages = [
        warning.internal_message
        for warning in estimate.warnings
        if unsafe_schedule_secret in warning.internal_message
        or "private_token" in warning.internal_message
    ]
    assert not leaked_messages, (
        f"Schedule payload leaked into estimate warnings: {leaked_messages}"
    )


def test_operation_estimator_rejects_non_finite_schedule_intervals() -> None:
    """Non-finite schedule values are not valid numeric cadence evidence."""
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "infinite-interval",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"every_minutes": "inf"}},
                }
            )
        ),
        horizon_hours=24,
    )

    assert estimate.run_count == 1, (
        f"Infinite interval should fall back to one run: {estimate}"
    )
    assert not ("estimate.schedule_unknown" not in warning_codes(estimate)), (
        f"Infinite interval warning is missing: {estimate.warnings}"
    )


def test_operation_estimator_supports_fractional_and_second_intervals() -> None:
    """Make client intervals may be fractional minutes or raw seconds."""
    fractional = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "fractional-minutes",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"every_minutes": "7.5"}},
                }
            )
        ),
        horizon_hours=1,
    )
    seconds = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "seconds-interval",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {
                        "schedule": {"type": "indefinitely", "interval": 900}
                    },
                }
            )
        ),
        horizon_hours=24,
    )

    assert (
        fractional.run_count == FRACTIONAL_SEVEN_AND_HALF_MINUTE_RUNS_PER_HOUR
    ), f"Fractional interval should ceil to 8 runs: {fractional}"
    assert seconds.run_count == NINE_HUNDRED_SECOND_RUNS_PER_DAY, (
        f"900-second interval should produce 96 daily runs: {seconds}"
    )


def test_operation_estimator_warns_when_module_only_target_is_missing() -> None:
    """Module-only mode needs an explicit node target."""
    estimate = estimate_blueprint_operations(
        root=blueprint_with_schedule("day"),
        execution_mode="module_only",
    )

    assert estimate.operations_per_run == 1, (
        f"Missing module-only target should fall back to one: {estimate}"
    )
    assert not (
        "estimate.module_only_target_missing" not in warning_codes(estimate)
    ), f"Missing module-only warning is absent: {estimate.warnings}"


def test_operation_estimator_supports_text_interval_metadata() -> None:
    """Text schedule metadata can carry a declared interval."""
    description_estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "text-interval",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"description": "Every 2 hours"}},
                }
            )
        ),
        horizon_hours=24,
    )
    interval_estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "text-interval-field",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"interval": "15 minutes"}},
                }
            )
        ),
        horizon_hours=24,
    )

    assert description_estimate.run_count == TWO_HOUR_RUNS_PER_DAY, (
        f"Description interval should produce 12 runs: {description_estimate}"
    )
    assert interval_estimate.run_count == FIFTEEN_MINUTE_RUNS_PER_DAY, (
        f"Interval text should produce 96 runs: {interval_estimate}"
    )


def test_operation_estimator_warns_for_ai_tools_volume_and_large_tests() -> (
    None
):
    """AI/tool, iterator, pagination, and large-test uncertainty are.

    surfaced.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "large-test",
                    "flow": [
                        {"id": 1, "module": "ai-local-agent:RunLocalAIAgent"},
                        {
                            "id": 2,
                            "module": "builtin:Iterator",
                            "parameters": {"page": "{{page}}"},
                        },
                    ],
                    "metadata": {"schedule": {"every": 1, "unit": "minutes"}},
                }
            )
        ),
        horizon_hours=24,
    )
    codes = warning_codes(estimate)

    for expected_code in (
        "estimate.ai_tool_usage ",
        "estimate.iterator_multiplier_unknown ",
        "estimate.pagination_volume_unknown ",
        "estimate.large_test_cost",
    ):
        assert not (expected_code not in codes), (
            f"Expected estimator warning {expected_code!r}: {codes}"
        )
    assert "exact" not in estimate.client_summary.casefold(), (
        f"Client summary must not claim exact cost: {estimate.client_summary}"
    )


def test_operation_estimator_warns_for_aggregator_volume() -> None:
    """Aggregator nodes carry unknown-volume warnings."""
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "aggregator-volume",
                    "flow": [{"id": 1, "module": "builtin:ArrayAggregator"}],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    assert not (
        "estimate.aggregator_multiplier_unknown" not in warning_codes(estimate)
    ), f"Aggregator volume warning is missing: {estimate.warnings}"


def test_operation_estimator_counts_error_routes_conservatively() -> None:
    """Direct error-handler routes count as possible operations with a.

    warning.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "error-routes",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [{"id": 2, "module": "builtin:Ignore"}],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    assert estimate.operations_per_run == FLOW_WITH_ERROR_HANDLER_OPERATIONS, (
        f"Error-handler operation was not counted: {estimate}"
    )
    assert not (
        "estimate.error_routes_included" not in warning_codes(estimate)
    ), f"Error-route warning is missing: {estimate.warnings}"


def test_operation_estimator_configured_profile_counts_retry_overhead() -> None:
    """Configured-profile cost includes explicit retry attempts from local.

    metadata.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "configured-retry-cost",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "onerror": [
                                {
                                    "id": 2,
                                    "module": "builtin:Retry ",
                                    "strategy": "retry",
                                    "retry": {
                                        "count": CONFIGURED_RETRY_OVERHEAD
                                    },
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        ),
        safety_profile="configured_profile",
    )

    assert (
        estimate.minimum_operations_per_run
        == FLOW_WITH_ERROR_HANDLER_OPERATIONS
    ), f"Configured profile should preserve minimum known cost: {estimate}"
    assert estimate.safety_overhead_per_run == CONFIGURED_RETRY_OVERHEAD, (
        f"Configured retry overhead was not counted: {estimate}"
    )
    expected_operations_per_run = (
        FLOW_WITH_ERROR_HANDLER_OPERATIONS + CONFIGURED_RETRY_OVERHEAD
    )
    assert estimate.operations_per_run == expected_operations_per_run, (
        f"Configured safety cost did not affect operations per run: {estimate}"
    )
    assert not (
        "estimate.configured_retry_overhead_included"
        not in warning_codes(estimate)
    ), f"Configured retry overhead warning is missing: {estimate.warnings}"


def test_operation_estimator_configured_profile_remains_ec0d6c() -> None:
    """Configured-profile cost remains unchanged when no local safety overhead.

    exists.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "configured-no-extra-cost",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        ),
        safety_profile="configured_profile",
    )

    assert estimate.minimum_operations_per_run == 1, (
        f"Configured profile should keep unchanged cost without retry: "
        f"{estimate}"
    )
    assert estimate.operations_per_run == 1, (
        f"Configured profile should keep unchanged cost without retry: "
        f"{estimate}"
    )
    assert estimate.safety_overhead_operations == 0, (
        f"Configured profile should report zero added safety cost: {estimate}"
    )
    assert not (estimate.evidence_gap_codes), (
        f"Complete unchanged profile should have no evidence gaps: {estimate}"
    )


def test_operation_estimator_worst_reasonable_profile_e3091720() -> None:
    """Worst reasonable local safety adds one possible handler branch per.

    unsafe.

    module.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "worst-reasonable-safety",
                    "flow": [
                        {"id": 1, "module": "http:MakeRequest"},
                        {"id": 2, "module": "datastore:DeleteRecord"},
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        ),
        safety_profile="worst_reasonable_local_safety",
    )

    assert (
        estimate.minimum_operations_per_run == WORST_REASONABLE_SAFETY_OVERHEAD
    ), f"Minimum known cost should count existing modules: {estimate}"
    assert (
        estimate.safety_overhead_per_run == WORST_REASONABLE_SAFETY_OVERHEAD
    ), f"Worst reasonable safety overhead drifted: {estimate}"
    assert estimate.operations_per_run == WORST_REASONABLE_OPERATIONS_PER_RUN, (
        f"Worst reasonable safety profile did not add handler branches: "
        f"{estimate}"
    )
    assert not (
        "estimate.safety_handler_overhead_included"
        not in warning_codes(estimate)
    ), f"Safety handler overhead warning is missing: {estimate.warnings}"


def test_operation_estimator_marks_missing_schedule_as_evidence_gap() -> None:
    """Missing required schedule fields make precision conservative, not.

    exact.
    """
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "missing-schedule-evidence-gap",
                    "flow": [{"id": 1, "module": "http:MakeRequest"}],
                }
            )
        )
    )

    assert estimate.precision_label == "conservative_with_evidence_gaps", (
        f"Missing schedule should prevent exact static precision: {estimate}"
    )
    assert estimate.evidence_gap_codes == ("estimate.schedule_missing",), (
        f"Missing schedule evidence gap is not explicit: {estimate}"
    )
    assert "exact" not in estimate.client_summary.casefold(), (
        f"Client summary must not claim exact cost: {estimate.client_summary}"
    )


def test_operation_estimator_pagination_warning_is_node_local() -> None:
    """Pagination warnings do not inherit child route payload text."""
    estimate = estimate_blueprint_operations(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "child-page-warning",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {"endpoint": "/contacts"},
                            "routes": [
                                {
                                    "flow": [
                                        {
                                            "id": 2,
                                            "module": "util:SetVariable",
                                            "parameters": {"page": "{{page}}"},
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                    "metadata": {"schedule": {"interval": "day"}},
                }
            )
        )
    )

    page_warning_ids = tuple(
        warning.node_id
        for warning in estimate.warnings
        if warning.code == "estimate.pagination_volume_unknown"
    )

    assert "1" not in page_warning_ids, (
        f"Parent node inherited child pagination text: {estimate.warnings}"
    )
    assert not ("2" not in page_warning_ids), (
        f"Child node pagination warning is missing: {estimate.warnings}"
    )


def blueprint_with_schedule(interval: str) -> MakeAstRoot:
    """Return a one-module AST with a schedule interval."""
    return parse_make_ast_json_text(
        json.dumps(
            {
                "name": f"{interval}-schedule",
                "flow": [{"id": 1, "module": "http:MakeRequest"}],
                "metadata": {"schedule": {"interval": interval}},
            }
        )
    )


def warning_codes(estimate: OperationEstimate) -> tuple[str, ...]:
    """Return warning codes from an operation estimate."""
    return tuple(warning.code for warning in estimate.warnings)
