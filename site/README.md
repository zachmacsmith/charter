# site

The Charter website's data layer (the site itself comes next).

- `lib/charter-data.js`: reads published runs in the browser straight from the Hugging Face dataset (catalog, run tables,
  channels, threads, inboxes, turns). File URLs are pinned to one dataset commit and cached; tables are fetched lazily, once.
  Follows export schema 2 (docs/data_format.md) and derives messages/channels from `events` for runs exported before it.
- `demo/index.html`: a bare runs → channels → thread browser over that module.

Try it against a local staging copy (`python -m charter publish RUN ... --staging DIR`, then `ln -s DIR site/_data`):

    python3 -m http.server 8790 --directory site      # open http://localhost:8790/demo/?base=/_data

Against the published dataset: http://localhost:8790/demo/ (optionally `?repo=OWNER/NAME`).
