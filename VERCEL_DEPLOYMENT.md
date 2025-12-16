# Vercel Deployment Guide

This guide explains how to deploy the colab91-ap-agent project to Vercel.

## Prerequisites

1. A Vercel account (sign up at https://vercel.com)
2. GitHub repository connected to Vercel
3. Environment variables configured (see below)

## Important Limitations

⚠️ **Note**: Vercel serverless functions have limitations that may affect this project:

1. **Size Limits**: Serverless functions have a 50MB limit. Heavy ML dependencies like:
   - `torch` (PyTorch)
   - `sentence-transformers`
   - `faiss-cpu`
   - `mlflow`
   
   May not work or may cause deployment issues.

2. **Cold Starts**: Serverless functions have cold start times, which may affect performance.

3. **Database**: The SQLite database (`data/classifications.db`) won't persist between deployments. Consider using:
   - Vercel Postgres
   - External database service (Supabase, PlanetScale, etc.)
   - S3 for file storage

## Deployment Steps

### Option 1: Deploy via Vercel CLI (Recommended)

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**:
   ```bash
   vercel login
   ```

3. **Deploy**:
   ```bash
   cd /Users/princesaxena/Desktop/gta/colab91-ap-agent
   vercel
   ```

4. **Follow the prompts**:
   - Link to existing project or create new
   - Confirm project settings
   - Deploy

5. **For production deployment**:
   ```bash
   vercel --prod
   ```

### Option 2: Deploy via GitHub Integration

1. **Go to Vercel Dashboard**: https://vercel.com/dashboard

2. **Click "Add New Project"**

3. **Import your GitHub repository**: `prince1823/colab91-ap-agent`

4. **Configure Project Settings**:
   - **Framework Preset**: Other
   - **Root Directory**: `./` (root)
   - **Build Command**: `cd frontend && npm install && npm run build`
   - **Output Directory**: `frontend/dist`
   - **Install Command**: `cd frontend && npm install`

5. **Add Environment Variables** (see below)

6. **Click Deploy**

## Environment Variables

Add these environment variables in Vercel Dashboard → Project Settings → Environment Variables:

### Required for API:
```
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

### Optional (if using Anthropic):
```
ANTHROPIC_API_KEY=your_anthropic_api_key
ANTHROPIC_MODEL=claude-3-opus-20240229
```

### Database Configuration:
```
DATABASE_PATH=/tmp/classifications.db
# Note: /tmp is ephemeral. Consider using external database.
```

### Storage Configuration:
```
STORAGE_TYPE=local
# Or use S3:
STORAGE_TYPE=s3
S3_BUCKET=your-bucket-name
S3_PREFIX=benchmarks/
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### Frontend (optional):
```
VITE_API_BASE_URL=/api/v1
```

## Project Structure

The deployment uses:
- **Frontend**: React app built with Vite, served as static files
- **API**: FastAPI app wrapped in serverless function at `/api/index.py`
- **Routing**: All `/api/*` requests go to the Python serverless function
- **Static Files**: All other requests serve the React app

## Troubleshooting

### Build Failures

1. **Python dependencies too large**:
   - Remove heavy ML packages from `requirements.txt`
   - Use external ML services via API calls instead

2. **Frontend build fails**:
   - Check Node.js version (Vercel uses Node 18+ by default)
   - Ensure all dependencies are in `package.json`

### Runtime Errors

1. **Module not found**:
   - Check that all dependencies are in `requirements.txt`
   - Verify Python path in `api/index.py`

2. **Database errors**:
   - SQLite files in `/tmp` are ephemeral
   - Consider using external database service

3. **CORS errors**:
   - Set `CORS_ORIGINS` environment variable
   - Include your Vercel domain in the list

### Function Timeout

- Default timeout is 10 seconds (Hobby plan)
- Upgrade to Pro for longer timeouts
- Optimize API endpoints for faster responses

## Alternative Deployment Options

If Vercel limitations are too restrictive, consider:

1. **Railway**: Better for Python apps with large dependencies
2. **Render**: Good for full-stack apps
3. **Fly.io**: Supports Docker, good for complex apps
4. **AWS/GCP/Azure**: More control, but more setup required

## Post-Deployment

1. **Test the API**: Visit `https://your-app.vercel.app/api/health`
2. **Test the Frontend**: Visit `https://your-app.vercel.app`
3. **Check Logs**: Vercel Dashboard → Functions → View Logs

## Updating the Deployment

After pushing to GitHub:
- Vercel will automatically redeploy if GitHub integration is set up
- Or run `vercel --prod` from CLI

