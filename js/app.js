/* ============================================
   keiba-study-site 共通JS
   ============================================ */

/**
 * JSONファイルを読み込む共通関数
 */
async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

/* ------------------------------------------
   血統ページ（pedigree.html）
   さくら担当：サイアーカードの描画
   ------------------------------------------ */
async function renderPedigree() {
  const container = document.getElementById('pedigree-list');
  if (!container) return;

  const data = await loadJSON('data/pedigree.json');
  container.innerHTML = data.sires.map(s => {
    const turf = s.turf_win_rate != null ? (s.turf_win_rate * 100).toFixed(1) + '%' : '-';
    const dirt = s.dirt_win_rate != null ? (s.dirt_win_rate * 100).toFixed(1) + '%' : '-';
    const top3 = s.top3_rate != null ? (s.top3_rate * 100).toFixed(1) + '%' : '-';
    const n = s.total_n ? s.total_n.toLocaleString() : '';
    return '<tr>' +
      '<td style="font-weight:600;color:#fff">' + s.name + '</td>' +
      '<td>' + s.best_distance_label + '</td>' +
      '<td style="color:var(--green);font-family:var(--mono)">' + turf + '</td>' +
      '<td style="color:var(--orange);font-family:var(--mono)">' + dirt + '</td>' +
      '<td style="color:var(--gold);font-family:var(--mono)">' + top3 + '</td>' +
      '<td style="color:var(--text2);font-family:var(--mono);font-size:12px">' + n + '</td>' +
      '</tr>';
  }).join('');
}

/* ------------------------------------------
   コースページ（course.html）
   あかり担当：コーステーブルの描画
   ------------------------------------------ */
async function renderCourse() {
  var container = document.getElementById('course-bias-cards');
  if (!container) return;

  var data = await loadJSON('data/course.json');

  container.innerHTML = data.courses.map(function(c) {
    var surfClass = c.surface === '芝' ? 'turf' : 'dirt';

    // 枠の最大値を求める
    var gateMax = Math.max(c.gates['内枠'] || 0, c.gates['中枠'] || 0, c.gates['外枠'] || 0);
    // 脚質の最大値を求める
    var styleMax = Math.max(c.styles['先行'] || 0, c.styles['中団'] || 0, c.styles['追込'] || 0);
    // バーの最大幅用（全体の最大）
    var allMax = Math.max(gateMax, styleMax, 1);

    function bar(label, val, bestVal) {
      var pct = Math.round(val / allMax * 100);
      var cls = val === bestVal && val > 0 ? 'best' : 'normal';
      return '<div class="bias-bar-row">' +
        '<div class="bias-label">' + label + '</div>' +
        '<div class="bias-track"><div class="bias-fill ' + cls + '" style="width:' + pct + '%">' + val + '%</div></div>' +
        '</div>';
    }

    return '<div class="bias-card">' +
      '<div class="bias-card-head">' +
        '<span class="bias-card-venue">' + c.venue + '</span>' +
        '<span class="bias-card-surface ' + surfClass + '">' + c.surface + '</span>' +
      '</div>' +
      '<div class="bias-section">' +
        '<div class="bias-title">枠順別の勝率</div>' +
        bar('内枠', c.gates['内枠'], gateMax) +
        bar('中枠', c.gates['中枠'], gateMax) +
        bar('外枠', c.gates['外枠'], gateMax) +
      '</div>' +
      '<div class="bias-section">' +
        '<div class="bias-title">脚質別の勝率</div>' +
        bar('先行', c.styles['先行'], styleMax) +
        bar('中団', c.styles['中団'], styleMax) +
        bar('追込', c.styles['追込'], styleMax) +
      '</div>' +
    '</div>';
  }).join('');
}

/* ------------------------------------------
   相性ページ（affinity.html）
   あかり×さくら共同：相性グリッドの描画
   ------------------------------------------ */
var evData = null;

// 現在選択中の会場・馬場を保持
var evFilter = {
  broadVenue: null, broadSurface: '全',
  hotVenue: null, hotSurface: '全'
};

async function renderAffinity() {
  var broadTbody = document.getElementById('broad-tbody');
  if (!broadTbody) return;

  evData = await loadJSON('data/affinity.json');
  var firstVenue = evData.venues[0];
  evFilter.broadVenue = firstVenue;
  evFilter.hotVenue = firstVenue;

  // 会場タブ（broad）
  buildVenueTabs('broad-tabs', function(venue) {
    evFilter.broadVenue = venue;
    renderBroad();
  });
  // 馬場タブ（broad）
  buildSurfaceTabs('broad-surface-tabs', function(s) {
    evFilter.broadSurface = s;
    renderBroad();
  });

  // 会場タブ（hotspot）
  buildVenueTabs('hotspot-tabs', function(venue) {
    evFilter.hotVenue = venue;
    renderHotspot();
  });
  // 馬場タブ（hotspot）
  buildSurfaceTabs('hotspot-surface-tabs', function(s) {
    evFilter.hotSurface = s;
    renderHotspot();
  });

  // 距離変更タブ
  setupDcTabs();

  renderBroad();
  renderHotspot();
  renderDistChange('延長');
}

function buildVenueTabs(containerId, onClick) {
  var container = document.getElementById(containerId);
  if (!container || !evData) return;
  container.innerHTML = evData.venues.map(function(v, i) {
    return '<button class="venue-tab' + (i === 0 ? ' active' : '') + '" data-venue="' + v + '">' + v + '</button>';
  }).join('');
  container.querySelectorAll('.venue-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      container.querySelectorAll('.venue-tab').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      onClick(btn.dataset.venue);
    });
  });
}

function buildSurfaceTabs(containerId, onClick) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var surfaces = ['全', '芝', 'ダート'];
  container.innerHTML = surfaces.map(function(s, i) {
    return '<button class="venue-tab' + (i === 0 ? ' active' : '') + '" data-surface="' + s + '">' + s + '</button>';
  }).join('');
  container.querySelectorAll('.venue-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      container.querySelectorAll('.venue-tab').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      onClick(btn.dataset.surface);
    });
  });
}

function sortByDistance(items) {
  return items.slice().sort(function(a, b) {
    // 芝が先、ダートが後、同じなら距離昇順
    if (a.surface !== b.surface) return a.surface === '芝' ? -1 : 1;
    return a.distance - b.distance;
  });
}

function roiColor(val) {
  if (val >= 200) return 'var(--gold)';
  if (val >= 100) return 'var(--green)';
  return 'var(--text2)';
}

function renderBroad() {
  var tbody = document.getElementById('broad-tbody');
  var venue = evFilter.broadVenue;
  var surfF = evFilter.broadSurface;
  var items = (evData.broad_by_venue && evData.broad_by_venue[venue]) || [];

  // 馬場フィルタ
  if (surfF !== '全') {
    items = items.filter(function(e) { return e.surface === surfF; });
  }
  // 芝→ダート、距離昇順
  items = sortByDistance(items);

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:24px">該当条件なし</td></tr>';
    return;
  }

  var lastKey = '';
  tbody.innerHTML = items.map(function(e) {
    var divider = '';
    var key = e.surface + e.distance;
    if (key !== lastKey) {
      lastKey = key;
      divider = '<tr><td colspan="6" style="background:var(--bg4);color:var(--gold);font-weight:700;font-size:12px;padding:6px 14px;letter-spacing:.06em">' + e.surface + ' ' + e.distance + 'm</td></tr>';
    }
    var fRoi = e.fukusho_roi != null ? e.fukusho_roi + '%' : '-';
    return divider + '<tr>' +
      '<td style="font-weight:600;color:#fff">' + e.sire + '</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + e.n + '</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + e.wins + '</td>' +
      '<td style="font-family:var(--mono);font-weight:700;color:' + roiColor(e.tansho_roi) + '">' + e.tansho_roi + '%</td>' +
      '<td style="font-family:var(--mono);font-weight:700;color:' + roiColor(e.fukusho_roi || 0) + '">' + fRoi + '</td>' +
      '<td style="font-family:var(--mono);color:' + (e.top3_rate >= 33 ? 'var(--green)' : 'var(--text2)') + '">' + e.top3_rate + '%</td>' +
      '</tr>';
  }).join('');
}

function renderHotspot() {
  var tbody = document.getElementById('hotspot-tbody');
  var venue = evFilter.hotVenue;
  var surfF = evFilter.hotSurface;
  var items = (evData.hotspots_by_venue && evData.hotspots_by_venue[venue]) || [];

  if (surfF !== '全') {
    items = items.filter(function(h) { return h.surface === surfF; });
  }
  items = sortByDistance(items);

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:24px">該当条件なし</td></tr>';
    return;
  }

  var lastKey = '';
  tbody.innerHTML = items.map(function(h) {
    var divider = '';
    var key = h.surface + h.distance;
    if (key !== lastKey) {
      lastKey = key;
      divider = '<tr><td colspan="8" style="background:var(--bg4);color:var(--gold);font-weight:700;font-size:12px;padding:6px 14px;letter-spacing:.06em">' + h.surface + ' ' + h.distance + 'm</td></tr>';
    }
    var wrPct = h.win_rate_pct != null ? h.win_rate_pct + '%' : '-';
    return divider + '<tr>' +
      '<td style="font-weight:600;color:#fff">' + h.sire + '</td>' +
      '<td>' + h.surface + '</td>' +
      '<td style="font-family:var(--mono)">' + h.distance + 'm</td>' +
      '<td>' + h.gate + '</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + h.n + '</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + wrPct + '</td>' +
      '<td style="font-family:var(--mono);font-weight:700;color:' + roiColor(h.tansho_roi) + '">' + h.tansho_roi + '%</td>' +
      '<td style="font-family:var(--mono);font-weight:700;color:' + roiColor(h.fukusho_roi) + '">' + h.fukusho_roi + '%</td>' +
      '</tr>';
  }).join('');
}

function setupDcTabs() {
  var container = document.getElementById('dc-tabs');
  if (!container) return;
  container.querySelectorAll('.venue-tab').forEach(function(btn) {
    btn.addEventListener('click', function() {
      container.querySelectorAll('.venue-tab').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      renderDistChange(btn.dataset.dc);
    });
  });
}

function renderDistChange(type) {
  var tbody = document.getElementById('dc-tbody');
  if (!tbody || !evData || !evData.dist_change) return;
  var items = evData.dist_change[type] || [];
  // 芝→ダート、距離昇順ソート
  items = sortByDistance(items);

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:24px">該当条件なし</td></tr>';
    return;
  }

  var lastKey = '';
  tbody.innerHTML = items.map(function(e) {
    var divider = '';
    var key = e.surface + e.distance;
    if (key !== lastKey) {
      lastKey = key;
      divider = '<tr><td colspan="8" style="background:var(--bg4);color:var(--gold);font-weight:700;font-size:12px;padding:6px 14px;letter-spacing:.06em">' + e.surface + ' ' + e.distance + 'm</td></tr>';
    }
    return divider + '<tr>' +
      '<td style="font-weight:600;color:#fff">' + e.sire + '</td>' +
      '<td>' + e.venue + '</td>' +
      '<td>' + e.surface + '</td>' +
      '<td style="font-family:var(--mono)">' + e.distance + 'm</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + e.n + '</td>' +
      '<td style="font-family:var(--mono);color:var(--text2)">' + e.wins + '</td>' +
      '<td style="font-family:var(--mono);font-weight:700;color:' + roiColor(e.tansho_roi) + '">' + e.tansho_roi + '%</td>' +
      '<td style="font-family:var(--mono);color:' + (e.top3_rate >= 33 ? 'var(--green)' : 'var(--text2)') + '">' + e.top3_rate + '%</td>' +
      '</tr>';
  }).join('');
}

/* ------------------------------------------
   クイズページ（quiz.html）
   ひなた担当：クイズロジック
   15問プールから10問ランダム出題、選択肢シャッフル
   ------------------------------------------ */
var quizState = {
  allQuestions: [],   // 元データ（15問）
  questions: [],      // 出題用（10問、選択肢シャッフル済み）
  current: 0,
  score: 0,
  answered: false,
  mistakes: []        // 間違えた問題を記録
};

function shuffleArray(arr) {
  var a = arr.slice();
  for (var i = a.length - 1; i > 0; i--) {
    var j = Math.floor(Math.random() * (i + 1));
    var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
  }
  return a;
}

async function initQuiz() {
  // データ読み込みのみ（ジャンル選択画面を表示）
  var container = document.getElementById('quiz-area');
  if (!container) return;

  var data = await loadJSON('data/quiz.json');
  quizState.allQuestions = data.questions;
}

function startQuiz(genre) {
  var container = document.getElementById('quiz-area');
  var genreSelect = document.getElementById('quiz-genre-select');

  // ジャンルフィルタ
  var pool = quizState.allQuestions;
  if (genre !== '全ジャンル') {
    pool = pool.filter(function(q) { return q.genre === genre; });
  }

  // 10問抽出（プールが10問未満なら全問）
  var numQ = Math.min(10, pool.length);
  var picked = shuffleArray(pool).slice(0, numQ);

  // 選択肢シャッフル
  quizState.questions = picked.map(function(q) {
    var correctText = q.choices[q.answer];
    var shuffled = shuffleArray(q.choices);
    var newAnswer = shuffled.indexOf(correctText);
    return {
      id: q.id,
      category: q.category,
      source: q.source,
      genre: q.genre,
      question: q.question,
      choices: shuffled,
      answer: newAnswer,
      explanation: q.explanation
    };
  });

  quizState.current = 0;
  quizState.score = 0;
  quizState.answered = false;
  quizState.mistakes = [];
  quizState.genre = genre;

  genreSelect.style.display = 'none';
  document.getElementById('quiz-result').style.display = 'none';
  container.style.display = 'block';
  renderQuizQuestion();
}

function renderQuizQuestion() {
  var q = quizState.questions[quizState.current];
  var total = quizState.questions.length;
  quizState.answered = false;

  // 進捗
  document.getElementById('quiz-progress-text').textContent =
    (quizState.current + 1) + ' / ' + total;
  document.getElementById('quiz-progress-fill').style.width =
    ((quizState.current) / total * 100) + '%';

  // バッジ
  var badgeHtml = '<span class="category-badge">' + q.category + '</span>';
  if (q.source === 'db_auto') {
    badgeHtml += ' <span class="category-badge db-badge">実データ</span>';
  }
  document.getElementById('quiz-badges').innerHTML = badgeHtml;

  // 問題文
  document.getElementById('quiz-question-text').textContent = q.question;

  // 選択肢
  var choicesList = document.getElementById('quiz-choices');
  choicesList.innerHTML = q.choices.map(function(c, i) {
    return '<li data-index="' + i + '">' + c + '</li>';
  }).join('');

  choicesList.querySelectorAll('li').forEach(function(li) {
    li.addEventListener('click', function() {
      handleAnswer(parseInt(li.dataset.index));
    });
  });

  // フィードバック・解説・次へ 非表示
  var fb = document.getElementById('quiz-feedback');
  if (fb) { fb.classList.remove('show', 'is-correct', 'is-wrong'); }
  document.getElementById('quiz-explanation').classList.remove('show');
  document.getElementById('quiz-next').classList.remove('show');
}

function handleAnswer(selected) {
  if (quizState.answered) return;
  quizState.answered = true;

  var q = quizState.questions[quizState.current];
  var choices = document.querySelectorAll('#quiz-choices li');

  choices.forEach(function(li) {
    var idx = parseInt(li.dataset.index);
    li.classList.add('disabled');
    if (idx === q.answer) li.classList.add('correct');
    if (idx === selected && selected !== q.answer) li.classList.add('wrong');
  });

  // フィードバック表示
  var fb = document.getElementById('quiz-feedback');
  if (selected === q.answer) {
    quizState.score++;
    fb.textContent = '正解！';
    fb.classList.add('show', 'is-correct');
  } else {
    quizState.mistakes.push({
      question: q.question,
      yourAnswer: q.choices[selected],
      correctAnswer: q.choices[q.answer],
      explanation: q.explanation
    });
    fb.textContent = '不正解… 正解は「' + q.choices[q.answer] + '」';
    fb.classList.add('show', 'is-wrong');
  }

  // 解説表示
  var explEl = document.getElementById('quiz-explanation');
  explEl.textContent = q.explanation;
  explEl.classList.add('show');

  // 次へボタン
  var nextEl = document.getElementById('quiz-next');
  nextEl.classList.add('show');
  var btn = nextEl.querySelector('button');
  if (quizState.current + 1 >= quizState.questions.length) {
    btn.textContent = '結果を見る';
  } else {
    btn.textContent = '次の問題へ';
  }
}

function nextQuestion() {
  quizState.current++;
  if (quizState.current >= quizState.questions.length) {
    showResult();
  } else {
    renderQuizQuestion();
  }
}

function showResult() {
  document.getElementById('quiz-area').style.display = 'none';
  var result = document.getElementById('quiz-result');
  result.style.display = 'block';

  var total = quizState.questions.length;
  var pct = Math.round((quizState.score / total) * 100);

  document.getElementById('result-score').textContent = quizState.score + ' / ' + total;
  document.getElementById('result-pct').textContent = '正答率: ' + pct + '%';

  // メッセージ
  var msg = '';
  if (pct === 100) msg = '満点！完璧な血統マスター！';
  else if (pct >= 90) msg = 'すごい！ほぼ完璧。自信を持って予想に活かそう！';
  else if (pct >= 70) msg = 'いい感じ！あと少しで上級者。間違えた問題を復習しよう';
  else if (pct >= 50) msg = '半分以上正解！伸びしろ十分。苦手なジャンルを重点的に';
  else if (pct >= 30) msg = 'まだ伸びる！血統ページとコースページを読み直してみよう';
  else msg = '大丈夫、ここから。まずは血統入門ガイドからスタート！';
  document.getElementById('result-message').textContent = msg;

  // 学習リンク
  var linksEl = document.getElementById('result-links');
  if (linksEl) {
    var genre = quizState.genre || '全ジャンル';
    if (genre === '血統' || genre === '全ジャンル') {
      linksEl.innerHTML = '<a href="pedigree.html" class="btn" style="margin:4px">血統ガイドで復習</a>';
    }
    if (genre === 'コース' || genre === '全ジャンル') {
      linksEl.innerHTML += '<a href="course.html" class="btn" style="margin:4px;background:var(--bg4);color:var(--text)">コースガイドで復習</a>';
    }
  }

  // 間違えた問題一覧
  var mistakeEl = document.getElementById('result-mistakes');
  if (quizState.mistakes.length === 0) {
    mistakeEl.innerHTML = '<p>全問正解！間違いはありません。</p>';
  } else {
    mistakeEl.innerHTML = '<h3>間違えた問題</h3>' +
      quizState.mistakes.map(function(m) {
        return '<div class="mistake-item">' +
          '<p class="mistake-q">' + m.question + '</p>' +
          '<p class="mistake-yours">あなたの回答: ' + m.yourAnswer + '</p>' +
          '<p class="mistake-correct">正解: ' + m.correctAnswer + '</p>' +
          '<p class="mistake-expl">' + m.explanation + '</p>' +
          '</div>';
      }).join('');
  }
}

function resetQuiz() {
  // 同じジャンルで再出題
  startQuiz(quizState.genre || '全ジャンル');
}

function backToGenre() {
  document.getElementById('quiz-area').style.display = 'none';
  document.getElementById('quiz-result').style.display = 'none';
  document.getElementById('quiz-genre-select').style.display = 'block';
}

/* ------------------------------------------
   初期化
   ------------------------------------------ */
document.addEventListener('DOMContentLoaded', () => {
  renderPedigree();
  renderCourse();
  renderAffinity();
  initQuiz();
});
