# Phase 4.5 canonical logical digest (SSOT)

This document is the authoritative specification for `logical_digest` bytes used in
derived snapshot identity, reconcile, and manifest metadata. Implementations MUST
match exact UTF-8 bytes and SHA-256 hashes in `tests/fixtures/phase45_golden_vectors.json`.

## Scope

- **logical_digest**: semantic identity of a trade-date snapshot (all instruments × metrics)
- **object_sha256**: SHA-256 of actual Parquet / gzip / manifest bytes (separate from logical)
- **manifest_sha256**: SHA-256 of manifest JSON bytes (self-hash field excluded from payload)

## Serialization rules

1. UTF-8, no BOM, Unicode NFC, no newlines inside JSON
2. JSON separators: `,` and `:` (compact, no extra whitespace)
3. No ASCII `\uXXXX` escapes for non-ASCII when UTF-8 direct encoding is valid
4. Object key order is **fixed** — do not rely on generic `sort_keys`

## Top-level payload

Fixed key order:

```json
{"schema_version":1,"trade_date":"YYYY-MM-DD","metric_set_version_id":"<lowercase-uuid>","rows":[...]}
```

- `metric_set_version_id` MUST be lowercase UUID string
- `trade_date` ISO date `YYYY-MM-DD`

## Rows

- Sorted by `instrument_code` Unicode code point ascending
- Each row:

```json
{"instrument_code":"...","values":[...],"flags":{...}}
```

## Values (tagged atoms)

Metric order follows metric set ordinal (YAML catalog). Each atom:

```json
{"metric_key":"k","type":"float","value":"1.23"}
```

Supported types: `float`, `int`, `bool`, `string`, `null`.

### Float canonical decimal string

1. Convert finite binary64 to `Decimal`, round-half-even to 10 decimal places
2. Render without exponent notation
3. Strip trailing zeros and trailing decimal point
4. `-0` → `"0"`
5. NaN / ±Inf → null atom + metric listed in `non_finite_metrics`
   Tagged atom for non-finite **float** metrics keeps `"type":"float"` with JSON `null` for `value` (not `"type":"null"`).

### Int / bool / string / null

- Explicit `type` field always present
- null type uses JSON `null` for `value`

## Row flags (fixed schema, fixed key order)

```json
{"missing_metrics":[...],"non_finite_metrics":[...],"po_indeterminate":false}
```

- Arrays sorted by metric set ordinal, no duplicates
- Missing inputs → `missing_metrics`
- Non-finite floats → null atom + `non_finite_metrics`
- Perfect Order indeterminate (history only) → `po_indeterminate: true`

## SHA-256

Apply SHA-256 to the exact UTF-8 bytes of the serialized payload.

## Golden vectors

See `tests/fixtures/phase45_golden_vectors.json` for:

- `-0.0`, tie-breaking, NaN/Inf, Unicode instrument codes
- Row order, metric order, flags projection
- Expected exact bytes (hex) and SHA-256

## Series canonical bytes

Separate payload for symbol-year gzip JSON:

```json
{"schema_version":1,"instrument_code":"...","year":YYYY,"dates":["YYYY-MM-DD",...],"series":{"metric_key":[...]},"flags":[...]}
```

Fixed key order; dates ascending; series keys in metric ordinal order.

## Change control

Changes require updating this document, golden vectors, and honesty/absolute contract tests **before** code changes (Phase 4.5 §0.2).
