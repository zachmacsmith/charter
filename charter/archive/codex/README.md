# The codex (monitor notes; not an article)

Codex articles describe what the agents' prompt leaves out: hidden powers (secret actions used through `invoke`) and lore
about them. The law-language articles (`codex/law/*`) are generated from `charter/lawdocs.py` according to the spec's
`law_docs` setting and are not files. Each file here starts with a frontmatter block:

- `tier`: common | uncommon | rare | legendary | false (false articles are plausible but wrong)
- `title`: shown to the holder in its prompt
- `capabilities`: hidden powers whose word and use the article teaches (knowing a power)
- `false_claims` (false articles only): what is wrong in it

Who starts with which article, who holds which power, tips, discoveries and every use are recorded in instance.json
(`hidden`), ground_truth.json (`hidden`), spec_outline.md and events.jsonl (monitor-only events). See `charter/hidden.py`.
This folder is not part of the Scientists' ordinary archive (archive.docs skips it).
