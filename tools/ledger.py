"""ledger · 跨轮义务台账（append-only，删句绕过检测）

R1 成立弱点在 R2 必须有核验记录（addressed / upheld_again）或处置说明；
既无核验记录也无处置 → UNRESOLVED_DISAPPEARANCE（把被判处的句子删掉而非修复）。
开放数 = upheld_again + no_record（R2 新成立的弱点由评审记录另行反映）。
"""

import json
from datetime import datetime
from pathlib import Path


def build(r1_upheld: list, r2_checks: list) -> tuple[list, int, int]:
    """→ (台账条目, 开放数, 删句绕过数)。"""
    checks = {c.get("id"): str(c.get("status", "no_record")).strip().lower() for c in r2_checks}
    entries, open_count, disappear = [], 0, 0
    for item in r1_upheld:
        wid = item.get("id", "")
        status = checks.get(wid, "no_record")
        if status == "addressed":
            resolved, note = True, "R2 已核验回应"
        elif status in {"upheld_again", "upheld", "仍成立"}:
            resolved, note = False, "R2 复审仍成立"
        else:
            resolved, note = False, "UNRESOLVED_DISAPPEARANCE：既无核验记录也无处置（删句绕过嫌疑）"
            disappear += 1
        if not resolved:
            open_count += 1
        entries.append(
            {
                "id": wid,
                "desc": item.get("desc", ""),
                "severity": item.get("severity", ""),
                "r2_status": status,
                "resolved": resolved,
                "note": note,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return entries, open_count, disappear


def build_and_save(r1_json_path: Path, r2_checks: list, out_path: Path) -> tuple[list, int, int]:
    r1_upheld = json.loads(Path(r1_json_path).read_text(encoding="utf-8")) if Path(r1_json_path).is_file() else []
    entries, open_count, disappear = build(r1_upheld, r2_checks)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:  # append-only：收据永不覆盖
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return entries, open_count, disappear
