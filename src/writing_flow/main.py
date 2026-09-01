#!/usr/bin/env python
"""writing_flow · ARIS 论文写作流程的 CrewAI Flow 实现（M1 骨架版）

结构（固定两轮改进循环，静态展开，满足 v1.15 禁自监听约束）：

    @start load_inputs          判道：upstream_handoff（上游交接）/ 独立素材 / 已有初稿
    @listen paper_plan          plan_crew → 论文_计划.md（claims-evidence 矩阵）
    @listen negotiate_contract  contract_crew ≤2 轮 → 验收_契约.md（accepted/contested）
    @router route_contract      accepted → "write"；contested → "write_flagged"（不阻断）
    @listen write_sections      write_crew 分节写作；refine 模式跳过（已有初稿直接进循环）
    @listen review_r1           review_crew 全新实例（跨家族）→ 评审原文逐字落盘
    @router route_r1            双条件停机（score>=6 且 verdict in ready/almost）→ final_audits / revise
    @listen revise_paper        revise_crew 按 R1 弱点最小修复
    @listen review_r2           复审（新实例）+ R1 清单核验 + 义务台账合成
    @router route_r2            恒转 final_audits（固定两轮）
    @listen kill_argument       kill_crew → 原子点三分类；verdict 由 verdict_map.py 代码映射
    @listen claim_audit         audit_crew 零上下文对账 → findings + _meta 指纹
    @listen verify_gates        纯代码五项检查 → overall 三态
    @listen finalize            时间戳留档 + 后缀合成 + RUN_STATE 终报

桩模式（M1 验收）：设 WRITING_FLOW_STUB=1 后全流程不调 LLM，
各 Crew 阶段以确定性桩数据驱动，验证 DAG、路由、状态机、台账、
投稿门与留档后缀的完整链路。

用法（项目根目录）：
    桩模式：$env:WRITING_FLOW_STUB='1'; & "..\.venv\Scripts\python.exe" src\writing_flow\main.py
    真实模式：& "..\.venv\Scripts\python.exe" src\writing_flow\main.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # writing_flow 仓库根

# Windows 控制台默认 GBK：LLM 输出含下标字符（如 SOF₂）时 print 崩溃，全程强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

# 将 crewai 的运行/配置数据目录重定向到项目内 .appdata/（须在首次 import crewai 前 patch；
# 否则 crewai 尝试写 ~/.config/crewai，在受限环境下被拦截）。MiKTeX 等子进程需要真实用户目录，
# 真实值存档备用（沿用 sf6 初探已验证的处理方式）。
_RUN_DATA_DIR = str(BASE_DIR / ".appdata")
os.makedirs(_RUN_DATA_DIR, exist_ok=True)
import crewai_core.paths as _crewai_paths  # noqa: E402

_crewai_paths.db_storage_path = lambda: _RUN_DATA_DIR
_REAL_USER_ENV = {k: os.environ[k] for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE") if k in os.environ}
os.environ["APPDATA"] = _RUN_DATA_DIR
os.environ["LOCALAPPDATA"] = _RUN_DATA_DIR
os.environ["USERPROFILE"] = _RUN_DATA_DIR

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE_DIR / ".env", override=True)

from crewai.flow import Flow, listen, or_, router, start  # noqa: E402
from crewai.flow.persistence import persist  # noqa: E402
from crewai.project.crew_loader import load_crew  # noqa: E402
from pydantic import BaseModel  # noqa: E402

sys.path.insert(0, str(BASE_DIR / "tools"))
import archive  # noqa: E402
import ledger  # noqa: E402
import prepare_inputs  # noqa: E402
import review_gate  # noqa: E402
import verdict_map  # noqa: E402
import verify_gates  # noqa: E402

try:  # 回收自 sf6 初探：真实模式才需要，缺失不阻塞桩模式
    import md2pdf  # noqa: E402

    md2pdf.REAL_USER_ENV.update(_REAL_USER_ENV)
except Exception:  # pragma: no cover
    md2pdf = None

OUTPUT_DIR = BASE_DIR / "output"
STUB = os.getenv("WRITING_FLOW_STUB", "") == "1"
# 数据目录可覆盖（M4：精修模式实测等场景免动生产交接区；默认生产路径不变）
DATA_DIR = Path(os.getenv("WRITING_FLOW_DATA_DIR", "")) if os.getenv("WRITING_FLOW_DATA_DIR") else BASE_DIR / "data"

DRAFT_FILE = OUTPUT_DIR / "论文_初稿.md"
REVIEWER_FAMILY = os.getenv("WRITING_FLOW_REVIEWER_FAMILY", "deepseek")


# ---------------------------------------------------------------- 状态模型
class ArisPaperState(BaseModel):
    """Flow 共享状态：只放路由决策、计数与标记；大文本一律走 output/ 文件。"""

    stamp: str = ""
    mode: str = "standalone"          # standalone | refine
    source_ref: str = ""              # 素材溯源：上游 HANDOFF 的 state.id 或文件名
    topic_anchor: str = ""            # 课题锚定（上游 HANDOFF 指定；空则由素材自行提炼）
    stage_status: dict = {}           # 阶段 → running/done/failed/skipped（幂等依据）
    contract_status: str = "pending"  # pending | accepted | contested
    review_scores: list = []          # R1/R2 综合分轨迹
    review_verdicts: list = []        # ready | almost | not_ready
    review_passed: bool = False       # review_gate 双条件判定结果（最近一轮）
    review_parse_error: bool = False
    r1_upheld: list = []              # R1 成立弱点清单（critical+major），review_r1 阶段代码生成
    reviewer_family: str = REVIEWER_FAMILY
    provisional: bool = False         # 同家族降级评审标记
    kill_verdict: str = ""            # PASS|WARN|FAIL|BLOCKED|NOT_APPLICABLE
    kill_unresolved: int = 0
    audit_findings: int = 0
    audit_parse_error: bool = False
    ledger_open: int = 0
    human_flags: list = []            # 转人工标记
    gate_results: dict = {}           # verify_gates 各检查项 → pass/fail
    overall: str = ""                 # accepted | provisional | no


# ---------------------------------------------------------------- 工具函数
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _kick(crew_file: str, inputs: dict):
    """加载根目录 jsonc Crew 并 kickoff（真实模式专用；每轮新建实例＝新鲜线程协议）。"""
    crew, defaults = load_crew(BASE_DIR / crew_file)
    return crew.kickoff(inputs={**defaults, **inputs})


def _snapshot_review(round_no: int) -> None:
    """真实模式桥接：评审_原文_R.txt → 评审_原文_R{round_no}.txt。
    Crew 未产出时落空文件 → 解析必失败 → fail-closed，杜绝读到上一轮/桩的旧评审。"""
    src = OUTPUT_DIR / "评审_原文_R.txt"
    text = src.read_text(encoding="utf-8") if src.is_file() else ""
    _write(OUTPUT_DIR / f"评审_原文_R{round_no}.txt", text)


def _merge_kill_artifacts() -> bool:
    """真实模式桥接：致命_攻击段.md + 致命_原子点.json → 规范名 致命一击.json。
    返回是否解析失败（atoms 缺失/为空/非法均 fail-closed 判失败，防止空 atoms 一路绿）。
    JSON 提取用 _extract_json（括号平衡，兼容围栏/散文前缀）——严格 json.loads 会把
    「散文+尾部JSON」形态误判为解析失败（M2 首跑审计实录：真 findings 曾被丢弃）。"""
    attack_path = OUTPUT_DIR / "致命_攻击段.md"
    attack = attack_path.read_text(encoding="utf-8").strip() if attack_path.is_file() else ""
    payload = {"attack": attack, "atoms": [], "parse_error": False}
    try:
        doc = review_gate._extract_json((OUTPUT_DIR / "致命_原子点.json").read_text(encoding="utf-8")) or {}
        atoms = doc.get("atoms", [])
        if atoms:
            payload["atoms"] = atoms
        else:
            payload["parse_error"] = True
    except (OSError, AttributeError):
        payload["parse_error"] = True
    _write(OUTPUT_DIR / "致命一击.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return payload["parse_error"]


def _merge_audit_artifacts(data_path) -> bool:
    """真实模式桥接：数值_复核_原文.json → 规范名 数值_复核.json，注入 _meta 双指纹（新鲜度门依据）。
    返回是否解析失败（失败仍落盘合法 JSON，由 audit_parse_error 与 verdict=PARSE_ERROR 双路 fail-closed）。
    提取用 _extract_json（括号平衡）：审计员常见「散文核对过程+尾部 JSON」形态，严格 loads 会误丢弃真 findings。"""
    meta = {
        "draft_sha256": _sha(DRAFT_FILE),
        "data_file": str(data_path or ""),
        "data_sha256": _sha(data_path) if data_path else None,
        "generated_at": _now(),
    }
    src = OUTPUT_DIR / "数值_复核_原文.json"
    try:
        doc = review_gate._extract_json(src.read_text(encoding="utf-8"))
        if doc is None or "findings" not in doc or "verdict" not in doc:
            raise ValueError("缺少 findings/verdict 字段")
        payload = {"findings": doc.get("findings", []), "verdict": doc.get("verdict", ""), "_meta": meta}
        parse_error = False
    except (OSError, ValueError):
        payload = {"findings": [], "verdict": "PARSE_ERROR", "parse_error": True, "_meta": meta}
        parse_error = True
    _write(OUTPUT_DIR / "数值_复核.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return parse_error


# ---------------------------------------------------------------- Flow 定义
@persist()  # SQLite 状态持久化：每个方法执行后自动快照（注意：persist 带默认参数，须调用形式）
class PaperFlow(Flow[ArisPaperState]):

    # ---------- 内部：阶段标记与人读状态双轨落盘 ----------
    def _mark(self, stage: str, status: str) -> None:
        self.state.stage_status[stage] = status
        payload = {
            "stamp": self.state.stamp,
            "mode": self.state.mode,
            "source_ref": self.state.source_ref,
            "stages": dict(self.state.stage_status),
            "contract_status": self.state.contract_status,
            "review": {
                "scores": list(self.state.review_scores),
                "verdicts": list(self.state.review_verdicts),
                "passed": self.state.review_passed,
                "parse_error": self.state.review_parse_error,
                "reviewer_family": self.state.reviewer_family,
                "provisional": self.state.provisional,
            },
            "kill": {"verdict": self.state.kill_verdict, "unresolved": self.state.kill_unresolved},
            "audit": {"findings": self.state.audit_findings, "parse_error": self.state.audit_parse_error},
            "ledger_open": self.state.ledger_open,
            "human_flags": list(self.state.human_flags),
            "gate_results": dict(self.state.gate_results),
            "overall": self.state.overall,
            "stub_mode": STUB,
            "updated_at": _now(),
        }
        _write(OUTPUT_DIR / "RUN_STATE.json", json.dumps(payload, ensure_ascii=False, indent=2))

    # ---------- F1 输入判道（纯代码） ----------
    @start()
    def load_inputs(self):
        self.state.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._mark("load_inputs", "running")
        info = prepare_inputs.run(DATA_DIR, OUTPUT_DIR)
        self.state.mode = info["mode"]
        self.state.source_ref = info["source_ref"]
        self.state.topic_anchor = info.get("topic_anchor", "")
        if info.get("from_upstream") and not info["handoff_present"] and info["mode"] == "refine":
            self.state.human_flags.append("交接不完整")  # 仅上游来源缺 HANDOFF 才标记；独立历史初稿不算
        self._mark("load_inputs", "done")
        print(f"[F1] 判道 mode={self.state.mode} source={self.state.source_ref} stamp={self.state.stamp}")

    # ---------- F2 论文规划 ----------
    @listen(load_inputs)
    def paper_plan(self):
        self._mark("paper_plan", "running")
        if STUB:
            _stub_plan()
        else:
            _kick("crew_plan.jsonc", {"SOURCES_MANIFEST": str(OUTPUT_DIR / "SOURCES_MANIFEST.json"), "TOPIC_ANCHOR": self.state.topic_anchor})
        self._mark("paper_plan", "done")

    # ---------- F3 验收契约谈判（≤2 轮） ----------
    @listen(paper_plan)
    def negotiate_contract(self):
        self._mark("negotiate_contract", "running")
        if STUB:
            _stub_contract()
            self.state.contract_status = "accepted"
        else:
            _kick("crew_contract.jsonc", {})
            self.state.contract_status = _read_contract_status()
        self._mark("negotiate_contract", "done")
        return self.state.contract_status

    @router(negotiate_contract)
    def route_contract(self, status: str) -> str:
        # 争议不阻断：带标记继续写作，终报降级（Submission-ready: no 由投稿门承担）
        if status == "contested":
            self.state.human_flags.append("契约争议")
        return "write" if status == "accepted" else "write_flagged"

    # ---------- F4 分节写作 ----------
    @listen(or_("write", "write_flagged"))
    def write_sections(self):
        self._mark("write_sections", "running")
        if self.state.mode == "refine":
            print("[F4] refine 模式：已有初稿直接进入改进循环")
            self._mark("write_sections", "skipped")
            return
        if STUB:
            _stub_draft()
        else:
            _kick("crew_write.jsonc", {})
        self._mark("write_sections", "done")

    # ---------- F5 改进循环 R1（跨家族·全新实例） ----------
    @listen(write_sections)
    def review_r1(self):
        self._mark("review_r1", "running")
        if STUB:
            _stub_review(1)
        else:
            _kick("crew_review.jsonc", {"DRAFT_PATH": str(DRAFT_FILE), "R1_UPHOLD_LIST": ""})
            _snapshot_review(1)
        parsed = review_gate.parse_file(OUTPUT_DIR / "评审_原文_R1.txt")
        gate = review_gate.decide(parsed)
        _save_review_record(1, parsed, gate)
        # R1 成立清单（critical+major）由代码从 R1 解析结果生成 → R2 注入核验 + 台账合成底稿；
        # 桩/真实统一走此路径（M1 遗留接线：原先桩内置、真实模式缺失）
        self.state.r1_upheld = review_gate.uphold_list(parsed, OUTPUT_DIR)
        self.state.review_scores.append(parsed.get("score"))
        self.state.review_verdicts.append(parsed.get("verdict", ""))
        self.state.review_parse_error = gate["parse_error"]
        self.state.review_passed = gate["passed"]
        self._mark("review_r1", "done")
        print(f"[F5] R1 score={parsed.get('score')} verdict={parsed.get('verdict')} → {gate['status']}")
        return gate["passed"]

    @router(review_r1)
    def route_r1(self, passed: bool) -> str:
        return "final_audits" if passed else "revise"

    # ---------- F5b 最小修复 ----------
    @listen("revise")
    def revise_paper(self):
        self._mark("revise_paper", "running")
        if not STUB:  # 真实模式修订前留档（M3 首跑发现的留痕缺口；桩模式自带快照）
            backup = OUTPUT_DIR / f"论文_初稿_{datetime.now().strftime('%Y%m%d_%H%M%S')}_修订前.md"
            if DRAFT_FILE.is_file():
                backup.write_text(DRAFT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        if STUB:
            _stub_revise()
        else:
            _kick("crew_revise.jsonc", {"WEAKNESS_LIST": str(OUTPUT_DIR / "评审_记录_R1.json")})
        self._mark("revise_paper", "done")

    # ---------- F5c 复审 R2 + 义务台账 ----------
    @listen(revise_paper)
    def review_r2(self):
        self._mark("review_r2", "running")
        if STUB:
            _stub_review(2)
        else:
            _kick("crew_review.jsonc", {"DRAFT_PATH": str(DRAFT_FILE), "R1_UPHOLD_LIST": str(OUTPUT_DIR / "评审_R1成立清单.md")})
            _snapshot_review(2)
        parsed = review_gate.parse_file(OUTPUT_DIR / "评审_原文_R2.txt")
        gate = review_gate.decide(parsed)
        _save_review_record(2, parsed, gate)
        self.state.review_scores.append(parsed.get("score"))
        self.state.review_verdicts.append(parsed.get("verdict", ""))
        self.state.review_parse_error = gate["parse_error"]
        self.state.review_passed = gate["passed"]
        entries, open_count, disappear = ledger.build_and_save(
            OUTPUT_DIR / "评审_R1成立清单.json", parsed.get("uphold_check", []), OUTPUT_DIR / "义务_台账.jsonl"
        )
        self.state.ledger_open = open_count
        if disappear:
            self.state.human_flags.append("删句绕过嫌疑")
        self._mark("review_r2", "done")
        print(f"[F5c] R2 score={parsed.get('score')} 台账开放 {open_count} 绕过 {disappear}")
        return gate["passed"]

    @router(review_r2)
    def route_r2(self, passed: bool) -> str:
        # 固定两轮：R2 后恒转终审；未达标只反映到留档后缀
        return "final_audits"

    # ---------- F6 致命一击 ----------
    @listen("final_audits")
    def kill_argument(self):
        self._mark("kill_argument", "running")
        if STUB:
            _stub_kill()
        else:
            _kick("crew_kill.jsonc", {"DRAFT_PATH": str(DRAFT_FILE)})
            if _merge_kill_artifacts():  # Crew 产物 → 规范名工件；解析失败 fail-closed 判 BLOCKED
                self.state.kill_verdict, self.state.kill_unresolved = "BLOCKED", 0
                self.state.human_flags.append("致命一击解析失败")
                self._mark("kill_argument", "done")
                print("[F6] 致命一击 verdict=BLOCKED（解析失败，fail-closed）")
                return
        atoms, verdict, unresolved = verdict_map.map_file(OUTPUT_DIR / "致命一击.json")
        self.state.kill_verdict, self.state.kill_unresolved = verdict, unresolved
        if verdict == "WARN":
            self.state.human_flags.append("kill_WARN_待人工确认")
        self._mark("kill_argument", "done")
        print(f"[F6] 致命一击 verdict={verdict} 未决={unresolved}")

    # ---------- F7 零上下文数值审计 ----------
    @listen(kill_argument)
    def claim_audit(self):
        self._mark("claim_audit", "running")
        data_path = prepare_inputs.current_data_file(OUTPUT_DIR)
        merged_error = False
        if STUB:
            _stub_audit(data_path)
        else:
            _kick("crew_audit.jsonc", {"DRAFT_PATH": str(DRAFT_FILE), "DATA_PATH": str(data_path or "")})
            merged_error = _merge_audit_artifacts(data_path)  # 注入 _meta 双指纹 → 规范名工件
        findings, parse_error = review_gate.read_findings(OUTPUT_DIR / "数值_复核.json")
        self.state.audit_findings = findings
        self.state.audit_parse_error = parse_error or merged_error
        self._mark("claim_audit", "done")
        print(f"[F7] 数值复核 findings={findings}")

    # ---------- F8 确定性投稿门（纯代码） ----------
    @listen(claim_audit)
    def verify_gates(self):
        self._mark("verify_gates", "running")
        snap = {
            "kill_verdict": self.state.kill_verdict,
            "kill_unresolved": self.state.kill_unresolved,
            "audit_findings": self.state.audit_findings,
            "audit_parse_error": self.state.audit_parse_error,  # M2 首跑实测漏传：解析失败曾绕过一致性门
            "ledger_open": self.state.ledger_open,
            "provisional": self.state.provisional,
            "human_flags": list(self.state.human_flags),
            "data_path": str(prepare_inputs.current_data_file(OUTPUT_DIR) or ""),
        }
        results, overall = verify_gates.run(OUTPUT_DIR, snap)
        self.state.gate_results = results
        self.state.overall = overall
        self._mark("verify_gates", "done")
        print(f"[F8] 投稿门 overall={overall} 明细={results}")

    # ---------- F9/F10 留档 + 终报 ----------
    @listen(verify_gates)
    def finalize(self):
        self._mark("finalize", "running")
        snap = json.loads((OUTPUT_DIR / "RUN_STATE.json").read_text(encoding="utf-8"))
        snap["gate_results"] = dict(self.state.gate_results)
        snap["overall"] = self.state.overall
        archived = archive.run(OUTPUT_DIR, snap, DRAFT_FILE, md2pdf)
        _write(
            OUTPUT_DIR / f"RUN_STATE_{self.state.stamp}.json",
            json.dumps({**snap, "archived": archived, "finished_at": _now()}, ensure_ascii=False, indent=2),
        )
        self._mark("finalize", "done")
        suffix = Path(archived).stem.replace(f"论文_成稿_{self.state.stamp}", "")
        print("=" * 60)
        print(f"[完成] 成稿留档：{Path(archived).name}")
        print(f"[完成] 投稿门 overall={self.state.overall}  后缀='{suffix or '（全绿）'}'")
        if self.state.human_flags:
            print(f"[转人工] {', '.join(self.state.human_flags)}")


# ---------------------------------------------------------------- 桩实现（M1 验收：确定性数据驱动全链路）
def _stub_plan() -> None:
    _write(
        OUTPUT_DIR / "论文_计划.md",
        "# 论文计划（桩）\n\n## claims-evidence 矩阵\n\n"
        "| # | 论断 | 证据槽位 | 可得 | 落点章节 |\n|---|------|---------|------|---------|\n"
        "| C1 | 吸附能排序 SOF2 > SO2 | data:关键物理量对照表 | 是 | 结果与讨论 |\n"
        "| C2 | 恢复时间量级判断 | data:对照表(留空) | 否→DATA_NEEDED | 结果与讨论 |\n\n"
        "## 章节结构（5-8 节）\n引言 / 计算方法 / 结果与讨论 / 结论 / 局限性\n\n"
        "## 图表计划\n吸附能分组柱状图（数据充足时）；不足自动跳过\n",
    )


def _stub_contract() -> None:
    _write(
        OUTPUT_DIR / "验收_契约.md",
        "# 验收契约（桩）\n\n状态：accepted\n\n"
        "| # | 可检验断言 | 挑战意见 | 处置 |\n|---|-----------|---------|------|\n"
        "| A1 | 正文吸附能数值与对照表逐项一致 | 无 | 接受 |\n"
    )


def _read_contract_status() -> str:
    text = (OUTPUT_DIR / "验收_契约.md").read_text(encoding="utf-8")
    return "contested" if "contested" in text else "accepted"


def _stub_draft() -> None:
    _write(
        DRAFT_FILE,
        "# 论文初稿（桩）\n\n主题锚定：SWNT-OH 对 SF6 分解气体的传感机制（第一性原理研究）。\n\n"
        "## 结果与讨论\n吸附能排序见对照表；恢复时间 <!-- DATA_NEEDED: 对照表该格留空 -->。\n\n"
        "## 局限性\n0 K 静态结果，不外推器件性能。\n",
    )


def _stub_review(round_no: int) -> None:
    if round_no == 1:
        payload = {
            "score": 5,
            "verdict": "not_ready",
            "weaknesses": [
                {"id": "w1", "severity": "critical", "desc": "结论表述超出数据支持范围", "min_fix": "收窄 scope"},
                {"id": "w2", "severity": "major", "desc": "图表与正文数值引用未一一对应", "min_fix": "补对照"},
                {"id": "w3", "severity": "minor", "desc": "术语混用", "min_fix": "统一术语"},
            ],
            "uphold_check": [],
        }
    else:
        payload = {
            "score": 7,
            "verdict": "almost",
            "weaknesses": [],
            "uphold_check": [
                {"id": "w1", "status": "addressed"},
                {"id": "w2", "status": "addressed"},
                {"id": "w3", "status": "addressed"},
            ],
        }
    _write(OUTPUT_DIR / f"评审_原文_R{round_no}.txt", "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n")


def _stub_revise() -> None:
    text = DRAFT_FILE.read_text(encoding="utf-8")
    _write(OUTPUT_DIR / f"论文_初稿_{datetime.now().strftime('%Y%m%d_%H%M%S')}_修订前.md", text)
    _write(DRAFT_FILE, text + "\n<!-- 修订说明（桩）：w1 已收窄结论表述；w2 已补图表-正文对照；w3 已统一术语 -->\n")


def _stub_kill() -> None:
    payload = {
        "attack": "（桩·致命一击）顶线主张依赖的恢复时间判据在数据表中留空，"
        "当前证据不足以支撑'高灵敏传感机制'的顶线表述，建议收窄或补算。",
        "atoms": [
            {"id": "a1", "disposition": "still_unresolved", "severity": "major", "point": "恢复时间证据缺失"},
            {"id": "a2", "disposition": "answered_by_current_text", "severity": "minor", "point": "单位与量纲已统一"},
            {"id": "a3", "disposition": "partially_answered", "severity": "minor", "point": "局限性章节可再收紧"},
        ],
    }
    _write(OUTPUT_DIR / "致命一击.json", json.dumps(payload, ensure_ascii=False, indent=2))


def _stub_audit(data_path) -> None:
    payload = {
        "findings": [],
        "verdict": "PASS",
        "_meta": {
            "draft_sha256": _sha(DRAFT_FILE),
            "data_file": str(data_path or ""),
            "data_sha256": _sha(data_path) if data_path else None,
            "generated_at": _now(),
        },
    }
    _write(OUTPUT_DIR / "数值_复核.json", json.dumps(payload, ensure_ascii=False, indent=2))


def _save_review_record(round_no: int, parsed: dict, gate: dict) -> None:
    record = {
        "round": round_no,
        "raw_file": f"评审_原文_R{round_no}.txt",
        "parsed": parsed,
        "gate": gate,
        "reviewer_family": REVIEWER_FAMILY,
        "provisional": REVIEWER_FAMILY == "qwen",
    }
    _write(OUTPUT_DIR / f"评审_记录_R{round_no}.json", json.dumps(record, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 入口
def _export_plot() -> None:
    """flow.plot() 写入临时目录并返回 html 路径；复制产物到 output/（html/js/css 三件套）。"""
    import shutil

    src = Path(PaperFlow().plot("flow_plot", show=False))
    for f in src.parent.glob(src.name + "*"):
        target = OUTPUT_DIR / ("flow_plot.html" if f.name == src.name else f.name)
        shutil.copyfile(f, target)
    print(f"[流程图] {OUTPUT_DIR / 'flow_plot.html'}")


def kickoff():
    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        _export_plot()
    except Exception as exc:  # 流程图失败不阻塞
        print(f"[提示] 流程图导出跳过：{exc}")
    flow = PaperFlow()
    flow.kickoff()


def plot():
    OUTPUT_DIR.mkdir(exist_ok=True)
    _export_plot()


if __name__ == "__main__":
    kickoff()
