"""review_gate · 评审停机状态机（纯代码，模型无权判定停机）

双条件停机：score>=6 且 verdict in {ready, almost} 同时成立才 PASSED；
单高分不停车（防「高分 + not_ready」假阳性）。
JSON 解析失败 → REVIEW_UNAVAILABLE，fail-closed，绝不即兴放行。
"""

import json
from pathlib import Path

PASS_SCORE = 6
PASS_VERDICTS = {"ready", "almost"}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[: t.rstrip().rfind("```")]
    return t.strip()


def _extract_json(text: str) -> dict | None:
    """从评审原文提取首个平衡的大括号 JSON 对象；解析只提字段不改写原文。"""
    t = _strip_fences(text)
    start = t.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
                    break
        start = t.find("{", start + 1)
    return None


def parse_file(path: Path) -> dict:
    """读评审原文文件 → 解析字段；失败返回 {"parse_error": True}（fail-closed 依据）。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {"parse_error": True}
    parsed = _extract_json(text)
    if parsed is None or "score" not in parsed or "verdict" not in parsed:
        return {"parse_error": True}
    parsed.setdefault("weaknesses", [])
    parsed.setdefault("uphold_check", [])
    return parsed


def decide(parsed: dict) -> dict:
    """状态机判定：PASSED / NOT_PASSED / REVIEW_UNAVAILABLE。"""
    if parsed.get("parse_error"):
        return {"status": "REVIEW_UNAVAILABLE", "passed": False, "parse_error": True}
    score = parsed.get("score")
    verdict = str(parsed.get("verdict", "")).strip().lower()
    passed = isinstance(score, (int, float)) and score >= PASS_SCORE and verdict in PASS_VERDICTS
    return {
        "status": "PASSED" if passed else "NOT_PASSED",
        "passed": passed,
        "parse_error": False,
        "rule": f"score>={PASS_SCORE} 且 verdict in {sorted(PASS_VERDICTS)}",
    }


def read_findings(path: Path) -> tuple[int, bool]:
    """读数值复核工件：返回 (findings 数, 是否解析失败)。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return len(data.get("findings", [])), False
    except (OSError, json.JSONDecodeError):
        return 0, True


def uphold_list(parsed_r1: dict, out_dir: Path) -> list:
    """从 R1 解析结果提取成立弱点清单（critical + major），供 R2 注入核验与台账合成。"""
    upheld = [
        {"id": w.get("id", f"w{i+1}"), "desc": w.get("desc", ""), "severity": w.get("severity", "major")}
        for i, w in enumerate(parsed_r1.get("weaknesses", []))
        if w.get("severity") in {"critical", "major"}
    ]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "评审_R1成立清单.md").write_text(
        "\n".join(f"- {u['id']} [{u['severity']}] {u['desc']}" for u in upheld) + "\n", encoding="utf-8"
    )
    (out_dir / "评审_R1成立清单.json").write_text(json.dumps(upheld, ensure_ascii=False, indent=2), encoding="utf-8")
    return upheld
