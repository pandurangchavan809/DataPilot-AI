# Authentication in DataPilot AI (JWT, with Interview Prep)

Users sign up and log in with email and password. The backend issues **JWT access and refresh
tokens**. Every API call except `/api/health` and `/api/auth/*` needs a valid access token.
Accounts and login history are stored in their own SQLite file, separate from the data users query.

**Demo login (shown on the login page):** `user` / `User@1234`

---

## 1. Where things live

| What | Where |
|---|---|
| User accounts, refresh tokens, login history | `auth/auth.db` (SQLite, created on first start, **gitignored**) |
| Demo data users ask questions about | `data/demo.db`: a different file, never mixed with accounts |
| Backend auth code | `app/auth/store.py` (database), `app/auth/service.py` (passwords and tokens), `app/api/auth.py` (endpoints), `require_auth()` in `app/api/deps.py` |
| Frontend auth code | `src/hooks/useAuth.ts` (store), `src/api.ts` (adds the token and refreshes it), `src/components/auth/AuthPage.tsx` (login/signup page), `UserCard` in `src/components/sidebar/Sidebar.tsx` |

### The three tables

```sql
users          (id, email UNIQUE, password_hash, created_at, last_login_at, login_count)
refresh_tokens (jti PRIMARY KEY, user_id, expires_at, revoked, created_at)
login_events   (id, user_id, email, success, ip, user_agent, created_at)
```

- **`password_hash`**, never the password. Werkzeug's `generate_password_hash` uses scrypt with a
  random salt, so two users with the same password get different hashes.
- **`login_events`** records every attempt, successful or failed, with IP and browser. This is how
  you keep track of who logs in.

Look at the login history yourself:

```bash
sqlite3 auth/auth.db "SELECT email, success, ip, datetime(created_at,'unixepoch') FROM login_events ORDER BY id DESC LIMIT 20;"
sqlite3 auth/auth.db "SELECT email, login_count, datetime(last_login_at,'unixepoch') FROM users;"
```

---

## 2. The two tokens

| | Access token | Refresh token |
|---|---|---|
| Lifetime | 15 minutes (`ACCESS_TOKEN_MINUTES`) | 7 days (`REFRESH_TOKEN_DAYS`) |
| Sent on | Every API call: `Authorization: Bearer <token>` | Only `POST /api/auth/refresh` and `/logout` |
| Checked by | Signature + expiry only. **No database lookup.** | Signature + expiry + a database lookup by `jti` |
| Can be revoked? | No: it simply expires in ≤ 15 min | Yes (`revoked = 1`) |

Both are JWTs signed with **HS256** using `JWT_SECRET_KEY` (defaults to `SECRET_KEY`). Payload:

```json
{ "sub": "7", "email": "pandurang809@gmail.com", "type": "access", "jti": "9f1c…", "iat": 1761900000, "exp": 1761900900 }
```

- `sub`: the user id. `type`: `access` or `refresh`, so one can't be used as the other.
- `jti`: a unique id. For refresh tokens it's the database key.
- `exp`: expiry. PyJWT rejects expired tokens automatically.

**Why two tokens?** A short access token limits the damage if it leaks, and checking it is free (no
database). A long refresh token means users don't log in every 15 minutes. Because it's checked in
the database, it can be revoked on logout.

---

## 3. The flows

### Sign up / log in

```
POST /api/auth/login {email, password}
  → find the user by email (lower-cased)
  → check_password_hash (also runs for unknown emails, so timing doesn't reveal which emails exist)
  → record the attempt in login_events
  → wrong: 401 "Incorrect email or password."  (same message for unknown email or wrong password)
  → right: { access_token, refresh_token, expires_in: 900, user }
```

Signup checks that the email looks valid and the password has at least 8 characters, with a letter and a
number. It then stores the hash and logs the user in. A duplicate email returns 409.

### Every API call

```
Authorization: Bearer <access>
  → require_auth() (a FastAPI dependency on the protected routers)
  → jwt.decode(algorithms=["HS256"]) + type == "access"
  → g.user_id = sub      → the endpoint runs
  → expired: 401 token_expired      bad/missing: 401 unauthorized / invalid_token
```

### Refresh (rotation)

```
POST /api/auth/refresh {refresh_token}
  → verify signature + expiry + type == "refresh"
  → UPDATE refresh_tokens SET revoked=1 WHERE jti=? AND revoked=0   (atomic: works exactly once)
      1 row  → ok: issue a NEW access + refresh pair
      0 rows, jti exists → REUSE: someone copied a token → revoke ALL of this user's refresh tokens → 401
      0 rows, unknown    → 401
```

### Logout

The frontend disconnects the user's database session, sends the refresh token to
`/api/auth/logout` (which revokes it), clears both tokens and wipes the chat in the tab.

### Frontend: automatic refresh

`authedFetch()` in `api.ts` wraps every call, including the streaming chat:

1. Send the request with the access token.
2. If the response is **401**, call `/api/auth/refresh` once, store the new pair and retry the request.
3. If the refresh also fails, clear the tokens. The app shows the login page again.

If several requests get a 401 at the same moment, they share **one** refresh call (`refreshing`
promise), so the refresh token isn't used twice. Tokens are kept in `localStorage`, so login
survives a reload. A `storage` listener keeps several open tabs in sync.

---

## 4. Security decisions (and why)

| Decision | Why |
|---|---|
| Salted scrypt hashes (werkzeug) | A leaked database doesn't reveal passwords; the salt defeats precomputed tables |
| Same error for wrong email and wrong password, plus a dummy hash check | Attackers can't find out which emails have accounts |
| `algorithms=["HS256"]` pinned when decoding | Blocks the classic "alg: none" / algorithm-confusion attacks |
| `type` claim checked | A refresh token can't be used as an access token |
| Refresh rotation + reuse detection | A stolen refresh token works at most once before everything is revoked |
| Atomic `UPDATE … WHERE revoked = 0` | Two parallel refreshes can't both succeed |
| Rate limit `10/minute` per IP on `/api/auth/*` | Slows down password guessing |
| DB session key = user id + session id | Even with a guessed `X-Session-Id`, one user can't use another's database connection |
| Accounts in `auth/auth.db`, separate from `data/demo.db` | The data people query never contains credentials; each can be backed up or reset on its own |
| Logout wipes the chat and makes a new session id | The next person on the same browser sees nothing from the previous user |

**Known trade-offs** (good to say out loud in an interview):

- Tokens are in `localStorage`, so an XSS bug could read them. The alternative is an
  `httpOnly` cookie. That's harder here because the frontend (Vercel) and backend (Render) are on
  different domains, which means `SameSite=None` cookies and CSRF protection. React escapes output
  by default and the Markdown renderer doesn't allow raw HTML, which lowers the XSS risk.
- An access token can't be revoked before it expires (at most 15 min). That's the price of
  stateless checks.
- SQLite is right for a student project with one server. For many servers, move `users` and
  `refresh_tokens` to Postgres. On Render's free plan the disk is wiped on deploy (see
  [deployment.md](deployment.md) 1.7).

---

## 5. Settings

| Setting | Default | Meaning |
|---|---|---|
| `AUTH_DB_PATH` | `auth/auth.db` | Accounts database file |
| `JWT_SECRET_KEY` | `SECRET_KEY` | Token signing key. Changing it logs everyone out. Use ≥ 32 characters. |
| `ACCESS_TOKEN_MINUTES` | `15` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh token lifetime |
| `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD` | `user` / `User@1234` | Demo account created on start. Set the email empty to disable it. |
| `AUTH_RATE_LIMIT` | `10/minute` | Requests per IP on `/api/auth/*` |

## 6. API

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/signup` | `{email, password}` | 201 + tokens + user · 400 weak/invalid · 409 email taken |
| POST | `/api/auth/login` | `{email, password}` | 200 + tokens + user · 401 `invalid_credentials` |
| POST | `/api/auth/refresh` | `{refresh_token}` | 200 + new tokens · 401 `invalid_token` / `token_expired` |
| POST | `/api/auth/logout` | `{refresh_token}` | 204 |
| GET | `/api/auth/me` | (Bearer) | `{user}` |

Try it:

```bash
curl -s -X POST localhost:5000/api/auth/login -H "Content-Type: application/json" \
     -d '{"email":"user","password":"User@1234"}'
curl -s localhost:5000/api/config -H "Authorization: Bearer <access_token>"
```

Tests: `tests/test_auth.py` covers the demo login, signup, duplicate and weak passwords, failed-login logging,
protected routes, an expired token, a refresh token used as an access token, rotation and reuse,
logout, and per-user session isolation.

---

## 7. Interview questions and answers

**Q1. What is a JWT?**
A signed token in three base64url parts: `header.payload.signature`. The payload holds claims (user
id, expiry). Anyone can *read* it, so never put secrets in it, but nobody can *change* it without the
key, because the signature would no longer match.

**Q2. Why both an access token and a refresh token?**
Access tokens are short and checked without the database: fast, and a leak expires quickly.
Refresh tokens are long, but checked against the database, so they can be revoked. You get speed
and control without logging in every 15 minutes.

**Q3. What is refresh token rotation?**
Each refresh returns a new refresh token and invalidates the old one. If an old one is ever used
again, it must have been copied, so I revoke all the user's refresh tokens and they log in again.

**Q4. How do you store passwords?**
Never in plain text. I store `generate_password_hash(password)`: scrypt with a random salt. At login,
`check_password_hash` recomputes the hash and compares it in constant time.

**Q5. Why HS256 and not RS256?**
There's one backend that both signs and verifies, so a shared secret is simplest. RS256 (a
private key to sign, a public key to verify) fits when *other* services need to verify tokens
without being able to create them.

**Q6. How does logout work if JWTs are stateless?**
The refresh token is revoked in the database, so no new access tokens can be made. The current
access token stays valid for at most 15 minutes. The frontend deletes it right away. For instant
revocation you'd keep a deny-list of access `jti`s (for example in Redis).

**Q7. How do you protect routes in FastAPI?**
With a dependency. `require_auth` is added with `Depends` to the protected routers. It reads the Bearer
token, verifies it and returns the claims, and FastAPI won't run the route if it raises. Health and auth endpoints are on routers without
the hook.

**Q8. How did you stop brute-force attacks?**
A rate-limit dependency (using the `limits` library) allows 10 auth requests per minute per IP, and scrypt hashing is deliberately slow. Every
failed attempt is logged with its IP, so attacks are visible.

**Q9. Why is the auth database separate from the demo database?**
They do different jobs. The demo DB is read-only analytics data that the LLM sees, and it's
recreated on every start. The auth DB holds credentials that the LLM must never see. Keeping
them apart means no query can ever touch the users table.

**Q10. Where does the frontend keep the tokens, and is that safe?**
In `localStorage`, so login survives a reload and works across tabs. The risk is XSS. The
mitigations are React's escaping, no raw HTML in Markdown, and short-lived access tokens.
With a shared domain I would move the refresh token to an `httpOnly`, `Secure`, `SameSite`
cookie.

**Q11. What happens when the access token expires during a chat?**
The API returns 401 with `token_expired`. `authedFetch` refreshes once, then retries the same request
automatically. The user notices nothing. If the refresh fails too, they see the login page.

**Q12. How would you scale this auth?**
Move users and refresh tokens to Postgres and keep the JWT secret in a secret manager. Access
tokens need no shared state, so any number of servers can verify them. Add email verification,
password reset and maybe OAuth (Google login) next.
