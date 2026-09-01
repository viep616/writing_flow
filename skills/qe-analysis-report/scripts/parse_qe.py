r"""解析 QE 吸附计算原始输出（pwi/pwo + convergence CSV）为结构化数据。

用法：
    python parse_qe.py <输入根目录> -o <输出目录>

输出：
    systems.json          每个体系的结构化数据（能量/结构/力/质量标志）
    summary.csv           全量摘要表
    data_quality.json     数据质量报告（缺失/重复/未收敛/未完成）
    convergence.csv       收敛性测试表（原样归一化）
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

RY_TO_EV = 13.6057
RYAU_TO_EVANG = 25.711

SYS_RE = re.compile(
    r"^adsorption_(?P<chirality>\d+,\d+_\w+)_"
    r"(?P<modifier>pure|Pt|PtN|PtPd)_"
    r"(?P<molecule>H2S|SO2|SOF2|SO2F2|SF6)_"
    r"(?P<site>top|bridge|hollow)_(?P<id>\d+)$"
)

PWI_FIELDS = {
    "calculation": r"calculation\s*=\s*'([^']+)'",
    "etot_conv_thr": r"etot_conv_thr\s*=\s*([\d.EeDd+-]+)",
    "forc_conv_thr": r"forc_conv_thr\s*=\s*([\d.EeDd+-]+)",
    "nat": r"nat\s*=\s*(\d+)",
    "ntyp": r"ntyp\s*=\s*(\d+)",
    "ecutwfc": r"ecutwfc\s*=\s*([\d.]+)",
    "ecutrho": r"ecutrho\s*=\s*([\d.]+)",
    "input_dft": r"input_dft\s*=\s*'([^']+)'",
    "vdw_corr": r"vdw_corr\s*=\s*'([^']+)'",
    "nspin": r"nspin\s*=\s*(\d+)",
    "occupations": r"occupations\s*=\s*'([^']+)'",
    "smearing": r"smearing\s*=\s*'([^']+)'",
    "degauss": r"degauss\s*=\s*([\d.]+)",
    "conv_thr": r"conv_thr\s*=\s*([\d.EeDd+-]+)",
    "ion_dynamics": r"ion_dynamics\s*=\s*'([^']+)'",
}

PWO_PATTERNS = {
    "nat_out": r"number of atoms/cell\s*=\s*(\d+)",
    "nelec": r"number of electrons\s*=\s*([\d.]+)",
    "kpoints": r"number of k points\s*=\s*(\d+)",
    "job_done": r"JOB DONE",
}


def num(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


def parse_pwi(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict = {}
    for key, pat in PWI_FIELDS.items():
        m = re.search(pat, text, re.I)
        out[key] = m.group(1) if m else None
    out["species"] = re.findall(r"^\s*([A-Z][a-z]?)\s+[\d.]+\s+\S+", text, re.M)
    return out


def parse_pwo(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict = {"file": path.name}
    for key, pat in PWO_PATTERNS.items():
        if key == "job_done":
            out[key] = bool(re.search(pat, text))
            continue
        m = re.search(pat, text)
        out[key] = m.group(1) if m else None

    energies = [float(x) for x in re.findall(r"total energy\s*=\s*(-?\d+\.\d+)\s*Ry", text)]
    out["total_energy_Ry"] = energies[-1] if energies else None
    out["total_energy_eV"] = energies[-1] * RY_TO_EV if energies else None
    out["n_scf"] = len(energies)

    acc = re.findall(r"estimated scf accuracy\s*<\s*(-?[\d.]+)", text)
    out["last_scf_accuracy_Ry"] = float(acc[-1]) if acc else None
    out["scf_converged"] = text.count("convergence has been achieved") > 0

    forces = []
    tail = text[text.rfind("Forces acting on atoms"):]
    end = tail.find("The non-local contrib.")
    tail = tail[:end] if end != -1 else tail[:30000]
    for fm in re.finditer(
        r"atom\s+\d+\s+type\s+\d+\s+force\s*=\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)",
        tail,
    ):
        fx, fy, fz = (float(fm.group(i)) for i in (1, 2, 3))
        forces.append((fx**2 + fy**2 + fz**2) ** 0.5)
    out["max_force_Ryau"] = max(forces) if forces else None
    out["max_force_eV_ang"] = max(forces) * RYAU_TO_EVANG if forces else None
    out["force_count"] = len(forces)
    return out


def parse_sys_name(name: str) -> dict | None:
    m = SYS_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    d["group"] = (d["chirality"], d["modifier"], d["molecule"])
    return d


def scan(root: Path) -> dict:
    systems: list[dict] = []
    warnings: list[dict] = []
    conv_csv = None

    conv_csv_path = root / "convergence_results.csv"
    if conv_csv_path.is_file():
        conv_csv = list(csv.DictReader(conv_csv_path.open(encoding="utf-8-sig")))

    for pwo_path in sorted(root.rglob("*.pwo")):
        folder = pwo_path.parent
        pwi_path = folder / "espresso.pwi"
        pwi_alt = folder / "espresso (1).pwi"
        pwo_alt = folder / "espresso (1).pwo"
        name = folder.name

        if SYS_RE.match(name):
            if pwo_path.name.startswith("espresso (1)"):
                continue  # 重复文件本身不解析，仅提示
            if pwo_path.name == "espresso.pwo" and pwo_alt.is_file():
                warnings.append({"type": "duplicate_pwo", "system": name,
                                 "files": [pwo_path.name, pwo_alt.name]})
            pwi = parse_pwi(pwi_path) if pwi_path.is_file() else None
            if not pwi and pwi_alt.is_file():
                pwi = parse_pwi(pwi_alt)
            pwo = parse_pwo(pwo_path)
            sys_info = parse_sys_name(name)
            systems.append({
                "system": name,
                "dir": str(folder),
                **sys_info,
                "pwi": pwi,
                "pwo": pwo,
                "quality": {
                    "has_pwi": bool(pwi),
                    "has_pwo": True,
                    "job_done": pwo["job_done"],
                    "scf_converged": pwo["scf_converged"],
                    "issues": [
                        ("missing_pwi" if not pwi else None),
                        ("job_not_done" if not pwo["job_done"] else None),
                        ("scf_not_converged" if not pwo["scf_converged"] else None),
                    ],
                },
            })
            systems[-1]["quality"]["issues"] = [i for i in systems[-1]["quality"]["issues"] if i]
        elif pwo_path.parent.name == "convergence_test":
            pass  # 收敛性测试由 CSV/单独扫描处理

    conv_test = []
    ct_dir = root / "convergence_test"
    if ct_dir.is_dir():
        for p in sorted(ct_dir.glob("*.pwo")):
            rec = parse_pwo(p)
            rec["file"] = p.name
            rec["system"] = p.stem
            conv_test.append(rec)

    # 缺失 pwo 的体系（有 pwi 无 pwo）
    for pwi_path in sorted(root.rglob("*.pwi")):
        folder = pwi_path.parent
        if SYS_RE.match(folder.name) and not (folder / "espresso.pwo").is_file():
            warnings.append({"type": "missing_pwo", "system": folder.name})

    return {"systems": systems, "convergence_csv": conv_csv,
            "convergence_test": conv_test, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("."))
    args = ap.parse_args()
    if not args.root.is_dir():
        print(f"输入目录不存在: {args.root}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    data = scan(args.root)

    (args.out / "systems.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.out / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["system", "chirality", "modifier", "molecule", "site", "id",
                    "total_energy_Ry", "total_energy_eV", "max_force_eV_ang",
                    "job_done", "scf_converged", "issues"])
        for s in data["systems"]:
            pwo = s["pwo"]
            w.writerow([s["system"], s["chirality"], s["modifier"], s["molecule"],
                        s["site"], s["id"], pwo["total_energy_Ry"], pwo["total_energy_eV"],
                        pwo["max_force_eV_ang"], pwo["job_done"], pwo["scf_converged"],
                        ";".join(s["quality"]["issues"])])
    if data["convergence_csv"]:
        with (args.out / "convergence.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(data["convergence_csv"][0].keys()))
            w.writeheader()
            w.writerows(data["convergence_csv"])
    (args.out / "data_quality.json").write_text(
        json.dumps({"n_systems": len(data["systems"]), "warnings": data["warnings"],
                    "n_convergence_test": len(data["convergence_test"])},
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"体系数: {len(data['systems'])}")
    print(f"警告: {len(data['warnings'])}")
    for w in data["warnings"][:10]:
        print(" -", w["type"], w["system"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
