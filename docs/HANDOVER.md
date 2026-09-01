# 交接说明（HANDOVER）

> 写给下一个工作区会话的执行者。读完本文件即可接手，无需翻旧会话记录。
> 交接日期：2026-09-01 ｜ 交接时仓库状态：M1 已完成并验证（commit `494f91d`）

## 项目一句话

把 ARIS 已验证的论文写作质量内核（验收契约、跨模型评审循环、致命一击、零上下文审计、确定性投稿门）跑在 CrewAI Flow 上，作为总项目产线的论文写作段——上游以文件契约衔接队友的前部进程（CrewAI Flow），本仓库是产线后部。

## 当前状态

- **M1 骨架直通：完成**。桩模式（`WRITING_FLOW_STUB=1`，不调 LLM）全链路验证通过：判道 → 规划 → 契约 → 写作 → R1（未达标走修复分支）→ 修订 → R2（台账闭合）→ 致命一击（WARN，代码映射）→ 数值复核（findings=0）→ 投稿门（五项全 pass，overall=provisional）→ 留档（后缀 `_致命一击未过` + 转人工标记）。两条路由分支、后缀合成、@persist 快照全部按设计工作。
- **M2 真实模式全流程首跑（2026-09-01，F7 崩溃后经状态快照恢复收尾）**：终态 overall=no，后缀 `_契约争议_致命一击未过_数值存疑_未通过门`——质量机制诚实拒掉了自己产线的成稿。**五项关键结论**：① R1 评审 JSON 字符串内嵌未转义双引号 → 解析失败，fail-closed 正确兜底但白烧一轮修订（其内容实为 6/almost 可直接达标）；隔离测试 5/5 ≠ 真实 Agent 环境，guardrail 由观察项升级为必做项；② 零上下文审计结论修正：审计员实际输出了「散文核对过程 + 尾部完整 JSON」（verdict=FAIL、8 条 findings，含写手新编造的超胞 12.5 Å、弛豫 300/100 步、DOS 窗口/展宽 0.1 eV、范德华半径和 2.67 Å）——首跑报 PARSE_ERROR 是合并桥误用严格 json.loads 丢弃了真证据，已改用 `_extract_json`（括号平衡）并恢复全部 findings；散文前缀仍属格式漂移，由 guardrail 反馈纠正；③ 投稿门两处 fail-open 实测修复：kill FAIL 原不封顶直通 accepted、`audit_parse_error` 未传入 snap 绕过一致性门；④ 致命一击机制真实威力：写手以"本质跃迁"立论（动力学概念），杀手精准判定 0K 静态证据无法支撑，5 原子点全 critical 未解 → FAIL，链条完整闭环；⑤ F7 崩溃因 claim_auditor 对象式 llm 配置漏改（只 grep 了字符串式），已修。恢复方式见坑 12。
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
2. ~~依次联调 plan → contract → write~~ **✅ 已完成（2026-09-01）**，三段真实模式全部跑通，产物在 output/（计划 9.5KB/16 论断全绑定槽位；契约 18 断言挑战者逐字核验 16 接受 2 需修订；初稿 7 节主题锚定成功）。**两个重要发现**：① 契约挑战者/写手原配置拿不到素材路径（FileReadTool 猜路径全失败）——已在 `crew_contract.jsonc`/`crew_write.jsonc` 注入 `SOURCES_MANIFEST` 输入修复，修复后挑战者实现逐字定位核验；② 写手在"模型验证"段编造了 2 个装饰性数值（-1.32 eV 色散消融对照、0.5–0.7 eV 文献典型值，素材中均不存在），且 `validate_report` 的差值/和+两位有效数字推导规则将它们放行（1.32≈1.42−0.09、0.5≈0.51、0.7≈0.51−(−0.18)）——prompt 纪律挡不住"合理化编造"，确定性白名单存在容差盲区。其余 20+ 核心数值全部精确照抄。待全流程首跑验证 R1 评审（数值表述纪律维度）能否抓住这 2 个值；收紧推导规则有误伤风险，暂记为待权衡项。
3. ~~改造点（M1 遗留）：R1 成立清单接线~~ **✅ 已完成（2026-09-01）**：`review_r1` 解析 R1 后即调 `review_gate.uphold_list()` 落盘成立清单（critical+major，代码裁决），桩/真实统一走此路径（原桩内置硬编码已删）；状态模型新增 `r1_upheld` 字段。桩模式回归全绿：清单在 R1 阶段生成、R2 台账按 id 对账闭合（开放 0/绕过 0）、后缀行为与 M1 基线一致。附带语义修正：旧桩把 minor 也写入清单，现按规范只留 critical+major。
4. ~~评审解析失败率压不住时，回退方案是给 review_crew 的 task 加 guardrail~~ **✅ 已完成（2026-09-01，升格为正式防线而非回退）**：新建 `tools/task_guardrails.py`（确定性校验：review_json / audit_json / arbiter_json，JSON 提取复用 review_gate 单一解析源），经 jsonc 任务字段 `{"python": "tools.task_guardrails.xxx"}` 接线到 review/audit/arbiter 三个任务，`guardrail_max_retries=1`；修正反馈针对两类实测漂移（字符串内未转义引号、散文前缀）。验证：内联重现的 R1 失败样本判 False、首跑审计实录恢复 8 条 findings、三个 Crew load_crew 挂载成功。重试耗尽仍失败由 main.py fail-closed 链兜底。附带修复：两处合并桥（kill/audit）从严格 json.loads 改为 `_extract_json`；投稿门新增 audit FAIL 阻断（第三处 fail-open：审计判 FAIL 而 kill 恰好 PASS 时原可直通 accepted）。
5. ~~M2 验收口径：双条件停机与 fail-closed 单测全绿；台账合成正确。~~ **✅ 已完成（2026-09-01）**：`tests/test_m2_acceptance.py`（零依赖自运行，兼容 pytest 收集）14/14 全绿——覆盖双条件停机（单高分不停车/非数值分）、解析 fail-closed（内引号/缺字段/缺文件/散文+尾部JSON）、verdict 计数表、台账（addressed/upheld_again/删句绕过/append-only）、投稿门（kill FAIL·audit FAIL·parse_error·BLOCKED·空verdict·WARN·STALE 七态）、后缀固定顺序、guardrail 三函数、合并桥（恢复 findings/垃圾/缺文件）。每个用例对应 M2 实测缺陷的回归固化。**M2 至此收口**；可选收尾验证：带全套防线二跑冲全绿（评审解析率已由 guardrail 加固，预期 R1 不再空转修订轮）。

## 待用户/团队裁决的决策点（不阻塞 M2，阻塞对应里程碑）

| # | 决策点 | 阻塞 | 默认状态 |
|---|--------|------|---------|
| 1 | 评审家族是否引入 DeepSeek（与「全千问合规」口径的权衡） | ~~M2 实际开跑~~ | ✅ 已定 deepseek-v4-pro（跨家族实测 5/5，2026-09-01）；降级开关在 .env |
| 2 | 上游契约六条与前部队友确认（交接目录/产物形态/HANDOFF 字段/触发方式/溯源互认/合并节奏） | M4 衔接验收 | **部分确认（2026-09-01）**：交接目录=data/upstream_handoff/、触发=同仓直写、上游产物=QE 计算结果（见下节勘察）；待定：HANDOFF 字段细则、溯源互认、QE 形态适配 |
| 3 | 引用三轴审计是否从 P1 提前（论文需带文献引用则提前） | 视情况 | 当前仅「待核清单」占位 |
| 4 | 仓库独立 vs 并入总项目仓做单仓多 Flow | 长期 | ✅ 已定：最终与前部 Flow 合并单仓多 Flow（2026-09-01）；合并前保持独立仓开发 |
| 5 | sf6 工具抽公共包 or 继续整文件拷贝 | 低 | 当前拷贝进 tools/；合并单仓时再议 |

### 上游契约确认进展与 QE 材料勘察（2026-09-01）

用户裁决：上游产物为 **QE（Quantum ESPRESSO）计算结果**，队友目录 `D:\QE计算结果\QE计算结果`；交接目录 `data/upstream_handoff/`；触发方式同仓直写；最终两段 Flow 合并单仓。勘察结论：

- 结构：`原训练集_94体系/`（94 个吸附体系 pwi+pwo，命名 `adsorption_{管型}_{材料}_{气体}_{位点}_{编号}`，Pt/PtPd/PtN 掺杂 × H₂S/SO₂/SOF₂/SO₂F₂/SF₆ × top/bridge/hollow × 6,6/8,0 手性）+ `convergence_test/`（9 个 SCF）+ `convergence_results.csv` + `README.md`（参数表与 pwo 读取方法：总能 `! total energy =` 行、E_ads=E(复合物)−E(基底)−E(气体)、1 Ry=13.6057 eV）。备注：原设计 133 体系，余 39 个在算；Au/Rh 外推集 14 结构在算。**物理体系与 M2 联调用的 VASP/SWNT-OH 素材不同**。
- 判道演练（临时目录实测）：README.md 被 `_form_of` 误判 draft → **refine 模式**（错误：会把归档说明当初稿精修）；CSV 与子目录不进清单（glob 仅 *.md）；HANDOFF 的 state.id 溯源字段链路正常。
- **M3 工作项（QE 形态适配）**：① ~~新增确定性提取工具 `tools/qe_extract.py`~~ **✅ 已完成（2026-09-01）**：终态能量取最后一个 `!` 行、JOB DONE 完成性 fail-closed、重复副本确定性取舍（mtime 最新且收敛，能量不一致记 flag）、位点稳定性 ΔE 代码推导、E_ads 缺参考能量显式 DATA_NEEDED；单测 5/5（`tests/test_qe_extract.py`），真实 94 体系烟雾验证 94/94 全提取（0 异常）；② ~~`prepare_inputs` 形态扩展~~ **✅ 已完成（2026-09-01）**：新增"原始计算归档"判道（目录含 `adsorption_*/…pwo` → standalone，优先级最高），自动触发 qe_extract 生成 `output/QE_数据表.md` 入清单（role=data，审计白名单源直指生成表），README/CSV 以 readme/aux 角色入清单，raw_calc 目录条目留档；缺 HANDOFF 降级仍可跑。单测 5/5（`tests/test_prepare_inputs.py`，含原有三分支回归）；真实 94 体系经目录联接端到端演练全通（mode=standalone、state.id 溯源、白名单表 94 体系全量、README 误判 refine 问题终结）；③ ~~`validate_report.build_whitelist` 适配 QE 表格格式与单位~~ **✅ 已完成（2026-09-01）**：单元格自带单位按格内单位归类（通用规则，修复 QE 换算列 eV 值错入 Ry 桶）；白名单全无的单位由静默跳过改为 `[白名单外·单位缺失]` 报警（堵 fail-open：编造 eV 值曾可绕过）；新增 Ry↔eV 互推核对（口径 13.6057 与提取器一致，容差 max(0.005, |v|·1e-6)）。单测 5/5（`tests/test_validate_report_qe.py`，含 VASP 表回归），全量回归 24/24（M2 14 + qe 5 + prepare 5）；④ 课题锚定需切换（Pt 系掺杂 CNT，非 SWNT-OH）。未动工。

## 已知坑（踩过的，别再踩）

1. `@persist` 因带默认参数必须写 `@persist()` 调用形式；裸 `@persist` 报 TypeError。
2. `flow.plot()` 实际写**临时目录**并返回路径（filename 参数只是临时目录内名字），需复制回 output/，且传 `show=False` 防止拉起浏览器——`main.py::_export_plot` 已处理。
3. crewai 启动时会写 `~/.config/crewai`，受限沙箱下被拦截；`main.py` 顶部已做 `.appdata/` 重定向（沿用 sf6 方案），**这段 patch 必须在首次 import crewai 之前执行**，调整代码时别挪位置。
4. Task 占位符只识别 ASCII 标识符，中文 key 不替换（inputs 键一律英文，值可中文）。
5. 路由标签不得与方法名同名（flow_definition 自引用校验）；当前标签 write / write_flagged / revise / final_audits 均合规，新增方法时保持此约束。
6. `restore_from_state_id` 未命中时**静默回退不报错**；恢复入口应先显式查询状态库（M4 实现时处理）。
7. Windows 控制台 GBK：main.py 已强制 stdout/stderr UTF-8；新增脚本同样处理。
8. md2pdf.py 的 pandoc/xelatex 路径硬编码 `D:\pandoc\...`、`D:\MiKTeX\...`，本机路径不符则 PDF 自动跳过（`.env` 的 `WRITING_FLOW_PDF=1` 默认注释）。
9. crewai 1.15.10 原生 provider 有型号白名单：`dashscope/` 前缀只认 `qwen*` 型号（`dashscope/deepseek-*` 一律初始化失败，且本 venv 未装 litellm 回退包，共享 venv 勿擅自加装）；DeepSeek 系必须走原生 `deepseek/` 前缀，它读 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL`，后者指到百炼兼容模式即复用现有 key。另注意原生 dashscope 默认端点是国际站 `dashscope-intl`，国内 key 必须显式 `DASHSCOPE_BASE_URL`（.env 已设）。
10. jsonc Crew 里凡需读素材文件的任务，必须把 `SOURCES_MANIFEST` 作为输入注入并在 description 里指明"按清单 path 字段的绝对路径读取"——只给文件名时 agent 会自己猜路径（output/、/home/user/ 等），全部失败后还会把"文件不存在"当结论写进产物（M2-2 实测：契约挑战者曾因此把 14 条断言全判"证据不可得"）。plan 段传绝对路径所以没踩过。
11. 工具层教训（两次踩中）：对同一文件的多处编辑绝不可并行发起，后写会基于旧版本覆盖前写（main.py 接线曾被覆盖丢失、HANDOVER 坑 #9 曾被覆盖丢失）——同文件多改必须串行。
12. crewai 1.15 断点续跑三坑（M2 首跑实测）：① `kickoff()` 不带参数会清空 `_completed_methods` 并从头重跑（要保留须 `kickoff(inputs={"id": uuid})` 走 is_restoring 分支）；② 即便 `reload(execution_data)` + 带 id kickoff，**监听已完成方法的尾部监听器不会触发**（claim_audit 静默跳过、流程显示"完成"）——官方 replay 机制无法直接用于尾部补跑；③ 可靠恢复配方：从 `flow_states.db` 按时间窗取崩溃前最后快照 → `flow._state = ArisPaperState.model_validate(state)` → **直接顺序调用剩余方法**（同一份代码，不经 DAG）；查询务必带时间窗过滤，被中止的重跑会写入污染行。M4 恢复入口照此实现。

## 环境与依赖

- Python 3.10-3.13 / Windows；复用 `C:\Users\王雨露\Desktop\挑战杯\.venv`（crewai==1.15.10 + crewai-tools，pyproject 已锁定同版本）。
- 若需独立环境：仓库根目录 `crewai install` 后 `crewai run`（pyproject `[tool.crewai] type="flow"` 已配）。
- 模型矩阵：执行 qwen-plus / 评审 deepseek-v4-pro（跨家族，经百炼兼容模式）/ 裁决 qwen3.8-max 零温度；配置全在 `agents/*.jsonc`，改模型不碰代码。

## 相关资料索引

- 设计文档：`docs/mvp-product-plan/`、`docs/tech-design/`（本仓库内，双格式）
- 机制源头：ARIS 仓库（`挑战杯\crew优化\Auto-claude-code-research-in-sleep`），技能定义见其 `skills/`
- 资产来源：sf6_writing_crew（`挑战杯\sf6_writing_crew`），本仓库 tools/ 回收了 validate_report / make_charts / md2pdf
- CrewAI 中文文档库：`挑战杯\crewai-docs`（v1.15.10）
