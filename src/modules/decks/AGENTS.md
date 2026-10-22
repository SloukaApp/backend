# Decks Module Rules

Inherits the root AGENTS.md. Public interface: `DecksService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership

- Own both decks and cards, including their content, visibility, access rules, public reads, and copying. Use one public DecksService; separate card URL paths do not imply a separate module.
- ORM relationships between decks and cards are internal to this module and allowed. Own the stored learning state in `cards`: EF, interval, repetitions, next review, new flag, and learned_at. Practice owns the scheduling calculation and answer workflow, not writes to cards.
- Sharing a deck is a decks use case; do not introduce a separate sharing module for visibility or copying.
- Access verification and copying, including the copy's activity record, form one transaction. Adding content and its activity record also form one transaction. Re-check access after external calls before writing.

- Activity records outlive their subjects: use nullable foreign keys with `SET NULL` and a stored historical ID rather than cascading their deletion.

## Foreign Content

- Foreign content: read-only, re-check visibility on every read, copy, and cache hit. Foreign DTO exposes navigation/copy ids + public learning content only — never author or author id, notes, tags, progress, scheduling state, statistics, settings.

## Learning State & Concurrency

- Expose public operations to read an owned card under `SELECT ... FOR UPDATE` and apply a calculated learning-state DTO. Only the decks repository writes `cards`; keep the lock until the caller's UoW exits. Decks never calls PracticeService.
- Practice locks the card through DecksService, computes SM2, then applies the result through DecksService in the same transaction as the accepted answer and activity. Do not read state unlocked and later overwrite a concurrent update.
- New/reset state: EF=2.5, interval=0, repetitions=0, is_new=true, next_review_at/learned_at=NULL. Reset preserves history. First success sets learned_at; later failures do not clear it. Auxiliary exercises do not change learning state.

## Content & Tags

- Enforce `(deck_id, word_lower)` uniqueness with word.lower(), without stripping diacritics/labels or lemmatizing; duplicates return 409. Homonyms and meanings of one spelling share one card.
- Store meanings, their examples and provided dictionary sources in related tables, preserving ordering and meaning–example relationships. Never invent absent content. Preserve Markdown notes without rewriting.
- Tags belong to a deck; names are unique within that deck ignoring case. A card and its assigned tag must belong to the same deck, enforced by DB constraints.

## Visibility & Copying

- Visibility is private/by_link/public; new decks are private. Foreign reads require authentication and current by_link/public visibility. Links use stable deck_id, no share_token; making private closes subsequent reads, reopening restores the same link.
- Public catalog: public decks only, limit/offset pagination, case-insensitive name substring; empty query lists all, no matches returns an empty list.
- Copy only words, meanings, examples and sources, never notes/tags/progress. Copied cards start new and unlearned; every copied card creates activity. Copies are independent of later changes/deletion of the source or its owner.
- A copied deck is private; use the source name with a sequence number on conflict. Copying into an owned target deck leaves its visibility unchanged; duplicate words return 409.
- Serialize the source visibility check with visibility changes and read a consistent content snapshot during copying. Deleting a deck closes its active practice sessions with a partial summary; coordinate through the owning workflow without introducing a decks → practice dependency cycle.
