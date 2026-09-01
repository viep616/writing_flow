#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M2 验收单测 · 双条件停机 / fail-closed / 台账合成 / 后缀合成 / guardrail / 合并桥

零依赖自运行：& ..\\.venv\\Scripts\\python.exe tests\\test_m2_acceptance.py
兼容 pytest 收集（函数名 test_*，团队后续装 pytest 可直接跑）。
用例来源：M2 各阶段实测缺陷的回归固化（首跑 fail-open ×3、合并桥严格解析丢 findings、
R1 未转义内引号、审计散文前缀等，详见 docs/HANDOVER.md）。
"""

import json
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import archive  # noqa: E402
import ledger  # noqa: E402
import review_gate  # noqa: E402
import task_guardrails as tg  # noqa: E402
import verdict_map  # noqa: E402
import verify_gates  # noqa: E402


def _fake_out(text):
    class _Out:
        raw = text
    return _Out()


# ---------------------------------------------------------------- A. 双条件停机
def test_gate_double_condition():
    """score>=6 且 verdict∈{ready,almost} 同时成立才 PASSED；单高分不停车。"""
    assert review_gate.decide({"score": 6, "verdict": "almost"})["passed"] is True
    assert review_gate.decide({"score": 10, "verdict": "ready"})["passed"] is True
    assert review_gate.decide({"score": 6, "verdict": "not_ready"})["passed"] is False  # 单高分不停车
    assert review_gate.decide({"score": 5, "verdict": "ready"})["passed"] is False
    assert review_gate.decide({"score": "7", "verdict": "ready"})["passed"] is False  # 非数值分


# ---------------------------------------------------------------- B. 解析 fail-closed
def test_parse_variants():
    ok = review_gate.parse_text('{"score": 6, "verdict": "almost"}')
    assert not ok.get("parse_error") and ok["weaknesses"] == []  # 默认字段补齐
    fenced = review_gate.parse_text("```json\n" + json.dumps({"score": 7, "verdict": "ready"}) + "\n```")
    assert not fenced.get("parse_error")  # 围栏兼容
    prose_json = review_gate.parse_text("核对如下：全部一致。\n\n" + json.dumps({"score": 7, "verdict": "ready"}))
    assert not prose_json.get("parse_error")  # 散文+尾部 JSON 可提取（首跑审计实录形态）
    # 首跑 R1 实录形态：字符串内嵌未转义双引号 → 必须判解析失败（fail-closed）
    bad = review_gate.parse_text('{"score": 6, "verdict": "almost", "weaknesses": [{"desc": "标注为"吸附能""}]}')
    assert bad.get("parse_error") is True
    assert review_gate.parse_text('{"score": 6}') .get("parse_error") is True  # 缺 verdict
    with tempfile.TemporaryDirectory() as d:
        assert review_gate.parse_file(Path(d) / "不存在.txt").get("parse_error") is True  # 缺文件


def test_uphold_list_filter():
    parsed = {"weaknesses": [
        {"id": "w1", "severity": "critical", "desc": "A"},
        {"id": "w2", "severity": "major", "desc": "B"},
        {"id": "w3", "severity": "minor", "desc": "C"},
    ]}
    with tempfile.TemporaryDirectory() as d:
        upheld = review_gate.uphold_list(parsed, Path(d))
        assert [u["id"] for u in upheld] == ["w1", "w2"]  # 规范语义：仅 critical+major（旧桩曾误含 minor）
        assert (Path(d) / "评审_R1成立清单.md").is_file() and (Path(d) / "评审_R1成立清单.json").is_file()


# ---------------------------------------------------------------- C. verdict 计数表
def test_verdict_map():
    assert verdict_map.map_atoms([]) == ("NOT_APPLICABLE", 0, 0)
    crit = [{"disposition": "still_unresolved", "severity": "critical"}]
    assert verdict_map.map_atoms(crit)[0] == "FAIL"
    major = [{"disposition": "still_unresolved", "severity": "major"}]
    assert verdict_map.map_atoms(major)[0] == "WARN"
    partial_heavy = [{"disposition": "partially_answered", "severity": "major"}]
    assert verdict_map.map_atoms(partial_heavy)[0] == "WARN"
    partial_minor = [{"disposition": "partially_answered", "severity": "minor"}]
    assert verdict_map.map_atoms(partial_minor)[0] == "PASS"
    answered = [{"disposition": "answered_by_current_text", "severity": "critical"}]
    assert verdict_map.map_atoms(answered)[0] == "PASS"  # 已回应的 critical 不阻断


# ---------------------------------------------------------------- D. 台账合成
def test_ledger_build_and_save():
    r1 = [{"id": "w1", "desc": "x", "severity": "critical"}, {"id": "w2", "desc": "y", "severity": "major"}]
    checks = [{"id": "w1", "status": "addressed"}, {"id": "w2", "status": "upheld_again"}]
    entries, open_n, disappear = ledger.build(r1, checks)
    assert open_n == 1 and disappear == 0
    assert entries[0]["resolved"] is True and entries[1]["resolved"] is False
    _, open2, disp2 = ledger.build(r1, [{"id": "w1", "status": "addressed"}])  # w2 无记录
    assert open2 == 1 and disp2 == 1  # 删句绕过：无核验记录即计入绕过
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "台账.jsonl"
        ledger.build_and_save(Path(d) / "无此清单.json", checks, p)  # 清单缺失 → 空台账不崩
        assert p.exists()
        ledger.build_and_save(Path(d) / "无此清单.json", checks, p)  # append-only：文件行数增长
        assert len(p.read_text(encoding="utf-8").strip().splitlines()) == 0  # 空清单 → 0 行


# ---------------------------------------------------------------- E. 投稿门（fail-open 回归 ×3 + 基线）
def _gate_fixture(tmp: str, kill_verdict="PASS", kill_atoms=None, audit_findings=0,
                  audit_verdict="PASS", audit_parse_error=False, fresh=True, provisional=False):
    out = Path(tmp)
    import hashlib

    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]

    draft, data = out / "论文_初稿.md", out / "data.md"
    draft.write_text("# 标题\n正文", encoding="utf-8")
    data.write_text("| 吸附能 | -1.85 | eV |", encoding="utf-8")
    for name in verify_gates.REQUIRED_ARTIFACTS:
        (out / name).write_text("{}", encoding="utf-8")  # 齐全性占位
    (out / "致命一击.json").write_text(json.dumps({"atoms": kill_atoms or [], "verdict_mapped": kill_verdict}, ensure_ascii=False), encoding="utf-8")
    meta = {"draft_sha256": sha(draft) if fresh else "过期指纹", "data_sha256": sha(data)}
    (out / "数值_复核.json").write_text(json.dumps(
        {"findings": list(range(audit_findings)), "verdict": audit_verdict, "_meta": meta}, ensure_ascii=False), encoding="utf-8")
    snap = {
        "kill_verdict": kill_verdict, "kill_unresolved": 0, "audit_findings": audit_findings,
        "audit_parse_error": audit_parse_error, "ledger_open": 0, "provisional": provisional,
        "human_flags": [], "data_path": str(data),
    }
    return out, snap


def test_gate_all_green_accepted():
    with tempfile.TemporaryDirectory() as d:
        _, overall = verify_gates.run(*_gate_fixture(d))
        assert overall == "accepted"


def test_gate_kill_fail_blocks():  # 首跑缺陷①：kill FAIL 曾直通 accepted
    with tempfile.TemporaryDirectory() as d:
        _, overall = verify_gates.run(*_gate_fixture(d, kill_verdict="FAIL"))
        assert overall == "no"


def test_gate_audit_fail_blocks():  # 第三处 fail-open：审计 FAIL 而 kill PASS 曾可 accepted
    with tempfile.TemporaryDirectory() as d:
        _, overall = verify_gates.run(*_gate_fixture(d, audit_verdict="FAIL", audit_findings=2))
        assert overall == "no"


def test_gate_audit_parse_error_blocks():  # 首跑缺陷②：parse_error 未入 snap 曾绕过一致性门
    with tempfile.TemporaryDirectory() as d:
        results, overall = verify_gates.run(*_gate_fixture(d, audit_parse_error=True))
        assert overall == "no" and results["一致性"].startswith("fail")


def test_gate_kill_blocked_or_empty_blocks():  # kill 侧 fail-closed：BLOCKED/空 verdict 不放行
    with tempfile.TemporaryDirectory() as d:
        assert verify_gates.run(*_gate_fixture(d, kill_verdict="BLOCKED"))[1] == "no"
        assert verify_gates.run(*_gate_fixture(d, kill_verdict=""))[1] == "no"


def test_gate_warn_provisional_and_stale():
    with tempfile.TemporaryDirectory() as d:
        assert verify_gates.run(*_gate_fixture(d, kill_verdict="WARN"))[1] == "provisional"
        assert verify_gates.run(*_gate_fixture(d, fresh=False))[1] == "no"  # 指纹不符＝STALE


# ---------------------------------------------------------------- F. 后缀合成
def test_suffix_compose_order():
    assert archive.compose_suffix({}) == ""
    snap = {
        "contract_status": "contested",
        "review": {"passed": False},
        "kill": {"verdict": "FAIL"},
        "audit": {"findings": 2},
        "overall": "no",
        "human_flags": ["交接不完整"],
    }
    assert archive.compose_suffix(snap) == "_契约争议_评审未达标_致命一击未过_数值存疑_未通过门_交接不完整"
    assert archive.compose_suffix({"audit": {"parse_error": True}}) == "_数值存疑"  # 解析失败也算数值存疑


# ---------------------------------------------------------------- G. guardrail
def test_guardrails():
    ok, _ = tg.review_json(_fake_out('{"score": 6, "verdict": "almost", "weaknesses": [], "uphold_check": []}'))
    assert ok is True
    ok, fb = tg.review_json(_fake_out('{"score": 6, "verdict": "almost", "weaknesses": [{"desc": "标"吸附能""}]}'))
    assert ok is False and ("转义" in fb or "引号" in fb)  # 内引号必须拦截且反馈含修正指引
    ok, _ = tg.audit_json(_fake_out("核对完毕，全部一致。"))  # 纯散文
    assert ok is False
    ok, _ = tg.audit_json(_fake_out("过程……\n" + json.dumps({"findings": [], "verdict": "PASS"})))
    assert ok is True  # 散文+尾部 JSON 放行（提取器负责）
    ok, _ = tg.arbiter_json(_fake_out('{"atoms": []}'))
    assert ok is False  # 空 atoms 拦截


# ---------------------------------------------------------------- H. 合并桥（严格解析丢 findings 回归）
def test_merge_bridges():
    sys.path.insert(0, str(REPO / "src"))
    import writing_flow.main as wf

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        real_out, real_draft = wf.OUTPUT_DIR, wf.DRAFT_FILE
        wf.OUTPUT_DIR, wf.DRAFT_FILE = tmp, tmp / "论文_初稿.md"
        try:
            wf.DRAFT_FILE.write_text("# 稿", encoding="utf-8")
            data_file = tmp / "data.md"
            data_file.write_text("| v | 1.0 |", encoding="utf-8")
            # 审计：散文前缀 + 尾部 JSON（首跑实录形态）→ 必须恢复 findings 而非 PARSE_ERROR
            (tmp / "数值_复核_原文.json").write_text(
                "逐项核对：一致。\n" + json.dumps({"findings": [{"type": "数值膨胀", "claim": "x", "evidence": "y", "detail": "z"}], "verdict": "FAIL"}, ensure_ascii=False),
                encoding="utf-8",
            )
            assert wf._merge_audit_artifacts(data_file) is False
            merged = json.loads((tmp / "数值_复核.json").read_text(encoding="utf-8"))
            assert len(merged["findings"]) == 1 and merged["verdict"] == "FAIL"
            assert merged["_meta"]["draft_sha256"] and merged["_meta"]["data_sha256"]  # 双指纹在位
            # 审计：真垃圾 → fail-closed
            (tmp / "数值_复核_原文.json").write_text("我说完了，没有 JSON。", encoding="utf-8")
            assert wf._merge_audit_artifacts(data_file) is True
            # kill：合法 atoms / 垃圾 / 缺文件
            (tmp / "致命_攻击段.md").write_text("攻击段", encoding="utf-8")
            (tmp / "致命_原子点.json").write_text(json.dumps({"atoms": [{"id": "a1", "disposition": "still_unresolved", "severity": "major"}]}, ensure_ascii=False), encoding="utf-8")
            assert wf._merge_kill_artifacts() is False
            (tmp / "致命_原子点.json").write_text("垃圾文本", encoding="utf-8")
            assert wf._merge_kill_artifacts() is True
            (tmp / "致命_原子点.json").unlink()
            assert wf._merge_kill_artifacts() is True
        finally:
            wf.OUTPUT_DIR, wf.DRAFT_FILE = real_out, real_draft


# ---------------------------------------------------------------- 自运行入口
if __name__ == "__main__":
    _tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    _passed, _failed = 0, []
    for _name, _fn in _tests:
        try:
            _fn()
            _passed += 1
            print(f"[PASS] {_name}")
        except Exception as _e:  # noqa: BLE001
            _failed.append(_name)
            print(f"[FAIL] {_name}: {_e!r}")
    print("=" * 56)
    print(f"M2 验收单测：{_passed}/{len(_tests)} 通过" + ("" if not _failed else f"｜失败：{_failed}"))
    sys.exit(0 if not _failed else 1)
