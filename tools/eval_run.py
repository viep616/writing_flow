#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""eval_run · 回归基线工具（M4 验收项 7）

桩模式下连续运行完整 Flow N 次，采集确定性指标入库 git（eval/回归基线.json），
作为后续改动的对照基线：
  - 每次运行的 overall / 后缀语义 / 11 阶段完成
  - 固定名工件 SHA256 指纹（成稿/计划/契约/评审记录/致命一击/数值复核）
  - 跨 run 确定性：N 次指纹两两一致 ⇒ 桩产线确定性成立（改动后重跑 diff 即知是否破坏）
台账为 append-only 跨 run 增长，取当次增量行数而非全文指纹。

用法（仓库根目录，桩模式强制）：
    & ..\\.venv\\Scripts\\python.exe tools\\eval_run.py --runs 3
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
os.environ["WRITING_FLOW_STUB"] = "1"
sys.path.insert(0, str(REPO / "src"))

import writing_flow.main as wf  # noqa: E402

FINGERPRINT_FILES = [
    "论文_成稿.md", "论文_计划.md", "验收_契约.md",
    "评审_记录_R1.json", "评审_记录_R2.json", "致命一击.json", "数值_复核.json",
]
STAGES = ["load_inputs", "paper_plan", "negotiate_contract", "write_sections", "review_r1",
          "revise_paper", "review_r2", "kill_argument", "claim_audit", "verify_gates", "finalize"]


def _sha(path: Path) -> str:
    """稳定指纹：剥离工件内的易变时间戳字段后取 SHA（否则 _meta.generated_at 会造成假漂移）。"""
    import re

    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'"(generated_at|recorded_at|timestamp|data_sha256)"\s*:\s*("[^"]*"|null)', "", text)
    # data_sha256 派生自含提取时间戳的 QE 表（判道每次重新生成），属易变链，一并剥离
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_once(idx: int, ledger_lines_before: int) -> dict:
    t0 = time.time()
    flow = wf.PaperFlow()
    flow.kickoff()
    elapsed = round(time.time() - t0, 2)
    state = json.loads((wf.OUTPUT_DIR / "RUN_STATE.json").read_text(encoding="utf-8"))
    fingerprints = {name: _sha(wf.OUTPUT_DIR / name) for name in FINGERPRINT_FILES}
    ledger = (wf.OUTPUT_DIR / "义务_台账.jsonl")
    ledger_now = len(ledger.read_text(encoding="utf-8").strip().splitlines()) if ledger.is_file() else 0
    return {
        "run": idx,
        "elapsed_s": elapsed,
        "overall": state.get("overall"),
        "stages_done": sum(1 for s in STAGES if state["stages"].get(s) == "done"),
        "contract": state.get("contract_status"),
        "kill": state.get("kill", {}).get("verdict"),
        "audit_findings": state.get("audit", {}).get("findings"),
        "ledger_new_lines": ledger_now - ledger_lines_before,
        "fingerprints": fingerprints,
    }


def main() -> int:
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    ledger = wf.OUTPUT_DIR / "义务_台账.jsonl"
    before = len(ledger.read_text(encoding="utf-8").strip().splitlines()) if ledger.is_file() else 0
    results = []
    ledger_count = before
    for i in range(runs):
        r = run_once(i + 1, ledger_count)
        ledger_count += r["ledger_new_lines"]
        results.append(r)
        print(f"[eval] run {i + 1}/{runs}：overall={r['overall']} 阶段 {r['stages_done']}/11 "
              f"kill={r['kill']} findings={r['audit_findings']} {r['elapsed_s']}s")

    fp_sets = [tuple(r["fingerprints"].values()) for r in results]
    deterministic = len(set(fp_sets)) == 1
    baseline = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "stub", "runs": runs,
        "deterministic": deterministic,
        "expectation": {
            "overall": "provisional", "stages_done": 11, "contract": "accepted",
            "kill": "WARN", "audit_findings": 0, "ledger_new_lines_per_run": 2,
        },
        "runs": results,
        "note": "桩模式确定性基线：N 次指纹两两一致即 deterministic=true；"
                "后续任何改动后重跑本工具，与 eval/回归基线.json 对照即可发现行为漂移。",
    }
    out = REPO / "eval" / "回归基线.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval] 确定性：{'✅ N 次指纹一致' if deterministic else '❌ 指纹漂移'}｜基线 → {out}")
    ok = deterministic and all(r["overall"] == "provisional" and r["stages_done"] == 11 for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
