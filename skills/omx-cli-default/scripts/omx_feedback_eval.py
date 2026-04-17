#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _score_from_report(report: dict[str, Any]) -> dict[str, Any]:
    modules = report.get("modules") or {}
    collection = report.get("collection_stats") or {}
    errors = report.get("errors") or []
    generic_steps = report.get("steps") or report.get("tasks") or []

    module_count = len([k for k, v in modules.items() if isinstance(v, list) and len(v) > 0])
    returned = int(collection.get("returned") or len(report.get("items") or []))
    raw = int(collection.get("raw_collected") or 0)
    dropped_old = int(collection.get("dropped_outside_48h") or 0)
    dropped_irrelevant = int(collection.get("dropped_irrelevant") or 0)

    generic_mode = module_count == 0 and raw == 0 and returned == 0

    # If the report is not a digest-style schema, fallback to generic metrics.
    if generic_mode:
        total = int(report.get("steps_total") or len(generic_steps) or 1)
        done = int(report.get("steps_done") or report.get("tasks_done") or total)
        failed_checks = int(report.get("failed_checks") or report.get("failed") or 0)
        failures = failed_checks + (len(errors) if isinstance(errors, list) else 0)

        coverage = min(1.0, max(0.0, done / max(total, 1)))
        yield_ratio = max(0.0, 1.0 - min(1.0, failures / max(total, 1)))
        freshness_penalty = 0.0
        noise_penalty = 0.0
        reliability = max(0.0, 1.0 - min(1.0, failures / 10.0))
    else:
        coverage = min(1.0, module_count / 6.0)
        yield_ratio = (returned / raw) if raw > 0 else 0.0
        freshness_penalty = min(1.0, dropped_old / max(raw, 1))
        noise_penalty = min(1.0, dropped_irrelevant / max(raw, 1))
        reliability = max(0.0, 1.0 - min(1.0, len(errors) / 10.0))

    overall = (
        coverage * 0.35
        + yield_ratio * 0.20
        + reliability * 0.25
        + (1.0 - freshness_penalty) * 0.10
        + (1.0 - noise_penalty) * 0.10
    )

    recommendations: list[str] = []
    if generic_mode:
        if coverage < 0.8:
            recommendations.append("完成率偏低：拆小任务并补齐未完成步骤。")
        if reliability < 0.8:
            recommendations.append("稳定性偏低：优先修复失败检查再继续扩展。")
        if yield_ratio < 0.7:
            recommendations.append("有效输出不足：增加验证证据和结果摘要。")
    else:
        if coverage < 0.6:
            recommendations.append("模块覆盖不足：扩展查询词，优先补齐高管/创业模块。")
        if yield_ratio < 0.08:
            recommendations.append("产出率偏低：增加高时效来源权重并放宽单点反查门槛。")
        if reliability < 0.8:
            recommendations.append("错误偏多：先修复前3类错误源，再执行日报。")
        if freshness_penalty > 0.5:
            recommendations.append("超窗淘汰偏高：提升 day/news 源，减少周级低时效源。")
        if noise_penalty > 0.3:
            recommendations.append("噪声偏高：加强 AI 关键词过滤与域名白名单。")
    if not recommendations:
        recommendations.append("当前质量稳定：保持策略并继续滚动优化查询词。")

    level = "A" if overall >= 0.85 else "B" if overall >= 0.7 else "C" if overall >= 0.55 else "D"

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "metrics": {
            "module_coverage": round(coverage, 4),
            "yield_ratio": round(yield_ratio, 4),
            "reliability": round(reliability, 4),
            "freshness_penalty": round(freshness_penalty, 4),
            "noise_penalty": round(noise_penalty, 4),
        },
        "overall_score": round(overall, 4),
        "grade": level,
        "recommendations": recommendations,
        "source_report_generated_at": report.get("generated_at_iso") or report.get("generated_at_bj"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate OMX task output quality and emit feedback JSON")
    ap.add_argument("--report", required=True, help="Path to output JSON report")
    ap.add_argument("--out", required=True, help="Path to write feedback JSON")
    args = ap.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    report = _load_json(report_path)
    feedback = _score_from_report(report)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
