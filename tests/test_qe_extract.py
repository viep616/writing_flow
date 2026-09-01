#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""qe_extract 单测 · 确定性提取规则的分支覆盖（零依赖自运行，兼容 pytest）。"""

import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import qe_extract  # noqa: E402


def _mini_pwo(energies, job_done=True, terminated=" 1Jan2026"):
    """构造多段弛豫的最小 pwo 样本：每个能量一个 '!' 终态行。"""
    body = ""
    for e in energies:
        body += f"     total energy              =   {e - 0.05:.8f} Ry\n"
        body += f"!    total energy              =   {e:.8f} Ry\n"
        body += "     convergence has been achieved in   9 iterations\n"
    body += f"   This run was terminated on:  {terminated}\n"
    if job_done:
        body += "=-------------------------------------------------------------------=\n   JOB DONE.\n"
    return body


def test_parse_pwo_last_bang_wins():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "espresso.pwo"
        p.write_text(_mini_pwo([-2140.0, -2140.36944178]), encoding="utf-8")
        info = qe_extract.parse_pwo(p)
        assert info["final_energy_ry"] == -2140.36944178  # 多段弛豫取最后一个 ! 行
        assert info["n_scf_stages"] == 2 and info["job_done"] is True
        assert round(info["final_energy_ry"] * qe_extract.RY_TO_EV, 4) == round(-2140.36944178 * 13.6057, 4)


def test_parse_pwo_no_done_no_energy():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "espresso.pwo"
        p.write_text(_mini_pwo([], job_done=False), encoding="utf-8")
        info = qe_extract.parse_pwo(p)
        assert info["final_energy_ry"] is None and info["job_done"] is False  # fail-closed


def test_parse_system_name():
    ok = qe_extract.parse_system_name("adsorption_6,6_armchair_PtN_SO2F2_bridge_069")
    assert not ok["malformed"] and ok["material"] == "PtN" and ok["gas"] == "SO2F2" and ok["idx"] == 69
    ok2 = qe_extract.parse_system_name("adsorption_8,0_zigzag_pure_H2S_top_014")
    assert ok2["material"] == "pure" and ok2["chirality"] == "8,0_zigzag"
    for bad in ("relax_Pt_H2S_top_1", "adsorption_6,6_armchair_Pt_Xe_top_001", "adsorption_6,6_armchair_Pt_SO2_center_001"):
        assert qe_extract.parse_system_name(bad)["malformed"] is True  # 命名不符 → 不猜


def test_extract_tree_rules():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # 正常体系 ×3（同组不同位点，用于 ΔE 推导）
        for name, e in (("adsorption_6,6_armchair_Pt_SOF2_top_035", -2140.0),
                        ("adsorption_6,6_armchair_Pt_SOF2_bridge_036", -2139.5),
                        ("adsorption_6,6_armchair_Pt_SOF2_hollow_037", -2139.0)):
            (root / name).mkdir()
            (root / name / "espresso.pwo").write_text(_mini_pwo([e]), encoding="utf-8")
        # 未收敛（无 JOB DONE）→ not_converged，不入白名单
        (root / "adsorption_6,6_armchair_Pt_SF6_top_041").mkdir()
        (root / "adsorption_6,6_armchair_Pt_SF6_top_041" / "espresso.pwo").write_text(_mini_pwo([-100.0], job_done=False), encoding="utf-8")
        # 命名不规范 → malformed
        (root / "随便一个目录").mkdir()
        # 重复副本：能量一致 → 不报 mismatch
        dup = root / "adsorption_6,6_armchair_Pt_SO2_top_032"
        dup.mkdir()
        (dup / "espresso.pwo").write_text(_mini_pwo([-2000.0]), encoding="utf-8")
        (dup / "espresso (1).pwo").write_text(_mini_pwo([-2000.0]), encoding="utf-8")
        # 重复副本：能量不一致 → 记 mismatch
        dup2 = root / "adsorption_6,6_armchair_Pt_SO2_hollow_034"
        dup2.mkdir()
        (dup2 / "espresso.pwo").write_text(_mini_pwo([-2001.0]), encoding="utf-8")
        (dup2 / "espresso (1).pwo").write_text(_mini_pwo([-2002.0]), encoding="utf-8")

        result = qe_extract.extract(root)
        assert result["n_total"] == 7
        assert len(result["rows"]) == 5  # 3+2（SO2 两目录均收敛入表）
        assert result["not_converged"] == ["adsorption_6,6_armchair_Pt_SF6_top_041"]
        assert len(result["malformed"]) == 1
        assert result["duplicate_mismatch"] == ["adsorption_6,6_armchair_Pt_SO2_hollow_034"]  # 一致的副本不报
        # ΔE 推导：SOF2 组内 top(-2140.0) 最稳，hollow 相对差 = 1.0 Ry × 13.6057
        top = next(r for r in result["rows"] if r["site"] == "top" and r["gas"] == "SOF2")
        hollow = next(r for r in result["rows"] if r["site"] == "hollow" and r["gas"] == "SOF2")
        assert top["delta_to_best_ev"] == 0.0 and hollow["delta_to_best_ev"] == round(1.0 * 13.6057, 4)
        so = next(g for g in result["site_deltas"] if g["group"].endswith("SOF2"))
        assert so["best_site"] == "top"


def test_whitelist_table_content():
    with tempfile.TemporaryDirectory() as d:
        root, out = Path(d) / "sys", Path(d) / "表.md"
        root.mkdir()
        (root / "adsorption_8,0_zigzag_PtN_H2S_top_119").mkdir()
        (root / "adsorption_8,0_zigzag_PtN_H2S_top_119" / "espresso.pwo").write_text(
            _mini_pwo([-3000.12345678]), encoding="utf-8")
        result = qe_extract.extract(root)
        qe_extract.write_whitelist_table(result, out, Path(d) / "表.json")
        text = out.read_text(encoding="utf-8")
        assert "-3000.12345678" in text and "Ry" in text          # 原始口径主值
        assert "DATA_NEEDED" in text                              # E_ads 缺参考能量 → 显式声明
        assert (Path(d) / "表.json").is_file()
        # 白名单兼容结构：表格三列（| 体系 | 值 | 单位 |）
        assert "| adsorption_8,0_zigzag_PtN_H2S_top_119 | -3000.12345678 | Ry |" in text


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
    print(f"qe_extract 单测：{_passed}/{len(_tests)} 通过" + ("" if not _failed else f"｜失败：{_failed}"))
    sys.exit(0 if not _failed else 1)
