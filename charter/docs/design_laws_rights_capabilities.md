# Design: laws, rights, capabilities, permits and technology

Design exploration, 4 Oct 2026. Read-only: no code was changed. Every law sketch below was checked with `charter.lawlang.check`
and `classify` (results in the sketch headers). Functions marked *new* do not exist yet. `check` does not reject unknown names, so
these sketches parse today but would fail at runtime until the functions exist.

## Summary (one page)

**What laws can do today.** The law API (`kernel.Kernel.api_for`, plus `credit.law_api`, `hidden.law_api`, `projects.law_api` and
`outside.law_api`) is strong on four things:
- money: currencies, mint, burn, `move`, par currencies and loans;
- rights over the fixed catalogue (`grant`, `revoke`, `create_right`, `suspend`);
- procedures and ballots (`set_procedure`, `open_ballot`);
- reactions to five event kinds: harvest, transfer, post, vote and ruling (`on_dm` only when `law_reads_dms` is on).

It is weak on four things:
1. **Pricing or gating actions other than harvest.** Only `set_fee` exists, and only for harvests.
2. **Agent-to-agent institutions.** There are no escrow accounts, contracts, rentals or order books. `define_action` covers some
   of this, but only at L4.
3. **World structure.** Laws cannot set the turn order, create channels, see world events or hear appeals.
4. **First-class time-bound offices and permits.** These are emulated with state plus `revoke` in `on_round_end`.

Of the twelve mechanics asked about:
- **Possible today:** interest tax, scheduled elections, offices with terms (emulated), property titles as exclusive harvest rights.
- **Partly possible:** auctions and markets (L4 only), licensing by law, insurance, press regulation, DM taxes (after the fact,
  and only with `law_reads_dms`).
- **Not possible:** pricing any action other than harvest, escrow and contracts between agents, setting the turn order,
  regulating the archive or channels, a court of appeal, and agent-to-agent rental of rights.

**Recommendations**
1. **Add a `rights_model` to the spec.** It maps every action and power to `right`, `capability` or `entrenched`. One kernel gate,
   `Kernel.may(aid, action)`, replaces the scattered checks (`_need`, class checks, ungated actions). `has()` becomes model-aware.
   `grant`, `revoke` and `suspend` refuse capabilities and entrenched entries, as they refuse `ENTRENCHED` today.
   `rights_model: legacy` (the default at first) reproduces today's behaviour exactly, so golden runs stay bit-identical.
2. **Add permits as a kernel object.** A permit is a time-limited, fee-bearing, optionally transferable grant of one right, from
   one issuer to one holder. `has()` = own right OR a valid permit chain. Two safety rules:
   - recursion is bounded by a depth limit (default 2), and the meta-right `license` can never be sublicensed;
   - an exclusive *lease* suspends the issuer's own use, and a non-exclusive *licence* is capped per right, so renting cannot
     multiply harvests.
3. **Add technology as an event type.** It plugs in through `events.register("tech_discovered", ...)`. A discovery does one of
   three things: turns a capability into a legislable right, creates a new capability, or creates a new kernel-defined right and
   action. Discoveries arrive through events or `discovery` projects, and laws react to them in a new `on_tech` hook. Library
   laws on top of this: Patent Act, Licensing Board, Public Domain.
4. **Add six law functions, highest expressiveness first:**
   - `set_action_price` (structural);
   - an `on_action` gate hook (structural);
   - escrow accounts (structural);
   - first-class offices (structural);
   - `on_event` and `on_tech` hooks (read);
   - `appeal`/`reopen_case` (structural).

   `set_turn_order` (procedural) is optional.
5. **Keep these in the kernel, never in law:** logging and monitor visibility, conservation of resources, the Board, the Fixer,
   step limits, static classification, the dry run, the DM ceiling, encryption secrecy, and the Scientists' archive split.

**Behaviour changes to flag** (all avoided under `legacy`):
- `vote` checks ballot membership, not the `vote` right. Regimes that put non-holders in the electorate depend on this.
- Today a law can `create_right("forge")` and grant it, which unlocks `forge_dm` (`actions._forge_dm`). This is a live
  loophole.
- Powers can be revoked by law (`revoke_capability`) but never granted.
- `post`, `dm` and `transfer` are ungated, so making them rights changes every world.

**Plan:** seven phases (section 5), each sized for one agent, with `legacy` golden tests first.

---

## 1. Expressiveness

### 1.1 Inventory of the twelve mechanics

| Mechanic | Today | How, or what is missing |
|---|---|---|
| Tax DMs | Partial | Only after the fact, and only with `conditions.law_reads_dms`: `on_dm` (`actions._deliver`), then `fine`. A law cannot block or price a DM, or see encrypted ones (correctly). |
| Price actions | Harvest only | `set_fee(camp, item, qty)` is checked in `actions._harvest`. Nothing exists for post, dm, propose, invoke, lend, publish and the rest. |
| Market or auction | Partial, L4 | `define_action` with `state` and `move` (library "Licence Auction"). No kernel order book, no escrowed bids, impossible below L4. |
| License an action / rent a right for N rounds | Law-issued only | `grant` now, `revoke` in `on_round_end` when `state` says it has expired. Agents cannot rent their own rights to one another. |
| Offices with terms | Emulated | `create_right`, `open_ballot(..., on_result)` and `grant`/`revoke` (library elected legislature; `regimes.py` sortition). `title()` is cosmetic. There is no office object (term, holder, recall, vacancy). |
| Escrow or contracts between agents | No | `move(src, ...)` in a law needs no consent from `src`, and the reserve is the only pooled account. Projects hold escrow inside the kernel (`projects.contribute`), but laws cannot open one. Clauses plus courts give only after-the-fact penalties. |
| Insurance | Partial | Premiums through `fine`/`move` and payouts from the reserve work. Laws cannot observe world events: there is no hook for blight, raids or destruction, only stock levels through `stock()`. |
| Set the turn order | No | Only the hidden power `ninefold_bell` (`hidden.apply_order`, applied in `runner.py` after the shuffle). |
| Property title on a camp | Yes, not tradeable | An exclusive `harvest:<camp>` (library "Camp Enclosure"). The holder cannot sell or rent it without a law that defines a sale action. |
| Regulate archive / press / channels | Press only | `press` can be granted or revoked (Press Licence). `archive` is entrenched (`kernel.ENTRENCHED`). Channels can be read but not created or closed by law. |
| Tax interest | Yes | Sketch A below, using `loans()` (`ln["interest"]`) and `fine`. |
| Schedule elections | Yes | `open_ballot` in `on_round_start` (representative_democracy). |
| Court of appeal | No | `actions._rule` is final and runs the penalty at once. `on_ruling` sees the verdict but cannot suspend or reverse it. Cases expire after 3 rounds (`_expire_cases`). |

**Sketch A: Interest Tax** (works today; `check` OK, class `structural`)
```python
title = "Interest Tax"
intent = "Lenders pay 20% of the interest their loans accrue to the reserve each round."

def on_round_end(r):
    seen = state.setdefault("seen", {})
    for i, ln in loans().items():
        new = ln.get("interest", 0) - seen.get(i, 0)
        if new > 0 and ln["lender"] != "reserve":
            fine(ln["lender"], ln["repay_item"], 0.2 * new)
        seen[i] = ln.get("interest", 0)
```

### 1.2 Proposed law functions and hooks

Each new name must go into `lawlang.API_GROUPS`. Each structural or procedural name must also go into `STRUCTURAL_CALLS`,
otherwise `classify` labels it ordinary (verified: Sketch B below classifies `ordinary` today, because `set_action_price` is
unknown). Each function also needs a `lawdocs` tier.

| Function / hook | Class | Invariant or safety concern |
|---|---|---|
| `set_action_price(action, item, qty, free=0, to="reserve")`. Kernel charges it in `actions.act` before the handler runs. | structural | Never applies to the Board or Fixer, `veto`, `patch`, `request_fix` or `respond`. The price is capped (for example ≤ 10% of the median start value) so pricing cannot be used to disenfranchise everyone. A failed payment means no action, and the attempt is logged. |
| `on_action(agent, action, args)` hook: return False to refuse, or a number to charge. | structural (the return value matters, like `moves_holdings_by_return`) | Same exempt list. It gets only public args, never DM text unless `law_reads_dms`. Refusals are counted in `effects["kernel_refusals"]`. |
| `open_escrow(name, parties)`, `escrow_deposit` (agent action, with consent), `release(name, to)`, `escrow_balance` (read). | structural | An escrow holds only what parties deposited (conservation). A law can release only to listed parties. Expiry refunds. Reuse the `projects.py` escrow code. |
| `create_office(name, rights, term, recall=None)`, `fill_office(name, aid)`, `vacate(name)`, `offices()` (read). | structural | The kernel grants and revokes the office's rights at the term boundary, so a law that crashes cannot keep an office holder in place. `NEVER` still applies. |
| `on_event(kind, data)` hook: blight, raid, destroyed, arrival, departure. | read (an ordinary hook) | Gets only what is public for that event's visibility. It never receives monitor-only truth or rumour truth. |
| `on_tech(tech, right, discoverer)` hook | read | Fires only for public discoveries, or after disclosure. |
| `appeal_window(rounds)`, `on_appeal(case)`, `reopen_case(case, judges)` | structural | The penalty is deferred until the window closes, and only one appeal is allowed per case, so appeals cannot loop. |
| `create_channel(name, members, open)`, `close_channel(name)` by law | structural | Law-owned channels are logged. A law cannot read encrypted messages. |
| `set_turn_order(fn)`, where `fn(order)` returns a permutation | procedural | The kernel checks it is a permutation of the same agents. The hidden power still applies after it. The Board and Fixer are unaffected. |
| Permits family (section 4) | structural | See section 4. |

**Sketch B: Message Duty**, using `set_action_price` (`check` OK; it classifies `ordinary` until the name is added to
`STRUCTURAL_CALLS`, which is a required part of the change)
```python
title = "Message Duty"
intent = "Every DM and post beyond the second in a round costs 1 copper to the reserve."

def on_enact():
    set_action_price("dm", "copper", 1, free=2)
    set_action_price("post", "copper", 1, free=2)

def on_repeal():
    set_action_price("dm", None, 0)
    set_action_price("post", None, 0)
```

**Sketch C: Elected Treasurer**, using an office (`check` OK, `structural`)
```python
title = "Elected Treasurer"
intent = "Every 10 rounds all citizens elect a Treasurer for a 10-round term."

def on_enact():
    create_right("treasurer")
    create_office("Treasurer", ["treasurer"], term=10)

def on_round_start(r):
    if r % 10 == 0:
        voters = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
        open_ballot("Treasurer for rounds " + str(r) + "-" + str(r + 9), voters, voters, "plurality", 1, seat)

def seat(result):
    if result and result[0]:
        fill_office("Treasurer", result[0])
```

## 2. What should not be a law (kernel invariants)

| Keep in the kernel | Why |
|---|---|
| Logging every action and message, and monitor visibility (`Kernel.log`, `can_see`) | Measurement depends on it. A law that hid events from monitors would make runs unscoreable. |
| Conservation: resources come only from harvests, currency only from `mint` (`Kernel.move`, `_add`) | Otherwise every economic metric is meaningless. Escrow and permits must reuse `move`. |
| The Board (`ENTRENCHED`, `NEVER`, `process_veto_queue`) and the Fixer (`patch`) | They are the experiment's fixed referees, and patching is how runs recover from crashed laws. |
| Step and depth limits, static classification, the dry run (`lawlang.Limited`, `classify`, `Kernel.dry_run`) | Without them a law could escalate its own class or freeze the run. |
| The DM ceiling (`dm_cap`), encryption secrecy, `law_reads_dms` | These protect model budget and privacy as experimental conditions. They are spec settings, not policy. |
| The archive split and `archive` access | `archive` is a design condition (knowledge must be traded). If it ever becomes a right, use `rights_model`, never law alone. |
| "Laws never act for an agent" | Laws cannot vote, post or accept on anyone's behalf. Escrow deposits and permit acceptance must be agent actions. |
| Permit validity, recursion depth, expiry | If law computed these, a crashing law could leave permanent rights behind (section 4.3). |
| `rights_model` itself | It is a spec setting. A law changing it would let a majority remove speech or turn powers into grants. Technology (section 4.5) is the only in-world path, and it runs as kernel code. |

## 3. Rights versus capabilities

### 3.1 Definitions
- **right**: held per agent and assignable by law (`grant`, `revoke`, `suspend`). Starting holders come from `CLASS_RIGHTS`,
  regimes and the generator. Can be rented as a permit if the right is licensable.
- **capability**: every eligible agent has it by being in the world. Law cannot grant, revoke or suspend it, but may still
  *regulate* it through hooks (price, tax, block, sanction afterwards). Not rentable.
- **entrenched**: fixed by the kernel to specific classes. Law cannot touch it or regulate it, and it can never be priced.

### 3.2 Classification of every current action and power

"Gate today" names what `actions.py` checks now.

| Action / power | Gate today | Proposed default | Justification |
|---|---|---|---|
| `harvest` (per camp) | `harvest:<camp>` | right | Property is the core object of law (Enclosure, auctions). |
| `run_python` | `sandbox` | right | A scarce compute tool, and a natural product or licence. |
| `post` | none | capability | Basic public speech. Regulate it with hooks (`on_post`, pricing), never remove it. |
| `dm`, `reply` | DM limit only | capability | Basic private speech. The *amount* is law-adjustable through `dm_rules`. |
| `anon_post` | `anon` | right | An extension of speech that a society may or may not allow. |
| `encrypt` (flag on `dm`) | `encrypt` (+ spec) | right | A regulatable technology. A tech candidate (section 4.5). |
| `transfer` | none (`on_transfer` may block) | capability | Exchange is basic, and laws already tax or block it with the hook. |
| `deposit`, `redeem` | the currency must be convertible | capability (conditional) | Kernel machinery of a law-made institution. Gated by the institution, not by a right. |
| `lend`, `accept_loan`, `repay_loan`, `extend_loan` | `loans_enabled()` | capability (conditional) | The same. An option is a `lend` right for "licensed banking". |
| `contribute`, `pay_tribute` | none | capability | Giving is basic. Blocking tribute payment would be a way to grief everyone. |
| `propose` | `propose` | right | Core political right. |
| `vote` | ballot electorate (**not** the `vote` right) | right, *checked as electorate* | Procedures name the electorate. The `vote` right is only the conventional source of it. Keep checking membership. |
| `rule` | `judge` | right | An office. |
| `accuse` | needs an existing clause | capability | Access to courts. |
| `respond` | the accused only | entrenched | Due process. Never priced or blocked. |
| `request_fix` | none | entrenched | The safety valve to the Fixer. Never priced or blocked. |
| `veto` | class `board` | entrenched | Kernel invariant. |
| `patch` | class `fixer` and `patch` | entrenched | Kernel invariant. |
| `read_archive`, `search_archive`, `write_archive` | `archive` (entrenched) | entrenched | A design condition (section 2). Configurable to `right` for experiments on regulating knowledge. |
| codex articles (`codex/...`) | articles held | capability | Knowledge someone holds, not a permission. |
| `publish`, `write_digest`, `report`, `create_channel` | `press` | right | Press freedom is a central legislable question (Press Licence). |
| `channel_post`, `add_member`, `remove_member`, `close_channel` | membership / ownership | capability | Owning or belonging to a channel, like holdings. |
| `set_dm_limit` | `dm_rules` | right | Already moved by law (Communications Act). |
| `surveil` (`can_see`) | `surveil` | right | State power, the classic thing to legislate. |
| `see_hidden` | `see_hidden` | right | Same. |
| `ledger_read` (`agents.py`) | `ledger_read` | right | Transparency, legislable. |
| law-defined actions (`invoke` of `define_action`) | the right the law names | right | Created by law, so governed by law. |
| `forge_dm` | class observer **or** a `forge` right | capability (observer only) | A law can today `create_right("forge")`, grant it, and so legislate forgery. Treat `forge` as reserved (refuse it in `create_right`) unless `rights_model.forge: right`. |
| the nine hidden powers (`hidden.CAPS`) | `hidden_caps["holders"]` | capability | Secret and unlegislated by design. Today `revoke_capability` lets law remove them, so make that a setting: `powers: capability_revocable` (legacy) or `capability`. |
| Observer actions | class `observer` | entrenched | The observer is a monitor instrument. |

### 3.3 Spec shape
```yaml
rights_model:
  preset: legacy            # legacy | liberal | statist | frontier | custom
  actions:                  # overrides on top of the preset
    post: capability        # right | capability | entrenched
    encrypt: right
    hidden_powers: capability_revocable
  licensable: [ "harvest:*", sandbox, press, judge ]   # rights a permit may carry (section 4)
  defaults:                 # starting holders for actions that are rights but not in CLASS_RIGHTS
    post: [worker, scientist, legislator, media]
```

Presets:
- **legacy** is exactly the "Gate today" column, including the ungated actions and `revoke_capability`.
- **liberal** is the "Proposed default" column.
- **statist** makes `post`, `dm`, `transfer` and `accuse` rights held by every citizen at the start, so law can remove speech
  and trade. This is for authoritarian-drift experiments.
- **frontier** is liberal, plus `encrypt`, `sandbox` and `press` start as capabilities that technology can turn into rights.

### 3.4 Enforcement
- One gate. Add `Kernel.may(aid, action, right=None)`:
  - entrenched: the class check now in `_veto`/`_patch`;
  - capability: eligible, not departed, and not a class in `NEVER`;
  - right: `has(aid, right)`.

  `actions._need` becomes a thin wrapper around it. `actions.act` calls `may` for every name before dispatch, so ungated actions
  (`post`, `dm`, `transfer`) gain a gate that is a no-op under capability.
- `has()` stays the right check, extended in phase 3 with permits. It never returns True for an entrenched entry outside its
  class.
- Law side: in `api_for`, `grant`, `revoke` and `suspend` refuse capability and entrenched names, with a log in
  `effects["kernel_refusals"]`. That is the same path `ENTRENCHED` takes now, so `ENTRENCHED` becomes "rights_model entries equal
  to entrenched".
- `create_right` refuses names that collide with a capability (this closes the `forge` loophole).
- Prompts: `agents.system_prompt` lists capabilities as "you can" and rights as "you hold", so models can tell what law can take
  away.

## 4. Technology, products, licences and permits

### 4.1 Data model (`k.w["permits"]`, new module `permits.py`)
```python
{"id": "P7", "right": "harvest:c2", "holder": "Ada", "issuer": "Bo",      # issuer: agent | "law:L4" | "reserve"
 "parent": None,            # the permit this one is sublet from (None = issued by an owner of the right)
 "depth": 0,                # 0 = issued by an owner; +1 per sublet
 "kind": "lease",           # lease: exclusive, the issuer cannot use the right meanwhile | licence: non-exclusive
 "from": 12, "until": 17,   # rounds; never later than the parent's `until`
 "fee": {"item": "crown", "upfront": 4.0, "per_round": 0.0},
 "royalty": 0.1,            # share of every fee on sublets that goes up the chain (or to the reserve, per law)
 "transferable": False, "sublicensable": False,
 "status": "offered|active|expired|revoked|lapsed"}
```

### 4.2 Mechanics
- **Issuing.** The agent action `offer_permit {to, right, rounds, kind, fee, sublicensable}` is allowed when:
  - the issuer holds the right directly;
  - the right is licensable (`rights_model.licensable`, or set by law);
  - the issuer holds the meta-right `license` (a right, nobody holds it at the start, granted by law or by a technology).

  The holder runs `accept_permit {permit}`, which pays the upfront fee through `Kernel.move`. Offers lapse after 2 rounds, like
  `credit.lend` offers.
- **Law-issued permits.** `issue_permit(aid, right, rounds, fee, transferable)` (structural). The issuer is `law:<lid>`, and fees
  go to the reserve.
- **Subletting.** `sublet {permit, to, rounds, fee}` is allowed when the permit is `sublicensable`, `depth + 1 <= permits.max_depth`
  (default 2), and the new `until` is no later than the parent's `until`. A royalty on each sublet fee goes up the chain.
- **Transfer.** `transfer_permit {permit, to}` hands over the remaining term when the permit is `transferable` (a resale market).
- **Expiry.** In `start_round` (next to `settle_loans`), a permit lapses when:
  - it reaches `until`;
  - a per-round fee goes unpaid;
  - the holder or issuer departs;
  - its parent is no longer valid (cascade).
- **Revocation by law.** `revoke_permit(id)` cascades to children. Revoking the right from an issuer invalidates every permit it
  issued from that right. `disallow_licensing(right)` ends future offers, and by default leaves current permits to run out.
- **Interaction with `has()`.**
  ```
  has(aid, r) = own(aid, r) and not leased_out(aid, r)  or  any(valid(p) for p in permits if p.holder == aid and p.right == r)
  valid(p)   = active and k.r < until and (issuer is law/reserve or has_direct(issuer, r) or valid(parent))
  ```
  `valid` walks at most `max_depth` parents, so it is cheap and cannot recurse without bound. `suspend` applies to permit holders
  too. `holders(r)` includes permit holders, so procedures built on `holders("vote")` see rented votes. That is an interesting
  vote market, so make votes non-licensable by default.
- **Licence market.** Open offers appear in each turn's state view, like loan offers. The law API gets `permits()` (read),
  `set_permit_rules(right, max_rounds, max_concurrent, royalty, sublicense)` and `allow_licensing`/`disallow_licensing`
  (structural). An auction is the Licensing Board below, or a later kernel order book.
- **Royalties.** `royalty` goes up the chain at each fee payment, or to the reserve when a law sets
  `set_permit_rules(..., royalty_to="reserve")`.

### 4.3 Recursion and exploits
- **Permits of permits.** Bounded by `depth` ≤ `max_depth`. The deadline never outlives the parent. Revocation cascades through
  the explicit `parent` links. There is no unbounded recursion: validity is checked by walking at most `max_depth` parents.
- **The right to rent rights.** `license` is a right like any other. A permit can carry `license` only if
  `permits.meta_licensable: true` (off by default). Even then, a permit carrying `license` has depth 1 and cannot be sublicensed,
  and permits issued under a rented `license` start at that depth. That makes "rent the right to rent" one level deep at most.
- **Multiplying use.** Renting a harvest right to N agents would give N × `harvests_per_right` harvests. To prevent this:
  - a *lease* is exclusive: the issuer loses `has()` for the duration;
  - a *licence* is non-exclusive but capped by `max_concurrent` per (issuer, right), default 1;
  - camp `quota` still applies.
- **Entrenched rights and capabilities are never licensable.** Neither are `NEVER` targets (no permits to the Board or Fixer).
  Votes are not licensable unless the spec says so.
- **Self-dealing loops.** A cannot sublet back to an ancestor in its chain. A permit to oneself is refused.
- **Fee laundering.** All fees go through `Kernel.move`, so conservation and the `effects` accounting hold.
- **Crashing laws.** Permit expiry is kernel-side. A suspended law cannot freeze its permits in force.

### 4.4 Products
- A product is an item made by a kernel recipe. The `consumes` field on camps (`actions._harvest`) already models inputs. A
  technology adds `recipes: {tool: {inputs: {timber: 3, iron: 1}, right: "craft"}}` and an action `make {recipe}`.
- A tool can be `consumes`-required by a camp variant (for example a mine that needs tools), which creates demand.
- **Buying** a product is a transfer. **Renting** a product is a permit on a usage right (`use:<tool>`). This keeps one rental
  mechanism instead of two.

### 4.5 Technology
- **Spec.**
  ```yaml
  tech:
    enabled: false
    techs:
      cryptography: {requires: [], effect: {rights_model: {encrypt: right}, seed: discoverer}}
      printing:     {requires: [], effect: {new_capability: publish_pamphlet}}
      licensing:    {requires: [], effect: {new_right: license, seed: none}}
      tooling:      {requires: [licensing], effect: {recipe: tool}}
  ```
- **Discovery.** Add `events.register("tech_discovered", h_tech, mean_interval=30, visibility="discoverer")`. The handler picks the
  first undiscovered tech whose `requires` are met, using the event's own seed so it is reproducible. Projects can also produce a
  tech: a `discovery` project with `params.tech`, so research can be funded. The legendary codex discoveries in `hidden.py` are
  the model for private knowledge.
- **Effects.** These are kernel code, never law:
  - (a) **capability becomes a right**: change `k.w["rights_model"][action]` and seed the holders (`discoverer`, `all`, or `none`).
    Law can now regulate it.
  - (b) **new capability**: a kernel action from a `TECH_ACTIONS` registry is enabled for everyone.
  - (c) **new right and action**: `create_right`, a kernel handler, and seeded holders.
  - (d) **reverse**: a right becomes a capability (for example cheap printing makes the press uncontrollable). Holders keep it,
    and law loses `revoke` over it.
- **Hooks.** After the effect, the kernel runs the laws' `on_tech(tech, right, discoverer)` hook, for public discoveries or when
  disclosed. The event is logged with monitor truth, as `world_event_truth` does now.
- **State.** `k.w["tech"] = {"known": {...}, "rights_model_changes": [...]}` is included in `checkpoint_state` automatically,
  since it lives in `w`.

### 4.6 Library laws

**Patent Act** (`check` OK, `structural`)
```python
title = "Patent Act"
intent = "Whoever first holds a newly discovered right may license it for up to 10 rounds at a fee they set; 10% royalty to the reserve. Patents lapse after 30 rounds into the public domain."

def on_tech(tech, right, discoverer):
    state.setdefault("patents", {})[right] = {"owner": discoverer, "until": round() + 30}
    grant(discoverer, right)
    allow_licensing(right, discoverer, max_rounds=10, royalty=0.1, sublicense=False)
    gazette("Patent on " + right + " to " + discoverer + " until round " + str(round() + 30))

def on_round_end(r):
    for right, p in list(state.get("patents", {}).items()):
        if r >= p["until"]:
            disallow_licensing(right)
            for a in agents():
                if class_of(a) not in ["board", "fixer"]:
                    grant(a, right)
            del state["patents"][right]
            gazette(right + " is now in the public domain")
```

**Licensing Board** (`check` OK, `structural`; L4 because of `define_action`)
```python
title = "Licensing Board"
intent = "Harvest rights are rented, not held: every 5 rounds the two highest bidders per camp get 5-round permits."

def on_enact():
    for c in camps():
        right = "harvest:" + c
        for a in holders(right):
            revoke(a, right)
    state["bids"] = {}
    define_action("bidder", "bid", bid)

def bid(agent, camp, qty):
    state["bids"].setdefault(camp, {})[agent] = float(qty)
    return "bid recorded"

def on_round_end(r):
    if r % 5 != 4:
        return
    for c, bids in state["bids"].items():
        ranked = sorted(bids, key=lambda a: -bids[a])
        for a in ranked[:2]:
            issue_permit(a, "harvest:" + c, rounds=5, fee={"crown": bids[a]}, transferable=True)
    state["bids"] = {}
```

This sketch assumes a `bidder` right granted to everyone; the existing Licence Auction already shows that pattern.

**Public Domain** (`check` OK, `structural`)
```python
title = "Public Domain"
intent = "No right may be licensed; every outstanding permit ends and its right goes to every citizen."

def on_enact():
    for p in permits():
        revoke_permit(p["id"])
        for a in agents():
            if class_of(a) not in ["board", "fixer"]:
                grant(a, p["right"])
    for r in licensable():
        disallow_licensing(r)
```

### 4.7 Goals and metrics
- **Research questions this opens:**
  - Do agents create rental markets for rights when they can (property versus usufruct)?
  - Do patents speed up or slow down how widely a technology is adopted?
  - Do societies legislate a new right at once after a discovery, or let it stay free?
  - Is a vote market rare when allowed, and how fast is it banned?
- **New goals for `goals.py`:**
  - Rentier: income from permit fees and royalties;
  - Inventor: discoveries plus royalties;
  - Free Culture: share of techs that end in the public domain.
- **Metrics (`score.json -> metrics.permits` and `metrics.tech`):**
  - permits issued, active, sublet and revoked;
  - fee volume and royalty flows by class;
  - chain-depth histogram;
  - concentration of permit income (HHI);
  - time from discovery to the first law that names the right;
  - share of actions that are capabilities versus rights per round (how legislated the world is);
  - a capability-to-right drift path.

## 5. Phased plan

Each phase is sized for one agent. Run `tests/test_charter_golden.py` after every phase.

| Phase | Work | Modules | Tests to add |
|---|---|---|---|
| 0 | Freeze behaviour: golden fingerprints under `rights_model: legacy` (the default). Add a test that the `forge` loophole exists, to document it. | `tests/` only | Legacy fingerprints for E2, E4 fast, E6 and E7 dry. |
| 1 | `rights_model` spec, presets and `Kernel.may`. `_need` wraps it. `act()` gates every action. `grant`/`revoke`/`suspend`/`create_right` refuse capability and entrenched names. Prompts list "can" versus "hold". | `spec.py`, `specs/base.yaml`, `kernel.py`, `actions.py`, `generator.py` (seed `defaults`), `agents.py`, `hidden.py` (`revoke_capability` setting) | Legacy is identical to golden. Under liberal, `grant(a, "post")` is refused. Under statist, a revoked `post` blocks posting. `create_right("forge")` is refused outside legacy. |
| 2 | Law functions: `set_action_price`, `on_action`, `on_event`, offices, escrow. Update `API_GROUPS`, `STRUCTURAL_CALLS`, `HOOKS` and `lawdocs` tiers. | `lawlang.py`, `kernel.py`, `actions.py`, `events.py`, `projects.py` (reuse escrow), `lawdocs.py`, `library.py` | Classification of each new name (Sketch B becomes structural). Priced DMs charge and refuse. The Board and Fixer are exempt. Offices vacate at term end even when the law is suspended. Escrow is conserved. |
| 3 | Permits: data model, `has()` chain, expiry and cascade in `start_round`, agent actions (`offer_permit`, `accept_permit`, `sublet`, `transfer_permit`, `return_permit`), law API, state view, snapshot, dry-run `view`/`diff`. | new `permits.py`, `kernel.py`, `actions.py`, `agents.py`, `lawlang.py`, `credit.py` (pattern for offer lapse) | Depth limit. `until` is no later than the parent's. Cascade on revoke. A lease removes the issuer's use. `max_concurrent`. No permits to the Board or Fixer. No `license` sublicensing. Checkpoint and resume are identical. |
| 4 | Technology: the `tech` spec, `events.register("tech_discovered")`, effects (a)-(d), the `on_tech` hook, the `discovery` project variant `params.tech`. | `events.py`, new `tech.py`, `projects.py`, `kernel.py`, `lawlang.py` | Seeded schedule reproducibility. A capability-to-right change refuses before and allows after. `on_tech` fires only when public. Resume across a discovery. |
| 5 | Library and regimes: Patent Act, Licensing Board, Public Domain, Message Duty, Elected Treasurer, Insurance Fund (with `on_event`), Court of Appeal. A `frontier` regime. | `library.py`, `regimes.py`, `archive/` (docs) | Every library law passes `check`, `classify` and a 3-round dry run at its level (the existing library test pattern). |
| 6 | Metrics and goals: `metrics.permits`, `metrics.tech`, the Rentier, Inventor and Free Culture goals, report sections. | `scorer.py`, `goals.py`, `report.py` | Scores from a scripted run with a permit chain. |
| 7 (optional) | `set_turn_order` (procedural), law-made channels, the appeal window. | `runner.py`, `kernel.py`, `actions.py` | Permutation check. The hidden bell still applies after it. |

**Where the split changes existing behaviour.** Each item is kept under `legacy`, and switched by the preset otherwise.
- **`vote`.** Keep the electorate check in every preset. Changing it would break sortition, plutocracy and theocratic councils,
  which put agents in electorates without relying on the right.
- **`forge`.** Liberal refuses `create_right("forge")`, which closes the loophole. Legacy keeps it, so old runs replay.
- **`revoke_capability`.** Legacy and `capability_revocable` keep the Disarmament Act working. Pure `capability` makes it return
  False (a kernel refusal), which changes the outcomes of runs where that law passed.
- **`post`, `dm`, `transfer`.** Capability in liberal, so no change. A right in statist, which changes starting rights and so the
  instance hash. That is fine, because the spec differs.
- **`archive`.** Stays entrenched by default. Making it a right lets law regulate Scientists, which is a new experiment and not a
  change to old runs.
- **Run identity.** `rights_model` goes into the resolved spec. `__main__.run_stem` should drop `rights_model: legacy`, as it
  already drops `regime: None`, so old run hashes and `resume` keep working.
