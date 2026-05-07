"""
tests/accuracy_eval.py — CER ベースの OCR 精度評価フレームワーク

使い方:
    python tests/accuracy_eval.py --mode cloud  --gt-dir tests/ground_truth
    python tests/accuracy_eval.py --all-modes   --gt-dir tests/ground_truth --output report.md

実際の OCR API を呼ばずに既存の JSON 出力と比較する場合:
    python tests/accuracy_eval.py --compare actual.json ground_truth.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# CER calculation (edit distance / total characters)
# ---------------------------------------------------------------------------

def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein distance (character level)."""
    m, n = len(s1), len(s2)
    if m == 0:
        return n
    if n == 0:
        return m

    # Only keep two rows to save memory
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + cost # substitution
            )
        prev, curr = curr, prev
    return prev[n]


def calc_cer(actual: str, expected: str) -> float:
    """
    Character Error Rate = edit_distance(actual, expected) / len(expected).
    Returns 0.0 for empty expected (no ground truth to evaluate against).
    """
    if not expected:
        return 0.0
    return _edit_distance(actual, expected) / len(expected)


# ---------------------------------------------------------------------------
# Flatten structured JSON → plain text for CER
# ---------------------------------------------------------------------------

def flatten_to_text(data: Any) -> str:
    """
    Recursively flatten a dict/list structure to a single string.
    Joins all string leaf values in order.
    """
    parts: list[str] = []
    _collect(data, parts)
    return "".join(parts)


def _collect(obj: Any, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect(item, out)


# ---------------------------------------------------------------------------
# Structural diff (JSON-level match rate)
# ---------------------------------------------------------------------------

def calc_struct_match(actual: dict, expected: dict) -> float:
    """
    Recursively count matching leaf values.
    Returns (matches / total_expected_leaves).
    """
    total, matched = _count_leaves(expected, actual)
    if total == 0:
        return 1.0
    return matched / total


def _count_leaves(expected: Any, actual: Any) -> tuple[int, int]:
    total = 0
    matched = 0
    if isinstance(expected, dict):
        for k, v in expected.items():
            t, m = _count_leaves(v, actual.get(k) if isinstance(actual, dict) else None)
            total += t
            matched += m
    elif isinstance(expected, list):
        for i, item in enumerate(expected):
            actual_item = actual[i] if isinstance(actual, list) and i < len(actual) else None
            t, m = _count_leaves(item, actual_item)
            total += t
            matched += m
    else:
        total = 1
        matched = 1 if expected == actual else 0
    return total, matched


# ---------------------------------------------------------------------------
# Ground truth helpers
# ---------------------------------------------------------------------------

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth"

# CER acceptance thresholds from ARCHITECTURE.md §10.2
CER_TARGETS: dict[str, dict[str, float]] = {
    "koyomi":  {"cloud": 0.01, "hybrid": 0.03, "local": 0.10},
    "daichou": {"cloud": 0.03, "hybrid": 0.08, "local": 0.20},
    "honbun":  {"cloud": 0.05, "hybrid": 0.15, "local": 0.30},
}


def load_ground_truth(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_ground_truth_files(gt_dir: Path) -> dict[str, list[Path]]:
    """Return dict of document_type → [Path, ...]."""
    result: dict[str, list[Path]] = {}
    for p in sorted(gt_dir.glob("*.json")):
        doc_type = p.stem.rsplit("_", 1)[0]  # koyomi_001 → koyomi
        result.setdefault(doc_type, []).append(p)
    return result


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

def evaluate_pair(actual: dict, expected: dict) -> dict[str, float]:
    """Compare one actual result against one ground truth."""
    actual_text   = flatten_to_text(actual)
    expected_text = flatten_to_text(expected)
    cer           = calc_cer(actual_text, expected_text)
    struct_match  = calc_struct_match(actual, expected)
    return {
        "cer":          round(cer, 4),
        "struct_match": round(struct_match, 4),
        "char_count":   len(expected_text),
    }


def evaluate_file(actual_path: Path, gt_path: Path) -> dict:
    actual   = load_ground_truth(actual_path)
    expected = load_ground_truth(gt_path)
    metrics  = evaluate_pair(actual, expected)
    doc_type = expected.get("document_type", "unknown")
    return {
        "file":          gt_path.name,
        "document_type": doc_type,
        **metrics,
    }


def evaluate_results(
    results: list[dict],  # list of {file, document_type, cer, struct_match, char_count}
    mode: str,
) -> dict:
    """Aggregate per-file metrics into a summary report."""
    by_type: dict[str, list[float]] = {}
    for r in results:
        dt = r["document_type"]
        by_type.setdefault(dt, []).append(r["cer"])

    summary_by_type = {}
    passed_targets  = []
    for dt, cers in by_type.items():
        avg_cer = sum(cers) / len(cers)
        target  = CER_TARGETS.get(dt, {}).get(mode, None)
        passed  = avg_cer <= target if target is not None else None
        summary_by_type[dt] = {
            "average_cer":      round(avg_cer, 4),
            "target_cer":       target,
            "passed":           passed,
            "file_count":       len(cers),
        }
        if passed is not None:
            passed_targets.append(passed)

    all_cers  = [r["cer"] for r in results]
    overall   = sum(all_cers) / len(all_cers) if all_cers else 0.0

    return {
        "mode":           mode,
        "overall_cer":    round(overall, 4),
        "by_document_type": summary_by_type,
        "all_passed":     all(passed_targets) if passed_targets else None,
        "files":          results,
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(reports: list[dict]) -> str:
    lines = ["# OCR 精度評価レポート\n"]
    lines.append("## モード別 CER サマリ\n")
    lines.append("| 文書種別 | モード | 平均 CER | 目標 CER | 合否 |")
    lines.append("|---|---|---|---|---|")

    for report in reports:
        mode = report["mode"]
        for dt, summary in report["by_document_type"].items():
            avg    = f"{summary['average_cer']:.2%}"
            target = f"{summary['target_cer']:.2%}" if summary["target_cer"] is not None else "—"
            passed = "✅" if summary["passed"] else ("❌" if summary["passed"] is False else "—")
            lines.append(f"| {dt} | {mode} | {avg} | {target} | {passed} |")

    lines.append("")
    lines.append("## ファイル別詳細\n")
    for report in reports:
        lines.append(f"### モード: {report['mode']}\n")
        lines.append("| ファイル | 文書種別 | CER | 構造一致率 |")
        lines.append("|---|---|---|---|")
        for f in report["files"]:
            cer   = f"{f['cer']:.2%}"
            match = f"{f['struct_match']:.2%}"
            lines.append(f"| {f['file']} | {f['document_type']} | {cer} | {match} |")
        lines.append("")

    return "\n".join(lines)


def render_json(reports: list[dict]) -> str:
    return json.dumps(reports, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# compare subcommand
# ---------------------------------------------------------------------------

def cmd_compare(actual_path: Path, gt_path: Path) -> None:
    actual   = load_ground_truth(actual_path)
    expected = load_ground_truth(gt_path)
    metrics  = evaluate_pair(actual, expected)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    cer = metrics["cer"]
    print(f"\nCER: {cer:.2%}  ({'ok' if cer < 0.05 else 'FAIL'})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR 精度評価ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # compare subcommand
    cmp_p = sub.add_parser("compare", help="2つのJSONを直接比較")
    cmp_p.add_argument("actual",   type=Path)
    cmp_p.add_argument("expected", type=Path)

    # evaluate subcommand (for pre-computed results dir)
    eval_p = sub.add_parser("evaluate", help="結果ディレクトリと正解データを比較")
    eval_p.add_argument("--results-dir", type=Path, required=True, help="実際の出力 JSON ディレクトリ")
    eval_p.add_argument("--gt-dir",      type=Path, default=GROUND_TRUTH_DIR)
    eval_p.add_argument("--mode",        default="cloud")
    eval_p.add_argument("--output",      type=Path, help="レポート出力先 (.md または .json)")
    eval_p.add_argument("--format",      choices=["md", "json"], default="md")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.command == "compare":
        cmd_compare(args.actual, args.expected)
        return 0

    if args.command == "evaluate":
        gt_files = list_ground_truth_files(args.gt_dir)
        file_results: list[dict] = []

        for doc_type, gt_paths in gt_files.items():
            for gt_path in gt_paths:
                actual_path = args.results_dir / gt_path.name
                if not actual_path.exists():
                    print(f"[warn] skip {gt_path.name}: no matching result in {args.results_dir}")
                    continue
                file_results.append(evaluate_file(actual_path, gt_path))

        if not file_results:
            print("[error] 比較できるファイルが見つかりません")
            return 1

        report  = evaluate_results(file_results, args.mode)
        reports = [report]

        fmt    = args.format
        if args.output:
            fmt = "json" if args.output.suffix == ".json" else "md"

        rendered = render_json(reports) if fmt == "json" else render_markdown(reports)

        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
            print(f"レポートを {args.output} に保存しました")
        else:
            print(rendered)

        return 0 if report.get("all_passed") is not False else 1

    # No subcommand
    _parse_args(["--help"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
