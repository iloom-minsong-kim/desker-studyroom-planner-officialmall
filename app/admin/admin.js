/* DESKER 학생방 플래너 — 관리자 대시보드 */
'use strict';
const $ = s => document.querySelector(s);
let L = null;          // labels.json
let ROWS = [];         // API 원본
let R = [];            // 목록 표시용
let F = [];            // 필터 결과
let sc = 0, sd = -1;   // 정렬 컬럼·방향
let colFilters = {};

const STEP_NAMES = ['자녀방 고민 계기', '방의 환경', '필요한 가구', '중요한 기능', '예산과 결과'];
const ORDINAL = ['age', 'budget', 'count', 'storageCount', 'roomKnown'];

function esc(x) { return String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function opts(field) { const f = L.fields[field]; return f.ref ? L.fields[f.ref].options : f.options; }
function lab(field, v) {
  if (v === undefined || v === null || v === '') return '';
  const o = opts(field);
  return Array.isArray(v) ? v.map(x => o[x] || x).join(', ') : (o[String(v)] || String(v));
}
function man(n) { return n ? Math.round(n / 10000).toLocaleString('ko-KR') + '만원' : '-'; }
function pct(a, b) { return b ? Math.round(a / b * 1000) / 10 : 0; }
function selPlan(r) {
  const res = r.results || [];
  if (!res.length) return null;
  const i = Number.isInteger(r.selected) && r.selected < res.length ? r.selected : 0;
  return res[i];
}
function ymd(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }

// ── 데이터 로드 ─────────────────────────────
async function api(url) {
  const r = await fetch(url, { credentials: 'same-origin' });
  if (r.status === 401) { location.reload(); throw new Error('login'); }
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
function rangeQuery() {
  const p = new URLSearchParams();
  if ($('#from').value) p.set('frm', $('#from').value);
  if ($('#to').value) p.set('to', $('#to').value);
  return p.toString();
}
async function load() {
  ROWS = await api('/api/admin/sessions?' + rangeQuery());
  renderInsight();
  buildList();
}

// ── 공통 차트 조각 ───────────────────────────
function hbars(items, { total, unit = '명', acc = false, valueFmt } = {}) {
  if (!items.length) return '<div class="empty">아직 데이터가 없어요.</div>';
  const max = Math.max(...items.map(x => x.v), 1);
  return items.map(x => {
    const w = x.v / max * 100;
    const right = valueFmt ? valueFmt(x) : `${x.v.toLocaleString('ko-KR')}${unit}${total ? `<small>${pct(x.v, total)}%</small>` : ''}`;
    const tip = x.tip || `${x.l}: ${x.v.toLocaleString('ko-KR')}${unit}${total ? ` (${pct(x.v, total)}%)` : ''}`;
    return `<div class="hbar" data-tip="${esc(tip)}"><span class="lb">${esc(x.l)}</span><span class="tr"><span class="fi${acc || x.acc ? ' acc' : ''}" style="width:${w}%;display:block"></span></span><span class="nv">${right}</span></div>`;
  }).join('');
}
function kpi(k, v, d = '') { return `<div class="card kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`; }

// ── 인사이트 ────────────────────────────────
function renderInsight() {
  const all = ROWS, done = ROWS.filter(r => r.completed_at && r.answers);
  const started = all.filter(r => r.max_step >= 1).length;
  const consult = done.filter(r => r.events.consult).length;
  const shop = done.filter(r => r.events.shop).length;
  const amounts = done.map(r => selPlan(r)?.amount).filter(Boolean);
  const avg = amounts.length ? amounts.reduce((s, x) => s + x, 0) / amounts.length : 0;

  $('#kpis').innerHTML =
    kpi('방문', all.length.toLocaleString('ko-KR'), '접속한 기기·브라우저 수') +
    kpi('설문 시작', started.toLocaleString('ko-KR'), `방문 대비 ${pct(started, all.length)}%`) +
    kpi('설문 완료', done.length.toLocaleString('ko-KR'), `시작 대비 ${pct(done.length, started)}%`) +
    kpi('매장 상담표 열람', pct(consult, done.length) + '%', `완료자 ${consult}명`) +
    kpi('온라인 구매 안내', pct(shop, done.length) + '%', `완료자 ${shop}명`) +
    kpi('선택안 평균 금액', man(avg), amounts.length ? `${amounts.length}건 기준` : '');

  // 퍼널
  const fun = [{ l: '방문', v: all.length }];
  STEP_NAMES.forEach((n, i) => fun.push({ l: `${i + 1}단계 · ${n}`, v: all.filter(r => r.max_step >= i + 1).length }));
  fun.push({ l: '설문 완료', v: done.length, acc: true });
  $('#funnel').innerHTML = hbars(fun, { total: all.length });

  renderTrend(all);

  // 결과 이후 행동
  const acts = ['select-result', 'detail', 'shop', 'consult', 'share', 'native-share', 'save-result', 'print', 'edit']
    .map(t => ({ l: L.events[t], v: done.filter(r => r.events[t]).length }));
  $('#actions').innerHTML = hbars(acts, { total: done.length });

  // 선택한 추천안 유형
  const pt = {};
  done.forEach(r => { const p = selPlan(r); if (p) pt[p.label || '(이름 없음)'] = (pt[p.label || '(이름 없음)'] || 0) + 1; });
  const noRes = done.filter(r => !(r.results || []).length).length;
  const ptItems = Object.entries(pt).sort((a, b) => b[1] - a[1]).map(([l, v]) => ({ l, v }));
  if (noRes) ptItems.push({ l: '추천 결과 없음(상담 안내)', v: noRes });
  $('#plantype').innerHTML = hbars(ptItems, { total: done.length });

  // 응답 분포
  const DIST = ['age', 'budget', 'channel', 'region', 'deskExp', 'buyTime', 'items', 'mandatory', 'kept', 'reason',
    'needs', 'useSel', 'monitor', 'motion', 'chair', 'colorPref', 'storageType', 'storageCount', 'room', 'mat',
    'roomKnown', 'wall', 'constraints', 'scope'];
  let html = DIST.map(f => distCard(f, done)).join('');
  const dv = {};
  done.forEach(r => { dv[r.device] = (dv[r.device] || 0) + 1; });
  html += `<div class="card"><h3>접속 기기</h3><div class="sub">응답 ${done.length}명</div>${hbars(Object.entries(dv).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ l: L.devices[k] || k, v })), { total: done.length })}</div>`;
  $('#dists').innerHTML = html;

  // 교차 분석
  $('#xt-age-budget').innerHTML = crosstab(done, 'age', 'budget');
  $('#xt-age-chair').innerHTML = crosstab(done, 'age', 'chair') + '<div style="height:10px"></div>' + crosstab(done, 'age', 'motion');
  const ba = Object.keys(opts('budget')).map(k => {
    const xs = done.filter(r => r.answers.budget === k).map(r => selPlan(r)?.amount).filter(Boolean);
    const m = xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0;
    return { l: opts('budget')[k], v: Math.round(m), n: xs.length, tip: `${opts('budget')[k]}: 평균 ${man(m)} (${xs.length}건)` };
  }).filter(x => x.n);
  $('#budget-amount').innerHTML = hbars(ba, { valueFmt: x => `${man(x.v)}<small>${x.n}건</small>` });

  const pc = {};
  done.forEach(r => (selPlan(r)?.lines || []).forEach(ln => {
    const k = ln.code; pc[k] = pc[k] || { l: `${ln.code} · ${ln.name}`, v: 0 }; pc[k].v += 1;
  }));
  $('#top-products').innerHTML = hbars(Object.values(pc).sort((a, b) => b.v - a.v).slice(0, 15), { unit: '건' });
}

function distCard(field, done) {
  const f = L.fields[field], o = opts(field), cnt = {};
  let n = 0;
  done.forEach(r => {
    const v = r.answers[field];
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) return;
    n += 1;
    (Array.isArray(v) ? v : [v]).forEach(x => { cnt[x] = (cnt[x] || 0) + 1; });
  });
  let items = Object.entries(cnt).map(([k, v]) => ({ k, l: o[k] || k, v }));
  if (ORDINAL.includes(field)) { const order = Object.keys(o); items.sort((a, b) => order.indexOf(a.k) - order.indexOf(b.k)); }
  else items.sort((a, b) => b.v - a.v);
  const multi = f.type === 'multi' ? ' · 복수 선택' : '';
  return `<div class="card"><h3>${esc(f.name)}</h3><div class="sub">응답 ${n}명${multi}</div>${hbars(items, { total: n })}</div>`;
}

function crosstab(done, rowF, colF) {
  const ro = opts(rowF), co = opts(colF);
  const rk = Object.keys(ro).filter(k => done.some(r => r.answers[rowF] === k));
  const ck = Object.keys(co).filter(k => done.some(r => r.answers[colF] === k));
  if (!rk.length || !ck.length) return '<div class="empty">아직 데이터가 없어요.</div>';
  const cell = (a, b) => done.filter(r => r.answers[rowF] === a && r.answers[colF] === b).length;
  const max = Math.max(1, ...rk.flatMap(a => ck.map(b => cell(a, b))));
  return `<div style="overflow-x:auto"><table class="xt"><thead><tr><th>${esc(L.fields[rowF].name)} \\ ${esc(L.fields[colF].name)}</th>${ck.map(k => `<th>${esc(co[k])}</th>`).join('')}<th>합계</th></tr></thead><tbody>` +
    rk.map(a => {
      let sum = 0;
      const tds = ck.map(b => { const v = cell(a, b); sum += v; const al = v ? 0.08 + v / max * 0.5 : 0; return `<td style="background:rgba(255,89,72,${al.toFixed(2)})" title="${esc(ro[a])} · ${esc(co[b])}: ${v}명">${v || ''}</td>`; }).join('');
      return `<tr><th>${esc(ro[a])}</th>${tds}<td><b>${sum}</b></td></tr>`;
    }).join('') + '</tbody></table></div>';
}

function renderTrend(all) {
  const by = {};
  all.forEach(r => { const d = r.created_at.slice(0, 10); by[d] = by[d] || { v: 0, c: 0 }; by[d].v += 1; if (r.completed_at) by[d].c += 1; });
  let days = Object.keys(by).sort();
  if (!days.length) { $('#trend').innerHTML = '<div class="empty">아직 데이터가 없어요.</div>'; return; }
  // 빈 날짜 채우기(최대 92일)
  const first = new Date(days[0] + 'T00:00:00'), last = new Date(days[days.length - 1] + 'T00:00:00');
  if ((last - first) / 864e5 <= 92) {
    days = [];
    for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 1)) days.push(ymd(d));
  }
  const W = 720, H = 220, pl = 34, pr = 8, pt = 10, pb = 26;
  const max = Math.max(1, ...days.map(d => (by[d] || {}).v || 0));
  const nice = Math.ceil(max / 5) * 5 || 5;
  const gw = (W - pl - pr) / days.length, bw = Math.max(2, Math.min(14, (gw - 4) / 2));
  const y = v => pt + (H - pt - pb) * (1 - v / nice);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const v = nice / 4 * i, yy = y(v);
    g += `<line x1="${pl}" x2="${W - pr}" y1="${yy}" y2="${yy}" stroke="#e5e5e5" stroke-width="1"/><text x="${pl - 6}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#969696">${Math.round(v)}</text>`;
  }
  const step = Math.ceil(days.length / 10);
  days.forEach((d, i) => {
    const o = by[d] || { v: 0, c: 0 }, cx = pl + gw * i + gw / 2;
    const bar = (v, x, col) => v ? `<path d="M${x},${y(0)} V${y(v) + 3} q0,-3 3,-3 h${bw - 6 > 0 ? bw - 6 : 0} q3,0 3,3 V${y(0)} Z" fill="${col}"/>` : '';
    g += `<g class="day" data-tip="${d} · 방문 ${o.v} · 완료 ${o.c}">` +
      `<rect x="${pl + gw * i}" y="${pt}" width="${gw}" height="${H - pt - pb}" fill="transparent"/>` +
      bar(o.v, cx - bw - 1, 'var(--s-visit)') + bar(o.c, cx + 1, 'var(--s-done)') + '</g>';
    if (i % step === 0) g += `<text x="${cx}" y="${H - 8}" text-anchor="middle" font-size="10" fill="#969696">${d.slice(5)}</text>`;
  });
  g += `<line x1="${pl}" x2="${W - pr}" y1="${y(0)}" y2="${y(0)}" stroke="#b3b3b3"/>`;
  $('#trend').innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="일자별 방문과 완료">${g}</svg>`;
}

// 툴팁
document.addEventListener('mousemove', e => {
  const el = e.target.closest && e.target.closest('[data-tip]');
  const tip = $('#tip');
  if (!el) { tip.style.display = 'none'; return; }
  tip.textContent = el.dataset.tip;
  tip.style.display = 'block';
  const x = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
});

// ── 응답 목록 ───────────────────────────────
const C = [
  { k: 'created', n: '접속시각' }, { k: 'done', n: '진행' }, { k: 'device', n: '기기' },
  { k: 'age', n: '연령' }, { k: 'budget', n: '예산' }, { k: 'items', n: '들이고 싶은 가구' },
  { k: 'mandatory', n: '꼭 필요한 가구' }, { k: 'needs', n: '중요 요소' }, { k: 'channel', n: '구매 방향' },
  { k: 'region', n: '지역' }, { k: 'buyTime', n: '구매 시기' },
  { k: 'plan', n: '선택 추천안' }, { k: 'amount', n: '선택안 금액', num: true },
  { k: 'consult', n: '상담표' }, { k: 'shop', n: '구매안내' }, { k: 'other', n: '추가 요청' },
];
const SEARCH_FIELDS = ['age', 'budget', 'items', 'mandatory', 'needs', 'plan', 'codes', 'other', 'channel', 'region'];

function buildList() {
  R = ROWS.map(r => {
    const a = r.answers || {}, p = selPlan(r);
    return {
      _r: r, _done: !!r.completed_at,
      created: r.created_at.slice(0, 16).replace('T', ' '),
      done: r.completed_at ? '완료' : `${r.max_step}단계`,
      device: L.devices[r.device] || r.device || '',
      age: lab('age', a.age), budget: lab('budget', a.budget), items: lab('items', a.items),
      mandatory: lab('mandatory', a.mandatory), needs: lab('needs', a.needs), channel: lab('channel', a.channel),
      region: [lab('region', a.region), a.district].filter(Boolean).join(' '), buyTime: lab('buyTime', a.buyTime),
      plan: p ? p.label : '', amount: p ? p.amount : null,
      consult: r.events.consult ? '●' : '', shop: r.events.shop ? '●' : '',
      other: a.other || '', codes: p ? p.lines.map(l => l.code).join(' ') : '',
    };
  });
  applyFilters();
}

function parseSearchTokens(raw) {
  // 공백/쉼표/줄바꿈/탭/세미콜론 으로 분리, 빈 토큰 제거, 소문자화
  return raw.split(/[\s,;]+/).map(t => t.trim().toLowerCase()).filter(Boolean);
}

function applyFilters() {
  const tokens = parseSearchTokens($('#s').value);
  const colEntries = Object.entries(colFilters);
  const onlyDone = $('#only-done').checked;
  F = R.filter(r => {
    if (onlyDone && !r._done) return false;
    if (tokens.length > 0) {
      // 토큰 중 하나라도 검색 필드 중 하나에 포함되면 매칭 (OR)
      const matched = tokens.some(tok => SEARCH_FIELDS.some(k => String(r[k] || '').toLowerCase().includes(tok)));
      if (!matched) return false;
    }
    // 컬럼별 필터 (AND, 부분일치, 대소문자 무시)
    for (const [cIdx, q] of colEntries) {
      const key = C[parseInt(cIdx)].k;
      const val = r[key] == null ? '' : String(r[key]).toLowerCase();
      if (!val.includes(q)) return false;
    }
    return true;
  });
  const parts = [];
  if (tokens.length > 1) parts.push(`${tokens.length}개 코드 검색`);
  if (colEntries.length > 0) parts.push(`컬럼필터 ${colEntries.length}개`);
  $('#tc').textContent = parts.join(' · ');
  $('#s').classList.toggle('multi', /\n/.test($('#s').value));
  doSort();
  renderList();
}

function doSort() {
  const k = C[sc].k;
  F.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (typeof av === 'number' || typeof bv === 'number') return sd * ((av ?? -1) - (bv ?? -1));
    return sd * String(av || '').localeCompare(String(bv || ''), 'ko');
  });
}

function renderList() {
  $('#respTable thead').innerHTML = '<tr>' + C.map((c, i) => {
    const cls = [colFilters[i] ? 'cf-active' : '', sc === i ? 'sorted' + (sd > 0 ? ' asc' : '') : ''].join(' ');
    return `<th class="${cls}" data-col="${i}">${c.n}</th>`;
  }).join('') + '</tr>';
  const MAXR = 1000;
  $('#respTable tbody').innerHTML = F.slice(0, MAXR).map((r, i) => '<tr data-i="' + i + '">' + C.map(c => {
    if (c.k === 'amount') return `<td class="num">${r.amount ? r.amount.toLocaleString('ko-KR') : ''}</td>`;
    if (c.k === 'consult' || c.k === 'shop') return `<td style="text-align:center">${r[c.k] ? '<span class="dot"></span>' : ''}</td>`;
    return `<td title="${esc(r[c.k])}">${esc(r[c.k])}</td>`;
  }).join('') + '</tr>').join('');
  $('#cnt').innerHTML = `전체 <b>${R.length.toLocaleString('ko-KR')}</b>건 중 <b>${F.length.toLocaleString('ko-KR')}</b>건 표시` + (F.length > MAXR ? ` (상위 ${MAXR}건만 표시)` : '');
}

$('#respTable thead').addEventListener('click', e => {
  const th = e.target.closest('th');
  if (!th) return;
  const i = Number(th.dataset.col);
  if (sc === i) sd = -sd; else { sc = i; sd = 1; }
  doSort(); renderList();
});
$('#respTable tbody').addEventListener('click', e => {
  const tr = e.target.closest('tr');
  if (tr) openDetail(F[Number(tr.dataset.i)]._r);
});
$('#s').addEventListener('input', applyFilters);
$('#only-done').addEventListener('change', applyFilters);
$('#reset').addEventListener('click', () => {
  $('#s').value = ''; colFilters = {}; sc = 0; sd = -1; $('#only-done').checked = true; applyFilters();
});

(function initColFilter() {
  const pop = document.createElement('div');
  pop.className = 'col-filter-popover';
  pop.innerHTML =
    '<div class="cfp-title" id="cfp-title"></div>' +
    '<input type="text" class="cfp-input" id="cfp-input" placeholder="검색어 입력 (부분일치)" />' +
    '<div class="cfp-hint">Enter 적용 · Esc 닫기 · 빈 값 적용 시 해제</div>' +
    '<div class="cfp-actions">' +
      '<button type="button" class="cfp-btn" id="cfp-clear">지우기</button>' +
      '<button type="button" class="cfp-btn apply" id="cfp-apply">적용</button>' +
    '</div>';
  document.body.appendChild(pop);
  const inputEl = pop.querySelector('#cfp-input');
  const titleEl = pop.querySelector('#cfp-title');
  let activeCol = null;

  function show(colIdx, th) {
    activeCol = colIdx;
    titleEl.textContent = C[colIdx].n + ' 검색';
    inputEl.value = colFilters[colIdx] || '';
    const rect = th.getBoundingClientRect();
    pop.style.top = (rect.bottom + window.scrollY + 4) + 'px';
    pop.style.left = (rect.left + window.scrollX) + 'px';
    pop.classList.add('show');
    setTimeout(() => {
      const r = pop.getBoundingClientRect();
      if (r.right > window.innerWidth - 10) pop.style.left = (window.innerWidth - r.width - 10 + window.scrollX) + 'px';
      inputEl.focus(); inputEl.select();
    }, 30);
  }
  function hide() { pop.classList.remove('show'); activeCol = null; }
  function applyCol() {
    if (activeCol === null) return;
    const q = inputEl.value.trim().toLowerCase();
    if (q) colFilters[activeCol] = q; else delete colFilters[activeCol];
    hide(); applyFilters();
  }
  function clearCol() {
    if (activeCol === null) return;
    delete colFilters[activeCol];
    inputEl.value = ''; hide(); applyFilters();
  }
  pop.querySelector('#cfp-apply').addEventListener('click', applyCol);
  pop.querySelector('#cfp-clear').addEventListener('click', clearCol);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); applyCol(); } else if (e.key === 'Escape') hide();
  });
  document.addEventListener('mousedown', e => { if (pop.classList.contains('show') && !pop.contains(e.target)) hide(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && pop.classList.contains('show')) hide(); });
  document.addEventListener('contextmenu', e => {
    const th = e.target.closest('th');
    if (!th || !th.closest('#respTable thead')) return;
    const colIdx = [...th.parentElement.cells].indexOf(th);
    if (colIdx < 0) return;
    e.preventDefault();
    show(colIdx, th);
  });
})();

// ── 상세 ────────────────────────────────────
function openDetail(r) {
  const a = r.answers || {};
  const kv = [['접속시각', r.created_at.replace('T', ' ').slice(0, 19)], ['완료시각', (r.completed_at || '미완료').replace('T', ' ').slice(0, 19)],
    ['기기 / 진입', `${L.devices[r.device] || r.device || ''} / ${L.entries[r.entry] || r.entry || '-'}`], ['도달 단계', r.completed_at ? '설문 완료' : `${r.max_step}단계`]];
  Object.keys(L.fields).forEach(f => { const v = lab(f, a[f]); if (v) kv.push([L.fields[f].name, v]); });
  Object.keys(L.numbers).forEach(n => { if (a[n]) kv.push([L.numbers[n], a[n]]); });
  Object.keys(L.texts || {}).forEach(t => { if (a[t]) kv.push([L.texts[t], a[t]]); });
  if (a.other) kv.push(['추가 요청', a.other]);
  const ev = Object.entries(r.events).filter(([k]) => L.events[k]).map(([k, v]) => `${L.events[k]} ${v}회`).join(' · ');
  if (ev) kv.push(['결과 화면 행동', ev]);
  const plans = (r.results || []).map((p, i) => {
    const sel = p === selPlan(r);
    return `<div class="plan${sel ? ' sel' : ''}"><div class="plan-h"><span>${esc(p.label)}${sel ? ' · 선택' : ''}</span><span>${(p.amount || 0).toLocaleString('ko-KR')}원</span></div>
      <table>${p.lines.map(l => `<tr><td>${esc(l.code)}</td><td>${esc(l.name)}</td><td>${esc(l.color)}</td><td class="num">${l.qty}개</td><td class="num">${(l.amount || 0).toLocaleString('ko-KR')}원</td></tr>`).join('')}</table></div>`;
  }).join('') || '<div class="empty">저장된 추천 결과가 없어요.</div>';
  $('#modal-body').innerHTML = `<div class="modal-head"><h2>응답 상세 <span style="font-weight:400;color:var(--muted);font-size:13px">${esc(r.sid.slice(0, 8))}</span></h2>
      <button class="btn sm" id="del">이 응답 삭제</button><button class="btn sm dark" id="close">닫기</button></div>
    <dl class="kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <h3 style="font-size:14px;margin-bottom:8px">추천 결과</h3>${plans}`;
  $('#modal').classList.add('show');
  $('#close').onclick = closeModal;
  $('#del').onclick = async () => {
    if (!confirm('이 응답을 삭제할까요? 테스트 응답 정리용이며 되돌릴 수 없어요.')) return;
    const res = await fetch('/api/admin/sessions/' + encodeURIComponent(r.sid), { method: 'DELETE', headers: { 'X-Requested-With': 'dk-admin' } });
    if (res.ok) { closeModal(); load(); } else alert('삭제하지 못했어요 (' + res.status + ')');
  };
}
function closeModal() { $('#modal').classList.remove('show'); }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── 비밀번호 변경 ───────────────────────────
$('#pw-open').addEventListener('click', () => {
  $('#modal-body').innerHTML = `<div class="modal-head"><h2>관리자 비밀번호 변경</h2><button class="btn sm dark" id="close">닫기</button></div>
    <form id="pw-form" class="pw-form">
      <label>현재 비밀번호<input type="password" id="pw-cur" autocomplete="current-password" required></label>
      <label>새 비밀번호 (8자 이상)<input type="password" id="pw-new" autocomplete="new-password" minlength="8" required></label>
      <label>새 비밀번호 확인<input type="password" id="pw-new2" autocomplete="new-password" minlength="8" required></label>
      <div class="err" id="pw-err"></div>
      <button class="btn primary" type="submit">변경하기</button>
      <p class="note">바꾼 뒤에는 새 비밀번호로만 로그인돼요. 다른 담당자에게도 알려 주세요.</p>
    </form>`;
  $('#modal').classList.add('show');
  $('#close').onclick = closeModal;
  $('#pw-cur').focus();
  $('#pw-form').onsubmit = async e => {
    e.preventDefault();
    const err = $('#pw-err');
    if ($('#pw-new').value !== $('#pw-new2').value) { err.textContent = '새 비밀번호 두 칸이 서로 달라요.'; return; }
    const r = await fetch('/api/admin/password', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'dk-admin' },
      body: JSON.stringify({ current: $('#pw-cur').value, new: $('#pw-new').value }),
    });
    if (r.ok) { closeModal(); alert('비밀번호를 바꿨어요. 다음 로그인부터 새 비밀번호를 쓰세요.'); return; }
    const d = await r.json().catch(() => ({}));
    err.textContent = d.detail || `변경하지 못했어요 (${r.status})`;
  };
});

// ── QR ──────────────────────────────────────
function qrSvg(text) {
  const qr = new LocalQRCode(-1, LocalQRLevel.M);
  qr.addData(text); qr.make();
  const n = qr.getModuleCount(), s = n + 8;
  let d = '';
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (qr.isDark(y, x)) d += `M${x + 4},${y + 4}h1v1h-1z`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${s} ${s}" shape-rendering="crispEdges"><rect width="${s}" height="${s}" fill="white"/><path d="${d}" fill="black"/></svg>`;
}
async function savePng(svg, name) {
  const uri = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  const img = new Image();
  await new Promise((ok, fail) => { img.onload = ok; img.onerror = fail; img.src = uri; });
  const cv = document.createElement('canvas'); cv.width = cv.height = 1200;
  const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false; ctx.drawImage(img, 0, 0, 1200, 1200);
  URL.revokeObjectURL(uri);
  const a = document.createElement('a'); a.href = cv.toDataURL('image/png'); a.download = name; a.click();
}
function renderQR() {
  const base = location.origin;
  const list = [
    { t: '고객용 · 첫 화면', d: '매장 POP·온라인 배너용. 서비스 소개부터 시작해요.', u: base + '/', f: 'desker_studyroom_qr_home.png' },
    { t: '관리자 페이지', d: '담당자 휴대폰 접속용. 비밀번호가 필요해요. 외부에 공유하지 마세요.', u: base + '/admin', f: 'desker_studyroom_qr_admin.png' },
  ];
  $('#qrs').innerHTML = list.map((x, i) => `<div class="card"><h3>${x.t}</h3><div class="sub">${x.d}</div>
    <div class="qr-box">${qrSvg(x.u)}</div><div class="url">${esc(x.u)}</div>
    <button class="btn sm dark" data-png="${i}">QR 이미지 저장</button> <button class="btn sm" data-copy="${i}">링크 복사</button></div>`).join('');
  $('#qrs').onclick = e => {
    const p = e.target.closest('[data-png]'), c = e.target.closest('[data-copy]');
    if (p) savePng(qrSvg(list[p.dataset.png].u), list[p.dataset.png].f);
    if (c) navigator.clipboard.writeText(list[c.dataset.copy].u).then(() => { c.textContent = '복사됨'; setTimeout(() => { c.textContent = '링크 복사'; }, 1200); });
  };
}

// ── 탭·기간 ─────────────────────────────────
document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'pane-' + b.dataset.tab));
  if (b.dataset.tab === 'data' && window.dkDataTab) window.dkDataTab.open();
}));
function setRange(v) {
  const today = new Date();
  if (v === 'all') { $('#from').value = ''; $('#to').value = ''; }
  else { const f = new Date(today); f.setDate(f.getDate() - Number(v) + (v === '0' ? 0 : 1)); $('#from').value = ymd(f); $('#to').value = ymd(today); }
  document.querySelectorAll('[data-range]').forEach(b => b.classList.toggle('on', b.dataset.range === v));
}
document.querySelectorAll('[data-range]').forEach(b => b.addEventListener('click', () => { setRange(b.dataset.range); load(); }));
['#from', '#to'].forEach(s => $(s).addEventListener('change', () => {
  document.querySelectorAll('[data-range]').forEach(b => b.classList.remove('on')); load();
}));
$('#reload').addEventListener('click', load);
$('#export').addEventListener('click', () => { location.href = '/api/admin/export.xlsx?' + rangeQuery(); });

(async function boot() {
  const meta = await api('/api/admin/meta');
  L = meta.labels;
  const st = $('#storage');
  st.textContent = meta.storage === 'SQLite' ? '임시 저장소(SQLite)' : 'DB 연결됨';
  if (meta.storage === 'SQLite') st.classList.add('warn');
  setRange('all');
  renderQR();
  await load();
})();
