#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""validate_report QE 适配单测 · 格内单位归类 / Ry↔eV 互推 / 单位缺失报警 / 端到端（零依赖自运行）。"""

import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import validate_report as vr  # noqa: E402

_QE_TABLE = """# QE 计算数据表

## 1. 体系终态能量（弛豫收敛值）

| 体系 | 终态能量 | 单位 | 换算 |
|------|---------|------|------|
| adsorption_6,6_armchair_Pt_SOF2_top_035 | -2140.04939365 | Ry | -29117.1965 eV |
| adsorption_6,6_armchair_Pt_SOF2_bridge_036 | -2139.50000000 | Ry | -29110.5513 eV |

## 3. 各体系相对最优位点差值

| 体系 | ΔE(相对组内最优) | 单位 |
|------|------------------|------|
| adsorption_6,6_armchair_Pt_SOF2_top_035 | 0.0 | eV |
| adsorption_6,6_armchair_Pt_SOF2_bridge_036 | 6.6451 | eV |
"""

_VASP_TABLE = """| 物理量 | 本项目材料 | 对比材料 | 单位 |
|------|------|------|------|
| 吸附距离（SOF₂） | 1.68（O–H···F 氢键） | 3.21（最近原子间距） | Å |
"""


def test_whitelist_incell_unit_bucket():
    wl = vr.build_whitelist(_QE_TABLE)
    assert -2140.049394 in wl["Ry"] and -2139.5 in wl["Ry"]          # 能量按单位列入 Ry 桶
    assert -29117.1965 in wl["eV"] and 6.6451 in wl["eV"]            # 换算/ΔE 归 eV 桶（错桶修复）
    assert not any(abs(v + 29117.1965) < 0.001 for v in wl["Ry"])    # eV 换算值不再混入 Ry 桶


def test_vasp_table_regression():
    wl = vr.build_whitelist(_VASP_TABLE)
    assert wl["Å"] == {1.68, 3.21}  # 括号注释单元格仍按单位列归类（原行为不变）


def _validate_with(data_text: str, report_text: str):
    with tempfile.TemporaryDirectory() as d:
        data, report = Path(d) / "数据.md", Path(d) / "报告.md"
        data.write_text(data_text, encoding="utf-8")
        report.write_text(report_text, encoding="utf-8")
        return vr.validate(report, data)


_SECTIONS = "# 标题\n## 摘要\nx\n## 引言\nx\n## 计算方法\nx\n## 结果与讨论\n{body}\n## 结论\nx\n"


def test_cross_unit_derivation_and_fabrication():
    body = "最优体系能量为 -2140.04939365 Ry（即 -29117.20 eV）；对照体系 -2139.50 Ry。\n"
    ok, problems = _validate_with(_QE_TABLE, _SECTIONS.format(body=body))
    assert ok, problems  # 精确 Ry + 换算 eV（互推容差内）均放行
    ok2, problems2 = _validate_with(_QE_TABLE, _SECTIONS.format(body="编造值 -12345.6 eV 应被拦截。\n"))
    assert not ok2 and any("白名单外" in p for p in problems2)      # 编造 eV 必须被抓（fail-open 已堵）


def test_unknown_unit_flagged():
    ok, problems = _validate_with(_VASP_TABLE, _SECTIONS.format(body="无据引用 0.5 Ry 应报警。\n"))
    assert not ok and any("单位缺失" in p for p in problems)        # 白名单全无的单位 → 报警


def test_qe_end_to_end_green():
    body = "Pt/SOF₂ 组 top 位点最稳（-2140.04939365 Ry），bridge 相对差 6.6451 eV。\n"
    ok, problems = _validate_with(_QE_TABLE, _SECTIONS.format(body=body))
    assert ok, problems


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
    print(f"validate_report QE 适配单测：{_passed}/{len(_tests)} 通过" + ("" if not _failed else f"｜失败：{_failed}"))
    sys.exit(0 if not _failed else 1)
