# Review 17: space (a weighted graph of places)

*9 Oct 2026, written at `integrate/w9` (`3f4aafc`). Design only: no code changed, no model called, no simulation run. Inputs: the
owner's request ("a weighted graph (distance), where each node can have various defined parameters like local resources that can
be extracted, land capacity for buildings etc. ... agents would naturally only see everything on their own space unless they leave
or there are communication channels"), ARCHITECTURE §1 (space "deferred"), D-24..D-37, review 07 §3 (the earlier site-graph
triage), reviews 11, 12 (tiers), 14 (§4.6, §7.1, §7.2), 15 (subsistence and the farming ladder) and 16 (economy audit), BACKLOG
(police and armies, custodian worlds), and the code named below. Section 11 asks the decisions.*

## Executive summary

**Verdict.** Space is worth building, but not as a feature switched on in today's worlds. It is a different simulation family that
shares the kernel. Most of what the owner wants from it (battles, buildings, seats of institutions, abandoned goods, information
that travels) follows from one mechanism: **presence**. Presence means an agent is at a node, and physical acts need the actor and
the object at the same node. Distance on its own adds little. The geometry is about 300 lines of code. The expensive part is
re-checking every physical act, every audience and every account against location. Review 07 §3 said this on 7 Oct,
and it is still true: 60 code sites name a `harvest:<camp>` right, 42 move goods, 98 read balances, and one `can_see` decides
every audience.

**Where space pays.** It pays when four other things are true, and not otherwise:

1. **Goods must be used where they are.** Review 15's food, eaten every round and spoiling, is the main case. Without consumption,
   located goods are friction with no payoff.
2. **Information is slower than people, or at least not instant.** If DMs and channels stay instant and global, space shrinks to
   a harvest-access tax and a smaller square.
3. **Accounts are located.** If treasuries and escrows remain global ledgers, any agent can teleport stone by depositing it at
   node A and having the institution pay it out at node B.
4. **There are enough agents per node** (about 5 or more) for local societies to form.

A space world with fewer than all four is a costlier version of today's world.

**Recommendation.**

- Build space as `space.enabled` (default off, every existing preset byte-identical) on a graph whose degenerate form, one node
  holding every camp with everyone present, reproduces today's world exactly. Equivalence is proven by `difftest`.
- Stage it. The first slice gives agents presence and travel, perception of only their own node, a square per node, and a ground
  where abandoned goods lie. Located treasuries, buildings, message latency, battles at nodes and markets follow as separate
  packages.
- Run no Haiku pilot on space before review 15's food (S1-S3) exists.

**Smallest valuable first slice (SP1 + SP2, about 2-3 weeks).**

- Nodes and edges from the spec, or generated from today's camps.
- `k.w["space"]["at"]` and the `travel` action. Travel costs actions, and long edges carry over into later rounds.
- Presence gates on `harvest`, `attack`, `join_attack`, `guard` and the physical `transfer`.
- The natural audience `local`: physical events are seen by the agents present.
- `channels.square: per_node`, plus state lines and a map.
- A `ground:<node>` account where estates without heirs and the assets of institutions that can no longer act come to lie. Anyone
  present can take them. This replaces review 14 §7.2's spaceless "locked".
- DMs stay instant and the ledger stays global in this slice.

This slice can be tested with scripted bots and difftest. It is enough to see whether locality changes who talks to whom and who
forms institutions with whom. It is not yet enough for logistics or custody.

**Top decisions for the owner** (§11):

- Do messages cross distance instantly, with delay, or only by courier?
- Do institutions' goods live somewhere (custody) or on a global ledger?
- Does a polity get territory? The recommendation is no claim primitive: physical control of chokepoints, plus entry-as-consent
  shown at the gate.
- Is travel paid in actions or in rounds?
- Is space a separate family with its own presets and goldens?
- Must space wait for food?

---

## 1. What is place-like today, against the code

| Today | Where | Is it space? |
|---|---|---|
| Camps: resource sites with a hidden yield function, logistic stock `S/K`, regrowth, drift, quotas, fees | `charter/camps.py` (`make_camp`, `harvest`, `regrow`), `charter/camptypes/framework.py` (`harvest_action`, `pay_yield`, `world_update`) | No. A camp is a resource *process*. Access is by right (`harvest:<camp>`, `actions._harvest` → `_need`) or by an open typed camp (`framework.can_take_part`), from anywhere. Review 07 noted "harvest from anywhere" |
| Camp rules (quota, harvest limit, fee) | `jurisdictions.camp_rules(k, aid, camp)` | Personal, not territorial. The *harvester's* jurisdiction's rules apply wherever the camp is. This matters for §4: Charter's law is already the nationality principle (review 10: "no territoriality, OUT without space") |
| Presence | `channels._present(k, aid, camp)`: holding the camp's harvest right, or an open typed camp | A legal fact used as a stand-in for location. The per-camp squares (`channels.square: per_camp`) and the `{"camp": c}` selector are already written against this stand-in, so they are the seam where real location plugs in |
| Projects: granary (stock floor), upgrade (yield multiplier), road (a *new camp* with rights for contributors), discovery | `charter/projects.py` (`KINDS`, `_new_camp`) | A road is the one thing that already sounds spatial, but it creates a camp and a right, not a route. Under space it becomes an edge (§5.2) |
| Leases of harvest rights | `charter/camptypes/leases.py` | Rights as tenancy. Under space they remain the legal title, separated from physical access |
| Forts, guards, weapons, attacks | `charter/conflict.py`: `k.w["conflict"]["forts"][aid]`, `guards_of`, `attack`, `_spoils` (50% to the attacker, 50% destroyed) | A fort belongs to an *agent*, not a place. Anyone can attack anyone. A guard defends anyone it chooses |
| The outside power's raids | `charter/outside.py` (`raid`: a camp loses stock, its holders lose goods) | Raids hit a camp, which is close to a place. Granary floors hold against them |
| Accounts | `charter/accounts.py` (`RESOLVERS`: agent, `reserve`, `reserve:<jid>`, `estate:`, `assoc:`, `escrow:`, `fund:`) | Every account is a global ledger entry. Goods teleport between any two accounts in one `move` |
| Stores (planned) | review 15 §2.5, `store:<sid>` | The first located account, owned by an agent or institution. Not yet built (no `charter/subsistence.py`) |
| Who sees what | `Kernel.log(..., vis=)`, `Kernel.can_see`, `charter/publication.py` (natural audience, then publication widening), `eventtypes.NATURAL` | An audience is a set of agents. It never depends on where anyone is. Deaths, raids, world events and births are `public` by nature (`eventtypes.NATURAL`) because "anyone in the world observes" |
| The feed | `context.feed_layer` iterates `k.events[since:]` through `can_see` | The feed is a cursor over one global log. Delayed delivery would slip past this cursor (§3.3) |
| Snapshots | `Kernel.snapshot` (`stocks`, `holdings`, ...), module `snapshot_fields`; export `STATE_KIND` maps `stocks`, `camptypes`, `granaries`, `upgrades` to camps | Per camp, no location |

So Charter has *sites* without *space*. Camps are already the natural nodes, and the per-camp square is already the natural local
channel. Everything else assumes that one agent can touch the whole world in one action.

---

## 2. The model

### 2.1 The graph

One store, `k.w["space"]`, present only when `space.enabled` is set:

```python
k.w["space"] = {
  "nodes": {nid: {"id", "name", "terrain", "land", "land_used", "defense", "camps": [cid, ...], "resources": {...},
                  "carrying": {...}, "xy": [x, y]}},          # xy: layout for the site only; no rule reads it
  "edges": {eid: {"id", "a", "b", "time", "capacity", "danger", "built": round | None, "by": account | None}},
  "adj":   {nid: [(nid2, eid), ...]},                         # derived, sorted; rebuilt on edge change
  "at":    {aid: nid},                                         # agents at a node
  "transit": {aid: {"edge": eid, "from": nid, "to": nid, "left": units_remaining, "dest": nid, "path": [nid, ...]}},
  "seats": {iid: nid},                                         # institutions (§5.3)
  "buildings": {bid: {...}},                                   # §5.2 (SP4)
  "seq": int,
}
```

**Edges are undirected, with integer `time` in action units** (§2.4). The other edge fields:

- `capacity` is the number of agents that may enter the edge per round. `None` means unlimited. It is for bridges and passes, and
  is off by default.
- `danger` is the per-traversal chance of an accident. It is drawn on the stream `"{seed}|space|danger|{round}|{aid}|{eid}"`, and
  its outcome is an `end_life(cause="accident")` or the loss of carried goods (a spec choice). Default 0.
- Edges change only by world events or by building them (§5.2), never by law. A law cannot move a mountain.

**Map sources** (spec `space.map`):

| `space.map.kind` | What it builds | Use |
|---|---|---|
| `single` | One node `here` holding every camp, with everyone at it | The degenerate world: must equal space off (§8.1) |
| `from_camps` | One node per camp, plus a hub `commons` (the square) joined to each camp node by an edge of `space.map.time` (default 1) | The first non-trivial map. Today's worlds, spread out by the minimum. Camp ids and draws are unchanged |
| `ring`, `grid`, `geometric` | N nodes from a seeded generator (`"{seed}\|space\|map"`). Camps are assigned to nodes by role and terrain. Edge times come from distances in the layout | Generated worlds for studies |
| `authored` | `space.nodes` and `space.edges` written out in the spec | Hand-made scenarios (a river valley, an island chain, a frontier) |

The camp-to-node mapping is generated *after* `camptypes.framework.compose`, on its own stream. So turning space on never changes
which camps exist or their hidden functions. This is the same rule review 15 §2.2 used to append food camps.

### 2.2 Node parameters

| Field | Meaning | Tier | Notes |
|---|---|---|---|
| `camps` | The camps (resource processes) at this node | P (initial condition X) | A node may hold none (a pass, a town site) or several. Camp internals are unchanged |
| `resources` | Optional node-level deposits that are not camps: `{"stone": {"S", "K", "r"}}` | P | The same logistic law as `camps.regrow`, so a node can be a quarry without a dial game. Off unless declared |
| `land` | Land units for buildings and plots | P | Buildings and fields plots consume it (§5.2, review 15 §2.4). Clearing a forest (review 15 §2.7 rung 4) moves land from forest to plots *at that node* |
| `terrain` | `plains \| forest \| hills \| river \| coast \| ...` | X (a label) | Read only through the fields it sets: `defense`, `land`, default resources, edge times. No rule branches on the name |
| `defense` | Terrain bonus added to every defender's strength at this node | P | Hills and walls. 0 by default |
| `carrying` | Food capacity per round (forest K and plots, review 15) | P | Derived from the node's forest and fields, not a separate cap. D-36: "carrying capacity from food/land/fertility is the only ceiling" becomes per node, which is what makes migration a response to scarcity |

The node record holds *facts*. It never holds rules. Who may harvest, build or enter is law or an owner's rule (§4), as camp rules
are today.

### 2.3 What "location" means for each kind of thing

| Thing | Location | Why |
|---|---|---|
| **Agent** | `at[aid]`: one node, or `transit[aid]` on an edge | Presence. In transit an agent is at no node. It perceives the edge only (fellow travellers, dangers) |
| **Carried goods** (agent holdings) | Wherever the agent is | `k.w["agents"][aid]["holdings"]` stays one dict, so the 52 direct readers in 14 files and `Kernel.bal` keep working. The pack moves with the agent |
| **Caches** (SP2) | `cache:<node>:<aid>`: goods an agent left at a node | A located account. The depositor is recorded (E: a fact, like review 15's "physics records the sower"). It counts toward the depositor's Wealth (X). Anyone present can take from it (the liberty residual). Whether that is theft is law |
| **Ground** (SP2) | `ground:<node>`: goods with no depositor (abandoned, dropped spoils, unclaimed estates) | Anyone present can take from it. This replaces "locked" (§5.4) |
| **Buildings** (SP4) | `bldg:<id>` at one node, consuming `land` | An account (a store's contents) plus a function (§5.2). Review 15's `store:<sid>` becomes a building kind |
| **Institution treasuries, escrows, funds** (SP3) | At the institution's **seat** (`seats[iid]`, its hall's node, else the founding node) | Under `space.ledger: located`. Under `global` they remain teleporting ledgers, which §2.5 shows leaks |
| **Currencies, shares, debts, contracts, rights, laws** | Nowhere: ledger | They are claims, not things. Redemption of a backed currency needs presence at the reserve's seat (SP3). That is where banks get physical |
| **Estates** | The node where the agent died | Probate transfers *title*. The goods stay where they are as a cache of the heir until it collects them (SP2), or they go to the ground if there is no heir and no law speaks |
| **Camps** | Their node | Unchanged internals. Harvest needs presence (P) and, where law says so, a right (the Land Registry Act, review 12 K1) |
| **Channels** | Squares at a node. Every other channel has no location | Reading or writing a square needs presence. Other channels are subject to the comms dial (§3.3) |

### 2.4 Travel

`travel {"to": node, "via": [node, ...]?}` is one action that starts a journey along the shortest path (ties broken by node id),
or along `via` if given.

**Time is in action units.** Each edge has `time` t. Starting a journey uses the travel action, then t action units, taken from
the agent's remaining actions this turn and then from later turns. An agent with 4 actions crossing a 2-unit edge arrives in the
same turn with 1 action left. A 6-unit edge takes the rest of this turn and part of the next. While in transit the agent's turns
shrink to the leftover after travel.

This keeps short trips inside a round, which matters because runs are 25 rounds (`specs/arms/base.yaml`) and lifespans are 60-120.
Long trips still cost real rounds. Rounds as the unit (`space.time_unit: rounds`) is the alternative (§11 Q4).

**Arrival** is a world-caused primitive (`arrive`, P, not blockable). Laws that bind the agent may react to it.

**Departure** is the routed primitive `travel` (an L-route free act). Laws that bind the traveller can hook `before_travel`. This is
how a polity bans its *members'* emigration under D-26. Nothing in law can stop a non-member. Only gates (§5.2) and force can.

**Turns in transit.** An agent with nothing left to do but walk gets no model call that round, unless something was pushed to it
(a DM or its inbox under instant comms). This saves cost. It is recorded in `reasoning.jsonl` as a `transit` row, so the absence is
visible in the data.

**Helpers, so spatial reasoning is not the test.** A free `route {"to"}` look-up returns the path and its time. The kernel paths
the agent, so the agent never has to compute shortest paths.

### 2.5 Goods: carrying, stashing, shipping, and why every physical account must be located

- **Physical items** (resources, food, weapons, tools) move between accounts only when both accounts are at the same node. This is
  one new physics check in `dispatch.checks` for `move`, applied when `space.goods: located`.
- **Ledger items** (currencies, shares) are exempt.
- A `transfer` to an agent elsewhere is refused with a reason ("Bo is at Hillfort; goods must be carried or shipped").

**The leak if accounts stay global.** Suppose agents and buildings are located, but treasuries, escrows and funds are not. Then
`deposit_escrow` at node A followed by an association paying out at node B moves stone across the map for free. Every institution
becomes a teleporter, and transport cost disappears from the economy. So the choice is all-or-nothing for physical goods:

- either the ledger stays global (SP1: space is presence and perception only),
- or every account that can hold physical goods has a node (SP3).

There is no consistent middle. This is the strongest argument for staging: SP1 on a global ledger is coherent, and so is SP3 with
everything located. A world with half the accounts located is not.

**Carrying limits.** The spec key is `space.carry: {limit: null | value | units}`. It is off by default. With a limit, agents must
stash, build stores, hire porters or ship. That creates logistics, at a large cost in bookkeeping for LLMs. Turn it on only in a
logistics treatment.

**Shipments (SP7).** `ship {from_account, to_account, item, qty}` creates `shipment:<id>`, an account on an edge path that arrives
after the path's time (in rounds at a caravan pace, `space.ship_pace`). It can be intercepted by anyone present on its route: a
`raid` of a shipment is an attack on its escort, or a plain take if it has none. Couriers for letters are the same object carrying
text (§3.3).

---

## 3. Perception and communication

### 3.1 Local perception: one new natural audience

Review 12 WP2's publication layer already separates the *natural audience* (E, the floor) from *publication* (L, the widening).
`eventtypes.NATURALS = ("given", "public", "parties", "channel")`. Space adds one value, **`local`**: the agents present at the
event's node when it happens, plus the parties.

- At log time, under `space.enabled`, an event of a `local`-natural type gets `vis = sorted(parties ∪ present(node))`. This is a
  plain list, which `can_see` already handles.
- The list is frozen when the event is logged. Perception happens at the moment. An agent who arrives later sees the *traces* (the
  ground, the ruined fort, the corpse's estate as a cache) through the node description, not the event itself.
- The event gains `"node": nid` (additive; export §9).

**Which public types become `local`?** Today's `NATURAL` public-by-nature list: `disabled`, `attack_failed`, `raid`,
`world_event`, `birth`, `camp_round`, `camp_created`, plus the conflict and harvest results that call sites log public. Two kinds
stay public-by-nature because publication *is* the act: `gazette` and posts. Even these reach readers only through channels, and
channels are subject to the comms dial.

**Dependency.** This needs `law.publication: true`, because the `local` floor lives in `publication.publish`. With the flag off
there is no natural audience to change, and `Kernel.log` keeps every call site's literal. So space requires the publication layer,
with base `none` (the state of nature) or `today`, and a schema check enforces this.

**V11 ("absence is observable").** Death is observed by those present. Everyone else learns it through news or by noticing that
the dead agent no longer answers. Under instant comms a DM to a dead agent already fails, so a death leaks to its correspondents.
That is realistic.

### 3.2 Channels on a map

Channels v2 (`charter/channels.py`) needs four small changes and no new verbs:

| Change | Where | What |
|---|---|---|
| `channels.square: per_node` | `channels.sync`, `SQUARES` | One world-owned square per node, `square:<nid>`, readers and writers `{"node": nid}`. `per_camp` remains for spaceless worlds |
| Selector `{"node": nid}` | `SELECTORS`, `matches` | True when `at[aid] == nid`. Resolved live, so readers come and go |
| `{"camp": c}` under space | `channels._present` | Means "at the camp's node", no longer "holds its harvest right". The stand-in becomes the real thing |
| Chambers at a seat (optional) | a template, not a mechanism | An institution may give its chamber readers `{"node": seat}` (an assembly) or `{"members": iid}` (a correspondence), by its own code |

Inboxes, DMs, institution channels and secret cells are unchanged in kind. What changes is whether they reach across distance, and
how fast.

### 3.3 Information delay: the comms dial

Space's biggest qualitative effect is not walking. It is that news is slow. That is also its biggest confound: agents acting on
stale information will look incompetent. So the delay is a world dial (E: technology, D-30), with three settings:

| `space.comms` | DMs, inboxes, channel posts across distance | World it models |
|---|---|---|
| `instant` | As today: delivered this round, wherever sender and reader are | Telegraph or internet. Space affects only physical perception and access |
| `latency` | Delivered after `ceil(dist(sender_node, reader_node) / space.msg_speed)` rounds; co-located is immediate | Riders and post roads. Agrarian states. Information delay is first-class |
| `courier` | No remote delivery. A message to an agent elsewhere becomes a `letter` (a shipment of text) that an agent must physically carry and hand over at the recipient's node. Squares and co-located DMs only | Hunter-gatherers and the early frontier |

Implementation that keeps the feed cursor correct (`context.feed_layer` walks `k.events[since:]` once, so an event that becomes
visible later would be skipped):

- **Pushed items (DMs, own inbox) under `latency`.** At send time, log the message with `vis = [sender]` plus any co-located
  recipients. At delivery time, a round-start step (`space.deliver`) logs one `delivered` event per message, with
  `vis = [recipient]` and `data = {"of": msg_id, "sent_round", "from_node"}`. The feed renders it as the message, with "(sent
  round r from X)". Replay is exact because delivery rounds are a pure function of nodes at send time.
- **Pulled channels.** `channels.read` and `unread` filter with `e["round"] + lag(e["node"], at[aid]) <= k.r`. Lag is measured to
  the reader's *current* node, so walking towards the news brings it sooner. This is deterministic, because positions are state.
- **Laws reading evidence** (`evidence.law_can_see`) are unchanged in v1 (§3.4).
- **Edges and buildings can change latency:** `relay` buildings or road upgrades lower an edge's message time. That gives
  infrastructure an information payoff.

### 3.4 What laws perceive

Today a law's hook fires on its members' primitives wherever and whenever they happen, and `evidence.law_can_see` gives it the
public record. On a map this is an omniscient, instantaneous state: a polity taxes a member's harvest five days' walk away in the
same instant. That is the least realistic thing left once space exists. It is also review 11's "perfect enforcement" axis wearing
geography.

**Recommendation for v1:** keep it, and state it as X. Members consented (D-37), and the comparison with spaceless worlds stays
clean. Later, review 11 H2's detection dial gets a spatial form. Under `law.enforcement.detection: presence`, after-hooks on a
member's act are delivered only if an officer of the law's institution is present at the node, or with the comms latency from the
seat. That one change would make police physical: enforcement requires being there. It is the right hook for BACKLOG's police
forces. It should not be in the first slice.

The same issue exists for **legal acts**. Proposals, votes and ballots are kernel-processed and instant. The dial
`space.legal_acts: anywhere | at_seat` (later) would make voting require presence at the seat (an assembly democracy) or a sent
proxy. That is a real institutional variable: representation exists because distance makes assembly costly.

---

## 4. Physics and law on a map

### 4.1 Tiers

| Item | Tier | Residual (no law) | What law can do (members only, D-37) | What only force or ownership can do |
|---|---|---|---|---|
| Nodes, edges, times, land, resources, terrain defense | P (the map is an initial condition, X) | — | Nothing: laws do not move mountains | Build or destroy roads, gates and walls (SP4) |
| Location and presence; arrival | P | — | React (`after_arrive`): register, charge members | — |
| Departure (`travel`) | L-route (routed free act) | Liberty: anyone may go anywhere | Ban, tax or delay members' travel (`before_travel`): emigration law, D-26 | Gates and guards stop anyone |
| Perceiving co-located events | E | Local | Widen (publish to a channel), never narrow (an agent cannot un-see) | — |
| Comms reach and latency | E (technology dial) | The world's setting | Nothing below the technology. Relays are built, not legislated | Intercepting couriers is force |
| Carrying limits | P | Spec | — | — |
| Possession (who holds goods; which cache or building they are in; who controls a building) | P | Whoever holds them | — | Taking, breaking in |
| Title (who *should* hold a plot, building or cache) | L | None: the state of nature has no property (review 15 U1, D-30) | Land Registry Act: refuses members' takes and harvests without title. Courts | Guards make title stick against non-members |
| Territory and jurisdiction | Not a kernel concept (§4.2) | Personal law only (today's `camp_rules` principle) | Consent clauses, including entry-as-consent shown at the gate (§4.2) | Physical control of chokepoints |
| Tolls | An owner's rule on its gate building (like a channel owner's rate or fee) | No tolls | Tax members' passage | Pay, fight the gate or detour: the traveller's choice |
| Migration and exit | Travel is P. Membership exit is L (D-26) | Free | A Nationality Act still says who is a member. Distance protects exiles: post-exit sanctions only through agents who travel (D-26) | Pursuit |
| Building | L-route (`build` routed) | Anyone, within land capacity (P) | Zoning over members; licences | Demolition by force |

### 4.2 Does space finally justify territorial reach?

**The tension.** Review 14 D12 chose "no claim primitive" (resolved as recommended). D-37 says institutions bind non-members only
by force or by recognition from agents already bound. Space makes territory *feel* natural: "our valley, our rules". So it is
tempting to add `claim(node)` and let a polity's laws bind everyone present.

**Recommendation: do not add a claim primitive.** Territorial reach should emerge from three things that already fit D-37:

1. **Physical control.** A gate or wall (SP4) on an edge or around a node is a building. Its owner decides admission, as a channel
   owner decides writers. Passing against the owner's will is an attack on the gate, using `conflict` physics with the gate's
   defense. Tolls are an admission price. This is control of chokepoints, which is how most historical territory was held.
2. **Entry as consent, shown at the gate.** A gate's admission rule may say "entering is joining J3" (an allegiance clause, D11,
   allowed when visible at join). The traveller sees the clause and J3's static facts (powers claimed, exit terms) before
   choosing to enter. Entering is then an ordinary join. Residence-based jurisdiction is consent at the border.
3. **Force over the rest.** A non-member inside the valley who did not pass a consenting gate is bound only by what J3's agents can
   physically do. That is the honest "there is just power" (review 14 §3.2), now with distance and terrain shaping power.

A derived **control map** (who has armed presence and gates at each node) is computed for analysis (X), never read by rules. It is
the spatial analogue of `jurisdictions.decisive_set`.

**What would change this:** agents repeatedly try to claim land, and fail for mechanical reasons rather than social ones (review 14
D12's own trigger). For example, gates are too expensive for any institution to build, so territory never forms. Then the
remedy is cheaper gates, not a claim primitive.

**Cost of this choice.** Entry-as-consent needs gates to be cheap enough to build. Until SP4 (buildings) exists, nothing in SP1
gives an institution any territorial handle beyond its members' presence. That is a correct state of nature, but it may look
inert in a first pilot.

---

## 5. Conflict, buildings and institutions on a map

### 5.1 Force

- **Presence gates (SP1).**
  - `attack` and `join_attack` need the attacker, its allies and the target at one node.
  - `guard` defends only a guarded agent at the guard's node.
  - `contract` (hiring the assassin) needs nothing physical, but the assassin must travel to strike.
  - These are `dispatch.checks` additions to the routed `attack`, `guard_bind` and `join_attack` rows. The tier stays P.
- **Defense at a node (SP6).** `conflict.defense(k, aid)` adds the node's terrain `defense` and, once buildings exist, the forts
  at the node that admit the defender. `k.w["conflict"]["forts"][aid]` becomes a fort building at the builder's node when space
  is on. A fort you walked away from defends nobody.
- **Battles (SP6).** With `conflict.timing: end_of_round`, every attack resolved at one node in one round is one *battle*. Charter
  already resolves attacks in initiative order there (`resolve_attacks`). Add a `battle` summary event (local) listing sides,
  units and outcomes, for readability and the site. **No new combat mechanic:** each attack stays `chance(A, D, delta)`.
  Defenders who travel away before end of round are not there to be hit. That is retreat, for free.
- **Spoils.** Today 50% goes to the attacker and 50% is destroyed. Under space, the destroyed half can instead drop to `ground` at
  the node (`conflict.spoils.ground` share). Bystanders loot. Battles leave stuff behind.
- **Sieges** need nothing new if two things hold:
  - food exists (review 15), and
  - leaving a fort's node with hostile armed agents present costs an attack's exposure (a departure from a contested node triggers
    one free attack chance from each hostile present: `space.disengage`).

  Without food, a siege is meaningless: nobody inside runs out of anything. This is one of the clearest cases of space without
  payoff.
- **Armies (BACKLOG).** An army is an institution with:
  - an armory: weapons in a building at its seat;
  - a command office with agency (P4.5) over members' `travel` and `attack` (D-32's authorization pattern: the member chooses to
    act, the order is attributed);
  - pay and food.

  Movement along edges at the pace of the slowest member, plus supply, is what makes armies an *institutional* problem
  (desertion, loyalty, pay in arrears) rather than a sum of weapons. Space is the precondition the backlog item lacked. Do this
  after SP6 and wave 9's grants (WP-E).
- **Police.** An officer must be present to act on a member. With §3.4's detection dial, the law sees only what officers see.
  Policing becomes deployment: where to station officers, what it costs, and corruption at remote posts (review 11 H3).

### 5.2 Buildings

A building is a located account plus a function, consuming land. One routed primitive, `build`, and one owner-rule primitive,
`set_building_rule` (the spatial generalisation of `set_camp_rule`):

```python
k.w["space"]["buildings"][bid] = {"id", "kind", "node", "owner": account, "built": round, "land": n, "hp": x,
                                  "rules": {...},          # the owner's settings: admission, access, fees (like a channel's)
                                  "holdings": {...}}       # its account, owner key "bldg:<bid>"
```

The catalogue is data (`space.buildings`). Each kind has cost, land, hp, and one function implemented in the owning module:

| Kind | Function | Ties to |
|---|---|---|
| `store` | Holds goods. Low spoilage (review 15: 2% instead of 15%). Only the owner withdraws; break-in is an attack on its hp | Review 15 S3 (`store:<sid>` becomes `bldg:<id>`), granaries |
| `fort` | Defense for agents its owner admits, at its node | `conflict.defense` |
| `hall` | An institution's seat: its treasury and escrows live here under `ledger: located`; optional assembly chamber | §5.3 |
| `gate` | Admission on an edge or node: owner's rule (open, members, fee, "entering is joining J3"); hp and defense like a fort | §4.2 territory, tolls |
| `workshop` | `forge` (weapons, tools, plough) needs one at the node | Review 15 §2.7 rung 2 |
| `market` | Standing offers that execute when a counterparty arrives, so trade survives absence | §6 |
| `road` (edge) | Lowers an edge's `time`, or creates an edge to a newly discovered node | Today's `road` project (§1) re-expressed: `projects._new_camp` becomes "new node with its camp, plus an edge" |

**Keep the design arm small.** The owner dislikes agents being handed too much. In the design arm only `store`, `fort` and `hall`
exist at first. Each kind is an action doc line and a manual paragraph, so the catalogue grows only when pilots show it is used.
Plots and irrigation (review 15) are not buildings. They are node land with plot state, as review 15 designs them.

### 5.3 Institutions with seats

- **The seat.** An institution's seat is the node of its hall, or the founder's node at founding. `relocate` moves it (routed; the
  treasury's physical goods must be carried, which can be done under `ledger: located`).
- **Under `ledger: located` (SP3):**
  - `reserve:<jid>`, `assoc:<cid>`, `escrow:<cid>:<aid>` and `fund:` accounts are at the seat. Deposits and payouts of physical
    goods need presence there.
  - Taxes in kind collected from a member elsewhere are a real problem. The physics check refuses them.
  - A law's charge in kind on a remote member becomes an arrears record, or must be in currency.
  - **This breaks library laws that assume teleporting treasuries** (transfer taxes in kind, relief payments to anyone). The law
    library would need spatial variants: taxes in currency, collection at a node, toll-style levies. Review the library before
    turning `located` on in a preset.
- **Custodian worlds (BACKLOG).** These fall out almost for free. The hall's contents are physically held. A `custodian` office is
  the agent whose presence controls the hall's store, and a custodian who walks off with the goods has absconded. Today's
  smart-contract treasuries are the `global` setting.
- **Companies and institutions "making sense".** Seats give institutions a *where*: members gather, assemblies meet (with
  `legal_acts: at_seat`), the treasury can be robbed, and rivals can besiege it.

### 5.4 Abandoned goods (replacing the spaceless "locked")

Review 14 §7.2: when an institution's code can no longer act, its assets are "locked in spaceless worlds; in worlds with space
(review 17) they become abandoned goods at their location, claimable under the conflict rules." Concretely:

| Source | Today (or spaceless) | Under space |
|---|---|---|
| Dissolved institution, no heirs and no parent law | `contracts._dissolve` → `_pay_heirs` / `_escheat` (parent only), else held | Remainder moves to `ground:<seat>` with event `goods_abandoned` (local) |
| Estate with no bequest and no default heirs, no polity law | `mortality._reserve_dst` → the world `"reserve"` (a black hole in the state of nature, review 16 §1) | Goods stay at the death node: `ground:<node>` |
| Spoils' destroyed share | Destroyed | A configurable share to `ground:<node>` |
| A cache whose owner died with no heir | — | The cache becomes ground |

**Taking.** `take {"from": "ground" | "cache:<aid>" | "bldg:<id>", "item", "qty"}` is a `move` with `why="take"`. The physics:

- The taker must be present.
- Ground is free to take.
- A cache can be taken from if it is unguarded. The depositor and present agents see it (local).
- A building needs its owner's admission, or an attack on its hp.

Whether a take is theft is law: a member's take can be refused or punished under a Land Registry or property Act. Against
non-members, only guards help. This is where "abandoned goods up for grabs" finally means something.

---

## 6. Economy

- **Specialisation from geography, not grants.** Today specialisation comes from the legal distribution of `harvest:<camp>` rights
  (review 16: only Workers earn). On a map, copper is in the hills and food in the river valley. Specialisation becomes a fact of
  location. In the state of nature that is more natural than kernel-granted rights. It also changes review 15 §2.8's "income paths
  for every class": anyone can walk to the forest.
- **Local markets and prices.** Goods have fixed scoring values (`unit_values`), but trades are quantities, so arbitrage pays in
  units: buy 10 timber for 2 copper where timber is plentiful, and sell it for 4 where it is scarce. The `market` building lets
  offers outlive the trader's presence. Price dispersion between nodes and its decay with roads is a clean measurement of trade
  integration (law of one price).
- **Transport cost** is actions (carrying) or caravan time (shipments), plus risk (`danger`, raids). It is real only under
  `ledger: located` (§2.5).
- **The farming ladder and Malthus (review 15, D-36).** These are the strongest economic payoffs:
  - Each node's forest and plots set a local carrying capacity. Overshoot is local, famine is local, and **migration is the release
    valve**. That gives boom-bust dynamics a spatial form: frontier settlement, abandoned villages, refugee waves.
  - Irrigation attached to a plot (U19) makes land tenure at a *place* the precondition of investment, which is the
    institutional question review 15 wanted.
  - Two-parent conception (review 15 §4) needs both parents at one node, which is natural.
- **Without food, almost none of this happens.** If goods are only scored and never consumed (today's economy, review 16 §1:
  "the economy does not starve anyone"), then:
  - where goods sit hardly matters;
  - carrying them costs actions for no reason except the inputs to forts, weapons and children.

  That is the clearest case of cost without payoff, and why §11 Q6 recommends that space wait for review 15 S1-S3 before any
  model spend.

---

## 7. The prompt and context budget

Space can shrink the prompt as much as grow it. Which way it goes depends on N and on the comms dial.

| Layer (`context.DEFAULTS["budgets"]`) | Today | Under space |
|---|---|---|
| Core (cached) | Overview lists *every* camp with its interface (`context.overview`) | Adds the **map**: an adjacency list, one line per node (`Riverbend: Hillfort 2, Mill 1, Coast 5`). About 15 tokens a node, so about 180 for 12 nodes. Static, so it stays in the cached core. Camps are listed per node, and only the local ones in detail |
| State (800) | `Order this round: <all N agents>`: about 300 tokens at N = 100 | **Local only:** "You are at Riverbend (plains, land 8/12). Here: Ada, Bo, +3. Buildings: store S2 (A3), fort F1 (Bo). Ground: 4 timber. Camps: camp2 timber (stock high). In transit to you: none." About 100-200 tokens. The order line lists co-located agents only |
| Feed (3,000) | Every visible event since the last turn. At N = 100, mostly other agents' public posts | Only local events and channels the agent follows (pull). With per-node squares, the feed load falls roughly with the node's share of N |
| Look-ups | — | `route {to}` (path and time). `places` returns "what you saw and when": the last observation of each node the agent has visited, built from events it saw (E, its own perception), as a look-up, never in the prompt |

**Net effect.**

- At N ≥ 24 with 4 or more nodes, the feed shrinks more than the map and local view add. Expect a net saving of 500-1,500 tokens
  per turn.
- At N ≤ 10, the prompt grows by about 300-400 tokens.
- These are estimates from `context` layer budgets, not measurements. `reasoning.jsonl` already records layer sizes per call, so
  the first scripted dry run settles it.

**Map representation for LLMs.** Use named nodes (`Riverbend`, not `n3`), an adjacency list with times, and no coordinates. Models
handle adjacency lists well and coordinates badly. `route` removes path-finding from the test. Haiku-class models will still lose
track of *what is elsewhere* (stale prices, a cache they left). The `places` look-up is the mitigation. Its use is itself a
measurement.

---

## 8. Migration path

### 8.1 Degenerate graphs and byte-identity

- **Space off (the default):** no `k.w["space"]`, no new snapshot keys, no `node` field on events, no new actions. Every existing
  preset is byte-identical, checked by the golden suite and prompt fingerprints.
- **`space.map.kind: single`:** one node holding every camp, everyone present, no edges. Presence gates always pass, `local`
  equals "everyone", and the per-node square equals the one square. **Required test:**
  `difftest --head-set space.enabled=true --head-set space.map.kind=single --ignore-field node --ignore-type channel_seeded`
  over the golden presets (with `law.publication` on, base `today`). It must show no divergence in events, snapshots (besides the
  new keys, dropped by the normaliser) or scores. This proves space is a strict generalisation, as D-34's `code: today` difftest
  proved default code.
- **`from_camps`:** the first map with distance. Not equivalent, by design. It is the "today's world, spread out" preset for the
  first comparison.

The brief suggested a one-node-per-camp graph with zero-distance edges as the degenerate case. It is worse than a single node.

- Zero-time edges still need a `travel` action to be "at" the other camp.
- So it is not equivalent unless presence means "reachable at zero cost". That is a second notion of presence that every gate
  would have to know about.

A single node is equivalent by construction. `from_camps` with edge time `t` is the knob that moves away from it.

### 8.2 Work packages

| WP | Content | Files | Depends on | Size |
|---|---|---|---|---|
| **SP1** Presence | Feature row `space`. `k.w["space"]` (nodes, edges, adj, at, transit). Map kinds `single`, `from_camps`, `authored`. `travel` (routed, L-route) and `arrive` (world, P). Action-unit travel with spill-over. `route` look-up. Presence checks on `harvest`, `attack`, `join_attack`, `guard_bind`, physical `transfer` (still global ledger). Natural audience `local` (publication layer) and `node` on events. `channels.square: per_node` and the `{"node"}` selector; `{"camp"}` reinterpreted. State lines, map in core, transit turns skipped. Snapshot keys `location`, `node_pop` | new `charter/space.py`; `features.py`, `primitives.py`, `action_registry.py`, `eventtypes.py`, `dispatch/checks.py`, `publication.py`, `channels.py`, `context.py`, `runner.py` (transit turns), `tiers.py`, `schema.py` | `law.publication` (W8c), channels v2 (C) | M-L |
| **SP2** Ground and caches | `ground:<node>` and `cache:<node>:<aid>` resolvers. `take` and `stash`. Estates at the death node. Dissolution remainder and unbequeathed estates to ground under space (§5.4). Spoils share to ground. Conservation rows | `accounts.py` (`RESOLVERS`, `SOURCES_SINKS`), `mortality.py` (`_reserve_dst`), `contracts.py` (`_dissolve`), `conflict.py` (`_spoils`), `Kernel.holdings_value` (caches count) | SP1 | S-M |
| **SP3** Located ledger | `space.ledger: global \| located`. A node for every physical account (seat for institutional accounts). The co-location check in `move` for physical items. Currency redemption at the reserve's seat. `relocate`. Library audit (taxes in kind) | `accounts.py`, `dispatch/checks.py`, `contracts.py`, `institutions.py`, `jurisdictions.py`, `library.py` | SP2, WP-D | M-L |
| **SP4** Buildings | Catalogue as data; `build`, `set_building_rule`, demolition via attack on hp; land use. `store` (absorbs review 15 S3), `fort` (migrates `conflict.forts` under space), `hall`, `gate`. Roads as edge projects | `space.py`, `projects.py` (`road`), `conflict.py`, review 15's `subsistence.py` | SP1 (SP3 for halls holding treasuries) | M |
| **SP5** Comms | `space.comms: instant \| latency \| courier`. `delivered` events. Lag filter in `channels.read`/`unread`. Letters as shipments. Relays | `space.py`, `channels.py`, `context.py`, `export.py` | SP1 (SP7 for couriers) | M-L |
| **SP6** Conflict at nodes | Terrain defense; forts at nodes; `battle` summary event; `space.disengage`; ground spoils; gate assault | `conflict.py` | SP1, SP4 | M |
| **SP7** Logistics and markets | Carry limits (dial); `ship` and `shipment:` accounts; interception; `market` standing offers | `space.py`, `accounts.py` | SP3 | M |
| **SP8** Law surface | Reads (`where(member)`, `nodes()`, `route`, `here(node)` counts under evidence rules); hooks `before_travel`, `after_arrive`, `before_build`, `before_take`; library: Border Act (members' emigration), Toll gate, Residence-as-consent gate clause, Land Registry over plots and buildings, Property Act (takes) | `lawapi.py`, `library.py`, `charter/code/` | SP1-SP4 | M |
| **SP9** Export and site | New tables and columns (§9); layout `xy`; site map view | `export.py`, `docs/data_format.md`, site | SP1 | S-M (plus site work) |
| **SP10** Calibration and presets | Scripted travel policies; sweeps over N, nodes and edge times; presets `space_nature` (SP1-SP2 + food) and `space_frontier` (generated map) | `space.py`, `specs/` | SP1, SP2, review 15 S1-S3 | M |
| *later* | Detection by presence (§3.4); `legal_acts: at_seat`; armies and police (BACKLOG); custodian offices | | SP3, SP6, WP-E | L |

Order:

1. SP1, then SP2 and SP9 in parallel.
2. SP4 and SP5 can follow without SP3.
3. SP3 before SP7.
4. SP10 gates any model spend.

Total roughly 8-11 weeks for one implementer. Review 07 estimated 2-3 agent-weeks for "a graph with presence", which matches
SP1 + SP2. The rest is what the owner's list (custody, buildings, battles, delay) actually costs.

### 8.3 The smallest valuable slice

SP1 + SP2 + SP9 (export only), on `from_camps` and a small authored map, with comms `instant` and ledger `global`. It answers:

- Does locality change the communication graph: who DMs whom, and how much of the talk is in local squares?
- Does it change who founds institutions with whom (co-location vs. randomness)?
- How much of agents' action budget goes to travel?
- Do bots strand themselves?
- What happens to abandoned goods: who takes them, and how fast?

It does not answer anything about logistics, custody or information delay. Those need SP3 and SP5. Build SP1 so that SP3 and SP5
are additions, not rewrites:

- the co-location check sits in one function (`space.colocated(k, src, dst, item)`) that SP1 calls only for agent-to-agent
  physical transfers;
- delivery goes through one function (`space.deliver_round(k, src_node, dst_node)`) that returns `k.r` under `instant`.

### 8.4 Test plan

- **Equivalence:** the `single`-map difftest (§8.1) on every golden preset. A golden case `space_pilot` (scripted, `from_camps`, 3
  rounds) added to `tests/charter_golden_cases.py`.
- **Unit tests (`tests/test_charter_space.py`):**
  - Paths are deterministic, with ties broken by id.
  - Spill-over arithmetic: arrival in the same turn, and next turn with the right leftover actions.
  - Transit agents perceive nothing local.
  - Presence gates refuse with a reason naming where the target is.
  - `local` audiences are frozen at log time.
  - A per-node square admits only present agents.
  - `before_travel` blocks members but not non-members.
  - Ground and cache conservation (extend `tests/test_charter_accounts.py`'s scripted run with the new resolvers).
  - Estates land at the death node.
  - A dissolved association's remainder goes to the ground at its seat, and a bystander takes it.
  - Under `latency`, a DM is delivered at `sent + ceil(d / speed)` and appears exactly once in the recipient's feed.
  - Checkpoint and resume mid-transit is byte-identical (the resume-equivalence tests).
- **Contract test:** every new `Act`, `Primitive` and `EventType` registered, with a tier, emits and a renderer.
  `tiers.RULES` gains rows S1..Sn for the spatial rules.
- **Scripted bots:** `space.scripted_actions` (travel to the best-known camp, return to seat, take ground goods, flee a contested
  node), in the `framework.scripted_actions` pattern. The difftest harness runs them offline.
- **Calibration (SP10):** with food on, check across N × nodes × edge time that:
  - travel uses 10-30% of actions;
  - node populations neither all collapse onto one node nor stay fixed;
  - local famines and migration are reachable;
  - stranding is near zero for bots.

---

## 9. Measurement and export (additive only)

Schema 2 promises (docs/data_format.md): new tables and columns bump `schema_minor` only, and readers ignore what they do not know.
Space stays inside that promise.

| Change | Kind | Content |
|---|---|---|
| `events.node` | column | Where it happened (null in spaceless runs) |
| `messages.node`, `messages.delivered_round` | columns | Sender's node; delivery round under latency (equals `round` otherwise) |
| `state` rows | new `key` values (no columns) | `location` (agent → node or `edge:<eid>`), `node_pop`, `node_land_used`, `ground` (node → value), `buildings`. `export.STATE_KIND` gains `location: agent`, `ground: node`, `buildings: building`, `node_pop: node` |
| `nodes` | table | run_id, node, name, terrain, land, defense, camps_json, x, y |
| `edges` | table | run_id, edge, a, b, time, capacity, danger, built_round, built_by |
| `journeys` | table | run_id, agent, depart_round, arrive_round, from, to, path_json, cause_event (the `travel` event) |
| `buildings` | table | run_id, building, kind, node, owner, built_round, destroyed_round |
| `battles` | table | run_id, round, node, sides_json, outcomes_json |

Analyses this enables:

- **Information lag:** the round each agent first could see an event (from `can_see` and delivery) minus the event's round.
- **Spatial Gini** and price dispersion by node.
- **Migration flows** against local food per head.
- **Co-location** as a predictor of institution membership.
- **The control map** (§4.2) over time.

**The site** needs a map view: nodes at `xy`, agents as dots per round, journeys as moving dots, battles as markers, and message
arcs with their delay. That is a new component, not a reskin. Its cost is real and separate from the simulator's.

---

## 10. Costs, risks, and when space is a bad idea

**Space adds cost without payoff when:**

- **There is no consumption.** Covered in §6. Located goods are friction.
- **Comms are instant and the ledger is global.** Then space is a harvest tax plus smaller squares. This is acceptable as SP1's
  *test*, but not as a research world.
- **Agents per node are too few.** At N = 10-15 over 4 or more nodes, each place holds 2-4 agents. Institutions fragment into
  dyads, and the square is empty. Keep about 5 or more agents per node: nodes ≈ N/6 to N/8, at least 3. Charter's typical N of
  10-25 (BACKLOG: "a democracy is a committee") is at the low edge. Space strengthens the case for the larger-population mode.
- **Runs are short.** At 25 rounds, migration and frontier dynamics barely start. Information delay of 2-3 rounds is a tenth of
  the run.
- **The research question is legal design.** Charter's core questions are about laws and institutions agents write. Space spends
  agent attention on walking and spatial bookkeeping, and gives fewer interactions per agent per dollar. If the next studies are
  1984-bench or Constitution-bench (review 13), space is a confound to keep off. One exception: information control under
  latency (pull, couriers) is a genuinely new lever for 1984-style questions.

**Risks:**

- **LLM competence.**
  - Opus-class models will handle adjacency lists and plans.
  - Haiku-class models will strand themselves, forget caches and act on stale news. Measure it: stranding, cache abandonment by
    their own depositors, and decisions on information older than k rounds.
  - Review 15's mitigation pattern applies: make failures visible as metrics, so they are not mistaken for institutional
    outcomes.
- **Run cost.**
  - Skipping turns for pure transit lowers model calls.
  - Smaller local feeds lower tokens per call.
  - Slower development raises the number of rounds needed to see the same institutional depth.
  - Net cost per *finding* is probably higher. Size presets to keep runs short and N moderate.
- **Complexity.** About 10 new primitives, 8-10 event types, 4 account kinds, a dozen spec keys, and changes in conflict,
  channels, context, accounts, mortality, contracts and export. Each is small. Together they are the largest single extension
  since law v2. The defence is the staging, and the single-node equivalence test at every stage.
- **The law library assumes a global ledger** (§5.3). `ledger: located` needs a library pass, or agents will find that library
  taxes fail.
- **The omniscient law** (§3.4) becomes visible on a map. Leaving it in v1 is a stated X choice, not an oversight.
- **Scoring.** Wealth at fixed unit values counts a cache on the far side of the map as fully as goods in hand. That is acceptable
  (titles still count), but it means Wealth goals do not reward logistics directly. Food survival does.

**What would make this a bad idea overall:** the SP1 dry runs and a small Opus pilot show that locality does not change the
communication or founding graph (agents use global DMs exactly as before). In that case the perception payoff is absent, and only
food and custody remain as reasons. If review 15's food economy is also not adopted, stop after SP2.

---

## 11. Decisions for the owner

**Q1. Do messages cross distance instantly, after a delay, or only when someone carries them?**

- The uncertainty: delay is the change that makes space matter most for institutions (governing at a distance, news as power).
  It is also the change most likely to make weak models look incompetent for reasons unrelated to institutions.
- What each answer changes:
  - Instant keeps every channel as today, and space acts only on physical perception.
  - Latency needs SP5 and makes the feed a function of distance.
  - Courier means remote politics needs messengers, which is a hunter-gatherer world.
- **Recommendation:** a world dial with all three. The SP1 pilot runs `instant`, so locality is tested alone. Agrarian presets use
  `latency`, and `courier` is for hunter-gatherer presets.
- **What would change it:** SP1 shows locality has no effect under instant comms. Then skip straight to latency, since the effect
  must come from delay.

**Q2. Do institutions' goods live somewhere, or on a global ledger?**

- §2.5 shows there is no consistent middle for physical goods.
- What each answer changes:
  - Located gives custody, robbery of treasuries, seats that matter, and custodian worlds almost for free. It costs a pass over
    the law library and arrears for remote taxes in kind.
  - Global keeps institutions as smart contracts and transport cost as fiction.
- **Recommendation:** `global` in SP1-SP2, `located` from SP3 on, with physical items located and currencies and shares as ledger.
- **What would change it:** the library pass shows most useful laws break. Then keep `global` as default and `located` as a
  treatment.

**Q3. Does a polity get territory?**

- The uncertainty: whether physical control plus entry-as-consent is enough for territorial polities to emerge at all, or whether
  only a kernel claim produces them.
- What each answer changes:
  - A claim primitive makes territorial states easy and breaks D-37 (a reach over non-members without force).
  - No claim keeps D-37, but territory waits on gates (SP4) and force.
- **Recommendation:** no claim primitive (keep D12 and D-37). Gates with admission rules and entry-as-consent clauses shown at the
  gate. A derived control map for analysis.
- **What would change it:** pilots where institutions want territory and cannot get it for mechanical reasons. Then make gates
  cheaper first.

**Q4. Is travel paid in actions or in rounds?**

- What each answer changes:
  - In actions, short trips fit inside a turn (3-4 actions), long ones spill over, and a 25-round run keeps most of its activity.
  - In rounds, every move costs a whole turn, so a three-hop trip is an eighth of a run. Space then dominates behaviour.
- **Recommendation:** action units, with edge times 1-3 on generated maps, so the diameter is about 2 rounds.
- **What would change it:** agents treat travel as free and churn between nodes. Then raise edge times, or charge one action per
  hop plus the time.

**Q5. Is space a separate simulation family, or a dial on any world?**

- The uncertainty: a dial invites mixing with every module (media2, the Board, E-series prompts), each needing spatial semantics.
- **Recommendation:** a flag in one kernel, but used only by space presets (`space_nature`, `space_frontier`) with their own
  goldens, goals and calibration (review 07's advice). Existing presets never turn it on. Modules without spatial semantics (media2,
  the outside power's raid targeting, the Board) are refused by `schema.validate` under `space.enabled` until each gets a reading.
- **What would change it:** a specific study needs space plus one legacy module. Then add that module's spatial reading then.

**Q6. Must space wait for food (review 15 S1-S3)?**

- The uncertainty: without consumption, space's economic and military payoffs (sieges, famine migration, local markets) are
  absent. With food, two hard calibrations interact.
- **Recommendation:** build SP1-SP2 now (scripted only, no model spend). Run no model pilot of a space world before S1-S3 exist.
  Calibrate food on a single node first (it equals today's world, §8.1), then spread it out.
- **What would change it:** the owner's interest is mainly perception and communication (who talks to whom). Then an SP1 pilot
  without food is informative on its own, at low cost.

**Q7. Should battles stay "each attack disables one agent", or get a battle mechanic (rout, capture, retreat)?**

- The uncertainty: mass disabling at one node could wipe out a local society in a round, and each agent is a costly persona.
- **Recommendation:** no new mechanic in v1. A battle is the set of attacks resolved at a node in one round, plus a summary event
  and ground spoils. Retreat is travelling away before resolution. Add `rout` (a forced move to a neighbour instead of a disable)
  only if pilots show wipe-outs dominate.

**Q8. How many buildings exist in the design arm?**

- The owner dislikes agents being handed too much, but buildings are how space gets institutions.
- **Recommendation:** `store`, `fort` and `hall` only, then `gate` once territory matters. The rest (workshop, market, relay) are
  spec-enabled per study, with catalogue entries as data.

**Q9. Should laws perceive members' remote acts instantly?**

- **Recommendation:** yes in v1, stated as X (§3.4). Make detection-by-presence the first package of the police/armies backlog
  item, because it is what makes police physical.

---

## 12. Honest limits

- **Nothing was run.** Token savings (§7), package sizes (§8.2) and the claim that the single-node map is exactly equivalent are
  reasoned from the code, not measured. The equivalence claim is the one to test first: if `publication.publish` with base
  `today` and a `local` floor of "everyone" does not reproduce today's audiences byte for byte, SP1's design needs a different
  seam.
- **Counts are from grep at `3f4aafc`.** These are 60 `harvest:` sites, 42 move sites and 98 `bal` calls, as indicators of the
  presence surface. Not every one needs a spatial check.
- **Review 15 is not built.** Its stores, fields and food are designed but not in the code. Several payoffs claimed here (sieges,
  famine migration, local markets) depend on it.
- **Space is a world-building commitment.** Every later module (tech, ecology, aliases) will need a spatial reading in space
  worlds. That is the price of a separate family, and the reason not to turn space on in existing presets.
