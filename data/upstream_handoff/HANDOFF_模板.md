# HANDOFF · 上游交接清单模板

> 复制本文件为 `HANDOFF.md`，与前部流程产物一起放入 `data/upstream_handoff/`。
> 字段约定为双方契约谈判基线（待与前部流程队友确认，见产品方案第 7 节待确认清单）。

- state.id：上游 Flow 本次运行的 state.id（溯源互认字段）
- generated_at：产物生成时间（ISO 8601）
- artifacts：
  - 产物 1 文件名（形态：narrative / data / draft 三型之一）
  - 产物 2 文件名（如有）
- notes：红线声明 / 课题锚定配置 / 其他需要写作段遵守的约束

## 形态判道规则（本流程侧）

- 目录含 `adsorption_*/…/*.pwo`（QE 原始计算归档）→ 原始归档（standalone；`qe_extract` 确定性提取自动生成白名单数据表，README/CSV 作辅助材料入清单）
- 文件名含 narrative/叙事 → 叙事（standalone 全新成稿）
- 文件名含 vasp/数据 → 数据表（standalone，数值白名单源）
- 其余 → 已成初稿（refine 精修模式，直接进入改进循环）
