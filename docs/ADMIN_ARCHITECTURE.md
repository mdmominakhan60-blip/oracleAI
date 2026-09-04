# OracleAI Admin Architecture

## Purpose

The admin panel is a static, same-origin Telegram WebApp served by FastAPI. Its DOM shell remains in `admin/index.html` so the server can keep stable accessibility and visual selectors, while behavior and styling are split into independently testable modules.

## Frontend boundaries

```text
admin/
├── index.html                         # stable DOM shell and accessibility contract
├── admin.js                           # thin ES-module entrypoint
├── admin.css                          # stable CSS entrypoint
├── pixel-reconstruction.css           # stable visual precision entrypoint
├── src/
│   ├── app.js                         # AdminApplication composition root
│   ├── core/runtime.js                # AdminApiClient, AdminState, action bus, shared helpers
│   ├── components/charts.js           # ChartRenderer presentation component
│   └── features/
│       ├── dashboard.js               # analytics and payment health
│       ├── users.js                   # CRM, user drawer, grants and access actions
│       ├── commerce.js                # orders, catalog and payment reconciliation
│       ├── engagement.js               # promo codes and broadcasts
│       ├── content.js                 # content CRUD editor
│       ├── settings.js                # settings, flags and administrator roles
│       ├── observability.js          # horoscopes, costs, safety and audit
│       └── logs.js                    # filtered realtime system-log stream
└── styles/
    ├── 00-foundations.css
    ├── 10-shell.css
    ├── 20-components.css
    ├── 30-feature-surfaces.css
    ├── 40-responsive-accessibility.css
    └── 50-pixel-reconstruction.css
```

`AdminApplication` is the only composition root. Feature classes own their event listeners, API calls and rendering for one bounded context. `AdminApiClient` owns Telegram headers, development identity propagation, error normalization and downloads. `AdminState` contains cross-feature state; feature-to-feature actions are explicit through the small `AdminActions` object rather than hidden globals.

## Extension workflow

A new screen should add one class under `admin/src/features/`, register one loader in `AdminApplication`, and keep DOM construction scoped to that feature's view. Shared formatting, tables, escaping and API behavior belong in `core/runtime.js`; reusable visualization belongs in `components/`. A feature must not reach into another feature's private methods. The logs screen additionally owns its stream AbortController and reconnect policy, so leaving the screen or applying a filter cannot leak a long-lived reader.
 If cross-feature navigation is needed, use `actions.navigate`, and if a user detail must open, use `actions.openUser`.

The backend logs transport lives in `app/core/log_stream.py` and `app/api/routers/logs.py`. `LogStream` is a bounded process-local ring buffer fed by the existing redacting logging formatter. The API exposes a filtered history endpoint and an authenticated SSE endpoint; the browser uses `fetch` streaming rather than native `EventSource` so Telegram init data can remain in the request header. This is an operational tail window, not a replacement for stdout/file log retention, and it never stores raw log messages before redaction.

CSS is organized by responsibility rather than screen order. The two root stylesheets are intentionally stable compatibility entrypoints because FastAPI and the Telegram WebApp already expose those URLs. New rules should be added to the appropriate file under `admin/styles/`, not to the entrypoint. The server computes the admin asset version recursively across all `.js`, `.css` and `.html` files, so changes in nested modules invalidate the HTML asset query string.

## Security and accessibility invariants

All API requests remain same-origin and carry `X-Init-Data`; development `dev_user` is still limited to development mode by the backend. Feature modules must continue to escape untrusted values before inserting HTML, preserve permission checks through `AdminState.can`, and keep destructive actions confirmation-gated. The stable HTML IDs, `data-view` attributes, skip link and minimum touch target rules are regression-tested by API and Playwright contracts.

## Testing

Use `node --check admin/admin.js admin/src/**/*.js` for module syntax, `pytest -q` for backend and contract regressions, `python3 scripts/admin_visual_contract.py` for desktop/mobile accessibility geometry, and the standard frontend build/static checks. Generated bundles and screenshots remain outside tracked source unless a release evidence task explicitly requires them.
