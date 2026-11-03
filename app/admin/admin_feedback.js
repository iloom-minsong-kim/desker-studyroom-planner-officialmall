/* DESKER 학생방 플래너 — 관리자 '고객 의견' 탭 (admin.js 의 $·esc·api·rangeQuery·openDetail·ROWS 사용) */
'use strict';
(function () {
  let FB = [], FL = null, FR = [], FF = [];
  let fsc = 0, fsd = -1, fbColFilters = {};
  const FC = [
    { k: 'created', n: '받은 시각' }, { k: 'cat', n: '의견 종류' }, { k: 'message', n: '내용' },
    { k: 'place', n: '보낸 화면' }, { k: 'device', n: '기기' }, { k: 'done', n: '설문 완료' }, { k: 'status', n: '처리 상태' },
  ];
  const FB_SEARCH = ['cat', 'message', 'place', 'device', 'status'];

  async function fbLoad() {
    const d = await api('/api/admin/feedback?' + rangeQuery());
    FB = d.rows; FL = d.labels;
    if ($('#fb-cat').options.length === 1) {
      Object.entries(FL.categories).forEach(([k, v]) => $('#fb-cat').add(new Option(v, k)));
      Object.entries(FL.status).forEach(([k, v]) => $('#fb-st').add(new Option(v, k)));
    }
    fbBuild();
  }

  function fbBuild() {
    FR = FB.map(r => ({
      _r: r,
      created: r.created_at.slice(0, 16).replace('T', ' '),
      cat: FL.categories[r.category] || r.category,
      message: r.message,
      place: FL.places[r.place] || r.place || '',
      device: (L && L.devices[r.device]) || r.device || '',
      done: r.completed_at ? '완료' : '',
      status: FL.status[r.status] || r.status,
    }));
    const n = k => FB.filter(r => r.category === k).length;
    const fresh = FB.filter(r => r.status === 'new').length;
    $('#fb-kpis').innerHTML = kpi('받은 의견', FB.length.toLocaleString('ko-KR'), '선택한 기간') +
      kpi('새 의견', fresh.toLocaleString('ko-KR'), '아직 확인하지 않은 의견') +
      Object.keys(FL.categories).map(k => kpi(FL.categories[k], n(k).toLocaleString('ko-KR'), '')).join('');
    $('#fb-new').textContent = fresh ? String(fresh) : '';
    fbApply();
  }

  function fbApply() {
    const tokens = parseSearchTokens($('#fb-s').value);
    const colEntries = Object.entries(fbColFilters);
    const cat = $('#fb-cat').value, st = $('#fb-st').value;
    FF = FR.filter(r => {
      if (cat && r._r.category !== cat) return false;
      if (st && r._r.status !== st) return false;
      if (tokens.length > 0 && !tokens.some(tok => FB_SEARCH.some(k => String(r[k] || '').toLowerCase().includes(tok)))) return false;
      for (const [cIdx, q] of colEntries) {
        const val = r[FC[parseInt(cIdx)].k] == null ? '' : String(r[FC[parseInt(cIdx)].k]).toLowerCase();
        if (!val.includes(q)) return false;
      }
      return true;
    });
    const parts = [];
    if (tokens.length > 1) parts.push(`${tokens.length}개 코드 검색`);
    if (colEntries.length > 0) parts.push(`컬럼필터 ${colEntries.length}개`);
    $('#fb-tc').textContent = parts.join(' · ');
    $('#fb-s').classList.toggle('multi', /\n/.test($('#fb-s').value));
    const k = FC[fsc].k;
    FF.sort((a, b) => fsd * String(a[k] || '').localeCompare(String(b[k] || ''), 'ko'));
    fbRender();
  }

  function fbRender() {
    $('#fbTable thead').innerHTML = '<tr>' + FC.map((c, i) => {
      const cls = [fbColFilters[i] ? 'cf-active' : '', fsc === i ? 'sorted' + (fsd > 0 ? ' asc' : '') : ''].join(' ');
      return `<th class="${cls}" data-col="${i}">${c.n}</th>`;
    }).join('') + '</tr>';
    $('#fbTable tbody').innerHTML = FF.map((r, i) => '<tr data-i="' + i + '">' + FC.map(c => {
      if (c.k === 'status') {
        return `<td><select class="fb-status ${esc(r._r.status)}" data-id="${r._r.id}">` +
          Object.entries(FL.status).map(([k, v]) => `<option value="${k}"${k === r._r.status ? ' selected' : ''}>${esc(v)}</option>`).join('') + '</select></td>';
      }
      if (c.k === 'done') return `<td style="text-align:center">${r.done ? '<span class="dot"></span>' : ''}</td>`;
      return `<td${c.k === 'message' ? ' class="fb-msg"' : ''} title="${esc(r[c.k])}">${esc(r[c.k])}</td>`;
    }).join('') + '</tr>').join('') || `<tr><td colspan="${FC.length}" class="empty" style="text-align:center">아직 받은 의견이 없어요.</td></tr>`;
    $('#fb-cnt').innerHTML = `전체 <b>${FR.length.toLocaleString('ko-KR')}</b>건 중 <b>${FF.length.toLocaleString('ko-KR')}</b>건 표시`;
  }

  async function setStatus(id, status) {
    const res = await fetch(`/api/admin/feedback/${id}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'dk-admin' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) { alert('처리 상태를 바꾸지 못했어요 (' + res.status + ')'); return false; }
    const r = FB.find(x => x.id === id);
    if (r) r.status = status;
    fbBuild();
    return true;
  }

  function fbDetail(r) {
    const sess = (typeof ROWS !== 'undefined' ? ROWS : []).find(x => x.sid === r.sid);
    const kv = [['받은 시각', r.created_at.replace('T', ' ').slice(0, 19)], ['의견 종류', FL.categories[r.category] || r.category],
      ['보낸 화면', FL.places[r.place] || r.place || '-'], ['기기', (L && L.devices[r.device]) || r.device || ''],
      ['설문 완료', r.completed_at ? '완료' : '미완료'], ['응답ID', r.sid.slice(0, 8)]];
    $('#modal-body').innerHTML = `<div class="modal-head"><h2>고객 의견</h2>
        ${sess ? '<button class="btn sm" id="fb-resp">이 사람의 응답 보기</button>' : ''}
        <button class="btn sm" id="fb-del">의견 삭제</button><button class="btn sm dark" id="close">닫기</button></div>
      <div class="fb-full">${esc(r.message)}</div>
      <dl class="kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
        <dt>처리 상태</dt><dd>${Object.entries(FL.status).map(([k, v]) => `<button class="btn sm${k === r.status ? ' on' : ''}" data-fbst="${k}">${esc(v)}</button>`).join(' ')}</dd></dl>`;
    $('#modal').classList.add('show');
    $('#close').onclick = closeModal;
    if (sess) $('#fb-resp').onclick = () => openDetail(sess);
    $('#modal-body').querySelectorAll('[data-fbst]').forEach(b => {
      b.onclick = async () => { if (await setStatus(r.id, b.dataset.fbst)) fbDetail(FB.find(x => x.id === r.id) || r); };
    });
    $('#fb-del').onclick = async () => {
      if (!confirm('이 의견을 삭제할까요? 되돌릴 수 없어요.')) return;
      const res = await fetch('/api/admin/feedback/' + r.id, { method: 'DELETE', headers: { 'X-Requested-With': 'dk-admin' } });
      if (res.ok) { closeModal(); fbLoad(); } else alert('삭제하지 못했어요 (' + res.status + ')');
    };
    // 새 의견은 열어 보면 '확인함'으로
    if (r.status === 'new') setStatus(r.id, 'seen');
  }

  $('#fbTable thead').addEventListener('click', e => {
    const th = e.target.closest('th');
    if (!th) return;
    const i = Number(th.dataset.col);
    if (fsc === i) fsd = -fsd; else { fsc = i; fsd = 1; }
    fbApply();
  });
  $('#fbTable tbody').addEventListener('change', e => {
    const s = e.target.closest('select.fb-status');
    if (s) setStatus(Number(s.dataset.id), s.value);
  });
  $('#fbTable tbody').addEventListener('click', e => {
    if (e.target.closest('select')) return;
    const tr = e.target.closest('tr[data-i]');
    if (tr) fbDetail(FF[Number(tr.dataset.i)]._r);
  });
  $('#fb-s').addEventListener('input', fbApply);
  $('#fb-cat').addEventListener('change', fbApply);
  $('#fb-st').addEventListener('change', fbApply);
  $('#fb-reset').addEventListener('click', () => {
    $('#fb-s').value = ''; $('#fb-cat').value = ''; $('#fb-st').value = ''; fbColFilters = {}; fsc = 0; fsd = -1; fbApply();
  });
  $('#fb-export').addEventListener('click', () => { location.href = '/api/admin/feedback.xlsx?' + rangeQuery(); });

  (function initFbColFilter() {
    const pop = document.createElement('div');
    pop.className = 'col-filter-popover';
    pop.innerHTML =
      '<div class="cfp-title"></div>' +
      '<input type="text" class="cfp-input" placeholder="검색어 입력 (부분일치)" />' +
      '<div class="cfp-hint">Enter 적용 · Esc 닫기 · 빈 값 적용 시 해제</div>' +
      '<div class="cfp-actions">' +
        '<button type="button" class="cfp-btn" data-cfp="clear">지우기</button>' +
        '<button type="button" class="cfp-btn apply" data-cfp="apply">적용</button>' +
      '</div>';
    document.body.appendChild(pop);
    const inputEl = pop.querySelector('.cfp-input');
    const titleEl = pop.querySelector('.cfp-title');
    let activeCol = null;

    function show(colIdx, th) {
      activeCol = colIdx;
      titleEl.textContent = FC[colIdx].n + ' 검색';
      inputEl.value = fbColFilters[colIdx] || '';
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
      if (q) fbColFilters[activeCol] = q; else delete fbColFilters[activeCol];
      hide(); fbApply();
    }
    function clearCol() {
      if (activeCol === null) return;
      delete fbColFilters[activeCol];
      inputEl.value = ''; hide(); fbApply();
    }
    pop.querySelector('[data-cfp="apply"]').addEventListener('click', applyCol);
    pop.querySelector('[data-cfp="clear"]').addEventListener('click', clearCol);
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); applyCol(); } else if (e.key === 'Escape') hide();
    });
    document.addEventListener('mousedown', e => { if (pop.classList.contains('show') && !pop.contains(e.target)) hide(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && pop.classList.contains('show')) hide(); });
    document.addEventListener('contextmenu', e => {
      const th = e.target.closest('th');
      if (!th || !th.closest('#fbTable thead')) return;
      const colIdx = [...th.parentElement.cells].indexOf(th);
      if (colIdx < 0) return;
      e.preventDefault();
      show(colIdx, th);
    });
  })();

  // 기간·새로고침은 admin.js 와 같은 버튼을 따른다
  $('#reload').addEventListener('click', fbLoad);
  document.querySelectorAll('[data-range]').forEach(b => b.addEventListener('click', fbLoad));
  ['#from', '#to'].forEach(s => $(s).addEventListener('change', fbLoad));
  window.dkFeedbackTab = { load: fbLoad };
  // admin.js 의 boot 가 L(라벨)을 받은 뒤 불러온다
  (function wait() { if (L) fbLoad().catch(() => {}); else setTimeout(wait, 100); })();
})();
