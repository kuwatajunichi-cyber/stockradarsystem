# Track B signed URL capability（正本）

Phase 5 トラック B の入出力契約。英語本文が機械検証用の正本（トークン signed_url_capability）である。

Capability SSOT. mint is SignedUrlMintPort (`src/stockradar/storage/signed_url.py`), DDL is `017_download_grants.sql`, internal CLI is `scripts/storage/signed_url_mint_cli.py`. No public endpoint / Auth / Web UI. live_gate_5b closed with live evidence (docs alone cannot close). Phase 5 overall_status is in_progress. Issue #93 is OPEN. A contract-only **docs only** PR is not capability complete.

要約: private bucket 上の committed blob にだけ短命 GetObject 署名を fail-closed で発行する。orphan 拒否。TTL 60-3600 秒（既定 300）。監査表は download_grants。P0 継承（RLS ON、anon/authenticated REVOKE、user policy ゼロ、service_role のみ）。entitlement 未証明は拒否（allow-stub 禁止）。公開 Worker / 公開 mint は Track C まで禁止。単体テストは Fake。製品ロール・利用者 RLS・画面キーは Out of scope。

---

**Adopt token:** `signed_url_capability`  
**Gates:** [phase5_gate_status.yaml](../operations/phase5_gate_status.yaml) `pr-5b-signed-contract` (this contract) and `pr-5b-signed-capability` (mint / DDL / internal CLI)  
**ADR:** [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md) (R2 = blob / Supabase = control; user download resolves only committed rows)  
**Cloudflare:** [R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/) (S3 GetObject, bearer token, S3 API domain)

This file is the Track B input/output contract SSOT. [supabase_control_plane_schema.md](supabase_control_plane_schema.md) only names the table; do not treat it as this contract.

This file remains the Track B SSOT. Capability implementation must keep private bucket / committed / P0 / Fake / allow-stub forbidden. Do not mark live_gate_5b closed from docs or from mint code without live evidence. A contract-only docs only PR is not capability complete.

---

## Purpose

Define an internal capability to mint short-lived **GetObject** signed URLs for **committed** blobs on a **private bucket**, fail-closed. No screens. No product roles. Who may see which object is Track C (Auth / entitlements) plus the Web UI spec.

---

## In scope

| Item | Contract |
|------|----------|
| R2 | **private bucket**. Do not use public access or a public custom-domain bucket as delivery. |
| Resolve | Resolve `object_key` only from a control-plane **committed** row. Do not use R2 `ListObjects` on the normal path. |
| orphan | pending / orphan / missing committed row: **refuse** mint |
| Operation | **GetObject** only. Refuse PUT / DELETE signatures (exit 1). |
| TTL | `ttl_seconds` below. Do not stretch to the R2 max (7 days). |
| Audit | Table name `download_grants`. Record issued and denied. Do not persist the signed URL body. |
| P0 inherit | If DDL is added: RLS ON, REVOKE from `anon` / `authenticated` / `PUBLIC`, zero user policies, `service_role` only |
| Protocol | mint and entitlement proof are Protocols. Unit tests inject **Fake**. No production I/O. |
| entitlement | Unproven mint is refused. **allow-stub forbidden**. |

---

## Out of scope (do not write / do not do on this track)

- work / paid **product roles**
- Per-user RLS policies
- Keys a screen would require; series vs published product API
- Supabase Auth, billing webhooks, entitlements product (Track C)
- Web UI (Track D)
- Drive / Dropbox / `published/` customer-canonical cutover (Track E)
- **public mint** (public Worker / Edge Function / anonymous HTTP)
- Internal smoke exposed as a public endpoint
- Healthchecks / Watchdog / 5.5b `runs` views (Track A)

---

## Input / output

### Input

| Field | Constraint |
|-------|------------|
| `object_key` or `(source_table, source_id)` | One required. If both, they must match the committed row or refuse (`identity_mismatch`) |
| `operation` | `GetObject` only |
| `ttl_seconds` | Integer. Default **300**. Outside **60-3600** is refuse |
| `request_id` | Caller unique key. Same id + same object: refresh signature (keep grant_id). Same id + different object: refuse `request_id_conflict`. Do not silently sign a different object. |
| `actor_ref` | Opaque caller id. This contract does not define a product user UUID schema |
| entitlement proof | Continue only when `EntitlementProofPort` returns `proven`. Missing / `unproven` / `denied` refuse |

### Success output (exit 0)

| Field | Content |
|-------|---------|
| `grant_id` | `download_grants` primary key |
| `expires_at_utc` | mint time + `ttl_seconds` |
| `object_key` | Resolved logical key |
| `signed_url` | GetObject URL on the S3 API host. **Do not log, Step-Summary, or store the full URL** (query string is a bearer token) |

### Refuse / failure

| Exit | When |
|------|------|
| **1** | Contract: entitlement unproven, not committed, orphan, prefix rejected, bad TTL, not GetObject, allow-stub-equivalent skip |
| **2** | Runtime I/O: R2 HEAD/sign, Supabase write, network |

Do not fail silently. Insert `download_grants` with `mint_result=denied` and `reason_code` (no URL).

`reason_code` vocabulary:

- `entitlement_unproven`
- `entitlement_denied`
- `not_committed`
- `orphan`
- `object_missing`
- `identity_mismatch` (object_key and source identity disagree)
- `checksum_mismatch` (HEAD size / sha256 disagrees with the committed row)
- `prefix_rejected`
- `ttl_invalid`
- `operation_rejected`
- `public_bucket_forbidden`
- `request_id_conflict`

---

## R2 constraints

1. The delivery bucket is a **private bucket**. Track B must not adopt a public bucket or public custom domain as the delivery method.
2. Signed URLs use the S3 API domain (`*.r2.cloudflarestorage.com`) only. Presigned URLs do not work with custom domains (Cloudflare docs).
3. Sign server-side with AWS Signature V4. Never give R2 secrets to the client.
4. A presigned URL is a bearer token. Keep TTL short. Share only with the intended recipient.
5. HEAD before mint is **required** (not optional). Missing blob is `object_missing`. size / sha256 mismatch with the committed row is `checksum_mismatch`. Do not return success without a URL.

---

## Control-plane resolve (committed only)

Normal path:

1. Read the control-plane row from `object_key` or the source identity.
2. If status is not **committed**, refuse (`not_committed` / `orphan`).
3. Check `object_key` prefix against the known namespace list (safety rail, not a product catalog).
4. Required HEAD: size / sha256 mismatch is `checksum_mismatch` (do not sign). Missing blob is `object_missing`.
5. Sign GetObject only when entitlement is `proven`.

Known prefixes (aligned with [github_state_to_r2_supabase_mapping.md](github_state_to_r2_supabase_mapping.md)):

- `published/`
- `runs/`
- `cache/`
- `monthly/`
- `derived-snapshots/`
- `derived-series/`
- `derived-inputs/`
- `0011_work/`
- `0012_paid/`

Being able to resolve `0011_work` / `0012_paid` is **capability**. Assigning work/paid as user roles stays forbidden until Track C.

ADR-003: orphan R2 keys are not exposed for user download. Do not mint from a pending row.

---

## Entitlement proof (allow-stub forbidden)

Track B does not implement proof contents (Auth, billing, roles). mint only reads `EntitlementProofPort`.

| Proof | mint |
|-------|------|
| `proven` | Issue if other rules pass |
| `unproven` | Refuse (`entitlement_unproven`) |
| `denied` | Refuse (`entitlement_denied`) |
| Missing port / swallowed exception | Forbidden. fail-closed (exit 1). This is **allow-stub**. |

Fake default is `unproven`. Tests inject `proven` explicitly. Production wiring must not treat missing proof as allow.

Until Track C supplies real proof, no production public call path may exist. Internal smoke is `service_role` plus an explicit fixture only.

---

## `download_grants` (DDL: `017_download_grants.sql`; unique issued `request_id` also in `019_download_grants_issued_request_id.sql`)

Audit row location. Not the product entitlements table.

| Column | Role |
|--------|------|
| `id` | `grant_id` |
| `created_at_utc` | mint attempt time |
| `request_id` | Caller unique key |
| `object_key` | Logical key |
| `source_table` / `source_id` | Control-plane row used to resolve |
| `sha256` | Copied from committed row when known |
| `actor_ref` | Opaque |
| `operation` | `GetObject` |
| `ttl_seconds` | Requested TTL |
| `expires_at_utc` | Issued rows only |
| `mint_result` | `issued` / `denied` |
| `reason_code` | Required on deny; null on issue |

**Do not store:** full signed URL, R2 secrets, Healthchecks ping URL.

DDL **P0 inherit** is mandatory (`017_download_grants.sql`):

- `ENABLE ROW LEVEL SECURITY`
- `REVOKE ALL ... FROM PUBLIC, anon, authenticated`
- Zero policies for `anon` / `authenticated` (`pg_policies` empty for this table)
- `GRANT` to `service_role` only
- If RPC is added, REVOKE `EXECUTE` from `anon` / `authenticated`
- Catalog self-check at end of migration (same shape as `003_p0_control_plane_hardening.sql`). Failure is fail-fast rollback

Per-user RLS on this table is Track C. Do not mix user policies into Track B DDL.

---

## Protocol / Fake

I/O is Protocol. Unit tests use Fake. CI `unit` / `job_integration` / `smoke` must pass without Secrets.

Locked surface:

- `SignedUrlMintPort.mint_get(...)`
- `EntitlementProofPort.prove(...)`
- `CommittedObjectResolverPort.resolve(...)`
- R2 HEAD / presign either extends `R2ObjectStorePort` or a dedicated Port. Fake is required either way.

Production adapters are called only from GHA / internal CLI as `service_role`. Unit tests must not hit production R2 / Supabase.

---

## Public path forbidden

Until Track C, all of these are forbidden:

- public Worker mint
- Supabase Edge Function mint granted to anon / authenticated
- R2 public bucket as a substitute for signed URLs
- unauthenticated HTTP labeled "internal smoke"

live gate 5b must not stand up a public URL. Use a `service_role` CLI. Do not paste signed URL bodies into GitHub issues.

---

## Idempotency

- Re-mint of the same committed `object_key` may create a new signature (new `expires_at`). The blob bytes do not change.
- mint must not update the committed control-plane row.
- `request_id` lock: same object refreshes the issued row (new TTL / URL, same grant_id). Different object is `request_id_conflict` (exit 1). Do not silently sign a different object. Issued `request_id` is unique (`download_grants_issued_request_id`).
- Resolve `source_table` only from the allowlist: `artifact_index`, `cache_index`, `publish_status`, `derived_object_index`, `monthly_snapshots`. Unknown tables are `identity_mismatch`. `monthly_snapshots` may resolve core/ipo/illiquid/manifest keys.

---

## Observability

- Success may log `grant_id`, `object_key`, `expires_at_utc`, `mint_result=issued`.
- Deny must log `reason_code`.
- Do not emit `signed_url` full text, Secrets, or signature query strings. Do not skip-and-succeed on missing config.

---

## Implementation (pr-5b-signed-capability)

1. Protocol + Fake + unit tests in `stockradar.storage.signed_url`
2. DDL `017_download_grants.sql` (P0 inherit) plus follow-up `019_download_grants_issued_request_id.sql` for unique issued `request_id`. A contract-only docs only PR is not capability complete
3. Internal CLI `scripts/storage/signed_url_mint_cli.py`. Do not add a public Worker
4. CLI exit codes are in [exit_codes.md](exit_codes.md)

---

## live gate 5b (docs alone cannot close)

Minimum to close:

- `pr-5b-signed-contract` and `pr-5b-signed-capability` are `merged_and_verified`
- bucket remains a private bucket
- internal mint success evidence against a committed row (run URL; no signed URL body)
- evidence that not-committed / unproven / non-GetObject are refused
- no public endpoint

Closed 2026-09-09 with Issue #93 comment `5587796941` (internal CLI issued + refuse; no signed URL body; no public endpoint). Closing `live_gate_5b` leaves Phase 5 `overall_status` `in_progress`. Issue #93 stays OPEN.

---

## Related

- [ADR-003](../adr/adr-003-r2-supabase-control-blob-split.md)
- [issue_93_roadmap.md](../operations/issue_93_roadmap.md) Track B
- [issue_93_post_phase4_audit.md](../operations/issue_93_post_phase4_audit.md) (unauthorized R2 series publish)
- `supabase/migrations/003_p0_control_plane_hardening.sql`
