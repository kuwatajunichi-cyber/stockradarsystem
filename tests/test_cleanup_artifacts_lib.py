from datetime import datetime, timezone

import pytest

from stockradar.jobs.cleanup_artifacts_lib import (
    coerce_yaml_bool,
    cutoff_epoch_utc,
    should_delete_artifact,
)

pytestmark = pytest.mark.unit


def test_should_delete_artifact_prefix_and_age() -> None:
    now = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)
    cut = cutoff_epoch_utc(keep_days=2, now=now)
    assert should_delete_artifact(
        "daily-core-csv-123",
        "2026-04-10T00:00:00Z",
        prefix="daily-core-csv-",
        cutoff_epoch=cut,
    )
    assert not should_delete_artifact(
        "daily-core-csv-124",
        "2026-04-15T23:00:00Z",
        prefix="daily-core-csv-",
        cutoff_epoch=cut,
    )
    assert not should_delete_artifact(
        "other-prefix-124",
        "2026-04-01T00:00:00Z",
        prefix="daily-core-csv-",
        cutoff_epoch=cut,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        (0, False),
        (1, True),
        ("false", False),
        ("FALSE", False),
        ("true", True),
        ("no", False),
        ("yes", True),
        ("off", False),
        ("on", True),
    ],
)
def test_coerce_yaml_bool_accepts_typed_values(raw: object, expected: bool) -> None:
    assert coerce_yaml_bool(raw, field="enabled") is expected


@pytest.mark.parametrize("raw", ["maybe", "", "2", [], {}])
def test_coerce_yaml_bool_rejects_invalid(raw: object) -> None:
    with pytest.raises(ValueError):
        coerce_yaml_bool(raw, field="enabled")