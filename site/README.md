# site

The Charter website: static HTML, CSS and ES modules (no node, no bundler), reading runs straight from the Hugging Face dataset.

| Page | What |
|---|---|
| `index.html` | the experiment, stories from the runs, featured runs, notes, open data |
| `runs.html` | the registry: every run in `catalog.json`, with search and filters |
| `run.html?id=RUN_ID` | one run: Story (the full story viewer), Conversations, Agents, Laws, Data |
| `notes.html`, `note.html?slug=` | analysis posts: markdown files in `notes/` with front matter (title, date, summary, draft) |

Three designs share one structure (switch in the header, or `?theme=swiss|broadsheet|night`); they are CSS variables plus a few
overrides in `assets/site.css`.

## Run it locally
```bash
python site/build.py                                   # viewer.html, notes/index.json, assets/mascots.svg
python -m charter publish RUN... --card site/cards.yaml --with-viewer-json --staging charter/out/site-data
ln -sfn ../charter/out/site-data site/_data            # the site reads _data on localhost, the Hub elsewhere
python3 -m http.server 8790 --directory site           # http://localhost:8790
```
`?data=hf` reads the published dataset instead of `_data`; `?data=URL` reads any copy.

## Pieces
- `lib/charter-data.js`: the data layer (catalog, run tables, channels, threads, inboxes, turns); commit-pinned, cached, lazy.
  Follows export schema 2 (docs/data_format.md) and derives messages/channels from `events` for older exports.
- `viewer.html`: generated from `charter/viewer/template.html` by `build.py`, adding `?src=URL` (load a run's viewer.json).
- `cards.yaml`: curated titles, descriptions, tags and featured flags for `charter publish --card`.

## Temporary (until export schema 2 lands)
- The Story tab loads `viewer.json`, the story viewer's own data file, written by `publish --with-viewer-json`. Once the viewer
  reads the Parquet tables through `lib/charter-data.js`, drop the flag and the file.
- Conversations use the schema-1 fallback (messages derived from `events`) until the exporter writes `messages`/`channels`.
