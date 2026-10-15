// The run model: turns a run's data (instance, events, snapshots, ground truth, reasoning, scores) into what the run page shows.
// The event semantics follow charter/viewer/template.html (prepare); presentation lives in the views, not here.
//
// Input today: the story viewer's viewer.json ({instance, events, snapshots, truth, reasoning, score, name}). When the export
// tables carry everything, build the same object from them (one adapter), and nothing below changes.

export const CLASS_ORDER = ["legislator", "worker", "scientist", "media", "board", "fixer", "observer"];
export const CLASS_LABEL = { legislator: "Legislator", worker: "Worker", scientist: "Scientist", media: "Editor", board: "Board",
  fixer: "Fixer", observer: "Secret observer", agent: "Agent" };
export const TRAITS = [["risk", "cautious", "bold"], ["trust", "wary", "trusting"], ["honesty", "slippery", "honest"],
  ["assertiveness", "follower", "leader"], ["patience", "impatient", "patient"], ["reciprocity", "forgiving", "tit-for-tat"],
  ["talkativeness", "quiet", "chatty"]];
const PUBLIC_SYS = new Set(["rights", "sanction", "censure", "rename", "ruling", "accuse", "respond", "case_dismissed", "invoke",
  "channel_created", "channel_closed", "dm_limit", "treasury_coins", "patched", "proposal_failed", "veto_window", "vetoed", "veto_vote",
  "ballot_open", "bank_run", "redemption_suspended", "redemption_resumed", "par_set", "interest_cap", "default_consequence",
  "loan_active", "loan_payment", "loan_repaid", "loan_defaulted", "loan_forgiven", "loan_bought", "loan_restructured", "power_used",
  "powers_disclosure", "factored", "post_hidden", "post_revealed", "law_error", "drift", "title", "repeal_failed", "disabled"]);
// how each kind of public happening is filed in a round's edition
export const SECTION_OF = (it) => ({ proposal: "legislature", law: "legislature", ballot: "legislature", media: "press", post: "letters",
  gazette: "gazette", world: "events" })[it.kind] || (it.kind === "sys" ? (/^(tribute|raid|project|bank_run|disabled|redemption)/.test(it.type)
  ? "events" : "legislature") : null);

export function prepare(D) {
  const inst = D.instance, truth = D.truth || {}, events = D.events, snaps = D.snapshots || [], score = D.score || {};
  const A = new Map();
  const add = (a) => { if (a && a.id && !A.has(a.id)) A.set(a.id, { id: a.id, cls: a.cls || "agent", model: a.model || "", tier: a.tier || "",
    goal: a.goal || {}, archetype: a.archetype || "", personality: a.personality || null, ptext: a.personality_text || "",
    atext: a.archetype_text || "", actions: a.actions, rights: a.rights || [], endowment: a.endowment || {} }); };
  (inst.agents || []).forEach(add);
  (truth.arrived_agents || []).forEach(add);
  if (inst.observer) add({ ...inst.observer, cls: "observer" });
  for (const e of events) if (e.agent && !A.has(e.agent) && !["constitution", "reserve"].includes(e.agent) && !String(e.agent).startsWith("law:")) add({ id: e.agent, cls: "agent" });
  const agents = [...A.values()].sort((a, b) => (CLASS_ORDER.indexOf(a.cls) - CLASS_ORDER.indexOf(b.cls)) || a.id.localeCompare(b.id));
  agents.forEach((a, i) => { a.hue = Math.round((i * 137.508 + 18) % 360); a.n = i; a.goalText = (a.goal && (a.goal.text || a.goal.primary)) || ""; });

  const anon = {}, forged = {}, rumor = {};
  for (const e of events) {
    if (e.type === "anon_truth") anon[e.data.event] = e.data.author;
    if (e.type === "forged_dm" || e.type === "forgery_truth") forged[e.data.event] = e.data.source || "power";
    if (e.type === "world_event_truth") rumor[e.data.event] = e.data;
  }
  const laws = new Map();
  for (const [id, l] of Object.entries(truth.laws || {})) laws.set(id, { ...l, id });
  const law = (id) => { if (!laws.has(id)) laws.set(id, { id }); return laws.get(id); };
  const lawTL = new Map(), tl = (id, x) => { if (!id) return; if (!lawTL.has(id)) lawTL.set(id, []); lawTL.get(id).push(x); };
  const items = [], dms = [], lawEvents = [], roundAt = [], roundEnd = [], roundStart = [];
  const turns = new Map(), gchanges = new Map(), departs = new Map(), arrives = new Map(), transfers = [], harvests = [], ballots = new Map();
  const turnAt = {}, dmOutAt = {}, posts = [], lookups = new Map();
  const push = (m, k, x) => { if (!m.has(k)) m.set(k, []); m.get(k).push(x); };
  let round = 0;
  events.forEach((e, i) => {
    if (e.round !== undefined) round = e.round;
    roundAt[i] = round; roundEnd[round] = i; if (roundStart[round] === undefined) roundStart[round] = i;
    const d = e.data || {};
    switch (e.type) {
      case "turn": push(turns, e.agent, { i, round, acts: d.actions || [], res: d.results || [], phase: d.phase }); turnAt[`${round}|${e.agent}`] = i; break;
      case "goal_change": push(gchanges, d.agent || e.agent, { i, round, ...d }); break;
      case "lookup": push(lookups, e.agent, { i, round, name: d.name, args: d.args || {}, via: d.via }); break;
      case "departure": departs.set(d.agent || e.agent, i); break;
      case "disabled": departs.set(d.agent || e.agent, i); break;
      case "arrival": case "agent_arrives": arrives.set(d.agent || e.agent, i); break;
      case "transfer": transfers.push({ i, round, from: e.agent, to: d.to, item: d.item, qty: d.qty }); break;
      case "harvest": harvests.push({ i, round, who: e.agent, camp: d.camp, y: d.yield }); break;
      case "ballot_open": { const q = String(d.question || ""); const b = { id: d.ballot, open: i, round, q, electorate: d.electorate || [], rule: d.rule,
          closes: d.closes_round, votes: [], law: d.law || (q.match(/\bL\d+\b/) || [])[0] };
        ballots.set(d.ballot, b); tl(b.law, { i, kind: "ballot", b }); break; }
      case "vote": { const b = ballots.get(d.ballot); if (b) b.votes.push({ i, who: e.agent, choice: d.choice }); break; }
      case "ballot_close": { const b = ballots.get(d.ballot); if (b) { b.close = i; b.result = d.result; b.final = d.votes || {}; } break; }
      case "proposal": { const l = law(d.law); for (const k of ["title", "intent", "code"]) if (!l[k] && d[k]) l[k] = d[k];
        if (!l.cls && d.class) l.cls = d.class; if (!l.author) l.author = e.agent; if (l.proposed == null) l.proposed = round;
        tl(d.law, { i, kind: "proposed", who: e.agent }); break; }
      case "enact": { const l = law(d.law); if (!l.title) l.title = d.title; if (!l.cls) l.cls = d.class; if (!l.author) l.author = e.agent;
        l.enacted = round; tl(d.law, { i, kind: "enacted", who: e.agent }); break; }
      case "repeal": law(d.law).repealed = round; tl(d.law, { i, kind: "repealed" }); break;
      case "veto_window": tl(d.law, { i, kind: "veto_window", until: d.until }); break;
      case "vetoed": law(d.law).vetoed = round; tl(d.law, { i, kind: "vetoed", by: d.by }); break;
      case "patched": tl(d.law, { i, kind: "patched", who: e.agent, reason: d.reason, diff: d.diff }); break;
      case "law_error": tl(d.law, { i, kind: "error", error: d.error }); break;
      case "dm": (dmOutAt[`${round}|${e.agent}`] = dmOutAt[`${round}|${e.agent}`] || []).push(i); break;
    }
    switch (e.type) {
      case "post": items.push({ i, round, kind: "post", who: e.agent, text: d.text }); posts.push({ i, who: e.agent, text: d.text }); break;
      case "anon_post": items.push({ i, round, kind: "post", who: anon[e.id] || null, anon: true, text: d.text }); posts.push({ i, who: anon[e.id] || null, anon: true, text: d.text }); break;
      case "channel_post": items.push({ i, round, kind: "post", who: e.agent, channel: d.channel, text: d.text }); break;
      case "story": items.push({ i, round, kind: "media", who: e.agent, label: "Front page", head: d.headline, text: d.text }); break;
      case "digest": items.push({ i, round, kind: "media", who: e.agent, label: "Digest", text: d.text }); break;
      case "report": items.push({ i, round, kind: "media", who: e.agent, label: "Report", text: d.text }); break;
      case "edition": items.push({ i, round, kind: "media", who: e.agent, label: d.name || "Edition", head: d.headline, text: d.text }); break;
      case "gazette": items.push({ i, round, kind: "gazette", text: d.text }); break;
      case "turn": if ((d.actions || []).length) items.push({ i, round, kind: "turn", who: e.agent, acts: d.actions, res: d.results || [] }); break;
      case "proposal": items.push({ i, round, kind: "proposal", who: e.agent, law: d.law, title: d.title, intent: d.intent, cls: d.class, code: d.code, preview: d.preview }); break;
      case "enact": items.push({ i, round, kind: "law", act: "enacted", who: e.agent, law: d.law, title: d.title, cls: d.class });
        lawEvents.push({ i, act: "enact", law: d.law, title: d.title, cls: d.class, author: e.agent }); break;
      case "repeal": items.push({ i, round, kind: "law", act: "repealed", law: d.law, title: (laws.get(d.law) || {}).title });
        lawEvents.push({ i, act: "repeal", law: d.law }); break;
      case "world_event": items.push({ i, round, kind: "world", text: d.text, truth: rumor[d.event], vis: e.vis }); break;
      case "ballot_close": items.push({ i, round, kind: "ballot", ballot: d.ballot }); break;
      case "dm": dms.push({ i, round, from: e.agent, to: d.to, text: d.text, enc: d.encrypted, shownAs: d.shown_as, shownTo: d.shown_to,
        forged: forged[e.id], pay: d.payment }); break;
      default:
        if (e.vis === "public" && (PUBLIC_SYS.has(e.type) || e.type.startsWith("project") || e.type.startsWith("tribute") || e.type.startsWith("raid")))
          items.push({ i, round, kind: "sys", type: e.type, who: e.agent, data: d });
    }
  });
  // private reasoning, at the turn it belongs to
  const reas = new Map();
  for (const x of D.reasoning || []) {
    const key = `${x.round}|${x.agent}`, dm = String(x.phase || "").startsWith("dm");
    let i = dm ? (dmOutAt[key] || []).slice(-1)[0] : turnAt[key];
    if (i === undefined) i = turnAt[key] ?? roundEnd[x.round] ?? events.length - 1;
    push(reas, x.agent, { ...x, i, dm });
  }
  // conversations: one per pair (true sender and recipient), with per-side notes for forgeries
  const convs = new Map();
  for (const m of dms) {
    const k = [m.from, m.to].sort().join("|");
    if (!convs.has(k)) convs.set(k, { key: k, a: [m.from, m.to].sort()[0], b: [m.from, m.to].sort()[1], msgs: [] });
    convs.get(k).msgs.push(m);
  }
  // round headlines: structured, rendered by the views
  const heads = [];
  const H = (r) => (heads[r] = heads[r] || { items: [], posts: 0, dms: 0, votes: 0, harvests: 0 });
  events.forEach((e, i) => {
    const r = roundAt[i], d = e.data || {}, t = e.type;
    if (t === "post" || t === "anon_post") H(r).posts++;
    else if (t === "dm") H(r).dms++;
    else if (t === "vote") H(r).votes++;
    else if (t === "harvest") H(r).harvests++;
    else if (t === "enact" && e.agent !== "constitution") H(r).items.push({ i, k: "enacted", law: d.law, title: d.title, who: e.agent });
    else if (t === "repeal") H(r).items.push({ i, k: "repealed", law: d.law });
    else if (t === "vetoed") H(r).items.push({ i, k: "vetoed", law: d.law });
    else if (t === "raid") H(r).items.push({ i, k: "raid", camp: d.camp });
    else if (t === "departure" || t === "disabled") H(r).items.push({ i, k: "left", who: d.agent || e.agent, cause: d.cause || t });
    else if (t === "arrival" || t === "agent_arrives") H(r).items.push({ i, k: "arrived", who: d.agent || e.agent });
    else if (t === "bank_run") H(r).items.push({ i, k: "bank_run", cur: d.currency });
    else if (t === "tribute_demand") H(r).items.push({ i, k: "tribute" });
    else if (t === "world_event") H(r).items.push({ i, k: "world", text: d.text });
  });
  const snapBy = new Map(snaps.map((s) => [s.round, s]));
  const lastRound = Math.max(0, ...events.map((e) => e.round || 0));
  const S = { inst, truth, events, snaps, snapBy, score, agents, A, items, dms, convs, lawEvents, laws, lawTL, roundAt, roundEnd, roundStart,
    lastRound, turns, reas, lookups, gchanges, departs, arrives, transfers, harvests, ballots, posts, heads,
    rounds: inst.rounds || lastRound + 1, name: D.name || inst.run_id || "run" };
  S.titleLaw = new Map();
  for (const [id, l] of laws) if (l.title && l.title.length >= 6 && (!S.titleLaw.has(l.title) || l.enacted != null)) S.titleLaw.set(l.title, id);
  return S;
}

// ------------------------------------------------------------------ queries over the model
// value at the start of round r (the snapshot after round r-1); round 0 = starting values
export function valueAt(S, id, r) {
  if (r <= 0) return (S.truth.start_values || {})[id];
  const s = S.snapBy.get(r - 1); return s ? (s.values || {})[id] : undefined;
}
// the state after round r (what the world looked like when round r ended)
export const snapAfter = (S, r) => S.snapBy.get(r) || null;
export function moodAt(S, id, r) {
  if (S.departs.has(id) && S.roundAt[S.departs.get(id)] <= r) return "gone";
  const v1 = valueAt(S, id, r + 1), v0 = valueAt(S, id, r);
  if (v1 == null || v0 == null || !v0) return "ok";
  return v1 > v0 * 1.04 ? "happy" : v1 < v0 * 0.96 ? "sad" : "ok";
}
export function lawsInForce(S, idx) {
  const active = new Map();
  for (const l of S.lawEvents) { if (l.i > idx) break; if (l.act === "enact") active.set(l.law, l); else active.delete(l.law); }
  for (const [id, x] of S.lawTL) for (const e of x) if (e.kind === "vetoed" && e.i <= idx) active.delete(id);
  return active;
}
export function lawStatus(S, id, idx = Infinity) {
  let st = "proposed";
  for (const x of S.lawTL.get(id) || []) {
    if (x.i > idx) break;
    st = { proposed: "proposed", ballot: "on the ballot", enacted: "in force", veto_window: "in force", vetoed: "vetoed", repealed: "repealed" }[x.kind] || st;
  }
  for (const b of S.ballots.values()) if (b.law === id && b.close !== undefined && b.close <= idx && b.result !== "yes" && st === "on the ballot") st = "rejected";
  return st;
}
export function regimeOf(snap) {
  if (!snap) return "";
  const d = (snap.decisive_set || []).length, f = snap.franchise_share ?? 0;
  return d === 0 ? "anarchy" : d === 1 ? "dictatorship" : f >= 0.5 ? "democracy" : "oligarchy";
}
export function parseGoalText(t) {
  const re = /(Primary|Secondary|Tertiary|Third) goal \((\d+)%(?: of your score)?\):\s*/g, out = []; let m, last = null;
  const L = { primary: "primary", secondary: "secondary", tertiary: "tertiary", third: "tertiary" };
  while ((m = re.exec(t))) { if (last) last.text = t.slice(last.end, m.index).trim(); last = { label: L[m[1].toLowerCase()], pct: +m[2], end: re.lastIndex }; out.push(last); }
  if (last) last.text = t.slice(last.end).trim();
  if (!out.length && t) out.push({ label: "primary", pct: 100, text: t });
  return out;
}
export function guessStats(S) {
  const out = {}, G = S.truth.guesses || {}, goals = S.truth.goals || {};
  for (const [guesser, gs] of Object.entries(G)) for (const [target, guess] of Object.entries(gs || {})) {
    const real = (goals[target] || {}).primary; if (!real) continue;
    const o = out[target] = out[target] || { right: 0, total: 0, by: [] }; o.total++; if (guess === real) { o.right++; o.by.push(guesser); }
  }
  return out;
}
export function gini(vs) {
  const x = vs.filter((v) => v >= 0).sort((a, b) => a - b), n = x.length, s = x.reduce((a, b) => a + b, 0);
  if (!n || !s) return 0;
  return x.reduce((acc, v, i) => acc + (2 * (i + 1) - n - 1) * v, 0) / (n * s);
}
export function series(S, f) { const out = []; for (let k = 0; k <= S.lastRound; k++) { const s = S.snapBy.get(k); out.push(s ? f(s) : null); } return out; }
export const citizens = (S) => S.agents.filter((a) => a.cls !== "observer");
export function goalScore(S, id) { return ((S.score.goals || {})[id] || {}).score; }
export function contacts(S, id, idx = Infinity) {
  const rel = new Map(), get = (p) => { if (!rel.has(p)) rel.set(p, { out: 0, in: 0, tx: 0, rx: 0 }); return rel.get(p); };
  for (const m of S.dms) { if (m.i > idx) break; if (m.from === id) get(m.to).out++; else if (m.to === id) get(m.from).in++; }
  for (const t of S.transfers) { if (t.i > idx) break; if (t.from === id && S.A.has(t.to)) get(t.to).tx++; else if (t.to === id && S.A.has(t.from)) get(t.from).rx++; }
  return [...rel.entries()].filter(([p]) => S.A.has(p)).sort((x, y) => (y[1].out + y[1].in + 2 * (y[1].tx + y[1].rx)) - (x[1].out + x[1].in + 2 * (x[1].tx + x[1].rx)));
}

// what a law hooks into, read from its code (stubs that only pass or return 0 are ignored)
const HOOKS = [["on_harvest", "acts on every harvest"], ["on_transfer", "acts on every transfer"], ["on_round_start", "runs each round's start"],
  ["on_round_end", "runs each round's end"], ["on_post", "reads public posts"], ["on_dm", "reads private messages"], ["on_vote", "watches votes"],
  ["on_propose", "watches proposals"], ["on_enact", "acts once when enacted"], ["on_repeal", "acts when repealed"], ["on_loan", "watches loans"]];
const CALLS = [[/set_procedure|electorate/, "changes who votes or how laws pass"], [/create_currency|mint\(/, "creates or mints money"],
  [/grant_right|revoke_right|set_right|grant\(|revoke\(/, "grants or removes rights"], [/\bfine\(|sanction\(/, "fines or sanctions"],
  [/hide_post/, "can hide posts"], [/unhide_post/, "reveals hidden posts"], [/enable_loans/, "enables loans"], [/set_dm_limit/, "changes the message limit"],
  [/set_quota|harvest_limit|quota/, "limits harvesting"], [/pay\(|give\(|move\(/, "moves resources"], [/burn\(/, "burns money"], [/entrench/, "entrenches itself"]];
export function lawDoes(code) {
  if (!code) return [];
  const out = [], fns = {};
  const re = /^def\s+(\w+)\s*\([^)]*\)\s*:\s*\n((?:[ \t]+.*\n?|[ \t]*\n)*)/gm;
  let m; while ((m = re.exec(code + "\n"))) fns[m[1]] = m[2].split("\n").map((s) => s.trim()).filter(Boolean);
  const stub = (b) => b.every((l) => /^(pass|return( 0(\.0)?| None| qty| y)?|#.*)$/.test(l));
  for (const [f, label] of HOOKS) if (fns[f] && !stub(fns[f])) out.push(label);
  for (const [r, label] of CALLS) if (r.test(code)) out.push(label);
  return [...new Set(out)];
}
