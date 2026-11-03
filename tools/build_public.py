"""고객용 페이지 빌드: source/customer_v3.html → app/public/index.html

- 5단계 '추가 정보'에서 이름·연락처 칸과 개인정보·마케팅 동의를 제거(익명 운영)
  지역·책상 구매 경험·구매 시기는 선택 입력으로 남긴다(가까운 매장 안내·익명 통계)
- 공개 서버에서는 ?admin=1 운영 도구(QR 배포·네이버 링크 관리)를 끈다
- '서버로 전송하지 않습니다' 류 안내 문구를 익명 수집 안내로 교체
- 응답 수집 스크립트(/collect.js) 연결
- 매장 안내는 네이버지도 검색으로, 시·군·구는 source/sigungu.json 목록에서 고르게 한다

원본 HTML이 바뀌면(예: 네이버 링크 반영본) source/ 파일만 교체하고 다시 실행한다.
    python tools/build_public.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source" / "customer_v3.html"
OUT = ROOT / "app" / "public" / "index.html"

REPLACEMENTS = [
    # ── 개인정보 수집 제거 ──
    ("'마지막으로, 소식을 받아보실래요? 🎁'", "'마지막으로, 조금만 더 알려주세요 📍'"),
    ("✨ 추가 정보를 입력해 주시면, 할인·이벤트 등 데스커의 새로운 소식을 전해드릴게요. 입력하지 않아도 추천 결과는 볼 수 있어요.",
     "📍 지역을 알려주시면 가까운 데스커 매장을 안내해 드려요. 입력하지 않아도 추천 결과는 볼 수 있어요."),
    ("  body+=question('이름과 연락처를 알려주세요',`<div class=\"input-row two\">${textField('name','이름','홍길동')}${textField('phone','연락처','010-0000-0000','tel')}</div>`);\n",
     ""),
    ("  body+=`<div class=\"agree\"><b>개인정보 수집·이용 동의 <span class=\"optional\">선택</span></b>", "  if(0)body+=`<div class=\"agree\"><b>개인정보 수집·이용 동의 <span class=\"optional\">선택</span></b>"),
    ("  body+=`<div class=\"agree\"><b>마케팅 정보 수신 동의 <span class=\"optional\">선택</span></b>", "  if(0)body+=`<div class=\"agree\"><b>마케팅 정보 수신 동의 <span class=\"optional\">선택</span></b>"),
    ("function leadErrors(){const e=[];", "function leadErrors(){return [];const e=[];"),
    ("async function submitLead(){if(!a.consentPrivacy)return;", "async function submitLead(){return;"),
    # ── 공개 서버에서 운영 도구 끄기 ──
    ("const ADMIN=/[?&]admin=1/.test(location.search);", "const ADMIN=false;"),
    # ── 익명 수집 안내 ──
    ("회원가입 없이 3분만에 간단하게! ⏱️",
     "회원가입 없이 3분만에 간단하게! ⏱️<br>이름·연락처는 받지 않고, 답변은 익명 통계로만 활용돼요."),
    ("설문 응답과 추천 결과는 서버에 자동 저장하지 않습니다.",
     "설문 응답과 추천 결과는 이름·연락처 없이 익명으로 저장되어 서비스 개선과 통계에 활용됩니다."),
    ("응답은 브라우저에서 처리합니다. ‘이 기기에 저장’을 선택하지 않으면 자동 저장하지 않으며,",
     "추천 계산은 브라우저에서 처리하고, 완료한 응답과 추천 결과는 이름·연락처 없이 익명으로 저장되어 통계에 활용됩니다. ‘이 기기에 저장’은 이 기기에서 답변을 다시 불러오는 기능이며,"),
    ("별도 서버에 접수되거나 매장에 자동 전달되지 않습니다.",
     "상담 접수로 처리되거나 매장에 자동 전달되지 않습니다."),
    ("No server, analytics, cookies, or third-party form submission.",
     "Anonymous survey responses are sent to same-origin /api by collect.js. No cookies or third-party submission."),
]
REPLACEMENTS += [
    # ── 데이터 관리 탭 연동: 사진 없는 제품도 추천(사진 목록으로 거르지 않음), 데이터 버전은 서버가 채움 ──
    ("DATA.HAS_IMAGE=(()=>{try{return Object.keys(JSON.parse(document.getElementById('images').textContent));}catch(e){return null;}})();",
     "DATA.HAS_IMAGE=null;"),
    ("DATA_VERSION='20261022-products149-v31'", "DATA_VERSION='__DK_DATA_VERSION__'"),
]
REPLACEMENTS += [
    # ── 고객 기반 데이터: 코드에 고정된 선호 가점을 관리자 '선호 규칙'(DATA.RULES)으로 대체 ──
    # 남기는 규칙: 폭·공간 계산, 함께 쓰기 폭, 벽고정 미확인·천장 불확실 감점, 우선 해결 가구 가중, 판매량
    (" const SALES_WEIGHT=30;\n",
     " const SALES_WEIGHT=30;\n"
     " const ruleOn=(r,a)=>{const v=a[r.field];return Array.isArray(v)?v.some(x=>r.values.includes(x)):r.values.includes(String(v??''));};\n"),
    ("  const young=['pre','low'].includes(a.age);\n",
     "  const young=['pre','low'].includes(a.age);\n"
     "  const RULES=(DATA.RULES||[]).filter(r=>ruleOn(r,a));\n"
     "  const ruleScore=k=>RULES.reduce((s,r)=>s+(r.pts&&r.codes.includes(k)?r.pts:0),0);\n"
     "  const ruleOut=new Set(RULES.filter(r=>r.exclude).flatMap(r=>r.codes));\n"),
    ("    if(a.needs.includes('study'))s+=m.family==='focus'?17:['desk','mdesk'].includes(m.cat)?12:4;\n"
     "    if((a.motion==='want'||a.motion==='must'||a.needs.includes('motion'))&&m.motion)s+=30;\n"
     "    if(m.multi&&a.use!=='paper')s+=24;\n"
     "    if(a.use==='digital'&&['computer','multidesk','notebook'].includes(m.family))s+=14;\n"
     "    if(a.use==='paper'&&!m.motion&&!m.multi)s+=8;\n"
     "    if(m.light&&a.needs.includes('study'))s+=5;\n", ""),
    ("    if(a.needs.includes('storage'))s+=m.tier===6?15:m.tier===5?11:6;\n"
     "    if(a.storageType==='mirror'&&m.cat==='mirror')s+=35;\n"
     "    if(a.storageType==='small'&&(/서랍/.test(p[1])||m.cat==='drawer'))s+=25;\n"
     "    if(a.storageType==='books'&&['shelf','low'].includes(m.cat))s+=20;\n", ""),
    ("    if(m.cat==='drawer'&&a.storageType==='books')s-=25;\n", ""),
    ("   if(m.cat==='ward'&&a.storageType==='clothes')s+=24;\n"
     "   if(m.cat==='chair')s+=k===(young?CHAIR_CODES.RNG:CHAIR_CODES.ALR)?20:k===CHAIR_CODES.IBL?(young?3:18):0;\n",
     "   s+=ruleScore(k);\n"),
    ("   if(m.cat==='organizer'&&a.storageType==='small')s+=12;\n", ""),
    # '제외' 등급: 제외 후 후보가 남을 때만 적용(후보가 비면 그 고객에게는 무시)
    ("   if(!choices.length&&noimg.length)choices=noimg;\n",
     "   if(!choices.length&&noimg.length)choices=noimg;\n"
     "   if(ruleOut.size){const kept=choices.filter(c=>!c.keys.some(x=>ruleOut.has(x)));if(kept.length)choices=kept;}\n"),
    # 추천 이유 문구도 규칙 기준으로
    ("const preferred=young?chairCode===CHAIR_CODES.RNG:[CHAIR_CODES.ALR,CHAIR_CODES.IBL].includes(chairCode);",
     "const preferred=ruleScore(chairCode)>0;"),
]
REPLACEMENTS += [
    # ── 수납장 2개 이상: 같은 제품 ×2 대신 서로 다른 제품, 그중 다른 품목(책장+거울수납장 등)을 우선 ──
    # 같은 제품 2개는 다른 조합이 하나도 없을 때만. 5단·6단을 섞지 않는 기존 규칙은 유지.
    ("     both.push({keys:ks,score:(choices[i].score+choices[j].score)/2+10});\n    }choices=both;\n",
     "     const same=i===j,mix=!same&&M[ks[0]].cat!==M[ks[1]].cat;\n"
     "     both.push({keys:ks,score:(choices[i].score+choices[j].score)/2+10+(mix?15:0),same});\n"
     "    }const distinct=both.filter(x=>!x.same);choices=distinct.length&&!allowSame?distinct:both;\n"),
    # 다른 제품 조합으로는 예산 안 추천이 하나도 없을 때만 같은 제품 ×2 허용(추천 없음이 새로 생기지 않게)
    ("function recommend(raw){\n",
     "function recommend(raw){const r=recommendCore(raw,false);"
     "if(r.results.length||!(r.answers&&r.answers.storageCount===2))return r;"
     "const r2=recommendCore(raw,true);return r2.results.length?r2:r;}\n"
     " function recommendCore(raw,allowSame){\n"),
]
REPLACEMENTS += [
    # ── 매장 안내: 공식 매장안내 페이지 대신 네이버지도에서 해당 매장 검색 ──
    ("const STORES=(()=>",
     "function naverMap(q){return 'https://map.naver.com/p/search/'+encodeURIComponent(q);}\nconst STORES=(()=>"),
    ('<a href="${esc(CONF.storeUrl)}" target="_blank" rel="noopener noreferrer">매장 안내·상담 예약 ↗</a>',
     '<a href="${esc(naverMap(s.name))}" target="_blank" rel="noopener noreferrer">네이버지도에서 보기 ↗</a>'),
    # 결과 하단 'IN STORE' 버튼: 지역을 입력했으면 가장 가까운 매장, 아니면 '데스커 매장'
    ("if(ac==='stores')window.open(CONF.storeUrl,'_blank','noopener,noreferrer');",
     "if(ac==='stores')window.open(naverMap(nearbyStores()[0]?.name||'데스커 매장'),'_blank','noopener,noreferrer');"),
]
REPLACEMENTS += [
    # ── 시·군·구: 직접 입력 → 시·도에 따라 바뀌는 선택 목록(전국 229곳, source/sigungu.json) ──
    ("${textField('district','시·군·구','예: 강남구')}", "${districtField()}"),
    ("function geoPoint(region,district){const sg=GEO.sigungu||{},sd=GEO.sido||{};if(!region)return null;const m=String(district||'').replace(/\\s+/g,'').match(/^([가-힣]{1,4}?)(시|군|구)/);if(m){const v=sg[region+' '+m[1]];if(v)return v;const key=Object.keys(sg).find(k=>k.startsWith(region+' ')&&m[1].startsWith(k.split(' ')[1]));if(key)return sg[key];}return sd[region]||null;}",
     "function districtsOf(region){return region?Object.keys(GEO.sigungu||{}).filter(k=>k.startsWith(region+' ')).map(k=>k.slice(region.length+1)):[];}\n"
     "function districtField(){const ds=districtsOf(a.region);if(a.region&&!ds.length)return '';"
     "return `<label class=\"input-field\"><span>시·군·구</span><select name=\"district\" aria-label=\"시군구\" ${a.region?'':'disabled'}>"
     "<option value=\"\">${a.region?'선택해 주세요':'시·도를 먼저 골라 주세요'}</option>"
     "${ds.map(d=>`<option value=\"${esc(d)}\" ${a.district===d?'selected':''}>${esc(d)}</option>`).join('')}</select></label>`;}\n"
     # 목록 값은 그대로 찾고, 예전에 직접 입력한 값(예: '금천', '수원시 영통구')은 이름 앞부분으로 찾는다
     "function geoPoint(region,district){const sg=GEO.sigungu||{},sd=GEO.sido||{};if(!region)return null;"
     "const d=String(district||'').replace(/\\s+/g,'');if(sg[region+' '+d])return sg[region+' '+d];"
     "if(d){const ds=districtsOf(region).sort((x,y)=>y.length-x.length),stem=x=>x.slice(0,-1);"
     "const hit=ds.find(x=>stem(x)===d)||ds.find(x=>d.startsWith(x))||ds.find(x=>stem(x).length>=2&&d.startsWith(stem(x)));"
     "if(hit)return sg[region+' '+hit];}return sd[region]||null;}"),
    # 시·도를 바꾸면 목록을 다시 그리고, 다른 시·도의 시·군·구 선택은 비운다
    ("saveDraft();if(view==='survey'&&['items','mandatory','unknownItems','roomKnown','room','kept','reason','needs','constraints','mat','scope','age'].includes(k))",
     "if(k==='region'&&a.district&&!districtsOf(a.region).includes(a.district))a.district='';"
     "saveDraft();if(view==='survey'&&['items','mandatory','unknownItems','roomKnown','room','kept','reason','needs','constraints','mat','scope','age','region'].includes(k))"),
]
REPLACEMENTS += [
    # ── 결과 페이지: '온라인으로 구매하고 싶다면 / 매장에서 상담받고 싶다면' 카드 제외(추천안별 버튼은 유지) ──
    ("<section class=\"next-section\"><div class=\"next-card\"><div class=\"eyebrow\">ONLINE</div><h3>🛒 온라인으로 구매하고 싶다면</h3>"
     "<p>구성된 제품마다 구매할 수 있는 상품 페이지를 안내해 드려요. 색상과 옵션을 한 번 더 확인하고 주문해 주세요.</p>"
     "${btn('구매 안내 보기','shop')}${btn('결과 링크 · QR','share')}</div><div class=\"next-card\"><div class=\"eyebrow\">IN STORE</div>"
     "<h3>🏬 매장에서 상담받고 싶다면</h3><p>선택한 구성과 답변, 설치 때 확인할 내용을 상담표로 정리해 드려요. 매장에서 보여 주시면 더 빠르게 상담받을 수 있어요.</p>"
     "${btn('상담표 보기','consult')}</div></section>", ""),
    # ── 온라인 구매 안내: 제품별 '코드 복사' 버튼 삭제('구매 목록 복사'는 유지) ──
    ('<button class="btn small-btn" data-v2copy="${esc(l.code)}">코드 복사</button>', ""),
    # ── 예상 금액 = 할인 전 정가 → 금액 바로 아래에 눈에 띄는 안내 ──
    ("function priceLabel(c){return '예상 금액';}",
     "function priceLabel(c){return '예상 금액 (정가 기준)';}\n"
     "const listNote=()=>'<p class=\"list-price-note\">💡 <b>할인 전 정가예요.</b><span>프로모션·멤버십 혜택으로 실제 구입가는 더 낮아요</span></p>';"),
    ('<span class="micro">${priceLabel(c)}</span><strong>${won(c.amount)}</strong></div><div class="summary-chips">',
     '<span class="micro">${priceLabel(c)}</span><strong>${won(c.amount)}</strong>${listNote()}</div><div class="summary-chips">'),
    ('<span class="micro">${priceLabel(c)}</span><strong>${won(c.amount)}</strong></div>${notesHTML()}',
     '<span class="micro">${priceLabel(c)}</span><strong>${won(c.amount)}</strong>${listNote()}</div>${notesHTML()}'),
    ('<div class="info-box">${priceLabel(c)} <b>${won(c.amount)}</b>${notesHTML()}',
     '<div class="info-box">${priceLabel(c)} <b>${won(c.amount)}</b>${listNote()}${notesHTML()}'),
    (".card-total small{color:var(--muted);font-size:13px}",
     ".card-total small{color:var(--muted);font-size:13px}\n"
     ".list-price-note{margin:8px 0 0;padding:10px 12px;border-radius:10px;background:var(--hero-deep);border-left:4px solid var(--yellow);"
     "color:var(--ink);font-size:14px;line-height:1.55;letter-spacing:-.01em}\n.list-price-note b{font-weight:800}"
     "\n.list-price-note span{display:block;margin-top:2px;font-size:12.5px;color:var(--body);letter-spacing:-.02em}"),
]
REPLACEMENTS += [
    # ── 단계 이동: PC 왼쪽 단계 목록·모바일 단계 버튼을 누르면 그 단계로 ──
    # 뒤로는 언제든, 앞으로는 가 본 단계(maxReach)까지만 + 사이 단계의 필수 답변을 '다음'과 같은 기준으로 확인
    ("function jumpStep(s){step=s;",
     "let maxReach=0;\n"
     # 모바일 단계 버튼은 가로로 넘치면 지금 단계를 가운데로
     "{const _rs=renderSurvey;renderSurvey=function(){const r=_rs.apply(this,arguments);"
     "const c=document.querySelector('.step-chips'),x=c&&c.querySelector('.active');if(x)c.scrollLeft=x.offsetLeft-(c.clientWidth-x.offsetWidth)/2;return r;};}\n"
     "function goStep(t){t=Number(t);if(!Number.isInteger(t)||t<0||t>4||t===step)return;"
     "if(t<step){saveDraft();jumpStep(t);return;}if(t>maxReach)return;"
     "const form=$('#survey');if(form&&!form.reportValidity())return;a=E.normalize(a);const cur=step;"
     "for(let s=cur;s<t;s++){step=s;const miss=missingRequired();"
     "const errs=miss.length?['아래 문항에 답해 주세요 🙏<br>'+miss.map(x=>'• '+esc(x)).join('<br>')]:E.validate(a,s).filter(x=>!/연령|이유를 골라/.test(x)).map(esc);"
     "if(errs.length){step=cur;if(s!==cur)jumpStep(s);$('#form-error').innerHTML='<div class=\"form-error\">'+errs.join('<br>')+'</div>';"
     "$('#form-error').scrollIntoView({block:'center',behavior:'smooth'});return;}}"
     "step=cur;saveDraft();jumpStep(t);}\n"
     "function jumpStep(s){maxReach=Math.max(maxReach,s);step=s;"),
    ("if(ac==='start'){demo=false;", "if(ac==='start'){demo=false;maxReach=0;"),
    ("if(ac==='home')home();", "if(ac==='home')home();if(ac==='gostep')goStep(el.dataset.step);"),
    ("${STEPS.map((s,i)=>`<li class=\"${i===step?'active':i<step?'done':''}\"><span class=\"circle\">${i<step?'✓':String(i+1).padStart(2,'0')}</span>${s}</li>`).join('')}",
     "${STEPS.map((s,i)=>`<li class=\"${i===step?'active':i<step?'done':i<=maxReach?'reach':''}\"><button type=\"button\" class=\"step-link\" data-action=\"gostep\" data-step=\"${i}\" ${i>maxReach?'disabled':''} ${i===step?'aria-current=\"step\"':''}>"
     "<span class=\"circle\">${i<step?'✓':String(i+1).padStart(2,'0')}</span><span class=\"lbl\">${s}</span></button></li>`).join('')}"),
    ('<div class="step-count">STEP',
     "<ol class=\"step-chips\" aria-label=\"설문 단계\">${['고민 계기','현재 환경','가구','고려 요소','추가 정보'].map((s,i)=>`<li><button type=\"button\" class=\"step-chip ${i===step?'active':i<step?'done':''}\" data-action=\"gostep\" data-step=\"${i}\" ${i>maxReach?'disabled':''} ${i===step?'aria-current=\"step\"':''}>"
     "<b>${i<step?'✓':i+1}</b>${s}</button></li>`).join('')}</ol>"
     '<div class="step-count">STEP'),
    (".step-nav li.done .circle{background:var(--yellow);color:var(--ink)}",
     ".step-nav li.done .circle{background:var(--yellow);color:var(--ink)}\n"
     ".step-nav li.done,.step-nav li.reach{color:var(--body)}\n"
     ".step-link{all:unset;display:flex;align-items:center;gap:12px;width:100%;cursor:pointer}\n"
     ".step-link:disabled{cursor:default}\n"
     ".step-link:not(:disabled):hover .lbl{text-decoration:underline;text-underline-offset:4px}\n"
     ".step-link:focus-visible{outline:2px solid var(--ink);outline-offset:4px;border-radius:6px}\n"
     ".step-chips{display:none;position:relative;list-style:none;margin:0 -20px 14px;padding:0 20px 2px;gap:6px;overflow-x:auto;scrollbar-width:none}\n"
     ".step-chips::-webkit-scrollbar{display:none}\n"
     ".step-chip{display:flex;align-items:center;gap:5px;white-space:nowrap;border:1px solid var(--line);background:var(--canvas);color:var(--body);"
     "border-radius:999px;padding:6px 10px 6px 6px;font:inherit;font-size:13px;font-weight:600;cursor:pointer}\n"
     ".step-chip b{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--surface);font-size:11px}\n"
     ".step-chip.active{background:var(--ink);border-color:var(--ink);color:#fff}.step-chip.active b{background:#fff;color:var(--ink)}\n"
     ".step-chip.done b{background:var(--yellow);color:var(--ink)}\n"
     ".step-chip:disabled{color:var(--soft);border-color:var(--line-soft);cursor:default}"),
    (".wizard-aside{display:none}", ".wizard-aside{display:none}.step-chips{display:flex}"),
]
REPLACEMENTS += [
    # ── 온라인 구매 안내 창: 아래 '구매 목록 복사'·'매장 상담표로 보기' 버튼 삭제 ──
    ("<div class=\"modal-actions\">${btn('구매 목록 복사','copy-list')}${btn('🏬 매장 상담표로 보기','consult','primary')}</div>", ""),
    # ── 안내 창(PC): 제목줄을 마우스로 잡고 끌어 옮기기. 제목줄은 스크롤해도 위에 고정, 닫으면 원래 자리 ──
    ("function closeModal(){$('#dialog').close();lastFocus?.focus?.();}",
     "function closeModal(){$('#dialog').close();lastFocus?.focus?.();}\n"
     "(()=>{const d=$('#dialog');let st=null;const wide=()=>matchMedia('(min-width:741px)').matches;"
     "d.addEventListener('pointerdown',e=>{const h=e.target.closest('.modal-head');"
     "if(!h||e.button!==0||e.target.closest('button,a,input,select,textarea')||!wide())return;"
     "const r=d.getBoundingClientRect(),m=(d.style.transform.match(/-?[\\d.]+/g)||[0,0]).map(Number);"
     "st={x:e.clientX,y:e.clientY,bx:m[0]||0,by:m[1]||0,r};h.setPointerCapture(e.pointerId);d.classList.add('dragging');e.preventDefault();});"
     "d.addEventListener('pointermove',e=>{if(!st)return;"
     "const dx=Math.max(Math.min(0,-st.r.left),Math.min(Math.max(0,innerWidth-st.r.right),e.clientX-st.x)),"
     "dy=Math.max(-st.r.top,Math.min(innerHeight-80-st.r.top,e.clientY-st.y));"
     "d.style.transform=`translate(${st.bx+dx}px,${st.by+dy}px)`;});"
     "const end=()=>{st=null;d.classList.remove('dragging');};d.addEventListener('pointerup',end);d.addEventListener('pointercancel',end);"
     "d.addEventListener('close',()=>{d.style.transform='';end();});})();"),
    (".modal-head h2{font-size:22px}",
     ".modal-head h2{font-size:22px}\n"
     "@media(min-width:741px){.modal-head{position:sticky;top:0;z-index:3;background:#fff;margin:-28px -28px 16px;padding:22px 28px 14px;"
     "border-radius:24px 24px 0 0;cursor:move;touch-action:none;user-select:none}.modal-head .close{cursor:pointer}"
     "dialog.dragging{box-shadow:0 18px 48px rgba(40,40,40,.28)}}"),
]
REPLACEMENTS += [
    # ── 매장 상담표 창: '인쇄 · PDF로 저장'·'상담표 파일로 저장' 삭제('결과 링크 · QR'은 유지) ──
    ("${btn('인쇄 · PDF로 저장','print','primary')}${btn('상담표 파일로 저장','save-result')}${btn('결과 링크 · QR','share')}",
     "${btn('결과 링크 · QR','share')}"),
]
REPLACEMENTS += [
    # ── 안내 창 뒤로 가기: 창 안에서 다른 창을 열면 이전 창을 기억, 제목 왼쪽 '←'로 돌아가기(스크롤 위치 포함) ──
    ("function openModal(title,content){lastFocus=document.activeElement;$('#dialog').innerHTML=`<div class=\"modal-content\"><div class=\"modal-head\"><h2>${title}</h2>"
     "<button type=\"button\" class=\"close\" data-action=\"close\" aria-label=\"닫기\">×</button></div>${content}</div>`;if(!$('#dialog').open)$('#dialog').showModal();}",
     "let modalStack=[],modalCur=null;\n"
     "function paintModal(title,content){$('#dialog').innerHTML=`<div class=\"modal-content\"><div class=\"modal-head\">"
     "${modalStack.length?'<button type=\"button\" class=\"modal-back\" data-action=\"modal-back\" aria-label=\"이전 화면으로\">←</button>':''}<h2>${title}</h2>"
     "<button type=\"button\" class=\"close\" data-action=\"close\" aria-label=\"닫기\">×</button></div>${content}</div>`;modalCur={title,content};}\n"
     "function openModal(title,content){const d=$('#dialog');if(d.open&&modalCur)modalStack.push({...modalCur,scroll:d.scrollTop});"
     "else{modalStack=[];lastFocus=document.activeElement;}paintModal(title,content);if(!d.open)d.showModal();d.scrollTop=0;}\n"
     "function modalBack(){const p=modalStack.pop();if(!p)return;paintModal(p.title,p.content);$('#dialog').scrollTop=p.scroll||0;}\n"
     "$('#dialog').addEventListener('close',()=>{modalStack=[];modalCur=null;});"),
    ("if(ac==='close')closeModal();", "if(ac==='close')closeModal();if(ac==='modal-back')modalBack();"),
    (".close{border:0;border-radius:50%;width:36px;height:36px;background:var(--surface);font-size:20px;line-height:1;flex:none}",
     ".close{border:0;border-radius:50%;width:36px;height:36px;background:var(--surface);font-size:20px;line-height:1;flex:none}\n"
     ".modal-back{border:0;border-radius:50%;width:36px;height:36px;background:var(--surface);font-size:18px;font-weight:700;line-height:1;flex:none;cursor:pointer;color:var(--ink)}\n"
     ".modal-back:hover,.close:hover{background:var(--line-soft)}.modal-back+h2{flex:1;min-width:0}"),
]
REPLACEMENTS += [
    # ── '어떤 수납이 더 필요하세요?' 복수 선택: storageType = 배열('아직 정하지 못했어요'는 단독) ──
    # 예전 값(문자열)·예전 결과 링크도 그대로 읽는다
    ("storageType:['any','books','clothes','small','mirror'].includes(x.storageType)?x.storageType:'any'",
     "storageType:arr(typeof x.storageType==='string'?[x.storageType]:x.storageType,{any:1,books:1,clothes:1,small:1,mirror:1}).filter((y,_,l)=>y!=='any'||l.length===1)"),
    ("body+=question('어떤 수납이 더 필요하세요?',radio('storageType',",
     "body+=question('어떤 수납이 더 필요하세요?',choices('storageType',"),
    ("small:'학용품·작은 물건 ✏️',mirror:'거울이 있는 수납 🪞'}));",
     "small:'학용품·작은 물건 ✏️',mirror:'거울이 있는 수납 🪞'}),'해당하는 걸 모두 골라 주세요.');"),
    ("else if(el.type==='checkbox'){let vals=[...(a[k]||[])];",
     "else if(el.type==='checkbox'){let vals=Array.isArray(a[k])?[...a[k]]:a[k]?[a[k]]:[];"),
    ("if(k==='constraints'){if(el.value==='none'&&el.checked)vals=['none'];else vals=vals.filter(x=>x!=='none');}",
     "if(k==='constraints'){if(el.value==='none'&&el.checked)vals=['none'];else vals=vals.filter(x=>x!=='none');}"
     "if(k==='storageType'){if(el.value==='any'&&el.checked)vals=['any'];else vals=vals.filter(x=>x!=='any');}"),
    ("'constraints','mat','scope','age','region'].includes(k))", "'constraints','mat','scope','age','region','storageType'].includes(k))"),
    # 추천 계산: 고른 수납 중 하나라도 맞으면 후보, 옷·의류는 옷장(다른 수납도 고르면 수납장도 함께)
    ("const ruleOn=(r,a)=>{const v=a[r.field];",
     "const ruleOn=(r,a)=>{let v=a[r.field];if(r.field==='storageType'&&Array.isArray(v)&&!v.length)v=['any'];"),
    ("  const a=normalize2(raw),errors=validate(a);",
     "  const a=normalize2(raw),errors=validate(a);const st=a.storageType.filter(x=>x!=='any'),stHas=x=>st.includes(x),"
     "stWanted=()=>stHas('clothes')?(st.length>1?['ward','storage']:['ward']):['storage'];"),
    ("const highStorage=a.needs.includes('storage')&&(a.priority==='storage'||a.storageType==='small');",
     "const highStorage=a.needs.includes('storage')&&(a.priority==='storage'||stHas('small'));"),
    ("   if(a.needs.includes('storage')||a.reason.includes('storage'))wanted.add(a.storageType==='clothes'?'ward':'storage');",
     "   if(a.needs.includes('storage')||a.reason.includes('storage'))stWanted().forEach(x=>wanted.add(x));"),
    ("   if(a.needs.includes('storage'))wanted.add(a.storageType==='clothes'?'ward':'storage');",
     "   if(a.needs.includes('storage'))stWanted().forEach(x=>wanted.add(x));"),
    ("     if(a.storageType==='mirror'&&m.cat!=='mirror')continue;\n"
     "     if(a.storageType==='books'&&m.cat==='drawer')continue;\n"
     "     if(a.storageType==='small'&&!/서랍/.test(P[k][1]))continue;\n",
     "     {const sk=st.filter(x=>x!=='clothes');if(sk.length&&!sk.some(x=>x==='mirror'?m.cat==='mirror':x==='books'?m.cat!=='drawer':/서랍/.test(P[k][1])))continue;}\n"),
    ("add(2,a.storageType==='small'?", "add(2,stHas('small')?"),
    # 결과 링크: 복수 선택 값은 음수(-1-비트마스크)로 담아 예전 링크(0~4 번호)와 구분
    ("['storageType',['any','books','clothes','small','mirror']]", "['storageType',['any','books','clothes','small','mirror'],'stmask']"),
    ("const packed=PACK_FIELDS.map(([k,opts,type])=>type==='mask'?",
     "const packed=PACK_FIELDS.map(([k,opts,type])=>type==='stmask'?-1-(a[k]||[]).reduce((m,v)=>m|(1<<opts.indexOf(v)),0):type==='mask'?"),
    ("decoded[k]=type==='mask'?",
     "decoded[k]=type==='stmask'?(v<0?opts.filter((_,j)=>((-1-v)&(1<<j))!==0):opts[v]):type==='mask'?"),
    # ── 매트리스 질문: 침대를 고르고 매트리스는 안 골랐을 때만. 안 보일 땐 매트리스 선택·계속 쓸 가구로 정함 ──
    ("if(a.items.includes('bed')||a.unknownItems)body+=question('침대를 사신다면, 매트리스는요?'",
     "if(a.items.includes('bed')&&!a.items.includes('mattress'))body+=question('침대를 사신다면, 매트리스는요?'"),
    ("function normalize2(x={}){\n const a=normalize(x);\n",
     "function normalize2(x={}){\n const a=normalize(x);\n"
     " if(!(a.items.includes('bed')&&!a.items.includes('mattress')))a.mat=!a.items.includes('mattress')&&a.kept.includes('mattress')?'keep':'new';\n"),
    # ── '추천을 받은 뒤엔 어떻게 하실 계획인가요?' 삭제(channel은 기본값 '둘 다') ──
    ("  body+=question('추천을 받은 뒤엔 어떻게 하실 계획인가요?',radio('channel',{both:'온라인 구매도, 매장 상담도 생각 중이에요',online:'온라인에서 바로 살래요',store:'매장에서 상담받고 정할래요'}));\n", ""),
    # ── 구매 시기 질문 문구 ──
    ("'자녀방 가구는 언제쯤 사실 계획이세요? 🗓️'", "'자녀방 가구는 언제쯤 구매할 계획이신가요? 🗓️'"),
]
REPLACEMENTS += [
    # ── 2단계: 천장 높이·책상 벽 너비는 방 크기를 (정확히·대략) 알 때만. 모르면 값도 비움 ──
    ("  else body+=question('천장 높이만 알고 있다면 알려주세요',numberField('ceiling','천장 높이 (cm)',100,1000));\n", ""),
    ("  body+=question('책상을 놓을 벽은 얼마나 넓나요?'", "  if(a.roomKnown!=='unknown')body+=question('책상을 놓을 벽은 얼마나 넓나요?'"),
    # ── 3단계: '꼭 필요한 가구'·'가장 먼저 해결하고 싶은 것' 삭제 → 고른 가구 전부 필수, 우선순위 없음 ──
    ("     body+=question('그중 꼭 필요한 가구는요?',choices('mandatory',must),'고르지 않은 가구는 예산에 따라 빠질 수도 있어요.',true);\n", ""),
    ("     body+=question('가장 먼저 해결하고 싶은 건요?',`<select name=\"priority\" aria-label=\"가장 먼저 해결하고 싶은 가구\"><option value=\"\">전체를 함께 살펴볼게요</option>${a.items.filter(k=>k!=='other').map(k=>`<option value=\"${k}\" ${a.priority===k?'selected':''}>${E.ITEMS[k]}</option>`).join('')}</select>`);\n", ""),
    # ── 4단계: 수납 종류는 수납류를, 의자는 의자를 골랐을 때만(가구를 잘 모르겠어요도 표시). 최대 금액 삭제 ──
    ("  body+=question('어떤 수납이 더 필요하세요?'", "  if(a.items.includes('storage')||a.unknownItems)body+=question('어떤 수납이 더 필요하세요?'"),
    ("  body+=question('의자는 어떤 걸 보고 싶으세요?'", "  if(a.items.includes('chair')||a.unknownItems)body+=question('의자는 어떤 걸 보고 싶으세요?'"),
    ("  body+=question('최대로 쓸 수 있는 금액이 있다면요?',numberField('cap','최대 금액 (만원)',1,10000),'예를 들어 300만원 이상을 고르셨어도 최대 350만원으로 정할 수 있어요.');\n", ""),
    # 숨긴·삭제한 질문의 값 정리(예전 임시저장·결과 링크 포함)
    (" if(!(a.items.includes('bed')&&!a.items.includes('mattress')))a.mat=",
     " if(a.roomKnown==='unknown'){a.ceiling=null;a.wallWidth=null;}\n"
     " if(!a.unknownItems)a.mandatory=a.items.filter(k=>k!=='other');a.priority='';a.cap=null;\n"
     " if(!a.unknownItems&&!a.items.includes('storage'))a.storageType=[];\n"
     " if(!a.unknownItems&&!a.items.includes('chair'))a.chair='auto';\n"
     " if(!(a.items.includes('bed')&&!a.items.includes('mattress')))a.mat="),
    # ── 일반 책상만 고르고 높이 조절은 '꼭 필요해요' → 모션데스크로 추천(일반 책상에는 높이 조절 제품이 없음) ──
    ("  const wantedDesk=a.items.filter(x=>deskCats.includes(x));\n  const mandatoryDesk=a.mandatory.filter(x=>deskCats.includes(x));\n",
     "  const motionSwap=a.motion==='must'&&a.items.some(x=>x==='desk'||x==='desk0')&&!a.items.some(x=>x==='mdesk'||x==='mdesk0');\n"
     "  const toM=x=>motionSwap?({desk:'mdesk',desk0:'mdesk0'}[x]||x):x;\n"
     "  const wantedDesk=a.items.filter(x=>deskCats.includes(x)).map(toM);\n"
     "  const mandatoryDesk=a.mandatory.filter(x=>deskCats.includes(x)).map(toM);\n"),
    ("    if(dk&&SALES[dk]?.measured)add(1,'많은 분이 선택한 베스트셀러 책상이에요');",
     "    if(motionSwap&&dm?.motion)add(0,'높이 조절이 꼭 필요하다고 하셔서 모션데스크로 골랐어요');\n"
     "    if(dk&&SALES[dk]?.measured)add(1,'많은 분이 선택한 베스트셀러 책상이에요');"),
    ("consultOnly:`${role==='desk'?'책상':role==='storage'?'수납장':ITEMS[role]||role} 은(는) 지금 조건에",
     "consultOnly:`${(n=>n+josa(n,'는','은'))(role==='desk'?'책상':role==='storage'?'수납장':ITEMS[role]||role)} 지금 조건에"),
]
GEO_FILE = ROOT / "source" / "sigungu.json"
# 제품 데이터·링크·사진은 서버(app/data_store.py)가 활성 버전으로 채운다
DATA_TAGS = {"catalog": "__DK_CATALOG__", "links": "__DK_LINKS__", "images": "__DK_IMAGES__"}
INJECT = '<script src="/collect.js"></script>\n</body>'


def build() -> None:
    html = SRC.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        n = html.count(old)
        if n != 1:
            raise SystemExit(f"[중단] 교체 대상 문구가 {n}회 발견됨(1회여야 함): {old[:50]}…")
        html = html.replace(old, new)
    for tag, token in DATA_TAGS.items():
        pat = re.compile(rf'(<script id="{tag}" type="application/json">)(.*?)(</script>)', re.S)
        html, n = pat.subn(lambda m: m.group(1) + token + m.group(3), html)
        if n != 1:
            raise SystemExit(f"[중단] {tag} 데이터 태그가 {n}개(1개여야 함)")
    geo = GEO_FILE.read_text(encoding="utf-8").strip()
    html, n = re.subn(r'(<script id="geo" type="application/json">)(.*?)(</script>)', lambda m: m.group(1) + geo + m.group(3), html, flags=re.S)
    if n != 1:
        raise SystemExit(f"[중단] geo 데이터 태그가 {n}개(1개여야 함)")
    if html.count("</body>") != 1:
        raise SystemExit("[중단] </body> 태그가 1개가 아님")
    html = html.replace("</body>", INJECT)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"OK {OUT.relative_to(ROOT)} ({len(html):,} chars, 교체 {len(REPLACEMENTS)}건)")


if __name__ == "__main__":
    build()
