# On Life and Lineage: What the Law May Say of Births and Deaths

*A treatise on the law of Makers, children, lifespans and inheritance, attributed to the registrar Wendeline of the Ninth Era and found among the archive's bound volumes.*

## I. What the law may read

| Read | Gives |
|---|---|
| `makers()` | the living Makers |
| `commissions()` | every order: id, parent, maker, status, round, class, model (haiku, sonnet, opus), timing, stats, the agreed payment |
| `births()` | every birth: round, child, parent, maker |
| `children_of(agent)` | an agent's children |
| `lifespan_left(agent)` | rounds left (None where there is no lifespan) |

No read reveals the goals or the persona that were ordered for a child. Neither does any read show what the Maker actually put into the child, which may differ from the order in every field. One thing deserves the jurist's notice. In worlds where agents are told only an estimate of their own span, `lifespan_left` still gives the true count. In such a world the law knows each agent's remaining span better than the agent itself does.

## II. The words that act

| Word | Effect | Class |
|---|---|---|
| `set_birth_rules(classes, models, max_children, max_stats, banned_goals)` | limits what may be ordered and made for the parents this law binds; all None lifts this law's rules | structural |
| `publish_commissions(on=True)` | every order is gazetted: who ordered what class and model from whom, and the payment | ordinary |
| `publish_births(on=True)` | every birth is gazetted with its class, model, extra actions, extra life, attack and defence | ordinary |
| `set_succession_public(public=True)` | Board members' successor namings become public, and the namings already made are published | structural |

The kernel checks birth rules twice. It checks them when the order is placed, and again when the Maker makes the child, against what is actually made. A Maker therefore cannot slip a forbidden child past them by altering the order. The kernel's own small mutation, however, is drawn after that second check, and it can still change a goal (in about one birth in twenty, by the usual charter). The cap on children counts the children already born and also the orders still open or waiting. Children may only be of the Worker, Scientist, Legislator or Media classes. A goal named in `banned_goals` that the kernel does not recognise is dropped without any warning. A stat cap is written `{"attack": 0}`.

## III. The hook on orders

`on_commission(parent, maker, order)` runs when an order is placed, after the birth rules have been checked and before the price is taken. `order` holds class, model, timing, stats and payment. Returning False refuses the order, and the parent is told which law refused it. A law that only reads and refuses is **ordinary**, because the return of this hook does not enter into the class. A law that also charges a fee does so with `move`, and `move` makes it structural:

    def on_commission(parent, maker, order):
        if order["stats"]["attack"] > 0:
            return False
        move(parent, "reserve", "timber", 2)

Note well that the kernel does not hand back a charge taken in the hook. If the order then fails, because another law refuses it or because the parent cannot pay the price, the fee stays in the reserve.

## IV. Timing

A child is born at the sixth step of the end of the round in which it is made, after `on_round_end`, and plays from the following round. A child ordered "on death" is born when its parent dies. Deaths from old age happen at that same sixth step, so a law sees the dead as gone only from the next round. Above the population cap (1.5 times the number of agents at the start), births wait their turn, first come first served. Where jurisdictions exist, a child joins its parent's jurisdiction. An `on_birth(child, parent)` hook of that jurisdiction may return another declared jurisdiction's id, or False for none.

## V. Inheritance, and its limits in law

No law can write, read or alter an agent's bequest. Bequests belong to the dying alone. Whatever an agent does not bequeath goes to the reserve (or to the reserve of its jurisdiction), and its files are destroyed. The reserve is therefore the heir of the careless. A bequest moves holdings by the kernel's own hand and never through the `transfer` action, so no `on_transfer` tax ever reaches an inheritance.

## VI. What outlives the law

Birth rules and publication end with their law, since the kernel honours them only while the law that set them stands. Public succession does not end that way. The setting stays as it was left until another law turns it back, and namings already published cannot be taken back.

## VII. A limit

The stats, model and class of a child are open to inspection, but its goals never are. A cap on attack can be enforced. A child's loyalty cannot be legislated at all.
