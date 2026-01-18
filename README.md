# Nexli Brand Audit API

This script powers the automated Website & Brand Audit lead magnet for Nexli Automation.

## What It Does

1. Receives a webhook from GHL with a website URL
2. Takes a screenshot of the website using ScreenshotOne API
3. Sends the screenshot to Gemini for analysis
4. Returns a brutally honest scorecard to GHL
5. GHL emails the scorecard to the lead

---

## Setup Instructions

### Step 1: Create Accounts (Free Tiers)

**ScreenshotOne API:**
1. Go to https://screenshotone.com
2. Sign up for free account
3. Get your API access key from the dashboard
4. Free tier: 100 screenshots/month

**Google Gemini API:**
1. Go to https://makersuite.google.com/app/apikey
2. Sign in with Google account
3. Create an API key
4. Free tier: Very generous for this use case

**Railway:**
1. Go to https://railway.app
2. Sign up with GitHub account
3. Free tier: 500 hours/month (plenty for this)

---

### Step 2: Deploy to Railway

**Option A: Deploy via GitHub**
1. Create a new GitHub repository
2. Upload these 3 files: main.py, requirements.txt, Procfile
3. In Railway, click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Railway will auto-detect and deploy

**Option B: Deploy via Railway CLI**
1. Install Railway CLI: `npm install -g @railway/cli`
2. Login: `railway login`
3. Create project: `railway init`
4. Deploy: `railway up`

---

### Step 3: Set Environment Variables in Railway

In your Railway project dashboard, go to Variables and add:

```
SCREENSHOT_API_KEY=your_screenshotone_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

---

### Step 4: Get Your Railway URL

After deployment, Railway gives you a URL like:
`https://your-project-name.up.railway.app`

Your audit endpoint will be:
`https://your-project-name.up.railway.app/audit`

This is the URL you'll put in your GHL outbound webhook.

---

### Step 5: Connect to GHL

In your GHL workflow:

1. Add action: **Webhook (Outbound)**
2. URL: `https://your-project-name.up.railway.app/audit`
3. Method: POST
4. Body (JSON):
```json
{
  "website_url": "{{contact.website_url}}",
  "email": "{{contact.email}}",
  "name": "{{contact.name}}"
}
```

5. Add action: **Wait for Webhook Response** or use the response directly
6. Add action: **Send Email** with the scorecard from the response

---

## GHL Email Template

Use this in your GHL email action:

**Subject:** Your Website Audit Results Are In

**Body:**
```
Hi {{contact.name}},

Thanks for requesting your free Website & Brand Audit.

We analyzed your website and here are the results:

{{webhook.scorecard}}

---

Ready to fix these issues and start attracting high-quality clients?

Book a free strategy call: https://nexli.net/book

— The Nexli Team
```

---

## Testing

You can test the endpoint directly:

```bash
curl -X POST https://your-project-name.up.railway.app/audit \
  -H "Content-Type: application/json" \
  -d '{"website_url": "https://example.com", "email": "test@test.com", "name": "Test User"}'
```

---

## Troubleshooting

**"No website URL provided" error:**
- Check that your GHL webhook is sending `website_url` in the JSON body

**Screenshot API error:**
- Verify your SCREENSHOT_API_KEY is correct in Railway variables
- Check if you've hit the free tier limit (100/month)

**Gemini API error:**
- Verify your GEMINI_API_KEY is correct in Railway variables
- Make sure the API key has access to Gemini models

**Health check:**
- Visit `https://your-project-name.up.railway.app/health`
- Should return: `{"status": "healthy"}`

---

## Costs

All free tiers:
- ScreenshotOne: 100 screenshots/month free
- Gemini API: Generous free tier
- Railway: 500 hours/month free

For a lead magnet, this should cost $0 until you're getting serious volume.
