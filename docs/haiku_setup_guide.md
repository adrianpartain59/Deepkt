# Claude Haiku Setup Guide for AMBIS

This guide explains how to connect Claude Haiku (Anthropic's fast, affordable LLM) to AMBIS for genre analysis.

---

## 1. Create an Anthropic Account

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up with email or Google
3. Verify your email address

## 2. Add Billing / Credits

Haiku is extremely affordable but requires an active billing plan or credits:

1. Go to **Settings > Billing** in the Anthropic Console
2. Add a payment method (credit card)
3. Optionally add credits — Haiku costs roughly:
   - **Input**: $0.80 per million tokens
   - **Output**: $4.00 per million tokens
   - A typical genre analysis request uses ~500 input tokens + ~800 output tokens = **~$0.004 per request**
   - At this rate, 1,000 analyses costs about **$4.00**

## 3. Generate an API Key

1. Go to [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
2. Click **"Create Key"**
3. Give it a descriptive name like `ambis-genre-analysis`
4. Copy the key — it starts with `sk-ant-api03-...`
5. **Store it securely** — you won't be able to see the full key again

## 4. Configure AMBIS — Local Development

### Option A: `.env` file (recommended for local dev)

Create or edit the `.env` file in the AMBIS project root:

```bash
# /Users/adrianpartain/LocalStorage/Developer/AMBIS/.env
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
```

The FastAPI server loads `.env` automatically via `python-dotenv`.

### Option B: Export in terminal

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
```

This only lasts for the current terminal session.

### Verify locally

Start the backend server and test:

```bash
# Start the server
python -m uvicorn api:app --reload --port 8000

# Test the analyze endpoint (requires auth token)
curl -X POST http://localhost:8000/api/projects/1/analyze \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "dark minimal techno like Surgeon, Regis, and Female"}'
```

Expected response:
```json
{
  "status": "success",
  "tags": ["dark minimal techno", "Birmingham industrial techno", "steely dub techno"],
  "seed_artists": ["Surgeon", "Regis", "Female", "...27 more..."],
  "message": null,
  "filtered_out": []
}
```

If you get `503 LLM service not configured`, the API key is not set or not being read.

## 5. Configure AMBIS — Railway (Production)

1. Go to your Railway project dashboard
2. Click on the AMBIS service
3. Go to **Variables** tab
4. Click **"New Variable"**
5. Set:
   - **Name**: `ANTHROPIC_API_KEY`
   - **Value**: `sk-ant-api03-YOUR-KEY-HERE`
6. Click **"Add"**
7. Railway will automatically redeploy with the new variable

### Verify on Railway

After deploy completes, test the endpoint against your production URL:

```bash
curl -X POST https://your-app.railway.app/api/projects/1/analyze \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "dark minimal techno like Surgeon, Regis, and Female"}'
```

## 6. Model Details

AMBIS uses **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`):
- Fastest Claude model — typical response in 1-2 seconds
- Cheapest Claude model — fractions of a cent per request
- Strong enough for genre classification and artist knowledge

The model ID is configured in `deepkt/llm.py`. To change models:

```python
# deepkt/llm.py
MODEL = "claude-haiku-4-5-20251001"  # Change this to switch models
```

Other options:
- `claude-sonnet-4-6` — more capable, ~5x cost
- `claude-opus-4-6` — most capable, ~30x cost

## 7. Troubleshooting

### "LLM service not configured" (503)
- The `ANTHROPIC_API_KEY` environment variable is not set
- Check `.env` file exists and has the key
- Restart the server after adding the key

### "Authentication error" from Anthropic
- The API key is invalid or expired
- Generate a new key at console.anthropic.com/settings/keys
- Make sure you copied the full key including the `sk-ant-` prefix

### "Rate limit exceeded" from Anthropic
- You've hit Anthropic's rate limits (not AMBIS's)
- Default tier: 50 requests/minute for Haiku
- Wait a moment and retry, or upgrade your Anthropic plan

### "Insufficient credits" from Anthropic
- Add more credits or set up a billing plan at console.anthropic.com

### Haiku returns unexpected results
- Check `deepkt/llm.py` system prompt for the instructions
- Raw LLM output is displayed on the project page for debugging
- Look at the `filtered_out` field to see which artists were excluded

## 8. Security Notes

- **Never commit your API key** to git. The `.env` file is in `.gitignore`.
- The key is only used server-side (Python backend). It is never sent to the browser.
- Each analyze request is rate-limited to 10/minute per user via the AMBIS API.
- Monitor usage at [console.anthropic.com/settings/usage](https://console.anthropic.com/settings/usage)
