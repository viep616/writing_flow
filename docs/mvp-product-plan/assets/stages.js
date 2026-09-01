(function () {
  var stages = [
    {
      id: 'F1', name: 'load_inputs',
      title: 'F1 · 输入判道与素材标准化',
      trigger: '流程启动（@start 唯一入口）',
      input: 'data/ 下固定路径：sf6_handoff/（衔接）、NARRATIVE_REPORT.md、vasp_results.md',
      output: 'SOURCES_MANIFEST.json（路径 + SHA256 指纹）+ mode 写入状态',
      executor: 'prepare_inputs.py（纯代码）',
      defense: '白名单源、红线声明、方法学自查三要素在此固化为审计基准',
      fallback: '无有效输入 → 显式报错并列出检索过的路径，不猜测'
    },
    {
      id: 'F2', name: 'paper_plan',
      title: 'F2 · 论文规划（claims-evidence 矩阵）',
      trigger: 'F1 完成',
      input: '素材包 + 白名单源',
      output: 'PAPER_PLAN.md：矩阵 / 5-8 节结构 / 图表计划',
      executor: 'plan_crew · paper_planner（qwen-plus）',
      defense: '每条 claim 必须绑定证据槽位；无证据 claim 标 DATA_NEEDED 不进强论证',
      fallback: 'refine 模式跳过新规划，从队友终稿反提矩阵作审计对照'
    },
    {
      id: 'F3', name: 'negotiate_contract',
      title: 'F3 · 验收契约谈判（≤2 轮）',
      trigger: 'F2 完成',
      input: 'PAPER_PLAN.md',
      output: '验收_契约_{stamp}.md（accepted / contested）',
      executor: 'contract_crew · claim_drafter（qwen-plus）+ contract_challenger（deepseek-v3，跨家族）',
      defense: '先谈后写：断言是否可测、证据是否可得、是否过度承诺，挑战后才冻结',
      fallback: '两轮未一致 → contested 留痕放行，human_flags 记录，终报 Submission-ready: no'
    },
    {
      id: 'F4', name: 'write_sections',
      title: 'F4 · 分节写作',
      trigger: '契约流程结束（accepted 或 contested 均放行）',
      input: 'PAPER_PLAN.md + 契约 + 数据表',
      output: '论文_初稿.md',
      executor: 'write_crew · section_writer（qwen-plus）',
      defense: '主题锚定 / 数值纪律 / 雷区黑名单三条 prompt 纪律；缺证据写 DATA_NEEDED 注释',
      fallback: 'refine 模式跳过本步（上游半成品或初探终稿直接进入循环）；引用一律标「待核实」'
    },
    {
      id: 'F5', name: 'review_r1',
      title: 'F5 · 改进循环 R1（跨模型评审·新实例）',
      trigger: 'F4 完成',
      input: '论文_初稿.md',
      output: '评审_记录_R1_{stamp}.json（原文逐字 + 解析字段）',
      executor: 'review_crew · cross_reviewer（deepseek-v3，全新 Crew 实例）',
      defense: '双条件停机：score≥6 且 verdict∈{ready,almost} 才放行；判定归 review_gate.py 状态机',
      fallback: '解析失败 → REVIEW_UNAVAILABLE，fail-closed 转修复 + 人工标记'
    },
    {
      id: 'F5b', name: 'revise_paper',
      title: 'F5b · 最小修复',
      trigger: 'R1 未达双条件（router 标签 revise）',
      input: 'R1 弱点清单（按严重度排序）',
      output: '论文_修订稿.md',
      executor: 'revise_crew · reviser（qwen-plus，复用写作配置）',
      defense: '固定修复模式表：overclaim 收窄 scope、矛盾重写、警告并入 Limitations、术语一致',
      fallback: '只做最小修复，不重写全文，防止修复引入新漂移'
    },
    {
      id: 'F5c', name: 'review_r2',
      title: 'F5c · 复审 R2 + 义务台账核验',
      trigger: 'F5b 完成（固定两轮，R2 后恒转终审）',
      input: '修订稿 + R1 成立清单（程序占位符注入）',
      output: '评审_记录_R2_{stamp}.json + 义务_台账_{stamp}.jsonl',
      executor: 'review_crew · 全新实例（deepseek-v3）+ ledger.py',
      defense: 'R1 弱点逐条核验下落；既无核验也无处置 → UNRESOLVED_DISAPPEARANCE（删句绕过检测）',
      fallback: 'R2 仍未达标不进入第三轮，带 _评审未达标 后缀转人工'
    },
    {
      id: 'F6', name: 'kill_argument',
      title: 'F6 · 致命一击',
      trigger: '改进循环结束（router 标签 final_audits）',
      input: '当前成稿',
      output: '致命一击_{stamp}.json（拒稿段 + 3-7 原子点三分类 + verdict）',
      executor: 'kill_crew · killer（deepseek-v3）+ arbiter（qwen3.8-max 零温度）',
      defense: 'verdict 由 verdict_map.py 纯代码映射：critical 未决即 FAIL；未决为 0 才可能 PASS',
      fallback: '不适用场景也落盘 NOT_APPLICABLE 工件，禁止静默跳过'
    },
    {
      id: 'F7', name: 'claim_audit',
      title: 'F7 · 零上下文数值审计',
      trigger: 'F6 完成',
      input: '只读两份材料：成稿 + 数据文件（排除一切中间产物）',
      output: '数值_复核_{stamp}.json（findings + _meta 指纹）',
      executor: 'audit_crew · claim_auditor（deepseek-v3 零温度）+ validate_report.py 白名单',
      defense: '七类数字失真检查；findings>0 程序强制 FAIL；零上下文防确认偏置',
      fallback: '有数字主张但缺原始文件 → BLOCKED 停下转人工'
    },
    {
      id: 'F8', name: 'verify_gates',
      title: 'F8 · 确定性投稿门',
      trigger: 'F7 完成',
      input: '全部留痕工件 + 当前成稿 + 数据文件',
      output: 'RUN_STATE_{stamp}.json（gate_results + overall 三态）',
      executor: 'verify_gates.py（纯代码，零 LLM）',
      defense: '五项检查：齐全性 / 哈希新鲜度（防审计旧稿）/ verdict 一致性 / 禁静默 / 后缀合成',
      fallback: 'overall = no 时成稿带 _未通过门 后缀，人工读 gate_results 定位'
    },
    {
      id: 'F9', name: 'finalize',
      title: 'F9/F10 · 留档、恢复与转人工标记',
      trigger: 'F8 完成',
      input: '成稿 + 全部工件 + gate 结果',
      output: '论文_成稿_{stamp}{后缀}.md/.pdf + 终报（含 Next Steps）',
      executor: 'archive.py + Flow @persist 状态快照',
      defense: '时间戳留档永不覆盖；后缀即质检结论；断点可从 SQLite 分叉恢复',
      fallback: 'PDF 工具缺失自动跳过；遗留争议全部显式进 human_flags 与终报'
    }
  ];

  var tabsEl = document.getElementById('stageTabs');
  var detailEl = document.getElementById('stageDetail');
  if (!tabsEl || !detailEl) return;

  stages.forEach(function (s, i) {
    var b = document.createElement('button');
    b.className = 'stage-tab';
    b.textContent = s.id + ' ' + s.name;
    b.addEventListener('click', function () { render(i); });
    tabsEl.appendChild(b);
  });

  function field(k, v, full) {
    return '<div class="' + (full ? 'full' : '') + '"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>';
  }

  function render(i) {
    var s = stages[i];
    var tabs = tabsEl.children;
    for (var j = 0; j < tabs.length; j++) tabs[j].classList.toggle('active', j === i);
    detailEl.innerHTML =
      '<h4>' + s.title + '</h4>' +
      '<div class="stage-grid">' +
      field('触发条件', s.trigger) +
      field('执行者', s.executor) +
      field('输入', s.input) +
      field('输出', s.output) +
      field('防线机制', s.defense, true) +
      field('失败兜底', s.fallback, true) +
      '</div>';
  }

  render(0);
})();
