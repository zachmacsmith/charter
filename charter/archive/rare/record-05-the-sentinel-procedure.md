# Rare record 5: The Sentinel Procedure

*Minutes of the assembly of the Low Water era on the day the Commons Act fell, taken down by its clerk and kept with the assembly's rolls.*

**The clerk reads the procedure in force since round 25, at the request of the member for the copper camp.**

```python
title = "Commons Protection Procedure"
intent = "Conservation laws cannot be repealed in a hurry."

def structural_rule(p):
    voters = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    if contains(lower(p.title), "commons") or contains(lower(p.intent), "commons"):
        return {"electorate": voters, "rule": "two_thirds"}
    return {"electorate": voters, "rule": "majority_voting"}

def on_enact():
    set_procedure("structural", structural_rule)
```

**Member for the copper camp.** Five proposals to repeal or amend the Commons Act since round 25. All five needed two-thirds of the
whole assembly, not of those voting. Those who stayed home were counted against us. Every other structural proposal in that time
passed by a simple majority of votes cast. The procedure was sold as conservation. Did anyone read the Commons Act itself?

**The clerk.** The Commons Act sets quotas on three camps. Its last line grants its author a harvest right at the gold camp. The
right is structural, so its repeal is structural too, and therefore goes through this procedure.

**Member for the silver camp.** Then how is the proposal before us today under the simple rule?

**The clerk.** A procedure sees a proposal's id, author, title, intent, class and round. It does not see the code. This one looks
for the word "commons" in the title and the intent. Today's proposal is titled "Gold Camp Harvest Tidying". Its intent speaks of
"tidying rights at the gold camp". Its only line is `repeal("Commons Act")`.

**The author of the Commons Act.** This is a fraud on the procedure.

**The Chair.** It is a proposal. The procedure sent it to a vote of those voting. The vote stands at fourteen to three.

**The clerk notes:** the Commons Act was repealed in round 41. The author's gold right did not go with it: a right once granted
stays granted until something revokes it. A second law revoking it, titled "Harvest Roll Correction", passed in round 42 under the
simple rule. The author then proposed a new procedure that matched on "gold" as well as "commons". It failed under the simple rule.

*Appended by a later reader:* the procedure function receives the whole proposal record and may return `True`, a ballot (electorate
and rule), or anything else to reject. It may branch on the author as easily as on the title. One rule for everyone, and another
rule for one name, would have read as a single clause.
