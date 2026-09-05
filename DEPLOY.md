# Deploying RecoverAI

```
 Browser ──► Vercel (React static)  ──/api/*──►  Render (FastAPI + SQLite, Docker)
```

The backend keeps state (SQLite, background batch runs), so it needs a real server, not
serverless. Vercel hosts the UI; Render hosts the API. Total cost: ₹0 on free tiers.

## 1. Backend → Render (5 min)

1. Push this repo to GitHub.
2. https://dashboard.render.com → **New → Blueprint** → pick the repo. Render reads `render.yaml`.
3. When prompted, paste `OPENAI_API_KEY` (OpenRouter `sk-or-v1-…` or OpenAI `sk-…`).
4. Click **Apply**. First build ≈ 3–4 min. You get a URL like `https://recoverai-api.onrender.com`.
5. Check `https://recoverai-api.onrender.com/api/health` → `{"ok": true, ...}`.

> Free Render instances sleep after 15 min idle; the first request takes ~30 s to wake.
> Open the API URL once before your demo. Also note SQLite lives on the container disk —
> it re-seeds itself on redeploy, which is fine for a demo.

## 2. Frontend → Vercel (3 min)

1. Edit `frontend/vercel.json`: replace `YOUR-BACKEND.onrender.com` with your Render host. Commit + push.
2. https://vercel.com/new → import the repo.
3. **Root Directory → `frontend`** (click *Edit* next to root directory). Framework auto-detects Vite.
4. Deploy. No env vars needed — the `rewrites` in `vercel.json` proxy `/api/*` to Render
   server-side, so the browser only ever talks to your Vercel domain (no CORS).

### Via CLI instead

```bash
npm i -g vercel
cd frontend
vercel            # follow prompts; accept defaults
vercel --prod
```

## 3. Verify

- Open your Vercel URL → KPI row loads (that's `/api/metrics` round-tripping through Render).
- Click **Run recovery** → progress bar → 500 processed.
- Top-right pills should read `gpt-4.1` and `rzp_test · simulated`.

## Alternatives

| Want | Do |
|---|---|
| One URL, one service | Deploy only Render — the Dockerfile also serves the built React app at `/`. Skip Vercel. |
| Fly.io instead of Render | `fly launch --copy-config --no-deploy && fly secrets set OPENAI_API_KEY=… && fly deploy` (`fly.toml` included, region `bom`). |
| Railway | New project → Deploy from repo → it detects the `Dockerfile`. Set `OPENAI_API_KEY`. |
| Frontend elsewhere (Netlify etc.) | Build with `VITE_API_BASE=https://your-api` so requests go cross-origin (CORS is already `*`). |

## Why not the backend on Vercel too?

Vercel Python functions are stateless: the filesystem is read-only except `/tmp` (SQLite
would reset on every cold start), background threads are killed when the response returns
(so `POST /api/agent/recover` would never finish), and functions time out at 10–60 s. It
could be hacked to work by running the batch synchronously in small pages, but that
changes the product for no benefit when Render is free.
