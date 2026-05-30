# API Keys Setup Guide

This document explains how to get free API keys for each service used in the automation pipeline.

---

## 1. Groq API (Recommended - Fastest)

Groq provides free, blazing-fast LLM inference for caption generation.

**Setup Steps:**
1. Go to https://console.groq.com
2. Sign up using Google or GitHub account
3. Navigate to **API Keys** section
4. Click **"Create API Key"**
5. Copy the key and add to `.env`:
   ```
   GROQ_API_KEY=gsk_your_key_here
   ```

**Free Tier Limits:**
- 30 requests per minute
- 500K tokens per day
- Access to models: Llama 3.3 70B, Mistral, Gemma, and more

**Models Available:**
- `llama-3.3-70b-versatile` (best quality)
- `llama-3.1-8b-instant` (fastest)

---

## 2. Gemini API (Free Backup)

Google's Gemini API as a free alternative for caption generation.

**Setup Steps:**
1. Visit https://aistudio.google.com/app/apikey
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the generated key and add to `.env`:
   ```
   GEMINI_API_KEY=AIza_your_key_here
   ```

**Free Tier Limits:**
- 60 requests per minute
- 1,000 requests per day
- Free usage tier (no credit card required)

---

## 3. Meta / Facebook Graph API

Required for posting content to your Facebook Page.

**Prerequisites:**
- A Facebook Page for your restaurant
- A Facebook Developer Account (free)

**Setup Steps:**

### Step 1: Create a Meta App
1. Go to https://developers.facebook.com/
2. Click **"My Apps"** → **"Create App"**
3. Choose **"Business"** as the app type
4. Fill in your app name and contact email
5. Note your **App ID** and **App Secret** from Settings → Basic

### Step 2: Get Page Access Token
1. Go to **Tools** → **Graph API Explorer**
2. Select your app from the dropdown
3. Select **"Get User Access Token"**
4. Select these permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
5. Click **"Generate Access Token"**
6. Click **"Add a Page"** → select your restaurant page
7. The token now has page permissions

### Step 3: Exchange for Long-Lived Token
The short-lived token expires in ~1 hour. Exchange it for a long-lived one:

```bash
curl -X GET "https://graph.facebook.com/v25.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_LIVED_TOKEN"
```

### Step 4: Get Your Page ID
```bash
curl -X GET "https://graph.facebook.com/v25.0/me/accounts?access_token=LONG_LIVED_TOKEN"
```

Find your page in the response and note the `id` field.

### Step 5: Configure .env
```
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_PAGE_ID=your_page_id
META_PAGE_ACCESS_TOKEN=your_long_lived_token
META_API_VERSION=v25.0
```

**Token Debug Tool:**
https://developers.facebook.com/tools/debug/accesstoken/

---

## 4. Ollama (Local - No Key Needed)

For completely offline caption generation with no API keys required.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2

# Start server
ollama serve
```

Add to `.env`:
```
OLLAMA_HOST=http://127.0.0.1
OLLAMA_PORT=11434
OLLAMA_MODEL=llama3.2
```

---

## API Key Priority System

The system automatically prioritizes providers:

1. **Groq** (if GROQ_API_KEY is set) - fastest
2. **Gemini** (if GEMINI_API_KEY is set) - free alternative
3. **Ollama** (if running locally) - fully offline

**Note:** You only need ONE caption provider for the system to work.

## Missing Keys Warning

If no API keys are configured, the system will still:
- ✅ Extract text via OCR
- ✅ Remove backgrounds
- ✅ Process images
- ✅ Use template-based fallback captions
- ❌ Won't generate AI-powered captions
- ❌ Won't post to Facebook (unless configured)

Check missing keys:
```bash
curl http://localhost:8000/api/config
```
