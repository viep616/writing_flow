---
name: qe-analysis-report
description: 分析 Quantum ESPRESSO（QE）吸附计算的原始输出（pwi/pwo、收敛性 CSV），生成中文数据分析报告（分章节、带图表、PDF 输出）。适用于 SF6 分解气体在（掺杂）碳纳米管等表面上的吸附能、结构参数、收敛性分析。输入为 QE 原始输出目录或文件集时使用；不用于 VASP/CASTEP 等其他软件输出，也不用于撰写论文正文以外的综述。
---

# QE 数据分析报告

## 用途

接收 QE 原始输出，产出论文风格的中文数据分析报告 PDF。核心原则：**每个数值必须来自输入数据，禁止编造，禁止用文献默认值冒充本数据计算值**。

## 输入

- QE 输出目录：每个体系含 `espresso.pwi`（输入）+ `espresso.pwo`（输出）；可选 `convergence_results.csv` 与参考能量（直接给 E_ads，或给 E_slab/E_mol）。
- 体系命名示例：`adsorption_6,6_armchair_Pt_H2S_top_029`，解析规则见 [references/input-schema.md](references/input-schema.md)。

## 核心流程

1. 盘点输入数据并做数据质量检查（缺失、重复、未收敛、`JOB DONE`）。
2. 运行 `scripts/parse_qe.py` 提取结构化数据（能量、结构、力、完成标志、体系分组）。
3. 按 [analysis-standards](references/analysis-standards/) 分析：吸附能 → 结构参数 → 收敛性；电子结构仅在数据包含电荷密度/能带/DOS 时启用。
   涉及排序、选择性、对比或互证时，先读 [references/domain/](references/domain/) 的领域蒸馏页与 [comparison-protocol.md](references/analysis-standards/comparison-protocol.md)；提供实验数据时再读 [simulation-experiment-verification.md](references/analysis-standards/simulation-experiment-verification.md)。
4. 按 [output-template.md](references/output-template.md) 组织报告（单体系深度 / 批量对比两种模式）。
5. 生成图表与 PDF（`scripts/build_report.py`，pandoc+xelatex，中文字体 SimHei）。
6. 对照 [quality-checklist.md](references/quality-checklist.md) 自查通过后再交付。

## 硬性红线

- 无参考能量（E_slab、E_mol 或直接给的 E_ads）时，**不得输出绝对值吸附能**；只做组内相对稳定性分析，E_ads 章节使用"待补参考能量"模板。
- 单位与转换必须交代：1 Ry = 13.6057 eV；力 1 Ry/a.u. = 25.711 eV/Å；电荷转移量单位为 e（不是 eV）。
- 未计算的量（脱附势垒、恢复时间、声子/有限温度效应、带隙等）不得下结论。
- 数值保留输入数据的有效位数，不四舍五入成整数；异常值（未收敛、缺文件、重复文件）必须如实报告。

## 参考路由

- 输入解析与数据质量：[references/input-schema.md](references/input-schema.md)
- 分析规范：[吸附能](references/analysis-standards/adsorption-energy.md)、[结构参数](references/analysis-standards/structural-parameters.md)、[收敛性](references/analysis-standards/convergence.md)、[电子结构（扩展）](references/analysis-standards/electronic-structure.md)
- 比较协议与互证：[comparison-protocol.md](references/analysis-standards/comparison-protocol.md)、[simulation-experiment-verification.md](references/analysis-standards/simulation-experiment-verification.md)
- 领域知识层（蒸馏页，证据级）：[references/domain/](references/domain/)（分析比较与互证 / 建模与体系设计 / 数据提取与指标计算）
- 推理规范（结果与讨论必须遵守）：[references/analysis-standards/reasoning.md](references/analysis-standards/reasoning.md)，示例见 [references/examples/analysis-paragraph.md](references/examples/analysis-paragraph.md)
- 呈现规范：[表格](references/presentation-standards/tables.md)、[图表](references/presentation-standards/figures.md)、[语言与结构](references/presentation-standards/language.md)
- 报告模板与质量门：[output-template.md](references/output-template.md)、[quality-checklist.md](references/quality-checklist.md)

## 在 writing_flow（CrewAI Flow）中的使用

- 本技能位于工作区 skills/qe-analysis-report/；读取 references/ 或运行 scripts/ 时以该目录为基准（例如 skills/qe-analysis-report/references/quality-checklist.md）。
- Flow 内 QE 数据提取一律以 tools/qe_extract.py 的产物 output/QE_数据表.md（白名单 + SHA256 指纹）为准；本技能 scripts/ 仅供独立环境（非 Flow）使用，不要在 Flow 内另起数据管线。
- 正文必须按 references/analysis-standards/reasoning.md 的四步法组织分析；交付前逐项自查 references/quality-checklist.md（含比较协议四项）。

