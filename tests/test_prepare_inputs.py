#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""prepare_inputs 判道单测 · raw_calc 新分支 + 原有三分支回归（零依赖自运行，兼容 pytest）。"""

import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import prepare_inputs  # noqa: E402

_PWO = (
    "     total energy              =   -2140.00000000 Ry\n"
    "!    total energy              =   -2140.04939365 Ry\n"
    "     convergence has been achieved in  16 iterations\n"
    "   This run was terminated on:  1Jan2026\n"
    "=-------------------------------------------------------------------=\n   JOB DONE.\n"
)


def _mk_archive(handoff: Path, systems=(("adsorption_6,6_armchair_Pt_SOF2_top_035",),
                                        ("adsorption_6,6_armchair_Pt_SOF2_bridge_036",))):
    root = handoff / "QE归档"
    root.mkdir(parents=True, exist_ok=True)
    for (name,) in systems:
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "espresso.pwo").write_text(_PWO, encoding="utf-8")
    (root / "README.md").write_text("# QE 归档说明\n参数：ecutwfc=30 Ry\n", encoding="utf-8")
    (root / "convergence_results.csv").write_text("system,ecutwfc,kgrid,total_energy_Ry,converged\n", encoding="utf-8")
    return root


def test_raw_calc_handoff():
    with tempfile.TemporaryDirectory() as d:
        data, out = Path(d), Path(d) / "out"
        handoff = data / "upstream_handoff"
        root = _mk_archive(handoff)
        (handoff / "HANDOFF.md").write_text(
            "# HANDOFF\n- state.id: qe-run-001\n- generated_at: 2026-09-01T18:00:00\n"
            "- 课题锚定：Pt 系掺杂碳纳米管对 SF₆ 分解气体的吸附与传感机制\n- artifacts: QE归档\n",
            encoding="utf-8",
        )
        manifest = prepare_inputs.run(data, out)
        assert manifest["mode"] == "standalone"                    # 不再误判 refine（核心回归点）
        assert manifest["source_ref"] == "qe-run-001"              # state.id 溯源
        assert manifest["topic_anchor"].startswith("Pt 系掺杂")    # 课题锚定透传（M3-④）
        assert manifest["handoff_present"] is True
        roles = {f["role"]: Path(f["path"]) for f in manifest["files"]}
        assert roles["data"].name == "QE_数据表.md" and roles["data"].is_file()   # 白名单表已生成
        assert "-2140.04939365" in roles["data"].read_text(encoding="utf-8")     # 能量值入表
        assert roles["readme"].name == "README.md" and roles["aux"].name.endswith(".csv")
        assert manifest["raw_calc_root"] == str(root)            # 原始目录留档溯源，不入素材清单（M3-④）
        assert prepare_inputs.current_data_file(out) == roles["data"]            # 审计白名单源指向生成表


def test_raw_calc_without_handoff_md():
    with tempfile.TemporaryDirectory() as d:
        data, out = Path(d), Path(d) / "out"
        root = _mk_archive(data / "upstream_handoff")
        manifest = prepare_inputs.run(data, out)
        assert manifest["mode"] == "standalone"
        assert manifest["source_ref"] == root.name and manifest["handoff_present"] is False  # 降级仍可跑


def test_narrative_handoff_regression():
    with tempfile.TemporaryDirectory() as d:
        data, out = Path(d), Path(d) / "out"
        handoff = data / "upstream_handoff"
        handoff.mkdir()
        (handoff / "研究报告_narrative.md").write_text("# 叙事", encoding="utf-8")
        manifest = prepare_inputs.run(data, out)
        assert manifest["mode"] == "standalone" and manifest["files"][0]["role"] == "narrative"


def test_independent_regression():
    with tempfile.TemporaryDirectory() as d:
        data, out = Path(d), Path(d) / "out"
        (data / "NARRATIVE_REPORT.md").write_text("# 叙事", encoding="utf-8")
        (data / "vasp_results.md").write_text("# 数据", encoding="utf-8")
        manifest = prepare_inputs.run(data, out)
        assert manifest["mode"] == "standalone"
        assert {f["role"] for f in manifest["files"]} == {"narrative", "data"}


def test_draft_refine_regression():
    with tempfile.TemporaryDirectory() as d:
        data, out = Path(d), Path(d) / "out"
        (data / "历史终稿.md").write_text("# 初稿", encoding="utf-8")
        manifest = prepare_inputs.run(data, out)
        assert manifest["mode"] == "refine" and manifest["files"][0]["role"] == "draft"


def test_topic_anchor_parse():
    with tempfile.TemporaryDirectory() as d:
        h = Path(d) / "HANDOFF.md"
        h.write_text("# H\n- state.id: x1\n- 课题锚定：Pt 掺杂 CNT 吸附机制\n", encoding="utf-8")
        assert prepare_inputs.topic_anchor_from_handoff(h) == "Pt 掺杂 CNT 吸附机制"
        assert prepare_inputs.topic_anchor_from_handoff(Path(d) / "无.md") == ""  # 缺文件空锚定


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
    print(f"prepare_inputs 判道单测：{_passed}/{len(_tests)} 通过" + ("" if not _failed else f"｜失败：{_failed}"))
    sys.exit(0 if not _failed else 1)
