# 交接说明（HANDOVER）

> 写给下一个工作区会话的执行者。读完本文件即可接手，无需翻旧会话记录。
> 交接日期：2026-09-01 ｜ 交接时仓库状态：M1 已完成并验证（commit `494f91d`）

## 项目一句话

把 ARIS 已验证的论文写作质量内核（验收契约、跨模型评审循环、致命一击、零上下文审计、确定性投稿门）跑在 CrewAI Flow 上，作为总项目产线的论文写作段——上游以文件契约衔接队友的前部进程（CrewAI Flow），本仓库是产线后部。

## 当前状态

- **M1 骨架直通：完成**。桩模式（`WRITING_FLOW_STUB=1`，不调 LLM）全链路验证通过：判道 → 规划 → 契约 → 写作 → R1（未达标走修复分支）→ 修订 → R2（台账闭合）→ 致命一击（WARN，代码映射）→ 数值复核（findings=0）→ 投稿门（五项全 pass，overall=provisional）→ 留档（后缀 `_致命一击未过` + 转人工标记）。两条路由分支、后缀合成、@persist 快照全部按设计工作。
- **M2 真实模式全流程首跑（2026-09-01，F7 崩溃后经状态快照恢复收尾）**：终态 overall=no，后缀 `_契约争议_致命一击未过_数值存疑_未通过门`——质量机制诚实拒掉了自己产线的成稿。**五项关键结论**：① R1 评审 JSON 字符串内嵌未转义双引号 → 解析失败，fail-closed 正确兜底但白烧一轮修订（其内容实为 6/almost 可直接达标）；隔离测试 5/5 ≠ 真实 Agent 环境，guardrail 由观察项升级为必做项；② 零上下文审计结论修正：审计员实际输出了「散文核对过程 + 尾部完整 JSON」（verdict=FAIL、8 条 findings，含写手新编造的超胞 12.5 Å、弛豫 300/100 步、DOS 窗口/展宽 0.1 eV、范德华半径和 2.67 Å）——首跑报 PARSE_ERROR 是合并桥误用严格 json.loads 丢弃了真证据，已改用 `_extract_json`（括号平衡）并恢复全部 findings；散文前缀仍属格式漂移，由 guardrail 反馈纠正；③ 投稿门两处 fail-open 实测修复：kill FAIL 原不封顶直通 accepted、`audit_parse_error` 未传入 snap 绕过一致性门；④ 致命一击机制真实威力：写手以"本质跃迁"立论（动力学概念），杀手精准判定 0K 静态证据无法支撑，5 原子点全 critical 未解 → FAIL，链条完整闭环；⑤ F7 崩溃因 claim_auditor 对象式 llm 配置漏改（只 grep 了字符串式），已修。恢复方式见坑 12。
- **M3 QE 素材全流程首跑（2026-09-01 18:06-18:42，tag m3 后）**：36 分钟 11 阶段全绿无崩溃。终态 overall=no，后缀 `_评审未达标_致命一击未过_数值存疑_未通过门`——每个标记均有真实证据。**亮点**：① 契约首次 accepted（15 断言全部逐字可判定）；② R1/R2 评审 JSON 双双解析成功（guardrail 时代首验）；③ 台账闭合，R1 四条弱点 R2 逐条核验 addressed；④ **三层防线交叉验证**：写手/修订稿把"最优位点"张冠李戴（027/065/047/052/021 等，R2 与零上下文审计各自独立抓到同批 10+ 处配置错配），审计 FAIL 12 findings + kill FAIL 4 未解 + R2 未达标（4 分）共同支撑拒稿——无一个事实错误溜到 accepted；⑤ 修订者专业回查原始能量核实 15.13 eV 异常构型。**暴露的系统性弱点**：执行侧 qwen-plus 在"查表式"结论（位点排序 vs 体系编号）上错误率高——后续改进方向：位点结论类内容考虑由代码预生成约束（qe_extract 位点表直接作写作输入），不依赖 LLM 查表；另真实模式修订前初稿无时间戳留档（桩模式有），留痕小缺口已在本日 M4 补齐。
- **M4 衔接收尾（2026-09-01 晚）**：产品方案验收清单 7 项中 6 项达成——#3 交接演练（超额：真实 QE 接入）、#4 评审独立性、#5 防刷四件套（M2/M3 实证）；本日新增：**#6 断点恢复 3/3**（`tools/resume_flow.py` 固化坑 12 配方：--list 查库 / --uuid 恢复、坑 6 显式报错不静默、R1 分支由状态重放不重跑 LLM；桩模式三崩溃点演练全过，已完成工件指纹不变）、**#7 回归基线**（`tools/eval_run.py --runs 3` → `eval/回归基线.json` 入库；稳定指纹剥离 generated_at/data_sha256 等易变链，3 次指纹一致确定性 ✅）、**#2 精修机制冒烟**（`WRITING_FLOW_DATA_DIR` 覆盖支持 + 历史终稿 refine 判道/写作跳过/循环留档全通；附带修正"交接不完整"标记仅对上游来源生效）。剩余：#1 全流程全绿——accepted 路径已有单测覆盖，真实全绿待数据补齐（39 体系 + E_ads 参考能量），不造假装绿；真实模式精修实测（约 20 分钟 LLM）待择机。
- **M5 技能集成与图文结合（2026-09-01）**：① 写作技能 qe-analysis-report（Codex 侧蒸馏的输出规范）接入 skills/ 并以 "skills": ["./skills"] 挂载 section_writer/reviser/cross_reviewer/claim_auditor（纯配置层，Flow 零改动；agent jsonc 的 skills 字段经 crew_loader 透传已实测）；SKILL.md 附 Flow 使用说明（数据表以 qe_extract 产物为准，scripts 仅独立环境用）。② qe_extract 新增 §5 分析素材（5.1 位点排序含并列位次 / 5.2 组内能差+位次 / 5.3 最优位点频次 / 5.4 组数占比 / 5.5 收敛性汇总，全部代码生成）——堵"聚合数错/图注-表格不符/百分比虚构"类审计发现；并列阈值 <1e-4 eV；convergence CSV 查找兼容体系根目录与其父目录。③ md2pdf.insert_figures 图文结合双通道：<!-- FIG:stem --> 锚点 + 正文"图 N："引用锚定（跳过 HTML 注释），无引用回退文末；真实初稿 4/4 就近插入（图4→§3、图2→4.1、图1→4.2、图3→4.5），演示 PDF 6 页（对照 v3 17 页）。④ 提示词新增聚合统计纪律与配图纪律（crew_write）。⑤ 真实模式两轮验证：技能生效（初稿四步法/口径声明/DATA_NEEDED），质量门两轮均诚实拒稿（kill FAIL 5 未解 + 审计 6~8 findings）；第二轮图回退文末因修订者删除 FIG 注释（见坑 16）。全量回归 30/30。

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
- **M3 工作项（QE 形态适配）**：① ~~新增确定性提取工具 `tools/qe_extract.py`~~ **✅ 已完成（2026-09-01）**：终态能量取最后一个 `!` 行、JOB DONE 完成性 fail-closed、重复副本确定性取舍（mtime 最新且收敛，能量不一致记 flag）、位点稳定性 ΔE 代码推导、E_ads 缺参考能量显式 DATA_NEEDED；单测 5/5（`tests/test_qe_extract.py`），真实 94 体系烟雾验证 94/94 全提取（0 异常）；② ~~`prepare_inputs` 形态扩展~~ **✅ 已完成（2026-09-01）**：新增"原始计算归档"判道（目录含 `adsorption_*/…pwo` → standalone，优先级最高），自动触发 qe_extract 生成 `output/QE_数据表.md` 入清单（role=data，审计白名单源直指生成表），README/CSV 以 readme/aux 角色入清单，raw_calc 目录条目留档；缺 HANDOFF 降级仍可跑。单测 5/5（`tests/test_prepare_inputs.py`，含原有三分支回归）；真实 94 体系经目录联接端到端演练全通（mode=standalone、state.id 溯源、白名单表 94 体系全量、README 误判 refine 问题终结）；③ ~~`validate_report.build_whitelist` 适配 QE 表格格式与单位~~ **✅ 已完成（2026-09-01）**：单元格自带单位按格内单位归类（通用规则，修复 QE 换算列 eV 值错入 Ry 桶）；白名单全无的单位由静默跳过改为 `[白名单外·单位缺失]` 报警（堵 fail-open：编造 eV 值曾可绕过）；新增 Ry↔eV 互推核对（口径 13.6057 与提取器一致，容差 max(0.005, |v|·1e-6)）。单测 5/5（`tests/test_validate_report_qe.py`，含 VASP 表回归），全量回归 24/24（M2 14 + qe 5 + prepare 5）；④ ~~课题锚定切换~~ **✅ 已完成（2026-09-01，M3 收口）**：排查确认全部 jsonc 仅 crew_audit 一处硬编码默认 DATA_PATH（已清空，main.py 本就显式传参）；锚定机制化——HANDOFF「课题锚定」行经 `topic_anchor_from_handoff` → manifest.topic_anchor → 状态 topic_anchor → crew_plan 的 {TOPIC_ANCHOR} 输入（上游可控，空则素材自提炼）；规划提示词加 QE 体系命名解读与"槽位必须绑定真实条目、禁通配符"硬约束。**QE 素材已正式接入 `data/upstream_handoff/`**（94 体系目录联接 + README/CSV 复制 + HANDOFF 含锚定；.gitignore 屏蔽素材仅留模板）。真实运行验证：判道 raw_calc ✓ 溯源 qe-20260831-archive ✓，规划段 11 论断全绑定真实体系编号与 ΔE 值（含一处论断自我收窄的科研级修正），课题锚定与 HANDOFF 指定一致，E_ads 缺口诚实 DATA_NEEDED。全量回归 30/30。

## 已知坑（踩过的，别再踩）

1. `@persist` 因带默认参数必须写 `@persist()` 调用形式；裸 `@persist` 报 TypeError。
2. `flow.plot()` 实际写**临时目录**并返回路径（filename 参数只是临时目录内名字），需复制回 output/，且传 `show=False` 防止拉起浏览器——`main.py::_export_plot` 已处理。
3. crewai 启动时会写 `~/.config/crewai`，受限沙箱下被拦截；`main.py` 顶部已做 `.appdata/` 重定向（沿用 sf6 方案），**这段 patch 必须在首次 import crewai 之前执行**，调整代码时别挪位置。
4. Task 占位符只识别 ASCII 标识符，中文 key 不替换（inputs 键一律英文，值可中文）。
5. 路由标签不得与方法名同名（flow_definition 自引用校验）；当前标签 write / write_flagged / revise / final_audits 均合规，新增方法时保持此约束。
6. `restore_from_state_id` 未命中时**静默回退不报错**；恢复入口应先显式查询状态库（M4 实现时处理）。
7. Windows 控制台 GBK：main.py 已强制 stdout/stderr UTF-8；新增脚本同样处理。
8. md2pdf.py 的 pandoc/xelatex 路径硬编码 `D:\pandoc\pandoc-3.6.4\pandoc.exe`、`D:\MiKTeX\miktex\bin\x64\xelatex.exe`。**2026-09-01 核实修正**：本机两路径分毫不差存在、SimHei 字体在位，前会话"本机路径不符"的假设过时；`WRITING_FLOW_PDF=1` 已在 .env 启用。但 **TRAE 沙箱会拦截 xelatex 启动**（0xC0000135：MiKTeX 动态 DLL 加载被断；pandoc 静态二进制可过、授权执行也一样）——在 agent 沙箱内跑不出 PDF，属环境限制而非代码问题；在用户自己的终端跑流程或补转命令（`& ..\.venv\Scripts\python.exe tools\md2pdf.py output\论文_成稿_xxx.md`）即可正常生成。
9. crewai 1.15.10 原生 provider 有型号白名单：`dashscope/` 前缀只认 `qwen*` 型号（`dashscope/deepseek-*` 一律初始化失败，且本 venv 未装 litellm 回退包，共享 venv 勿擅自加装）；DeepSeek 系必须走原生 `deepseek/` 前缀，它读 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL`，后者指到百炼兼容模式即复用现有 key。另注意原生 dashscope 默认端点是国际站 `dashscope-intl`，国内 key 必须显式 `DASHSCOPE_BASE_URL`（.env 已设）。
10. jsonc Crew 里凡需读素材文件的任务，必须把 `SOURCES_MANIFEST` 作为输入注入并在 description 里指明"按清单 path 字段的绝对路径读取"——只给文件名时 agent 会自己猜路径（output/、/home/user/ 等），全部失败后还会把"文件不存在"当结论写进产物（M2-2 实测：契约挑战者曾因此把 14 条断言全判"证据不可得"）。plan 段传绝对路径所以没踩过。
11. 工具层教训（两次踩中）：对同一文件的多处编辑绝不可并行发起，后写会基于旧版本覆盖前写（main.py 接线曾被覆盖丢失、HANDOVER 坑 #9 曾被覆盖丢失）——同文件多改必须串行。
12. crewai 1.15 断点续跑三坑（M2 首跑实测）：① `kickoff()` 不带参数会清空 `_completed_methods` 并从头重跑（要保留须 `kickoff(inputs={"id": uuid})` 走 is_restoring 分支）；② 即便 `reload(execution_data)` + 带 id kickoff，**监听已完成方法的尾部监听器不会触发**（claim_audit 静默跳过、流程显示"完成"）——官方 replay 机制无法直接用于尾部补跑；③ 可靠恢复配方：从 `flow_states.db` 按时间窗取崩溃前最后快照 → `flow._state = ArisPaperState.model_validate(state)` → **直接顺序调用剩余方法**（同一份代码，不经 DAG）；查询务必带时间窗过滤，被中止的重跑会写入污染行。M4 恢复入口照此实现。
13. 沙箱演练陷阱（M3-④ 实测两次）：把素材放 %TEMP% 做联调演练时，agent 的 FileReadTool 读不到清单指向的文件（沙箱仅放行工作区）→ 规划师读不到白名单表只能臆造体系名（5,5/7,7/F₂ 等不存在物），且清理时联接目录的 rmdir/unlink 也被拦。**结论：联调/演练素材必须放在工作区内**（正式契约本就是同仓直写 data/upstream_handoff/，gitignore 已屏蔽）；Windows 目录联接（New-Item -ItemType Junction）免拷贝免管理员，gitignore 的目录不会被 git 遍历。另：素材清单里绝不能放"原始输出目录"条目——94×4.5MB pwo 会诱导 agent 逐个去读，上下文撑爆后表格内容被摘要丢失（已改为 manifest 顶层 raw_calc_root 留档字段）。
14. crewai Flow 方法不可事后替换（M4 断点演练实测）：monkeypatch `PaperFlow.某方法` 后，监听图里对应的边会消失（补丁函数没有 @listen 装饰器），流程会**静默"完成"并跳过该段**，比崩溃更危险。注入崩溃/桩应替换方法内部调用的底层函数（如 `_stub_plan`），保持方法装饰器不动。另观察到：桩高速路径下 @persist 快照可能滞后于 _mark（演练 1 断点落在 load_inputs），恢复保证边界＝最后快照点，其后幂等重跑无害；真实模式方法分钟级，快照逐方法落（M2 首跑已证）。
15. PDF 链路四坑（M4 用户实测反馈修复，2026-09-01 晚）：① **公式定界**——写手爱用 `\[...\]`/`\(...\)`，pandoc 只认 `$...$`/`$$...$$` → preprocess 定界规范化；② **修订说明泄漏**——修订者把说明放开头且 `<!-- -->` 只包标题行 → preprocess 整块剪下移文末，承载容器用 fenced div（`::: {.revision-notes}` + CSS display:none）——**pandoc 会把含列表的多行 HTML 注释拆进正文渲染**，别用注释承载；③ **Edge 无头对中文长文件名的 file URL/输出路径组合渲染异常**（产出残缺 PDF）→ browser 后端中间文件全程 ASCII（临时目录）+ 成功后拷回；**目标 PDF 被阅读器打开会锁定导致拷贝 PermissionError**（报错易误诊）；④ **相对路径资源必须随迁**——md 搬到临时目录后 `figures/` 断链，Edge 只渲染 12px 占位框 → copytree(figures) + --resource-path。渲染引擎现为双后端自动回退：xelatex →（失败/被沙箱拦）→ pandoc HTML(MathML) + Edge 无头打印（宽表 word-break 不重叠、公式离线渲染、沙箱内可用），`WRITING_FLOW_PDF_ENGINE=xelatex|browser|auto`。配图链 `qe_charts.py`（4 张确定性图）已在 finalize 接线（QE 数据时自动出图插入）。
16. **修订者会删除 <!-- FIG:xxx --> 注释并改写为 [图N：标题] 文本**（M5 实测，修订说明 w6 自述）——锚点机制会被 LLM 层破坏；md2pdf.insert_figures 已加"正文图 N 引用锚定"第二层兜底（正则 图\s*N[:：]，跳过 HTML 注释行），任一通道命中即图文结合；改 prompt 只能降概率，代码层兜底才是确定性保证。
17. **xelatex 偶发 MiKTeX 更新检查失败（exit 1），浏览器回退也可能空产出**（M5 第二轮实测）→ archive 沿用旧 PDF，归档 PDF 可能是陈旧文件（字节数/时间戳与上轮一致即疑似陈旧）。跑前先手动 & ..\.venv\Scripts\python.exe tools\md2pdf.py output\论文_成稿.md 预热；验收 PDF 时核对时间戳。
18. **agent 沙箱内 venv 启动器对中文路径编码异常**：..\.venv\Scripts\python.exe 报 Unable to create process using 'C:\Users\???\...python.exe'（pyvenv.cfg 本身完好）。规避：用基解释器 C:\Users\王雨露\AppData\Local\Programs\Python\Python311\python.exe + PYTHONPATH 指向 venv site-packages（须含 win32;win32\lib;pywin32_system32，PATH 追加 pywin32_system32）。用户自己终端不受影响。

## 环境与依赖

- Python 3.10-3.13 / Windows；复用 `C:\Users\王雨露\Desktop\挑战杯\.venv`（crewai==1.15.10 + crewai-tools，pyproject 已锁定同版本）。
- 若需独立环境：仓库根目录 `crewai install` 后 `crewai run`（pyproject `[tool.crewai] type="flow"` 已配）。
- 模型矩阵：执行 qwen-plus / 评审 deepseek-v4-pro（跨家族，经百炼兼容模式）/ 裁决 qwen3.8-max 零温度；配置全在 `agents/*.jsonc`，改模型不碰代码。

## 相关资料索引

- 设计文档：`docs/mvp-product-plan/`、`docs/tech-design/`（本仓库内，双格式）
- 机制源头：ARIS 仓库（`挑战杯\crew优化\Auto-claude-code-research-in-sleep`），技能定义见其 `skills/`
- 资产来源：sf6_writing_crew（`挑战杯\sf6_writing_crew`），本仓库 tools/ 回收了 validate_report / make_charts / md2pdf
- CrewAI 中文文档库：`挑战杯\crewai-docs`（v1.15.10）
