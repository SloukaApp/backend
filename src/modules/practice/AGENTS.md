# Practice Module Rules

Inherits the root AGENTS.md. Public interface: `PracticeService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership & Atomicity

- Own sessions, accepted answers, scheduling calculations and session summaries. Deck/card content and stored learning state belong to decks; use DecksService for reads, locking and updates.
- Answer acceptance, the learning-state update through DecksService, and activity form one transaction. Lock the card through DecksService before reading its current state, calculate SM2 locally, then apply the result through DecksService. Statistics are computed; do not persist aggregate updates.
- An unconfirmed account receives 403 on learning routes. Missing or inaccessible learning objects return 404.

## Event Idempotency & History

- Idempotency: client event ids immutable, unique per account in DB. Same id + same payload → return the stored result of that accepted answer, not the card's current state; write nothing. Same id + different payload → 409. Acceptance time and derived state are fixed at first acceptance; client timestamps and redelivery never change them. Concurrent events on one row serialize in server order. Event referencing a deleted object → 404, writes nothing; already-accepted events stay recognizable. A finished session is never resumed; late events still update its summary.
- Deletion is deliberate: accepted answers and activity outlive their subjects → nullable FK + `SET NULL` + stored historical id, not cascades.

## Scheduling

- `domain.py` scheduling, pure function of prior state + grade + acceptance time. Grades 1, 2, 4, 5 (3 intentionally absent; anything else 422); success = 4 or 5. Below threshold: `repetitions=0`, `interval=1`. Else `repetitions++`; first success 1 day, second 6, then `interval = (prev_interval * old_EF).to_integral_value(rounding=ROUND_HALF_UP)` — `round()` is banker's and forbidden; never mix `Decimal` and `float` in one expression. Every grade: `EF = max(1.3, old_EF + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))` with `old_EF`. `next_review_at = accepted_at + interval * 24h`. Clear "new" on any first grade; set `learned_at` on first success after creation or reset, never clear it on later failures. Reset → `EF=2.5`, `interval=0`, `repetitions=0`, new flag set, `next_review_at`/`learned_at` NULL, history preserved. Auxiliary exercise modes never touch scheduling state, new flag, or `learned_at`.

## Session Composition & Answers

- Filter by ownership and selected deck tags before applying limits. Select due cards by next_review_at/id, then new cards by created_at/id: at most 20 total and 10 new, without repeats. New-only selections are valid; an empty selection creates no session.
- Forward, reverse and random direction use the same card progress, grade scale and session limits. Record actual direction and ordered membership at session creation.
- Validate answer ownership, original session membership and exercise mode. Looking at a card without an accepted grade is not a review or activity. Changes from another device do not invalidate an otherwise valid answer; apply it to current locked state.
- Deleting a deck finishes its active sessions with partial summaries. Finished sessions never resume; valid late answers update their original summary. Persist historical card IDs and each answer's resulting state so retries remain recognizable after deletion and subsequent reviews.
