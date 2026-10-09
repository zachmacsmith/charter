// charter-data.js: read published Charter runs in the browser, straight from the Hugging Face dataset (docs/data_format.md).
//
//   import { openDataset } from "./charter-data.js";
//   const ds = await openDataset({ repo: "zachmacsmith/charter-runs" });
//   const runs = await ds.catalog();                       // one row per published run (catalog.json)
//   const run = ds.run(runs[0]);                           // lazy: nothing is fetched until a table is asked for
//   const chans = await run.channels();                    // [{channel_id, channel_kind, name, members, n_messages, ...}]
//   const thread = await run.thread("dm:Bjorn|Kasper");    // messages of one conversation, in log order
//   const inbox = await run.inbox("Bjorn");                // the channels Bjorn could see, newest first
//   const diary = await run.turns("Bjorn");                // Bjorn's turns: reasoning, notes, actions, results
//
// Every file URL is pinned to one dataset commit (resolve/<sha>/...), so the browser may cache it forever; within a page each
// table is fetched once. Tables follow export schema 2; missing tables are empty and unknown columns are ignored, as the format
// promises. Runs exported before schema 2 (no messages/channels tables) get messages and channels derived from `events` here.
import { asyncBufferFromUrl, parquetReadObjects } from "https://cdn.jsdelivr.net/npm/hyparquet@1.31.3/+esm";

const HF = "https://huggingface.co";

export async function openDataset({ repo = "zachmacsmith/charter-runs", revision = "main", base = null } = {}) {
  // base: serve the dataset from another URL (a local copy while developing); then no revision lookup happens
  let root = base;
  if (!root) {
    const sha = await resolveRevision(repo, revision);
    root = `${HF}/datasets/${repo}/resolve/${sha}`;
  }
  const json = memo(async (path) => (await fetchOk(`${root}/${path}`)).json());
  return {
    root,
    catalog: async () => (await json("catalog.json")).runs,
    run: (entry) => openRun(root, typeof entry === "string" ? entry : entry.path, json),
  };
}

async function resolveRevision(repo, revision) {
  const key = `charter-sha:${repo}:${revision}`;
  try { const hit = sessionStorage.getItem(key); if (hit) return hit; } catch (e) {}
  const r = await fetchOk(`${HF}/api/datasets/${repo}/revision/${encodeURIComponent(revision)}`);
  const sha = (await r.json()).sha;
  try { sessionStorage.setItem(key, sha); } catch (e) {}
  return sha;
}

function openRun(root, path, json) {
  const manifest = memo(() => json(`${path}/manifest.json`));
  const card = memo(() => json(`${path}/card.json`).catch(() => ({})));
  const table = memo(async (name) => {
    const m = await manifest();
    if (!m.tables || !m.tables[name]) return [];                       // a table this run's export does not have: empty
    const file = await asyncBufferFromUrl({ url: `${root}/${path}/${m.tables[name].file}` });
    return parquetReadObjects({ file });
  });

  const messages = memo(async () => {
    const t = await table("messages");
    if (t.length) return t.map(parseJsonCols);
    return deriveMessages(await table("events"));                     // schema 1 runs
  });
  const channels = memo(async () => {
    const t = await table("channels");
    if (t.length) return t.map(parseJsonCols).map((c) => ({ ...c, members: c.members_json || null }));
    return deriveChannels(await messages());
  });
  const byChannel = memo(async () => groupBy(await messages(), (m) => m.channel_id));

  return {
    path,
    manifest, card, table,
    agents: memo(async () => (await table("agents")).map(parseJsonCols)),
    laws: memo(async () => (await table("laws")).map(parseJsonCols)),
    messages, channels,
    async thread(channelId) {
      return ((await byChannel()).get(channelId) || []).slice().sort((a, b) => num(a.seq) - num(b.seq));
    },
    async inbox(agent) {
      const chans = await channels();
      const mine = chans.filter((c) => c.channel_kind === "public" || c.channel_kind === "gazette" || c.channel_kind === "outlet"
        || (Array.isArray(c.members) && c.members.includes(agent)));
      return mine.sort((a, b) => num(b.last_round) - num(a.last_round));
    },
    async turns(agent) {
      const t = (await table("turns")).map(parseJsonCols);
      return (agent ? t.filter((r) => r.agent === agent) : t).sort((a, b) => num(a.round) - num(b.round) || num(a.position) - num(b.position));
    },
  };
}

// ------------------------------------------------------------------ schema-1 fallback (runs exported before messages/channels)
const MESSAGE_TYPES = new Set(["dm", "reply", "post", "anon_post", "channel_post", "story", "report", "digest", "edition",
  "gazette", "notify", "submission"]);

function deriveMessages(events) {
  const out = [];
  for (const e of events) {
    if (!MESSAGE_TYPES.has(e.type)) continue;
    const data = parse(e.data_json) || {};
    const recips = parse(e.recipients_json);
    const sender = e.agent || null;
    let id, kind;
    if (e.type === "dm" || e.type === "reply") {
      const to = data.to || e.data_to;
      id = `dm:${[sender, to].filter(Boolean).sort().join("|")}`; kind = "dm";
    } else if (e.type === "channel_post" && data.channel) { id = `ch:${data.channel}`; kind = "channel"; }
    else if (e.type === "edition") { id = `outlet:${data.outlet || data.name || "press"}`; kind = "outlet"; }
    else if (e.type === "gazette") { id = "gazette:main"; kind = "gazette"; }
    else if (e.type === "notify") { id = "system:notify"; kind = "system"; }
    else if (e.vis_kind === "public" || !recips) { id = "public"; kind = "public"; }
    else if (recips.length === 2) { id = `dm:${recips.slice().sort().join("|")}`; kind = "dm"; }
    else { id = `group:${recips.slice().sort().join("|")}`; kind = "group"; }
    out.push({ run_id: e.run_id, msg_id: e.event_id, seq: num(e.seq), round: num(e.round), type: e.type, channel_id: id,
      channel_kind: kind, sender, anonymous: e.type === "anon_post", audience: e.vis_kind, recipients_json: recips,
      title: data.title || null, text: data.text || null, encrypted: !!data.encrypted, reply_to: data.reply_to || null,
      data_json: data });
  }
  return out;
}

function deriveChannels(messages) {
  const out = [];
  for (const [id, ms] of groupBy(messages, (m) => m.channel_id)) {
    const senders = new Set(ms.map((m) => m.sender).filter(Boolean));
    const members = id.startsWith("dm:") || id.startsWith("group:") ? id.split(":")[1].split("|") : null;
    out.push({ channel_id: id, channel_kind: ms[0].channel_kind, channel_source: "derived",
      name: members ? members.join(" & ") : id, members, n_messages: ms.length, n_senders: senders.size,
      first_round: Math.min(...ms.map((m) => m.round)), last_round: Math.max(...ms.map((m) => m.round)) });
  }
  return out.sort((a, b) => b.n_messages - a.n_messages);
}

// ------------------------------------------------------------------ small helpers
function memo(fn) {
  const cache = new Map();
  return (...args) => {
    const k = JSON.stringify(args);
    if (!cache.has(k)) cache.set(k, fn(...args).catch((err) => { cache.delete(k); throw err; }));
    return cache.get(k);
  };
}
async function fetchOk(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r;
}
function parse(v) { if (v == null || typeof v !== "string") return v ?? null; try { return JSON.parse(v); } catch (e) { return null; } }
function parseJsonCols(row) {
  const out = { ...row };
  for (const k of Object.keys(out)) if (k.endsWith("_json")) out[k] = parse(out[k]);
  for (const k of Object.keys(out)) if (typeof out[k] === "bigint") out[k] = Number(out[k]);
  return out;
}
function num(v) { return typeof v === "bigint" ? Number(v) : (v ?? 0); }
function groupBy(xs, key) {
  const m = new Map();
  for (const x of xs) { const k = key(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); }
  return m;
}
