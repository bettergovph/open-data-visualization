# Rust route and source inventory

Inventory of routes registered by the Actix application in `src/main.rs` and `src/project_documents.rs`, with the associated template, data inputs, and upstream service. “Hidden” means not exposed in the old primary navigation in `templates/visualizations_home.html` / `templates/navbar.html`; it does not mean access-controlled. There is no authentication middleware on these routes.

## Hidden and less-discoverable page routes

| Route | Page/template | Status in old navigation | Data/source trail |
|---|---|---|---|
| `/integrated` | `templates/integrated.html` or `templates/mobile/integrated.html` | Explicitly removed from desktop/mobile nav; homepage card is `display:none` | SSP, DIME, PhilGEPS, DPWH InfraWatch microsite, and DPWH Transparency are the page’s named sources. Representative views load `/api/dynasty-projects/congressmen`, `/api/dynasty-projects/congressman?name=...`, and related overview/coverage APIs. Local representative caches are `static/data/congressman-projects-*/all-projects-cache.json` and `summary.json`; representative list/config is `static/data/dynasty-projects-config.json`. Project search uses `/api/integrated/projects`; integration chart reads `static/data/integration_venn_data.json`. The Rust app registers only `/api/integrated/projects` and the single-representative cache endpoint, not all API paths fetched by the template (see “Route gaps”). |
| `/hours` | `templates/hours.html` | Described as Secret; not in main nav | Static `static/data/hours.json`. |
| `/circles` | `templates/circles.html` | Handler comment says unpublished; not in main nav | Static `static/data/philippines-regions.json`; visualizes coordinates/data quality. |
| `/integ2026` | `templates/integrated_matrix.html` | Not in main nav | `/api/integrated/matrix` serves `static/data/integrated_matrix.json`; Python API source uses 2026 amendment data `static/data/budget_amendments_2026.json`, historical/resurrected/flagged JSONs, and location data such as `data/parquet/unified_locations.parquet`. Several template API requests are not registered in Rust (see gaps). |
| `/dpwh2026` | `templates/dpwh2026.html` or mobile template | Not in main nav | Rust proxies only `/api/dpwh2026/projects` and `/api/dpwh2026/summary` to Python (`PYTHON_API_URL`, default port 8001). The template also calls stats, repeated, hierarchy, risk, distribution, diff, and multi-flag endpoints not registered in Rust. |
| `/family?surname=…&province=…` | `templates/family.html` | Not in main nav | Template calls Python dynasty family/roster APIs; those routes are not registered in Rust. |
| `/zaldy` | `templates/zaldy.html` | Not in main nav | Template calls `/api/zaldy/dpwh-projects`; no matching Rust route. |
| `/zarah` | `templates/zarah.html` | Not in main nav | Investigation page; inspect its static and API references before treating it as a complete source pipeline. |
| `/dynasty-projects` | `templates/dynasty-projects.html` | Not in primary nav | Related Python dynasty-project APIs and caches; only `/api/dynasty-projects/congressman` is registered in Rust. |
| `/budget-trivia-mobile` | `templates/mobile/budget-trivia.html` on mobile; redirects desktop to static preview | Not in main nav | `static/nep-preview/budget-trivia.html` / mobile template. |
| `/static/nep-preview/ignorant.html` | Redirect handler | Not a content page | Permanent redirect to `/static/nep-preview/congress.html`. |
| `/static/nep-preview/budget-trivia.html` | Redirect/device handler | Not a content page | Desktop serves static preview; mobile serves mobile template. |

Other routes such as `/eogo`, `/budget-nep-correlation`, `/budget-flood-correlation`, `/flood-dime-correlation`, `/contractor-district-correlation`, and `/dynasty-poverty-correlation` are in the Actix router and are linked contextually from some pages, but are absent from the old primary menu. They render their corresponding templates; map each template’s fetch calls to the Python APIs and static JSON/parquet files before relying on its figures.

## Rust API and proxy routes

| Route | Handler behavior | Source / dependency |
|---|---|---|
| `GET /api/integrated/matrix` | Returns a static JSON file | `static/data/integrated_matrix.json`. |
| `GET /api/integrated/projects` | Proxies query to Python | `{PYTHON_API_URL}/api/integrated/projects`, default `http://127.0.0.1:8000`. Python handler reads `data/parquet/integrated_projects_classified.parquet` if present, otherwise falls back to `data/parquet/integrated_projects.parquet`. The Actix query struct currently forwards only `page`, `limit`, `project_name`, and `contractor`, so other Python filters/modes (including `green` and `dpwh_all`) are dropped by this Rust proxy; this workspace has `integrated_projects_matched.parquet` and `tmp_integrated_projects_classified.parquet`, but not those exact preferred filenames. Confirm deployed file names/config before assuming which dataset is served. `green`/`dpwh_all` mode reads `static/data/budget_amendments_2026.json` and supporting flagged/resurrected project files. |
| `GET /api/dynasty-projects/congressman?name=…` | Converts name to slug and returns a local JSON cache | `static/data/congressman-projects-{slug}/all-projects-cache.json`. |
| `GET /api/mpb/top-buildings` | Proxies to Python | `{PYTHON_API_URL}/api/mpb/top-buildings`, default port 8000; source is selected in Python handler and should be checked against current parquet/cache filenames. |
| `GET /api/dpwh/contract-splitting` | Proxies to Python | `{PYTHON_API_URL}/api/dpwh/contract-splitting`, default port 8001. |
| `GET /api/dpwh2026/projects` | Preserves query string and proxies | `{PYTHON_API_URL}/api/dpwh2026/projects`, default port 8001. |
| `GET /api/dpwh2026/summary` | Proxies to Python | `{PYTHON_API_URL}/api/dpwh2026/summary`, default port 8001. |
| `GET /api/nep-documents/{code}` | Optional document-worker proxy | `DOCUMENT_SERVICE_URL` (default `http://127.0.0.1:8879`); accepts only `2027DPWH-Proposal-` plus five digits. Nested tail route permits GET/POST after path validation. |

## `/integrated` source map and caveats

1. Actix serves `templates/integrated.html`; mobile requests use `templates/mobile/integrated.html`.
2. The representative list is backed by Python’s `/api/dynasty-projects/congressmen`, which reads `static/data/dynasty-projects-config.json` and per-representative caches. Party-list rows are identified from the config’s `is_partylist` field or absence of geographic district fields.
3. Project rows and cost summaries are from the individual caches under `static/data/congressman-projects-*`. Their summaries combine sources and may contain cross-source overlap; they are not official party-list budget allocations.
4. The integrated project search is a separate pipeline: Rust forwards `/api/integrated/projects` to Python. Python intends to read a classified integrated-project parquet and exposes source/match fields. The local parquet directory currently has similarly named but not identical files; deployment configuration and generation scripts determine the active file.
5. The page also calls APIs absent from Actix, including `/api/integrated/coverage`, `/api/dynasty-projects/congressmen`, `/api/dynasty-projects/overview`, `/api/dynasty-projects/overview`, and `/api/province-projects/...`. Their Python implementations/caches exist in `visualization.py`; standalone Rust deployment needs an upstream router/proxy for them.
6. Named source stores in this workspace include `data/parquet/dime_projects.parquet`, `data/parquet/philgeps_contracts.parquet`, `data/parquet/microsite_projects.parquet`, `data/parquet/transparency_projects.parquet`, plus integrated/matched/classified project parquets and the individual representative JSON caches. SSP is represented in unified source records/caches rather than a standalone `ssp_*.parquet` in this checkout.

## All remaining Actix page routes

`/`, `/budget`, `/flood`, `/dime`, `/nep`, `/map`, `/mpb`, `/philgeps`, `/dynasty`, `/budget-nep-correlation`, `/budget-flood-correlation`, `/flood-dime-correlation`, `/contractor-district-correlation`, `/dynasty-poverty-correlation`, `/eogo`, and `/sources` are also registered in `src/main.rs`. `/family`, `/zaldy`, `/zarah`, `/circles`, `/hours`, `/integrated`, `/integ2026`, and `/dpwh2026` are registered page routes above. Static files are mounted at `/static` and `/static/nep-preview`.

## Route gaps to resolve or track

The Rust router is not a complete mirror of every endpoint requested by its templates. In particular, `/integrated`’s congressman list, coverage, overview, province-project, and search APIs do not appear in the Actix route table. The templates may depend on a separate Python service or reverse-proxy rules. Verify deployment routing before assuming Rust alone serves the microsite end to end. Likewise, `templates/dpwh2026.html`, `templates/integrated_matrix.html`, `templates/family.html`, and `templates/zaldy.html` request API paths not registered in this Rust app.

## Source files checked

- `src/main.rs` — page and API route registration and proxy handlers.
- `src/project_documents.rs` — optional on-demand NEP document proxy.
- `templates/visualizations_home.html`, `templates/navbar.html` — old navigation visibility.
- `templates/integrated.html`, `templates/integrated_matrix.html`, `templates/dpwh2026.html` — frontend API calls.
- `visualization.py` — Python APIs and their cache/parquet sources.
