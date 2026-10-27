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
Code: `backend/app/auth/reset.py`, table `password_resets`. Email goes through `app/notify.py` (see NFR-10 for SMTP settings; without SMTP the email, link included, is printed in the backend log).

| Method | Path | Access | Request -> Response |
|---|---|---|---|
| POST | /api/auth/password-reset | public | `{userId}` -> 202 `{message}`. Always the same answer, so it never reveals whether a user ID exists. Active users get an email with `{FRONTEND_URL}/reset-password?token=...` |
| POST | /api/auth/password-reset/confirm | public (token) | `{token, newPassword}` -> 200 `{message}`. 400 `RESET_LINK_INVALID` if the link is unknown, used or expired; 400 if the password is under 8 characters |

**Rules**
- The link works once and expires after 30 minutes (`PASSWORD_RESET_EXPIRE_MINUTES`).
- Only the newest link works: asking again cancels the older one. Asking again within 60 s sends no second email, and the first link still works.
- Only a SHA-256 hash of the token is stored. With SMTP on, the link is never logged.
- After a reset the old password stops working and all the user's sessions end.
- A locked account stays locked (SEC-3: only an Admin unlocks). A Manager or Admin still needs the emailed 2FA code (NFR-10).
- Deactivated users get no email, and their old links stop working.

**Frontend (to do, Mathin):** a "Forgot password?" link on the login page that posts `{userId}` and shows the message, and a `/reset-password` page that reads `token` from the URL and posts `{token, newPassword}`. Until then, test with `/docs`.

**Tests** (`backend/tests/test_reset.py`): TC-AUTH-13 (email sent, new password works, old rejected) and TC-AUTH-14 (used link rejected); unknown and deactivated users get the same answer and no email; link expires after 30 min; made-up token rejected; only a hash is stored; a newer link cancels the older one; no second email within 60 s; short password rejected without using the link; reset logs the user out everywhere; new password stored as argon2id; locked account stays locked; deactivated user can't use the link; Manager still needs 2FA; link never logged with SMTP; frontend URL configurable. `tests/test_access.py` lists the two endpoints as intentionally public.

**Existing databases:** adds the `password_resets` table, which is created automatically at startup. No reset needed.

## NFR-10 Two-factor authentication for Manager and Admin (TC-SEC-07)
**Method:** a 6-digit code sent to the user's email. Code is in `backend/app/auth/otp.py`; email goes through `backend/app/notify.py` (`send_email()`, also for SEC-5 and alerts).

**How it works**
1. A Manager or Admin logs in with user ID and password. If those are right and no `otpCode` was sent, a code is emailed and the answer is `401 OTP_REQUIRED` with `details.sentTo` (e.g. `m*******@example.com`). The login page then shows the code box.
2. The login page sends user ID, password and `otpCode`. If the code is right, the user is logged in; if it is wrong, used or expired, the answer is `401 INVALID_OTP`.

- Other roles log in as before, with no code and no email.
- The code expires after 10 minutes (`OTP_EXPIRE_MINUTES`), works once, and only a keyed hash of it is stored.
- A wrong code counts like a wrong password (SEC-3): five wrong codes lock the account (423).
- A wrong password sends no email. Asking again within 30 s (`OTP_RESEND_SECONDS`) does not send another one, so nobody can flood an inbox.
- `REQUIRE_2FA=false` switches 2FA off (local work only).

**Email settings:** with `SMTP_HOST` empty (default), no email leaves the machine: it is printed in the backend log (`EMAIL (not sent, SMTP_HOST is empty) ... Your login code is 123456`). Use that for development and the demo. To send real email set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (Gmail: `smtp.gmail.com`, port 587, an app password). In that mode the code is never logged.

**Tests** (`backend/tests/test_2fa.py`): password alone gives OTP_REQUIRED and emails a code (Manager and Admin); wrong code rejected then right code accepted (TC-NFR-13 steps); other roles need no code; wrong password sends no email; right code with wrong password refused; a code works once; expires after OTP_EXPIRE_MINUTES; spaces allowed; malformed codes rejected; only a hash is stored; with SMTP the code is never logged; no second email within 30 s; a newer code replaces the old one; 5 wrong codes lock; asking for a code is not a failure; a locked account gets no email; 2FA can be switched off; expiry is configurable.

**Existing databases:** this adds three columns to `users` (`otp_code_hash`, `otp_sent_at`, `otp_expires_at`). Tables are created at startup, not migrated, so reset the database once (delete the SQLite file, or `docker compose down -v`).

## NFR-11 Employee data encrypted at rest (TC-SEC-08)
To do.
