# Vercel Deployment Checklist

## Issues Fixed
✅ Frontend now loads transactions from API instead of static CSV file
✅ API calls use correct response field (`rows` instead of `items`)

## Required Configuration

### For Frontend Deployment (Vercel)

**Environment Variables to Set:**
1. `VITE_API_BASE_URL` = `https://your-backend-url.vercel.app/api/v1`
   - Replace `your-backend-url` with your actual backend Vercel deployment URL
   - This tells the frontend where to find the backend API

**Build Settings:**
- Root Directory: `frontend`
- Build Command: `npm run build` (or leave default)
- Output Directory: `dist`
- Install Command: `npm install` (or leave default)

### For Backend Deployment (Vercel)

**Environment Variables to Set:**
- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_MODEL` - Model name (e.g., `gpt-4o` or `gpt-4o-mini`)
- `CORS_ORIGINS` - Your frontend URL (e.g., `https://your-frontend.vercel.app`)
- Any other environment variables your backend needs

**Build Settings:**
- Root Directory: `./` (root of project)
- Build Command: (leave empty or `None`)
- Output Directory: (leave `N/A`)
- Install Command: `pip install -r requirements.txt`

## Testing After Deployment

1. **Test Backend Health:**
   ```
   https://your-backend-url.vercel.app/health
   ```
   Should return: `{"status": "healthy"}`

2. **Test Backend API:**
   ```
   https://your-backend-url.vercel.app/api/v1/transactions?dataset_id=innova&foldername=default&limit=10
   ```
   Should return transaction data

3. **Test Frontend:**
   - Visit your frontend URL
   - Check browser console for errors
   - Transactions should load from the API
   - Feedback should load from the API

## Common Issues

### Error: "Failed to load transactions"
- **Cause**: `VITE_API_BASE_URL` not set or incorrect
- **Fix**: Set the environment variable to your backend URL + `/api/v1`

### Error: CORS errors
- **Cause**: Backend `CORS_ORIGINS` doesn't include frontend URL
- **Fix**: Add frontend URL to backend's `CORS_ORIGINS` environment variable

### Error: SSL Protocol Error
- **Cause**: API URL is incorrect (e.g., using HTTP instead of HTTPS, or wrong port)
- **Fix**: Make sure `VITE_API_BASE_URL` uses HTTPS and the correct Vercel domain

### Error: 404 on API endpoints
- **Cause**: Backend not deployed or wrong URL
- **Fix**: Verify backend is deployed and URL is correct

## Quick Reference

**Frontend Environment Variable:**
```
VITE_API_BASE_URL=https://your-backend.vercel.app/api/v1
```

**Backend Environment Variables:**
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
CORS_ORIGINS=https://your-frontend.vercel.app
```

