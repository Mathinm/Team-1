# S2-9 Security extras (#18)

Builds on S1-1 (`docs/S1-1-auth.md`). Requirements (SRS v1.0): SEC-3, SEC-5, NFR-10, NFR-11.

## SEC-3 Account lockout and idle logout (TC-AUTH-03)

**Lockout**
- Each wrong password for an existing, active account adds 1 to `users.failed_logins`. A correct password resets it to 0, so only failures *in a row* count.
- The 5th wrong password in a row locks the account (`users.locked_at`) and answers **423** `{"error": {"code": "ACCOUNT_LOCKED", "message": "Account locked, contact Admin"}}`. From then on every login answers 423, even with the right password.
- An unknown user ID never gets 423 (always the generic 401), so lockout does not reveal which IDs exist.
- Every lock is logged: `ACCOUNT_LOCKED user=... after 5 failed logins` (`pms.security`).
- An Admin unlocks with `PATCH /api/users/{userId}/unlock` (logged as `USER_UNLOCKED` in `pms.audit`). `GET /api/users` shows `locked: true/false`.
- The limit is `MAX_FAILED_LOGINS` (default 5).

**Idle logout**
- `user_sessions.last_seen_at` is updated on requests (at most every 30 s per session).
- A session with no request for `IDLE_TIMEOUT_MINUTES` (default 30) is ended on its next use and answers 401 "Your session has ended. Please log in again."; the frontend then shows the login page. Coming back later does not reopen it.

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | /api/auth/login | public | adds **423** `ACCOUNT_LOCKED` |
| PATCH | /api/users/{userId}/unlock | Admin | 200 user (with `locked: false`) |

**Database:** adds `users.failed_logins` and `users.locked_at`. Tables are still created at startup, which does not add columns to an existing table, so reset your local database once: `docker compose down -v`.

**Tests** (`backend/tests/test_lockout.py`): 4 failures then success resets the counter; the 5th failure locks (423) and the right password is then refused; only consecutive failures count; unknown users never see 423; the lock is logged; Admin unlocks and only Admin can; the limit is configurable; an idle session is ended and stays ended; an active session stays open and records activity; the idle timeout is configurable (1 minute, as in the Test Case Document).

## SEC-5 Password reset by email (TC-AUTH-05)
To do.

## NFR-10 Two-factor authentication for Manager and Admin (TC-SEC-07)
To do.

## NFR-11 Employee data encrypted at rest (TC-SEC-08)
To do.
