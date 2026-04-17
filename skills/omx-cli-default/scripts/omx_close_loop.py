#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _avg(history: list[dict[str, Any]], key: str) -> float:
    vals = []
    for h in history:
        try:
            vals.append(float(h.get(key) or 0.0))
        except Exception:
            pass
    return sum(vals) / len(vals) if vals else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist OMX feedback history and generate next-run brief")
    ap.add_argument("--feedback", required=True, help="Path to feedback JSON from omx_feedback_eval.py")
    ap.add_argument("--state", default=".omx/state/skill-feedback/omx-cli-default.json", help="State history JSON path")
    ap.add_argument("--brief", default=".omx/plans/omx-next-run-brief.md", help="Output next-run brief markdown path")
    ap.add_argument("--goal", default="执行用户目标并稳定完成验证", help="Current execution goal")
    args = ap.parse_args()

    feedback = _read_json(Path(args.feedback).expanduser().resolve())
    state_path = Path(args.state).expanduser().resolve()
    brief_path = Path(args.brief).expanduser().resolve()

    state = _read_json(state_path)
    history = list(state.get("history") or [])

    m = feedback.get("metrics") or {}
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "overall_score": float(feedback.get("overall_score") or 0.0),
        "module_coverage": float(m.get("module_coverage") or 0.0),
        "yield_ratio": float(m.get("yield_ratio") or 0.0),
        "reliability": float(m.get("reliability") or 0.0),
        "grade": str(feedback.get("grade") or "D"),
    }
    history.append(row)
    history = history[-50:]

    recent = history[-7:]
    baseline = {
        "overall_score_avg7": round(_avg(recent, "overall_score"), 4),
        "module_coverage_avg7": round(_avg(recent, "module_coverage"), 4),
        "yield_ratio_avg7": round(_avg(recent, "yield_ratio"), 4),
        "reliability_avg7": round(_avg(recent, "reliability"), 4),
    }

    delta = {
        "overall_score_delta": round(row["overall_score"] - baseline["overall_score_avg7"], 4),
        "module_coverage_delta": round(row["module_coverage"] - baseline["module_coverage_avg7"], 4),
        "yield_ratio_delta": round(row["yield_ratio"] - baseline["yield_ratio_avg7"], 4),
        "reliability_delta": round(row["reliability"] - baseline["reliability_avg7"], 4),
    }

    progress = []
    if delta["overall_score_delta"] > 0:
        progress.append("总评分较近7次上升")
    if delta["module_coverage_delta"] > 0:
        progress.append("模块覆盖提升")
    if delta["yield_ratio_delta"] > 0:
        progress.append("有效产出率提升")
    if delta["reliability_delta"] > 0:
        progress.append("稳定性提升")
    if not progress:
        progress.append("暂无显著提升，按建议继续收敛")

    state_obj = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "history": history,
        "baseline_avg7": baseline,
        "last_feedback": feedback,
        "last_delta": delta,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    recs = feedback.get("recommendations") or []
    brief_lines = [
        "# OMX 下一轮执行简报",
        "",
        f"- 目标: {args.goal}",
        f"- 当前等级: {feedback.get('grade','D')}",
        f"- 当前总评分: {feedback.get('overall_score',0)}",
        f"- 近7次均值: {baseline['overall_score_avg7']}",
        f"- 评分变化: {delta['overall_score_delta']}",
        "",
        "## 进步信号",
    ]
    brief_lines.extend([f"- {x}" for x in progress])
    brief_lines.append("")
    brief_lines.append("## 下一轮优化动作")
    brief_lines.extend([f"- {x}" for x in recs[:5]] or ["- 保持当前策略"]) 
    brief_lines.append("")
    brief_lines.append("## 执行模板")
    brief_lines.append("- 先跑 OMX 主执行命令")
    brief_lines.append("- 再跑反馈评估脚本")
    brief_lines.append("- 最后依据本简报微调查询词/路由/验证门槛")

    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("\n".join(brief_lines) + "\n", encoding="utf-8")

    print(str(state_path))
    print(str(brief_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
