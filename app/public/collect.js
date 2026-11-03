/* DESKER 학생방 플래너 — 익명 응답 수집
 * 이름·연락처는 받지 않는다. 같은 서버의 /api 로만 보낸다.
 * 원본 페이지 스크립트의 전역 함수(renderSurvey·next·renderResults)를 감싸서 동작하므로
 * 원본 HTML을 교체할 때는 tools/build_public.py 로 다시 빌드한다.
 */
(function () {
  'use strict';
  if (!/^https?:$/.test(location.protocol)) return;   // 저장한 상담표(file://)에서는 동작 안 함
  if (window.__dkCollect) return;
  window.__dkCollect = true;

  const API = '/api';
  const ACTIONS = ['select-result', 'detail', 'shop', 'consult', 'share', 'native-share',
    'save-result', 'print', 'official', 'stores', 'copy-list', 'copy-code', 'edit'];

  function newId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'x' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
  }
  let sid = null;
  try { sid = sessionStorage.getItem('dk_sid'); } catch (e) { /* 저장소 차단 */ }
  if (!sid) {
    sid = newId();
    try { sessionStorage.setItem('dk_sid', sid); } catch (e) { /* 저장소 차단 */ }
  }

  function send(path, body) {
    const data = JSON.stringify(Object.assign({ sid: sid }, body));
    try {
      if (navigator.sendBeacon && navigator.sendBeacon(API + path, new Blob([data], { type: 'application/json' }))) return;
    } catch (e) { /* fetch 로 폴백 */ }
    fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: data, keepalive: true })
      .catch(function () { /* 수집 실패는 고객 화면에 영향 주지 않음 */ });
  }

  function summarize(res) {
    if (!res || !Array.isArray(res.results)) return [];
    return res.results.slice(0, 3).map(function (c) {
      return {
        label: c.label || '', amount: c.amount || 0, partial: !!c.partial,
        lines: (c.lines || []).slice(0, 30).map(function (l) {
          return { code: l.code, name: l.name, qty: l.qty, amount: l.amount, color: l.color || '', bundle: !!l.bundle };
        })
      };
    });
  }

  // 1) 방문
  const entry = location.hash.indexOf('#r=') === 0 ? 'shared'
    : (/[?&]start=1/.test(location.search) ? 'direct' : 'home');
  send('/track', { type: 'visit', entry: entry });

  // 2) 단계 도달 + 마지막 단계 익명 안내
  let maxStep = 0;
  const NOTICE = '입력하신 답변과 추천 결과는 이름·연락처 없이 익명으로 저장되어 서비스 개선과 통계에 활용됩니다. 추가 요청란에는 개인정보를 적지 말아 주세요.';
  if (typeof renderSurvey === 'function') {
    const origRender = renderSurvey;
    renderSurvey = function () {
      const r = origRender.apply(this, arguments);
      try {
        if (view === 'survey') {
          const s = step + 1;
          if (s > maxStep) { maxStep = s; send('/track', { type: 'step', step: s }); }
          if (step === 4 && !document.querySelector('.dk-privacy')) {
            const form = document.querySelector('#survey');
            if (form) {
              const p = document.createElement('p');
              p.className = 'micro dk-privacy';
              p.style.cssText = 'margin-top:14px;color:#70746f';
              p.textContent = NOTICE;
              form.appendChild(p);
            }
          }
        }
      } catch (e) { /* 수집 오류는 무시 */ }
      return r;
    };
  }

  // 3) 설문 완료 → 응답·추천 결과 저장
  let completed = false;
  function submit(kind) {
    try {
      if (demo || !result) return;
      // publicA(): v3 가 공유·저장용으로 이름·연락처를 비운 답변(없으면 원본)
      const answers = typeof publicA === 'function' ? Object.assign({}, publicA(), {
        region: a.region, district: a.district, deskExp: a.deskExp, buyTime: a.buyTime
      }) : a;
      send('/submit', {
        kind: kind, v: typeof DATA_VERSION === 'string' ? DATA_VERSION : '',
        answers: answers, results: summarize(result), selected: selected
      });
    } catch (e) { /* 수집 오류는 무시 */ }
  }
  if (typeof next === 'function') {
    const origNext = next;
    // v3 의 next() 는 async 라서 결과 화면 전환이 끝난 뒤에 판정한다
    next = function () {
      const wasLast = view === 'survey' && step === 4;
      const r = origNext.apply(this, arguments);
      Promise.resolve(r).then(function () {
        if (wasLast && view === 'results') { completed = true; submit('complete'); keepResult(); }
      }, function () { /* 원본 오류는 원본이 처리 */ });
      return r;
    };
  }
  // 완료 후 결과 화면에서 의자·색상을 바꾸면 최신 결과로 갱신
  if (typeof renderResults === 'function') {
    const origResults = renderResults;
    let timer = null;
    renderResults = function () {
      const r = origResults.apply(this, arguments);
      if (completed) { clearTimeout(timer); timer = setTimeout(function () { submit('update'); }, 1500); }
      return r;
    };
  }

  // 4) 결과 화면 유지: 상품 링크로 나갔다 뒤로 오면 브라우저가 페이지를 새로 불러와
  //    처음 화면이 뜨므로 결과 상태를 세 곳에 두고 남아 있는 것으로 복원한다
  //    ① 탭 저장소 ② 주소 #k=(아이폰 사파리처럼 저장소가 비는 경우) ③ 기기 저장소(뒤로가기·새로고침 + 1시간 이내만)
  const KEEP = 'dk_result_v1', KEEP_TTL = 60 * 60 * 1000;
  const ver = function () { return typeof DATA_VERSION === 'string' ? DATA_VERSION : ''; };
  function keepResult() {
    const data = JSON.stringify({
      v: ver(), a: a, selected: selected, demo: !!demo, completed: completed, y: window.scrollY || 0, t: Date.now()
    });
    try { sessionStorage.setItem(KEEP, data); } catch (e) { /* 저장소 차단 */ }
    try { localStorage.setItem(KEEP, data); } catch (e) { /* 저장소 차단 */ }
    try { history.replaceState(history.state, '', location.pathname + location.search + '#k=' + encodePayload()); } catch (e) { /* 주소 갱신 실패 */ }
  }
  function dropResult() {
    try { sessionStorage.removeItem(KEEP); } catch (e) { /* 저장소 차단 */ }
    try { localStorage.removeItem(KEEP); } catch (e) { /* 저장소 차단 */ }
    try { if (location.hash.indexOf('#k=') === 0) history.replaceState(history.state, '', location.pathname + location.search); } catch (e) { /* 무시 */ }
  }
  if (typeof renderResults === 'function') {
    const keptResults = renderResults;
    renderResults = function () { const r = keptResults.apply(this, arguments); keepResult(); return r; };
  }
  // 결과 화면을 떠나면(처음으로·다시 설문) 복원 대상에서 뺀다
  ['home', 'jumpStep'].forEach(function (name) {
    if (typeof window[name] !== 'function') return;
    const orig = window[name];
    window[name] = function () { dropResult(); return orig.apply(this, arguments); };
  });
  window.addEventListener('pagehide', function () { if (view === 'results') keepResult(); });
  (function restore() {
    if (location.hash.indexOf('#r=') === 0 || view !== 'home') return;   // 공유 링크·스냅샷은 원본 boot 가 처리
    function read(store) { try { return JSON.parse(store.getItem(KEEP) || 'null'); } catch (e) { return null; } }
    const ok = function (x) { return x && x.a && x.v === ver(); };
    const hashK = location.hash.indexOf('#k=') === 0 ? location.hash.slice(3) : '';
    let nav = '';
    try { nav = (performance.getEntriesByType('navigation')[0] || {}).type || ''; } catch (e) { /* 구형 브라우저 */ }
    let x = read(sessionStorage);
    if (!ok(x)) {
      const l = read(localStorage);
      // 기기 저장소는 같은 결과(주소 일치)이거나, 뒤로가기·새로고침으로 1시간 안에 돌아온 경우만
      x = ok(l) && (hashK || nav === 'back_forward' || nav === 'reload') && Date.now() - (l.t || 0) < KEEP_TTL ? l : null;
    }
    if (!x && hashK) {
      try { const d = decodePayload(hashK); x = { a: d.a, selected: d.i }; } catch (e) { x = null; }
    }
    if (!x) { if (hashK) dropResult(); return; }
    try {
      a = E.normalize(x.a); touchAll(); demo = !!x.demo;
      selected = Number.isInteger(x.selected) ? x.selected : 0;
      renderResults();
      completed = !!x.completed;   // 복원 렌더로 갱신 전송이 다시 나가지 않게 렌더 뒤에 켠다
      keepResult();
      window.scrollTo(0, x.y || 0);
    } catch (e) { dropResult(); home(); }
  })();

  // 5) QR 이미지 저장: SVG 는 휴대폰 갤러리에 안 들어가므로 PNG 로 만들어
  //    휴대폰은 공유 시트(사진 저장) → 안 되면 길게 눌러 저장 안내, PC 는 PNG 내려받기
  function qrPng() {
    const svg = typeof generatedQR === 'string' ? generatedQR : '';
    const vb = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
    if (!vb) return null;
    const n = Number(vb[1]), cell = Math.max(8, Math.floor(960 / n)), cap = 90;
    const c = document.createElement('canvas');
    c.width = n * cell; c.height = n * cell + cap;
    const g = c.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
    g.fillStyle = '#000';
    const re = /M(\d+),(\d+)h1v1h-1z/g;
    let m;
    while ((m = re.exec(svg))) g.fillRect(Number(m[1]) * cell, Number(m[2]) * cell, cell, cell);
    g.fillStyle = '#333'; g.font = 'bold ' + Math.round(cell * 2.4) + 'px sans-serif'; g.textAlign = 'center';
    g.fillText('DESKER 학생방 플래너 · 추천 결과', c.width / 2, n * cell + cap / 2);
    const url = c.toDataURL('image/png');
    const bin = atob(url.split(',')[1]), buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return { url: url, blob: new Blob([buf], { type: 'image/png' }) };
  }
  function showQrImage(url) {
    openModal('QR 이미지 저장', '<div class="qr-area"><img src="' + url + '" alt="결과 QR 코드" style="width:260px;max-width:100%;display:block;margin:0 auto"></div>'
      + '<div class="info-box" style="margin-top:14px">QR 이미지를 <b>길게 눌러</b> \'이미지 저장\'(사진에 저장)을 선택해 주세요.</div>');
  }
  document.addEventListener('click', function (ev) {
    const el = ev.target.closest && ev.target.closest('[data-action="save-qr"]');
    if (!el) return;
    ev.preventDefault(); ev.stopImmediatePropagation();   // 원본의 SVG 내려받기 대신 처리
    const png = qrPng();
    if (!png) { download('DESKER_QR.svg', generatedQR, 'image/svg+xml'); return; }
    send('/track', { type: 'save-qr', plan: selected });
    const mobile = matchMedia('(pointer:coarse)').matches;
    if (!mobile) {
      const aEl = document.createElement('a'); aEl.href = png.url; aEl.download = 'DESKER_QR.png'; aEl.click();
      return;
    }
    let file = null;
    try { file = new File([png.blob], 'DESKER_QR.png', { type: 'image/png' }); } catch (e) { /* 구형 브라우저 */ }
    if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
      navigator.share({ files: [file] }).catch(function (e) { if (!e || e.name !== 'AbortError') showQrImage(png.url); });
      return;
    }
    showQrImage(png.url);
  }, true);

  // 6) 휴대폰 안내 창: 스크롤해도 제목·←·✕ 줄을 위에 고정(PC 는 원본 CSS 가 이미 고정)
  const headCss = document.createElement('style');
  headCss.textContent = '@media(max-width:740px){.modal-head{position:sticky;top:0;z-index:3;background:#fff;'
    + 'margin:-22px -18px 14px;padding:16px 18px 12px;border-radius:24px 24px 0 0;border-bottom:1px solid #f0f0ee}}';
  document.head.appendChild(headCss);

  // 7) 결과에서 '답변 수정하기': 단계 버튼 전부 열어 원하는 단계만 고치고, '결과 바로 보기'로 복귀
  let fromResults = false;
  document.addEventListener('click', function (ev) {
    const el = ev.target.closest && ev.target.closest('[data-action]');
    if (!el) return;
    const ac = el.dataset.action;
    if (ac === 'edit' && view === 'results') { fromResults = true; maxReach = 4; }   // 원본 jumpStep(0) 보다 먼저
    if (ac === 'start' || ac === 'home') fromResults = false;
  }, true);
  function toResults() {
    const form = document.querySelector('#survey');
    if (form && !form.reportValidity()) return;
    a = E.normalize(a);
    const cur = step;
    for (let s = 0; s <= 4; s++) {
      step = s;
      const miss = missingRequired();
      const errs = miss.length ? ['아래 문항에 답해 주세요 🙏<br>' + miss.map(function (x) { return '• ' + esc(x); }).join('<br>')]
        : E.validate(a, s).filter(function (x) { return !/연령|이유를 골라/.test(x); }).map(esc);
      if (errs.length) {
        step = cur;
        if (s !== cur) jumpStep(s);
        const box = document.querySelector('#form-error');
        if (box) { box.innerHTML = '<div class="form-error">' + errs.join('<br>') + '</div>'; box.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
        return;
      }
    }
    step = cur;
    saveDraft();
    demo = false;
    renderResults();
    window.scrollTo(0, 0);
  }
  if (typeof renderSurvey === 'function') {
    const editRender = renderSurvey;
    renderSurvey = function () {
      const r = editRender.apply(this, arguments);
      try {
        const acts = document.querySelector('#survey .form-actions');
        if (fromResults && view === 'survey' && step < 4 && acts && !document.querySelector('.dk-to-results')) {
          const b = document.createElement('button');
          b.type = 'button'; b.className = 'btn dk-to-results';
          b.style.cssText = 'width:100%;min-height:52px;margin-top:10px;font-size:16px;border-radius:var(--radius-xl)';
          b.textContent = '수정 완료 · 결과 바로 보기';
          b.addEventListener('click', toResults);
          acts.insertAdjacentElement('afterend', b);
        }
      } catch (e) { /* 버튼 추가 실패는 무시 */ }
      return r;
    };
  }

  // 8) 선택 칸(시/도 등)을 바꾼 뒤 다시 그릴 때 그 칸에 포커스를 돌려주면
  //    아이폰 사파리가 선택창을 또 띄우므로, 선택 칸은 포커스 없이 스크롤만 유지한다
  if (typeof renderSurvey === 'function') {
    const focusRender = renderSurvey;
    renderSurvey = function (focusName) {
      const el = focusName && document.querySelector('[name="' + focusName + '"]');
      if (el && el.tagName === 'SELECT') return focusRender.call(this, focusName, '\u0000dk-nofocus');
      return focusRender.apply(this, arguments);
    };
  }

  // 9) 고객 의견: 결과 화면 아래 카드 + 설문 단계마다 '의견 보내기' 링크(같은 입력 창)
  const FB_CATS = [['inconvenient', '😣 불편한 점'], ['fix', '🛠 고쳐야 할 점'], ['feature', '✨ 추가됐으면 하는 기능'], ['etc', '💬 기타']];
  const fbCss = document.createElement('style');
  fbCss.textContent = '.dk-fb{margin:32px 0 8px;padding:24px;border-radius:var(--radius-l,20px);background:var(--surface,#f5f5f3)}'
    + '.dk-fb h3{font-size:19px;margin:0 0 6px}.dk-fb .choices{margin-top:14px}'
    + '.dk-fb .choice{background:#fff;min-height:48px;padding:11px 14px;font-size:15px}'
    + '.dk-fb textarea{width:100%;min-height:110px;margin-top:12px;padding:12px 14px;border:1px solid var(--line,#ddd);border-radius:14px;font:inherit;font-size:15px;resize:vertical;background:#fff;box-sizing:border-box}'
    + '.dk-fb .dk-fb-meta{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--muted,#70746f);margin-top:6px}'
    + '.dk-fb .btn{margin-top:14px;width:100%}.dk-fb-err{color:#c0392b;font-size:13px;margin-top:8px}'
    + '.dk-fb-done{text-align:center;padding:12px 0;font-size:15px}'
    + '#dialog .dk-fb{margin:0;padding:0;background:none}'
    + '.dk-fb-link{all:unset;display:block;margin:18px auto 0;font-size:13px;color:var(--muted,#70746f);text-decoration:underline;text-underline-offset:3px;cursor:pointer;text-align:center}';
  document.head.appendChild(fbCss);
  let fbSeq = 0;
  function fbPlace() { return view === 'results' ? 'results' : view === 'survey' ? 'step' + (step + 1) : 'home'; }
  function fbForm(title, sub) {
    const n = 'dkfb' + (++fbSeq);
    return '<form class="dk-fb" novalidate>' + (title ? '<h3>' + title + '</h3>' : '') + '<p class="micro">' + sub + '</p>'
      + '<div class="choices">' + FB_CATS.map(function (c) {
        return '<label class="choice"><input type="radio" name="' + n + '" value="' + c[0] + '">' + c[1] + '</label>';
      }).join('') + '</div>'
      + '<textarea maxlength="1000" placeholder="편하게 적어 주세요. 이름·연락처 같은 개인정보는 적지 말아 주세요."></textarea>'
      + '<div class="dk-fb-meta"><span>익명으로 전달돼요</span><span class="dk-fb-len">0 / 1000</span></div>'
      + '<div class="dk-fb-err" role="alert"></div>'
      + '<button type="submit" class="btn primary">의견 보내기</button></form>';
  }
  function fbOpenModal() {
    openModal('💬 의견 보내기', fbForm('', '설문하면서 불편했던 점, 고쳐야 할 점, 있었으면 하는 기능을 알려 주세요. 더 좋은 플래너를 만드는 데 쓸게요.'));
  }
  // 원본 문서 리스너(답변 저장)로 번지지 않게 폼 안에서 멈춘다
  ['change', 'input'].forEach(function (t) {
    document.addEventListener(t, function (ev) {
      const f = ev.target.closest && ev.target.closest('.dk-fb');
      if (!f) return;
      ev.stopPropagation();
      if (ev.target.tagName === 'TEXTAREA') f.querySelector('.dk-fb-len').textContent = ev.target.value.length + ' / 1000';
    }, true);
  });
  document.addEventListener('submit', function (ev) {
    const f = ev.target.closest && ev.target.closest('.dk-fb');
    if (!f) return;
    ev.preventDefault(); ev.stopPropagation();
    const cat = f.querySelector('input[type=radio]:checked');
    const msg = f.querySelector('textarea').value.trim();
    const err = f.querySelector('.dk-fb-err');
    if (!cat) { err.textContent = '의견 종류를 골라 주세요.'; return; }
    if (!msg) { err.textContent = '내용을 적어 주세요.'; return; }
    const btn = f.querySelector('button[type=submit]');
    btn.disabled = true; err.textContent = '';
    fetch(API + '/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid: sid, category: cat.value, message: msg, place: fbPlace() })
    }).then(function (r) {
      if (r.ok) {
        f.innerHTML = '<div class="dk-fb-done">💛 소중한 의견 고마워요!<br><span class="micro">보내 주신 내용은 담당자가 꼼꼼히 확인할게요.</span></div>';
        return;
      }
      btn.disabled = false;
      err.textContent = r.status === 429 ? '의견을 너무 많이 보내셨어요. 잠시 뒤에 다시 보내 주세요.' : '전송하지 못했어요. 잠시 뒤 다시 시도해 주세요.';
    }, function () { btn.disabled = false; err.textContent = '전송하지 못했어요. 인터넷 연결을 확인해 주세요.'; });
  }, true);
  document.addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('.dk-fb-link')) { ev.preventDefault(); fbOpenModal(); }
  });
  if (typeof renderResults === 'function') {
    const fbResults = renderResults;
    renderResults = function () {
      const r = fbResults.apply(this, arguments);
      try {
        const foot = document.querySelector('#root .footer');
        if (view === 'results' && foot && !document.querySelector('#root .dk-fb')) {
          foot.insertAdjacentHTML('beforebegin', '<div class="dk-fb-wrap">' + fbForm('플래너 써 보니 어떠셨나요? 🙏',
            '불편했던 점, 고쳐야 할 점, 있었으면 하는 기능을 알려 주세요. 더 좋은 플래너를 만드는 데 쓸게요.') + '</div>');
        }
      } catch (e) { /* 카드 추가 실패는 무시 */ }
      return r;
    };
  }
  if (typeof renderSurvey === 'function') {
    const fbSurvey = renderSurvey;
    renderSurvey = function () {
      const r = fbSurvey.apply(this, arguments);
      try {
        const panel = document.querySelector('#root .form-panel');
        if (view === 'survey' && panel && !panel.querySelector('.dk-fb-link')) {
          panel.insertAdjacentHTML('beforeend', '<button type="button" class="dk-fb-link">💬 설문하면서 불편한 점이 있나요? 의견 보내기</button>');
        }
      } catch (e) { /* 링크 추가 실패는 무시 */ }
      return r;
    };
  }

  // 10) 결과 화면 행동(구매 안내·상담표·공유 등)
  document.addEventListener('click', function (ev) {
    const el = ev.target.closest && ev.target.closest('[data-action]');
    if (!el) return;
    const ac = el.dataset.action;
    if (ACTIONS.indexOf(ac) < 0) return;
    let plan = el.hasAttribute('data-i') ? Number(el.dataset.i) : null;
    try { if (plan === null || isNaN(plan)) plan = selected; } catch (e) { plan = null; }
    send('/track', { type: ac, plan: plan });
  }, true);
})();
