# Deploy Frontend to Railway

## Quick Deploy

### Option 1: Railway Dashboard (Recommended)

1. **Go to Railway Dashboard**
   - Visit https://railway.app/dashboard
   - Click **"New Project"**
   - Select **"Deploy from GitHub repo"**

2. **Configure Repository**
   - Choose: `glover1102/FinGPT`
   - Click **"Add variables"** and set:
     - **Root Directory:** `frontend`
   - Click **"Deploy"**

3. **Add Environment Variable**
   - Go to **Variables** tab
   - Add variable:
     ```
     VITE_API_BASE_URL=https://fingpt-production-c5b4.up.railway.app
     ```
   - Railway will auto-redeploy

4. **Get Your URL**
   - Go to **Settings** → **Domains**
   - Copy your Railway URL (e.g., `fingpt-frontend.up.railway.app`)
   - Visit it to see your dashboard! 🎉

### Option 2: Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Navigate to frontend
cd frontend

# Initialize and deploy
railway init
railway up

# Add environment variable
railway variables set VITE_API_BASE_URL=https://fingpt-production-c5b4.up.railway.app
```

## How It Works

### Build Process

1. Railway detects `nixpacks.toml`
2. Installs Node.js 20
3. Runs `npm install`
4. Runs `npm run build` (creates `dist/` folder)
5. Serves static files using `serve` on port 8080

### Configuration Files

- **`railway.toml`** - Railway service configuration
- **`nixpacks.toml`** - Build and start commands
- **`package.json`** - Includes `serve` dependency

### Environment Variables

| Variable | Value | Required |
|----------|-------|----------|
| `VITE_API_BASE_URL` | Your backend API URL | Yes |

**Default backend:** `https://fingpt-production-c5b4.up.railway.app`

## Architecture

```
User Browser
    ↓
Frontend (Railway Static Site)
    ↓ API calls
Backend API (Railway FastAPI Service)
```

## Troubleshooting

### Build Fails

**Check Node version:**
- Ensure `nixpacks.toml` specifies `nodejs_20`

**Check dependencies:**
```bash
cd frontend
npm install
npm run build
```

### Blank Page After Deploy

**Check environment variables:**
- Ensure `VITE_API_BASE_URL` is set in Railway dashboard
- Variables starting with `VITE_` must be set **before build time**

**Check browser console:**
- Open DevTools → Console
- Look for CORS or API errors

### API Calls Failing

**CORS issue:**
- Backend must allow frontend domain
- Check backend CORS settings in `trading_service/config.py`

**Wrong API URL:**
- Verify `VITE_API_BASE_URL` matches your backend Railway URL
- Check in Railway Variables tab

## Custom Domain (Optional)

1. Go to **Settings** → **Domains**
2. Click **"Add Custom Domain"**
3. Enter your domain (e.g., `sentiment.yoursite.com`)
4. Update DNS records as shown
5. Railway auto-provisions SSL certificate

## Cost

Frontend is a **static site** (~50MB):
- **Free tier:** More than enough
- **Pro tier:** $5/month (if needed)

Much cheaper than backend (uses minimal resources).

## Next Steps

1. ✅ Deploy frontend to Railway
2. ✅ Set `VITE_API_BASE_URL` environment variable
3. ✅ Visit your Railway URL
4. ✅ Test sentiment analysis
5. 🎉 Share your dashboard!

---

**Need help?** Check Railway logs in the dashboard for detailed error messages.
