# Decks Module Rules

Inherits the root AGENTS.md. Public interface: `DecksService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership

- Own both decks and cards, including their content, visibility, access rules, public reads, and copying. Use one public DecksService; separate card URL paths do not imply a separate module.
- ORM relationships between decks and cards are internal to this module and allowed. Learning progress and scheduling belong to practice.
- Sharing a deck is a decks use case; do not introduce a separate sharing module for visibility or copying.
- Access verification and copying, including the copy's activity record, form one transaction. Adding content and its activity record also form one transaction. Re-check access after external calls before writing.

- Activity records outlive their subjects: use nullable foreign keys with `SET NULL` and a stored historical ID rather than cascading their deletion.

## Foreign Content

- Foreign content: read-only, re-check visibility on every read, copy, and cache hit. Foreign DTO exposes navigation/copy ids + public learning content only — never author or author id, notes, tags, progress, scheduling state, statistics, settings.
