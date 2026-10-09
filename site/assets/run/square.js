// The square: the whole society as a map at one moment (charter/viewer/template.html's society view, on the shared clock).
// Mascots grow with wealth and smile or sweat as it moves; lines are this round's private messages (dashed when forged);
// bubbles are recent public posts. Playing steps through the run event by event and moves the page's clock as rounds pass.
import * as M from "./model.js";
import { esc, fmt, clip } from "./views.js";
import { agentColor } from "./mascots.js";

const SW = 1000, SH = 700, CX = 500, CY = 360;
const RES = { timber: "#8C6A43", stone: "#9A9890", copper: "#C46B3D", silver: "#AEB6C2", gold: "#D9A93A", crystal: "#7FA7D9", grain: "#C9A646", quicksilver: "#9FB4C7" };
const resCol = (k) => RES[k] || "#999";
const INTERESTING = new Set(["post", "anon_post", "dm", "transfer", "harvest", "enact", "repeal", "vote", "ballot_open", "ballot_close", "vetoed",
  "world_event", "raid", "departure", "disabled", "arrival", "story", "round_start", "tribute_payment", "tribute_demand", "project_open", "proposal", "patched", "rights", "bank_run"]);

export function mountSquare(el, st, onRound) {
  const S = st.S;
  let sIdx = S.roundEnd[st.round] ?? 0, playing = false, speed = 1, playT = null;
  const pos = {}, campPos = {};
  el.innerHTML = `<div class="square">
      <div class="stagewrap">
        <svg class="stage" viewBox="0 0 ${SW} ${SH}" preserveAspectRatio="xMidYMid meet">
          <g class="g-camps"></g><g class="g-paths"></g><g class="g-plaza"></g><g class="g-edges"></g><g class="g-agents"></g><g class="g-bubbles"></g><g class="g-fx"></g>
        </svg>
        <div class="toasts"></div>
        <div class="ctrl"><button class="pb" title="Play or pause (space)">▶</button><span class="rl"></span>
          <input type="range" min="0" max="${S.events.length - 1}" step="1" aria-label="Moment in the run">
          <select aria-label="Speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></div>
      </div>
      <aside class="sq-side"></aside>
    </div>`;
  const $ = (s) => el.querySelector(s);
  const ring = S.agents.filter((a) => a.cls !== "observer"), n = ring.length;
  ring.forEach((a, k) => { const t = -Math.PI / 2 + 2 * Math.PI * k / n; pos[a.id] = [CX + 285 * Math.cos(t), CY + 215 * Math.sin(t)]; });
  S.agents.filter((a) => a.cls === "observer").forEach((a, k) => { pos[a.id] = [SW - 60 - k * 70, SH - 50]; });
  const camps = S.inst.camps || [];
  camps.forEach((c, k) => { const t = -Math.PI / 2 + Math.PI / Math.max(1, camps.length) + 2 * Math.PI * k / camps.length; campPos[c.id] = [CX + 440 * Math.cos(t), CY + 300 * Math.sin(t)]; });
  $(".g-paths").innerHTML = `<ellipse cx="${CX}" cy="${CY}" rx="285" ry="215" fill="none" stroke="var(--line)" stroke-width="14" opacity=".6"/>`;
  $(".g-camps").innerHTML = camps.map((c) => { const [x, y] = campPos[c.id];
    return `<g class="camp" data-camp="${esc(c.id)}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})"><title>${esc(c.id)}: ${esc(c.resource)}</title>
      <clipPath id="sqclip-${esc(c.id)}"><circle r="22"/></clipPath><circle r="22" fill="var(--surface)"/>
      <rect class="lvl" x="-22" y="-22" width="44" height="44" fill="${resCol(c.resource)}" clip-path="url(#sqclip-${esc(c.id)})" opacity=".85"/>
      <circle class="rim" r="22" fill="none" stroke="var(--ink)" stroke-width="1.4"/>
      <text y="40" text-anchor="middle">${esc(c.resource)}</text><text class="s" y="53" text-anchor="middle">${esc(c.id)} · <tspan class="pct"></tspan></text></g>`; }).join("");
  const hashN = (s) => { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
  $(".g-agents").innerHTML = S.agents.map((a) => { const [x, y] = pos[a.id], dly = (hashN(a.id) % 1000) / 1000 * 2.6;
    return `<g class="node" data-agent="${esc(a.id)}" data-n="${a.n}" style="transform:translate(${x}px,${y}px)"><g class="sc"><g class="bob" style="animation-delay:-${dly.toFixed(2)}s">
      <use class="mu" href="#m${a.n}-ok" x="-24" y="-30" width="48" height="48"/></g><g class="crown"></g></g>
      <text class="nm" y="34" text-anchor="middle">${esc(a.id)}</text><text class="wv" y="47" text-anchor="middle"></text></g>`; }).join("");
  $(".pb").onclick = () => setPlaying(!playing);
  $("input[type=range]").oninput = (e) => { setPlaying(false); setIdx(+e.target.value, false); };
  $("select").onchange = (e) => { speed = +e.target.value; };
  el.querySelectorAll(".node").forEach((g) => (g.onclick = () => { location.hash = `#people/${encodeURIComponent(g.dataset.agent)}@${(S.roundAt[sIdx] ?? 0) + 1}`; }));

  function setPlaying(on) {
    playing = on; $(".pb").textContent = on ? "❚❚" : "▶"; clearTimeout(playT);
    if (on) { if (sIdx >= S.events.length - 1) setIdx(0, false); step(); }
  }
  const nextInteresting = (i) => { let j = i + 1; while (j < S.events.length - 1 && !INTERESTING.has(S.events[j].type)) j++; return Math.min(j, S.events.length - 1); };
  function step() {
    if (!playing || !el.isConnected) return;
    const j = nextInteresting(sIdx); setIdx(j, true);
    if (j >= S.events.length - 1) return setPlaying(false);
    const t = S.events[j].type;
    playT = setTimeout(step, ({ post: 1500, anon_post: 1500, story: 1600, round_start: 1500, enact: 1800, world_event: 1700, raid: 1800, ballot_close: 1300, dm: 650, harvest: 260, vote: 300 }[t] || 520) / speed);
  }
  function setIdx(nIdx, animate) {
    const prev = sIdx; sIdx = Math.max(0, Math.min(S.events.length - 1, nIdx));
    $("input[type=range]").value = sIdx;
    render();
    if (animate && sIdx > prev && sIdx - prev <= 80) for (let i = prev + 1; i <= sIdx; i++) fx(S.events[i]);
    const r = S.roundAt[sIdx] ?? 0;
    if (r !== st.round) onRound(r);                                   // move the page's clock (the strip, the URL)
  }
  function render() {
    const idx = sIdx, r = S.roundAt[idx] ?? 0, snap = r > 0 ? S.snapBy.get(r - 1) : null;
    const values = snap ? snap.values || {} : (S.truth.start_values || {});
    const decisive = new Set((snap && snap.decisive_set) || []);
    const max = Math.max(1e-9, ...S.agents.map((a) => values[a.id] ?? 0));
    $(".rl").textContent = `Round ${r + 1} of ${S.rounds}`;
    for (const a of S.agents) {
      const g = el.querySelector(`.node[data-n="${a.n}"]`); if (!g) continue;
      const gone = S.departs.has(a.id) && S.departs.get(a.id) <= idx;
      const arrival = S.arrives.has(a.id) && S.arrives.get(a.id) > idx;
      const v = values[a.id], s = a.cls === "observer" ? 0.8 : 0.75 + 0.85 * Math.sqrt(Math.max(0, v ?? 0) / max);
      let [x, y] = pos[a.id]; if (gone) { x = CX + (x - CX) * 1.18; y = CY + (y - CY) * 1.18; }
      g.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
      g.querySelector(".sc").setAttribute("transform", `scale(${s.toFixed(3)})`);
      g.style.opacity = arrival ? "0" : ""; g.classList.toggle("gone", gone);
      g.querySelector(".mu").setAttribute("href", `#m${a.n}-${gone ? "gone" : M.moodAt(S, a.id, Math.max(0, r - 1))}`);
      g.querySelector(".crown").innerHTML = decisive.has(a.id) ? `<path d="M-10 -31 L-8 -42 L-3.5 -35.5 L0 -44 L3.5 -35.5 L8 -42 L10 -31 Z" fill="#c9a227" stroke="#7a5d0c" stroke-width="1"/>` : "";
      g.querySelector(".nm").setAttribute("y", (34 * s + 4).toFixed(1));
      const wv = g.querySelector(".wv"); wv.setAttribute("y", (34 * s + 17).toFixed(1)); wv.textContent = a.cls === "observer" ? "watching" : v != null ? fmt(v) : "";
    }
    const pairs = new Map(), r0 = S.roundStart[r] ?? 0;
    for (const m of S.dms) { if (m.i > idx) break; if (m.i < r0 || !pos[m.from] || !pos[m.to]) continue;
      const k = [m.from, m.to].sort().join("|"), p = pairs.get(k) || { n: 0, last: 0, from: m.from, odd: false };
      p.n++; p.last = m.i; if (m.forged || m.shownAs || m.shownTo) p.odd = true; pairs.set(k, p); }
    $(".g-edges").innerHTML = [...pairs.entries()].map(([k, p]) => { const [a, b] = k.split("|"), [x1, y1] = pos[a], [x2, y2] = pos[b];
      const mx = (x1 + x2) / 2 + (CX - (x1 + x2) / 2) * 0.25, my = (y1 + y2) / 2 + (CY - (y1 + y2) / 2) * 0.25;
      return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}" fill="none" stroke="${agentColor(S.A.get(p.from), "solid")}"
        stroke-width="${Math.min(9, 1 + p.n * 1.1).toFixed(1)}" stroke-linecap="round" opacity="${idx - p.last < 12 ? .75 : .32}"${p.odd ? ' stroke-dasharray="5 6"' : ""}>
        <title>${esc(a)} and ${esc(b)}: ${p.n} message${p.n > 1 ? "s" : ""} this round</title></path>`; }).join("");
    for (const c of camps) {
      const g = el.querySelector(`.camp[data-camp="${CSS.escape(c.id)}"]`); if (!g) continue;
      const f = snap && snap.stocks ? snap.stocks[c.id] : (c.S != null && c.K ? c.S / c.K : null);
      if (f != null) { const h = 44 * Math.max(0, Math.min(1, f)); g.querySelector(".lvl").setAttribute("y", (22 - h).toFixed(1)); g.querySelector(".lvl").setAttribute("height", h.toFixed(1)); g.querySelector(".pct").textContent = Math.round(100 * f) + "%"; }
    }
    const regime = snap ? M.regimeOf(snap) : (S.score.summary || {}).regime_start || "";
    const active = M.lawsInForce(S, idx);
    $(".g-plaza").innerHTML = `<circle cx="${CX}" cy="${CY}" r="92" fill="var(--surface)" stroke="var(--ink)" stroke-width="1"/>
      <text x="${CX}" y="${CY - 8}" text-anchor="middle" class="pz-big">${esc(regime || "the square")}</text>
      <text x="${CX}" y="${CY + 16}" text-anchor="middle" class="pz">round ${r + 1} · ${active.size} law${active.size === 1 ? "" : "s"} in force</text>
      ${snap ? `<text x="${CX}" y="${CY + 34}" text-anchor="middle" class="pz">${Math.round(100 * (snap.franchise_share || 0))}% can vote · ${decisive.size} decide</text>` : ""}`;
    const bub = new Map();
    for (const p of S.posts) { if (p.i > idx) break; if (idx - p.i <= 30 && p.who && pos[p.who]) bub.set(p.who, p); }
    $(".g-bubbles").innerHTML = [...bub.values()].map((p) => { const [x, y] = pos[p.who], t = clip(p.text, 46), w = Math.min(280, 14 + t.length * 6.1);
      const by = y < CY ? y + 52 : y - 70, bx = Math.max(6, Math.min(SW - w - 6, x - w / 2));
      return `<g class="bubble" opacity="${Math.max(.6, 1 - (idx - p.i) / 60).toFixed(2)}"><rect x="${bx.toFixed(1)}" y="${by.toFixed(1)}" width="${w.toFixed(1)}" height="24" rx="2"/>
        <text x="${(bx + 10).toFixed(1)}" y="${(by + 16).toFixed(1)}">${esc(t)}</text></g>`; }).join("");
    side(idx, r, active);
  }
  let lastSig = "";
  function side(idx, r, active) {
    const tk = ticker(idx, 12), sig = `${r}|${tk.length ? tk[0].i : -1}|${active.size}`;
    if (sig === lastSig) return; lastSig = sig;
    $(".sq-side").innerHTML = `<h3 class="kicker">Laws in force</h3><ul class="lawlist">${[...active.values()].map((l) => `<li><a class="lawref" href="#laws/${esc(l.law)}@${r + 1}" data-law="${esc(l.law)}">${esc(l.law)}</a> ${esc(l.title || (S.laws.get(l.law) || {}).title || "")}</li>`).join("") || '<li class="meta">None yet.</li>'}</ul>
      <h3 class="kicker">Latest</h3><ul class="ticker">${tk.map((x) => `<li><span class="meta">round ${x.r + 1}</span> ${x.h}</li>`).join("") || '<li class="meta">Nothing yet.</li>'}</ul>
      <p class="meta">Mascots grow with wealth and smile or sweat as it moves. ♛ marks the decisive set. Lines are this round's private messages (dashed: forged); boxes are public posts. Click a mascot for its dossier.</p>`;
  }
  function ticker(idx, n) {
    const out = [];
    for (let i = idx; i >= 0 && out.length < n; i--) {
      const e = S.events[i], d = e.data || {}, t = e.type; let h = null;
      if (t === "enact" && e.agent !== "constitution") h = `<b>${esc(d.law)} ${esc(d.title || "")}</b> becomes law`;
      else if (t === "repeal") h = `${esc(d.law)} repealed`;
      else if (t === "vetoed") h = `The Board vetoes ${esc(d.law)}`;
      else if (t === "proposal") h = `${esc(e.agent)} proposes <b>${esc(d.title || d.law)}</b>`;
      else if (t === "ballot_close") h = `Ballot ${esc(d.ballot)}: <b>${esc(d.result)}</b>`;
      else if (t === "world_event") h = esc(clip(d.text, 120));
      else if (t === "raid") h = `<b>Raid</b> on ${esc(d.camp)}`;
      else if (t === "departure" || t === "disabled") h = `${esc(d.agent || e.agent)} ${t === "disabled" ? "is removed" : "leaves"}`;
      else if (t === "story") h = `<b>${esc(d.headline || "")}</b>`;
      else if (t === "tribute_demand") h = `Tribute demanded: ${fmt((d.demand || {}).value)}`;
      if (h) out.push({ i, h, r: S.roundAt[i] });
    }
    return out;
  }
  function fly(a, b, html, dur = 900) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g"); g.innerHTML = html; $(".g-fx").appendChild(g);
    g.animate([{ transform: `translate(${a[0]}px,${a[1]}px)`, opacity: 0 }, { opacity: 1, offset: .15 }, { transform: `translate(${b[0]}px,${b[1]}px)`, opacity: 1, offset: .9 },
      { transform: `translate(${b[0]}px,${b[1]}px)`, opacity: 0 }], { duration: dur / Math.sqrt(speed), easing: "ease-in-out" }).onfinish = () => g.remove();
  }
  function popAt(xy, html, dur = 1100) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g"); g.innerHTML = html; $(".g-fx").appendChild(g);
    g.animate([{ transform: `translate(${xy[0]}px,${xy[1]}px) scale(.3)`, opacity: 0 }, { transform: `translate(${xy[0]}px,${xy[1] - 30}px) scale(1.1)`, opacity: 1, offset: .3 },
      { transform: `translate(${xy[0]}px,${xy[1] - 46}px) scale(1)`, opacity: 0 }], { duration: dur / Math.sqrt(speed), easing: "ease-out" }).onfinish = () => g.remove();
  }
  function toast(html) {
    const box = $(".toasts"), t = document.createElement("div"); t.className = "toast"; t.innerHTML = html; box.appendChild(t);
    while (box.children.length > 3) box.firstChild.remove(); setTimeout(() => t.remove(), 3300);
  }
  const mark = (s, size = 18) => `<text text-anchor="middle" dominant-baseline="central" font-size="${size}">${s}</text>`;
  function fx(e) {
    if (!e) return; const d = e.data || {}, P = pos;
    switch (e.type) {
      case "dm": if (P[e.agent] && P[d.to]) fly(P[e.agent], P[d.to], mark(d.encrypted ? "🔒" : "✉️", 16), 950); break;
      case "transfer": if (P[e.agent] && P[d.to]) fly(P[e.agent], P[d.to], `<circle r="7" fill="${resCol(d.item)}" stroke="var(--bg)" stroke-width="2"/>`, 1200); break;
      case "harvest": if (campPos[d.camp] && P[e.agent] && d.yield > 0) fly(campPos[d.camp], P[e.agent], `<circle r="5" fill="${resCol((camps.find((c) => c.id === d.camp) || {}).resource)}"/>`, 900); break;
      case "vote": if (P[e.agent]) popAt(P[e.agent], mark(d.choice === "yes" ? "👍" : d.choice === "no" ? "👎" : "🤷", 20)); break;
      case "post": case "anon_post": if (P[e.agent]) popAt(P[e.agent], mark("💬", 18), 800); break;
      case "proposal": if (P[e.agent]) popAt(P[e.agent], mark("📜", 22), 1300); break;
      case "enact": if (e.agent !== "constitution") toast(`${esc(d.law)} · ${esc(d.title || "")} is now law`); break;
      case "repeal": toast(`${esc(d.law)} repealed`); break;
      case "vetoed": toast(`The Board vetoes ${esc(d.law)}`); break;
      case "raid": { toast(`Raid on ${esc(d.camp)}`); const g = el.querySelector(`.camp[data-camp="${CSS.escape(d.camp || "")}"]`); if (g) { g.classList.remove("raid"); void g.getBBox(); g.classList.add("raid"); } break; }
      case "departure": case "disabled": toast(`${esc(d.agent || e.agent)} ${e.type === "disabled" ? "is removed" : "leaves"}`); break;
      case "world_event": toast(esc(clip(d.text, 80))); break;
      case "round_start": toast(`Round ${(d.round ?? e.round) + 1}`); break;
      case "ballot_close": toast(`Ballot ${esc(d.ballot)}: ${esc(d.result)}`); break;
    }
  }
  render();
  return {
    // the page's clock moved (the strip, the keyboard): jump to the end of that round unless we are already in it
    setRound(r) { if ((S.roundAt[sIdx] ?? 0) !== r) { setPlaying(false); sIdx = S.roundEnd[r] ?? sIdx; $("input[type=range]").value = sIdx; render(); } },
    togglePlay() { setPlaying(!playing); },
    stop() { setPlaying(false); },
  };
}
