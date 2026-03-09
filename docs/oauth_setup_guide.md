# OAuth & Authentication Setup Guide

Complete instructions for configuring AMBIS user authentication, including email+password and Google OAuth.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Generate a JWT Secret](#step-1-generate-a-jwt-secret)
3. [Step 2: Email + Password Auth (No External Setup)](#step-2-email--password-auth-no-external-setup)
4. [Step 3: Google OAuth Setup](#step-3-google-oauth-setup)
5. [Step 4: Final .env Configuration](#step-4-final-env-configuration)
6. [Step 5: Verify Everything Works](#step-5-verify-everything-works)
7. [Production Deployment Notes](#production-deployment-notes)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python dependencies installed: `pip install -r requirements.txt`
- A `.env` file in the project root (copy from `.env.example` if you don't have one)
- The API server (`python api.py`) and frontend (`cd web && npm run dev`) running for testing

---

## Step 1: Generate a JWT Secret

The JWT secret is used to sign all access and refresh tokens. It must be a long, random string.

**Generate one from your terminal:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

This outputs a 64-character hex string like: `a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1`

**Add it to your `.env`:**

```
JWT_SECRET=a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
```

**Important:** Never commit this value to git. The `.gitignore` already excludes `.env`.

If `JWT_SECRET` is not set, the server falls back to `dev-secret-change-me-in-production` which is fine for local development but **must** be changed before deploying.

---

## Step 2: Email + Password Auth (No External Setup)

Email+password authentication works out of the box once `JWT_SECRET` is set. No external services needed.

**Test it:**

```bash
# Register a user
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "mypassword123"}'

# Login
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "mypassword123"}'
```

Both return:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {"id": "...", "email": "you@example.com", "display_name": "you", "auth_provider": "email"}
}
```

Password requirements: minimum 8 characters, enforced on both backend and frontend.

---

## Step 3: Google OAuth Setup

### 3.1 Create a Google Cloud Project

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Click the project dropdown in the top nav bar
3. Click **New Project**
4. Name it something like `AMBIS` or `AMBIS Auth`
5. Click **Create**
6. Wait a few seconds, then select your new project from the dropdown

### 3.2 Enable Required APIs

1. In the left sidebar, go to **APIs & Services > Library**
2. Search for **"Google Identity Services"** (or **"People API"**)
3. Click on it and click **Enable**
   - This is required for OpenID Connect (reading email/name from Google accounts)

### 3.3 Configure the OAuth Consent Screen

Before creating credentials, you must configure what users see when they sign in.

1. Go to **APIs & Services > OAuth consent screen**
2. Click **Get Started** (or **Configure Consent Screen**)
3. Select **External** user type
4. Fill in the required fields only:

   | Field | Value |
   |-------|-------|
   | App name | `AMBIS` |
   | User support email | Your email address |
   | Developer contact email | Your email address |

   Leave all optional fields blank (app logo, home page, privacy policy, terms of service, authorized domains). These are not required for development.

5. Click **Save and Continue**

6. **Scopes** page:
   - Click **Add or Remove Scopes**
   - Find and check these three scopes:
     - `openid`
     - `.../auth/userinfo.email`
     - `.../auth/userinfo.profile`
   - Click **Update**, then **Save and Continue**

7. **Test users** page:
   - Click **Add Users**
   - Add your own Google email address (e.g., `yourname@gmail.com`)
   - Click **Save and Continue**
   - **While the app is in "Testing" mode, only these emails can sign in.** You can publish the app later to allow any Google account.

8. Click **Back to Dashboard**

### 3.4 Create OAuth Client Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Web application**
4. Name: `AMBIS Web Client` (or anything you like)
5. **Authorized JavaScript origins** (just the origin, no path):
   - Click **Add URI**
   - Add: `http://localhost:3000`
   - Click **Add URI** again
   - Add: `http://127.0.0.1:3000`
6. **Authorized redirect URIs** (full callback URL with path):
   - Click **Add URI**
   - Add: `http://127.0.0.1:8000/api/auth/google/callback`

   This must match `GOOGLE_REDIRECT_URI` in your `.env` exactly — same protocol, host, port, and path.

7. Click **Create**

8. A dialog appears with your **Client ID** and **Client Secret**. Copy both.

   - Client ID looks like: `123456789-abcdefg.apps.googleusercontent.com`
   - Client Secret looks like: `GOCSPX-AbCdEfGhIjKlMnOpQrSt`

### 3.5 Add to .env

```
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-AbCdEfGhIjKlMnOpQrSt
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
```

### 3.6 Test Google OAuth

1. Restart the API server (`python api.py`)
2. Open the app in your browser (`http://localhost:3000`)
3. Open the menu, click **Sign In**
4. Click **Continue with Google**
5. A popup opens showing the Google consent screen
6. Sign in with one of the test emails you added in step 3.3
7. The popup closes and you should be logged in

---

## Step 4: Final .env Configuration

Here is what a complete `.env` looks like with all auth configured:

```bash
# Spotify OAuth
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/api/spotify/callback
FRONTEND_URL=http://localhost:3000

# JWT (REQUIRED for any auth)
JWT_SECRET=a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1

# Google OAuth (OPTIONAL — leave blank to disable)
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-AbCdEfGhIjKlMnOpQrSt
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
```

**Minimum viable setup:** Only `JWT_SECRET` is required. Email+password auth works without any OAuth configuration. Google is optional — if the credentials are blank, the button returns a 503 with a "not configured" message.

---

## Step 5: Verify Everything Works

### 5.1 Backend Health Check

```bash
# Start the API server
python api.py

# Test email registration
curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "password": "testpass123"}' | python -m json.tool

# Test login
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "password": "testpass123"}' | python -m json.tool

# Test authenticated endpoint (replace TOKEN with access_token from login response)
curl -s http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer TOKEN" | python -m json.tool

# Test that public endpoints still work without auth
curl -s http://127.0.0.1:8000/api/universe | python -m json.tool | head -5

# Test that protected endpoints require auth
curl -s http://127.0.0.1:8000/api/projects
# Should return: {"detail":"Not authenticated"}
```

### 5.2 Frontend Walkthrough

1. Start both servers:
   ```bash
   python api.py                    # Terminal 1
   cd web && npm run dev            # Terminal 2
   ```
2. Open `http://localhost:3000`
3. The universe canvas loads without login (public)
4. Open the menu (hamburger icon top-left)
5. Click **CREATE** — you should see "Sign in to create and manage projects"
6. Click **SIGN IN** in the menu (or navigate to auth page)
7. Create an account with email+password
8. After signing in, the menu shows your name/email and a sign out button
9. Navigate to CREATE — you can now create projects
10. Connect Spotify and import playlists into a project

### 5.3 Token Refresh Test

Access tokens expire after 15 minutes. To verify auto-refresh works:

1. Sign in via the frontend
2. Open browser DevTools > Application > Local Storage
3. You should see a `refresh_token` key
4. Wait 15+ minutes (or temporarily change `ACCESS_TOKEN_EXPIRY` in `deepkt/auth.py` to `timedelta(seconds=10)` for testing)
5. Perform an action (e.g., load projects) — the frontend should silently refresh and continue working

---

## Production Deployment Notes

### Change These for Production

| Setting | Dev Value | Production Value |
|---------|-----------|-----------------|
| `JWT_SECRET` | `dev-secret-change-me...` | Random 64+ char string |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:8000/...` | `https://yourdomain.com/api/auth/google/callback` |
| `FRONTEND_URL` | `http://localhost:3000` | `https://yourdomain.com` |
| `CORS_ORIGINS` | (defaults to localhost) | `https://yourdomain.com` |

### Google Production Checklist

1. In Google Cloud Console > OAuth consent screen, click **Publish App**
2. This removes the test-user restriction so any Google account can sign in
3. Google may require verification if you request sensitive scopes (the ones we use — openid, email, profile — are non-sensitive so this is usually instant)
4. Update the **Authorized redirect URI** in your Google OAuth client to your production URL
5. Add your production domain to **Authorized JavaScript origins**

### Security Reminders

- Rate limiting is active: login is limited to 5 attempts/minute, registration to 3/minute per IP
- Refresh tokens use single-session rotation — each refresh invalidates the previous token
- Passwords are hashed with argon2id (memory-hard, resistant to GPU/ASIC attacks)
- Access tokens expire in 15 minutes; refresh tokens in 30 days

---

## Troubleshooting

### "Not authenticated" on all requests

- Check that `JWT_SECRET` is set in `.env`
- Make sure the frontend is sending the `Authorization: Bearer <token>` header (check DevTools > Network tab)

### Google OAuth popup opens but shows an error

- **"redirect_uri_mismatch"**: The redirect URI in your `.env` doesn't match what's configured in Google Cloud Console. They must be identical — check for trailing slashes, http vs https, port numbers.
- **"access_denied"**: Your Google account isn't in the test users list. Add it in OAuth consent screen > Test users.
- **"invalid_client"**: Double-check `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in your `.env`.

### "Google OAuth not configured" (503)

- This means `GOOGLE_CLIENT_ID` is blank in `.env`. Set the credentials to enable Google sign-in.

### Token expired immediately after login

- Check your system clock — JWT expiry relies on accurate time. Run `date` and verify it's correct.
- If testing with short expiry, make sure you set it back to 15 minutes afterward.

### Rate limit errors (429)

- Login: max 5 attempts per minute per IP
- Registration: max 3 attempts per minute per IP
- Wait 60 seconds and try again

### Projects disappeared after adding auth

- Projects are now per-user. The old file-based projects in `data/projects/` are no longer used. Each user starts with empty project slots. If you need to migrate old projects, you'll need to create a user first and then insert the project data into the `projects` table in SQLite.
