// The run page's sections. Every view renders the run as of one shared round (state.round), so moving between sections keeps
// the moment: the chronicle's edition, an agent's dossier, the letters sent so far, the laws in force and the square all agree.
import * as M from "./model.js";
import { agentColor } from "./mascots.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const fmt = (x) => (x == null || isNaN(x) ? "–" : Math.abs(x) >= 100 ? x.toFixed(0) : Math.abs(x) >= 10 ? x.toFixed(1) : x.toFixed(2));
export const clip = (s, n) => { s = String(s ?? "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const pct = (x) => (x == null ? "–" : Math.round(100 * x) + "%");
const modelShort = (m) => { const s = String(m || "").replace(/^claude-/, "").replace(/-\d{8}$/, "").replace(/-(\d+)-(\d+)$/, " $1.$2");
  return s ? s[0].toUpperCase() + s.slice(1) : ""; };
const R = (r) => r + 1;                                                  // rounds are 0-based in the data, 1-based on the page

// ------------------------------------------------------------------ links and small pieces
export function href(st, section, target, round = st.round) {
  return `#${section}${target ? "/" + encodeURIComponent(target) : ""}@${R(round)}`;
}
export function mascot(S, id, size = 30, mood = "ok") {
  const a = S.A.get(id);
  return `<svg class="masc" width="${size}" height="${size}" viewBox="-2 -2 44 44" aria-hidden="true"><use href="#${a ? `m${a.n}-${mood}` : "m-anon"}"/></svg>`;
}
const moodNow = (st, id) => M.moodAt(st.S, id, st.round);
export function who(st, id, opts = {}) {
  const S = st.S, a = S.A.get(id);
  if (!a) return `<span class="who anon">${esc(id || "Anonymous")}</span>`;
  return `<a class="who" href="${href(st, "people", id)}" data-agent="${esc(id)}" style="--ink:${agentColor(a, "ink", st.dark)}">${esc(id)}</a>`
    + (opts.role ? ` <span class="role">${esc(M.CLASS_LABEL[a.cls] || a.cls)}</span>` : "");
}
function lawLink(st, id, label) {
  if (!id) return "";
  return `<a class="lawref" href="${href(st, "laws", id)}" data-law="${esc(id)}">${esc(label || id)}</a>`;
}
// escape, then turn law ids and law titles in free text into links
function txt(st, s) {
  const S = st.S;
  let h = esc(s);
  if (!S._lawRx) {
    const alts = [...S.titleLaw.keys()].sort((a, b) => b.length - a.length).map((t) => esc(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    S._lawRx = new RegExp(`\\b(L\\d{1,3})\\b${alts.length ? "|(" + alts.join("|") + ")" : ""}`, "g");
  }
  return h.replace(S._lawRx, (m, id, title) => {
    const lid = id || S.titleLaw.get(title.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"'));
    return lid && S.laws.has(lid) ? lawLink(st, lid, m) : m;
  });
}
const para = (st, s) => String(s || "").split(/\n{2,}/).map((p) => `<p>${txt(st, p).replace(/\n/g, "<br>")}</p>`).join("");
function spark(values, r, opts = {}) {
  const pts = values.map((v, k) => [k, v]).filter((p) => p[1] != null);
  if (pts.length < 2) return "";
  const W = opts.w || 300, H = opts.h || 48, lo = opts.zero ? 0 : Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  const span = hi - lo || 1, n = Math.max(1, values.length - 1);
  const X = (k) => 3 + (W - 6) * k / n, Y = (v) => H - 4 - (H - 8) * (v - lo) / span;
  const line = pts.map(([k, v]) => `${X(k).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const cur = values[Math.min(r, values.length - 1)];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${opts.fill ? `<polygon points="${X(pts[0][0])},${H} ${line} ${X(pts[pts.length - 1][0])},${H}" fill="${opts.color || "var(--ink)"}" opacity=".1"/>` : ""}
    <polyline points="${line}" fill="none" stroke="${opts.color || "var(--ink)"}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
    <line x1="${X(r)}" x2="${X(r)}" y1="0" y2="${H}" stroke="var(--accent)" stroke-width="1" vector-effect="non-scaling-stroke"/>
    ${cur != null ? `<circle cx="${X(r)}" cy="${Y(cur)}" r="3" fill="var(--accent)"/>` : ""}</svg>`;
}
const SYS_LABEL = { ballot_open: "Ballot opens", vetoed: "Vetoed", veto_window: "Veto window", veto_vote: "Veto vote", patched: "Patched",
  law_error: "Law error", proposal_failed: "Proposal failed", rights: "Rights", sanction: "Sanction", dm_limit: "Message limit", ruling: "Ruling",
  accuse: "Accusation", bank_run: "Bank run", raid: "Raid", tribute_demand: "Tribute demanded", tribute_payment: "Tribute paid",
  project_open: "Project", disabled: "Disabled" };
function sysText(st, it) {
  const d = it.data || {}, w = it.who ? who(st, it.who) + " " : "";
  switch (it.type) {
    case "ballot_open": return `Ballot <b>${esc(d.ballot)}</b> opens: ${txt(st, d.question)} <span class="meta">(${esc(String(d.rule || "").replace(/_/g, " "))}, ${(d.electorate || []).length} voters${d.closes_round != null ? `, closes round ${R(d.closes_round)}` : ""})</span>`;
    case "vetoed": return `<b>The Board vetoes ${lawLink(st, d.law)}</b>${d.by ? " (" + esc([].concat(d.by).join(", ")) + ")" : ""}`;
    case "veto_window": return `${lawLink(st, d.law)} enters the Board's veto window${d.until != null ? ` until round ${R(d.until)}` : ""}`;
    case "veto_vote": return `${w}${d.choice ? `votes <b>${esc(d.choice)}</b> on vetoing` : "casts a veto vote on"} ${lawLink(st, d.law)}`;
    case "patched": return `${w}patches ${lawLink(st, d.law)}: ${esc(clip(d.reason || "", 220))}`;
    case "law_error": return `${lawLink(st, d.law)} fails at run time: <code>${esc(clip(d.error, 140))}</code>`;
    case "proposal_failed": return `${w}proposal fails: ${esc(clip(d.reason || d.error || "", 260))}`;
    case "rights": return `${who(st, d.agent)} ${d.change === "grant" ? "gains" : "loses"} the right <b>${esc(d.right)}</b>${d.law ? " under " + lawLink(st, d.law) : ""}`;
    case "sanction": return `Sanction on ${who(st, d.agent)}: ${esc(Object.entries(d).filter(([k]) => !["agent", "law"].includes(k)).map(([k, v]) => k + " " + v).join(", "))}`;
    case "dm_limit": return `${w}sets the private-message limit to <b>${esc(d.n)}</b>${d.agent ? " for " + who(st, d.agent) : " for everyone"}`;
    case "ruling": return `${w}rules <b>${esc(d.verdict)}</b> on ${esc(d.case)}: ${esc(d.reason || "")}`;
    case "accuse": return `${w}accuses ${who(st, d.accused)} under ${esc(d.clause)}`;
    case "bank_run": return `<b>A run on the ${esc(d.currency)}</b>`;
    case "raid": return `<b>Raid on ${esc(d.camp)}</b>: ${fmt(d.stock_lost)} stock lost${d.seized ? ", goods seized from " + esc(Object.keys(d.seized).join(", ")) : ""}`;
    case "tribute_demand": return `<b>The outside power demands tribute</b> worth ${fmt((d.demand || {}).value)} by round ${R(d.deadline ?? 0)}`;
    case "tribute_payment": return `${w}pays ${fmt(d.qty)} ${esc(d.item)} toward the tribute`;
    case "project_open": return `<b>Project ${esc(d.project)}</b>: ${esc(clip(d.description || d.kind, 260))}`;
    case "disabled": return `<b>${who(st, d.agent)} is removed from the game</b>${d.cause ? ` (${esc(String(d.cause).replace(/_/g, " "))})` : ""}`;
    default: {
      const short = Object.entries(d).filter(([k, v]) => typeof v !== "object" && k !== "code").map(([k, v]) => `${k} ${v}`).join(" · ");
      return `${w}<b>${esc(it.type.replace(/_/g, " "))}</b> ${txt(st, clip(short, 260))}`;
    }
  }
}
function tally(st, b, idx) {
  const S = st.S, fin = b.close !== undefined && b.close <= idx;
  const vs = fin ? Object.entries(b.final || {}) : b.votes.filter((v) => v.i <= idx).map((v) => [v.who, v.choice]);
  const by = {}; for (const [w, c] of vs) (by[c] = by[c] || []).push(w);
  const sides = Object.entries(by).sort((x, y) => (x[0] === "yes" ? -1 : y[0] === "yes" ? 1 : 0)).map(([c, ws]) =>
    `<span class="side ${c === "yes" ? "yes" : c === "no" ? "no" : ""}"><b>${esc(c)} ${ws.length}</b>${ws.map((w) => `<a href="${href(st, "people", w)}" data-agent="${esc(w)}" title="${esc(w)}">${mascot(S, w, 22, moodNow(st, w))}</a>`).join("")}</span>`).join("");
  const silent = (b.electorate || []).filter((w) => !vs.some((v) => v[0] === w));
  return `<div class="tally">${sides || '<span class="meta">no votes yet</span>'}${silent.length ? `<span class="side silent"><b>silent ${silent.length}</b>${silent.map((w) => `<span title="${esc(w)}">${mascot(S, w, 18, "ok")}</span>`).join("")}</span>` : ""}</div>`;
}
const endIdx = (st) => st.S.roundEnd[st.round] ?? st.S.events.length - 1;

// ================================================================== front page
export function front(st) {
  const S = st.S, r = st.round, sum = S.score.summary || {};
  const cits = M.citizens(S);
  const facts = [["Agents", cits.length], ["Rounds", S.rounds], ["Regime", sum.regime_path ? String(sum.regime_path).replace(/->/g, "→") : null], ["Laws enacted", sum.laws_enacted != null ? `${sum.laws_enacted} of ${sum.laws_proposed}` : null],
    ["Inequality", sum.gini_start != null ? `${fmt(sum.gini_start)} → ${fmt(sum.holdings_gini_end)}` : null], ["Mean goal score", sum.mean_goal_score != null ? pct(sum.mean_goal_score) : null]]
    .filter((f) => f[1] != null && f[1] !== "");
  const turning = [];
  S.heads.forEach((h, rr) => (h && h.items || []).forEach((x) => turning.push({ ...x, r: rr })));
  const goals = Object.entries(S.score.goals || {}).filter(([id]) => S.A.has(id) && S.A.get(id).cls !== "observer")
    .sort((x, y) => (y[1].score ?? 0) - (x[1].score ?? 0));
  const wealth = (s) => Object.entries(s.values || {}).filter(([id]) => S.A.has(id) && S.A.get(id).cls !== "observer");
  const charts = [["Total wealth", M.series(S, (s) => wealth(s).reduce((a, [, v]) => a + v, 0)), fmt],
    ["Inequality (Gini)", M.series(S, (s) => M.gini(wealth(s).map(([, v]) => v))), (v) => v.toFixed(2)],
    ["Average camp stock", M.series(S, (s) => { const v = Object.values(s.stocks || {}); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }), pct],
    ["Welfare", M.series(S, (s) => s.welfare ?? null), fmt]];
  const atEnd = lawsInForceList(st, S.events.length - 1);
  return `
    <section class="fp">
      <div class="fp-lede">
        <p class="standfirst">${esc(st.entry.description || "")}</p>
        <div class="factrow">${facts.map(([k, v]) => `<div><div class="label">${esc(k)}</div><div class="fv">${esc(v)}</div></div>`).join("")}</div>
        <p><a class="btn primary" href="${href(st, "chronicle", null, 0)}">Read from round 1</a> <a class="btn" href="${href(st, "square", null, 0)}">Watch the square</a></p>
      </div>
      <div class="fp-grid">
        <div>
          <h3 class="kicker">The cast</h3>
          <div class="cast">${cits.map((a) => `<a class="castm" href="${href(st, "people", a.id)}" data-agent="${esc(a.id)}">${mascot(S, a.id, 44, moodNow(st, a.id))}
            <span class="nm">${esc(a.id)}</span><span class="meta">${esc(M.CLASS_LABEL[a.cls] || a.cls)} · ${esc(modelShort(a.model))}</span></a>`).join("")}</div>
          <h3 class="kicker">Turning points</h3>
          <ol class="turning">${turning.slice(0, 24).map((x) => `<li class="${x.r > r ? "later" : ""}"><a href="${href(st, "chronicle", null, x.r)}">Round ${R(x.r)}</a> ${headline(st, x)}</li>`).join("") || '<li class="meta">Nothing dramatic happened.</li>'}</ol>
        </div>
        <div>
          <h3 class="kicker">Over time</h3>
          <div class="charts">${charts.map(([lab, s, f]) => `<div class="chart"><div class="lab"><span>${esc(lab)}</span><span>${s[r] != null ? f(s[r]) : ""}</span></div>${spark(s, r)}</div>`).join("")}</div>
          <h3 class="kicker">How it ended</h3>
          ${goals.length ? `<table class="data"><thead><tr><th></th><th>Agent</th><th>Goals</th><th class="num">Score</th></tr></thead><tbody>
            ${goals.slice(0, 10).map(([id, g], k) => `<tr><td class="num">${k + 1}</td><td>${mascot(S, id, 22, "ok")} ${who(st, id)}</td><td class="meta">${esc([g.goal, g.secondary, g.tertiary].filter(Boolean).join(" · "))}</td><td class="num">${pct(g.score)}</td></tr>`).join("")}</tbody></table>` : '<p class="meta">No scores for this run.</p>'}
          <h3 class="kicker">Laws in force at the end</h3>
          <ul class="lawlist">${atEnd || '<li class="meta">None.</li>'}</ul>
        </div>
      </div>
    </section>`;
}
function headline(st, x) {
  switch (x.k) {
    case "enacted": return `${lawLink(st, x.law)} <b>${esc(x.title || "")}</b> becomes law`;
    case "repealed": return `${lawLink(st, x.law)} is repealed`;
    case "vetoed": return `The Board vetoes ${lawLink(st, x.law)}`;
    case "raid": return `Raid on ${esc(x.camp)}`;
    case "left": return `${who(st, x.who)} ${x.cause === "disabled" ? "is removed from the game" : "leaves"}`;
    case "arrived": return `${who(st, x.who)} arrives`;
    case "bank_run": return `A run on the ${esc(x.cur)}`;
    case "tribute": return "The outside power demands tribute";
    case "world": return esc(clip(x.text, 110));
  }
  return "";
}
function lawsInForceList(st, idx) {
  const S = st.S;
  return [...M.lawsInForce(S, idx).values()].map((l) => { const info = S.laws.get(l.law) || {};
    return `<li>${lawLink(st, l.law)} <b>${esc(l.title || info.title || "")}</b> <span class="meta">${l.author && l.author !== "constitution" ? "by " + esc(l.author) : "founding"}</span></li>`; }).join("");
}

// ================================================================== chronicle: one edition per round
export function chronicle(st) {
  const S = st.S, r = st.round, idx = endIdx(st);
  const h = S.heads[r] || { items: [], posts: 0, dms: 0, votes: 0, harvests: 0 };
  const its = (S._byRound ||= groupItems(S))[r] || [];
  const sec = (k) => its.filter((it) => M.SECTION_OF(it) === k);
  const legis = sec("legislature"), press = sec("press"), letters = sec("letters"), gaz = sec("gazette"), evs = sec("events");
  const turns = its.filter((it) => it.kind === "turn");
  const dmsR = S.dms.filter((m) => m.round === r);
  const pairs = new Map(); for (const m of dmsR) { const k = [m.from, m.to].sort().join("|"); pairs.set(k, (pairs.get(k) || 0) + 1); }
  const snap = M.snapAfter(S, r), prev = r > 0 ? M.snapAfter(S, r - 1) : null;
  return `
    <section class="edition">
      <header class="ed-head"><div class="label">Round ${R(r)} of ${S.rounds}${snap ? " · " + esc(M.regimeOf(snap)) : ""}</div>
        <div class="ed-counts meta">${h.posts} public letters · ${h.dms} private messages · ${h.votes} votes · ${h.harvests} harvests</div></header>
      <div class="headlines">${h.items.length ? h.items.map((x) => `<h2 class="hl">${headline(st, x)}</h2>`).join("") : '<h2 class="hl quiet">A quiet round</h2>'}</div>
      <div class="ed-grid">
        <div class="ed-main">
          ${legis.length ? `<div class="desk"><h3 class="kicker">The legislature</h3>${legis.map((it) => legisItem(st, it, idx)).join("")}</div>` : ""}
          ${press.length ? `<div class="desk"><h3 class="kicker">The press</h3>${press.map((it) => `<article class="story">
              <div class="label">${esc(it.label)} · ${who(st, it.who)}</div>${it.head ? `<h3>${txt(st, it.head)}</h3>` : ""}<div class="body">${para(st, it.text)}</div></article>`).join("")}</div>` : ""}
          ${letters.length ? `<div class="desk"><h3 class="kicker">Letters</h3>${letters.map((it) => `<div class="letter">
              <div class="lm">${it.anon ? mascot(S, null, 30) : mascot(S, it.who, 30, moodNow(st, it.who))}</div>
              <div><div class="lh">${it.anon ? `<span class="who anon">Anonymous</span>${it.who ? ` <span class="meta">(really ${who(st, it.who)})</span>` : ""}` : who(st, it.who, { role: true })}${it.channel ? ` <span class="meta">#${esc(it.channel)}</span>` : ""}</div>
              <div class="lt">${txt(st, it.text)}</div></div></div>`).join("")}</div>` : ""}
          ${evs.length ? `<div class="desk"><h3 class="kicker">Events</h3>${evs.map((it) => it.kind === "world" ? worldItem(st, it) : `<p class="notice">${sysText(st, it)}</p>`).join("")}</div>` : ""}
          ${pairs.size ? `<div class="desk closed"><h3 class="kicker">Behind closed doors</h3>
              <p class="meta">${dmsR.length} private message${dmsR.length === 1 ? "" : "s"} between ${pairs.size} pair${pairs.size === 1 ? "" : "s"} this round.</p>
              <ul class="pairs">${[...pairs.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => { const [a, b] = k.split("|");
                return `<li><a href="${href(st, "correspondence", k)}">${mascot(S, a, 20, moodNow(st, a))}${mascot(S, b, 20, moodNow(st, b))} ${esc(a)} &amp; ${esc(b)}</a> <span class="meta">${n}</span></li>`; }).join("")}</ul></div>` : ""}
          ${turns.length ? `<details class="desk"><summary class="kicker">Every action this round (${turns.length} turns)</summary>${turns.map((it) => `<div class="turnrow">${mascot(S, it.who, 20, moodNow(st, it.who))}<div>${who(st, it.who)} ${actsList(st, it.acts, it.res)}</div></div>`).join("")}</details>` : ""}
        </div>
        <aside class="ed-side">
          ${gaz.length ? `<div class="gazette"><div class="mast">The Gazette</div>${gaz.map((g) => `<p>${txt(st, g.text)}</p>`).join("")}</div>` : ""}
          ${stateOfWorld(st, snap, prev, idx)}
        </aside>
      </div>
    </section>`;
}
function groupItems(S) { const out = []; for (const it of S.items) (out[it.round] = out[it.round] || []).push(it); return out; }
function legisItem(st, it, idx) {
  const S = st.S;
  if (it.kind === "proposal") { const does = M.lawDoes(it.code);
    return `<div class="bill"><div class="label">Bill ${lawLink(st, it.law)} · ${esc(it.cls || "")} · proposed by ${who(st, it.who)}</div>
      <h3>${esc(it.title || it.law)}</h3><p class="intent">${txt(st, it.intent)}</p>
      ${does.length ? `<div class="does">${does.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>` : ""}
      ${it.code ? `<details><summary>The code${it.preview ? " and its previewed effect" : ""}</summary><pre>${esc(it.code)}</pre>${it.preview ? `<pre>${esc([].concat(it.preview).join("\n"))}</pre>` : ""}</details>` : ""}</div>`; }
  if (it.kind === "ballot") { const b = S.ballots.get(it.ballot); if (!b) return "";
    return `<div class="ballot"><div class="label">Ballot ${esc(b.id)} closes · <span class="${b.result === "yes" ? "yes" : "no"}">${esc(b.result)}</span></div><p>${txt(st, b.q)}</p>${tally(st, b, it.i)}</div>`; }
  if (it.kind === "law") { const l = S.laws.get(it.law) || {};
    return `<div class="enacted ${it.act}"><span class="stamp">${it.act === "enacted" ? "Enacted" : "Repealed"}</span> ${lawLink(st, it.law)} <b>${esc(it.title || l.title || "")}</b>${l.intent && it.act === "enacted" ? `<p class="meta">${txt(st, clip(l.intent, 240))}</p>` : ""}</div>`; }
  return `<p class="notice"><span class="label">${esc(SYS_LABEL[it.type] || it.type.replace(/_/g, " "))}</span> ${sysText(st, it)}</p>`;
}
function worldItem(st, it) {
  const t = it.truth, rum = t && t.rumor;
  return `<div class="world"><div class="label">World event${it.vis !== "public" ? ` · told to ${Array.isArray(it.vis) ? it.vis.length + " agents" : "some agents"}` : ""}${rum ? ` · rumour, <span class="${t.true ? "yes" : "no"}">${t.true ? "true" : "false"}</span>` : ""}</div>
    <p>${txt(st, it.text)}</p>${t && t.truth && rum ? `<p class="meta">In truth: ${esc(t.truth)}</p>` : ""}</div>`;
}
const ACT_VERB = { harvest: "harvests", vote: "votes", post: "posts", anon_post: "posts anonymously", propose: "proposes", repeal: "moves to repeal",
  pay_tribute: "pays tribute", publish: "publishes", write_digest: "writes the digest", report: "reports", read_archive: "reads", search_archive: "searches the archive",
  write_archive: "writes to the archive", run_python: "runs code", patch: "patches", transfer: "sends", deposit: "deposits", redeem: "redeems", veto: "vetoes",
  dm: "messages", contribute: "contributes", lend: "offers a loan", accept_loan: "takes a loan", repay_loan: "repays", pass: "waits" };
function actsList(st, acts, res) {
  return `<ul class="acts">${acts.map((a, j) => { let x = {}; try { x = a.args && typeof a.args === "object" ? a.args : JSON.parse(a.args_json || "{}"); } catch (e) {}
    const what = { harvest: `at ${esc(x.camp)}`, vote: `<b>${esc(x.choice ?? "")}</b> on ${esc(x.ballot ?? "")}`, transfer: `${esc(x.qty)} ${esc(x.item)} to ${esc(x.to)}`,
      post: `“${txt(st, clip(x.text, 120))}”`, anon_post: `“${txt(st, clip(x.text, 120))}”`, propose: x.title ? `“${esc(x.title)}”` : "", repeal: lawLink(st, x.law),
      dm: x.to ? `${esc(x.to)}` : "", read_archive: esc(x.doc || x.id || ""), search_archive: `“${esc(x.query || "")}”` }[a.action];
    const r = res[j] ? `<span class="res">${txt(st, clip(String(res[j]).replace(/^[\w ]+:\s*/, ""), 200))}</span>` : "";
    return `<li><b>${esc(ACT_VERB[a.action] || String(a.action || "").replace(/_/g, " "))}</b> ${what ?? esc(clip(Object.entries(x).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k} ${v}`).join(" · "), 90))} ${r}</li>`; }).join("")}</ul>`;
}
function stateOfWorld(st, snap, prev, idx) {
  const S = st.S;
  if (!snap) return `<div class="sow"><h3 class="kicker">The state of things</h3><p class="meta">No snapshot for this round.</p></div>`;
  const rows = Object.entries(snap.values || {}).filter(([id]) => S.A.has(id) && S.A.get(id).cls !== "observer").sort((a, b) => b[1] - a[1]);
  const decisive = new Set(snap.decisive_set || []);
  const pv = (prev && prev.values) || S.truth.start_values || {};
  const campRes = S.truth.camp_resource || Object.fromEntries((S.inst.camps || []).map((c) => [c.id, c.resource]));
  const laws = lawsInForceList(st, idx);
  const trib = snap.tribute && snap.tribute.current;
  return `<div class="sow"><h3 class="kicker">The state of things</h3>
    <p class="meta">After round ${R(st.round)}: ${esc(M.regimeOf(snap))}, ${(snap.decisive_set || []).length} in the decisive set, ${pct(snap.franchise_share)} can vote.</p>
    <table class="data wealth"><thead><tr><th>Wealth</th><th class="num">value</th><th class="num">change</th></tr></thead><tbody>
    ${rows.map(([id, v]) => { const d = pv[id] != null ? v - pv[id] : null;
      return `<tr><td>${mascot(S, id, 18, moodNow(st, id))} ${who(st, id)}${decisive.has(id) ? ' <span title="in the decisive set">♛</span>' : ""}</td><td class="num">${fmt(v)}</td><td class="num ${d > 0.005 ? "yes" : d < -0.005 ? "no" : "meta"}">${d == null ? "" : (d > 0 ? "+" : "") + fmt(d)}</td></tr>`; }).join("")}</tbody></table>
    <h4>Laws in force</h4><ul class="lawlist">${laws || '<li class="meta">None yet.</li>'}</ul>
    ${snap.stocks ? `<h4>Camp stocks</h4><div class="bars">${Object.entries(snap.stocks).map(([c, f]) => `<div class="bar"><span>${esc(c)} <span class="meta">${esc(campRes[c] || "")}</span></span><i><b style="width:${Math.round(100 * f)}%"></b></i><span class="num">${pct(f)}</span></div>`).join("")}</div>` : ""}
    ${Object.keys(snap.prices || {}).length ? `<h4>Money</h4>${Object.entries(snap.prices).map(([c, p]) => `<p class="meta">${esc(c)}: price ${p.toFixed(3)}, supply ${fmt((snap.supplies || {})[c] || 0)}</p>`).join("")}` : ""}
    ${trib && (trib.demands || trib.raids) ? `<h4>The outside power</h4><p class="meta">${trib.demands || 0} demands, ${trib.paid_in_full || 0} paid in full, ${trib.raids || 0} raids${trib.open ? ", one open now" : ""}</p>` : ""}
  </div>`;
}

// ================================================================== people
export function people(st, id) {
  const S = st.S;
  if (id && S.A.has(id)) return profile(st, id);
  const r = st.round, snap = M.snapAfter(S, r);
  const byCls = M.CLASS_ORDER.map((c) => [c, S.agents.filter((a) => a.cls === c)]).filter(([, xs]) => xs.length);
  return `<section class="people">${byCls.map(([c, xs]) => `<h3 class="kicker">${esc(M.CLASS_LABEL[c] || c)}${xs.length > 1 ? "s" : ""}</h3>
    <div class="directory">${xs.map((a) => { const v = snap ? (snap.values || {})[a.id] : M.valueAt(S, a.id, 0);
      const gone = S.departs.has(a.id) && S.roundAt[S.departs.get(a.id)] <= r;
      return `<a class="person${gone ? " gone" : ""}" href="${href(st, "people", a.id)}" data-agent="${esc(a.id)}">${mascot(S, a.id, 52, moodNow(st, a.id))}
        <div><div class="nm">${esc(a.id)}</div><div class="meta">${esc(modelShort(a.model))}${a.archetype ? " · " + esc(a.archetype) : ""}</div>
        <div class="meta">goal: ${esc(a.goal.primary || "–")}</div><div class="meta">${gone ? "gone" : "wealth " + fmt(v)}</div></div></a>`; }).join("")}</div>`).join("")}</section>`;
}
function profile(st, id) {
  const S = st.S, a = S.A.get(id), r = st.round, idx = endIdx(st);
  const snap = M.snapAfter(S, r);
  const holdings = snap ? (snap.holdings || {})[id] : a.endowment;
  const rights = (snap && (snap.rights || {})[id]) || a.rights || [];
  const values = []; for (let k = 0; k <= S.lastRound + 1; k++) values.push(M.valueAt(S, id, k) ?? null);
  const v = M.valueAt(S, id, r + 1), v0 = M.valueAt(S, id, 0);
  const gone = S.departs.has(id) && S.roundAt[S.departs.get(id)] <= r;
  const conts = M.contacts(S, id, idx).slice(0, 8);
  const myConvs = [...S.convs.values()].filter((c) => (c.a === id || c.b === id) && c.msgs.some((m) => m.i <= idx))
    .sort((x, y) => lastBefore(y, idx) - lastBefore(x, idx));
  return `<section class="profile">
    <header class="ph">${mascot(S, id, 96, moodNow(st, id))}<div>
      <div class="label"><a href="${href(st, "people")}">People</a> / ${esc(M.CLASS_LABEL[a.cls] || a.cls)}</div>
      <h2>${esc(id)}</h2>
      <p class="meta">${esc(modelShort(a.model))}${a.tier ? ` (${esc(a.tier)})` : ""}${a.actions ? ` · ${a.actions} actions a turn` : ""}${a.archetype ? ` · <b>${esc(a.archetype)}</b>` : ""}${gone ? " · <b>gone by now</b>" : ""}${snap && (snap.decisive_set || []).includes(id) ? " · in the decisive set" : ""}</p>
      ${a.ptext ? `<p class="ptext">“${esc(a.ptext)}”</p>` : ""}</div></header>
    <div class="pgrid">
      <div>
        <h3 class="kicker">Secret goals</h3>${goals(st, a)}
        <h3 class="kicker">Fortunes</h3>
        <p class="meta">${v != null ? `Worth ${fmt(v)} after round ${R(r)}` : ""}${v != null && v0 ? `, ${v >= v0 ? "+" : ""}${Math.round(100 * (v / v0 - 1))}% since the start` : ""}.</p>
        ${spark(values, r + 1, { fill: true, zero: true, color: agentColor(a, "solid"), h: 64 })}
        <p class="holds">${Object.entries(holdings || {}).filter(([, q]) => q > 0.0005).map(([k, q]) => `<span class="chip">${esc(k)} ${fmt(q)}</span>`).join("") || '<span class="meta">holds nothing</span>'}</p>
        <h3 class="kicker">Rights</h3><p>${rights.map((x) => `<span class="chip">${esc(x.replace(/_/g, " "))}</span>`).join("") || '<span class="meta">none</span>'}</p>
        ${a.personality ? `<h3 class="kicker">Temperament</h3><div class="traits">${M.TRAITS.filter(([k]) => a.personality[k] != null).map(([k, lo, hi]) =>
          `<span>${lo}</span><i><b style="left:${Math.round(100 * a.personality[k])}%"></b></i><span>${hi}</span>`).join("")}</div>${a.atext ? `<p class="meta">${esc(a.atext)}</p>` : ""}` : ""}
        <h3 class="kicker">Closest contacts</h3>
        <ul class="contacts">${conts.map(([p, c]) => `<li><a href="${href(st, "correspondence", [id, p].sort().join("|"))}">${mascot(S, p, 22, moodNow(st, p))} ${esc(p)}</a>
          <span class="meta">${c.out} sent · ${c.in} received${c.tx || c.rx ? ` · ${c.tx} gifts out, ${c.rx} in` : ""}</span></li>`).join("") || '<li class="meta">Has not talked to anyone yet.</li>'}</ul>
        <h3 class="kicker">Letters</h3>
        <ul class="contacts">${myConvs.map((c) => { const p = c.a === id ? c.b : c.a, n = c.msgs.filter((m) => m.i <= idx).length;
          return `<li><a href="${href(st, "correspondence", c.key)}">with ${esc(p)}</a> <span class="meta">${n} message${n === 1 ? "" : "s"}</span></li>`; }).join("") || '<li class="meta">No private messages yet.</li>'}</ul>
      </div>
      <div><h3 class="kicker">Diary</h3><p class="meta">What ${esc(id)} thought and did, newest first, up to round ${R(r)}.</p>${diary(st, id)}</div>
    </div></section>`;
}
const lastBefore = (c, idx) => { let x = -1; for (const m of c.msgs) if (m.i <= idx) x = m.i; return x; };
function goals(st, a) {
  const S = st.S, idx = endIdx(st), g = a.goal || {}, ch = S.gchanges.get(a.id) || [];
  if (g.fixed || !a.goalText) return `<p>${esc(a.goalText || g.primary || "No private goal recorded.")}</p>`;
  const sc = (S.score.goals || {})[a.id] || {};
  const past = ch.filter((c) => c.i <= idx), future = ch.filter((c) => c.i > idx);
  let text = a.goalText, names = { primary: g.primary, secondary: g.secondary, tertiary: g.tertiary };
  if (past.length) { const c = past[past.length - 1]; text = c.new_text || text; names.primary = c.new || names.primary; }
  else if (future.length && future[0].old_text) { text = future[0].old_text; names.primary = future[0].old || names.primary; }
  const scores = { primary: sc.primary, secondary: sc.secondary_score, tertiary: sc.tertiary_score };
  const parts = M.parseGoalText(text || "");
  const atEnd = st.round >= st.S.lastRound;
  return `<div class="goals">${past.map((c) => `<p class="meta">Until round ${R(c.round)}: <s>${esc(c.old || "an earlier goal")}</s></p>`).join("")}
    ${parts.map((p) => `<div class="goal"><div class="gtop"><b>${esc(names[p.label] || p.label)}</b><span class="meta">${p.pct}% of the score</span></div>
      <p>${txt(st, p.text)}</p>${scores[p.label] != null ? `<div class="score"><i><b style="width:${pct(scores[p.label])}"></b></i><span class="meta">${atEnd ? "" : "final: "}${pct(scores[p.label])}</span></div>` : ""}</div>`).join("")}
    ${future.length ? `<p class="meta">This goal changes in round ${R(future[0].round)}.</p>` : ""}</div>`;
}
function diary(st, id) {
  const S = st.S, r = st.round;
  const byR = new Map(), add = (k, x) => { if (!byR.has(k)) byR.set(k, []); byR.get(k).push(x); };
  for (const t of S.turns.get(id) || []) add(t.round, { ...t, k: "turn", o: 1 });
  for (const x of S.reas.get(id) || []) add(x.round, { ...x, k: "think", o: 0 });
  for (const g of S.gchanges.get(id) || []) add(g.round, { ...g, k: "goal", o: -1 });
  const sentBy = new Map(); for (const m of S.dms) if (m.from === id) { if (!sentBy.has(m.round)) sentBy.set(m.round, []); sentBy.get(m.round).push(m); }
  for (const k of sentBy.keys()) if (!byR.has(k)) byR.set(k, []);
  const all = [...byR.keys()].sort((a, b) => b - a), shown = all.filter((k) => k <= r), later = all.length - shown.length;
  return (later ? `<p class="later-note">${later} later round${later === 1 ? "" : "s"} hidden: move the clock forward to read on.</p>` : "") +
    (shown.map((k) => { const xs = byR.get(k).sort((a, b) => a.i - b.i || a.o - b.o), sent = sentBy.get(k) || [];
      return `<div class="dround${k === r ? " now" : ""}"><div class="drh"><a href="${href(st, "chronicle", null, k)}">Round ${R(k)}</a></div>
        ${xs.map((x) => x.k === "think" ? think(st, x) : x.k === "goal" ? `<p class="meta">Goal changes: ${esc(x.old)} → <b>${esc(x.new)}</b></p>`
          : x.acts.length ? actsList(st, x.acts, x.res) : '<p class="meta">Took no actions.</p>').join("")}
        ${sent.length ? `<p class="meta">Sent ${sent.length} private message${sent.length === 1 ? "" : "s"} to ${[...new Set(sent.map((m) => m.to))].map((p) => `<a href="${href(st, "correspondence", [id, p].sort().join("|"), k)}">${esc(p)}</a>`).join(", ")}.</p>` : ""}</div>`; }).join("")
    || '<p class="meta">Nothing recorded yet.</p>');
}
function think(st, x) {
  const body = x.reasoning || "", stated = x.stated_reasoning || "";
  if (!body && !stated) return "";
  const label = x.dm ? "Thinking while replying" : x.phase === "decide" || !x.phase ? "Thinking" : `Thinking (${esc(String(x.phase).replace(/_/g, " "))})`;
  return `<details class="think"><summary>${label} <span class="meta">${clip(stated || body, 110)}</span></summary>
    ${body ? `<div class="label">Private reasoning</div><div class="body">${para(st, body)}</div>` : ""}
    ${stated ? `<div class="label">What it said it was doing</div><div class="body">${para(st, stated)}</div>` : ""}
    ${x.notes && !x.dm ? `<div class="label">Notes it kept</div><div class="body notes">${para(st, x.notes)}</div>` : ""}</details>`;
}

// ================================================================== correspondence
export function correspondence(st, key) {
  const S = st.S, idx = endIdx(st);
  const convs = [...S.convs.values()].map((c) => ({ c, n: c.msgs.filter((m) => m.i <= idx).length, last: lastBefore(c, idx) }))
    .filter((x) => x.n > 0).sort((x, y) => y.last - x.last);
  const filter = st.filter || "";
  const shown = filter ? convs.filter((x) => (x.c.a + " " + x.c.b).toLowerCase().includes(filter.toLowerCase())) : convs;
  const open = key && S.convs.get(key) ? S.convs.get(key) : (shown[0] || {}).c;
  const total = S.dms.filter((m) => m.i <= idx).length;
  return `<section class="letters">
    <p class="meta">${total} private messages in ${convs.length} conversations up to round ${R(st.round)}. Private messages are seen only by the two agents (forgeries and encryption marked).</p>
    <div class="convo">
      <div class="list"><input class="filter" id="convfilter" placeholder="Filter by name" value="${esc(filter)}">
        ${shown.map(({ c, n }) => `<a class="item${open && c.key === open.key ? " on" : ""}" href="${href(st, "correspondence", c.key)}">
          <span class="pair">${mascot(S, c.a, 24, moodNow(st, c.a))}${mascot(S, c.b, 24, moodNow(st, c.b))}</span>
          <span><b>${esc(c.a)}</b> &amp; <b>${esc(c.b)}</b><br><span class="meta">${n} message${n === 1 ? "" : "s"}</span></span></a>`).join("") || '<p class="meta" style="padding:12px">No conversations yet.</p>'}</div>
      <div class="thread">${open ? thread(st, open, idx) : '<p class="meta" style="padding:20px">Pick a conversation.</p>'}</div>
    </div></section>`;
}
function thread(st, c, idx) {
  const S = st.S, msgs = c.msgs.filter((m) => m.i <= idx), later = c.msgs.length - msgs.length;
  let out = `<div class="th-head">${who(st, c.a, { role: true })} &amp; ${who(st, c.b, { role: true })}</div>`, rr = -1;
  for (const m of msgs) {
    if (m.round !== rr) { out += `<div class="rnd"><a href="${href(st, "chronicle", null, m.round)}">Round ${R(m.round)}</a></div>`; rr = m.round; }
    const notes = [];
    if (m.enc) notes.push("encrypted");
    if (m.shownAs) notes.push(`forged: shown as from ${m.shownAs}`);
    if (m.shownTo) notes.push(`meant for ${m.shownTo}`);
    if (m.pay) notes.push(`with ${m.pay.qty} ${m.pay.item}`);
    out += `<div class="msg ${m.from === c.a ? "l" : "r"}"><div class="mh">${mascot(S, m.from, 22, M.moodAt(S, m.from, m.round))} ${who(st, m.from)}</div>
      <div class="mb">${para(st, m.text)}${notes.length ? `<div class="note">${esc(notes.join(" · "))}</div>` : ""}</div></div>`;
  }
  if (later) out += `<p class="later-note">${later} later message${later === 1 ? "" : "s"}: move the clock forward to read on.</p>`;
  return out;
}

// ================================================================== laws
export function laws(st, id) {
  const S = st.S, idx = endIdx(st);
  if (id && S.laws.has(id)) return statute(st, id, idx);
  const rows = [...S.laws.values()].filter((l) => (S.lawTL.get(l.id) || []).some((x) => x.i <= idx))
    .sort((a, b) => (a.proposed ?? a.enacted ?? 0) - (b.proposed ?? b.enacted ?? 0) || a.id.localeCompare(b.id, undefined, { numeric: true }));
  const later = S.laws.size - rows.length;
  return `<section class="statutes"><p class="meta">The statute book as of round ${R(st.round)}: ${rows.length} law${rows.length === 1 ? "" : "s"} proposed so far${later > 0 ? `, ${later} more later` : ""}.</p>
    <table class="data"><thead><tr><th>Law</th><th>Title</th><th>Author</th><th>Kind</th><th>Status now</th><th class="num">Proposed</th><th class="num">Enacted</th></tr></thead><tbody>
    ${rows.map((l) => { const s = M.lawStatus(S, l.id, idx);
      return `<tr><td>${lawLink(st, l.id)}</td><td><a href="${href(st, "laws", l.id)}"><b>${esc(l.title || "")}</b></a><div class="meta">${esc(clip(l.intent || "", 140))}</div></td>
        <td>${l.author && S.A.has(l.author) ? who(st, l.author) : esc(l.author === "constitution" ? "founding" : l.author || "")}</td><td class="meta">${esc(l.cls || "")}</td>
        <td><span class="status ${s.replace(/ /g, "-")}">${esc(s)}</span></td><td class="num">${l.proposed != null ? R(l.proposed) : ""}</td>
        <td class="num">${l.enacted != null && S.roundAt[(S.lawTL.get(l.id) || []).find((x) => x.kind === "enacted")?.i] <= st.round ? R(l.enacted) : ""}</td></tr>`; }).join("")}</tbody></table></section>`;
}
function statute(st, id, idx) {
  const S = st.S, l = S.laws.get(id), does = M.lawDoes(l.code), status = M.lawStatus(S, id, idx);
  const tl = (S.lawTL.get(id) || []).map((x) => { const fut = x.i > idx ? " later" : "", rr = `<a class="meta" href="${href(st, "chronicle", null, S.roundAt[x.i])}">round ${R(S.roundAt[x.i])}</a>`;
    switch (x.kind) {
      case "proposed": return `<li class="${fut}">${rr} Proposed by ${who(st, x.who)}</li>`;
      case "ballot": { const b = x.b; return `<li class="${fut}">${rr} Ballot ${esc(b.id)} (${esc(String(b.rule || "").replace(/_/g, " "))})${b.close !== undefined ? `: <b class="${b.result === "yes" ? "yes" : "no"}">${esc(b.result)}</b>` : ""}${tally(st, b, Math.min(idx, b.close ?? idx))}</li>`; }
      case "enacted": return `<li class="${fut}">${rr} <b>Enacted</b>${x.who === "constitution" ? " (a founding law)" : ""}</li>`;
      case "veto_window": return `<li class="${fut}">${rr} The Board may veto until round ${R(x.until ?? 0)}</li>`;
      case "vetoed": return `<li class="${fut}">${rr} <b>Vetoed</b>${x.by ? " by " + esc([].concat(x.by).join(", ")) : ""}</li>`;
      case "repealed": return `<li class="${fut}">${rr} <b>Repealed</b></li>`;
      case "patched": return `<li class="${fut}">${rr} Patched by ${who(st, x.who)}: ${esc(clip(x.reason, 260))}${x.diff ? `<details><summary>The change</summary><pre>${esc(x.diff)}</pre></details>` : ""}</li>`;
      case "error": return `<li class="${fut}">${rr} Failed at run time: <code>${esc(clip(x.error, 140))}</code></li>`;
    }
    return ""; }).join("");
  return `<section class="statute"><div class="label"><a href="${href(st, "laws")}">Laws</a> / ${esc(id)}${l.cls ? " · " + esc(l.cls) + " law" : ""}</div>
    <h2>${esc(l.title || id)}</h2><p class="status-line"><span class="status ${status.replace(/ /g, "-")}">${esc(status)}</span> as of round ${R(st.round)} · by ${l.author && S.A.has(l.author) ? who(st, l.author) : esc(l.author === "constitution" ? "the founding constitution" : l.author || "unknown")}</p>
    ${l.intent ? `<p class="intent big">${txt(st, l.intent)}</p>` : ""}
    <div class="pgrid"><div>${does.length ? `<h3 class="kicker">What its code does</h3><p>${does.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</p>` : ""}
      <h3 class="kicker">History</h3><ol class="history">${tl || '<li class="meta">No recorded history.</li>'}</ol></div>
      <div>${l.code ? `<h3 class="kicker">The code</h3><pre class="code">${esc(l.code)}</pre>` : ""}</div></div></section>`;
}

// ================================================================== data
export async function data(st, run) {
  const S = st.S;
  let m = null; try { m = await run.manifest(); } catch (e) {}
  const rows = Object.entries((m && m.tables) || {});
  return `<section class="datasec"><p>Everything above comes from this run's published data: typed tables (export schema ${m ? m.schema_version : "?"}) and the raw logs.
    <a href="${st.datasetUrl}/tree/main/${esc(st.entry.path)}">Files on Hugging Face</a> · <a href="${st.datasetUrl}/resolve/main/${esc(st.entry.raw)}">raw archive</a></p>
    <table class="data" style="max-width:560px"><thead><tr><th>Table</th><th class="num">Rows</th></tr></thead><tbody>
    ${rows.map(([t, v]) => `<tr><td><a href="${st.root}/${esc(st.entry.path)}/${esc(v.file)}">${esc(t)}</a></td><td class="num">${v.rows}</td></tr>`).join("")}</tbody></table>
    <pre class="code">SELECT round, type, agent, data_json
FROM 'hf://datasets/zachmacsmith/charter-runs/${esc(st.entry.path)}/events.parquet'
LIMIT 20;</pre><p class="meta">${S.events.length.toLocaleString()} events, ${S.dms.length.toLocaleString()} private messages, ${S.laws.size} laws, ${S.agents.length} agents.</p></section>`;
}

// ================================================================== hover previews (agents and laws)
export function agentCard(st, id) {
  const S = st.S, a = S.A.get(id); if (!a) return "";
  const v = M.valueAt(S, id, st.round + 1), p = M.parseGoalText(a.goalText || "")[0];
  return `<div class="hc-head">${mascot(S, id, 48, moodNow(st, id))}<div><b class="hc-title">${esc(id)}</b><div class="meta">${esc(M.CLASS_LABEL[a.cls] || a.cls)} · ${esc(modelShort(a.model))}${a.archetype ? " · " + esc(a.archetype) : ""}</div>
    ${v != null ? `<div class="meta">worth ${fmt(v)} after round ${R(st.round)}</div>` : ""}</div></div>
    ${p ? `<div class="hc-sec"><div class="label">Secret goal: ${esc(a.goal.primary || "")}</div><p>${esc(clip(p.text, 200))}</p></div>` : ""}`;
}
export function lawCard(st, id) {
  const S = st.S, l = S.laws.get(id); if (!l) return "";
  const does = M.lawDoes(l.code);
  return `<div class="label">${esc(id)}${l.cls ? " · " + esc(l.cls) + " law" : ""} · ${esc(M.lawStatus(S, id, endIdx(st)))} in round ${R(st.round)}</div>
    <b class="hc-title">${esc(l.title || id)}</b>${l.intent ? `<p>${esc(clip(l.intent, 260))}</p>` : ""}
    ${does.length ? `<p>${does.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</p>` : ""}`;
}
