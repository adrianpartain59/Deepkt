# User Authentication Implementation Plan

## Context

ABMIS currently has no user accounts. Projects are stored as shared JSON files (5 slots in `data/projects/`), and the only auth is a server-global Spotify OAuth for playlist import. This plan adds full user authentication so projects are per-user, with email+password, Google, and Apple sign-in options.

**Requirements:**
- Auth methods: Email+password, Google OAuth, Apple OAuth
- JWT access + refresh tokens
- Projects become per-user (isolated)
- Spotify import requires login
- Browsing (universe, search, audio) stays public

---

## Phase 1: Backend Auth Infrastructure

### 1.1 Dependencies — `requirements.txt`
Add:
- `PyJWT>=2.8` — JWT encode/decode
- `argon2-cffi>=23.1` — password hashing
- `authlib>=1.3` — Google/Apple OAuth (handles OIDC, JWKS, Apple's JWT client_secret)

### 1.2 Database Schema — `deepkt/db.py`
Add to `_init_tables()`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,       -- UUID4
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT,
    password_hash   TEXT,                   -- NULL for OAuth-only users
    auth_provider   TEXT DEFAULT 'email',   -- 'email', 'google', 'apple'
    provider_id     TEXT,                   -- OAuth subject ID
    refresh_token   TEXT,                   -- hashed refresh token
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    slot        INTEGER NOT NULL,
    name        TEXT NOT NULL,
    playlist_urls TEXT DEFAULT '[]',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, slot)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider
    ON users(auth_provider, provider_id) WHERE provider_id IS NOT NULL;
```

### 1.3 New Module — `deepkt/auth.py` (~200 lines)
- `hash_password(plain)` / `verify_password(plain, hashed)` — argon2
- `create_access_token(user_id, email)` — 15min expiry, HS256
- `create_refresh_token(user_id)` — 30-day expiry, `jti` stored hashed in DB
- `decode_token(token)` — verify signature + expiry
- `get_current_user` — FastAPI `Depends()`, extracts Bearer token, returns `UserClaims(user_id, email)`, raises 401
- `optional_current_user` — same but returns `None` instead of 401
- `google_oauth_exchange(code)` — exchange code, verify ID token, return `{email, name, provider_id}`
- `apple_oauth_exchange(code, user_json)` — exchange code, decode ID token, return `{email, name, provider_id}`

### 1.4 Environment Variables — `.env.example`
```
JWT_SECRET=generate-a-random-64-char-string
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
APPLE_CLIENT_ID=
APPLE_TEAM_ID=
APPLE_KEY_ID=
APPLE_PRIVATE_KEY_PATH=
APPLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/apple/callback
```

---

## Phase 2: Auth API Endpoints — `api.py`

### Email+Password
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/register` | None | Create account, return tokens |
| POST | `/api/auth/login` | None | Verify credentials, return tokens |
| POST | `/api/auth/refresh` | None | Rotate refresh token, return new pair |
| POST | `/api/auth/logout` | Bearer | Revoke refresh token |
| GET | `/api/auth/me` | Bearer | Return user profile |

### Google OAuth
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/auth/google/login` | Redirect to Google consent |
| GET | `/api/auth/google/callback` | Exchange code, return HTML with postMessage tokens |

### Apple OAuth
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/auth/apple/login` | Redirect to Apple consent |
| POST | `/api/auth/apple/callback` | Exchange code (Apple POSTs), return HTML with postMessage |

Account linking: If an OAuth email matches an existing account, link them rather than creating a duplicate.

---

## Phase 3: Per-User Projects

### 3.1 Migrate project endpoints — `api.py`
- Replace file-based `_project_path`/`_load_project`/`_save_project` with SQL queries
- All project endpoints get `user: UserClaims = Depends(get_current_user)`
- Queries scope by `WHERE user_id = ?`
- Delete `data/projects/` file logic

### 3.2 Refactor Spotify to per-user — `deepkt/spotify.py`
- Replace module-level globals (`_sp_client`, `_token_info`, etc.) with per-user token storage
- Add `spotify_tokens` columns to `users` table (or separate table)
- Pass user context through `/api/spotify/*` endpoints
- Key `_import_progress` dict by `user_id`

---

## Phase 4: Frontend Auth

### 4.1 Auth Store — `web/src/stores/authStore.ts` (new file)
Zustand store (already a dependency, currently unused):
- State: `user`, `accessToken` (memory only), `refreshToken` (localStorage), `isLoading`
- Actions: `login`, `register`, `oauthLogin`, `refresh`, `logout`, `loadFromStorage`
- `getAuthHeaders()` helper for fetch calls

Token strategy: refresh token in localStorage, access token in memory. On page load, call `/api/auth/refresh` to get a fresh access token.

### 4.2 API Client — `web/src/lib/api.ts` (new file)
Thin fetch wrapper that:
- Attaches Bearer token from auth store
- On 401, attempts refresh + retry once
- On refresh failure, calls `logout()`

### 4.3 Auth Page — `web/src/components/AuthPage.tsx` (new file)
- Full-screen overlay (same pattern as CreatePage/AboutPage)
- Toggle between Sign In / Sign Up modes
- Email + password form
- "Continue with Google" / "Continue with Apple" buttons → open OAuth popups (reuse existing Spotify popup pattern from CreatePage)
- Add `"auth"` to `PageTab` type in MenuPanel

### 4.4 Update `page.tsx`
- Import AuthPage, render when `activeTab === "auth"`
- Initialize auth store on mount (call `loadFromStorage` → `refresh`)

### 4.5 Update `CreatePage.tsx`
- If not logged in, show "Sign in to create projects" with button to auth page
- Use API client wrapper for all project/Spotify fetch calls

### 4.6 Update `MenuPanel.tsx`
- Show user display name/email at bottom when logged in
- Show "Sign In" button when not logged in
- Add "Sign Out" option

---

## Phase 5: Security

- **Rate limiting**: Add `slowapi` to `/api/auth/login` (5/min) and `/api/auth/register` (3/min)
- **Password validation**: Min 8 characters, enforced on both frontend and backend
- **Token rotation**: Each refresh invalidates the old token (single-session per user)
- **HTTPS reminder**: Log warning if JWT_SECRET is set but requests come over HTTP (non-localhost)

---

## Critical Files to Modify
- `api.py` — add auth endpoints, convert project endpoints to require auth
- `deepkt/db.py` — add `users` and `projects` tables
- `deepkt/spotify.py` — refactor from global to per-user tokens
- `requirements.txt` — add PyJWT, argon2-cffi, authlib
- `.env.example` — add JWT and OAuth env vars
- `web/src/app/page.tsx` — add auth page routing, init auth store
- `web/src/components/CreatePage.tsx` — gate behind auth, use API client
- `web/src/components/MenuPanel.tsx` — add user display + sign in/out

## New Files
- `deepkt/auth.py` — auth utilities (JWT, password hashing, OAuth helpers, FastAPI deps)
- `web/src/stores/authStore.ts` — Zustand auth state
- `web/src/lib/api.ts` — authenticated fetch wrapper
- `web/src/components/AuthPage.tsx` — sign in/up UI

---

## Verification
1. **Register**: POST `/api/auth/register` with email+password → get tokens back
2. **Login**: POST `/api/auth/login` → get tokens, use access token on `/api/auth/me`
3. **Refresh**: POST `/api/auth/refresh` with refresh token → get new pair
4. **Google OAuth**: Click "Continue with Google" → popup → redirected back → logged in
5. **Projects**: Create project while logged in → only visible to that user
6. **Public browsing**: Universe canvas loads without login, search works
7. **Spotify import**: Requires login, ties import to user
8. **Token expiry**: Wait 15min (or set short expiry for testing) → automatic refresh works
