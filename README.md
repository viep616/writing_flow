# writing_flow · ARIS 论文写作流程的 CrewAI Flow 实现

> 设计依据：`docs/mvp-product-plan/`（MVP 产品方案 v1.1）与 `docs/tech-design/`（技术方案 v1.1），各有 HTML（含交互演示）与 Markdown 双版本。
> 新会话接手先读 `docs/HANDOVER.md`（交接说明：当前状态 / M2 计划 / 待决事项 / 已知坑）。
> 定位：总项目产线的论文写作段——上游承接队友基于 CrewAI Flow 的前部进程（文件交接），产出一篇经过跨模型评审与多层确定性审计、留痕完整的论文成稿。

## 结构

```
writing_flow/
├── src/writing_flow/main.py     # PaperFlow(Flow[ArisPaperState]) 全骨架（@persist 持久化）
├── crew_plan.jsonc … crew_audit.jsonc   # 7 个 Crew 声明（根目录平铺，队友改 prompt 不碰代码）
├── agents/*.jsonc               # 9 个角色（执行 qwen-plus / 评审 deepseek-v3 / 裁决零温度）
├── tools/
│   ├── prepare_inputs.py        # F1 判道 + SOURCES_MANIFEST（SHA256 指纹）
│   ├── review_gate.py           # 双条件停机状态机（fail-closed）
│   ├── verdict_map.py           # 致命一击 verdict 计数表映射（代码裁决，不信模型自评）
│   ├── ledger.py                # 义务台账（append-only，删句绕过检测）
│   ├── verify_gates.py          # 投稿门五项检查 → overall 三态
│   ├── qe_extract.py            # QE pwo → 白名单数据表（M3，确定性提取零 LLM）
│   ├── task_guardrails.py       # Crew/审计任务 guardrail（jsonc {"python": ...} 接线）
│   ├── resume_flow.py           # 断点恢复入口（--list 查库 / --uuid 恢复，M4）
│   ├── eval_run.py              # 回归基线（桩模式 N 次确定性指纹 → eval/回归基线.json）
│   ├── qe_charts.py             # QE 数据确定性配图（4 张，finalize 自动插入）
│   ├── archive.py               # 时间戳留档 + 后缀合成
│   ├── validate_report.py       # ↓ 以下三个回收自 sf6 初探
│   ├── make_charts.py
│   └── md2pdf.py
├── skills/qe-analysis-report/   # 写作技能（qe-analysis-report：输出规范/分析素材规范/图文结合，挂载 4 个写作/评审/审计 agent）
├── data/                        # 输入三入口：NARRATIVE_REPORT / vasp_results / upstream_handoff
└── output/                      # 全部工件 + 时间戳留档（git 不入库）
```

## 运行

```powershell
# 桩模式（M1 验收：不调 LLM，确定性桩数据驱动全链路）
$env:WRITING_FLOW_STUB='1'; & "..\.venv\Scripts\python.exe" src\writing_flow\main.py

# 真实模式（M2 起联调；需 .env 配置 DASHSCOPE_API_KEY）
& "..\.venv\Scripts\python.exe" src\writing_flow\main.py

# 流程图（答辩物料）
& "..\.venv\Scripts\python.exe" -c "from writing_flow.main import plot; plot()"   # 需已 crewai install
```

运行约定：复用上级目录团队 `.venv`（crewai==1.15.10 锁定，与总项目前部 Flow 同版本）。若需独立环境：`crewai install` 后 `crewai run`。

## 输入入口（程序自动判道，无需声明）

| 入口 | 路径 | 形态 → 模式 |
|------|------|------------|
| 上游·原始计算归档 | `data/upstream_handoff/`（含 `adsorption_*/…pwo`） | QE 归档→standalone，`qe_extract` 自动提取白名单表（M3） |
| 上游交接 | `data/upstream_handoff/` + HANDOFF.md | 叙事/数据表→standalone；已成初稿→refine |
| 独立·叙事 | `data/NARRATIVE_REPORT.md` | standalone |
| 独立·数据 | `data/vasp_results.md`（sf6 七节模板，表中数值即白名单） | standalone |
| 已有初稿 | `data/` 下其他 md | refine（跳过写作段，直接进改进循环） |

## 产物与后缀语义

固定名工件（最新版）+ 时间戳留档（永不覆盖）：`论文_成稿_{stamp}{后缀}.md`、`验收_契约`、`评审_记录_R1/R2`、`致命一击`、`数值_复核`、`义务_台账`、`RUN_STATE_{stamp}.json`。

后缀按固定顺序合成：`_契约争议 → _评审未达标 → _致命一击未过 → _数值存疑 → _未通过门 → _交接不完整`；无后缀即全绿（投稿门 overall=accepted）。

## 质量机制（谁说了算）

- 停不停机：`review_gate.py` 双条件（score>=6 且 verdict∈{ready,almost}），模型无权判定
- 致命一击 verdict：`verdict_map.py` 计数表（critical 未决→FAIL；未决为 0 才可能 PASS）
- 数值事实：白名单对账（validate_report）+ 零上下文审计（只读成稿与数据文件两份材料）
- 评审独立性：执行千问 / 评审 DeepSeek 跨家族；每轮重建全新 Crew 实例（新鲜线程协议）
- 全流程留痕：评审原文逐字落盘；台账 append-only；工件 _meta 带 SHA256 指纹

## 状态

- **M1 已完成**：骨架直通（判道→规划→契约→写作→两轮循环→致命一击→审计→投稿门→留档），桩模式全链路验证通过
- **M2 已完成（2026-09-01）**：评审模型迁移 v4-pro（稳定性 5/5）、R1 成立清单接线、写作段三段联调、真实模式全流程首跑（终态 overall=no，后缀全链留痕）、guardrail 兜底上线（确定性校验+一次重试）、验收单测 14/14 全绿（`tests/`，零依赖自运行：`& ..\.venv\Scripts\python.exe tests\test_m2_acceptance.py`）。首跑共产出 12 项缺陷修复（含投稿门三处 fail-open），全部固化为回归用例。可选收尾：二跑冲全绿
- **M5 技能集成与图文结合（2026-09-01）**：写作技能 qe-analysis-report 接入 skills/（jsonc "skills": ["./skills"] 挂载 section_writer/reviser/cross_reviewer/claim_auditor，Flow 拓扑零改动）；qe_extract 新增 §5 分析素材（位点排序/位次含并列/频次/组数占比/收敛性汇总，代码生成禁止手算）；md2pdf.insert_figures 图文结合双通道（<!-- FIG:xxx --> 锚点 + 正文"图 N"引用锚定）；写作任务新增聚合统计纪律与配图纪律。全量回归 30/30。
- **决策点待裁**：评审家族合规（若纯千问，设 WRITING_FLOW_REVIEWER_FAMILY=qwen 降级，结论标 provisional）；上游契约六条与队友确认

## 工程约定

全 UTF-8；`.env` 管密钥；jsonc 配置层与代码层分离；crewai 运行数据重定向至项目内 `.appdata/`（Windows 受限环境实测必需）；大改前打 tag，master 保持可用版本。
