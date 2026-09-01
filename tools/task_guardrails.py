"""task_guardrails · CrewAI Task guardrail 兜底（确定性校验，代码裁决）

经 jsonc 任务字段 {"python": "tools.task_guardrails.xxx"} 接线（crew_review / crew_audit / crew_kill）。
校验失败返回修正性反馈触发重试（guardrail_max_retries=1，配置在各 jsonc）；
重试耗尽仍失败则放行原文，由 main.py 的 fail-closed 链（停机门/投稿门）兜底拦截。
JSON 提取复用 review_gate（单一解析源），两类实测失败模式的修正指引：
  ① 字符串内嵌未转义双引号（M2 首跑 R1 实录）
  ② 输出散文/核对过程而非严格 JSON（M2 首跑审计实录）
"""

from __future__ import annotations

try:
    import review_gate  # main.py 已将 tools/ 挂入 sys.path
except ImportError:  # 经 jsonc {"python": ...} 独立加载时按包内相对导入
    from . import review_gate  # type: ignore[no-redef]

_RULE = (
    "修正要求：只输出单个 JSON 对象，禁止任何解释文字、核对过程或 Markdown 列表；"
    "字符串值内部若需引用原文，用全角引号「」，禁止出现未转义的半角双引号。"
)


def _out(task_output):
    return task_output.raw if hasattr(task_output, "raw") else str(task_output)


def review_json(task_output):
    """评审任务：必须可解析出 score + verdict（与 review_gate.parse_text 同规）。"""
    parsed = review_gate.parse_text(_out(task_output))
    if parsed.get("parse_error"):
        return (
            False,
            "上一次输出不是可解析的评审 JSON（字符串内未转义引号或混入散文均会导致解析失败）。"
            + _RULE
            + '必须字段：{"score": 1-10 整数, "verdict": "ready|almost|not_ready", '
            '"weaknesses": [...], "uphold_check": [...]}。请原样重出完整 JSON。',
        )
    return (True, task_output)


def audit_json(task_output):
    """审计任务：必须可解析出 findings + verdict。"""
    parsed = review_gate._extract_json(_out(task_output))
    if parsed is None or "findings" not in parsed or "verdict" not in parsed:
        return (
            False,
            "上一次输出是逐项核对的散文而非严格 JSON——对账过程不必呈现，只交付结论。"
            + _RULE
            + '必须字段：{"findings": [{"type":"...","claim":"...","evidence":"...","detail":"..."}], '
            '"verdict": "PASS|FAIL"}（findings 可为空数组）。请重出纯 JSON。',
        )
    return (True, task_output)


def arbiter_json(task_output):
    """裁决任务：必须可解析出非空 atoms 数组。"""
    parsed = review_gate._extract_json(_out(task_output))
    atoms = (parsed or {}).get("atoms")
    if not isinstance(atoms, list) or not atoms:
        return (
            False,
            "上一次输出缺少可解析的非空 atoms 数组。"
            + _RULE
            + '必须字段：{"atoms": [{"id":"a1","point":"...",'
            '"disposition":"answered_by_current_text|partially_answered|still_unresolved",'
            '"severity":"critical|major|minor","evidence":"..."}]}（3-7 条）。请重出纯 JSON。',
        )
    return (True, task_output)
