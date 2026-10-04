"""Readable report for one run folder (works on any run dir; the runner calls it at the end):

  overview.md                   the central round-by-round account of what happened
  spec_outline.md               the resolved spec, every seed and derived RNG seed, every random draw (world, agents, camps,
                                turn orders, harvest noise), the constitution, and the shared archive at start
  agents/<Name>/transcript.md   per turn: the prompt the agent saw, its private reasoning, its actions and their results, its notes
  agents/<Name>/working/        the agent's working documents: notes over time, sandbox code and output, law drafts and their fate,
                                archive reads/writes, messages and transfers, harvest log
Raw data stays alongside: instance.json, events.jsonl, reasoning.jsonl, snapshots.json, ground_truth.json, score.json, summary.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml


def _load(d: Path):
    inst = json.loads((d / "instance.json").read_text())
    ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()] if (d / "events.jsonl").exists() else []
    rs = [json.loads(l) for l in (d / "reasoning.jsonl").read_text().splitlines() if l.strip()] if (d / "reasoning.jsonl").exists() else []
    snaps = json.loads((d / "snapshots.json").read_text()) if (d / "snapshots.json").exists() else []
    gt = json.loads((d / "ground_truth.json").read_text()) if (d / "ground_truth.json").exists() else {}
    score = json.loads((d / "score.json").read_text()) if (d / "score.json").exists() else None
    return inst, ev, rs, snaps, gt, score


def _q(text, n=None):
    t = str(text if n is None else str(text)[:n])
    return "\n".join("> " + ln if ln else ">" for ln in t.splitlines()) or "> (empty)"


def _cut(text, n=220):
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n] + "..."


# ------------------------------------------------------------------ spec outline
def spec_outline(d, inst, ev, gt):
    seed = inst["seed"]
    sp = inst["spec"]
    L = [f"# Spec outline: {d.name}", "",
         "## Seeds and random-number streams",
         f"- Instance seed: **{seed}** (drives every draw below through `random.Random({seed})` in the generator).",
         f"- Kernel RNG (turn orders, harvest noise): `random.Random({seed * 7919 + 17})` = seed x 7919 + 17.",
         f"- Law RNG (rng() inside laws, e.g. the Chair or Council draw): `random.Random({seed * 104729 + 3})` = seed x 104729 + 3.",
         f"- Scripted-bot RNG (dry runs only): `random.Random({seed})`. Model sampling is not seeded (model calls are not deterministic).",
         f"- Run id: {inst.get('run_id', '-')}. Library access: {inst['library_access']}. Repairs by the validator: {inst.get('repairs') or 'none'}.",
         f"- Unreachable goals (allowed): {inst.get('unreachable_goals') or 'none'}.", "",
         "## World draws",
         f"- Constitution: **{inst['constitution']}**; law level **{inst['law_level']}**; rounds **{inst['rounds']}**.",
         f"- Endowment Gini target: {inst['endowment_gini_target']:.3f}.",
         f"- Conditions: {json.dumps(inst['conditions'])}", "",
         "## Camps (hidden functions included: agents never see these)", "",
         "| camp | tier | resource | family | K | start stock | r | noise sigma | best attainable f | parameters |", "|---|---|---|---|---|---|---|---|---|---|"]
    for c in inst["camps"]:
        L.append(f"| {c['id']} | {c['tier']} | {c['resource']} | {c['fn']['family']} | {c['K']} | {c['S']:.1f} | {c['r']:.3f} | {c['sigma']:.3f} | "
                 f"{c.get('norm', 1):.3f} | `{json.dumps(c['fn'])[:300]}` |")
    L += ["", "## Agents", "", "| agent | class | model (tier) | actions/turn | start rights | endowment | goal | secondary | third | personality |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for a in inst["agents"]:
        g = a["goal"]
        goal = g["primary"] + (f" {json.dumps(g.get('params'))}" if g.get("params") else "") + ("" if g.get("reachable", True) else " (unreachable)")
        sec = (g.get("secondary") or "") + (f" {json.dumps(g.get('secondary_params'))}" if g.get("secondary_params") else "")
        ter = (g.get("tertiary") or "") + (f" {json.dumps(g.get('tertiary_params'))}" if g.get("tertiary_params") else "")
        pers = ", ".join(f"{k} {v:.2f}" for k, v in (a.get("personality") or {}).items())
        L.append(f"| {a['id']} | {a['cls']} | {a['model']} ({a['tier']}) | {a['actions']} | {', '.join(a['rights']) or '-'} | "
                 f"{json.dumps(a['endowment'])} | {goal} | {sec} | {ter} | {pers} |")
    scis = [a for a in inst["agents"] if a.get("archive_docs")]
    if scis:
        L += ["", "## Archive split between Scientists", ""] + [f"- {a['id']} ({len(a['archive_docs'])} documents): {', '.join(a['archive_docs'])}" for a in scis]
    L += ["", "## Turn orders (drawn by the kernel RNG each round)", ""]
    for e in ev:
        if e["type"] == "round_start":
            L.append(f"- Round {e['data']['round'] + 1}: {', '.join(e['data']['order'])}")
    harv = [e for e in ev if e["type"] == "harvest"]
    if harv:
        L += ["", "## Harvest noise draws", "", "| round | agent | camp | x | stock before | efficiency | noise | yield |", "|---|---|---|---|---|---|---|---|"]
        for e in harv:
            x = e["data"]
            L.append(f"| {e['round'] + 1} | {e['agent']} | {x['camp']} | {x['x']} | {x.get('stock_before', '')} | {x['efficiency']} | {x.get('noise', '')} | {x['yield']:.3f} |")
    L += ["", "## Starting constitution", "", "```python", inst["constitution_code"].strip(), "```", "",
          "## Library visible in this world", "", ", ".join(inst["library"]) or "none", "",
          "## Shared archive at start", "", "```json", json.dumps(gt.get("shared_archive_at_start", {}), indent=1), "```", "",
          "## Resolved spec", "", "```yaml", yaml.safe_dump(sp, sort_keys=False, default_flow_style=None).strip(), "```"]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ overview
def overview(d, inst, ev, rs, snaps, gt, score, status=None):
    by_round = defaultdict(list)
    for e in ev:
        by_round[e["round"]].append(e)
    errors = defaultdict(int)
    for r in rs:
        errors[r["round"]] += sum(1 for x in r["results"] if ": ERROR " in x)
    snap = {s["round"]: s for s in snaps}
    agents = {a["id"]: a for a in inst["agents"]}
    L = [f"# Run overview: {d.name}", "",
         f"{len(agents)} agents ({', '.join(f'{n} {c}' for c, n in sorted(_count(a['cls'] for a in inst['agents']).items()))}), "
         f"{inst['rounds']} rounds, constitution **{inst['constitution']}**, law level **{inst['law_level']}**, "
         f"camps {', '.join(c['id'] + ' (' + c['resource'] + ')' for c in inst['camps'])}. Seed {inst['seed']}. "
         f"Models: {', '.join(sorted({a['model'] for a in inst['agents']}))}.", "",
         "Files: [messages.md](messages.md) (every message and post, untruncated), [spec_outline.md](spec_outline.md) (seeds and every random draw), "
         "`agents/<Name>/transcript.md`, `agents/<Name>/working/`.", ""]
    if status:
        L[1:1] = ["", f"**In progress: {status}.** This page updates after every turn; transcripts and working documents update every round.", ""]
    if score:
        s = score["summary"]
        L += ["## Outcome", "",
              f"- Regime at the end: **{s['regime_final']}** (decisive set {s['decisive_set_final']}, franchise share {s['franchise_final']:.2f}); regime changes: {s['regime_changes']}.",
              f"- Laws enacted: {s['laws_enacted']} of {s['laws_proposed']} proposed; currency adopted: {s['currency_adopted']}; vetoes: {s['vetoes']}.",
              f"- Welfare change: {s['welfare_change']}; lowest stock: {s['lowest_stock']}; holdings Gini at end: {s['holdings_gini_end']}; power Gini: {s['power_gini']}.",
              f"- Corruption candidates: {s['corruption_candidates']}; knowledge transfers: {s['knowledge_transfers']}; archive leaks: {s['archive_leaks']}.",
              "", "| agent | class | goal | score |", "|---|---|---|---|"]
        for aid, g in score["goals"].items():
            L.append(f"| {aid} | {agents[aid]['cls']} | {g['goal']} | {g['score']} |")
        L.append("")
    L.append("## Round by round")
    for r in sorted(by_round):
        es = by_round[r]
        order = next((e["data"]["order"] for e in es if e["type"] == "round_start"), [])
        L += ["", f"### Round {r + 1}", "", f"Order: {', '.join(order)}"]
        harv = [e for e in es if e["type"] == "harvest"]
        if harv:
            tot = defaultdict(float)
            for e in harv:
                tot[e["data"]["camp"]] += e["data"]["yield"]
            L.append(f"- Harvests: {len(harv)} ({', '.join(f'{c} {v:.2f}' for c, v in tot.items())} units)")
        for e in es:
            t, x, who = e["type"], e["data"], e["agent"]
            line = None
            if t == "post":
                line = f"- {who} posted: \"{_cut(x['text'])}\""
            elif t == "anon_post":
                line = f"- Anonymous posted: \"{_cut(x['text'])}\""
            elif t in ("post_hidden", "post_revealed", "channel_member", "channel_closed", "channel_created"):
                line = f"- {t.replace('_', ' ')}: {_cut(json.dumps(x), 160)}"
            elif t == "dm":
                line = f"- DM {who} -> {x['to']}{' (encrypted)' if x.get('encrypted') else ''}: \"{_cut(x['text'], 160)}\""
            elif t == "channel_post":
                line = f"- #{x['channel']} {who}: \"{_cut(x['text'], 160)}\""
            elif t == "transfer":
                line = f"- Transfer {who} -> {x['to']}: {x['qty']:g} {x['item']}" + (f" (tax {x['tax']:g})" if x.get("tax") else "")
            elif t == "proposal":
                line = f"- **Proposal** {x['law']} '{x['title']}' ({x['class']}) by {who}. Intent: {_cut(x['intent'], 160)}"
            elif t == "proposal_check_failed":
                line = f"- Proposal by {who} failed the dry run: {_cut(x['error'], 160)}"
            elif t == "ballot_close":
                line = f"- Ballot {x['ballot']} closed: **{x['result']}** (votes {json.dumps(x['votes'])})"
            elif t == "enact":
                line = f"- **Enacted** {x['law']} '{x['title']}' ({x['class']})"
            elif t in ("repeal", "vetoed", "law_error", "patched", "patch_submitted", "request_fix", "case_dismissed", "rename", "sanction", "censure"):
                line = f"- {t.replace('_', ' ')}: {_cut(json.dumps({k: v for k, v in x.items() if k not in ('diff', 'code')}), 200)}"
            elif t == "veto_window":
                line = f"- {x['law']} enters the Board's veto window (until round {x['until'] + 1})"
            elif t in ("story", "digest", "report"):
                line = f"- Media {t} by {who}: \"{_cut(x.get('headline', '') + ' ' + x['text'], 200)}\""
            elif t == "accuse":
                line = f"- Accusation {x['case']}: {who} v {x['accused']} under {x['clause']}"
            elif t == "ruling":
                line = f"- Ruling {x['case']}: **{x['verdict']}** by {who}: {_cut(x['reason'], 160)}"
            elif t in ("archive_read", "archive_search", "archive_write"):
                line = f"- Archive {t.split('_')[1]} by {who}: {x.get('doc') or x.get('query')}"
            elif t == "sandbox":
                line = f"- {who} ran sandbox code ({len(x['code'])} chars)"
            elif t in ("deposit", "redeem"):
                line = f"- {who} {t}: {_cut(json.dumps(x), 160)}"
            elif t.startswith("loan_") and t != "loan_offer" or t in ("bank_run", "redemption_suspended", "redemption_resumed", "par_set",
                                                                       "interest_cap", "default_consequence"):
                line = f"- {'**' + t.replace('_', ' ') + '**' if t in ('bank_run', 'redemption_suspended') else t.replace('_', ' ')}" \
                       f"{' ' + who if who else ''}: {_cut(json.dumps(x), 160)}"
            elif t == "gazette" and not str(x["text"]).startswith("Round "):
                line = f"- Gazette: {_cut(x['text'], 200)}"
            if line:
                L.append(line)
        if errors.get(r):
            L.append(f"- Rejected actions this round: {errors[r]} (see transcripts)")
        s = snap.get(r)
        if s:
            stocks = ", ".join(f"{c} {v:.0%}" for c, v in s["stocks"].items())
            prices = ", ".join(f"{c} P={p:.3f}" for c, p in s["prices"].items()) or "no currency"
            L.append(f"- End of round: stocks {stocks}; {prices}; laws in force {len(s['laws_active'])}; decisive set {len(s['decisive_set'])} "
                     f"({', '.join(s['decisive_set'])}); franchise {s['franchise_share']:.2f}; welfare {s.get('welfare', 0):.1f}")
    return "\n".join(L) + "\n"


def _count(xs):
    out = defaultdict(int)
    for x in xs:
        out[x] += 1
    return out


# ------------------------------------------------------------------ per agent
def agent_docs(d, inst, ev, rs, gt):
    root = d / "agents"
    for a in inst["agents"]:
        aid = a["id"]
        ad = root / aid
        wd = ad / "working"
        wd.mkdir(parents=True, exist_ok=True)
        turns = sorted((r for r in rs if r["agent"] == aid),
                       key=lambda r: (r["round"], int(str(r.get("phase") or "decide").rpartition("_")[2] or 0) if str(r.get("phase", "")).startswith("dm_reply") else 0))
        sysp = (d / "prompts" / f"{aid}.system.md")
        T = [f"# {aid}: transcript", "",
             f"Class {a['cls']}, model {a['model']} ({a['tier']}), {a['actions']} actions per turn. Goal: {a['goal'].get('text') or a['goal']['primary']}.",
             f"Personality: {a.get('personality_text') or '-'}", ""]
        if sysp.exists():
            T += ["<details><summary>System prompt</summary>", "", "```", sysp.read_text().strip(), "```", "", "</details>", ""]
        for t in turns:
            ph = str(t.get("phase") or "decide")
            T += [f"## Round {t['round'] + 1}, position {t['position']}" if ph == "decide" else
                  f"### Round {t['round'] + 1}: reply to DMs (exchange {ph.rpartition('_')[2]})", ""]
            if t.get("prompt"):
                T += ["<details><summary>What the agent saw</summary>", "", "```", t["prompt"].strip(), "```", "", "</details>", ""]
            if t.get("reasoning"):
                T += ["**Chain of thought (native thinking, private)**", "", _q(t["reasoning"]), ""]
            else:
                T += ["_No native thinking returned for this turn (see the README on which models return it)._", ""]
            if t.get("stated_reasoning"):
                T += ["**Stated reasoning (written in the reply, private)**", "", _q(t["stated_reasoning"]), ""]
            T += ["**Actions**", ""] + [f"- `{x.get('action')}` {x.get('args_json', '')}" for x in t["actions"]] + [""]
            if t.get("final_actions") is not None:
                T += ["**Plan carried out (after replying to DMs)**", ""] + [f"- `{x.get('action')}` {x.get('args_json', '')}" for x in t["final_actions"]] + [""]
            if ph == "decide":
                T += ["**Results** (the whole round, including DMs sent while replying)" if t.get("final_actions") is not None else "**Results**", ""] \
                    + [f"- {_cut(x, 600)}" for x in t["results"]] + [""]
            T += ["**Notes to self**", "", _q(t.get("notes") or "(none)"), ""]
            if t.get("error"):
                T += [f"_Reply error: {t['error']}_", ""]
        (ad / "transcript.md").write_text("\n".join(T) + "\n")

        (wd / "notes.md").write_text(f"# {aid}: notes over time\n\n" + "\n\n".join(
            f"## Round {t['round'] + 1}\n\n{t.get('notes') or '(none)'}" for t in turns if (t.get("phase") or "decide") == "decide") + "\n")
        mine = [e for e in ev if e["agent"] == aid]
        sb = [e for e in mine if e["type"] == "sandbox"]
        if sb:
            (wd / "sandbox.md").write_text(f"# {aid}: sandbox sessions\n\n" + "\n\n".join(
                f"## Round {e['round'] + 1} ({e['id']})\n\n```python\n{e['data']['code']}\n```\n\nOutput:\n\n```\n{e['data']['output']}\n```" for e in sb) + "\n")
        laws = [l for l in gt.get("laws", {}).values() if l.get("author") == aid]
        if laws:
            (wd / "laws.md").write_text(f"# {aid}: law drafts and their fate\n\n" + "\n\n".join(
                f"## {l['id']} '{l['title']}' ({l['cls']}): {l['status']}\n\nIntent: {l['intent']}\n\nProposed round {l['proposed_round'] + 1}"
                + (f", enacted round {l['enacted_round'] + 1}" if l.get("enacted_round") is not None else "")
                + (f"\n\nEffect preview: {'; '.join(l['preview'][:30])}" if l.get("preview") else "")
                + f"\n\n```python\n{l['code']}\n```" for l in laws) + "\n")
        arch = [e for e in mine if e["type"].startswith("archive_")]
        if arch:
            (wd / "archive.md").write_text(f"# {aid}: archive use\n\n" + "\n".join(
                f"- Round {e['round'] + 1} {e['type'].split('_')[1]}: {e['data'].get('doc') or e['data'].get('query')}"
                + (f"\n\n```\n{e['data']['text'][:6000]}\n```\n" if e["type"] == "archive_write" else "") for e in arch) + "\n")
        msgs = [e for e in ev if (e["type"] in ("dm", "transfer") and (e["agent"] == aid or e["data"].get("to") == aid))
                or (e["type"] in ("post", "story", "digest", "report", "channel_post") and e["agent"] == aid)]
        if msgs:
            (wd / "messages.md").write_text(f"# {aid}: messages, posts and transfers\n\n" + "\n".join(
                f"- r{e['round'] + 1} {e['type']} {e['agent']}" + (f" -> {e['data']['to']}" if e["data"].get("to") else "") + ": "
                + (_cut(e["data"].get("text", ""), 1000) if e["type"] != "transfer" else f"{e['data']['qty']:g} {e['data']['item']}") for e in msgs) + "\n")
        hv = [e for e in mine if e["type"] == "harvest"]
        if hv:
            (wd / "harvests.md").write_text(f"# {aid}: harvest log\n\n| round | camp | x | yield | efficiency |\n|---|---|---|---|---|\n" + "\n".join(
                f"| {e['round'] + 1} | {e['data']['camp']} | {e['data']['x']} | {e['data']['yield']:.3f} | {e['data']['efficiency']} |" for e in hv) + "\n")


MESSAGE_TYPES = ("post", "anon_post", "dm", "channel_post", "story", "digest", "report", "gazette", "notify", "channel_created",
                 "post_hidden", "post_revealed")


def messages(d, inst, ev):
    """Every message and post, untruncated, in order (the monitors' view: encrypted DMs and anonymous authors included)."""
    L = [f"# All messages: {d.name}", "",
         "Every public post, DM (encrypted ones marked), channel post, Media item, gazette entry and private notice, in order, untruncated. "
         "This is the monitors' view: anonymous posts show their true author and hidden posts are marked.", ""]
    cur = None
    anon = {e["data"]["event"]: e["data"]["author"] for e in ev if e["type"] == "anon_truth"}
    hidden = {e["data"]["event"] for e in ev if e["type"] == "post_hidden"} - {e["data"]["event"] for e in ev if e["type"] == "post_revealed"}
    for e in ev:
        if e["type"] not in MESSAGE_TYPES:
            continue
        if e["round"] != cur:
            cur = e["round"]
            L += ["", f"## Round {cur + 1}", ""]
        x, who, t = e["data"], e["agent"], e["type"]
        head = f"**[{e['id']}]**" + (" (HIDDEN)" if e["id"] in hidden else "")
        if t == "post":
            body = f"{head} {who} (public post{', titled ' + x['title'] if x.get('title') else ''}):"
        elif t == "anon_post":
            body = f"{head} Anonymous (public post; true author {anon.get(e['id'], '?')}):"
        elif t == "dm":
            body = f"{head} {who} -> {x['to']} (DM{', encrypted' if x.get('encrypted') else ''}):"
        elif t == "channel_post":
            body = f"{head} {who} in #{x['channel']}:"
        elif t == "story":
            body = f"{head} {who} (Media story) **{x['headline']}**:"
        elif t == "digest":
            body = f"{head} {who} (Media digest):"
        elif t == "report":
            body = f"{head} {who} (Media report on {x['about']}'s post {x['source']}):"
        elif t == "gazette":
            body = f"{head} Gazette{' (' + who + ')' if who else ''}:"
        elif t == "notify":
            body = f"{head} Notice to {x['to']}{' from ' + who if who else ''}:"
        elif t == "channel_created":
            L.append(f"{head} {who} created channel #{x['channel']} (members {', '.join(x['members'])}{', open' if x.get('open') else ''})")
            continue
        elif t in ("post_hidden", "post_revealed"):
            L.append(f"{head} post {x['event']} was {'hidden' if t == 'post_hidden' else 'revealed'}" + (f" by law {x.get('law')}" if x.get("law") else ""))
            continue
        L += [body, "", _q(x.get("text", "")), ""]
    return "\n".join(L) + "\n"


def build(run_dir, status=None) -> Path:
    d = Path(run_dir)
    inst, ev, rs, snaps, gt, score = _load(d)
    (d / "messages.md").write_text(messages(d, inst, ev))
    (d / "spec_outline.md").write_text(spec_outline(d, inst, ev, gt))
    (d / "overview.md").write_text(overview(d, inst, ev, rs, snaps, gt, score, status))
    agent_docs(d, inst, ev, rs, gt)
    return d


def build_overview(run_dir, status=None) -> Path:
    d = Path(run_dir)
    inst, ev, rs, snaps, gt, score = _load(d)
    (d / "overview.md").write_text(overview(d, inst, ev, rs, snaps, gt, score, status))
    (d / "messages.md").write_text(messages(d, inst, ev))
    return d
