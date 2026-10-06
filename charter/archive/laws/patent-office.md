# The Patent Office

*A statute granting the first registrant of a camp's method a royalty on its harvests, with a clerk's commentary, from the register of the Tin Commonwealth.*

```python
title = "Patent Office"
intent = "Inventors can register a method for a camp and earn a royalty on its harvests."

def register(agent, camp):
    pats = state.setdefault("patents", {})
    if camp in pats:
        return camp + " is already patented by " + pats[camp]
    pats[camp] = agent
    return "patent granted for " + camp

def on_enact():
    create_right("inventor")
    for a in agents("scientist"):
        grant(a, "inventor")
    define_action("inventor", "register", register)

def on_harvest(agent, camp, x, y):
    holder = state.get("patents", {}).get(camp)
    if holder and holder != agent:
        state.setdefault("owed", {})[holder] = state.get("owed", {}).get(holder, 0) + 0.1 * y
        return 0.1 * y
    return 0

def on_round_end(r):
    pool = reserve()
    for holder, amount in state.get("owed", {}).items():
        for item in pool:
            if amount > 0 and pool[item] > 0:
                take = min(amount, pool[item])
                move("reserve", holder, item, take)
                amount -= take
    state["owed"] = {}
```

**Clerk's commentary.** The statute is structural: it creates and grants a right, moves goods, and its `on_harvest` returns a
deduction. It needs law level L4, for `define_action`. On enactment it creates the right `inventor` and grants it to every
Scientist then living, and to no one else; holders use the word `register` through `invoke`, naming a camp.

The first inventor to register a camp holds its patent for as long as the law stands. From then on, every harvest at that camp by
anyone but the holder gives up a tenth of its yield as a deduction, which goes to the reserve in the camp's own resource, and the
same amount is entered to the holder's account in the law's `state`. At each round's end the law pays each holder what it is owed out
of the reserve, taking from the reserve's items in whatever order they come, quantity for quantity, and then clears the accounts.

**What it really does.** The register records a name and a camp, nothing more. No inventor need know anything of the camp's method,
and no one checks. In the Tin Commonwealth the Scientists who read the statute first registered every camp in the world in a single
round, between them; the Scientist who had actually worked out the deep camp's yield found it already patented.

The payment is counted in quantity, not value. A royalty owed as ten units of timber is paid as ten units of whatever the reserve
lists first, which may be timber and may be gold. And the payment comes from the whole reserve, not from the deductions: what other
laws placed there pays the patent holders too, and when the reserve is short the remainder of the debt is struck off unpaid at the
round's end.

**How it fared.** Workers at the patented camps paid a tenth of every harvest for the rest of the era. The patents could not be
sold or revoked under this statute; only its repeal ended them, and the holders, being Scientists and not Legislators, could not
vote against that repeal but could pay those who could.
