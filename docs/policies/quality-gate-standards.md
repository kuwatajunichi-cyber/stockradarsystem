# Quality Gate Standards

## Purpose

This document defines operational standards that apply quality governance principles to the current implementation.
This file is expected to evolve as workflows and architecture change.

## 1. Contract Scope

### 1.1 Required contracts

Each job/CLI should define:

- Input contract (required args, format, prerequisites)
- Output contract (artifacts, ordering, missing value policy)
- Exit code contract (error classes)
- Idempotency contract (same condition rerun behavior)
- Failure visibility contract (logs, summary, manifest)

### 1.2 Contract document location

Store contracts under `docs/contracts/`:

- `exit_codes.md`
- `datetime_normalization.md`
- `determinism_and_idempotency.md`
- `workflow_preflight_contract.md`

## 2. Test Standards

- `unit`: pure logic, boundaries, contract audit
- `job_integration`: job contracts, parallel equivalence, rerun consistency
- `smoke`: entrypoint-level contract checks including exit behavior

Markers must be registered. Unknown markers are treated as failures.

## 3. CI and Workflow Standards

### 3.1 Common preflight

Production workflows must not start main jobs unless common preflight passes.

### 3.2 Minimum preflight checks

- lint
- type check
- contract smoke
- workflow lint (actionlint + shellcheck)

### 3.3 Workflow shell guidance

- Use `set -euo pipefail` in shell blocks
- Quote variable expansion
- Quote `$GITHUB_OUTPUT` path
- Bind `${{ ... }}` to local variables before command use
- Prefer machine-safe listing over `ls | head | xargs`

## 4. Artifact Integrity

- Keep deterministic output ordering
- Guarantee idempotent rerun behavior for same inputs/run date
- Expose exclusion/degradation/retry states in logs or metadata

## 5. Change Management

When contract changes are involved, follow this order:

1. Update contract docs
2. Update acceptance tests
3. Update implementation
4. Update CI gates
5. Confirm rollback unit

Recommended PR notes:

- Changed vs unchanged contracts
- Scope impact
- Failure behavior
- Validation results (lint/type/test/actionlint)
- Rollback unit

## 6. Operational acceptance

A change is accepted when:

- Contract tests pass
- Common preflight passes
- Production workflows still enforce start blocking on preflight failure
- Core artifact contracts (integrity/idempotency/determinism) are satisfied

## 7. Review cadence

- For each new feature: decide whether a new contract is needed
- For each new workflow: verify common preflight wiring
- Quarterly: audit drift between contracts and implementation
