#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""qe_extract · QE pwo → 白名单数据表（确定性提取，零 LLM，数值代码裁决）

上游（前部队友）交付 Quantum ESPRESSO 原始计算输出（见 HANDOVER「QE 材料勘察」）。
本工具从每个体系的 pwo 提取终态能量，生成白名单格式的数据表：
  - 终态能量 = 文件中最后一个 "!" 开头的 total energy 行（多段弛豫取终段）
  - 完成性 = 尾部 JOB DONE 标记；未完成体系标 not_converged，不入白名单（fail-closed）
  - 同目录多个 pwo（重跑副本）→ 取 mtime 最新且含 JOB DONE 者；能量不一致记 duplicate_mismatch
  - E_ads 绝对值 = E(复合物)−E(基底)−E(气体)：归档中无基底/孤立气体参考计算 → DATA_NEEDED（不猜）
  - 位点稳定性 ΔE = 同管型×同材料×同气体内各位点能量差（纯代码可推导，入白名单）
  - 分析素材（§5）：位点排序与位次（并列注明）、最优位点频次、组数/占比、收敛性汇总
    —— 全部由代码从 §1 终态能量与 convergence_results.csv 生成，写作/审计直接引用，禁止手算
单位：主值保留 Ry（原始口径），换算 eV 用上游 README 同口径 13.6057。

用法：
    python qe_extract.py <体系根目录> <输出md路径> [--json 路径]
    （可作为模块导入：extract() / write_whitelist_table()）
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

RY_TO_EV = 13.6057  # 与上游 README 口径一致（1 Ry = 13.6057 eV）

_FINAL_E_RE = re.compile(r"^!\s+total energy\s*=\s*(-?\d+\.?\d*)\s*Ry", re.MULTILINE)
_SYS_RE = re.compile(
    r"^adsorption_(?P<chirality>\d,\d_(?:armchair|zigzag))_"
    r"(?P<material>PtPd|PtN|Pt|pure)_"
    r"(?P<gas>SOF2|SO2F2|SO2|SF6|H2S)_"
    r"(?P<site>top|bridge|hollow)_"
    r"(?P<idx>\d{3})$"
)
_RANK_LABELS = ["最优", "次优", "第三优", "第四优"]
_TIE_EV_TOL = 1e-4  # 位次并列阈值：组内能量差小于该值（eV）视为简并/并列


def parse_pwo(path: Path) -> dict:
    """流式解析单个 pwo → 终态能量与完成标记。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    hits = _FINAL_E_RE.findall(text)
    return {
        "file": Path(path).name,
        "final_energy_ry": float(hits[-1]) if hits else None,
        "n_scf_stages": len(hits),
        "job_done": "JOB DONE" in text,
        "terminated_at": _terminated_at(text),
    }


def _terminated_at(text: str) -> str:
    m = re.search(r"terminated on:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def parse_system_name(name: str) -> dict:
    """目录名 → 结构化元数据；不匹配命名规范返回 malformed=True（fail-closed 不猜）。"""
    m = _SYS_RE.match(name)
    if not m:
        return {"system": name, "malformed": True}
    d = m.groupdict()
    d["idx"] = int(d["idx"])
    d["system"] = name
    d["malformed"] = False
    return d


def _pick_pwo(dir_path: Path) -> tuple[Path, list[Path], bool]:
    """同目录多 pwo：取 mtime 最新且 JOB DONE 者；能量一致性由调用方复核。"""
    pwos = sorted(dir_path.glob("*.pwo"), key=lambda p: p.stat().st_mtime)
    candidates = [p for p in pwos if "JOB DONE" in p.read_text(encoding="utf-8", errors="replace")[-4096:]]
    pool = candidates or pwos
    return pool[-1], pwos, bool(candidates)


def _read_convergence_csv(root: Path) -> list[dict]:
    """读取 convergence_results.csv（有能量值的行），供 §5.5 收敛性汇总。
    查找顺序与 prepare_inputs 的 aux 规则一致：体系根目录 → 其父目录。"""
    csv_path = next(
        (p for p in (Path(root) / "convergence_results.csv",
                     Path(root).parent / "convergence_results.csv") if p.is_file()),
        None,
    )
    if csv_path is None:
        return []
    rows = []
    try:
        with csv_path.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("total_energy_Ry"):
                    rows.append({
                        "system": r.get("system", "").strip(),
                        "ecutwfc": r.get("ecutwfc", "").strip(),
                        "kgrid": r.get("kgrid", "").strip(),
                        "energy_ry": r["total_energy_Ry"].strip(),
                        "status": r.get("converged", "").strip(),
                    })
    except (OSError, csv.Error):
        return []
    return rows


def extract(root: Path) -> dict:
    """遍历体系目录 → {rows, malformed, not_converged, duplicates, flags, 分析素材}。"""
    root = Path(root)
    rows, malformed, not_converged, dup_mismatch = [], [], [], []
    for dir_path in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = parse_system_name(dir_path.name)
        if meta["malformed"]:
            malformed.append(dir_path.name)
            continue
        pwo, all_pwos, has_done = _pick_pwo(dir_path)
        if not pwo.exists() or not has_done:
            not_converged.append(dir_path.name)
            continue
        info = parse_pwo(pwo)
        if info["final_energy_ry"] is None:
            not_converged.append(dir_path.name)
            continue
        row = {**{k: meta[k] for k in ("chirality", "material", "gas", "site", "idx", "system")},
               **info,
               "final_energy_ev": round(info["final_energy_ry"] * RY_TO_EV, 4)}
        # 重复副本能量一致性（确定性规则：不一致记 flag，不擅自取舍）
        if len(all_pwos) > 1:
            others = [p for p in all_pwos if p != pwo]
            energies = [parse_pwo(p)["final_energy_ry"] for p in others]
            if any(e != row["final_energy_ry"] for e in energies):
                dup_mismatch.append(dir_path.name)
                row["duplicate_mismatch"] = True
        rows.append(row)
    # 位点稳定性 ΔE（同 管型×材料×气体 组内相对最优位点，纯差值推导）
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["chirality"], r["material"], r["gas"]), []).append(r)
    deltas = []
    for key, members in sorted(groups.items()):
        best = min(members, key=lambda r: r["final_energy_ry"])
        for r in members:
            r["delta_to_best_ev"] = round((r["final_energy_ry"] - best["final_energy_ry"]) * RY_TO_EV, 4)
        deltas.append({
            "group": f"{key[0]}/{key[1]}/{key[2]}",
            "best_site": best["site"],
            "best_idx": best["idx"],
            "sites_ranked": [m["site"] for m in sorted(members, key=lambda r: r["final_energy_ry"])],
        })

    # ---- 分析素材：位点排序/位次（并列注明）、最优位点频次、组数占比、收敛性（纯代码） ----
    ranking: list[dict] = []
    best_freq: dict[tuple[str, str], dict[str, int]] = {}
    mat_best: dict[str, dict[str, int]] = {}
    for key, members in sorted(groups.items()):
        ordered = sorted(members, key=lambda r: (r["final_energy_ry"], r["site"]))
        # 位次按能量层级分组：组内能量差 < _TIE_EV_TOL 视为并列，同一层级共享位次标签
        levels: list[dict] = []
        for m in ordered:
            for lv in levels:
                if abs(lv["energy"] - m["final_energy_ry"]) * RY_TO_EV < _TIE_EV_TOL:
                    lv["members"].append(m)
                    break
            else:
                levels.append({"energy": m["final_energy_ry"], "members": [m]})
        for li, lv in enumerate(levels):
            label = _RANK_LABELS[li] if li < len(_RANK_LABELS) else f"第{li + 1}优"
            if len(lv["members"]) > 1:
                label += "（并列）"
            for m in lv["members"]:
                m["rank_label"] = label
        best_e = levels[0]["energy"]
        order_txt = [f"{m['site']}({m['rank_label']})" for m in ordered]
        ranking.append({
            "group": f"{key[0]}/{key[1]}/{key[2]}",
            "order": order_txt,
            "best_site": ordered[0]["site"],
            "best_system": ordered[0]["system"],
        })
        bf = best_freq.setdefault((key[1], key[2]), {})
        bf[ordered[0]["site"]] = bf.get(ordered[0]["site"], 0) + 1
        mb = mat_best.setdefault(key[1], {})
        mb[ordered[0]["site"]] = mb.get(ordered[0]["site"], 0) + 1

    best_freq_rows = [
        {"material": mat, "gas": gas, "site": site, "count": cnt}
        for (mat, gas), freq in sorted(best_freq.items())
        for site, cnt in sorted(freq.items())
    ]
    site_share_rows = []
    for mat, freq in sorted(mat_best.items()):
        total = sum(freq.values()) or 1
        site_share_rows.append({
            "material": mat,
            "top": round(freq.get("top", 0) / total * 100, 1),
            "bridge": round(freq.get("bridge", 0) / total * 100, 1),
            "hollow": round(freq.get("hollow", 0) / total * 100, 1),
        })
    n_groups_total = len(groups)
    n_groups_doped = sum(1 for k in groups if k[1] != "pure")
    convergence = _read_convergence_csv(root)

    return {
        "rows": rows, "site_deltas": deltas, "malformed": malformed,
        "not_converged": not_converged, "duplicate_mismatch": dup_mismatch,
        "ranking": ranking, "best_freq": best_freq_rows,
        "group_stats": {
            "n_groups_total": n_groups_total,
            "n_groups_doped": n_groups_doped,
            "n_groups_pure": n_groups_total - n_groups_doped,
        },
        "site_share": site_share_rows,
        "convergence": convergence,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "n_total": len(rows) + len(malformed) + len(not_converged),
    }


def write_whitelist_table(result: dict, out_md: Path, out_json: Path | None = None) -> Path:
    """生成白名单格式数据表（三列：量 | 值 | 单位——validate_report.build_whitelist 兼容结构）。"""
    lines = [
        "# QE 计算数据表（qe_extract 确定性提取，白名单源）",
        "",
        f"> 提取时间 {result['extracted_at']}｜体系 {len(result['rows'])}/{result['n_total']}"
        f"（未收敛 {len(result['not_converged'])}，命名不规范 {len(result['malformed'])}，副本能量不一致 {len(result['duplicate_mismatch'])}）",
        "> E_ads 绝对值缺基底/孤立气体参考计算 → DATA_NEEDED（待上游补充，禁止估算）",
        "> §5 分析素材由代码生成（排序/位次/频次/占比/收敛性），写作与审计直接引用，禁止手算或改标位次",
        "",
        "## 1. 体系终态能量（弛豫收敛值）",
        "",
        "| 体系 | 终态能量 | 单位 | 换算 |",
        "|------|---------|------|------|",
    ]
    for r in result["rows"]:
        lines.append(
            f"| {r['system']} | {r['final_energy_ry']:.8f} | Ry | {r['final_energy_ev']} eV |"
        )
    lines += ["", "## 2. 位点稳定性（组内相对最优，ΔE 为代码推导差值）", "",
              "| 组 | 最优位点 | 最优体系 | 位点排序（稳→不稳） |", "|----|---------|---------|---------------------|"]
    for d in result["site_deltas"]:
        lines.append(f"| {d['group']} | {d['best_site']} | {d['best_idx']:03d} | {' > '.join(d['sites_ranked'])} |")
    lines += ["", "## 3. 各体系相对最优位点差值", "",
              "| 体系 | ΔE(相对组内最优) | 单位 |", "|------|------------------|------|"]
    for r in result["rows"]:
        lines.append(f"| {r['system']} | {r['delta_to_best_ev']} | eV |")
    lines += ["", "## 4. 方法学自查", "",
              "| 项 | 状态 |", "|----|------|",
              "| E_ads 绝对值（基底/气体参考能量） | 未计算（DATA_NEEDED） |",
              "| 未收敛体系 | " + ("；".join(result["not_converged"]) or "无") + " |",
              "| 命名不规范 | " + ("；".join(result["malformed"]) or "无") + " |",
              "| 副本能量不一致 | " + ("；".join(result["duplicate_mismatch"]) or "无") + " |",
              "| 单位换算 | 1 Ry = 13.6057 eV（上游 README 口径） |", "",
              "## 5. 分析素材（代码生成，禁止手算/改写）", "",
              "> 本节由 qe_extract 从 §1 终态能量与 convergence_results.csv 确定性生成；"
              "论文中的位点排序、位次、频次、占比与收敛性数值必须直接引用本节，禁止自行统计、重新计算或改标位次。", "",
              "### 5.1 组内位点排序（稳→不稳，并列注明）", "",
              "| 组 | 排序 | 最优位点 | 最优体系 |", "|----|------|---------|---------|"]
    for r in result.get("ranking", []):
        lines.append(f"| {r['group']} | {' > '.join(r['order'])} | {r['best_site']} | {r['best_system']} |")
    lines += ["", "### 5.2 组内能差（ΔE 相对组内最优）", "",
              "| 体系 | ΔE | 单位 | 位次 |", "|------|-----|------|------|"]
    for r in result["rows"]:
        lines.append(f"| {r['system']} | {r['delta_to_best_ev']} | eV | {r.get('rank_label', '')} |")
    lines += ["", "### 5.3 最优位点频次（材料×气体，跨手性合计）", "",
              "| 掺杂 | 气体 | 最优位点 | 出现次数 | 单位 |", "|------|------|---------|---------|------|"]
    for r in result.get("best_freq", []):
        lines.append(f"| {r['material']} | {r['gas']} | {r['site']} | {r['count']} | 次 |")
    gs = result.get("group_stats", {})
    lines += ["", "### 5.4 组数与占比", "",
              "| 类别 | 数值 | 单位 |", "|------|------|------|",
              f"| 体系总数 | {result['n_total']} | 个 |",
              f"| 入白名单体系数 | {len(result['rows'])} | 个 |",
              f"| 组总数（管型×掺杂×气体） | {gs.get('n_groups_total', 0)} | 组 |",
              f"| 掺杂体系组数 | {gs.get('n_groups_doped', 0)} | 组 |",
              f"| 纯体系组数 | {gs.get('n_groups_pure', 0)} | 组 |", "",
              "| 掺杂 | top 占比 | bridge 占比 | hollow 占比 | 单位 |",
              "|------|-----------|-------------|-------------|------|"]
    for r in result.get("site_share", []):
        lines.append(f"| {r['material']} | {r['top']} | {r['bridge']} | {r['hollow']} | % |")
    lines += ["", "### 5.5 收敛性测试汇总（来自 convergence_results.csv）", "",
              "| 体系 | 参数 | 总能量 | 状态 |", "|------|------|--------|------|"]
    for r in result.get("convergence", []):
        lines.append(f"| {r['system']} | ecut{r['ecutwfc']}/k{r['kgrid']} | {r['energy_ry']} Ry | {r['status']} |")
    lines.append("")
    out_md = Path(out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_md


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    root, out_md = Path(sys.argv[1]), Path(sys.argv[2])
    out_json = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
    result = extract(root)
    table = write_whitelist_table(result, out_md, out_json)
    print(f"[qe_extract] 体系 {len(result['rows'])}/{result['n_total']}｜未收敛 {len(result['not_converged'])}"
          f"｜不规范 {len(result['malformed'])}｜副本不一致 {len(result['duplicate_mismatch'])}")
    print(f"[qe_extract] 白名单表 → {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
