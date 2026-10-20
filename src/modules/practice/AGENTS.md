# Practice Module Rules

Inherits the root AGENTS.md. Public interface: `PracticeService`; DTOs: `dto.py`;
documented public exceptions: `errors.py`. HTTP mappings belong in `http_errors.py`
and are assembled in `main.py`, never imported by services or workers.

## Ownership & Atomicity

- Own answer acceptance, learning progress, scheduling state, and practice-session summaries. Deck/card content belongs to decks; access it through DecksService.
- Answer acceptance, progress, activity, and statistics updates form one transaction. Serialize concurrent answers affecting one progress row using `SELECT ... FOR UPDATE`.
- An unconfirmed account receives 403 on learning routes. Missing or inaccessible learning objects return 404.

## Event Idempotency & History

- Idempotency: client event ids immutable, unique per account in DB. Same id + same payload → return stored result, write nothing. Same id + different payload → 409. Acceptance time and derived state are fixed at first acceptance; client timestamps and redelivery never change them. Concurrent events on one row serialize in server order. Event referencing a deleted object → 404, writes nothing; already-accepted events stay recognizable. A finished session is never resumed; late events still update its summary.
- Deletion is deliberate: accepted answers and activity outlive their subjects → nullable FK + `SET NULL` + stored historical id, not cascades.

## Scheduling

- `domain.py` scheduling, pure function of prior state + grade + acceptance time. Grades 1, 2, 4, 5 (3 intentionally absent; anything else 422); success = 4 or 5. Below threshold: `repetitions=0`, `interval=1`. Else `repetitions++`; first success 1 day, second 6, then `interval = (prev_interval * old_EF).to_integral_value(rounding=ROUND_HALF_UP)` — `round()` is banker's and forbidden; never mix `Decimal` and `float` in one expression. Every grade: `EF = max(1.3, old_EF + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))` with `old_EF`. `next_review_at = accepted_at + interval * 24h`. Clear "new" on any first grade; set `learned_at` on first success after creation or reset, never clear it on later failures. Reset → `EF=2.5`, `interval=0`, `repetitions=0`, new flag set, `next_review_at`/`learned_at` NULL, history preserved. Auxiliary exercise modes never touch scheduling state, new flag, or `learned_at`.
