# Backend Deployment on Render

This sets up the full-feature FastAPI backend (with `dspy-ai`, etc.) on Render and keeps the frontend on Vercel.

## What’s included
- `Dockerfile` to build and run the API at port 8000
- `.dockerignore` to keep the image small
- `render.yaml` to create a Render Web Service from the repo

## Deploy steps (Render)
1. Push these files to GitHub (already done on `main`).
2. In Render, click **New Web Service** → **Build and deploy from a repo** → select this repo.
3. Render will auto-detect `render.yaml`. Confirm the service name (e.g., `colab91-ap-agent-backend`).
4. Set environment variables (Render Dashboard → your service → Environment):
   - `OPENAI_API_KEY` = your key
   - `OPENAI_MODEL` = `gpt-4o-mini` (or your choice)
   - `CORS_ORIGINS` = `https://colab91-ap-agent-lake.vercel.app` (your Vercel frontend URL)
   - Optional: `ANTHROPIC_API_KEY`, `EXA_API_KEY`
5. Deploy. Health check path: `/health`.

## Frontend configuration (Vercel)
In your Vercel project for the frontend, set:
- `VITE_API_BASE_URL` = `https://<your-render-service>.onrender.com/api/v1`

After setting, redeploy the frontend (or push to `main` and let Vercel auto-deploy).

## Local test of Docker image
```bash
docker build -t ap-agent-backend .
docker run -p 8000:8000 ap-agent-backend
# test
curl http://localhost:8000/health
```

## Notes
- Render free/starter tiers may have cold starts; upgrade for more consistent performance.
- Torch and other heavy deps are installed inside the container (no Vercel 250MB limit issue).

