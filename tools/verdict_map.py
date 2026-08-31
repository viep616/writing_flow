"""verdict_map · 致命一击 verdict 计数表映射（纯代码，模型不参与自己 verdict 的判定）

映射规则（与 ARIS kill-argument 一致）：
  无原子点                      → NOT_APPLICABLE（仍须落盘工件）
  任一 still_unresolved@critical → FAIL
  存在任一 still_unresolved      → WARN
  partial@critical / partial@major → WARN
  其余（未决为 0）              → PASS
"""

import json
from pathlib import Path

UNRESOLVED = "still_unresolved"
PARTIAL = "partially_answered"


def map_atoms(atoms: list) -> tuple[str, int, int]:
    """→ (verdict, 未决总数, 其中 critical 未决数)。"""
    if not atoms:
        return "NOT_APPLICABLE", 0, 0
    unresolved = [a for a in atoms if a.get("disposition") == UNRESOLVED]
    crit_unresolved = [a for a in unresolved if a.get("severity") == "critical"]
    partial_heavy = [
        a for a in atoms if a.get("disposition") == PARTIAL and a.get("severity") in {"critical", "major"}
    ]
    if crit_unresolved:
        verdict = "FAIL"
    elif unresolved or partial_heavy:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return verdict, len(unresolved), len(crit_unresolved)


def map_file(path: Path) -> tuple[list, str, int]:
    """读致命一击工件 → 代码映射 verdict 并回写 verdict_mapped 字段（留痕显示结论来源）。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    atoms = data.get("atoms", [])
    verdict, unresolved, _crit = map_atoms(atoms)
    data["verdict_mapped"] = verdict
    data["unresolved_count"] = unresolved
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return atoms, verdict, unresolved
