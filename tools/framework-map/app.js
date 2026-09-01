/* ---------- helpers ---------- */
const E = (s)=>String(s==null?"":s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const slug = (s)=>s.toLowerCase().replace(/[^a-z0-9]+/g,"-");
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
window.LANG = "en";
const T = (k)=> (LBL[window.LANG] && LBL[window.LANG][k]!=null) ? LBL[window.LANG][k] : (LBL.en[k]!=null?LBL.en[k]:k);
const getDS = ()=> (window.LANG==="ro" && typeof DATA_RO!=="undefined" && DATA_RO) ? DATA_RO : DATA;

/* ---------- render one action ---------- */
function actionHTML(a){
  const args = a.a||[];
  let argsHTML;
  if(!args.length){
    argsHTML = '<div class="noargs">'+T('l_noargs')+'</div>';
  } else {
    argsHTML = args.map(g=>
      `<div class="arg"><span class="an">${E(g.n)}</span>`+
      (g.r?'<span class="req">'+T('l_req')+'</span>':'<span class="opt">'+T('l_opt')+'</span>')+
      (g.d?`<span class="ad">${E(g.d)}</span>`:'')+`</div>`
    ).join("");
  }
  const w = args.length===1?T('w_arg'):T('w_args');
  return `<details class="act"><summary>${E(a.n)}<span class="argn">${args.length} ${w}</span></summary>`+
    `<div class="abody">`+
    (a.d?`<div class="adesc">${E(a.d)}</div>`:'')+
    argsHTML+`</div></details>`;
}

/* ---------- render one tool card ---------- */
function toolCard(t){
  const acts = t.actions||[];
  const trig = (t.triggers||[]).slice(0,10);
  const searchBlob = (t.name+" "+t.desc+" "+(t.triggers||[]).join(" ")+" "+acts.map(a=>a.n+" "+a.d).join(" ")).toLowerCase();
  let body = `<div class="body">`;
  body += `<div class="full">${E(t.desc)}</div>`;
  if(t.example){ body += `<div class="sec-l">${T('l_primary')}</div><div class="ex">${E(t.example)}</div>`; }
  if(trig.length){ body += `<div class="sec-l">${T('l_triggers')}</div><div class="chiprow trigchips">`+trig.map(x=>`<span class="chip mono">${E(x)}</span>`).join("")+`</div>`; }
  if((t.secrets||[]).length){ body += `<div class="sec-l">${T('l_creds')}</div><div class="chiprow">`+t.secrets.map(s=>`<span class="lockchip" title="${E(s.desc)}">&#128274; ${E(s.name)}</span>`).join("")+`</div>`; }
  body += `<div class="sec-l">${T('l_actions')} &middot; ${acts.length}</div><div class="acts">`+acts.map(actionHTML).join("")+`</div>`;
  body += `</div>`;
  return `<details class="card tool-card" id="tool-${E(t.name)}" data-search="${E(searchBlob)}" data-name="${E(t.name)}">`+
    `<summary><div><div class="nm">${E(t.name)}</div><div class="ds">${E(t.desc)}</div></div>`+
    `<div class="meta"><span class="acount">${acts.length} ${T('w_actions')}</span>`+
    `<span class="dotr ${t.ready?'on':'off'}" title="${t.ready?T('tip_ready'):T('tip_needs')}"></span></div></summary>`+
    body+`</details>`;
}

/* ---------- render tools grouped by category ---------- */
function renderTools(){
  const cats = {};
  getDS().tools.forEach(t=>{ (cats[t.cat]=cats[t.cat]||[]).push(t); });
  const order = Object.keys(cats).sort();
  let html = "";
  order.forEach(cat=>{
    const list = cats[cat].sort((a,b)=>a.name.localeCompare(b.name));
    const id = "cat-"+slug(cat);
    html += `<div class="catwrap" data-cat="${E(cat)}">`+
      `<div class="cathead" data-target="${id}"><span class="tw">&#9660;</span><h3>${E(cat)}</h3><span class="cx">${list.length} ${T('w_tools')}</span></div>`+
      `<div class="catgrid" id="${id}">`+list.map(toolCard).join("")+`</div></div>`;
  });
  $("#tools-view").innerHTML = html;
}

/* ---------- render agents ---------- */
function agentCard(a){
  const acts = a.actions||[];
  const searchBlob = (a.name+" "+a.desc+" "+(a.triggers||[]).join(" ")+" "+acts.map(x=>x.n+" "+x.d).join(" ")).toLowerCase();
  let body = `<div class="body">`;
  body += `<div class="full">${E(a.desc)}</div>`;
  if(a.example){ body += `<div class="sec-l">${T('l_primary')}</div><div class="ex">${E(a.example)}</div>`; }
  if((a.tools||[]).length){ body += `<div class="sec-l">${T('l_drives')} &middot; ${a.tools.length}</div><div class="drives">`+a.tools.map(tn=>`<span class="tchip" data-jump="${E(tn)}">${E(tn)}</span>`).join("")+`</div>`; }
  body += `<div class="sec-l">${T('l_actions')} &middot; ${acts.length}</div><div class="acts">`+acts.map(actionHTML).join("")+`</div>`;
  body += `</div>`;
  return `<details class="card agent-card" id="agent-${E(a.name)}" data-search="${E(searchBlob)}" data-name="${E(a.name)}">`+
    `<summary><div><div class="nm">${E(a.name)}</div><div class="ds">${E(a.desc)}</div></div>`+
    `<div class="meta"><span class="acount">${acts.length} ${T('w_actions')}</span><span class="acount">${(a.tools||[]).length} ${T('w_tools')}</span></div></summary>`+
    body+`</details>`;
}
function renderAgents(){
  $("#agents-view").innerHTML = `<div class="catgrid">`+getDS().agents.slice().sort((a,b)=>a.name.localeCompare(b.name)).map(agentCard).join("")+`</div>`;
}

/* ---------- render skills ---------- */
function skillCard(s){
  const searchBlob = (s.name+" "+s.desc).toLowerCase();
  return `<details class="card skill-card" data-search="${E(searchBlob)}" data-name="${E(s.name)}">`+
    `<summary><div><div class="nm">${E(s.name)}</div><div class="ds">${E(s.desc)}</div></div>`+
    `<div class="meta"><span class="acount">${T('l_autotrigger')}</span></div></summary>`+
    `<div class="body"><div class="sec-l">${T('l_when')}</div><div class="full">${E(s.desc)}</div></div></details>`;
}
function renderSkills(){
  $("#skills-view").innerHTML = `<div class="catgrid">`+getDS().skills.slice().sort((a,b)=>a.name.localeCompare(b.name)).map(skillCard).join("")+`</div>`;
}

/* ---------- tabs ---------- */
function showTab(name){
  window.CURTAB = name;
  $$(".tabs button").forEach(b=>b.classList.toggle("on", b.dataset.tab===name));
  ["tools","agents","skills"].forEach(v=>{ $("#"+v+"-view").style.display = v===name ? "" : "none"; });
  $(".exp-bar").className = "exp-bar exp-"+name;
  applySearch();
}

/* ---------- search ---------- */
function applySearch(){
  const q = $("#search").value.trim().toLowerCase();
  const view = $("#"+window.CURTAB+"-view");
  let shown = 0;
  $$(".card", view).forEach(c=>{
    const hit = !q || c.dataset.search.includes(q);
    c.style.display = hit ? "" : "none";
    if(hit) shown++;
    if(q && hit) c.open = true; else if(q && !hit) c.open = false;
  });
  $$(".catwrap", view).forEach(w=>{
    const any = $$(".card", w).some(c=>c.style.display!=="none");
    w.style.display = any ? "" : "none";
  });
  $("#expcount").textContent = q ? (shown+" "+(shown===1?T('m_one'):T('m_many'))) : "";
  const em = $("#emptymsg"); if(em) em.style.display = shown ? "none" : "block";
}

/* ---------- expand / collapse all ---------- */
function setAll(open){
  const view = $("#"+window.CURTAB+"-view");
  $$(".card", view).forEach(c=>{ if(c.style.display!=="none") c.open = open; });
}

/* ---------- jump to a tool/agent ---------- */
function jumpTo(kind, name){
  const tab = kind==="agent" ? "agents" : "tools";
  showTab(tab);
  $("#search").value=""; applySearch();
  const el = document.getElementById((kind==="agent"?"agent-":"tool-")+name);
  if(!el){ return; }
  const grid = el.closest(".catgrid");
  if(grid){ grid.classList.remove("hide"); const head=grid.previousElementSibling; head&&head.classList.remove("closed"); }
  el.open = true;
  el.scrollIntoView({behavior:"smooth", block:"center"});
  el.classList.remove("hl"); void el.offsetWidth; el.classList.add("hl");
}

/* ---------- anchors: only the VISIBLE language keeps the canonical id ---------- */
const SECS = ["layers","split","triggers","loop","platform","schedules","store","together","prompts","cases"];
function fixAnchors(lang){
  const off = lang==="en" ? "ro" : "en";
  SECS.forEach(s=>{
    const on = document.querySelector('.lang-'+lang+' [data-sec="'+s+'"]');
    const hidden = document.querySelector('.lang-'+off+' [data-sec="'+s+'"]');
    if(hidden) hidden.id = s+"--"+off;
    if(on) on.id = s;
  });
}

/* ---------- language ---------- */
function setLang(lang){
  window.LANG = lang;
  document.body.classList.toggle("ro", lang==="ro");
  document.documentElement.lang = lang;
  fixAnchors(lang);
  $$("[data-t]").forEach(el=>{ el.innerHTML = T(el.dataset.t); });
  const s = $("#search"); if(s) s.setAttribute("placeholder", T("ctl_search"));
  $$(".langtoggle button").forEach(b=>b.classList.toggle("on", b.dataset.lang===lang));
  renderTools(); renderAgents(); renderSkills();
  showTab(window.CURTAB||"tools");
}

/* ---------- wire up ---------- */
function init(){
  window.CURTAB = "tools";
  $("#search").addEventListener("input", applySearch);
  $$(".tabs button").forEach(b=>b.addEventListener("click", ()=>{ $("#search").value=""; showTab(b.dataset.tab); }));
  $("#expand-all").addEventListener("click", ()=>setAll(true));
  $("#collapse-all").addEventListener("click", ()=>setAll(false));
  $$(".langtoggle button").forEach(b=>b.addEventListener("click", ()=>{ $("#search").value=""; setLang(b.dataset.lang); }));
  document.addEventListener("click", (e)=>{
    const head = e.target.closest(".cathead");
    if(head){ head.classList.toggle("closed"); document.getElementById(head.dataset.target).classList.toggle("hide"); return; }
    const jc = e.target.closest("[data-jump]");
    if(jc){ jumpTo("tool", jc.dataset.jump); return; }
    const uj = e.target.closest("[data-ujump]");
    if(uj && uj.dataset.ukind!=="none"){ jumpTo(uj.dataset.ukind, uj.dataset.ujump); return; }
  });
  setLang("en");
}
document.addEventListener("DOMContentLoaded", init);
