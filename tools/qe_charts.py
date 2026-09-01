#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""qe_charts · QE 数据确定性出图（零 LLM，matplotlib，M4 PDF 链路补全）

从 output/QE_数据表.json（qe_extract 产物）与 convergence_results.csv 生成论文配图：
  图 1 位点稳定性热力图（行=管型×材料，列=气体，格=最优位点）
  图 2 位点翻转案例（6,6/H₂S：pure→bridge、Pt→top、PtPd→bridge 组内 ΔE 柱状）
  图 3 异常构型可视化（8,0/PtN/SOF₂ 组内 ΔE，暴露 hollow 15.13 eV 非物理高能态）
  图 4 参数收敛性（Pt_SF6_top_101 的 k 点/截断能 vs 总能量折线）
图与图注均程序生成，不经过 LLM。返回 [(文件名, 图注)]，由 md2pdf.insert_figures 锚点插入。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")


def _setup_font() -> None:
    for name in ("Noto Sans CJK SC", "Microsoft YaHei", "SimHei"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


SITE_COLORS = {"top": "#2e86ab", "bridge": "#e07b39", "hollow": "#6a994e"}


def _load_rows(json_path: Path) -> list[dict]:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))["rows"]


def _fig_site_heatmap(rows: list[dict], out: Path) -> str:
    groups: dict[tuple, dict[str, str]] = {}
    for r in rows:
        groups.setdefault((r["chirality"], r["material"]), {})[r["gas"]] = None
    for r in rows:
        if r["delta_to_best_ev"] == 0.0:
            groups[(r["chirality"], r["material"])][r["gas"]] = r["site"]
    gases = ["SOF2", "SO2F2", "SO2", "H2S", "SF6"]
    gas_label = {"SOF2": "SOF₂", "SO2F2": "SO₂F₂", "SO2": "SO₂", "H2S": "H₂S", "SF6": "SF₆"}
    keys = sorted(groups)
    fig, ax = plt.subplots(figsize=(7.4, 0.62 * len(keys) + 1.5))
    for y, key in enumerate(keys):
        for x, gas in enumerate(gases):
            site = groups[key].get(gas)
            if site:
                ax.text(x, y, site, ha="center", va="center", fontsize=9,
                        color="white", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.32", fc=SITE_COLORS[site]))
    ax.set_xticks(range(len(gases)))
    ax.set_xticklabels([gas_label[g] for g in gases], fontsize=10)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([f"{c.split('_')[0]} · {m}" for c, m in keys], fontsize=9)
    ax.set_xlim(-0.5, len(gases) - 0.5)
    ax.set_ylim(len(keys) - 0.5, -0.5)
    ax.set_title("图 1　管型×掺杂×气体 的组内最优吸附位点图谱", fontsize=11)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return "各分组内能量最低构型的吸附位点（数据表 §2 位点稳定性，代码推导）"


def _fig_group_bars(rows: list[dict], chir: str, mat: str, gas: str, out: Path, title: str) -> str | None:
    members = sorted((r for r in rows if r["chirality"] == chir and r["material"] == mat and r["gas"] == gas),
                     key=lambda r: r["site"])
    if len(members) < 2:
        return None
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    sites = [m["site"] for m in members]
    vals = [m["delta_to_best_ev"] for m in members]
    ax.bar(sites, vals, color=[SITE_COLORS[s] for s in sites], width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.02, f"{v:.4f}", ha="center", fontsize=8.5)
    ax.set_ylabel("ΔE (eV)", fontsize=10)
    ax.set_title(title, fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return f"{title}（数据表 §3，ΔE 为相对组内最优的代码推导差值）"


def _fig_convergence(csv_path: Path, out: Path) -> str | None:
    if not csv_path.is_file():
        return None
    sys_pt = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["system"] == "Pt_SF6_top_101" and row["total_energy_Ry"]:
                sys_pt.append((f"{row['ecutwfc']}Ry·{row['kgrid']}", float(row["total_energy_Ry"])))
    if len(sys_pt) < 2:
        return None
    fig, ax = plt.subplots(figsize=(5.6, 3.0))
    labels = [s for s, _ in sys_pt]
    vals = [v for _, v in sys_pt]
    base = vals[-1]
    ax.plot(labels, [v - base for v in vals], "o-", color="#2e86ab")
    for i, v in enumerate(vals):
        ax.annotate(f"{v - base:+.3f}", (i, v - base), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=8.5)
    ax.set_ylabel("ΔE_total (Ry, 相对最收敛点)", fontsize=9.5)
    ax.set_title("图 4　Pt/SF₆@(101) 体系 k 点与截断能收敛性", fontsize=10.5)
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return "convergence_results.csv 中 Pt_SF6_top_101 各参数组合的总能差（原始数据，未换算）"


def generate(json_path: Path, csv_path: Path | None = None, out_dir: Path | None = None) -> list[tuple[str, str]]:
    """→ [(png 文件名, 图注)]。图注由代码生成，图片插入由 md2pdf.insert_figures 完成。"""
    _setup_font()
    out_dir = Path(out_dir) if out_dir else Path(json_path).parent / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _load_rows(json_path)
    figures: list[tuple[str, str]] = []

    f1 = "qe_fig1_site_map.png"
    figures.append((f1, _fig_site_heatmap(rows, out_dir / f1)))

    for fname, (chir, mat, gas, title) in {
        "qe_fig2_site_flip.png": ("6,6_armchair", "PtPd", "H2S", "图 2　6,6 扶手椅管 PtPd/H₂S 组内位点稳定性"),
        "qe_fig3_outlier.png": ("8,0_zigzag", "PtN", "SOF2", "图 3　8,0 锯齿管 PtN/SOF₂ 组内位点稳定性（含异常高能构型）"),
    }.items():
        cap = _fig_group_bars(rows, chir, mat, gas, out_dir / fname, title)
        if cap:
            figures.append((fname, cap))

    if csv_path and csv_path.is_file():
        f4 = "qe_fig4_convergence.png"
        cap4 = _fig_convergence(csv_path, out_dir / f4)
        if cap4:
            figures.append((f4, cap4))

    print(f"[qe_charts] 生成 {len(figures)} 张图 → {out_dir}")
    return figures


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    generate(base / "output" / "QE_数据表.json", base / "data" / "upstream_handoff" / "convergence_results.csv")
