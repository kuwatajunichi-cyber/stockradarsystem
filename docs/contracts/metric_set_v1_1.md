# metric_set_v1_1 draft catalog

**Adopt token:** `metric_set_v1_1`
**Status:** Production-metrics **adoption** of `rs_sma75_topix` / `rs_sma75_nikkei` as the next set. ADR-004 **draft**. This file does not CAS. Ops CAS of the production pointer is recorded in `phase5_gate_status.yaml`, not here.
**Active YAML:** first-live full set is `config/metrics/metric_set_v1_1.yaml`. Do not grow `metric_set_v1.yaml` / `metric_set_v1_free.yaml` in place.
**First Web live:** empty SMA75 columns are forbidden. First-live active catalog is **full** `metric_set_v1_1.yaml` (not `_free`). `live_gate_5d` stays **open** until this set is **active** and bundles contain SMA75 RS. CAS requires `SMA75_NON_NULL_RATE_MIN` 0.98 on names with 105 trading-day lookback. This file does not CAS. Do not write Web UI complete.

## I/O

| Item | Contract |
|------|----------|
| Full set | `config/metrics/metric_set_v1_1.yaml` (`daily_core_v1_1`). v1 21 metrics + SMA75 RS 2 |
| Free set | `config/metrics/metric_set_v1_1_free.yaml`. v1_free 13 + SMA75 RS 2 |
| Definition | SMA75 series then B-method RS window 31. `min_history_days` / `lookback_trading_days` = 105. missing `null` |
| fingerprint | YAML `definition_fingerprint` is canonical JSON SHA-256; mismatch fails load |
| writer | YAML must match resolved UUID fingerprint before \egin_generation\. First Web live active YAML is \metric_set_v1_1.yaml\ (not this file) |
| writer | YAML must match resolved UUID fingerprint before `begin_generation`. First Web live active YAML is `metric_set_v1_1.yaml` (not this file) |
## Must not

- Grow `metric_set_v1.yaml` in place
- CAS active pointer, production backfill, or XLSX template revision from this file alone
- Turn the metric into advice
