#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""resume_flow · 断点恢复入口（M4：坑 6/12 配方固化，零 LLM 重跑已完成阶段）

用法（仓库根目录）：
    & ..\\.venv\\Scripts\\python.exe tools\\resume_flow.py --list
    & ..\\.venv\\Scripts\\python.exe tools\\resume_flow.py --uuid <id> [--before <ISO 时间>]

设计依据（HANDOVER 坑 12 实测结论）：
  - crewai 官方 kickoff() 不带参会清空 _completed_methods 从头重跑 → 不用；
  - reload(execution_data) + inputs id 的「监听已完成方法」尾部不触发 → 不用官方 replay；
  - 可靠配方：按时间窗取状态库快照 → flow._state = ArisPaperState.model_validate →
    直接顺序调用剩余方法（同一份真实代码，不经 DAG），路由结果由已存状态字段重放。
坑 6：--uuid 未命中显式报错退出（exit 2），绝不静默回退从头跑。
注意：恢复时的运行模式（桩/真实）取当前环境变量，应与原运行保持一致；
      --before 用于跳过被中止重跑写入的污染行（取该时间前的最后快照）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
sys.path.insert(0, str(REPO / "src"))

import writing_flow.main as wf  # noqa: E402  模块级完成 .appdata 重定向 + .env + 路径

DB = REPO / ".appdata" / "flow_states.db"
ALL_STAGES = ["load_inputs", "paper_plan", "negotiate_contract", "write_sections", "review_r1",
              "revise_paper", "review_r2", "kill_argument", "claim_audit", "verify_gates", "finalize"]


def list_runs() -> None:
    if not DB.is_file():
        print("[恢复] 状态库不存在（无历史运行）")
        return
    con = sqlite3.connect(DB)
    rows = con.execute(
        "select flow_uuid, method_name, timestamp, state_json from flow_states order by rowid"
    ).fetchall()
    con.close()
    runs: dict[str, dict] = {}
    for uuid, method, ts, state_json in rows:
        runs.setdefault(uuid, {"snapshots": 0, "last_ts": "", "state": None})
        runs[uuid]["snapshots"] += 1
        runs[uuid]["last_ts"] = ts
        runs[uuid]["state"] = state_json
    print(f"[恢复] 状态库共 {len(runs)} 个运行：")
    for uuid, info in sorted(runs.items(), key=lambda kv: kv[1]["last_ts"], reverse=True):
        state = json.loads(info["state"])
        stages = state.get("stage_status", {})
        done = [s for s in ALL_STAGES if stages.get(s) == "done"]
        finished = "✅ 已完成" if len(done) == len(ALL_STAGES) else f"⏸ 中断于 {done[-1] if done else '开始前'}"
        print(f"  {uuid}\n    快照 {info['snapshots']}｜{finished}（{len(done)}/{len(ALL_STAGES)}）"
              f"｜stamp={state.get('stamp')}｜{info['last_ts'][:19]}")


def resume(uuid: str, before: str = "") -> int:
    if not DB.is_file():
        print(f"[恢复·错误] 状态库不存在，无法恢复。")
        return 2
    con = sqlite3.connect(DB)
    sql = "select method_name, timestamp, state_json from flow_states where flow_uuid=?"
    args: list = [uuid]
    if before:
        sql += " and timestamp < ?"
        args.append(before)
    rows = con.execute(sql + " order by rowid", args).fetchall()
    con.close()
    if not rows:  # 坑 6：显式报错，绝不静默回退
        print(f"[恢复·错误] 未找到运行 {uuid}{'（时间窗 ' + before + ' 内）' if before else ''} 的快照。"
              f"先 --list 核对 uuid 与时间窗。")
        return 2
    state = json.loads(rows[-1][2])
    stages = state.get("stage_status", {})
    print(f"[恢复] 快照 {rows[-1][1][:19]}（{rows[-1][0]}）｜STUB={wf.STUB}｜"
          f"已完成 {sum(1 for s in ALL_STAGES if stages.get(s) == 'done')}/{len(ALL_STAGES)}")

    flow = wf.PaperFlow()
    flow._state = wf.ArisPaperState.model_validate(state)

    def _pending(name: str) -> bool:
        return flow.state.stage_status.get(name) != "done"

    # 前段线性链
    for m in ("load_inputs", "paper_plan", "negotiate_contract", "write_sections", "review_r1"):
        if _pending(m):
            print(f"[恢复] 执行 {m}")
            getattr(flow, m)()
    # R1 分支重放（路由结果由状态字段判定，不重跑 LLM）
    if not flow.state.review_passed and _pending("revise_paper"):
        print("[恢复] 执行 revise_paper（R1 未达标分支）")
        flow.revise_paper()
    if flow.state.stage_status.get("revise_paper") == "done" and _pending("review_r2"):
        print("[恢复] 执行 review_r2")
        flow.review_r2()
    # 终审链
    for m in ("kill_argument", "claim_audit", "verify_gates", "finalize"):
        if _pending(m):
            print(f"[恢复] 执行 {m}")
            getattr(flow, m)()

    done_n = sum(1 for s in ALL_STAGES if flow.state.stage_status.get(s) == "done")
    print(f"[恢复] 完成：{done_n}/{len(ALL_STAGES)}｜overall={flow.state.overall or '未定'}"
          f"｜kill={flow.state.kill_verdict}｜audit findings={flow.state.audit_findings}")
    print(f"[恢复] 终态见 {wf.OUTPUT_DIR / 'RUN_STATE.json'}")
    return 0 if done_n == len(ALL_STAGES) else 1


def main() -> int:
    args = sys.argv[1:]
    if "--list" in args:
        list_runs()
        return 0
    if "--uuid" in args:
        uuid = args[args.index("--uuid") + 1]
        before = args[args.index("--before") + 1] if "--before" in args else ""
        return resume(uuid, before)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
