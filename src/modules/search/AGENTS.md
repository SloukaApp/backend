# Search Module Rules

Inherits the root AGENTS.md. Public interface: `SearchService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership & Dependencies

- Own Verbum dictionary search, upstream validation, dictionary-specific HTML parsing, and search cache. Do not create cards or define card uniqueness here; decks owns stored content.
- Dependency direction: search router → public auth dependency → materialized confirmed account. Auth completes its database scope before search performs external I/O. SearchService has no PostgreSQL access and runs outside DB transactions.
- Inject concrete VerbumClient and RedisSearchCache instances. API lifespan owns the shared httpx client; dependency assembly supplies RedisSearchCache. Do not contact Verbum during startup.

## Request & Result Contract

| Operation | Dictionaries | Entry fields beyond `word` and `source` |
| --- | --- | --- |
| `GET /api/v1/search` | `tsblm2022`, `tsbm` | `alternative_words`, `homonym`, `grammar`, `phrases`, `definitions`, `related` |
| `GET /api/v1/translate` | `rbs10` (Russian to Belarusian) | `alternative_words`, `homonym`, `grammar`, `phrases`, `translations` |
| `GET /api/v1/synonyms` | `klyshka` | `synonyms` (text) |

- All operations require a Bearer token and confirmed account. Require `query`, reject ASCII controls, normalize with strip/lower and require 1–200 normalized characters. Accept `page` ≥ 1, default 1, and forward it unchanged.
- Intersect the operation's dictionary IDs with `VERBUM__DICTIONARY_IDS` in configured order. An empty intersection returns 503 after authorization, without an upstream request.
- Return `query`, `items`, `suggestions` and `pagination`. Keep suggestions on empty or out-of-range pages, which return 200. Preserve `requested_page`, `upstream_current`, `upstream_total` and `upstream_relation`. Pass Verbum's Total through without treating it as an article count.
- Stable-sort by configured priority and preserve upstream order within a dictionary. Matches can occur anywhere in article content. Keep separate entries for each headword or homonym and allow the same `source` to recur. Source holds opaque `dictionary_id`, `article_id` and the explicit dictionary name. Do not merge articles or filter by exact headword.
- Declare 200, 401, 403, FastAPI's 422, 502 and 503 in OpenAPI. The three response schemas and service result DTOs are distinct.

## Parsed Content Invariants

- Keep header, ordered senses and blocks, phrases and related content during parsing. Preserve labels and available expansions there. Public projections use plain text and retain the dictionary's abbreviations, punctuation and accents.
- Keep headword variants and their forms. Extract homonym indices only from explicit markup. Put source-word forms and labels in `grammar`; keep translated forms and labels in the translation, including those in a header paragraph.
- Definitions contain `number`, `text`, `examples` and `notes`. Each example has `text` and `citation`, using the full bibliographic expansion when supplied and visible text otherwise. Keep unlinked bibliographic notes under their definition.
- Translations contain `number`, `text` and `examples`. Preserve bilingual examples as strings. Join the text fragments of a sense with newlines. Keep phrases and related forms at entry level. Do not split synonym groups on punctuation, infer grammatical traits or create numbered senses out of submeaning separators.
- Return empty arrays as `[]` and absent grammar, homonym, sense number or citation as `null`. Table appendices remain textual.

## Dictionary Parsing Rules

- Keep HTML interpretation in the parser package and strict upstream JSON schemas in external.py. Validate the configured dictionary set and every article's dictionary ID before parsing. Unsupported structure must fail the complete search; never silently skip an article or fall back to stripped HTML.
- TSLM-2022 (`tsblm2022`): strong.hw headwords, strong numbered senses, v-ex examples, strong.phr phraseology, standalone ○/◊ section markers and related forms after `||`.
- TSBM (`tsbm`): strong.hw headwords, examples embedded in sense paragraphs, bibliographic notes identified by midnightblue styling, phraseology after standalone •••. A phrase heading may contain v-ex; keep it in phraseology. Attach adjacent punctuation to the bibliographic text. Associate a reference with the preceding example when the reference immediately follows it within the paragraph.
- Klyshka (`klyshka`): synonym text may appear outside paragraphs. Remove the initial comma that separated the headword from the synonyms and render the `□` group separator as a semicolon and a space. Preserve other punctuation, italic labels and the original synonym ordering.
- RBS (`rbs10`): b.hw headwords, b numbered senses, examples in p.ms-3 and phraseology after standalone ◊. A translation may occupy the header paragraph. Superscript Roman homonym indices and grammar alone must not create a translation sense.
- RBS also uses plain sequential sense numbers in the header or after an example's semicolon. Split these before assigning paragraph semantics; keep header grammar separate and assign the following translation to the new sense. Do not interpret numbers inside bold example originals, italic explanations or phraseology as sense boundaries. Preserve nonsequential numbers as text. Regression: `собака` must have senses 1/2, two examples under sense 1 and `слімак` under sense 2.
- Concatenate span.accent fragments without inserted spaces. Search highlight tags may cross semantic tag boundaries; ignore their wrapper while preserving text. Reject active content. Standalone section markers switch sections without becoming content blocks.

## Cache & Failures

- Cache only complete successful service results, including empty results. Cache hits return the validated operation DTO directly. Include the operation, normalized query, effective ordered dictionaries, page and PARSER_VERSION in cache identity under the configured key prefix. Do not extend TTL on a hit. Invalid cached DTO data is a miss. Cache I/O failure is 503.
- Increment PARSER_VERSION whenever the cached format or parsing semantics change so previously cached interpretations are not reused. Keep cache TTL at least 30 days; TTL is not a durability or capacity guarantee.
- Use configured HTTPS endpoint, timeouts and bounded retries. Retry only network/timeouts and upstream 429/502/503/504. Exhaustion maps to SearchUnavailableError (503); other HTTP errors, redirects, invalid JSON, dictionary mismatch or unsupported HTML map to SearchInvalidResponseError (502). Cache errors map to SearchCacheUnavailableError (503).
- Support only the configured nonempty unique subset of tsblm2022, tsbm, klyshka and rbs10. Adding a dictionary requires an explicit parser, name mapping, validation updates and regression coverage; do not accept arbitrary upstream dictionaries.

## Change Verification

- For parser fixes, capture a minimal real upstream article under tests/fixtures/verbum and assert semantic output in tests/test_search_parser.py. Cover sense boundaries, example ownership, labels and section separation affected by the fix. Use synthetic cases for ambiguous numbers and markup edge cases; do not rely only on live upstream availability.
- Run `make test` plus the root-required Ruff and strict mypy checks for application changes. Existing fixtures cover homonym indices, header translations, phrase markers, bibliographic punctuation, alternative headwords inline RBS senses and unwrapped Klyshka entries; keep these regressions passing.
- Parser support is limited to covered structures. A successful sample does not prove all Verbum articles are supported. Do not record historical manual checks as permanent correctness guarantees.
