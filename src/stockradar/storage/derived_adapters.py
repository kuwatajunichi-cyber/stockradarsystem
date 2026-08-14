"""Factory helpers for Phase 4.5 derived writer stores (Fake vs production)."""
from __future__ import annotations

import os

from stockradar.storage.derived_generation import FakeMetricGenerationStore, MetricGenerationPort
from stockradar.storage.metric_registry import FakeMetricRegistryStore, MetricRegistryPort
from stockradar.storage.r2_object_store import FakeR2ObjectStore, R2ObjectStorePort, S3R2ObjectStore
from stockradar.storage.supabase_metric_generation import SupabaseMetricGenerationAdapter
from stockradar.storage.supabase_metric_registry import SupabaseMetricRegistryAdapter

ENV_DERIVED_GENERATION_FAKE = "DERIVED_GENERATION_FAKE"


def is_derived_generation_fake() -> bool:
    return os.environ.get(ENV_DERIVED_GENERATION_FAKE, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def generation_store_from_env() -> MetricGenerationPort:
    if is_derived_generation_fake():
        return FakeMetricGenerationStore()
    return SupabaseMetricGenerationAdapter.from_env()


def r2_store_from_env() -> R2ObjectStorePort:
    if is_derived_generation_fake():
        return FakeR2ObjectStore()
    return S3R2ObjectStore.from_env()


def registry_store_from_env() -> MetricRegistryPort:
    if is_derived_generation_fake():
        return FakeMetricRegistryStore()
    return SupabaseMetricRegistryAdapter.from_env()
