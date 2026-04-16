from datetime import datetime, timezone

from stockradar.jobs.cleanup_artifacts_lib import cutoff_epoch_utc, should_delete_artifact


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