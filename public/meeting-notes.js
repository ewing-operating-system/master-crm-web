/**
 * meeting-notes.js — Next Chapter M&A Advisory
 * Auto-saves meeting form fields to Supabase on change.
 * Completeness score in real-time. Offline queue via localStorage.
 */
(function () {
  'use strict';

  const SUPABASE_URL = window.__SUPABASE_URL;
  const SUPABASE_KEY = window.__SUPABASE_ANON_KEY;
  const API = SUPABASE_URL + '/rest/v1/meeting_notes';
  const OFFLINE_KEY = 'meeting_notes_offline_queue';

  const CORE_FIELDS = [
    'owner_motivation','timeline','revenue_recurring_pct','revenue_ecommerce_pct',
    'gross_margin_pct','ebitda_margin_pct','key_employees','deal_breakers',
    'perfect_buyer_description','emotional_temperature','next_steps','story_elements',
  ];

  const FIELD_LABELS = {
    owner_motivation:'owner motivation', timeline:'timeline',
    revenue_recurring_pct:'recurring revenue %', revenue_ecommerce_pct:'eCommerce revenue %',
    gross_margin_pct:'gross margin', ebitda_margin_pct:'EBITDA margin',
    key_employees:'key employees', deal_breakers:'deal breakers',
    perfect_buyer_description:'perfect buyer description', emotional_temperature:'emotional temperature',
    next_steps:'next steps agreed', story_elements:'story elements',
  };

  const TEMP_LABELS = ['','Cold','Lukewarm','Warm','Hot','Ready to Engage'];
  const TEMP_COLORS = ['','#6c757d','#fd7e14','#ffc107','#28a745','#20c997'];

  const MEETING_ID = document.body.dataset.meetingId || '';
  if (!MEETING_ID) { console.warn('[meeting-notes] No data-meeting-id on <body>'); return; }

  const capturedState = {};

  function loadQ() { try { return JSON.parse(localStorage.getItem(OFFLINE_KEY)||'[]'); } catch(_){return [];} }
  function saveQ(q) { try { localStorage.setItem(OFFLINE_KEY, JSON.stringify(q)); } catch(_){} }
  async function flushQ() {
    const q = loadQ(); if (!q.length) return;
    const rem = [];
    for (const item of q) { try { await upsert(item.field_name, item.field_value, true); } catch(_){ rem.push(item); } }
    saveQ(rem);
  }
  window.addEventListener('online', flushQ);

  async function upsert(fieldName, fieldValue, skipQueue) {
    const body = { meeting_id:MEETING_ID, field_name:fieldName, field_value:String(fieldValue), captured_at:new Date().toISOString() };
    if (!navigator.onLine) {
      if (!skipQueue) { const q=loadQ(); const i=q.findIndex(e=>e.field_name===fieldName); if(i>=0)q[i]=body;else q.push(body); saveQ(q); }
      throw new Error('offline');
    }
    const res = await fetch(API, {
      method:'POST',
      headers:{ 'Content-Type':'application/json','apikey':SUPABASE_KEY,'Authorization':'Bearer '+SUPABASE_KEY,'Prefer':'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('HTTP '+res.status);
  }

  function getInd(fieldName) {
    let el = document.querySelector('[data-save-indicator="'+fieldName+'"]');
    if (!el) {
      el = document.createElement('span');
      el.dataset.saveIndicator = fieldName;
      el.className = 'mn-save-indicator';
      const src = document.querySelector('[data-field-name="'+fieldName+'"]');
      if (src) { const wrap = src.closest('.mn-field-wrap')||src.parentElement; if(wrap) wrap.appendChild(el); }
    }
    return el;
  }
  function setInd(fieldName, state) {
    const el = getInd(fieldName); if (!el) return;
    const labels={saving:'saving\u2026',saved:'saved \u2713',error:'retry\u2026',queued:'queued (offline)'};
    el.textContent = labels[state]||''; el.className='mn-save-indicator mn-save-'+state;
    if (state==='saved') setTimeout(()=>{ el.textContent=''; el.className='mn-save-indicator'; },2500);
  }

  function debounce(fn,ms){ let t; return function(...a){ clearTimeout(t); t=setTimeout(()=>fn.apply(this,a),ms); }; }

  async function saveField(fieldName, value) {
    capturedState[fieldName] = value;
    setInd(fieldName,'saving');
    try { await upsert(fieldName,value,false); setInd(fieldName,'saved'); }
    catch(e) { setInd(fieldName, e.message==='offline'?'queued':'error'); }
    updateCompleteness(); updatePost();
  }
  const dSave = debounce(saveField, 600);

  function getVal(f) {
    if (capturedState[f]!==undefined) return capturedState[f];
    const el=document.querySelector('[data-field-name="'+f+'"]');
    if (!el) return '';
    if (el.type==='range') return el.value!=='0'?el.value:'';
    return (el.value||'').trim();
  }
  function calcComp() {
    let filled=0; const missing=[];
    for (const f of CORE_FIELDS) { const v=getVal(f); if(v&&v!==''&&v!=='[]'&&v!=='{}') filled++; else missing.push(f); }
    return {filled, total:CORE_FIELDS.length, missing};
  }
  function updateCompleteness() {
    const sEl=document.getElementById('mn-completeness-score');
    const bEl=document.getElementById('mn-completeness-bar');
    const mEl=document.getElementById('mn-completeness-missing');
    if (!sEl) return;
    const {filled,total,missing}=calcComp();
    const pct=Math.round(filled/total*100);
    sEl.textContent=filled+' of '+total+' key fields captured ('+pct+'%)';
    if (bEl){ bEl.style.width=pct+'%'; bEl.className='mn-bar-fill '+(pct>=80?'mn-bar-green':pct>=50?'mn-bar-amber':'mn-bar-red'); }
    if (mEl){ if(!missing.length){ mEl.textContent='All key fields captured. Ready to generate every downstream document.'; mEl.className='mn-completeness-missing mn-missing-done'; } else { mEl.textContent='Missing: '+missing.map(f=>FIELD_LABELS[f]||f).join(', '); mEl.className='mn-completeness-missing'; } }
    updateUnlocks(filled);
  }
  function updateUnlocks(filled) {
    const rules={'mn-unlock-valuation':filled>=4,'mn-unlock-proposal':filled>=6,'mn-unlock-buyer-targeting':filled>=5,'mn-unlock-letter':filled>=3,'mn-unlock-full':filled>=10};
    for (const [id,ready] of Object.entries(rules)){ const el=document.getElementById(id); if(el) el.className='mn-unlock-item '+(ready?'mn-unlock-ready':'mn-unlock-locked'); }
  }

  function escH(s){ if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function updatePost() {
    const sEl=document.getElementById('mn-auto-summary'); if(!sEl) return;
    const motivation=getVal('owner_motivation'),timeline=getVal('timeline'),
      recurring=getVal('revenue_recurring_pct'),ecommerce=getVal('revenue_ecommerce_pct'),
      gross=getVal('gross_margin_pct'),ebitda=getVal('ebitda_margin_pct'),sde=getVal('sde_amount'),
      temp=getVal('emotional_temperature'),buyer=getVal('perfect_buyer_description'),
      story=getVal('story_elements'),quotes=getVal('verbatim_quotes');
    const lines=[];
    if(motivation) lines.push('Owner motivation: <strong>'+escH(motivation)+'</strong>.');
    if(timeline) lines.push('Timeline: <strong>'+escH(timeline)+'</strong>.');
    if(recurring||ecommerce){ let r=[]; if(recurring)r.push(recurring+'% recurring'); if(ecommerce)r.push(ecommerce+'% eCommerce'); lines.push('Revenue mix: <strong>'+r.join(', ')+'</strong>.'); }
    if(gross||ebitda||sde){ let m=[]; if(gross)m.push(gross+'% gross'); if(ebitda)m.push(ebitda+'% EBITDA'); if(sde)m.push('$'+escH(sde)+' SDE'); lines.push('Margins: <strong>'+m.join(' &middot; ')+'</strong>.'); }
    if(temp&&parseInt(temp)>0){ const v=parseInt(temp); lines.push('Emotional temperature: <strong style="color:'+TEMP_COLORS[v]+'">'+escH(TEMP_LABELS[v])+'</strong>.'); }
    if(buyer) lines.push('Perfect buyer: '+escH(buyer));
    if(story) lines.push('Story: '+escH(story));
    if(quotes) lines.push('<em>&ldquo;'+escH(quotes)+'&rdquo;</em>');
    sEl.innerHTML = lines.length ? lines.map(l=>'<p>'+l+'</p>').join('') : '<span class="mn-summary-empty">Summary populates as you capture data during the meeting.</span>';

    const eEl=document.getElementById('mn-followup-email-link');
    if(eEl){
      const company=document.body.dataset.companyName||'', owner=document.body.dataset.ownerName||'there';
      const subj='Following up \u2014 '+company+' / Next Chapter';
      let body='Hi '+owner+',\n\nThank you for your time today.';
      if(motivation) body+=' I appreciate you sharing your thinking around '+motivation+'.';
      body+='\n\nAgreed next steps:\n';
      const ns=getVal('next_steps');
      if(ns&&ns!=='[]'){ try{ const steps=JSON.parse(ns); if(Array.isArray(steps))steps.forEach(s=>{body+='\u2022 '+s+'\n';}); else body+=ns+'\n'; }catch(_){body+=ns+'\n';} }
      else body+='\u2022 [Fill in next steps]\n';
      body+='\nBest,\nEwing\nNext Chapter M&A Advisory';
      eEl.href='mailto:?subject='+encodeURIComponent(subj)+'&body='+encodeURIComponent(body);
    }
  }

  function serializeEmps() {
    const out=[];
    document.querySelectorAll('.mn-employee-row').forEach(row=>{
      const name=(row.querySelector('[data-col="name"]')||{}).value||'';
      const role=(row.querySelector('[data-col="role"]')||{}).value||'';
      const risk=(row.querySelector('[data-col="risk"]')||{}).value||'';
      if(name||role) out.push({name,role,retention_risk:risk});
    });
    return JSON.stringify(out);
  }
  function triggerEmpSave(){
    const val=serializeEmps(); capturedState['key_employees']=val;
    setInd('key_employees','saving');
    upsert('key_employees',val,false).then(()=>setInd('key_employees','saved')).catch(e=>setInd('key_employees',e.message==='offline'?'queued':'error'));
    updateCompleteness(); updatePost();
  }
  function addEmpRow(tbody,data){
    const row=document.createElement('tr'); row.className='mn-employee-row';
    const name=escH((data&&data.name)||''), role=escH((data&&data.role)||''), risk=(data&&data.retention_risk)||'';
    row.innerHTML='<td><input type="text" data-col="name" placeholder="Full name" value="'+name+'" class="mn-input"></td>'
      +'<td><input type="text" data-col="role" placeholder="Role / Title" value="'+role+'" class="mn-input"></td>'
      +'<td><select data-col="risk" class="mn-input"><option value="">&#8212;</option>'
      +'<option value="low"'+(risk==='low'?' selected':'')+'>Low</option>'
      +'<option value="medium"'+(risk==='medium'?' selected':'')+'>Medium</option>'
      +'<option value="high"'+(risk==='high'?' selected':'')+'>High</option>'
      +'</select></td><td><button type="button" class="mn-remove-row">&times;</button></td>';
    tbody.appendChild(row);
    const dS=debounce(triggerEmpSave,800);
    row.querySelectorAll('input').forEach(el=>el.addEventListener('input',dS));
    row.querySelectorAll('select').forEach(el=>el.addEventListener('change',triggerEmpSave));
    row.querySelector('.mn-remove-row').addEventListener('click',()=>{ row.remove(); triggerEmpSave(); });
  }
  function bindEmpTable(){
    const table=document.getElementById('mn-employee-table'), addBtn=document.getElementById('mn-add-employee');
    if(!table||!addBtn) return;
    const tbody=table.querySelector('tbody');
    addBtn.addEventListener('click',()=>addEmpRow(tbody,null));
    if(tbody&&!tbody.querySelectorAll('.mn-employee-row').length) addEmpRow(tbody,null);
    const wrap=table.closest('.mn-field-wrap')||table.parentElement;
    if(wrap&&!wrap.querySelector('[data-save-indicator="key_employees"]')){
      const ind=document.createElement('span'); ind.dataset.saveIndicator='key_employees'; ind.className='mn-save-indicator'; wrap.insertBefore(ind,table.nextSibling);
    }
  }

  function serializeDB(){ const out=[]; document.querySelectorAll('.mn-dealbreaker-cb:checked').forEach(cb=>out.push(cb.value)); const oth=document.getElementById('mn-dealbreaker-other'); if(oth&&oth.value.trim())out.push(oth.value.trim()); return JSON.stringify(out); }
  function triggerDB(){ const val=serializeDB(); capturedState['deal_breakers']=val; setInd('deal_breakers','saving'); upsert('deal_breakers',val,false).then(()=>setInd('deal_breakers','saved')).catch(e=>setInd('deal_breakers',e.message==='offline'?'queued':'error')); updateCompleteness(); updatePost(); }
  function bindDB(){
    document.querySelectorAll('.mn-dealbreaker-cb').forEach(cb=>cb.addEventListener('change',triggerDB));
    const oth=document.getElementById('mn-dealbreaker-other'); if(oth) oth.addEventListener('input',debounce(triggerDB,800));
    const wrap=document.querySelector('.mn-dealbreakers-wrap');
    if(wrap&&!wrap.querySelector('[data-save-indicator="deal_breakers"]')){const ind=document.createElement('span');ind.dataset.saveIndicator='deal_breakers';ind.className='mn-save-indicator';wrap.appendChild(ind);}
  }

  function serializeNS(){ const out=[]; document.querySelectorAll('.mn-nextstep-cb:checked').forEach(cb=>out.push(cb.value)); return JSON.stringify(out); }
  function triggerNS(){ const val=serializeNS(); capturedState['next_steps']=val; setInd('next_steps','saving'); upsert('next_steps',val,false).then(()=>setInd('next_steps','saved')).catch(e=>setInd('next_steps',e.message==='offline'?'queued':'error')); updateCompleteness(); updatePost(); }
  function bindNS(){
    document.querySelectorAll('.mn-nextstep-cb').forEach(cb=>cb.addEventListener('change',triggerNS));
    const wrap=document.querySelector('.mn-nextsteps-wrap');
    if(wrap&&!wrap.querySelector('[data-save-indicator="next_steps"]')){const ind=document.createElement('span');ind.dataset.saveIndicator='next_steps';ind.className='mn-save-indicator';wrap.appendChild(ind);}
  }

  function bindSlider(){
    const sl=document.querySelector('[data-field-name="emotional_temperature"]'), lbl=document.getElementById('mn-temp-label');
    if(!sl) return;
    function upd(){ const v=parseInt(sl.value); if(lbl){lbl.textContent=TEMP_LABELS[v]||'';lbl.style.color=TEMP_COLORS[v]||'inherit';} }
    sl.addEventListener('input',upd); upd();
  }

  function bindTabs(){
    const tabs=document.querySelectorAll('[data-tab-target]'), secs=document.querySelectorAll('[data-tab-section]');
    if(!tabs.length) return;
    function activate(target){
      tabs.forEach(t=>t.classList.toggle('mn-tab-active',t.dataset.tabTarget===target));
      secs.forEach(s=>{s.style.display=s.dataset.tabSection===target?'':'none';});
      history.replaceState(null,'','#'+target);
      if(target==='post'){updateCompleteness();updatePost();}
    }
    tabs.forEach(tab=>tab.addEventListener('click',()=>activate(tab.dataset.tabTarget)));
    const hash=(window.location.hash||'').replace('#','')||'pre';
    activate(['pre','during','post'].includes(hash)?hash:'pre');
  }

  async function loadExisting(){
    try{
      const res=await fetch(API+'?meeting_id=eq.'+encodeURIComponent(MEETING_ID),{headers:{'apikey':SUPABASE_KEY,'Authorization':'Bearer '+SUPABASE_KEY}});
      if(!res.ok) return;
      const rows=await res.json();
      for(const row of rows){ capturedState[row.field_name]=row.field_value; populateField(row.field_name,row.field_value); }
      updateCompleteness(); updatePost();
    }catch(e){console.warn('[meeting-notes] Load error:',e.message);}
  }
  function populateField(fieldName,value){
    if(fieldName==='key_employees'){try{const emps=JSON.parse(value);const t=document.getElementById('mn-employee-table');if(t){const tb=t.querySelector('tbody');tb.innerHTML='';emps.forEach(e=>addEmpRow(tb,e));if(!emps.length)addEmpRow(tb,null);}}catch(_){}return;}
    if(fieldName==='deal_breakers'){try{const items=JSON.parse(value);items.forEach(item=>{const cb=document.querySelector('.mn-dealbreaker-cb[value="'+item.replace(/"/g,'\\"')+'"]');if(cb)cb.checked=true;else{const o=document.getElementById('mn-dealbreaker-other');if(o&&!o.value)o.value=item;}});}catch(_){}return;}
    if(fieldName==='next_steps'){try{const items=JSON.parse(value);items.forEach(item=>{const cb=document.querySelector('.mn-nextstep-cb[value="'+item.replace(/"/g,'\\"')+'"]');if(cb)cb.checked=true;});}catch(_){}return;}
    const el=document.querySelector('[data-field-name="'+fieldName+'"]'); if(!el) return;
    el.value=value; if(el.type==='range') el.dispatchEvent(new Event('input'));
  }

  function bindFields(){
    document.querySelectorAll('[data-field-name]').forEach(el=>{
      if(el.classList.contains('mn-dealbreaker-cb')||el.classList.contains('mn-nextstep-cb')||el.closest('#mn-employee-table')) return;
      const h=()=>dSave(el.dataset.fieldName,el.value);
      el.addEventListener('change',h);
      if(['textarea','text','number','range'].includes(el.type)||el.tagName==='TEXTAREA') el.addEventListener('input',h);
    });
  }

  function injectStyles(){
    const s=document.createElement('style');
    s.textContent='.mn-save-indicator{font-size:11px;margin-left:8px;font-style:italic}'
      +'.mn-save-saving{color:#8b949e}.mn-save-saved{color:#3fb950}.mn-save-error{color:#f85149}.mn-save-queued{color:#d29922}'
      +'.mn-bar-fill{height:100%;border-radius:4px;transition:width .4s ease,background .4s ease}'
      +'.mn-bar-green{background:#3fb950}.mn-bar-amber{background:#d29922}.mn-bar-red{background:#f85149}'
      +'.mn-completeness-missing{font-size:12px;color:#8b949e;margin-top:6px}'
      +'.mn-missing-done{color:#3fb950!important}'
      +'.mn-unlock-item{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:6px;transition:all .3s}'
      +'.mn-unlock-ready{background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.3);color:#3fb950}'
      +'.mn-unlock-locked{background:rgba(139,148,158,.06);border:1px solid rgba(139,148,158,.12);color:#6e7681}'
      +'.mn-tab-active{border-bottom-color:#58a6ff!important;color:#58a6ff!important}'
      +'.mn-summary-empty{color:#8b949e;font-style:italic;font-size:13px}'
      +'#mn-auto-summary p{margin-bottom:8px;font-size:14px;line-height:1.6;color:#c9d1d9}'
      +'.mn-input{background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:7px 10px;font-size:13px;font-family:inherit;width:100%;transition:border-color .2s;box-sizing:border-box}'
      +'.mn-input:focus{outline:none;border-color:#58a6ff}'
      +'.mn-input option{background:#21262d}'
      +'.mn-remove-row{background:none;border:none;color:#f85149;font-size:18px;cursor:pointer;padding:2px 8px;border-radius:4px;line-height:1}'
      +'.mn-remove-row:hover{background:rgba(248,81,73,.12)}';
    document.head.appendChild(s);
  }

  function init(){
    injectStyles(); bindTabs(); bindFields(); bindSlider(); bindEmpTable(); bindDB(); bindNS();
    loadExisting().then(flushQ);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
