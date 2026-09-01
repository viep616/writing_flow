# 交接说明（HANDOVER）

> 写给下一个工作区会话的执行者。读完本文件即可接手，无需翻旧会话记录。
> 交接日期：2026-09-01 ｜ 交接时仓库状态：M1 已完成并验证（commit `494f91d`）

## 项目一句话

把 ARIS 已验证的论文写作质量内核（验收契约、跨模型评审循环、致命一击、零上下文审计、确定性投稿门）跑在 CrewAI Flow 上，作为总项目产线的论文写作段——上游以文件契约衔接队友的前部进程（CrewAI Flow），本仓库是产线后部。

## 当前状态

- **M1 骨架直通：完成**。桩模式（`WRITING_FLOW_STUB=1`，不调 LLM）全链路验证通过：判道 → 规划 → 契约 → 写作 → R1（未达标走修复分支）→ 修订 → R2（台账闭合）→ 致命一击（WARN，代码映射）→ 数值复核（findings=0）→ 投稿门（五项全 pass，overall=provisional）→ 留档（后缀 `_致命一击未过` + 转人工标记）。两条路由分支、后缀合成、@persist 快照全部按设计工作。
- **`.env` 已配好**：DASHSCOPE_API_KEY 复制自 sf6_writing_crew（团队同一 key），BASE_URL 已设。**2026-09-01 更新**：百炼公告全系旧 DeepSeek（v3/v3.1/v3.2/r1）2026-10-10 下架，评审系三角色已迁移 `deepseek/deepseek-v4-pro`，经 crewai 原生 `deepseek/` 前缀 + `.env` 的 `DEEPSEEK_API_KEY`（同 DASHSCOPE key）与 `DEEPSEEK_BASE_URL`（指向百炼兼容模式）路由；连通性与评审 JSON 稳定性已实测（见下）。
- git 两个提交：`ea0df6a`（骨架）→ `494f91d`（plot 导出修复）。master 即可用版本，大改前打 tag。

## 怎么跑

```powershell
# 仓库根目录；复用上级团队 venv（crewai==1.15.10 锁定）
$env:WRITING_FLOW_STUB='1'; & "..\.venv\Scripts\python.exe" src\writing_flow\main.py   # 桩模式
& "..\.venv\Scripts\python.exe" src\writing_flow\main.py                                # 真实模式（M2 起）
```

结构、输入三入口、产物与后缀语义见仓库 README.md；设计全貌见 `docs/mvp-product-plan/`（产品方案）与 `docs/tech-design/`（技术方案），各有 HTML（含交互演示）与 Markdown 双版本。

## 下一步：M2 真实模式联调（建议顺序）

1. ~~先单段验证评审 Crew 的 JSON 稳定性~~ **✅ 已完成（2026-09-01）**：用与 Flow 同层的 `crewai.LLM` 直调（提示词镜像 `crew_review.jsonc`，评审对象为桩初稿）。结果：`deepseek/deepseek-v4-pro` 连通 4.1s，评审 5/5 解析成功（score 1-2、verdict 一致 not_ready、22-45s/次，对桩稿打分比 qwen 更严）；降级路径 `dashscope/qwen-plus` 同样 5/5（score 3-4、not_ready、约 11s/次）。停机门 `review_gate.parse_file` 全部吃得下，无需 guardrail 前置。测试脚本未入库（一次性验证），结论以本条为准。
2. 依次联调 plan → contract → write（写作段的数值纪律条款是否真的挡住编造，用 `data/vasp_results.md` 模拟数据对照）。
3. **改造点（M1 遗留）**：R1 成立清单目前由桩内置生成；真实模式下应改为 `review_r1` 阶段解析 R1 后调用 `review_gate.uphold_list()` 生成（函数已写好，在 `tools/review_gate.py`，接线即可）。
4. 评审解析失败率压不住时，回退方案是给 review_crew 的 task 加 guardrail（结构化校验 + 一次重试），CrewAI Task 层现成能力。
5. M2 验收口径：双条件停机与 fail-closed 单测全绿；台账合成正确。

## 待用户/团队裁决的决策点（不阻塞 M2，阻塞对应里程碑）

| # | 决策点 | 阻塞 | 默认状态 |
|---|--------|------|---------|
| 1 | 评审家族是否引入 DeepSeek（与「全千问合规」口径的权衡） | M2 实际开跑 | 默认已配 deepseek；降级开关在 .env |
| 2 | 上游契约六条与前部队友确认（交接目录/产物形态/HANDOFF 字段/触发方式/溯源互认/合并节奏） | M4 衔接验收 | 清单见产品方案第 7 节 |
| 3 | 引用三轴审计是否从 P1 提前（论文需带文献引用则提前） | 视情况 | 当前仅「待核清单」占位 |
| 4 | 仓库独立 vs 并入总项目仓做单仓多 Flow | 长期 | 当前独立仓 |
| 5 | sf6 工具抽公共包 or 继续整文件拷贝 | 低 | 当前拷贝进 tools/ |

## 已知坑（踩过的，别再踩）

1. `@persist` 因带默认参数必须写 `@persist()` 调用形式；裸 `@persist` 报 TypeError。
2. `flow.plot()` 实际写**临时目录**并返回路径（filename 参数只是临时目录内名字），需复制回 output/，且传 `show=False` 防止拉起浏览器——`main.py::_export_plot` 已处理。
3. crewai 启动时会写 `~/.config/crewai`，受限沙箱下被拦截；`main.py` 顶部已做 `.appdata/` 重定向（沿用 sf6 方案），**这段 patch 必须在首次 import crewai 之前执行**，调整代码时别挪位置。
4. Task 占位符只识别 ASCII 标识符，中文 key 不替换（inputs 键一律英文，值可中文）。
5. 路由标签不得与方法名同名（flow_definition 自引用校验）；当前标签 write / write_flagged / revise / final_audits 均合规，新增方法时保持此约束。
6. `restore_from_state_id` 未命中时**静默回退不报错**；恢复入口应先显式查询状态库（M4 实现时处理）。
7. Windows 控制台 GBK：main.py 已强制 stdout/stderr UTF-8；新增脚本同样处理。
8. md2pdf.py 的 pandoc/xelatex 路径硬编码 `D:\pandoc\...`、`D:\MiKTeX\...`，本机路径不符则 PDF 自动跳过（`.env` 的 `WRITING_FLOW_PDF=1` 默认注释）。

## 环境与依赖

- Python 3.10-3.13 / Windows；复用 `C:\Users\王雨露\Desktop\挑战杯\.venv`（crewai==1.15.10 + crewai-tools，pyproject 已锁定同版本）。
- 若需独立环境：仓库根目录 `crewai install` 后 `crewai run`（pyproject `[tool.crewai] type="flow"` 已配）。
- 模型矩阵：执行 qwen-plus / 评审 deepseek-v4-pro（跨家族，经百炼兼容模式）/ 裁决 qwen3.8-max 零温度；配置全在 `agents/*.jsonc`，改模型不碰代码。

## 相关资料索引

- 设计文档：`docs/mvp-product-plan/`、`docs/tech-design/`（本仓库内，双格式）
- 机制源头：ARIS 仓库（`挑战杯\crew优化\Auto-claude-code-research-in-sleep`），技能定义见其 `skills/`
- 资产来源：sf6_writing_crew（`挑战杯\sf6_writing_crew`），本仓库 tools/ 回收了 validate_report / make_charts / md2pdf
- CrewAI 中文文档库：`挑战杯\crewai-docs`（v1.15.10）
