"""The primitives' changes (W8a): one module per domain, each change a row's `fn` ("dispatch.changes.<domain>:do_<name>",
(k, **payload, **options) -> dict result). Most changes are made by the feature module that owns the state (jurisdictions,
contracts, credit, media, conflict, courts, camptypes); their do_* here adapt the payload to its function."""
