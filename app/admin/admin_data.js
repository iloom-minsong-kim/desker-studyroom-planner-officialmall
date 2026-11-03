/* DESKER 학생방 플래너 — 관리자 '데이터 관리' 탭 (제품·판매량·제품특성·제품가이드·적용 이력) */
'use strict';
(function () {
  const $ = s => document.querySelector(s);
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const H = { 'X-Requested-With': 'dk-admin' };
  let D = null;            // /api/admin/data 응답
  let sub = 'products';    // 현재 하위 탭
  const dirty = { products: false, sales: false, features: false, rules: false };
  const view = {};
  ['products', 'sales', 'features', 'rules', 'guides'].forEach(t => { view[t] = { q: '', cf: {}, sc: null, sd: 1 }; });
  // 제품가이드 PDF 표(읽기 전용) — 같은 검색·우클릭 필터·정렬을 쓴다
  const GCOLS = [{ k: 'name', label: '파일 이름' }, { k: 'mb', label: '크기(MB)', num: true }, { k: 'created', label: '올린 시각' },
    { k: 'linked', label: '연결 제품' }, { k: 'dup', label: '중복' }];
  const colsOf = tab => COLS[tab] || GCOLS;
  function guideRows() {
    const byHash = {}, byName = {}, linked = {};
    D.guides.forEach(g => { if (g.sha256) byHash[g.sha256] = (byHash[g.sha256] || 0) + 1; const n = g.name.trim().toLowerCase(); byName[n] = (byName[n] || 0) + 1; });
    D.rows.features.forEach(r => { if (r.guide) (linked[r.guide] = linked[r.guide] || []).push(r.code); });
    return D.guides.map(g => {
      const same = g.sha256 ? byHash[g.sha256] : 1, nm = byName[g.name.trim().toLowerCase()];
      const dup = [same > 1 ? `같은 파일 ${same}개` : '', nm > 1 ? `같은 이름 ${nm}개` : ''].filter(Boolean).join(' · ');
      const codes = linked[g.id] || [];
      return { id: g.id, name: g.name, mb: (g.size / 1024 / 1024).toFixed(1), created: g.created_at.slice(0, 16).replace('T', ' '),
        linked: codes.length ? `${codes.length}개 · ${codes.join(', ')}` : '0개', dup };
    });
  }

  const COLS = {
    products: [
      { k: 'unit', t: 'select', o: 'unit', w: 80 }, { k: 'cat', t: 'select', o: 'cat', w: 130 },
      { k: 'code', w: 120 }, { k: 'name', w: 380 }, { k: 'official_url', w: 300 },
      { k: 'price', w: 100, num: true }, { k: 'promo', t: 'check', w: 80 }, { k: 'promo_price', w: 100, num: true },
      { k: 'promo_start', t: 'date', w: 130 }, { k: 'promo_end', t: 'date', w: 130 }, { k: '_image', label: '이미지 파일', w: 150, ro: true }],
    sales: [
      { k: 'code', w: 140 }, { k: 'group', t: 'select', o: 'group', w: 90 }, { k: 'name', w: 380 },
      { k: 'monthly', w: 130, num: true }],
    features: [
      { k: 'code', w: 120 }, { k: '_name', label: '명칭(제품 탭)', w: 240, ro: true }, { k: 'tier', w: 60, num: true },
      { k: 'width', w: 80, num: true }, { k: 'depth', w: 80, num: true }, { k: 'wall', t: 'select', o: 'wall', w: 90 },
      { k: 'min_ceiling', w: 90, num: true }, { k: 'motion', w: 56 }, { k: 'multi', w: 56 }, { k: 'light', w: 56 },
      { k: 'colors', w: 150 }, { k: 'features', w: 280 }, { k: 'checks', w: 280 }, { k: 'guide', t: 'guide', w: 200 }],
    rules: [
      { k: 'on', t: 'fixed', o: ['Y', 'N'], w: 60 }, { k: 'field', t: 'question', w: 170 },
      { k: 'values', t: 'multi', src: r => D.options.questions[r.field] || [], w: 220 },
      { k: 'cats', t: 'multi', src: () => D.options.catsOnly, w: 200 },
      { k: 'target_type', t: 'select', o: 'target_type', w: 100 },
      { k: 'target', t: 'target', w: 220 }, { k: 'level', t: 'select', o: 'level', w: 100 }, { k: 'memo', w: 260 }],
  };
  const label = (tab, c) => c.label || D.headers[tab][c.k] || c.k;

  async function api(url, opt = {}) {
    const r = await fetch(url, { credentials: 'same-origin', ...opt, headers: { ...(opt.headers || {}), ...H } });
    if (r.status === 401) { location.reload(); throw new Error('login'); }
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    return d;
  }
  function toast(msg, bad) {
    const t = $('#dm-toast'); t.textContent = msg; t.className = 'dm-toast show' + (bad ? ' bad' : '');
    clearTimeout(toast.t); toast.t = setTimeout(() => { t.className = 'dm-toast'; }, 3500);
  }

  async function load() {
    D = await api('/api/admin/data');
    Object.keys(dirty).forEach(k => { dirty[k] = false; });
    D.rows.products.forEach((r, i) => { r._i = i; });
    renderShell();
  }

  // ── 상단 상태 + 하위 탭 ──
  function renderShell() {
    const a = D.active;
    $('#dm-status').innerHTML = `<div><b>고객 페이지 적용 중:</b> ${a ? `v${a.id} · ${esc(a.created_at.slice(0, 16).replace('T', ' '))} · ${esc(a.note || '')}` : '없음'}</div>
      <div class="dm-check">${D.errors.length ? `<span class="bad">오류 ${D.errors.length}</span>` : '<span class="ok">오류 없음</span>'}${D.warnings.length ? ` · <span class="warn">확인 ${D.warnings.length}</span>` : ''}</div>`;
    const counts = { products: D.rows.products.length, sales: D.rows.sales.length, features: D.rows.features.length, rules: D.rows.rules.length, guides: D.guides.length, history: D.versions.length };
    $('#dm-subtabs').innerHTML = [['products', '제품'], ['sales', '책상세트 판매량'], ['features', '제품특성'], ['rules', '고객 기반 데이터'], ['guides', '제품가이드 PDF'], ['history', '적용 이력']]
      .map(([k, n]) => `<button class="dm-sub${sub === k ? ' on' : ''}" data-sub="${k}">${n}${counts[k] != null ? ` <small>${counts[k]}</small>` : ''}${dirty[k] ? ' <i class="dm-dot"></i>' : ''}</button>`).join('');
    renderBody();
  }
  function renderBody() {
    if (sub in COLS) return renderGrid(sub);
    if (sub === 'guides') return renderGuides();
    if (sub === 'history') return renderHistory();
  }

  // ── 표(그리드) ──
  function tokens(q) { return q.split(/[\s,;]+/).map(t => t.trim().toLowerCase()).filter(Boolean); }
  function cellValue(tab, r, c) {
    if (c.k === '_image') return D.images[r.code] ? '있음' : '없음';
    if (c.k === '_name') { const p = D.rows.products.find(x => x.code === r.code); return p ? p.name : '(제품 탭에 없음)'; }
    if (c.k === 'guide' && 'guide' in r) { const g = D.guides.find(x => x.id === r.guide); return g ? g.name : ''; }
    return r[c.k] ?? '';
  }
  function filtered(tab) {
    const v = view[tab], toks = tokens(v.q), rows = (tab === 'guides' ? guideRows() : D.rows[tab]).map((r, i) => ({ r, i }));
    const CL = colsOf(tab);
    let out = rows.filter(({ r }) => {
      if (tab === 'guides' && v.dupOnly && !r.dup) return false;
      if (toks.length && !toks.some(t => CL.some(c => String(cellValue(tab, r, c)).toLowerCase().includes(t)))) return false;
      for (const [ci, q] of Object.entries(v.cf)) if (!String(cellValue(tab, r, CL[ci])).toLowerCase().includes(q)) return false;
      return true;
    });
    if (v.sc != null) {
      const c = CL[v.sc];
      out.sort((a, b) => {
        const x = cellValue(tab, a.r, c), y = cellValue(tab, b.r, c);
        return v.sd * (c.num ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : String(x).localeCompare(String(y), 'ko'));
      });
    }
    return out;
  }
  function inputFor(tab, r, c, i) {
    if (c.k === '_image') {
      const u = D.images[r.code];
      return `<div class="dm-img">${u ? `<img src="${esc(u)}" alt="">` : '<span class="dm-noimg">없음</span>'}<button class="btn sm" data-img="${i}">올리기</button>${u ? `<button class="btn sm" data-imgdel="${i}">삭제</button>` : ''}</div>`;
    }
    if (c.ro) return `<span class="dm-ro" title="${esc(cellValue(tab, r, c))}">${esc(cellValue(tab, r, c))}</span>`;
    if (c.t === 'select') {
      const opts = D.options[c.o];
      return `<select data-i="${i}" data-k="${c.k}">${opts.includes(r[c.k]) ? '' : `<option value="${esc(r[c.k])}">${esc(r[c.k] || '선택')}</option>`}${opts.map(o => `<option${o === r[c.k] ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    }
    if (c.t === 'fixed' || c.t === 'question') {
      const opts = c.t === 'fixed' ? c.o : Object.keys(D.options.questions);
      return `<select data-i="${i}" data-k="${c.k}">${opts.includes(r[c.k]) ? '' : `<option value="${esc(r[c.k])}">${esc(r[c.k] || '선택')}</option>`}${opts.map(o => `<option${o === r[c.k] ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    }
    if (c.t === 'multi' || (c.t === 'target' && r.target_type === '특성')) {
      return `<button type="button" class="dm-multi" data-mi="${i}" data-mk="${c.k}">${esc(r[c.k] || '선택')}</button>`;
    }
    if (c.t === 'target' && (r.target_type || '전체') === '전체') return '<span class="dm-ro">—</span>';
    if (c.t === 'check') return `<input type="checkbox" data-i="${i}" data-k="${c.k}" data-check="1"${r[c.k] === 'Y' ? ' checked' : ''}>`;
    if (c.t === 'date') return `<input type="date" data-i="${i}" data-k="${c.k}" value="${esc(r[c.k])}">`;
    if (c.t === 'guide') {
      return `<select data-i="${i}" data-k="guide"><option value="">없음</option>${D.guides.map(g => `<option value="${g.id}"${g.id === r.guide ? ' selected' : ''}>${esc(g.name)}</option>`).join('')}</select>`;
    }
    return `<input data-i="${i}" data-k="${c.k}" value="${esc(r[c.k])}"${c.num ? ' inputmode="decimal"' : ''}>`;
  }
  function renderGrid(tab) {
    const v = view[tab], rows = filtered(tab), parts = [];
    const tk = tokens(v.q), nf = Object.keys(v.cf).length;
    if (tk.length > 1) parts.push(`${tk.length}개 코드 검색`);
    if (nf) parts.push(`컬럼필터 ${nf}개`);
    const help = {
      products: '공식몰 프로모션: [프로모션]을 체크하고 혜택가·기간(시작일~종료일, 비우면 상시)을 넣으면 결과 페이지에서 혜택 구성으로 먼저 보여줘요. 체크하지 않은 제품은 혜택 외 구성으로만 보여요. 판매단위·구분은 목록에서 고르세요. 구분이 "책상+의자 세트"인 행은 명칭(책상세트 명칭 + 의자 이름)으로 구성을 자동 인식해요. 이 탭에 없는 제품은 추천하지 않아요.',
      sales: '책상세트·모션데스크 세트의 월평균 판매량이에요. 일반·모션을 따로 비교해 판매량이 많을수록 우선 추천해요(조건이 맞는 제품 안에서).',
      rules: '설문 답변에 따라 제품 순서를 바꾸는 선호 규칙이에요. 등급: 우선 추천 > 추천 > (보통) > 비추천, 제외는 그 제품을 빼요(빼면 후보가 없을 땐 무시). 예산·꼭 필요한 가구·설치 조건은 바꾸지 않고, 조건을 통과한 제품들의 순서만 바꿔요. 대상 = 대상 구분(선택) 그리고 대상 조건(코드·특성·명칭 포함).',
      features: '추천 조건(단수·폭·벽고정·천장·색상)에 쓰는 값이에요. 모션·멀티·조명은 Y로 표시하고, 특징·구매 전 확인은 " | "로 나눠 적어요. 제품가이드는 PDF 탭에서 올린 파일을 고르세요.',
    }[tab];
    swapBody(`<p class="note dm-help">${help}</p>
      <div class="list-filters dm-tools">
        <textarea id="dm-q" rows="1" placeholder="여러 코드는 공백·쉼표·줄바꿈으로 구분 · 모든 칸에서 검색">${esc(v.q)}</textarea>
        <button class="btn sm" data-act="reset">초기화</button>
        <span class="spacer"></span>
        <button class="btn sm" data-act="add">행 추가</button>
        <button class="btn sm" data-act="del">선택 삭제</button>
        ${tab === 'products' ? '<button class="btn sm" data-act="bulkimg">사진 여러 장 올리기</button>' : ''}
        ${tab === 'rules' ? '<button class="btn sm dark" data-act="compare">시험 설문 비교</button>' : ''}
        <button class="btn sm" data-act="export">엑셀 내려받기</button>
        <button class="btn sm" data-act="import">엑셀 올리기</button>
        <button class="btn sm primary" data-act="save">저장${dirty[tab] ? ' ●' : ''}</button>
      </div>
      <div class="statusbar"><span>전체 <b>${D.rows[tab].length}</b>행 중 <b>${rows.length}</b>행 표시${dirty[tab] ? ' · <b>저장 안 된 변경이 있어요</b>' : ''}</span><span>${parts.join(' · ')}</span></div>
      <div class="table-wrap dm-wrap"><table class="std dm-grid" id="dm-grid" data-tab="${tab}"><thead><tr><th class="dm-chk"><input type="checkbox" id="dm-all"></th>${COLS[tab].map((c, ci) =>
        `<th data-col="${ci}" style="min-width:${c.w}px" class="${v.cf[ci] ? 'cf-active' : ''}${v.sc === ci ? ' sorted' + (v.sd > 0 ? ' asc' : '') : ''}">${esc(label(tab, c))}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(({ r, i }) => `<tr><td class="dm-chk"><input type="checkbox" data-sel="${i}"></td>${COLS[tab].map(c => `<td>${inputFor(tab, r, c, i)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="note">헤더 좌클릭 = 정렬 · 우클릭 = 해당 컬럼 검색 · 저장 후 [검사·미리보기] → [고객 페이지에 적용]을 눌러야 고객 화면에 반영돼요.</p>`);
    $('#dm-q').classList.toggle('multi', /\n/.test(v.q));
  }

  // 검색 중에는 검색창(#dm-q)을 그대로 두고 나머지만 바꾼다 — 검색창을 새로 만들면 한글 조합이 끊겨 'ㅇㅏ'처럼 입력됨
  function swapBody(html) {
    const body = $('#dm-body'), q = $('#dm-q'), keep = q && q.closest('.dm-tools');
    if (!q || document.activeElement !== q || !keep) { body.innerHTML = html; return; }
    const t = document.createElement('div'); t.innerHTML = html;
    const tools = t.querySelector('.dm-tools');
    if (!tools || !tools.querySelector('#dm-q')) { body.innerHTML = html; return; }
    [...keep.children].forEach(ch => { if (ch !== q) ch.remove(); });
    [...tools.children].forEach(ch => { if (ch.id !== 'dm-q') keep.appendChild(ch); });
    [...body.children].forEach(ch => { if (ch !== keep) ch.remove(); });
    const kids = [...t.children], at = kids.indexOf(tools);
    kids.slice(0, at).forEach(k => body.insertBefore(k, keep));
    kids.slice(at + 1).forEach(k => body.appendChild(k));
  }

  // 입력 → 상태 반영
  document.addEventListener('input', e => {
    const el = e.target;
    if (el.id === 'dm-q') { view[sub].q = el.value; renderBody(); return; }
    if (!el.closest('#dm-grid') || el.dataset.i == null || el.dataset.check) return;
    D.rows[sub][+el.dataset.i][el.dataset.k] = el.value;
    if (!dirty[sub]) { dirty[sub] = true; renderShellKeepGrid(); }
  });
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.id === 'dm-all') { document.querySelectorAll('[data-sel]').forEach(x => { x.checked = el.checked; }); return; }
    if (el.id === 'dm-duponly') { view.guides.dupOnly = el.checked; renderGuides(); return; }
    if (el.dataset.check && el.closest('#dm-grid')) {
      D.rows[sub][+el.dataset.i][el.dataset.k] = el.checked ? 'Y' : '';
      if (!dirty[sub]) { dirty[sub] = true; renderShellKeepGrid(); }
      return;
    }
    if (el.tagName === 'SELECT' && el.closest('#dm-grid') && el.dataset.i != null) {
      const row = D.rows[sub][+el.dataset.i];
      row[el.dataset.k] = el.value;
      if (sub === 'rules' && el.dataset.k === 'field') row.values = '';
      if (sub === 'rules' && el.dataset.k === 'target_type') row.target = '';
      if (!dirty[sub]) { dirty[sub] = true; renderShellKeepGrid(); }
      if (sub === 'rules' && ['field', 'target_type'].includes(el.dataset.k)) renderGrid('rules');
    }
  });
  function renderShellKeepGrid() {
    document.querySelectorAll('.dm-sub').forEach(b => { if (b.dataset.sub === sub && !b.querySelector('.dm-dot')) b.insertAdjacentHTML('beforeend', ' <i class="dm-dot"></i>'); });
    const s = document.querySelector('[data-act="save"]'); if (s) s.textContent = '저장 ●';
  }

  // 버튼
  document.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b || !b.closest('#pane-data')) return;
    try {
      if (b.dataset.sub) { sub = b.dataset.sub; renderShell(); return; }
      const th = e.target.closest('#dm-grid thead th[data-col]');
      if (th) return;
      const act = b.dataset.act;
      if (act === 'reset') { view[sub] = { q: '', cf: {}, sc: null, sd: 1 }; renderBody(); }
      if (act === 'add') { const r = Object.fromEntries(Object.keys(D.headers[sub]).map(k => [k, ''])); D.rows[sub].unshift(r); dirty[sub] = true; view[sub] = { q: '', cf: {}, sc: null, sd: 1 }; renderShell(); }
      if (act === 'del') {
        const sel = [...document.querySelectorAll('[data-sel]:checked')].map(x => +x.dataset.sel);
        if (!sel.length) return toast('삭제할 행을 먼저 선택해 주세요.', true);
        if (!confirm(`${sel.length}행을 삭제할까요? (저장해야 반영돼요)`)) return;
        D.rows[sub] = D.rows[sub].filter((_, i) => !sel.includes(i)); dirty[sub] = true; renderShell();
      }
      if (act === 'save') await save(sub);
      if (act === 'export') { location.href = `/api/admin/data/export/${sub}.xlsx`; }
      if (act === 'import') pickFile('.xlsx', false, async fs => {
        const fd = new FormData(); fd.append('file', fs[0]);
        const d = await api(`/api/admin/data/import/${sub}`, { method: 'POST', body: fd });
        if (!confirm(`엑셀에서 ${d.count}행을 읽었어요 (인식한 열: ${d.matched.join(', ')}).\n지금 표를 이 내용으로 바꿀까요? (저장해야 반영돼요)`)) return;
        D.rows[sub] = d.rows; dirty[sub] = true; renderShell();
      });
      if (act === 'bulkimg') pickFile('image/webp,image/png,image/jpeg', true, fs => uploadImages(fs, ''));
      if (b.dataset.img != null) { const r = D.rows.products[+b.dataset.img]; if (!r.code) return toast('코드를 먼저 입력해 주세요.', true); pickFile('image/webp,image/png,image/jpeg', false, fs => uploadImages(fs, r.code)); }
      if (b.dataset.imgdel != null) {
        const r = D.rows.products[+b.dataset.imgdel]; if (!confirm(`${r.code} 사진을 지울까요?`)) return;
        await api('/api/admin/files/images/' + encodeURIComponent(r.code), { method: 'DELETE' }).catch(() => ({}));
        delete D.images[r.code]; renderGrid('products');
      }
      if (b.dataset.gdel) {
        if (!confirm('이 PDF를 삭제할까요? 연결된 제품특성의 제품가이드도 비워져요(저장 후 적용 필요).')) return;
        await api('/api/admin/files/guides/' + b.dataset.gdel, { method: 'DELETE' }).catch(() => ({}));
        D.rows.features.forEach(r => { if (r.guide === b.dataset.gdel) { r.guide = ''; dirty.features = true; } });
        D.guides = D.guides.filter(g => g.id !== b.dataset.gdel); renderShell();
      }
      if (act === 'gupload') pickFile('application/pdf', true, async fs => {
        const fd = new FormData(); [...fs].forEach(f => fd.append('files', f));
        const d = await api('/api/admin/files/guides', { method: 'POST', body: fd });
        D.guides = d.guides; renderShell();
        toast(`PDF ${d.saved.length}개 올렸어요.` + (d.failed.length ? ` 올리지 않음: ${d.failed.join(' / ')}` : ''), !!d.failed.length);
      });
      if (b.dataset.rollback) {
        if (!confirm(`v${b.dataset.rollback} 버전으로 되돌릴까요? 고객 페이지와 표 내용이 그 버전으로 바뀌어요.`)) return;
        await api('/api/admin/data/rollback/' + b.dataset.rollback, { method: 'POST' }); await load(); toast(`v${b.dataset.rollback}로 되돌렸어요.`);
      }
    } catch (err) { if (err.message !== 'login') toast(err.message, true); }
  });
  $('#dm-preview').addEventListener('click', () => preview().catch(err => toast(err.message, true)));

  function pickFile(accept, multiple, cb) {
    const f = document.createElement('input'); f.type = 'file'; f.accept = accept; f.multiple = multiple;
    f.onchange = () => { if (f.files.length) Promise.resolve(cb(f.files)).catch(err => toast(err.message, true)); };
    f.click();
  }
  async function uploadImages(fs, code) {
    const fd = new FormData(); [...fs].forEach(f => fd.append('files', f)); if (code) fd.append('code', code);
    const d = await api('/api/admin/files/images', { method: 'POST', body: fd });
    D.images = d.images; if (sub === 'products') renderGrid('products');
    toast(`사진 ${d.saved.length}장 올렸어요. [고객 페이지에 적용]을 눌러야 고객 화면에 보여요.` + (d.failed.length ? ` 실패: ${d.failed.join(' / ')}` : ''), !!d.failed.length);
  }
  async function save(tab) {
    const rows = D.rows[tab].map(r => Object.fromEntries(Object.entries(r).filter(([k]) => k === '_carry' || !k.startsWith('_'))));
    const d = await api(`/api/admin/data/${tab}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows, base: (D.stamps || {})[tab] || '' }) })
      .catch(err => { if (/새로고침/.test(err.message)) alert(err.message); throw err; });
    dirty[tab] = false; D.errors = d.errors; D.warnings = d.warnings;
    const fresh = await api('/api/admin/data'); D.rows[tab] = fresh.rows[tab]; D.stamps[tab] = fresh.stamps[tab];
    renderShell();
    toast(`${d.saved}행 저장했어요.` + (d.errors.length ? ` 오류 ${d.errors.length}건이 있어 아직 적용할 수 없어요.` : ' [검사·미리보기]에서 확인 후 적용하세요.'), !!d.errors.length);
  }

  async function preview() {
    const unsaved = Object.entries(dirty).filter(([, v]) => v).map(([k]) => ({ products: '제품', sales: '판매량', features: '제품특성', rules: '고객 기반 데이터' }[k]));
    if (unsaved.length && !confirm(`저장 안 된 탭(${unsaved.join(', ')})이 있어요. 저장된 내용만 검사해요. 계속할까요?`)) return;
    const d = await api('/api/admin/data/preview', { method: 'POST' });
    const ok = !d.errors.length;
    $('#modal-body').innerHTML = `<div class="modal-head"><h2>검사·미리보기</h2><button class="btn sm dark" id="close">닫기</button></div>
      ${d.errors.length ? `<h3 class="dm-h bad">오류 ${d.errors.length}건 — 고쳐야 적용할 수 있어요</h3><ul class="dm-list">${d.errors.slice(0, 50).map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="ok">오류가 없어요.</p>'}
      ${d.warnings.length ? `<h3 class="dm-h warn">확인 ${d.warnings.length}건</h3><ul class="dm-list">${d.warnings.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      <h3 class="dm-h">지금 고객 페이지와 비교</h3><ul class="dm-list">${d.diff.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      ${ok ? `<label class="dm-note">적용 메모 <input id="dm-note" placeholder="예: 10월 판매가 반영"></label><button class="btn primary" id="dm-publish">고객 페이지에 적용</button>` : ''}`;
    $('#modal').classList.add('show');
    $('#close').onclick = () => $('#modal').classList.remove('show');
    if (ok) $('#dm-publish').onclick = async () => {
      try {
        const r = await api('/api/admin/data/publish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: $('#dm-note').value }) });
        $('#modal').classList.remove('show'); await load(); toast(`v${r.version}로 적용했어요. 고객 페이지에 바로 반영돼요.`);
      } catch (err) { toast(err.message, true); }
    };
  }

  function renderGuides() {
    const v = view.guides, rows = filtered('guides'), tk = tokens(v.q), nf = Object.keys(v.cf).length, parts = [];
    if (tk.length > 1) parts.push(`${tk.length}개 코드 검색`);
    if (nf) parts.push(`컬럼필터 ${nf}개`);
    const ndup = guideRows().filter(r => r.dup).length;
    swapBody(`<p class="note dm-help">제품가이드 PDF를 올린 뒤, 제품특성 탭의 '제품가이드' 칸에서 제품별로 연결하세요. 한 PDF를 여러 제품에 연결할 수 있어요. 내용이 똑같은 PDF는 다시 올리지 않아요.</p>
      <div class="list-filters dm-tools">
        <textarea id="dm-q" rows="1" placeholder="여러 코드는 공백·쉼표·줄바꿈으로 구분">${esc(v.q)}</textarea>
        <label class="dm-chkl"><input type="checkbox" id="dm-duponly"${v.dupOnly ? ' checked' : ''}> 중복만 보기${ndup ? ` (${ndup})` : ''}</label>
        <button class="btn sm" data-act="reset">초기화</button>
        <span class="spacer"></span>
        <button class="btn sm primary" data-act="gupload">PDF 올리기 (여러 개 가능)</button>
      </div>
      <div class="statusbar"><span>전체 <b>${D.guides.length}</b>개 중 <b>${rows.length}</b>개 표시${ndup ? ` · 중복 <b>${ndup}</b>개` : ''}</span><span>${parts.join(' · ')}</span></div>
      <div class="table-wrap dm-wrap"><table class="std dm-grid" id="dm-grid" data-tab="guides"><thead><tr>${GCOLS.map((c, ci) =>
        `<th data-col="${ci}" class="${v.cf[ci] ? 'cf-active' : ''}${v.sc === ci ? ' sorted' + (v.sd > 0 ? ' asc' : '') : ''}">${c.label}</th>`).join('')}<th>보기·삭제</th></tr></thead><tbody>
      ${rows.map(({ r }) => `<tr><td>${esc(r.name)}</td><td class="num">${r.mb}</td><td>${esc(r.created)}</td><td class="dm-sum">${esc(r.linked)}</td>
        <td>${r.dup ? `<span class="dm-dup">${esc(r.dup)}</span>` : ''}</td>
        <td><a class="btn sm" href="/files/guide/${r.id}.pdf" target="_blank" rel="noopener">보기</a> <button class="btn sm" data-gdel="${r.id}">삭제</button></td></tr>`).join('')
        || `<tr><td colspan="6">${D.guides.length ? '조건에 맞는 PDF가 없어요.' : '아직 올린 PDF가 없어요.'}</td></tr>`}
      </tbody></table></div>
      <p class="note">헤더 좌클릭 = 정렬 · 우클릭 = 해당 컬럼 검색 · 중복: 같은 파일 = 내용이 똑같은 PDF, 같은 이름 = 이름만 같고 내용은 다른 PDF(개정판 등)</p>`);
    $('#dm-q').classList.toggle('multi', v.q.includes('\n'));
  }
  function renderHistory() {
    $('#dm-body').innerHTML = `<div class="table-wrap"><table class="std"><thead><tr><th>버전</th><th>적용 시각</th><th>메모</th><th>변경 내용</th><th></th></tr></thead><tbody>
      ${D.versions.map(v => `<tr><td>v${v.id}${D.active && D.active.id === v.id ? ' <span class="badge">적용 중</span>' : ''}</td><td>${esc(v.created_at.slice(0, 16).replace('T', ' '))}</td><td>${esc(v.note || '')}</td>
        <td class="dm-sum">${v.summary.map(esc).join('<br>')}</td><td>${D.active && D.active.id === v.id ? '' : `<button class="btn sm" data-rollback="${v.id}">이 버전으로 되돌리기</button>`}</td></tr>`).join('')}
      </tbody></table></div>`;
  }

  // 헤더 정렬(좌클릭) · 컬럼 검색(우클릭)
  document.addEventListener('click', e => {
    const th = e.target.closest('#dm-grid thead th[data-col]'); if (!th) return;
    const v = view[sub], ci = +th.dataset.col;
    if (v.sc === ci) v.sd = -v.sd; else { v.sc = ci; v.sd = 1; }
    renderBody();
  });
  const pop = document.createElement('div');
  pop.className = 'col-filter-popover';
  pop.innerHTML = '<div class="cfp-title" id="dmcf-title"></div><input type="text" class="cfp-input" id="dmcf-input" placeholder="검색어 입력 (부분일치)" />' +
    '<div class="cfp-hint">Enter 적용 · Esc 닫기 · 빈 값 적용 시 해제</div><div class="cfp-actions"><button type="button" class="cfp-btn" id="dmcf-clear">지우기</button><button type="button" class="cfp-btn apply" id="dmcf-apply">적용</button></div>';
  document.body.appendChild(pop);
  let cfCol = null;
  const hide = () => { pop.classList.remove('show'); cfCol = null; };
  const applyCf = clear => { if (cfCol == null) return; const q = clear ? '' : $('#dmcf-input').value.trim().toLowerCase(); if (q) view[sub].cf[cfCol] = q; else delete view[sub].cf[cfCol]; hide(); renderBody(); };
  $('#dmcf-apply').addEventListener('click', () => applyCf(false));
  $('#dmcf-clear').addEventListener('click', () => applyCf(true));
  $('#dmcf-input').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyCf(false); } else if (e.key === 'Escape') hide(); });
  document.addEventListener('mousedown', e => { if (pop.classList.contains('show') && !pop.contains(e.target)) hide(); });
  document.addEventListener('contextmenu', e => {
    const th = e.target.closest('#dm-grid thead th[data-col]'); if (!th) return;
    e.preventDefault(); cfCol = +th.dataset.col;
    $('#dmcf-title').textContent = label(sub, colsOf(sub)[cfCol]) + ' 검색';
    $('#dmcf-input').value = view[sub].cf[cfCol] || '';
    const rc = th.getBoundingClientRect();
    pop.style.top = (rc.bottom + window.scrollY + 4) + 'px'; pop.style.left = Math.min(rc.left + window.scrollX, window.innerWidth - 260) + 'px';
    pop.classList.add('show'); setTimeout(() => { $('#dmcf-input').focus(); $('#dmcf-input').select(); }, 30);
  });
  window.addEventListener('beforeunload', e => { if (Object.values(dirty).some(Boolean)) { e.preventDefault(); e.returnValue = ''; } });

  // ── 여러 개 고르기(답·대상 구분·특성) ──
  const mpop = document.createElement('div');
  mpop.className = 'col-filter-popover dm-mpop';
  document.body.appendChild(mpop);
  let mTarget = null;
  document.addEventListener('click', e => {
    const b = e.target.closest('.dm-multi');
    if (b) {
      const i = +b.dataset.mi, k = b.dataset.mk, r = D.rows[sub][i];
      const c = COLS[sub].find(x => x.k === k);
      const opts = k === 'target' ? D.options.features : c.src(r);
      if (!opts.length) return toast('먼저 질문을 골라 주세요.', true);
      const cur = String(r[k] || '').split(/[,\n]+/).map(x => x.trim()).filter(Boolean);
      mTarget = { i, k };
      mpop.innerHTML = `<div class="cfp-title">${esc(label(sub, c))}</div><div class="dm-mlist">${opts.map(o => `<label><input type="checkbox" value="${esc(o)}"${cur.includes(o) ? ' checked' : ''}> ${esc(o)}</label>`).join('')}</div>
        <div class="cfp-actions"><button type="button" class="cfp-btn" data-mclear>지우기</button><button type="button" class="cfp-btn apply" data-mapply>적용</button></div>`;
      const rc = b.getBoundingClientRect();
      mpop.style.top = (rc.bottom + window.scrollY + 4) + 'px';
      mpop.style.left = Math.min(rc.left + window.scrollX, window.innerWidth - 280) + 'px';
      mpop.classList.add('show');
      return;
    }
    if (e.target.closest('[data-mapply],[data-mclear]') && mTarget) {
      const vals = e.target.closest('[data-mclear]') ? [] : [...mpop.querySelectorAll('input:checked')].map(x => x.value);
      D.rows[sub][mTarget.i][mTarget.k] = vals.join(', ');
      dirty[sub] = true; mpop.classList.remove('show'); mTarget = null; renderShell();
      return;
    }
    if (mpop.classList.contains('show') && !mpop.contains(e.target)) { mpop.classList.remove('show'); mTarget = null; }
  });

  // ── 시험 설문 비교(지금 고객 페이지 vs 저장된 데이터) ──
  let engineReady = null;
  function loadEngine() {
    if (!engineReady) engineReady = new Promise((ok, fail) => {
      const s = document.createElement('script');
      s.src = '/admin/assets/engine.js'; s.onload = ok; s.onerror = () => fail(new Error('추천 엔진을 불러오지 못했어요.'));
      document.head.appendChild(s);
    });
    return engineReady;
  }
  const sig = r => r.results.map(x => x.lines.map(l => l.code + 'x' + l.qty).join('+')).join(' / ');
  function planHtml(res) {
    if (!res.results.length) return '<p class="note">추천 결과 없음(상담 안내)</p>';
    return res.results.map(x => `<div class="plan"><div class="plan-h"><span>${esc(x.label)}</span><span>${(x.amount || 0).toLocaleString('ko-KR')}원</span></div>
      <table>${x.lines.map(l => `<tr><td>${esc(l.code)}</td><td>${esc(l.name)}</td></tr>`).join('')}</table></div>`).join('');
  }
  const FIELD_OF = { '자녀 나이': 'age', '예산': 'budget', '중요하게 생각하는 것': 'needs', '책상 사용 방식(요약)': 'use', '모션데스크': 'motion', '수납 종류': 'storageType' };
  async function compare() {
    if (Object.values(dirty).some(Boolean) && !confirm('저장 안 된 변경이 있어요. 저장된 내용으로 비교해요. 계속할까요?')) return;
    await loadEngine();
    const C = await api('/api/admin/data/catalogs');
    const E = window.DeskerEngine, ea = E.createEngine(C.active), eb = E.createEngine(C.draft);
    const q = D.options.questions;
    const sel = (id, name, multi) => `<label class="dm-cmpf"><span>${name}</span><select id="${id}"${multi ? ' multiple size="4"' : ''}>${(q[name] || []).map((o, i) => `<option${multi && i === 0 ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select></label>`;
    const itemOpts = [['desk', '책상세트'], ['mdesk', '모션데스크 책상세트'], ['desk0', '책상(단품)'], ['chair', '의자'], ['bed', '침대'], ['mattress', '매트리스'], ['ward', '옷장'], ['storage', '책장·수납류'], ['light', '데스크 조명']];
    $('#modal-body').innerHTML = `<div class="modal-head"><h2>시험 설문 비교</h2><button class="btn sm dark" id="close">닫기</button></div>
      <p class="note" style="margin-bottom:10px">왼쪽 = 지금 고객 페이지(v${C.activeId}), 오른쪽 = 저장된 데이터(아직 적용 전). 같은 답변으로 추천 1~3안을 비교해요.</p>
      <div class="dm-cmpform">${sel('cq-age', '자녀 나이')}${sel('cq-budget', '예산')}${sel('cq-needs', '중요하게 생각하는 것', true)}${sel('cq-use', '책상 사용 방식(요약)')}${sel('cq-motion', '모션데스크')}${sel('cq-st', '수납 종류')}
        <label class="dm-cmpf"><span>들이고 싶은 가구(꼭 필요)</span><select id="cq-items" multiple size="4">${itemOpts.map(([k, n]) => `<option value="${k}"${['desk', 'chair'].includes(k) ? ' selected' : ''}>${n}</option>`).join('')}</select></label></div>
      <div class="list-filters"><button class="btn sm primary" id="cq-run">이 답변으로 비교</button><button class="btn sm" id="cq-all">전체 조합 비교(약 1,700가지)</button><span id="cq-sum" class="note"></span></div>
      <div class="dm-cmp"><div><h3 class="dm-h">지금 고객 페이지</h3><div id="cq-a"></div></div><div><h3 class="dm-h">저장된 데이터</h3><div id="cq-b"></div></div></div>`;
    $('#modal').classList.add('show');
    $('#close').onclick = () => $('#modal').classList.remove('show');
    const keyOf = (name, lab) => C.keys[FIELD_OF[name]][lab];
    $('#cq-run').onclick = () => {
      const val = id => $(id).value, multi = id => [...$(id).selectedOptions].map(o => o.value);
      const use = keyOf('책상 사용 방식(요약)', val('#cq-use')), items = multi('#cq-items');
      const a = E.normalize({ age: keyOf('자녀 나이', val('#cq-age')), reason: ['growth'], items, mandatory: items, budget: keyOf('예산', val('#cq-budget')),
        needs: multi('#cq-needs').map(x => keyOf('중요하게 생각하는 것', x)), useSel: use === 'paper' ? ['paper'] : use === 'digital' ? ['digital'] : ['both'],
        motion: keyOf('모션데스크', val('#cq-motion')), storageType: keyOf('수납 종류', val('#cq-st')), roomKnown: 'unknown' });
      const ra = ea.recommend(a), rb = eb.recommend(a);
      $('#cq-a').innerHTML = planHtml(ra); $('#cq-b').innerHTML = planHtml(rb);
      $('#cq-sum').textContent = !ra.results.length && !rb.results.length ? '이 답변으로는 추천 결과가 없어요(예산·가구 선택을 바꿔 보세요).'
        : sig(ra) === sig(rb) ? '두 결과가 같아요.' : '추천 구성이 달라졌어요.';
    };
    $('#cq-all').onclick = () => {
      $('#cq-sum').textContent = '계산 중…';
      setTimeout(() => {
        const ages = ['pre', 'low', 'high', 'middle', 'older'], budgets = ['u50', '50', '100', '150', '200', '250', '300', 'unknown'];
        const sets = [['desk', 'chair'], ['mdesk', 'chair', 'bed', 'mattress', 'ward'], ['ward', 'storage'], ['desk', 'chair', 'storage'], ['bed', 'mattress'], ['mdesk0', 'chair'], ['desk0', 'storage', 'light']];
        const needsSets = [['study', 'budget'], ['storage', 'motion']], sts = ['any', 'books', 'small'];
        let n = 0, same = 0; const ex = [];
        for (const age of ages) for (const budget of budgets) for (const items of sets) for (const needs of needsSets) for (const storageType of sts) {
          const a = E.normalize({ age, reason: ['growth'], items, mandatory: items.slice(0, 2), needs, budget, storageType, roomKnown: 'unknown' });
          const x = sig(ea.recommend(a)), y = sig(eb.recommend(a)); n++;
          if (x === y) same++; else if (ex.length < 5) ex.push(`${age}·${budget}·${items.join('+')}·${needs.join('+')}·${storageType}`);
        }
        $('#cq-sum').textContent = `${n.toLocaleString()}가지 중 ${same.toLocaleString()}가지(${(same / n * 100).toFixed(1)}%) 같음` + (ex.length ? ` · 달라진 예: ${ex.join(' / ')}` : '');
      }, 30);
    };
  }
  document.addEventListener('click', e => { if (e.target.closest('[data-act="compare"]')) compare().catch(err => toast(err.message, true)); });

  window.dkDataTab = { open: () => (D ? renderShell() : load().catch(err => toast(err.message, true))) };
})();
