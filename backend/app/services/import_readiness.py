from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReadinessCheck:
    key: str
    label: str
    passed: bool
    blocker_count: int = 0


@dataclass
class ImportReadinessResult:
    is_ready: bool
    checks: list[ReadinessCheck]
    blockers: list[ImportReadinessBlocker]


@dataclass
class ImportReadinessBlocker:
    key: str
    label: str
    count: int


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _count_missing_required_fields(clean_payload: dict[str, object], required_fields: list[str]) -> int:
    return sum(1 for field in required_fields if _is_empty(clean_payload.get(field)))


def _count_schema_mismatches(clean_payload: dict[str, object], template_columns: list[dict[str, object]]) -> int:
    template_names = {str(column.get("name")) for column in template_columns if column.get("name")}
    payload_names = set(clean_payload)
    return len(template_names.symmetric_difference(payload_names))


def _collect_blockers(checks: list[ReadinessCheck]) -> list[ImportReadinessBlocker]:
    return [
        ImportReadinessBlocker(key=check.key, label=check.label, count=check.blocker_count)
        for check in checks
        if not check.passed and check.blocker_count > 0
    ]


def evaluate_import_readiness(
    *,
    clean_payload: dict[str, object],
    required_fields: list[str] | None = None,
    template_columns: list[dict[str, object]] | None = None,
    is_duplicate: bool = False,
) -> ImportReadinessResult:
    required = required_fields or []
    columns = template_columns or []

    missing_required_count = _count_missing_required_fields(clean_payload, required)
    duplicate_count = 1 if is_duplicate else 0
    schema_mismatch_count = _count_schema_mismatches(clean_payload, columns) if columns else 0

    checks = [
        ReadinessCheck(
            key="required_critical_fields",
            label="Required critical fields filled",
            passed=missing_required_count == 0,
            blocker_count=missing_required_count,
        ),
        ReadinessCheck(
            key="duplicates",
            label="No duplicate records detected",
            passed=duplicate_count == 0,
            blocker_count=duplicate_count,
        ),
        ReadinessCheck(
            key="schema_match",
            label="Schema matches template",
            passed=schema_mismatch_count == 0,
            blocker_count=schema_mismatch_count,
        ),
    ]

    return ImportReadinessResult(
        is_ready=all(check.passed for check in checks),
        checks=checks,
        blockers=_collect_blockers(checks),
    )
