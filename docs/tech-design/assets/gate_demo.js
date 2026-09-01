(function () {
  var scoreEl = document.getElementById('gScore');
  var verdictEl = document.getElementById('gVerdict');
  var parseEl = document.getElementById('gParse');
  var resultEl = document.getElementById('gResult');
  if (!scoreEl || !verdictEl || !parseEl || !resultEl) return;

  var PASS = '#0e9f6e', REVISE = '#b7791f', UNAVAIL = '#d64545';

  function decide() {
    var score = parseFloat(scoreEl.value);
    var verdict = verdictEl.value;
    var parseOk = parseEl.value === 'ok';
    var html;

    if (!parseOk) {
      html = '<b style="color:' + UNAVAIL + '">REVIEW_UNAVAILABLE</b><br>' +
        'JSON 解析失败 → fail-closed：判定为未通过，转 revise 分支，同时写 human_flags 请求人工复核。<br>' +
        '<span style="color:#5d6b7e">route_r1 → "revise"</span>';
    } else if (score >= 6 && (verdict === 'ready' || verdict === 'almost')) {
      html = '<b style="color:' + PASS + '">PASSED</b><br>' +
        '双条件成立（score=' + score + ' ≥ 6 且 verdict=' + verdict + '）→ 停机，跳过修复轮直转终审。<br>' +
        '<span style="color:#5d6b7e">route_r1 → "final_audits"</span>';
    } else {
      var why = score < 6 ? 'score=' + score + ' 未达 6' : 'verdict=' + verdict + ' 不在 {ready, almost}';
      html = '<b style="color:' + REVISE + '">NOT_PASSED</b><br>' +
        '双条件未满足（' + why + '）→ 单高分不停车，转最小修复轮。<br>' +
        '<span style="color:#5d6b7e">route_r1 → "revise"</span>';
    }
    resultEl.innerHTML = 'review_gate 判定 → ' + html;
  }

  [scoreEl, verdictEl, parseEl].forEach(function (el) {
    el.addEventListener('change', decide);
    el.addEventListener('input', decide);
  });
  decide();
})();
