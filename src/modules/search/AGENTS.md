# Search Module Rules

Inherits the root AGENTS.md. Public interface: `SearchService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership & Dependencies

- Own Verbum dictionary search, upstream validation, dictionary-specific HTML parsing, search cache and per-account search rate limiting. Do not create cards or define card uniqueness here; decks owns stored content.
- Dependency direction: search router → public auth dependency → materialized confirmed account. Auth completes its database scope before search performs external I/O. SearchService has no PostgreSQL access and runs outside DB transactions.
- Inject DictionaryClient and SearchCache Protocol implementations. API lifespan owns the shared httpx client; dependency assembly supplies Redis cache and rate limiter. Do not contact Verbum during startup.

## Request & Result Contract

- `GET /api/v1/search` requires an access token and confirmed account. Normalize query with strip/lower; require 1–200 characters after normalization and reject ASCII control characters. Require page ≥ 1. Allow spaces, hyphens, apostrophes, Latin characters and combining accents; do not strip diacritics or restrict input to one Cyrillic word.
- Forward the requested page unchanged. Search matches article content, not only headwords. Do not add exact-headword filtering, hidden page traversal, cross-page deduplication or automatic merging of dictionary articles.
- Preserve article identity as `(dictionary_id, article_id)`; IDs are opaque strings, not normalized headwords. Assign dictionary names from the explicit supported dictionary map. Stable-sort each page by configured dictionary priority; preserve upstream order within each dictionary.
- Return query, articles, term_suggestions and pagination. Keep suggestions independent of articles: they may accompany an empty or out-of-range page. Do not convert suggestions into articles or assume their order is stable.
- Preserve `requested_page`, `upstream_current`, `upstream_total`, `upstream_relation`. Observations from 2026-11-20: Total counted pages, not articles; `замак` had Total=3 and 29 articles; Current echoed even page=999; Relation was `eq`. These are observations, not a guarantee for unknown Relation values. Do not invent an article count or reinterpret pagination without verifying upstream semantics and reviewing the public contract.
- Empty and out-of-range results are successful 200 responses. Invalid input is 422. Never turn an upstream/cache failure into an empty success.

## Parsed Content Invariants

- Keep separate entries for separate headword paragraphs/homonyms within one article. Preserve alternative_headwords within a header. Do not merge separate articles or entries by spelling.
- Preserve headword text and supplied accents. `accent` is the full headword containing a combining acute accent, otherwise null; never calculate an accent position or invent stress.
- Keep header, ordered senses with supplied number or null, ordered blocks, phrases and related content. Keep examples with their owning sense and preserve their order relative to definitions and notes. Do not attach phraseology to the last sense.
- Block kinds are definition, translation, synonyms, example, note, phrase and related. Preserve label text and supplied explanation or null. Preserve grammar, cross-references, alternative inflections, bibliographic notes and meaningful punctuation.
- Return plain text only; never expose upstream HTML. Do not guess separate original/translation fields from bilingual example text, split synonym groups by commas, or invent numbered senses from `/` and `//` submeanings. Table appendices remain textual notes; do not claim structured declension support.

## Dictionary Parsing Rules

- Keep HTML interpretation in parser.py and strict upstream JSON schemas in external.py. Validate the configured dictionary set and every article's dictionary ID before parsing. Unsupported structure must fail the complete search; never silently skip an article or fall back to stripped HTML.
- TSLM-2022 (`tsblm2022`): strong.hw headwords, strong numbered senses, v-ex examples, strong.phr phraseology, standalone ○/◊ section markers and related forms after `||`.
- TSBM (`tsbm`): strong.hw headwords, examples embedded in sense paragraphs, bibliographic notes identified by midnightblue styling, phraseology after standalone •••. A phrase heading may contain v-ex; keep it in phraseology. Attach adjacent punctuation to its bibliographic note.
- Klyshka (`klyshka`): synonym text may appear outside paragraphs. Preserve separators including `;` and `□`, italic labels and the original synonym ordering.
- RBS (`rbs10`): b.hw headwords, b numbered senses, examples in p.ms-3 and phraseology after standalone ◊. A translation may occupy the header paragraph. Superscript Roman homonym indices and grammar alone must not create a translation sense.
- RBS also uses plain sequential sense numbers in the header or after an example's semicolon. Split these before assigning paragraph semantics; keep header grammar separate and assign the following translation to the new sense. Do not interpret numbers inside bold example originals, italic explanations or phraseology as sense boundaries. Preserve nonsequential numbers as text. Regression: `собака` must have senses 1/2, two examples under sense 1 and `слімак` under sense 2.
- Concatenate span.accent fragments without inserted spaces. Search highlight tags may cross semantic tag boundaries; ignore their wrapper while preserving text. Reject active content. Standalone section markers switch sections without becoming content blocks.

## Cache, Rate Limits & Failures

- Apply the per-account Redis limiter before cache lookup. Every admitted attempt consumes budget, including cache hits and upstream failures. Exceeded budget returns 429 with Retry-After; Redis failures fail closed with 503.
- Cache only complete successful results, including empty results. Include normalized query, configured dictionaries, page and PARSER_VERSION in cache identity under the configured key prefix. Do not extend TTL on a hit. Invalid cached DTO data is a miss. Cache I/O failure is 503.
- Increment PARSER_VERSION whenever parsing semantics change so previously cached interpretations are not reused. Keep cache TTL at least 30 days; TTL is not a durability or capacity guarantee.
- Use configured HTTPS endpoint, timeouts and bounded retries. Retry only network/timeouts and upstream 429/502/503/504. Exhaustion maps to SearchUnavailableError (503); other HTTP errors, redirects, invalid JSON, dictionary mismatch or unsupported HTML map to SearchInvalidResponseError (502). Cache errors map to SearchCacheUnavailableError (503).
- Support only the configured nonempty unique subset of tsblm2022, tsbm, klyshka and rbs10. Adding a dictionary requires an explicit parser, name mapping, validation updates and regression coverage; do not accept arbitrary upstream dictionaries.

## Change Verification

- For parser fixes, capture a minimal real upstream article under tests/fixtures/verbum and assert semantic output in tests/test_search_parser.py. Cover sense boundaries, example ownership, labels and section separation affected by the fix. Use synthetic cases for ambiguous numbers and markup edge cases; do not rely only on live upstream availability.
- Run `make test` plus the root-required Ruff and strict mypy checks for application changes. Existing fixtures cover homonym indices, header translations, phrase markers, bibliographic punctuation, alternative headwords and inline RBS senses; keep these regressions passing.
- Parser support is limited to covered structures. A successful sample does not prove all Verbum articles are supported. Do not record historical manual checks as permanent correctness guarantees.
