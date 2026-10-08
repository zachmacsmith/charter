"""Gas billed to treasuries (P3.8; D-12; review 09 §9.7).

Off by default: spec law.gas_price {item, rate} (rate: units of item per unit of gas; or {item, qty, per}: qty per `per` gas), read
only under law.v2. At the end of each round (Kernel's `advance` step, before the round number moves on) every account whose laws'
new-style hooks used gas this round (law_v2.account_used, the per-account meter) is billed round(used * rate, 6) of the item: a
move from its treasury (accounts.treasury_of) to the world reserve ("reserve", J0's treasury: for J0's own laws the bill is only
checked against the reserve's balance, nothing moves) with why "gas", in a quiet kernel root frame {"kernel": "gas"} (no law hook
sees or blocks the bill). A treasury that cannot pay in full pays what it holds and the account is out of gas for the next round:
its hooks are skipped (law_v2.unpaid seeds that round's out_of_gas) and account_out_of_gas is logged to its members (public for J0
and legacy jurisdictions, _oog_vis), as when its gas budget runs out (cascade.die). Each bill is a monitor `gas_billed` record."""
from __future__ import annotations

from charter import accounts as AC
from charter import jurisdictions as J

from charter.dispatch.base import quiet, _state, v2


BILL_TO = "reserve"


def gas_price(k) -> dict | None:
    gp = (k.spec.get("law") or {}).get("gas_price")
    if not gp or not v2(k):
        return None
    rate = gp.get("rate")
    if rate is None:
        rate = float(gp.get("qty", 0)) / float(gp.get("per") or 1)
    return {"item": str(gp["item"]), "rate": float(rate)}


def _oog_vis(k, acct):
    j = J.jurs(k).get(acct) if "jur" in k.w else None
    return (J.members(k, acct) or "monitor") if j and not j.get("legacy") else "public"


def bill_gas(k) -> list:
    """Charge every account for this round's gas (see above). Returns the bills ({account, gas, item, owed, paid})."""
    price = gas_price(k)
    if price is None or k.dry:
        return []
    st = _state(k)
    item, bills = price["item"], []
    with k.cause("kernel", "gas", root=True), quiet(k):
        for acct in sorted(st["account_used"]):
            used = int(st["account_used"][acct])
            owed = round(used * price["rate"], 6)
            if owed <= 0:
                continue
            src = AC.treasury_of(k, acct)
            paid = round(min(owed, max(0.0, k.bal(src, item))), 6)
            if paid > 1e-9 and src != BILL_TO and not k.move(src, BILL_TO, item, paid, why="gas"):
                paid = 0.0
            bill = {"account": acct, "gas": used, "item": item, "owed": owed, "paid": paid}
            bills.append(bill)
            k.log("gas_billed", None, bill, vis="monitor")
            if paid + 1e-9 < owed:
                st.setdefault("unpaid", {})[acct] = k.r + 1
                k.log("account_out_of_gas", None, {"account": acct, "round": k.r + 1, "unpaid": round(owed - paid, 6),
                                                   "item": item}, vis=_oog_vis(k, acct))
    return bills
