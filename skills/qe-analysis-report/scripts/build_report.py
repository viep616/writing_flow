r"""从 parse_qe.py 的结构化数据生成中文数据分析报告（Markdown + PDF）。

用法：
    python build_report.py <解析输出目录> -o <报告.md> [--pdf 报告.pdf]
    python build_report.py <解析输出目录> -o 报告.md --mode single --system adsorption_6,6_armchair_pure_H2S_top_014

依赖（本项目默认环境）：pandoc + xelatex + SimHei；matplotlib。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

RY_TO_EV = 13.6057
PANDOC = Path(r"D:\pandoc\pandoc-3.6.4\pandoc.exe")
XELATEX = Path(r"D:\MiKTeX\miktex\bin\x64\xelatex.exe")


def setup_chinese_font():
    simhei = Path(r"C:\Windows\Fonts\simhei.ttf")
    if simhei.is_file():
        font_manager.fontManager.addfont(str(simhei))
    plt.rcParams["font.sans-serif"] = ["SimHei"]
    plt.rcParams["axes.unicode_minus"] = False


SUB_MAP = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUP_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def preprocess(text: str) -> str:
    """Unicode 上下标 → LaTeX 数学模式（pandoc/xelatex 缺字形规避）。"""
    text = re.sub(r"[₀₁₂₃₄₅₆₇₈₉]+",
                  lambda m: "$_{" + m.group().translate(SUB_MAP) + "}$", text)
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+",
                  lambda m: "$^{" + m.group().translate(SUP_MAP) + "}$", text)
    return text


def load_parsed(root: Path) -> dict:
    data = json.loads((root / "systems.json").read_text(encoding="utf-8"))
    conv = []
    if (root / "convergence.csv").is_file():
        conv = list(csv.DictReader((root / "convergence.csv").open(encoding="utf-8-sig")))
    quality = json.loads((root / "data_quality.json").read_text(encoding="utf-8"))
    return {"systems": data["systems"], "convergence": conv, "quality": quality}


def tex(name: str) -> str:
    return re.sub(r"[₀₁₂₃₄₅₆₇₈₉]+",
                  lambda m: "$_{" + m.group().translate(SUB_MAP) + "}$", name)


def fig_convergence(conv: list[dict], out: Path) -> str | None:
    """总能量 vs 参数收敛图；只画有数值的行。"""
    rows = [r for r in conv if r.get("total_energy_Ry")]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(6, 3.6))
    labels, vals = [], []
    for r in rows:
        labels.append(f"{r['system']}\n{r['ecutwfc']}Ry/{r['kgrid']}")
        vals.append(float(r["total_energy_Ry"]))
    ax.bar(range(len(vals)), vals, color="#2b6cb0")
    ax.set_xticks(range(len(vals)), labels, fontsize=7)
    ax.set_ylabel("总能量 (Ry)")
    ax.set_title("截断能/k 点收敛性验证（有值项）")
    fig.tight_layout()
    p = out / "fig_convergence.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p.name


def fig_site_relative(systems: list[dict], group: tuple, out: Path) -> str | None:
    """同组（chirality, modifier, molecule）三位点的相对总能柱状图。"""
    g = [s for s in systems if (s["chirality"], s["modifier"], s["molecule"]) == group]
    g = [s for s in g if s["pwo"].get("total_energy_eV")]
    if len(g) < 2:
        return None
    g.sort(key=lambda s: s["site"])
    base = min(s["pwo"]["total_energy_eV"] for s in g)
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    labels = [s["site"] for s in g]
    rel = [s["pwo"]["total_energy_eV"] - base for s in g]
    ax.bar(labels, rel, color="#e2a13a")
    ax.set_ylabel("相对总能 ΔE (eV，取组内最低为 0)")
    ax.set_title(f"{tex(group[0])} {group[1]} + {tex(group[2])} 位点比较（相对值）")
    for i, v in enumerate(rel):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    p = out / "fig_sites.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p.name


def md_quality_table(quality: dict) -> str:
    lines = ["| 检查项 | 结果 |", "|---|---|",
             f"| 体系总数 | {quality.get('n_systems', 0)} |",
             f"| 收敛性测试文件数 | {quality.get('n_convergence_test', 0)} |",
             f"| 警告数 | {len(quality.get('warnings', []))} |"]
    for w in quality.get("warnings", [])[:15]:
        lines.append(f"| [!] {w['type']} | {w['system']} |")
    return "\n".join(lines)


def md_conv_table(conv: list[dict]) -> str:
    if not conv:
        return "_无收敛性测试数据_"
    lines = ["| 体系 | ecutwfc (Ry) | k 点 | 总能量 (Ry) | 状态 |", "|---|---|---|---|---|"]
    for r in conv:
        lines.append(f"| {r['system']} | {r['ecutwfc']} | {r['kgrid']} | "
                     f"{r.get('total_energy_Ry') or '—'} | {r.get('converged') or '—'} |")
    return "\n".join(lines)


def md_analysis_materials(systems: list[dict], conv: list[dict]) -> str:
    """分析素材：位点排序与能差、异常提示、收敛性相邻差值（正文须消化为分析段落）。"""
    md = ["\n## 分析素材（正文须消化为分析段落）\n"]
    groups = sorted({(s["chirality"], s["modifier"], s["molecule"]) for s in systems})
    md.append("### 位点排序与能差（组内相对值）\n")
    md.append("| 手性 | 修饰 | 分子 | 位点排序（低→高） | 组内最大能差 (meV) | 异常提示 |")
    md.append("|---|---|---|---|---|---|")
    shown = 0
    for g in groups:
        gs = [s for s in systems
              if (s["chirality"], s["modifier"], s["molecule"]) == g
              and s["pwo"].get("total_energy_eV")]
        if len(gs) < 2:
            continue
        order = sorted(gs, key=lambda s: s["pwo"]["total_energy_eV"])
        base = order[0]["pwo"]["total_energy_eV"]
        spread = (order[-1]["pwo"]["total_energy_eV"] - base) * 1000
        anomaly = ""
        if spread > 500:
            anomaly += "组内能差>500 meV，需核对；"
        energies = [(s["site"], s["pwo"]["total_energy_eV"]) for s in order]
        if any(abs(b - a) < 1e-6 for (_, a), (_, b) in zip(energies, energies[1:])):
            anomaly += "存在完全相同的总能（疑似收敛到同一终态/精度不足）；"
        order_txt = " < ".join(f"{s['site']}({s['pwo']['total_energy_eV'] - base:.1f} meV)"
                               for s in order)
        md.append(f"| {g[0]} | {g[1]} | {tex(g[2])} | {order_txt} | {spread:.1f} | {anomaly or '—'} |")
        shown += 1
        if shown >= 20:
            md.append("| … | | | （仅列前 20 组，其余见附录） | | |")
            break

    if conv:
        md.append("\n### 收敛性相邻参数差值\n")
        md.append("| 体系 | 对比 | ΔE (eV) | 提示 |")
        md.append("|---|---|---|---|")
        by_sys: dict[str, list[dict]] = {}
        for r in conv:
            if r.get("total_energy_Ry"):
                by_sys.setdefault(r["system"], []).append(r)
        for sys_name, rows in sorted(by_sys.items()):
            rows = sorted(rows, key=lambda r: (int(r["ecutwfc"]), r["kgrid"]))
            for a, b in zip(rows, rows[1:]):
                de = abs((float(b["total_energy_Ry"]) - float(a["total_energy_Ry"])) * RY_TO_EV)
                tip = "差异大，截断能收敛性存疑" if de > 0.1 else "（正常量级）"
                md.append(f"| {sys_name} | {a['ecutwfc']}Ry/{a['kgrid']} → {b['ecutwfc']}Ry/{b['kgrid']} | {de:.3f} | {tip} |")
    return "\n".join(md)


def md_batch_report(data: dict, figs: dict, out_dir: Path) -> str:
    systems = data["systems"]
    q = data["quality"]
    mol_order = ["H2S", "SO2", "SOF2", "SO2F2", "SF6"]
    mod_order = ["pure", "Pt", "PtN", "PtPd"]
    coverage = {}
    for s in systems:
        coverage[(s["modifier"], s["molecule"])] = coverage.get((s["modifier"], s["molecule"]), 0) + 1

    md = []
    md.append("# QE 吸附计算数据分析报告\n")
    md.append("## 摘要\n\n本报告基于 QE 弛豫计算的原始输出（pwi/pwo），对吸附体系的收敛性、"
              "结构弛豫质量与组内位点相对稳定性进行分析。**吸附能绝对值待参考能量补齐后生成**。"
              "所有数值均直接来自输入文件，未作任何推测性补全。\n")
    md.append("## 数据集与计算设置\n")
    if systems:
        p = systems[0]["pwi"] or {}
        md.append(f"- 体系总数：{len(systems)}；元素种类：{p.get('ntyp')}；"
                  f"泛函：{p.get('input_dft')}；vdW 校正：{p.get('vdw_corr')}；"
                  f"截断能 ecutwfc：{p.get('ecutwfc')} Ry / ecutrho：{p.get('ecutrho')} Ry；"
                  f"展宽：{p.get('smearing')} {p.get('degauss')} Ry；自旋：nspin={p.get('nspin')}\n")
    md.append("\n| 修饰 \\ 分子 | " + " | ".join(tex(m) for m in mol_order) + " |\n|---|---" + "---|" * len(mol_order))
    for m in mod_order:
        cells = [str(coverage.get((m, g), 0)) for g in mol_order]
        md.append(f"| {m} | " + " | ".join(cells) + " |")
    md.append("\n## 数据质量说明\n")
    md.append(md_quality_table(q))
    md.append("\n## 收敛性验证\n")
    md.append(md_conv_table(data["convergence"]))
    if figs.get("convergence"):
        md.append(f"\n![]({figs['convergence']})\n\n*图 1 截断能/k 点收敛性（有值项）。*\n")
    md.append("\n## 结果与讨论\n")
    md.append("### 组内位点相对稳定性\n")
    md.append("说明：无参考能量（E_slab/E_mol）时，绝对吸附能不可得；"
              "同组（同手性、同修饰、同分子）内 top/bridge/hollow 的化学组成相同，"
              "总能差为有效相对量。\n")
    groups = sorted({(s["chirality"], s["modifier"], s["molecule"]) for s in systems})
    if figs.get("sites"):
        md.append(f"\n![]({figs['sites']})\n\n*图 2 组内位点相对总能（示例组）。*\n")
    md.append("\n| 手性 | 修饰 | 分子 | 位点 | 总能量 (eV) | 相对 ΔE (eV) |\n|---|---|---|---|---|---|")
    shown = 0
    for g in groups:
        gs = [s for s in systems if (s["chirality"], s["modifier"], s["molecule"]) == g
              and s["pwo"].get("total_energy_eV")]
        if len(gs) < 2 or shown >= 12:
            continue
        base = min(s["pwo"]["total_energy_eV"] for s in gs)
        for s in sorted(gs, key=lambda x: x["site"]):
            md.append(f"| {s['chirality']} | {s['modifier']} | {tex(s['molecule'])} | {s['site']} | "
                      f"{s['pwo']['total_energy_eV']:.4f} | {s['pwo']['total_energy_eV'] - base:.4f} |")
        shown += 1
    md.append(md_analysis_materials(systems, data["convergence"]))
    md.append("\n## 结论\n")
    n_ok = sum(1 for s in systems if s["quality"]["job_done"] and s["quality"]["scf_converged"])
    n_bad = len(systems) - n_ok
    md.append(f"1) 数据质量：{len(systems)} 个体系中 {n_ok} 个正常完成且 SCF 收敛"
              f"{'，' + str(n_bad) + ' 个存在未完成/未收敛等问题（详见数据质量说明）' if n_bad else ''}。\n")
    md.append("2) 收敛性：收敛测试中可得到总能量的参数组合已列出；未收敛项如实保留，"
              "所选计算参数的可信度需结合收敛曲线判定。\n")
    md.append("3) 组内位点相对稳定性：同组内各吸附位点的总能差已在结果章节给出，"
              "可作为稳定吸附位判定依据（相对量，非绝对吸附能）。\n")
    md.append("4) 吸附能绝对值：**待参考能量补齐**（裸基底 4 修饰 × 2 手性 + 孤立分子 5 个），"
              "补齐后可直接生成 E_ads 表与跨体系排序。\n")
    md.append("\n## 附录：全量数据表\n")
    md.append("| 体系 | 修饰 | 分子 | 位点 | 总能量 (Ry) | 总能量 (eV) | 最大力 (eV/Å) | JOB DONE | SCF 收敛 |\n|---|---|---|---|---|---|---|---|---|")
    for s in sorted(systems, key=lambda x: x["system"]):
        pwo = s["pwo"]
        md.append(f"| {s['system']} | {s['modifier']} | {tex(s['molecule'])} | {s['site']} | "
                  f"{pwo.get('total_energy_Ry') or '—'} | {pwo.get('total_energy_eV') or '—'} | "
                  f"{pwo.get('max_force_eV_ang') if pwo.get('max_force_eV_ang') is not None else '—'} | "
                  f"{'✓' if pwo['job_done'] else '✗'} | {'✓' if pwo['scf_converged'] else '✗'} |")
    return "\n".join(md)


def md_single_report(data: dict, system: str, figs: dict) -> str:
    s = next((x for x in data["systems"] if x["system"] == system), None)
    if not s:
        print(f"未找到体系: {system}", file=sys.stderr)
        return ""
    pwi, pwo = s["pwi"] or {}, s["pwo"]
    md = []
    md.append(f"# {system} 数据分析报告\n")
    md.append("## 摘要\n")
    md.append(f"对 {s['chirality']}（{s['modifier']} 修饰）吸附 {tex(s['molecule'])}（{s['site']} 位点）"
              f"的 QE 弛豫计算结果进行分析。计算完成标志：{'正常（JOB DONE）' if pwo['job_done'] else '异常'}；"
              f"SCF 收敛：{'是' if pwo['scf_converged'] else '否'}。\n")
    md.append("## 体系与计算设置\n")
    md.append(f"- 修饰/手性/分子/位点：{s['modifier']} / {s['chirality']} / {tex(s['molecule'])} / {s['site']}\n"
              f"- 泛函：{pwi.get('input_dft')}；vdW 校正：{pwi.get('vdw_corr')}\n"
              f"- 截断能：ecutwfc = {pwi.get('ecutwfc')} Ry，ecutrho = {pwi.get('ecutrho')} Ry\n"
              f"- 展宽：{pwi.get('smearing')}，degauss = {pwi.get('degauss')} Ry；自旋：nspin = {pwi.get('nspin')}\n"
              f"- 收敛阈值：etot_conv_thr = {pwi.get('etot_conv_thr')} Ry，forc_conv_thr = {pwi.get('forc_conv_thr')} Ry/a.u.，SCF conv_thr = {pwi.get('conv_thr')} Ry\n"
              f"- 原子数：{pwo.get('nat_out')}；电子数：{pwo.get('nelec')}；k 点数：{pwo.get('kpoints')}\n")
    md.append("\n## 数据质量说明\n")
    issues = s["quality"]["issues"]
    md.append(f"- JOB DONE：{'✓' if pwo['job_done'] else '✗'}；SCF 收敛：{'✓' if pwo['scf_converged'] else '✗'}"
              f"{'；问题：' + '、'.join(issues) if issues else ''}\n")
    md.append("\n## 结果\n")
    md.append(f"- 总能量：{pwo.get('total_energy_Ry'):.6f} Ry（{pwo.get('total_energy_eV'):.4f} eV）\n"
              f"- 最大原子力：{pwo.get('max_force_eV_ang'):.4f} eV/Å\n"
              f"- SCF 迭代次数：{pwo.get('n_scf')}\n")
    md.append("\n## 结论\n")
    relaxed_ok = bool(pwo.get("job_done")) and bool(pwo.get("scf_converged"))
    md.append("1) 结构弛豫" + ("正常完成（JOB DONE 且 SCF 收敛）。" if relaxed_ok
              else "存在异常（JOB DONE/SCF 未全部满足），需核对 pwo 输出。") + "\n")
    md.append("   最大原子力见“结果”节；因采用选择性弛豫，冻结原子仍会输出力，"
              "最大力不宜单独作为弛豫失败判据。\n")
    md.append("2) 吸附能绝对值待参考能量补齐后给出；当前仅可报告总能与结构弛豫状态。\n")
    md.append("\n> 吸附能 E_ads = E(复合物) − E(基底) − E(气体)。所需参考能量："
              "对应裸基底与孤立气体分子的总能（同参数）。补齐后可生成 E_ads 绝对值。\n")
    return "\n".join(md)


def md_to_pdf(md_path: Path, pdf_path: Path) -> bool:
    if not PANDOC.is_file() or not XELATEX.is_file():
        print(f"[PDF] 缺少 pandoc 或 xelatex：\n  {PANDOC}\n  {XELATEX}")
        return False
    tmp = md_path.with_name(md_path.stem + ".tmp_pdf.md")
    tmp.write_text(preprocess(md_path.read_text(encoding="utf-8")), encoding="utf-8")
    cmd = [str(PANDOC), tmp.name, "-o", pdf_path.name, f"--pdf-engine={XELATEX}",
           "-V", "CJKmainfont=SimHei", "-V", "geometry:margin=2.5cm",
           "-V", "fontsize=11pt", "--resource-path", "."]
    try:
        r = subprocess.run(cmd, cwd=md_path.parent, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        print("[PDF] xelatex 编译超时（>600s）")
        return False
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        print("[PDF] 编译失败：\n", r.stdout[-2000:], r.stderr[-2000:])
        return False
    print(f"[PDF] 已生成 {pdf_path}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parsed", type=Path, help="parse_qe.py 输出目录")
    ap.add_argument("-o", "--out", type=Path, default=Path("report.md"))
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--mode", choices=["batch", "single"], default="batch")
    ap.add_argument("--system", default=None)
    args = ap.parse_args()
    if not args.parsed.is_dir():
        print(f"解析目录不存在: {args.parsed}", file=sys.stderr)
        return 1
    data = load_parsed(args.parsed)
    setup_chinese_font()
    out_dir = args.out.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    figs = {}
    conv_fig = fig_convergence(data["convergence"], out_dir)
    if conv_fig:
        figs["convergence"] = conv_fig
    if args.mode == "batch":
        group = None
        for g in sorted({(s["chirality"], s["modifier"], s["molecule"]) for s in data["systems"]}):
            if sum(1 for s in data["systems"]
                   if (s["chirality"], s["modifier"], s["molecule"]) == g) >= 2:
                group = g
                break
        if group:
            f = fig_site_relative(data["systems"], group, out_dir)
            if f:
                figs["sites"] = f
        md = md_batch_report(data, figs, out_dir)
    else:
        if not args.system:
            print("single 模式需要 --system", file=sys.stderr)
            return 1
        md = md_single_report(data, args.system, figs)
    if not md:
        return 1
    args.out.write_text(md, encoding="utf-8")
    print(f"[MD] 已生成 {args.out}")
    if args.pdf:
        md_to_pdf(args.out, args.pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
