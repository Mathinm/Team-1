# S1-1 Auth: login, salted hashes, role-based access, user admin (#3)

Requirements (SRS v1.0): SEC-1, NFR-9, SEC-2, SEC-4. Design: SAD 3.9, 4.3, 4.4.
Built on the sales/device code from #4/#7: it uses `app/db.py`, `app/config.py`, `app/errors.py`
and `app/rbac.py`, so `require_roles(...)` in every router works unchanged.

## Endpoints
| Method | Path | Who | Request / response |
|---|---|---|---|
| POST | /api/auth/login | public | `{userId, password, otpCode?}` -> 200 `{token, role, expiresIn, name, userId}`. 401 `"Invalid user ID or password"` for wrong password, unknown user or deactivated user. 400 missing field |
| POST | /api/auth/logout | logged in | 204. That token stops working; other devices stay logged in |
| GET | /api/auth/me | logged in | `{userId, name, role, menu[]}` |
| GET | /api/users | Admin | `[{userId, name, email, role, active, storeId}]` |
| POST | /api/users | Admin | `{userId, name, email, role, password}` -> 201. 409 `"User ID already exists"` |
| PUT | /api/users/{userId} | Admin | `{name?, email?, role?}` -> 200 |
| PATCH | /api/users/{userId}/deactivate | Admin | 200. Login refused, open sessions ended, record kept |
| PATCH | /api/users/{userId}/activate | Admin | 200 |

Roles: `Admin`, `Manager`, `Inventory Staff`, `Cashier` (same strings as `frontend/src/config/roles.js`).

## How it works
- **Passwords (NFR-9):** argon2id via `argon2-cffi`, random salt per password stored inside the hash. A hash made with older, weaker settings is upgraded the next time the user logs in. Passwords never appear in the database or logs.
- **Sessions (SEC-1):** login stores a row in `user_sessions` and returns a signed JWT (HS256, `JWT_SECRET`, `TOKEN_EXPIRE_MINUTES`) whose `sid` points to it. Every request checks the row and that the user is still active, so logout and deactivation take effect at once. Role and name are read from the database on each request, so a role change applies immediately.
- **Unknown user vs wrong password:** both take the same code path (a dummy hash is checked) and return the same 401, so user IDs cannot be guessed.
- **Roles (SEC-2):** `require_roles(...)` returns 403 and logs `ACCESS_DENIED user=... role=... method=... path=...` to `pms.security`. `GET /api/auth/me` returns the role's menu so the UI hides other screens (`ROLE_MENUS` in `app/rbac.py`; keep it in step with the frontend).
- **Every endpoint is protected:** `tests/test_access.py` lists every `/api` route and fails if one answers without a login. If you add an endpoint that must be public, add it to `PUBLIC` there and say why in your PR.
- **User admin (SEC-4):** Admin-only. Users are never deleted, only deactivated, so their sales and removals keep their author. An Admin cannot deactivate or demote themselves. Changes are logged to `pms.audit`.
- **First users:** at startup an Admin is created if there are no users (`ADMIN_USER_ID` / `ADMIN_PASSWORD`, default `admin/admin123`). With `SEED_DEMO_USERS=true` (the default in docker-compose) also `manager1/manager123`, `staff1/staff123`, `cashier1/cashier123`. Turn it off and change the Admin password for the final demo.

## For other modules
```python
from fastapi import Depends
from app.rbac import ADMIN, MANAGER, STAFF, CurrentUser, get_current_user, require_roles

@router.post("/api/batches", status_code=201)
def receive_batch(body: BatchIn, user: CurrentUser = Depends(require_roles(ADMIN, MANAGER, STAFF)),
                  db: Session = Depends(get_db)):
    ...  # user.user_id, user.role, user.name

@router.get("/api/products")
def list_products(user: CurrentUser = Depends(get_current_user)):  # any logged-in user
    ...
```
In tests use `auth("staff1", "Inventory Staff")` from `tests/conftest.py`; it creates the user and an open session.

## Test coverage (SRS v1.0 test IDs)
| Requirement | Test case | Tests |
|---|---|---|
| SEC-1 login | TC-AUTH-01 | `tests/test_auth.py`: valid login, wrong password and unknown user get the same 401, deactivated user refused, logout, separate sessions per device, token without a session refused, bad/no token, missing field |
| NFR-9 salted hashes | TC-SEC-06 | `tests/test_passwords.py`: same password gives different argon2id hashes, no plaintext in the users table, verify only the right password, passwords never logged, weak old hashes upgraded on login |
| SEC-2 roles | TC-AUTH-02 | `tests/test_access.py`: every `/api` endpoint refuses anonymous calls, each role's menu, out-of-role call 403 and logged, role change applies on the next request |
| SEC-4 user admin | TC-AUTH-04 | `tests/test_users.py`: create and log in, duplicate 409, edit and assign role, deactivate (login refused, sessions ended, record kept) and reactivate, non-admins 403, invalid input 400, no self-lockout, unknown user 404, audit log without passwords |

## Deviations from the SAD (for S2-11)
- `POST /api/users` also takes the first `password`; the SAD body has no way to set one.
- Added `GET /api/auth/me` and `PATCH /api/users/{userId}/activate`.
- Login response also has `name` and `userId` (frontend contract).

## Left for S2-9 (#18)
Lockout after 5 failures (423), idle logout (`user_sessions.last_seen_at`), password reset by email,
2FA for Manager/Admin (the login page shows the code field when the backend answers `OTP_REQUIRED`),
employee-data encryption.
