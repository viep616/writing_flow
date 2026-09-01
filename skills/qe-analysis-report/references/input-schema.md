# QE 输入识别与数据质量

## 典型目录结构（本项目实测）

```text
QE计算结果/
├── README.md                    # 项目说明（参数、公式、数据状态）
├── convergence_results.csv      # 收敛性测试汇总：system,ecutwfc,kgrid,total_energy_Ry,converged
├── convergence_test/
│   └── *_ecut30_k1x1x2.pwo 等   # 截断能/k 点扫描的 SCF 输出
└── 原训练集_94体系/
    └── adsorption_6,6_armchair_Pt_H2S_top_029/
        ├── espresso.pwi         # QE 输入
        └── espresso.pwo         # QE 输出（弛豫）
```

## 体系命名解析

`adsorption_{chirality}_{modifier}_{molecule}_{site}_{id}`

| 段 | 取值 | 示例 |
|---|---|---|
| chirality | `6,6_armchair` / `8,0_zigzag` | 6,6_armchair |
| modifier | `pure` / `Pt` / `PtN` / `PtPd` | Pt |
| molecule | `H2S` / `SO2` / `SOF2` / `SO2F2` / `SF6` | H2S |
| site | `top` / `bridge` / `hollow` | top |
| id | 三位编号 | 029 |

分组键（用于组内相对比较）：`(chirality, modifier, molecule)`。同组内不同 site 的总能可直接比较（原子数、化学组成相同）。

## pwi 关键字段

| 字段 | 说明 |
|---|---|
| `calculation` | relax / scf / bands / nscf |
| `etot_conv_thr` / `forc_conv_thr` | 总能/力收敛阈值（Ry、Ry/a.u.） |
| `nat` / `ntyp` | 原子数 / 元素种类数 |
| `ecutwfc` / `ecutrho` | 截断能（Ry） |
| `input_dft` | 泛函（PBE 等） |
| `vdw_corr` | 色散校正（grimme-d3 等） |
| `nspin` | 1 或 2（含金属体系自旋极化） |
| `occupations` / `smearing` / `degauss` | 展宽方式与宽度 |
| `conv_thr` | SCF 收敛阈值（Ry） |
| `ion_dynamics` | bfgs 等 |
| `CELL_PARAMETERS` / `ATOMIC_POSITIONS` | 晶胞与初始坐标 |

## pwo 关键字段（正则提取）

| 内容 | 正则要点 |
|---|---|
| 原子/电子数 | `number of atoms/cell`、`number of electrons` |
| k 点与展宽 | `number of k points=  N  Gaussian smearing, width (Ry)=` |
| 总能 | `total energy\s*=\s*(-?\d+\.\d+)\s*Ry`（取最后一次；README 记为 `!` 行） |
| SCF 精度 | `estimated scf accuracy`（取最后一次，判是否收敛） |
| 力 | `Forces acting on atoms` 块（`force =` 三列，取最后一次并算最大值） |
| 完成标志 | 文件末尾 `JOB DONE` |

单位换算（写进报告）：1 Ry = 13.6057 eV；1 Ry/a.u. = 25.711 eV/Å。

**选择性弛豫注意**：本项目 pwi 采用 `ion_dynamics=bfgs` 选择性弛豫（README 注明"冻结距吸附位点 > 3.5 Å 的管身 C 原子"）。pwo 的力块包含冻结原子，`max_force` 因此包含冻结原子分量：报告须说明该口径，不单凭最大力判定弛豫失败；弛豫状态以 `JOB DONE` + SCF 收敛为主，最大力仅作辅助信息。

## 参考能量（E_ads 前提）

E_ads = E(复合物) − E(基底) − E(气体)。三类输入均可：

1. 直接提供 E_ads 数值表（CSV/Markdown）；
2. 提供 E_slab（各修饰×各手性的裸基底）与 E_mol（各孤立气体分子）；
3. 都没有 → **降级模式**：只输出组内相对稳定性（同组 site 总能差）、结构参数、收敛性分析；E_ads 章节用"待补参考能量"模板（见 output-template.md），明确写出所需参考能量清单，禁止编造数值。

**来源约束（防混用）**：参考能量必须来自与吸附体系同一套 QE 计算（同软件、同泛函/赝势/截断能/色散校正），且原子组成与吸附体系可对应（复合物 − 基底 − 气体恰好消去）。不得把 VASP/其它软件或文献中的 E_ads 数值当作本数据集的参考能量填入 E_ads 表；即使写作项目内已有 VASP 吸附能表（如 `vasp_results.md`），也只能作为"趋势对照"使用，且必须标注来源与"不同计算方法"的限定。任何被当作本数据计算值的 E_ads 都必须能由本数据集文件或同源参考文件复算。

## 数据质量检查（写进报告"数据说明"）

- 每个体系必须有 `espresso.pwi` + `espresso.pwo`，缺一即标记；
- `pwo` 末尾必须 `JOB DONE`，否则标记"未正常结束"；
- SCF 未收敛（`estimated scf accuracy` 未降到阈值）标记"SCF 未收敛"；
- 同名重复文件（如 `espresso (1).pwi`）去重并提示；
- 收敛性 CSV 中的 `no(...)` 状态必须如实呈现（如"难收敛""SCF 慢未完成"）；
- 命名不一致（如 CSV 中 `OH_SO2_top_013` 与训练集 `adsorption_*` 命名不同）需提示核对。
