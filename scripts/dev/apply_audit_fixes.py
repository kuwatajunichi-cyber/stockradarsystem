"""One-shot Phase 4.5 audit remediation (run: python scripts/dev/apply_audit_fixes.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch_canonicalize() -> None:
    path = ROOT / "src/stockradar/metrics/canonicalize.py"
    text = path.read_text(encoding="utf-8")
    if "struct" not in text:
        text = text.replace(
            "import math\nimport unicodedata",
            "import math\nimport struct\nimport unicodedata",
        )
    if "_binary64_to_decimal" not in text:
        text = text.replace(
            "DigestRow = dict[str, Any]\n\n\ndef canonical_decimal_string",
            (
                "DigestRow = dict[str, Any]\n\n\n"
                "def _binary64_to_decimal(value: float) -> Decimal:\n"
                "    return Decimal(struct.unpack('!d', struct.pack('!d', value))[0])\n\n\n"
                "def canonical_decimal_string"
            ),
        )
    text = text.replace(
        "dec = Decimal(str(value)).quantize",
        "dec = _binary64_to_decimal(value).quantize",
    )
    path.write_text(text, encoding="utf-8")


def patch_golden_vectors() -> None:
    path = ROOT / "tests/fixtures/phase45_golden_vectors.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("logical_digest_vectors", []):
        hex_val = item.get("utf8_hex")
        if isinstance(hex_val, str):
            item["utf8"] = bytes.fromhex(hex_val).decode("utf-8")
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def patch_absolute_contract() -> None:
    path = ROOT / "src/stockradar/governance/phase4_5_absolute_contract.py"
    text = path.read_text(encoding="utf-8")
    old = (
        "        if isinstance(utf8, str):\n"
        "            actual = hashlib.sha256(utf8.encode(\"utf-8\")).hexdigest()\n"
        "            if actual != expected_digest:\n"
        "                violations.append(f\"vector {name}: digest mismatch\")"
    )
    new = (
        "        utf8_hex = item.get(\"utf8_hex\")\n"
        "        if isinstance(utf8, str):\n"
        "            actual = hashlib.sha256(utf8.encode(\"utf-8\")).hexdigest()\n"
        "            if actual != expected_digest:\n"
        "                violations.append(f\"vector {name}: digest mismatch\")\n"
        "            if isinstance(utf8_hex, str):\n"
        "                try:\n"
        "                    from_hex = bytes.fromhex(utf8_hex)\n"
        "                except ValueError:\n"
        "                    violations.append(f\"vector {name}: invalid utf8_hex\")\n"
        "                else:\n"
        "                    if from_hex != utf8.encode(\"utf-8\"):\n"
        "                        violations.append(f\"vector {name}: utf8_hex mismatch\")"
    )
    if old in text and "utf8_hex mismatch" not in text:
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def patch_adr() -> None:
    path = ROOT / "docs/adr/phase45_canonical_digest.md"
    text = path.read_text(encoding="utf-8")
    needle = "5. NaN / ±Inf → null atom + metric listed in `non_finite_metrics`"
    extra = (
        "   Tagged atom for non-finite **float** metrics keeps "
        "`\"type\":\"float\"` with JSON `null` for `value` (not `\"type\":\"null\"`)."
    )
    if needle in text and extra not in text:
        text = text.replace(needle, needle + "\n" + extra)
        path.write_text(text, encoding="utf-8")


def patch_perfect_order() -> None:
    path = ROOT / "src/stockradar/metrics/perfect_order.py"
    text = path.read_text(encoding="utf-8")
    if "pd.isna(sub.iloc[-1])" not in text:
        text = text.replace(
            "    if pd.Timestamp(sub.index.max()).date() != run_date:\n"
            "        return None\n",
            "    if pd.Timestamp(sub.index.max()).date() != run_date:\n"
            "        return None\n"
            "    if pd.isna(sub.iloc[-1]):\n"
            "        return None\n",
        )
    if "ordered.isna().any()" not in text:
        text = text.replace(
            "    ordered = (sma25 > sma75) & (sma75 > sma200)\n"
            "    if ordered.isna().all():",
            "    ordered = (sma25 > sma75) & (sma75 > sma200)\n"
            "    if ordered.isna().any():\n"
            "        return None\n"
            "    if ordered.isna().all():",
        )
    path.write_text(text, encoding="utf-8")


def patch_verify_digest() -> None:
    path = ROOT / "scripts/storage/derived_bus_cli.py"
    text = path.read_text(encoding="utf-8")
    old = (
        "    expected = (args.expected_digest or \"\").strip().lower()\n"
        "    verified = not expected or digest == expected"
    )
    new = (
        "    expected = (args.expected_digest or \"\").strip().lower()\n"
        "    if not expected:\n"
        "        _emit(\n"
        "            {\n"
        "                \"status\": \"error\",\n"
        "                \"verified\": False,\n"
        "                \"reason\": \"expected_digest_required\",\n"
        "                \"logical_digest\": digest,\n"
        "            },\n"
        "            args.json_output,\n"
        "        )\n"
        "        return 2\n"
        "    verified = digest == expected"
    )
    if old in text:
        text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def patch_gate_docs() -> None:
    gs = ROOT / "docs/operations/phase4_5_gate_status.yaml"
    text = gs.read_text(encoding="utf-8")
    text = text.replace(
        "capacity_gate\n    open.'",
        "capacity_gate closed (Path B).'",
    )
    gs.write_text(text, encoding="utf-8")
    rm = ROOT / "docs/operations/issue_93_roadmap.md"
    rm_text = rm.read_text(encoding="utf-8")
    rm_text = rm_text.replace(
        "capacity_gate open・rollout off",
        "capacity_gate closed (Path B)・rollout off",
    )
    rm.write_text(rm_text, encoding="utf-8")


def update_yaml_fingerprints() -> None:
    import yaml

    from stockradar.metrics.fingerprint import compute_definition_fingerprint
    from stockradar.metrics.registry_spec import definition_payload_for_fingerprint

    for rel in ("config/metrics/metric_set_v1.yaml", "config/metrics/metric_set_v1_free.yaml"):
        ypath = ROOT / rel
        data = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        for item in data.get("members", []):
            item["definition_fingerprint"] = compute_definition_fingerprint(
                definition_payload_for_fingerprint(item)
            )
        ypath.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def patch_derived_generation_fake() -> None:
    path = ROOT / "src/stockradar/storage/derived_generation.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "def _object_coordinate_key(\n"
        "    *,\n"
        "    object_kind: str,\n"
        "    object_key: str,\n"
        "    trade_date: str | None,\n"
        "    instrument_code: str | None,\n"
        "    series_year: int | None,\n"
        ") -> tuple[str, str, str | None, str | None, int | None]:\n"
        "    return (\n"
        "        object_kind.strip().lower(),\n"
        "        object_key.strip(),\n"
        "        trade_date,\n"
        "        instrument_code,\n"
        "        series_year,\n"
        "    )",
        "def _object_coordinate_key(\n"
        "    *,\n"
        "    object_kind: str,\n"
        "    trade_date: str | None,\n"
        "    instrument_code: str | None,\n"
        "    series_year: int | None,\n"
        ") -> tuple[str, str | None, str | None, int | None]:\n"
        "    return (\n"
        "        object_kind.strip().lower(),\n"
        "        trade_date,\n"
        "        instrument_code,\n"
        "        series_year,\n"
        "    )",
    )
    text = text.replace(
        "    coord = _object_coordinate_key(\n"
        "      object_kind=object_kind,\n"
        "      object_key=object_key,\n"
        "      trade_date=trade_date,\n"
        "      instrument_code=instrument_code,\n"
        "      series_year=series_year,\n"
        "    )",
        "    coord = _object_coordinate_key(\n"
        "      object_kind=object_kind,\n"
        "      trade_date=trade_date,\n"
        "      instrument_code=instrument_code,\n"
        "      series_year=series_year,\n"
        "    )",
    )
    text = text.replace(
        "      existing_coord = _object_coordinate_key(\n"
        "        object_kind=str(existing[\"object_kind\"]),\n"
        "        object_key=str(existing[\"object_key\"]),\n"
        "        trade_date=existing.get(\"trade_date\"),\n"
        "        instrument_code=existing.get(\"instrument_code\"),\n"
        "        series_year=existing.get(\"series_year\"),\n"
        "      )",
        "      existing_coord = _object_coordinate_key(\n"
        "        object_kind=str(existing[\"object_kind\"]),\n"
        "        trade_date=existing.get(\"trade_date\"),\n"
        "        instrument_code=existing.get(\"instrument_code\"),\n"
        "        series_year=existing.get(\"series_year\"),\n"
        "      )",
    )
    if "committed_latest_observations" not in text:
        text = text.replace(
            "  committed_snapshot_digest_by_set_date: dict[tuple[str, str], str] = field(default_factory=dict)\n"
            "  identity_index: dict[tuple[str, ...], str] = field(default_factory=dict)",
            "  committed_snapshot_digest_by_set_date: dict[tuple[str, str], str] = field(default_factory=dict)\n"
            "  committed_latest_observations: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)\n"
            "  identity_index: dict[tuple[str, ...], str] = field(default_factory=dict)",
        )
    old_begin = (
        "      if status == GenerationStatus.COMMITTED.value:\n"
        "        if (\n"
        "          request.new_logical_digest\n"
        "          and row.get(\"new_logical_digest\") == request.new_logical_digest\n"
        "        ):\n"
        "          return self._to_generation_record(row)\n"
        "        raise GenerationConflictError(\n"
        "          f\"committed generation {existing_id!r} cannot be restarted with different payload\"\n"
        "        )\n"
        "      if status == GenerationStatus.FAILED.value:\n"
        "        raise GenerationConflictError(f\"generation {existing_id!r} is failed\")\n"
        "      row[\"heartbeat_at\"] = now\n"
        "      return self._to_generation_record(row)"
    )
    new_begin = (
        "      if status == GenerationStatus.COMMITTED.value:\n"
        "        if _generation_payload_mismatch(row, request, profile):\n"
        "          raise GenerationConflictError(\n"
        "            f\"committed generation {existing_id!r} cannot be restarted with different payload\"\n"
        "          )\n"
        "        return self._to_generation_record(row)\n"
        "      if status == GenerationStatus.FAILED.value:\n"
        "        raise GenerationConflictError(f\"generation {existing_id!r} is failed\")\n"
        "      if status == GenerationStatus.PENDING.value and _generation_payload_mismatch(row, request, profile):\n"
        "        raise GenerationConflictError(\n"
        "          f\"pending generation {existing_id!r} payload mismatch on retry\"\n"
        "        )\n"
        "      row[\"heartbeat_at\"] = now\n"
        "      return self._to_generation_record(row)"
    )
    if old_begin in text:
        text = text.replace(old_begin, new_begin)
    if "def _generation_payload_mismatch" not in text:
        text = text.replace(
            "def _object_coordinate_key(",
            "def _generation_payload_mismatch(\n"
            "    row: dict[str, Any],\n"
            "    request: BeginGenerationRequest,\n"
            "    profile: str,\n"
            ") -> bool:\n"
            "    if profile != str(row.get(\"artifact_profile\")):\n"
            "        return True\n"
            "    pairs = (\n"
            "        (\"expected_object_count\", request.expected_object_count),\n"
            "        (\"expected_object_set_digest\", request.expected_object_set_digest),\n"
            "        (\"expected_latest_set_digest\", request.expected_latest_set_digest),\n"
            "        (\"new_logical_digest\", request.new_logical_digest),\n"
            "        (\"expected_logical_digest\", request.expected_logical_digest),\n"
            "    )\n"
            "    for key, expected in pairs:\n"
            "        if expected is not None and row.get(key) != expected:\n"
            "            return True\n"
            "    return False\n\n\n"
            "def _object_coordinate_key(",
        )
    old_commit_tail = (
        "    expected_count = generation.get(\"expected_object_count\")\n"
        "    if expected_count is not None and int(expected_count) != len(objects):\n"
        "      raise GenerationConflictError(\"expected_object_count mismatch\")\n\n"
        "    now = self._now()"
    )
    new_commit_tail = (
        "    expected_count = generation.get(\"expected_object_count\")\n"
        "    if expected_count is not None and int(expected_count) != len(objects):\n"
        "      raise GenerationConflictError(\"expected_object_count mismatch\")\n\n"
        "    object_keys = [str(row[\"object_key\"]) for row in objects]\n"
        "    actual_object_set_digest = compute_object_set_digest(object_keys)\n"
        "    expected_object_set = generation.get(\"expected_object_set_digest\")\n"
        "    if expected_object_set is not None and actual_object_set_digest != str(expected_object_set).strip().lower():\n"
        "      raise GenerationConflictError(\"expected_object_set_digest mismatch\")\n\n"
        "    staging_rows = self._latest_rows(generation_id)\n"
        "    if profile == ArtifactProfile.SNAPSHOT_SERIES_LATEST.value and not staging_rows:\n"
        "      raise GenerationConflictError(\"latest staging required for profile\")\n"
        "    if staging_rows:\n"
        "      instrument_codes = sorted({row.instrument_code for row in staging_rows})\n"
        "      actual_latest_digest = compute_object_set_digest(instrument_codes)\n"
        "      expected_latest = generation.get(\"expected_latest_set_digest\")\n"
        "      if expected_latest is not None and actual_latest_digest != str(expected_latest).strip().lower():\n"
        "        raise GenerationConflictError(\"expected_latest_set_digest mismatch\")\n\n"
        "    now = self._now()"
    )
    if old_commit_tail in text:
        text = text.replace(old_commit_tail, new_commit_tail)
    old_commit_end = (
        "    if has_snapshot:\n"
        "      self.committed_snapshot_digest_by_set_date[(set_id, trade_date)] = digest\n"
        "    return self._to_generation_record(generation)"
    )
    new_commit_end = (
        "    if has_snapshot:\n"
        "      self.committed_snapshot_digest_by_set_date[(set_id, trade_date)] = digest\n"
        "    for row in staging_rows:\n"
        "      key = (set_id, row.instrument_code)\n"
        "      self.committed_latest_observations[key] = {\n"
        "        \"instrument_code\": row.instrument_code,\n"
        "        \"metric_set_version_id\": set_id,\n"
        "        \"trade_date\": row.trade_date,\n"
        "        \"values_json\": dict(row.values_json),\n"
        "        \"logical_digest\": row.logical_digest,\n"
        "        \"generation_id\": generation_id,\n"
        "      }\n"
        "    for key in list(self.latest_staging):\n"
        "      if key[0] == generation_id:\n"
        "        del self.latest_staging[key]\n"
        "    return self._to_generation_record(generation)"
    )
    if old_commit_end in text:
        text = text.replace(old_commit_end, new_commit_end)
    path.write_text(text, encoding="utf-8")


def write_indicators_converter() -> None:
    path = ROOT / "scripts/storage/indicators_csv_to_snapshot_json.py"
    path.write_text(
        '''"""Convert daily indicators CSV to derived snapshot JSON (Phase 4.5)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from stockradar.metrics.normalize_instrument_code import normalize_instrument_code
from stockradar.metrics.registry_spec import load_metric_set_spec


def indicators_csv_to_snapshot(csv_path: Path, metric_set_yaml: Path) -> dict[str, dict[str, object]]:
    spec = load_metric_set_spec(metric_set_yaml)
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if "code" not in df.columns:
        raise ValueError("indicators CSV requires code column")
    out: dict[str, dict[str, object]] = {}
    for _, row in df.iterrows():
        code = normalize_instrument_code(str(row["code"]))
        values: dict[str, object] = {}
        for member in spec.members:
            col = member.metric_key
            if col not in df.columns:
                continue
            val = row[col]
            if pd.isna(val):
                values[col] = None
            elif member.value_type == "int":
                values[col] = int(val)
            elif member.value_type == "float":
                values[col] = float(val)
            else:
                values[col] = val
        out[code] = values
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Indicators CSV to snapshot JSON")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--metric-set-yaml", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    snapshot = indicators_csv_to_snapshot(Path(args.csv), Path(args.metric_set_yaml))
    Path(args.output).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(snapshot)} instruments to {args.output}")


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )


def patch_daily_workflow() -> None:
    path = ROOT / ".github/workflows/daily.yml"
    text = path.read_text(encoding="utf-8")
    upload_step = (
        "      - name: Upload indicators writer handoff artifact\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        "          name: daily-indicators-writer-handoff\n"
        "          path: |\n"
        "            ${{ steps.indicators_csv.outputs.path }}\n"
        "            /tmp/r2_producer/compute_indicators/artifact-daily-indicators.json\n"
        "          if-no-files-found: error\n\n"
    )
    if "daily-indicators-writer-handoff" not in text:
        text = text.replace(
            "      - name: Write compute_indicators producer handoff summary\n",
            upload_step + "      - name: Write compute_indicators producer handoff summary\n",
        )
    download_step = (
        "      - name: Download indicators writer handoff artifact\n"
        "        if: steps.phase45.outputs.rollout_stage != 'off'\n"
        "        uses: actions/download-artifact@v4\n"
        "        with:\n"
        "          name: daily-indicators-writer-handoff\n"
        "          path: .\n\n"
    )
    if "Download indicators writer handoff" not in text:
        text = text.replace(
            "      - name: Phase A-B-C preflight\n",
            download_step + "      - name: Phase A-B-C preflight\n",
        )
    old_run = (
        "          DERIVED_GENERATION_FAKE: \"1\"\n"
        "          RUN_DATE: ${{ needs.resolve_trading_day.outputs.run_date }}\n"
    )
    new_run = (
        "          RUN_DATE: ${{ needs.resolve_trading_day.outputs.run_date }}\n"
    )
    if old_run in text:
        text = text.replace(old_run, new_run)
    old_cli = (
        "          python scripts/storage/derived_bus_cli.py put-generation \\\n"
        "            --mode \"$MODE\" \\\n"
        "            --trade-date \"$RUN_DATE\" \\\n"
        "            --phase4-5-rollout-stage \"${{ steps.phase45.outputs.rollout_stage }}\" \\\n"
        "            --metric-set-version-id \"$PHASE45_SHADOW_METRIC_SET_ID\" \\\n"
        "            --lifecycle-status \"$LIFECYCLE\" \\\n"
        "            --metric-set-yaml config/metrics/metric_set_v1_free.yaml \\\n"
        "            --snapshot-json tests/fixtures/phase45_ci_snapshot.json \\\n"
        "            --layer1-input-fingerprint \"$(python -c 'print(\"c\"*64)')\" \\\n"
    )
    new_cli = (
        "          RUN_DATE_COMPACT=\"${RUN_DATE//-/}\"\n"
        "          INDICATORS_CSV=\"data/indicators/daily/indicators_${RUN_DATE_COMPACT}.csv\"\n"
        "          SNAPSHOT_JSON=\"/tmp/derived_snapshot_${RUN_DATE_COMPACT}.json\"\n"
        "          python scripts/storage/indicators_csv_to_snapshot_json.py \\\n"
        "            --csv \"$INDICATORS_CSV\" \\\n"
        "            --metric-set-yaml config/metrics/metric_set_v1_free.yaml \\\n"
        "            --output \"$SNAPSHOT_JSON\"\n"
        "          LAYER1_FP=$(python -c \"import json;print(json.load(open('tmp/r2_producer/compute_indicators/artifact-daily-indicators.json',encoding='utf-8')).get('byte_sha256',''))\")\n"
        "          if [ \"$LIFECYCLE\" = \"shadow\" ]; then\n"
        "            export DERIVED_GENERATION_FAKE=1\n"
        "          fi\n"
        "          python scripts/storage/derived_bus_cli.py put-generation \\\n"
        "            --mode \"$MODE\" \\\n"
        "            --trade-date \"$RUN_DATE\" \\\n"
        "            --phase4-5-rollout-stage \"${{ steps.phase45.outputs.rollout_stage }}\" \\\n"
        "            --metric-set-version-id \"$PHASE45_SHADOW_METRIC_SET_ID\" \\\n"
        "            --lifecycle-status \"$LIFECYCLE\" \\\n"
        "            --metric-set-yaml config/metrics/metric_set_v1_free.yaml \\\n"
        "            --snapshot-json \"$SNAPSHOT_JSON\" \\\n"
        "            --layer1-input-fingerprint \"$LAYER1_FP\" \\\n"
    )
    if "--snapshot-json tests/fixtures/phase45_ci_snapshot.json" in text:
        text = text.replace(old_cli, new_cli)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_golden_vectors()
    patch_absolute_contract()
    patch_adr()
    patch_canonicalize()
    patch_perfect_order()
    patch_verify_digest()
    patch_gate_docs()
    patch_derived_generation_fake()
    write_indicators_converter()
    patch_daily_workflow()
    sys.path.insert(0, str(ROOT / "src"))
    update_yaml_fingerprints()
    print("apply_audit_fixes: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
