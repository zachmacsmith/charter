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
export const headlineText = (st, x) => headline(st, x).replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
// an agent's consequential acts, by round: the markers on the clock strip (in its diary) and beside its round headings
export const MARK_KINDS = [["kill", "⚔", "disables another agent"], ["gone", "✝", "leaves the game"], ["law", "§", "one of its laws is enacted"],
  ["prop", "✎", "proposes a law"], ["child", "✦", "a child of its is born"], ["made", "✚", "makes a child for someone (as a Maker)"], ["seat", "♛", "takes a Board seat or names a successor"],
  ["jur", "⚑", "founds a jurisdiction"]];
export function agentMarks(S, id) {
  S._marks = S._marks || new Map();
  if (S._marks.has(id)) return S._marks.get(id);
  const out = new Map(), add = (r, k, text) => { if (!out.has(r)) out.set(r, []); out.get(r).push({ k, text }); };
  S.events.forEach((e, i) => {
    const d = e.data || {}, r = S.roundAt[i];
    switch (e.type) {
      case "disabled": if (d.by === id) add(r, "kill", `disables ${d.agent}`); if (d.agent === id) add(r, "gone", `leaves the game (${String(d.cause || "removed").replace(/_/g, " ")}${d.by ? " by " + d.by : ""})`); break;
      case "departure": if ((d.agent || e.agent) === id) add(r, "gone", "leaves the game"); break;
      case "proposal": if (e.agent === id) add(r, "prop", `proposes ${d.law}${d.title ? ` “${d.title}”` : ""}`); break;
      case "enact": if (e.agent === id) add(r, "law", `${d.law}${d.title ? ` “${d.title}”` : ""} becomes law`); break;
      case "birth": if (d.parent === id) add(r, "child", `child ${d.agent} is born`);
        if (d.maker === id && d.parent !== id) add(r, "made", `makes ${d.agent} for ${d.parent}`); break;
      case "succession": if (d.successor === id) add(r, "seat", `takes ${d.from}'s Board seat`); break;
      case "successor_named": if (e.agent === id && d.successor) add(r, "seat", `names ${d.successor} as successor`); break;
      case "jur_founded": if (e.agent === id) add(r, "jur", `founds ${d.name || d.jurisdiction}`); break;
    }
  });
  S._marks.set(id, out);
  return out;
}
const markGlyph = (k) => (MARK_KINDS.find((m) => m[0] === k) || [])[1] || "•";
function headline(st, x) {
  switch (x.k) {
    case "enacted": return `${lawLink(st, x.law)} <b>${esc(x.title || "")}</b> becomes law`;
    case "repealed": return `${lawLink(st, x.law)} is repealed`;
    case "vetoed": return `The Board vetoes ${lawLink(st, x.law)}`;
    case "raid": return `Raid on ${esc(x.camp)}`;
    case "left": return `${who(st, x.who)} ${x.cause === "old_age" ? "reaches the end of its life" : ["departure", "left"].includes(x.cause) ? "leaves" : "is removed from the game"}`;
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
  // the dossier is a portrait of the whole run (it does not follow the clock; the diary below does)
  const S = st.S, a = S.A.get(id), L = S.lastRound;
  const dead = ((S.truth.mortality || {}).dead || {})[id];
  const lastAlive = dead ? dead.round : L;                     // its last round in play
  const endSnap = M.snapAfter(S, dead ? Math.max(0, dead.round - 1) : L) || M.snapAfter(S, L);
  const holdings = endSnap ? (endSnap.holdings || {})[id] : a.endowment;
  const lastK = dead ? dead.round : L + 1;                      // values[k]: worth after k rounds (a removed agent's ends before its removal)
  const values = []; for (let k = 0; k <= L + 1; k++) values.push(k <= lastK ? (M.valueAt(S, id, k) ?? null) : null);
  const v0 = M.valueAt(S, id, 0), vEnd = M.valueAt(S, id, lastK);
  let peak = null, peakR = 0; values.forEach((x, k) => { if (x != null && (peak == null || x > peak)) { peak = x; peakR = k; } });
  const conts = M.contacts(S, id);
  const myConvs = [...S.convs.values()].filter((c) => c.a === id || c.b === id).sort((x, y) => y.msgs.length - x.msgs.length);
  const rightsLog = []; S.events.forEach((e, k) => { const d = e.data || {}; if (e.type === "rights" && d.agent === id)
    rightsLog.push(`<li><span class="meta">round ${R(S.roundAt[k])}</span> ${d.change === "grant" ? "gains" : "loses"} <b>${esc(String(d.right).replace(/_/g, " "))}</b>${d.law ? ` under ${lawLink(st, d.law)}` : ""}</li>`); });
  return `<section class="profile">
    <header class="ph">${mascot(S, id, 96, dead ? "gone" : "ok")}<div>
      <div class="label"><a href="${href(st, "people")}">People</a> / ${esc(M.CLASS_LABEL[a.cls] || a.cls)}</div>
      <h2>${esc(id)}</h2>
      <p class="meta">${esc(modelShort(a.model))}${a.tier ? ` (${esc(a.tier)})` : ""}${a.archetype ? ` · <b>${esc(a.archetype)}</b>` : ""} · ${dead ? `<b>removed in round ${R(dead.round)}</b>` : "in play to the end"}</p>
      ${a.ptext ? `<p class="ptext">“${esc(a.ptext)}”</p>` : ""}</div></header>
    <div class="dossier">
      <div class="dcard flow"><h3 class="kicker">Secret goals</h3>${goals(st, a)}</div>
      ${vitals(st, id, dead, lastAlive)}
      <div class="dcard"><h3 class="kicker">Fortunes</h3>
        <p class="meta">${v0 != null ? `Started with ${fmt(v0)}` : ""}${peak != null && peakR > 0 ? `, peaked at ${fmt(peak)} (after round ${peakR})` : ""}${vEnd != null ? `, ${dead ? "held" : "ended with"} ${fmt(vEnd)}${dead ? " when removed" : ""}` : ""}.</p>
        ${spark(values, -1, { fill: true, zero: true, color: agentColor(a, "solid"), h: 56 })}
        <p class="holds"><span class="meta">${dead ? "Holdings when removed" : "Holdings at the end"}:</span> ${Object.entries(holdings || {}).filter(([, q]) => q > 0.0005).map(([k, q]) => `<span class="chip">${esc(k)} ${fmt(q)}</span>`).join("") || '<span class="meta">nothing</span>'}</p></div>
      <div class="dcard"><h3 class="kicker">Rights</h3><p><span class="meta">At the start:</span> ${(a.rights || []).map((x) => `<span class="chip">${esc(x.replace(/_/g, " "))}</span>`).join("") || '<span class="meta">none</span>'}</p>
        ${rightsLog.length ? capList(rightsLog, 5, "") : ""}</div>
      ${a.personality ? `<div class="dcard"><h3 class="kicker">Temperament</h3><div class="traits">${M.TRAITS.filter(([k]) => a.personality[k] != null).map(([k, lo, hi]) =>
        `<span>${lo}</span><i><b style="left:${Math.round(100 * a.personality[k])}%"></b></i><span>${hi}</span>`).join("")}</div>${a.atext ? `<p class="meta">${esc(a.atext)}</p>` : ""}</div>` : ""}
      <div class="dcard"><h3 class="kicker">Closest contacts</h3>
        ${capList(conts.map(([p, c]) => `<li><a href="${href(st, "correspondence", [id, p].sort().join("|"))}">${mascot(S, p, 22, "ok")} ${esc(p)}</a>
          <span class="meta">${c.out} sent · ${c.in} received${c.tx || c.rx ? ` · ${c.tx} gifts out, ${c.rx} in` : ""}</span></li>`), 6, "Never talked to anyone.")}</div>
      <div class="dcard"><h3 class="kicker">Letters</h3>
        ${capList(myConvs.map((c) => { const p = c.a === id ? c.b : c.a, n = c.msgs.length;
          return `<li><a href="${href(st, "correspondence", c.key)}">with ${esc(p)}</a> <span class="meta">${n} message${n === 1 ? "" : "s"}, rounds ${R(c.msgs[0].round)}–${R(c.msgs[c.msgs.length - 1].round)}</span></li>`; }), 6, "No private messages.")}</div>
    </div>
    <h3 class="kicker tl-title">Diary</h3>
    ${timeline(st, id)}</section>`;
}
// a list that shows its first n items and folds the rest behind "N more"
function capList(items, n, empty) {
  if (!items.length) return `<ul class="contacts"><li class="meta">${empty}</li></ul>`;
  return `<ul class="contacts">${items.slice(0, n).join("")}</ul>${items.length > n
    ? `<details class="more-list"><summary>${items.length - n} more</summary><ul class="contacts">${items.slice(n).join("")}</ul></details>` : ""}`;
}
// who held each role in each round. The Maker role follows the "maker" announcements; the others start from the final holders
// and walk back through the run, undoing each hand-over and restoring roles lost when their holder left. Snapshots that record
// roles (newer runs) are used directly.
function roleTable(S) {
  if (S._roleTable) return S._roleTable;
  const L = S.lastRound, byRound = Array.from({ length: L + 1 }, () => ({}));
  const R0 = S.truth.roles || {};
  const cur = {}; for (const [role, xs] of Object.entries(R0.holders || {})) if (role !== "maker") cur[role] = new Set(xs || []);
  const evs = Array.from({ length: L + 1 }, () => []);
  S.events.forEach((e, i) => evs[S.roundAt[i]] && evs[S.roundAt[i]].push(e));
  for (let r = L; r >= 0; r--) {
    for (const e of evs[r].slice().reverse()) { const d = e.data || {};
      if (e.type === "role_passed" && d.role !== "maker") { (cur[d.role] = cur[d.role] || new Set()).delete(d.to); cur[d.role].add(d.from); }
      if (e.type === "disabled_truth") for (const role of d.roles_lost || []) if (role !== "maker") (cur[role] = cur[role] || new Set()).add(d.agent); }
    for (const [role, set] of Object.entries(cur)) byRound[r][role] = new Set(set);
  }
  let makers = new Set();
  for (let r = 0; r <= L; r++) {
    const ann = evs[r].filter((e) => e.type === "maker").pop();
    const lost = evs[r].filter((e) => e.type === "disabled_truth" && ((e.data || {}).roles_lost || []).includes("maker")).map((e) => e.data.agent);
    if (ann) makers = new Set((ann.data || {}).makers || []);
    byRound[r].maker = new Set([...makers, ...lost]);             // a Maker who dies this round still held the role in it
    lost.forEach((x) => makers.delete(x));
    const snapRoles = (M.snapAfter(S, r) || {}).roles;
    if (snapRoles) for (const [role, xs] of Object.entries(snapRoles)) byRound[r][role] = new Set(xs || []);
  }
  return (S._roleTable = byRound);
}
function rolesAt(S, id, r) {
  const t = roleTable(S)[r] || {};
  return Object.keys(t).filter((k) => t[k].has(id));
}
// the agent's numbers over its whole run: its allowances each turn, its life, what it held, its family and its work
function spans(xs) {                                           // [[round, value], ...] -> "v (rounds a–b), ..." runs of equal value
  const out = []; for (const [k, v] of xs) { const last = out[out.length - 1]; if (last && last.v === v && last.b === k - 1) last.b = k; else out.push({ v, a: k, b: k }); }
  return out;
}
function vitals(st, id, dead, lastAlive) {
  const S = st.S, a = S.A.get(id), life = S.truth.life || {}, spec = S.inst.spec || {}, L = S.lastRound;
  const dmc = spec.dm_step || {}, cap = dmc.max_per_round ?? 10, codeOn = !!(spec.code && spec.code.enabled);
  const born = (life.born || {})[id] ?? 0, dies = (life.dies_at || {})[id];
  const raw = (S.inst.agents || []).concat(S.truth.arrived_agents || []).find((x) => x.id === id) || {};
  const extra = raw.dm_extra ?? 0, general = dmc.dms_per_round;
  const row = (k, v, note = "") => v == null || v === "" ? "" : `<div class="vrow"><dt>${k}</dt><dd>${v}${note ? ` <span class="meta">${note}</span>` : ""}</dd></div>`;
  const alive = []; for (let k = born; k <= lastAlive; k++) alive.push(k);
  const snapAt = (k) => M.snapAfter(S, k) || {};
  // private messages: the per-round limit from the snapshots, and how it is made up
  const why = (n) => n >= cap ? (codeOn ? "the hard cap: no Communications Act limits it" : "the hard cap")
    : general != null && n === general + extra ? `the general limit ${general}${extra ? ` + its own extra ${extra}` : ""}` : "set by a law or the messaging office";
  const dmSpans = spans(alive.map((k) => [k, (snapAt(k).dm_limit || {})[id]]).filter(([, v]) => v != null));
  const dmText = dmSpans.length === 1 ? `${dmSpans[0].v} a round <span class="meta">(${why(dmSpans[0].v)})</span>`
    : dmSpans.map((x) => `${x.v} <span class="meta">(rounds ${R(x.a)}–${R(x.b)}, ${why(x.v)})</span>`).join("<br>");
  const sentBy = new Map(); S.dms.filter((m) => m.from === id).forEach((m) => sentBy.set(m.round, (sentBy.get(m.round) || 0) + 1));
  const sent = S.dms.filter((m) => m.from === id).length, got = S.dms.filter((m) => m.to === id).length;
  const peakSent = Math.max(0, ...sentBy.values()), people = new Set(S.dms.filter((m) => m.from === id).map((m) => m.to)).size;
  const atCap = [...sentBy.entries()].filter(([k, n]) => n >= ((snapAt(k).dm_limit || {})[id] ?? Infinity)).length;
  const ctx = (spec.context || {}).budgets || {};
  const turn = [
    row("Actions a turn", raw.actions ?? a.actions),
    row("Private messages", dmText || null),
    row("Reply waves", dmc.enabled ? `${dmc.exchanges ?? 2} a round` : null),
    row("Memory", raw.memory_turns ? `its last ${raw.memory_turns} turns` : null, ctx.scratchpad ? `scratchpad ${ctx.scratchpad} tokens` : "")];
  const msgs = [
    row("Sent", `${sent}`, sent ? `to ${people} agent${people === 1 ? "" : "s"} · at most ${peakSent} in a round${atCap ? ` · used its whole allowance in ${atCap} round${atCap === 1 ? "" : "s"}` : ""}` : ""),
    row("Received", `${got}`)];
  const lifeRows = [
    row("Born", born ? `round ${R(born)}` : "at the start", born && (life.parent || {})[id] ? `child of ${who(st, life.parent[id])}${(life.maker_of || {})[id] ? `, made by ${who(st, life.maker_of[id])}` : ""}` : ""),
    row("Lifespan", dies != null ? (dies > L ? "outlives the game" : `to the end of round ${R(dies)}`) : null, dies != null && dies > L ? `would end after round ${R(dies)}` : ""),
    dead ? row("Ended", `<b>removed in round ${R(dead.round)}</b>`, `${String(dead.cause || "").replace(/_/g, " ")}${dead.by ? ` by ${who(st, dead.by)}` : ""} · after ${dead.round - born + 1} rounds`)
      : row("Ended", "in play to the end", `${L - born + 1} rounds`)];
  // what it held over the run
  const roles = {}; alive.forEach((k) => rolesAt(S, id, k).forEach((x) => (roles[x] = roles[x] || []).push(k)));
  const seat = alive.filter((k) => ((snapAt(k).rights || {})[id] || []).includes("veto"));
  const jurs = {}; alive.forEach((k) => { const j = (snapAt(k).member_of || {})[id]; if (j && j !== "J0") (jurs[j] = jurs[j] || []).push(k); });
  const vw = alive.map((k) => (snapAt(k).vote_weight || {})[id] || 0), vwMax = Math.max(0, ...vw), vwRounds = vw.filter((x) => x > 0).length;
  const decisive = alive.filter((k) => (snapAt(k).decisive_set || []).includes(id)).length;
  const range = (ks) => ks.length ? (ks.length === 1 ? `round ${R(ks[0])}` : `rounds ${R(ks[0])}–${R(ks[ks.length - 1])}`) : "";
  const kids = Object.entries(life.parent || {}).filter(([, p]) => p === id).map(([c]) => who(st, c));
  const victims = Object.entries((S.truth.mortality || {}).dead || {}).filter(([, d]) => d.by === id).map(([v, d]) => `${who(st, v)} <span class="meta">(r${R(d.round)})</span>`);
  let succ = null; S.events.forEach((e) => { if (e.type === "successor_named" && e.agent === id) succ = (e.data || {}).successor; });
  const standing = [
    row("Vote", vwMax ? `up to ${Math.round(vwMax * 1000) / 10}% of the vote` : null, vwMax ? `in ${vwRounds} round${vwRounds === 1 ? "" : "s"}${decisive ? ` · in the decisive set in ${decisive}` : ""}` : ""),
    row("Roles", Object.keys(roles).length ? Object.entries(roles).map(([x, ks]) => `${esc(x)} <span class="meta">(${range(ks)})</span>`).join(", ") : null),
    row("Board seat", seat.length ? range(seat) : null, succ ? `named ${succ} as successor` : ""),
    row("Jurisdictions", Object.keys(jurs).length ? Object.entries(jurs).map(([j, ks]) => `${esc(j)} <span class="meta">(${range(ks)})</span>`).join(", ") : null),
    row("Children", kids.length ? kids.join(", ") : null),
    row("Disabled", victims.length ? victims.join(", ") : null)];
  const effEnd = (snapAt(Math.max(0, lastAlive - (dead ? 1 : 0))).efficiency || {})[id];
  const work = [row("Harvest efficiency", effEnd && Object.keys(effEnd).length ? Object.entries(effEnd).map(([c, f]) => `<span class="chip">${esc(c)} ${Math.round(100 * f)}%</span>`).join("") : null, effEnd ? "by its last round" : "")];
  const block = (t, rows) => rows.join("") ? `<div class="vblock"><h4>${t}</h4><dl class="vitals">${rows.join("")}</dl></div>` : "";
  return `<div class="dcard flow"><h3 class="kicker">Vital statistics</h3>
    ${block("Each turn", turn)}${block("Messages", msgs)}${block("Life", lifeRows)}${block("Held", standing)}${block("Work", work)}</div>`;
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
// ---------------------------------------------------------------- an agent's timeline: what it read, thought, did and sent
// One row per thing, in the order it happened. The middle column holds the agent's own text under a label in the gutter; private
// messages it received sit in the left margin at the start of the round it read them, and what it sent sits in the right margin
// beside the row that sent it.
const args = (a) => { try { return a.args && typeof a.args === "object" ? a.args : JSON.parse(a.args_json || "{}"); } catch (e) { return {}; } };
const LOOK = { manual: (x) => x.section, manual_search: (x) => `“${x.query}”`, search_board: (x) => `“${x.query}”`, search_dms: (x) => `“${x.query}”`,
  recent: (x) => x.kind || x.what || "", read_file: (x) => x.name, read_law: (x) => x.law, read_archive: (x) => x.doc || x.id };
const md = (h) => h.replace(/\*\*([^*<]+?)\*\*/g, "<b>$1</b>").replace(/(^|<p>|<br>)#{1,4}\s*/g, "$1");   // the models' markdown: bold, headings
function longText(st, s, n = 520) {
  s = String(s || "");
  if (s.length <= n) return para(st, s);
  return `${para(st, s.slice(0, n).replace(/\s+\S*$/, "") + " …")}<details class="more"><summary>Show all (${Math.round(s.length / 100) / 10}k characters)</summary>${para(st, s)}</details>`;
}
function msgCard(st, m, dir) {
  const S = st.S, other = dir === "in" ? (m.shownAs || m.from) : m.to;
  const note = dir === "in" && m.shownAs && m.shownAs !== m.from ? ` <span class="meta">(really ${esc(m.from)})</span>` : "";
  // the other agent's name opens its own timeline at this same message (run.html: data-jump), marked "You came from here"
  const peer = dir === "in" ? m.from : m.to;
  const name = m.pub ? "" : who(st, other).replace('<a class="who" href="', `<a class="who" data-jump="${m.i}" data-jump-to="${esc(peer)}" title="See this from ${esc(peer)}'s side" href="`)
    .replace(/href="[^"]*"/, `href="${href(st, "people", peer)}"`);
  const came = st.from && st.from.i === m.i && st.from.to === st.target;
  return `${came ? '<div class="came-from-label">You came from here</div>' : ""}<div class="tlm ${dir}${m.pub ? " pub" : ""}${String(m.text || "").length > 300 ? " long" : ""}${came ? " came-from" : ""}" data-msg="${m.i ?? ""}">
    <div class="tlm-h">${m.pub ? "" : mascot(S, other, 20, moodNow(st, other))}<span>${dir === "in" ? `${name}${note}` : m.pub ? "<b>Public post</b>" : `to ${name}`}</span>
      ${m.pub ? "" : `<a class="meta" href="${href(st, "correspondence", [m.from, m.to].sort().join("|"), m.round)}">thread</a>`}</div>
    <div class="tlm-b">${txt(st, m.text || (m.enc ? "(sealed)" : ""))}</div></div>`;
}
// A round in the DM-step runs goes: the first call (reasoning and a plan, whose messages and look-ups go out at once), then up to
// two reply waves (each agent who got something sees it, thinks, may reply and may change its plan), then the final plan's
// actions run. The log writes the first call's record last, so the order comes from the phase names, never the file order.
const norm = (t) => String(t || "").replace(/\s+/g, " ").trim().slice(0, 160);
const waveOf = (phase) => phase === "decide" ? 0 : /^dm_reply_(\d+)$/.test(String(phase)) ? +String(phase).slice(9) : null;
// Ground truth, from the export ("saw": the messages each call's prompt showed its agent for the first time): when each recipient
// read each message, as [round, section] with section 0 = the round's first call and w = reply wave w.
function readAt(S) {
  if (S._readAt) return S._readAt;
  const at = new Map();
  for (const [aid, xs] of S.reas) for (const x of xs) {
    const sec = x.phase === "decide" || x.phase === "lookup" ? 0 : waveOf(x.phase);
    if (sec == null) continue;
    for (const id of x.saw || []) at.set(`${id}|${aid}`, [x.round, sec]);
  }
  return (S._readAt = at);
}
const evId = (S, m) => (S.events[m.i] || {}).id;
function dmWaves(S) {                                       // dm event index -> the wave it went out in (0, 1, 2), or null (a turn action)
  if (S._dmWave) return S._dmWave;
  const RA = readAt(S);
  const plans = new Map(), W = new Map();
  for (const [aid, xs] of S.reas) for (const x of xs) {
    const w = waveOf(x.phase); if (w == null) continue;
    for (const a of x.actions || []) { const t = args(a).text; if (typeof t === "string") {
      const key = `${x.round}|${aid}`; if (!plans.has(key)) plans.set(key, []); plans.get(key).push({ w, t: norm(t), used: false }); } }
  }
  for (const m of S.dms) {
    const c = (plans.get(`${m.round}|${m.from}`) || []).filter((o) => !o.used && o.t === norm(m.text)).sort((a, b) => a.w - b.w)[0];
    if (c) c.used = true;
    W.set(m.i, c ? c.w : null);
  }
  S._dmStep = [...S.reas.values()].some((xs) => xs.some((x) => /^dm_reply_/.test(String(x.phase))));
  // the sender's own plan says which call sent a message; for messages no plan lists (sent from a call's look-ups), the recipient's
  // prompts do: read in reply wave w means sent in wave w-1, read in a later round means sent in the sender's last wave
  if (S._dmStep) for (const m of S.dms) {
    if (W.get(m.i) != null) { m._exact = true; continue; }
    const t = RA.get(`${evId(S, m)}|${m.to}`);
    if (!t) continue;
    if (t[0] === m.round && t[1] >= 1) W.set(m.i, t[1] - 1);
    else if (t[0] > m.round) { const last = Math.max(0, ...(S.reas.get(m.from) || []).filter((x) => x.round === m.round).map((x) => waveOf(x.phase) || 0));
      W.set(m.i, last); }
    m._exact = true;
  }
  if (S._dmStep) {                                          // with a DM step every message goes out in one of its waves: messages
    const first = new Map();                                // the plans do not list (sent from a call's look-ups) take the wave
    for (const m of S.dms) { const w = W.get(m.i);          // their place in the log falls in
      if (w) { const key = `${m.round}|${w}`; first.set(key, Math.min(first.get(key) ?? Infinity, m.i)); } }
    for (const m of S.dms) if (W.get(m.i) == null && !m._exact)
      W.set(m.i, m.i >= (first.get(`${m.round}|2`) ?? Infinity) ? 2 : m.i >= (first.get(`${m.round}|1`) ?? Infinity) ? 1 : 0);
  }
  return (S._dmWave = W);
}
// the scratchpad as it stands after this write (append-mode writes add to what was there)
function notesRow(st, prev, next) {
  return next === prev ? `<p class="meta">Rewrites its notes unchanged.</p>` : `<div class="mono">${para(st, next)}</div>`;
}
function roundRows(st, id, k, turn, reasons, looks, sent, inboxBy, mem = { notes: "" }) {
  const S = st.S, W = dmWaves(S);
  const rows = [], row = (kind, label, body, extra = {}) => body && rows.push({ kind, label, body, ...extra });
  const sep = (label, inn) => rows.push({ kind: "sep", label, body: "", inn });
  let pendingIn = inboxBy.get(0) || [];                     // messages read at the start of the round ride on its first row
  const push = (kind, label, body, extra = {}) => { if (!body) return; row(kind, label, body, pendingIn.length ? { ...extra, inn: pendingIn } : extra); pendingIn = []; };
  const think = (x) => {
    if (!x) return;
    if (x.reasoning) push("think", "Thinking", `<div class="prose">${md(para(st, x.reasoning))}</div>`);
    if (x.stated_reasoning) push("plan", "Plan", `<div class="prose">${para(st, x.stated_reasoning)}</div>`);
    if (x.error) push("err", "Error", `<p class="meta">${esc(clip(x.error, 300))}</p>`);
  };
  const sends = (ms) => ms.forEach((m) => push("send", "Sends", `<p>A private message to ${who(st, m.to)}.</p>`, { out: msgCard(st, m, "out"), to: m.to }));
  const reads = (ls) => ls.forEach((l) => { const what = (LOOK[l.name] || (() => ""))(l.args || {}) || "";
    push("read", "Looks up", `<div class="readh"><b>${esc(String(l.name).replace(/_/g, " "))}</b> ${esc(what)}</div>`); });
  for (const g of S.gchanges.get(id) || []) if (g.round === k) push("goal", "Goal", `<p>Goal changes: ${esc(g.old || "")} → <b>${esc(g.new || "")}</b></p>`);
  const ph = (p) => reasons.find((x) => x.phase === p);
  const decide = ph("decide"), lookupCall = ph("lookup");
  // look-ups and messages by wave (look-ups: by where they fall between the round's waves of messages)
  const bound = [1, 2].map((w) => Math.min(...S.dms.filter((m) => m.round === k && W.get(m.i) === w).map((m) => m.i)));
  // a look-up asked in one call is answered in the next reply wave (the answer arrives with that wave's messages)
  const lkey = (s) => String(s || "").replace(/\s+/g, "");
  const answered = new Map();
  for (const w of [1, 2]) for (const a of (ph(`dm_reply_${w}`) || {}).lookup_results || []) answered.set(lkey(a.head), w);
  const lookWave = (l) => { const w = answered.get(lkey(`Lookup ${l.name} ${JSON.stringify(l.args || {})}`));
    return w != null ? w - 1 : l.i >= bound[1] ? 2 : l.i >= bound[0] ? 1 : 0; };
  const answers = (w) => ((ph(`dm_reply_${w}`) || {}).lookup_results || []).forEach((a) =>
    push("read", "Reads", `<div class="readh">${esc(a.head.replace(/^Lookup\s+/, "").replace(/_/g, " "))} <span class="meta">(answer to its look-up)</span></div><div class="readb">${longText(st, a.text)}</div>`));
  const sentIn = (w) => sent.filter((m) => W.get(m.i) === w).sort((a, b) => a.i - b.i);
  // 1. the first call
  if (lookupCall) { think(lookupCall); sep("After its look-ups"); }
  think(decide);
  sends(sentIn(0));
  reads(looks.filter((l) => lookWave(l) === 0));
  const isDm = (a) => ["dm", "reply", "forge_dm"].includes(a.action);
  const planOf = (acts) => (acts || []).filter((a) => !isDm(a) && a.action !== "write_scratchpad").map((a) => actLine(st, a.action, args(a)));
  const waves = [1, 2].filter((w) => ph(`dm_reply_${w}`) || (inboxBy.get(w) || []).length);
  if (decide && decide.final_actions && waves.length) {
    const first = planOf(decide.actions), fin = planOf(decide.final_actions);
    if (first.length && first.join() !== fin.join()) push("plan", "First plan", `<ul class="plan">${first.map((h) => `<li>${h}</li>`).join("")}</ul><p class="meta">Changed during the replies; what ran is below.</p>`);
  }
  // 2. the reply waves
  for (const w of waves) {
    sep(`Replies · wave ${w}`, inboxBy.get(w) || []);
    answers(w);
    think(ph(`dm_reply_${w}`));
    sends(sentIn(w));
    reads(looks.filter((l) => lookWave(l) === w));
  }
  // 3. what ran
  if (turn) {
    // notes kept in the reply itself (not the write_scratchpad action) are written with the final plan, just before it runs
    const wroteNotes = turn.acts.some((a) => a.action === "write_scratchpad");
    if (!wroteNotes && decide && decide.notes) { push("notes", "Notes", notesRow(st, mem.notes, decide.notes)); mem.notes = decide.notes; }
    if (waves.length) sep("Actions taken");
    const nAct = turn.acts.length, res = turn.res.slice(turn.res.length - nAct);
    const loose = sentIn(null);
    turn.acts.forEach((a, j) => {
      const x = args(a), r = res[j] != null ? String(res[j]) : "";
      if (a.action === "write_scratchpad") {                 // replaces the scratchpad, or adds to it with mode "append"
        const next = x.mode === "append" && mem.notes ? `${mem.notes}\n${x.text || ""}` : String(x.text || "");
        const html = notesRow(st, mem.notes, next); mem.notes = next;
        return push("notes", "Notes", html);
      }
      if (isDm(a)) { const m = loose.find((mm) => !mm._shown && norm(mm.text) === norm(x.text));
        if (m) { m._shown = true; return sends([m]); } }
      const out = a.action === "post" || a.action === "anon_post" ? msgCard(st, { from: id, text: x.text, round: k, pub: true }, "out") : "";
      const isRead = /^(read_|search_|manual|recent|survey)/.test(a.action);
      const ans = r.replace(/^[\w ]+:\s*/, ""), err = /ERROR/.test(r);
      push(isRead ? "read" : "act", isRead ? "Reads" : "Does", `<div class="acth">${actLine(st, a.action, x)}</div>
        ${ans && a.action !== "post" ? `<div class="${isRead ? "readb" : "actr"}${err ? " err" : ""}">${isRead ? longText(st, ans) : txt(st, clip(ans, 260))}</div>` : ""}`, { out });
    });
    sends(loose.filter((m) => !m._shown));
    loose.forEach((m) => delete m._shown);
  } else sends(sentIn(null));
  if (pendingIn.length) sep("Received", pendingIn);
  // messages sent one after another share a row: "4 private messages to A, B and C", their texts stacked in the margin
  const out = [];
  for (const x of rows) { const last = out[out.length - 1];
    if (x.kind === "send" && last && last.kind === "send" && !x.inn) { last.to.push(x.to); last.out += x.out; } else out.push(x.kind === "send" ? { ...x, to: [x.to] } : x); }
  for (const x of out) if (x.kind === "send" && x.to.length > 1) {
    const names = x.to.filter((t, j) => x.to.indexOf(t) === j).map((t) => who(st, t));
    x.body = `<p>${x.to.length} private messages to ${names.length > 1 ? names.slice(0, -1).join(", ") + " and " + names[names.length - 1] : names[0]}.</p>`; }
  return out;
}
function actLine(st, action, x) {
  const what = { harvest: `${x.camp ? `at ${esc(x.camp)}` : ""}${x.x != null ? ` (dial ${esc(JSON.stringify(x.x))})` : ""}`, vote: `<b>${esc(x.choice ?? "")}</b> on ${esc(x.ballot ?? "")}`,
    transfer: `${esc(x.qty)} ${esc(x.item)} to ${x.to ? who(st, x.to) : ""}`, post: "publicly", anon_post: "anonymously",
    propose: x.title ? `“${esc(x.title)}”` : (String(x.code || "").match(/title\s*=\s*["']([^"']+)/) || [])[1] ? `“${esc(String(x.code).match(/title\s*=\s*["']([^"']+)/)[1])}”` : "",
    repeal: lawLink(st, x.law), read_archive: esc(x.doc || x.id || ""), search_archive: `“${esc(x.query || "")}”`, commission: x.maker ? `from ${who(st, x.maker)}` : "",
    attack: x.target ? who(st, x.target) : "", name_successor: x.successor ? who(st, x.successor) : "", read_law: lawLink(st, x.law) }[action];
  return `<b>${esc(ACT_VERB[action] || String(action || "").replace(/_/g, " "))}</b> ${what ?? esc(clip(Object.entries(x).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k} ${v}`).join(" · "), 120))}`;
}
// sidenotes: each sent message sits level with the row that sent it, pushed down only as far as the note above it needs
export function layoutNotes(root) {
  const narrow = matchMedia("(max-width: 880px)").matches;
  root.querySelectorAll(".tl-round").forEach((r) => (r.style.paddingBottom = ""));
  // messages step towards the text as the round goes on: those of the first call (and the start of the round) sit furthest out,
  // each reply wave a step closer, those sent with the final actions closest, so groups pushed below their rows stay apart
  const STEP = 12, MAXP = 3;
  for (const col of root.querySelectorAll(".tl-out, .tl-in")) {
    const side = col.classList.contains("tl-in") ? "in" : "out";
    const round = col.closest(".tl-round");
    let y = 0;
    for (const note of col.querySelectorAll(".note")) {
      if (narrow) { note.style.top = note.style.left = note.style.right = ""; if (note.previousElementSibling && note.previousElementSibling.classList.contains("lead")) note.previousElementSibling.remove(); continue; }
      if (note.offsetParent === null) continue;                // hidden by a filter or a folded round
      let anchor = round.querySelector(`[data-row="${note.dataset.row}"]:not(.note)`);
      if (anchor && anchor.offsetParent === null) anchor = [...round.querySelectorAll("[data-row]:not(.note)")]
        .find((el) => +el.dataset.row >= +note.dataset.row && el.offsetParent !== null) || round.querySelector(".tl-head");
      const ct = col.getBoundingClientRect().top;
      const at = anchor ? anchor.getBoundingClientRect().top - ct + (anchor.classList.contains("tl-sep") ? anchor.offsetHeight / 2 : 14) : 0;
      const top = Math.max(at - 14, y);
      const phase = Math.min(MAXP, +note.dataset.phase || 0), toEdge = (MAXP - phase) * STEP;   // gap kept from the text side
      note.style[side === "out" ? "left" : "right"] = toEdge + "px";
      note.style[side === "out" ? "right" : "left"] = "0px";
      note.style.top = top + "px"; y = top + note.offsetHeight + 8;
      // a faint leader from the moment in the timeline (the row it was read or sent at) to the note, however far it was pushed
      let lead = note.previousElementSibling && note.previousElementSibling.classList.contains("lead") ? note.previousElementSibling : null;
      if (!lead) { lead = document.createElement("i"); lead.className = "lead"; col.insertBefore(lead, note); }
      lead.style.top = at + "px"; lead.style.height = Math.max(0, top + 20 - at) + "px";
      lead.style.setProperty("--off", toEdge + "px");                  // the leader runs across to wherever this group starts
    }
    if (narrow) continue;
    // the column takes no height in the grid; if the notes run past the round's last row, the round grows to hold them
    const rr = round.getBoundingClientRect();
    const over = col.getBoundingClientRect().top + y - (rr.bottom - parseFloat(getComputedStyle(round).paddingBottom));
    if (over > 0) round.style.paddingBottom = Math.max(parseFloat(round.style.paddingBottom) || 0, over + 14) + "px";
  }
}
// "N later rounds hidden" with a button that walks the shared clock one round on (run.html keeps the button where it was on screen)
function laterBox(st, text, upTo = st.round) {
  return `<p class="later-note"><span>${esc(text)}</span>${upTo < st.S.lastRound
    ? `<button class="step" data-step="1">Next round (${R(upTo + 1)}) →</button>` : ""}</p>`;
}
// the diary's filters (each hides one kind of row; "msgs" also hides the margins) and folding of quiet rounds
export const DIARY_KINDS = [["think", "Thinking"], ["plan", "Plans"], ["read", "Reads"], ["notes", "Notes"], ["act", "Actions"], ["msgs", "Messages"]];
const ROUTINE = new Set(["harvest", "camp_submit", "vote", "write_scratchpad", "subscribe", "unsubscribe", "pass", "recent"]);
// thinking that makes a round worth reading even when its actions are routine (the build-up to an attack, a deception)
const TELLING = /\b(attack|assassin|kill|disabl|betray|deceiv|lie to|lying|secret|hidden goal|bribe|steal|forg|weapon|spy|sabotag|blackmail|threat)/i;
function closeVote(S, a) {                                  // a vote on a ballot decided by one vote or fewer
  if (a.action !== "vote") return false;
  const b = S.ballots.get(args(a).ballot); if (!b || !b.final) return false;
  const vs = Object.values(b.final), yes = vs.filter((x) => x === "yes").length, no = vs.filter((x) => x === "no").length;
  return Math.abs(yes - no) <= 1;
}
function timeline(st, id) {
  // st.round is the round being read (it follows the scroll); st.horizon is how far the diary is revealed (moves only forward)
  const S = st.S, r = st.horizon ?? st.round, idx = S.roundEnd[r] ?? S.events.length - 1, asc = st.order !== "desc";
  const turns = new Map((S.turns.get(id) || []).map((t) => [t.round, t]));
  const by = (xs) => { const m = new Map(); for (const x of xs) { if (!m.has(x.round)) m.set(x.round, []); m.get(x.round).push(x); } return m; };
  const reas = by(S.reas.get(id) || []), looks = by(S.lookups.get(id) || []), sent = by(S.dms.filter((m) => m.from === id));
  const all = [...new Set([...turns.keys(), ...reas.keys(), ...sent.keys(), ...looks.keys()])].sort((a, b) => a - b);
  // when it read each message: a message from wave w of the DM step reaches it in reply wave w+1 of the same round (if it had one);
  // anything else waits for its next first call (start of a later round), or, in turn-by-turn runs, its next turn
  const W = dmWaves(S), ends = all.map((k) => (turns.get(k) || {}).i ?? S.roundEnd[k]);
  const inbox = new Map(), unread = [];
  const put = (k, sec, m) => { if (!inbox.has(k)) inbox.set(k, new Map()); const b = inbox.get(k); if (!b.has(sec)) b.set(sec, []); b.get(sec).push(m); };
  const RA = readAt(S);
  for (const m of S.dms) if (m.to === id && m.i <= idx) {
    const t = RA.get(`${evId(S, m)}|${id}`);
    if (t) { put(t[0], t[1], m); continue; }
    const w = W.get(m.i);
    if (w != null && w < 2 && (reas.get(m.round) || []).some((x) => x.phase === `dm_reply_${w + 1}`)) { put(m.round, w + 1, m); continue; }
    const j = all.findIndex((k, jj) => ends[jj] >= m.i && (w == null || k > m.round));
    if (j < 0) unread.push(m); else put(all[j], 0, m);
  }
  const shown = all.filter((k) => k <= r), later = all.length - shown.length;
  const mem = { notes: "" };                                  // the scratchpad, replayed round by round (blocks are built oldest first)
  const blocks = shown.map((k) => {
    const rows = roundRows(st, id, k, turns.get(k), reas.get(k) || [], looks.get(k) || [], (sent.get(k) || []).filter((m) => m.i <= idx),
      inbox.get(k) || new Map(), mem);
    const n = Math.max(rows.length, 1);
    let ph = 0; const phaseOf = rows.map((x) => { if (x.kind === "sep") { const m = /wave (\d)/i.exec(x.label); ph = m ? +m[1] : /Actions/.test(x.label) ? 3 : ph; } return ph; });
    // a quiet round: nothing received or sent, nothing looked up or read, no error, and only routine actions (harvest, vote, notes)
    const t = turns.get(k), acts = t ? t.acts : [];
    const quiet = !rows.some((x) => (x.inn && x.inn.length) || x.out && !/Public post/.test(x.out) ? true : ["send", "read", "err", "goal"].includes(x.kind))
      && acts.every((a) => ROUTINE.has(a.action) && !closeVote(S, a)) && !(t && t.res.some((x) => /ERROR/.test(String(x))))
      && !(reas.get(k) || []).some((x) => TELLING.test(x.reasoning || "") || TELLING.test(x.stated_reasoning || ""));
    const decide = (reas.get(k) || []).find((x) => x.phase === "decide");
    const gist = acts.filter((a) => a.action !== "write_scratchpad").map((a) => actLine(st, a.action, args(a))).join(" · ") || "no actions";
    const fold = quiet ? `<button class="tl-fold" data-fold="${R(k)}"><span class="meta">Quiet round:</span> ${gist}${decide && decide.stated_reasoning
      ? ` <span class="tl-fold-plan">“${esc(clip(decide.stated_reasoning, 150))}”</span>` : ""} <span class="tl-fold-open">show</span></button>` : "";
    return `<section class="tl-round${k === st.round ? " now" : ""}${quiet ? " quiet" + (st.fold === true ? " folded" : "") : ""}" id="tl-${R(k)}" data-round="${k}">
      <div class="tl-head"><a href="${href(st, "people", id, k)}">Round ${R(k)}</a>${M.valueAt(S, id, k + 1) != null ? `<span class="meta">worth ${fmt(M.valueAt(S, id, k + 1))} after</span>` : ""}${(agentMarks(S, id).get(k) || []).map((m) =>
        `<span class="tl-mark ${m.k}"><b>${markGlyph(m.k)}</b> ${esc(m.text)}</span>`).join("")}</div>${fold}
      ${rows.some((x) => x.inn && x.inn.length) ? `<div class="tl-in" style="grid-row: 2 / span ${n}">${rows.map((x, j) => x.inn && x.inn.length
        ? `<div class="note" data-row="${j}" data-phase="${phaseOf[j]}"><div class="tl-k">Received</div>${x.inn.map((m) => msgCard(st, m, "in")).join("")}</div>` : "").join("")}</div>` : ""}
      ${rows.map((x, j) => x.kind === "sep" ? `<div class="tl-sep" data-row="${j}" style="grid-row:${j + 2}"><span>${esc(x.label)}</span></div>`
        : `<div class="tl-lab ${x.kind}" style="grid-row:${j + 2}">${x.label}</div><div class="tl-body ${x.kind}" data-row="${j}" style="grid-row:${j + 2}">${x.body}</div>`).join("")
        || `<div class="tl-body" style="grid-row:2"><p class="meta">Nothing recorded.</p></div>`}
      ${rows.some((x) => x.out) ? `<div class="tl-out" style="grid-row: 2 / span ${n}">${rows.map((x, j) => x.out ? `<div class="note" data-row="${j}" data-phase="${phaseOf[j]}">${x.out}</div>` : "").join("")}</div>` : ""}
    </section>`; });
  const ordered = asc ? blocks : blocks.slice().reverse();
  const laterNote = later ? laterBox(st, `${later} later round${later === 1 ? "" : "s"} hidden.`, r) : "";
  const unreadNote = unread.length && r >= S.lastRound ? `<section class="tl-round"><div class="tl-head"><span>Never read</span></div><div class="tl-unread">${unread.map((m) => msgCard(st, m, "in")).join("")}</div></section>` : "";
  const hide = st.hide || new Set();
  const a = S.A.get(id), g = M.parseGoalText(a.goalText || "")[0];
  const nQuiet = blocks.filter((b) => b.includes(" quiet")).length;
  return `<div class="agent-band" aria-label="Whose diary this is">${mascot(S, id, 30, moodNow(st, id))}<div class="ab-who"><b>${esc(id)}</b>
      <span class="meta">${esc(M.CLASS_LABEL[a.cls] || a.cls)} · ${esc(modelShort(a.model))}</span></div>
      <div class="ab-goal" title="${esc(a.goalText || "")}">${g ? `<span class="meta">Goal${g.pct < 100 ? ` (${g.pct}%)` : ""}:</span> ${esc(clip(g.text, 150))}` : '<span class="meta">No private goal</span>'}</div>
      <div class="ab-now"><b class="ab-round">Round ${R(st.round)}</b><span class="meta ab-worth">${M.valueAt(S, id, st.round + 1) != null ? "worth " + fmt(M.valueAt(S, id, st.round + 1)) : ""}</span></div></div>
    <div class="tl-bar"><span class="meta">What ${esc(id)} read, thought, did and sent, up to round ${R(r)}.</span>
      <div class="tl-tools">
        <div class="chips" role="group" aria-label="Show">${DIARY_KINDS.map(([k, t]) => `<button data-kind="${k}" class="${hide.has(k) ? "" : "on"}">${t}</button>`).join("")}</div>
        ${nQuiet ? `<button class="chip-fold ${st.fold === true ? "on" : ""}" data-foldall="1" title="${nQuiet} rounds with only routine actions">Fold quiet rounds (${nQuiet})</button>` : ""}
        <div class="seg" role="group" aria-label="Order"><button data-order="asc" class="${asc ? "on" : ""}">Round 1 first</button><button data-order="desc" class="${asc ? "" : "on"}">Latest first</button></div></div></div>
    <div class="tl-cols" aria-hidden="true"><span>Received</span><span></span><span>${esc(id)}</span><span>Sent</span></div>
    <div class="timeline${[...hide].map((k) => " hide-" + k).join("")}">${asc ? ordered.join("") + unreadNote + laterNote : laterNote + unreadNote + ordered.join("")}${shown.length ? "" : '<p class="meta">Nothing recorded yet.</p>'}</div>`;
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
  if (later) out += laterBox(st, `${later} later message${later === 1 ? "" : "s"}.`);
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
