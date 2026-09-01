"""verify_gates · 确定性投稿门（纯代码，零 LLM）

五项检查：齐全性 / 新鲜度（哈希防 STALE）/ verdict 一致性 / 禁静默 / 降级声明封顶。
overall 三态：no（存在阻断项）> provisional（降级评审或 kill WARN）> accepted（全绿）。
"""

import hashlib
import json
from pathlib import Path

REQUIRED_ARTIFACTS = [
    "SOURCES_MANIFEST.json",
    "论文_计划.md",
    "验收_契约.md",
    "评审_记录_R1.json",
    "评审_记录_R2.json",
    "致命一击.json",
    "数值_复核.json",
    "义务_台账.jsonl",
]


def _sha16(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run(out_dir: Path, snap: dict) -> tuple[dict, str]:
    out_dir = Path(out_dir)
    results: dict = {}

    # 1) 齐全性：六类工件 + 素材清单全部存在且非空
    missing = [name for name in REQUIRED_ARTIFACTS if not (out_dir / name).is_file() or (out_dir / name).stat().st_size == 0]
    results["齐全性"] = "pass" if not missing else f"fail:缺 {','.join(missing)}"

    # 2) 新鲜度：审计工件 _meta 指纹与当前成稿/数据文件实测一致（防「审计的是旧稿」）
    audit = _load(out_dir / "数值_复核.json") or {}
    meta = audit.get("_meta", {})
    draft = out_dir / "论文_初稿.md"
    fresh = meta.get("draft_sha256") == _sha16(draft) if draft.is_file() else False
    data_path = snap.get("data_path") or ""
    if fresh and data_path and meta.get("data_sha256"):
        fresh = meta.get("data_sha256") == _sha16(Path(data_path))
    results["新鲜度"] = "pass" if fresh else "fail:审计指纹与当前稿件不一致(STALE)或缺失"

    # 3) verdict 一致性：数据说 A、结论写 B 的任何组合都不放行
    findings = snap.get("audit_findings", 0)
    audit_ok = not (findings > 0 and str(audit.get("verdict", "")).upper() != "FAIL")
    audit_ok = audit_ok and not snap.get("audit_parse_error", False)
    kill = _load(out_dir / "致命一击.json") or {}
    crit_unres = sum(
        1
        for a in kill.get("atoms", [])
        if a.get("disposition") == "still_unresolved" and a.get("severity") == "critical"
    )
    kill_ok = not (crit_unres > 0 and snap.get("kill_verdict") != "FAIL")
    kill_ok = kill_ok and snap.get("kill_verdict") not in {"", "BLOCKED"}  # 解析失败/无 verdict 一律不放行（fail-closed）
    ledger_open = snap.get("ledger_open", 0)
    flags = snap.get("human_flags", [])
    ledger_ok = ledger_open == 0 or any(("台账" in f or "绕过" in f) for f in flags)
    results["一致性"] = (
        "pass" if (audit_ok and kill_ok and ledger_ok)
        else f"fail:audit_ok={audit_ok} kill_ok={kill_ok} ledger_ok={ledger_ok}"
    )

    # 4) 禁静默：阴性结论也必须有工件（NOT_APPLICABLE 同样落盘）
    silent_ok = (out_dir / "致命一击.json").is_file() and (out_dir / "数值_复核.json").is_file()
    results["禁静默"] = "pass" if silent_ok else "fail:审计环节缺工件"

    # 5) 降级声明封顶
    results["降级声明"] = "pass" if not snap.get("provisional") else "pass(封顶 provisional)"

    any_fail = any(v.startswith("fail") for v in results.values())
    if any_fail or snap.get("kill_verdict") == "FAIL":
        # kill FAIL＝存在 critical 未解拒稿点，属阻断项（M2 首跑实测曾漏网：FAIL 不封顶直通 accepted）
        overall = "no"
    elif snap.get("provisional") or snap.get("kill_verdict") == "WARN":
        overall = "provisional"
    else:
        overall = "accepted"
    return results, overall
