/* HireSignal shared UI helpers (T20 UI redesign): icons, the pipeline view, drag-and-drop, backend status.
   A view only: it renders what the station API reports (/ui/progress, /ui/batch/status, a result) and invents no
   status, duration or percentage. Icons are simple stroke paths drawn for this project (no third-party icon set). */
"use strict";
const HS = (() => {
  const P = {
    logo:'<path d="M7 17v-5M12 17V7M17 17v-7"/>',
    file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    files:'<path d="M9 7V5a2 2 0 0 1 2-2h5l4 4v10a2 2 0 0 1-2 2h-2"/><path d="M13 9H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2v-6z"/>',
    users:'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.5 3.2-5.5 6.5-5.5s5.9 2 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.8c1.6.8 2.7 2.6 3 5.2"/>',
    upload:'<path d="M12 15V4M7 9l5-5 5 5M5 20h14"/>',
    check:'<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    x:'<path d="M6 6l12 12M18 6L6 18"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    alert:'<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.01"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/>',
    grid:'<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    newdoc:'<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5"/><path d="M13 3v5h5v3M18 15v6M15 18h6"/>',
    list:'<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6l.01 0M4.5 12l.01 0M4.5 18l.01 0"/>',
    activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    compare:'<rect x="3.5" y="4" width="7" height="16" rx="1.5"/><rect x="13.5" y="4" width="7" height="16" rx="1.5"/><path d="M6 9h2M16 9h2M6 13h2M16 13h2"/>',
    play:'<path d="M7 4.5v15l12-7.5z"/>',
    shield:'<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M8.8 12.2l2.2 2.2 4.4-4.6"/>',
    sparkle:'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z"/>',
    arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
    back:'<path d="M19 12H5M11 6l-6 6 6 6"/>',
    refresh:'<path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4"/>',
    loop:'<path d="M17 2l3 3-3 3"/><path d="M4 11V9a4 4 0 0 1 4-4h12M7 22l-3-3 3-3"/><path d="M20 13v2a4 4 0 0 1-4 4H4"/>',
    split:'<path d="M6 3v6a3 3 0 0 0 3 3h6a3 3 0 0 1 3 3v6M6 21v-6"/><path d="M3 18l3 3 3-3M15 6l3-3 3 3"/>',
    hourglass:'<path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9"/>',
    skip:'<path d="M5 5l8 7-8 7M17 5v14"/>',
    trash:'<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    download:'<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    merge:'<path d="M6 3v4a5 5 0 0 0 5 5h2a5 5 0 0 1 5 5v4M18 3v4a5 5 0 0 1-5 5"/>',
    eye:'<path d="M2.5 12S6 5 12 5s9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7z"/><circle cx="12" cy="12" r="3"/>',
    mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5L12 13l8.5-6.5"/>',
    book:'<path d="M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2z"/><path d="M4 20a2 2 0 0 0 2 2h13v-4"/>'};
  const icon = (n, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

  /* Fill every <i data-ic="name"></i> placeholder of the static HTML with its icon. */
  function paintIcons(root = document){ root.querySelectorAll("i[data-ic]").forEach(el => { el.outerHTML = icon(el.dataset.ic, "i " + (el.className || "")); }); }

  /* ---------------- pipeline: the real n8n order (n8n/hiresignal_v1.json) ---------------- */
  const STAGE = {
    reader: {title:"CV Reader", what:"Reads the file: its text layer, or OCR + a vision model (late fusion) for scans and photos."},
    profile:{title:"Profile Agent", what:"Hides the identity in code, then lists skills, jobs and degrees."},
    job:    {title:"Job Agent", what:"Turns the job text into must-have and nice-to-have requirements.", tag:"skipped with a confirmed card"},
    rag:    {title:"RAG Retrieval", what:"Looks up skill meanings from ESCO. It gives knowledge, never CV evidence.", tag:"only without a literal CV match"},
    match:  {title:"Matcher", what:"Checks whether the CV meets each job requirement, with an exact CV quote."},
    judge:  {title:"Judge", what:"Checks whether the CV quote supports the match."},
    bias:   {title:"Bias Auditor", what:"Checks for unfair identity-related changes (counterfactual swap test)."},
    outcome:{title:"Outcome Gate", what:"Applies the existing decision rules: invite, reject or review."},
    report: {title:"Report Writer", what:"Writes the recruiter summary and the letter, then fact-checks them."},
    human:  {title:"Human Review", what:"Borderline or flagged cases wait for the recruiter's decision.", tag:"review cases only"}};
  const LAYOUT = ["reader", {par:["profile", "job"]}, {loop:["rag", "match", "judge"]}, "bias", "outcome", "report", "human"];
  const LABEL = {pending:"Pending", running:"Running", done:"Completed", failed:"Failed", skipped:"Skipped", waiting:"Waiting for recruiter"};
  const LOOP = ["rag", "match", "judge"];

  /* One stage's state from a /ui/progress snapshot `p` and the run context `o`:
     o.phase: idle | running | done | error;  o.outcome: invite | reject | review (when known);  o.formWaiting: bool */
  function stage(k, p, o){
    const d = (p.stages || {})[k], T = p.total_requirements, fin = o.phase === "done" || o.phase === "error";
    let s = d ? ({running:"running", done:"done", error:"failed"}[d.status] || "pending") : "pending";
    let sum = d ? (d.summary || "") : "", prog = null;
    const time = d && d.elapsed_s != null ? Number(d.elapsed_s) : null;
    if (LOOP.includes(k) && T) {
      prog = {done:(d && d.done) || 0, total:T};
      if (s === "done" && prog.done < T && !fin) s = "running";  // between two requirements of the loop
      if (d && s !== "failed") sum = `${sum}${sum ? " · " : ""}${prog.done} of ${T} requirements`;
    }
    if (k === "job" && !d && p.card_given) { s = "skipped"; sum = "Skipped: the recruiter's confirmed requirement card is used."; }
    if (k === "human") {
      if (o.outcome === "review") { s = "waiting"; sum = o.formWaiting ? "The gate sends this case to the recruiter (n8n form waiting)." : "The gate sends this case to the recruiter."; }
      else if (o.outcome) { s = "skipped"; sum = `Not needed: the gate decided "${o.outcome}".`; }
    }
    if (fin && s === "running") { s = o.phase === "error" ? "failed" : "done"; if (o.phase === "error") sum = "The run stopped while this stage was running."; }
    if (fin && s === "pending" && k !== "human") {
      if (o.phase === "error") sum = "Not reached.";
      else { s = "skipped"; sum = k === "job" ? "Skipped: the recruiter's confirmed requirement card was used." : "Not called in this run."; }
    }
    return {k, ...STAGE[k], s, sum, time, prog};
  }

  const fmt = t => `${t < 10 ? t.toFixed(1) : t.toFixed(t < 100 ? 1 : 0)} s`;
  function stateIcon(s){
    if (s === "running") return '<span class="spin" role="img" aria-label="running"></span>';
    return icon({done:"check", failed:"alert", waiting:"hourglass", skipped:"skip"}[s] || "clock");
  }
  function row(x, n){
    const tm = x.s === "running" ? `<span class="spin" aria-hidden="true"></span>${x.time != null ? `Running ${fmt(x.time)}` : "Running"}`
             : x.time != null && (x.s === "done" || x.s === "failed") ? `${icon("clock")}${fmt(x.time)}` : "—";
    const bar = x.prog && x.s !== "skipped" && x.s !== "pending" ? `<div class="pbar"><i style="width:${Math.min(100, 100 * x.prog.done / x.prog.total)}%"></i></div>` : "";
    return `<div class="stg ${x.s}" data-stage="${x.k}"><div class="n">${n}</div><div class="si">${stateIcon(x.s)}</div>
      <div><div class="nm">${x.title}${x.tag ? `<small>${x.tag}</small>` : ""}</div><div class="ds">${x.what}</div>
      ${x.sum ? `<div class="sm">${esc(x.sum)}</div>` : ""}${bar}</div>
      <div class="tm">${tm}</div><div class="stt"><span class="st ${x.s}">${LABEL[x.s]}</span></div></div>`;
  }

  /* p: progress snapshot ({stages, total_requirements, card_given}); o: see stage(); o.groupTime: measured
     RAG + Matcher + Judge time from result.timings_s (shown only when known). */
  function renderPipeline(el, p, o){
    p = p || {stages:{}}; o = o || {phase:"idle"};
    let n = 0;
    el.innerHTML = `<div class="pipe">${LAYOUT.map(item => {
      if (typeof item === "string") return row(stage(item, p, o), ++n);
      if (item.par) return `<div class="grp"><div class="grp-h">${icon("split")}In parallel after the Reader</div>${item.par.map(k => row(stage(k, p, o), ++n)).join("")}</div>`;
      const rows = item.loop.map(k => stage(k, p, o));
      const T = p.total_requirements, j = rows[2].prog, cur = ((p.stages || {}).match || {}).req_id;
      const info = T ? `<span class="tm" style="text-transform:none">${j ? `${j.done} of ${T} checked` : ""}${cur && o.phase === "running" ? ` · now ${esc(cur)}` : ""}${o.groupTime != null ? ` · ${icon("clock")}${fmt(o.groupTime)} in total` : ""}</span>` : "";
      return `<div class="grp"><div class="grp-h">${icon("loop")}For each requirement, one at a time<span class="grow"></span>${info}</div>${rows.map(x => row(x, ++n)).join("")}</div>`;
    }).join("")}</div>`;
  }

  /* A saved result has no live progress: rebuild what it proves (statuses + the measured timings_s only). */
  function replay(res){
    const n = (res.requirements || []).length, t = res.timings_s || {}, rd = res.reader || {}, sw = (res.bias || {}).swap || {};
    const cnt = d => (res.requirements || []).filter(x => x.decision === d).length;
    const routes = [...new Set(rd.read_path || [])].join(", ");
    const st = {
      reader:{status:"done", summary:`${rd.file_type || "?"}, route ${routes || "-"}`, elapsed_s:t.reader},
      profile:{status:"done", summary:"anonymised; identity stored apart", elapsed_s:t.profile},
      rag:{status:"done", summary:"per requirement", done:n},
      match:{status:"done", summary:`${cnt("MET")} met, ${cnt("MISSING")} missing, ${cnt("UNCERTAIN")} uncertain`, done:n},
      judge:{status:"done", summary:"quotes checked", done:n},
      outcome:{status:"done", summary:`${res.outcome}${res.rule ? ` (${res.rule})` : ""}`},
      report:{status:"done", summary:`${(res.report || {}).source === "llm" ? "AI" : "checked template"} report`}};
    // with a confirmed card, n8n's "Confirmed job card" node reports elapsed_s 0: the Job Agent (/job) was not called
    if (t.job) st.job = {status:"done", summary:`${n} requirements`, elapsed_s:t.job};
    if (sw.ran != null) st.bias = {status:"done", summary: sw.ran ? `swap test ran (${sw.counterfactual}), identical input: ${sw.identical_matcher_input ? "yes" : "no"}` : `swap test skipped (${sw.skipped || "not needed"})`};
    return {snap:{finished:true, total_requirements:n, card_given:!t.job, stages:st}, groupTime: t.match_and_judge ?? null};
  }

  /* Prefer what was measured live (durations, summaries) over the replay, stage by stage, when the stage had finished. */
  function merge(base, live){
    if (!live || !live.stages) return base;
    const out = {...base, stages:{...base.stages}};
    for (const [k, d] of Object.entries(live.stages)) {
      if (d.status !== "done") continue;
      if (LOOP.includes(k) && base.total_requirements && (d.done || 0) < base.total_requirements) continue;
      out.stages[k] = {...out.stages[k], ...d};
    }
    return out;
  }

  /* ---------------- drag and drop onto a zone that wraps a file input ---------------- */
  function dropzone(zone, input, onFiles){
    const on = e => { e.preventDefault(); zone.classList.add("drag"); };
    const off = e => { e.preventDefault(); zone.classList.remove("drag"); };
    zone.addEventListener("dragenter", on); zone.addEventListener("dragover", on);
    zone.addEventListener("dragleave", e => { if (!zone.contains(e.relatedTarget)) off(e); });
    zone.addEventListener("drop", e => { off(e); const f = [...(e.dataTransfer.files || [])]; if (f.length) onFiles(f); });
    zone.addEventListener("click", e => { if (!e.target.closest("button,label,input,a,textarea")) input.click(); });
  }

  /* ---------------- backend status chip (GET /ready: API + local LLM) ---------------- */
  async function ready(el){
    try {
      const r = await fetch("/ready");
      if (r.ok) { el.className = "live ok"; el.textContent = "AI ready · local models"; return; }
      el.className = "live warn"; el.textContent = "API up · LLM not ready";
    } catch(e) { el.className = "live bad"; el.textContent = "Station API offline"; }
  }

  return {icon, esc, paintIcons, renderPipeline, replay, merge, dropzone, ready, STAGE};
})();
