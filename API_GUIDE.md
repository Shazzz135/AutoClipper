# AutoClipper: APIs, Authentication & Quota Guide

This guide details all APIs required by the pipeline, explaining which require keys, which work with zero authentication, how to set them up, and their daily quota limits.

---

## 1. Summary of Required APIs

| Service | API Used | Authentication Required? | Cost / Free Tier | What It Does In AutoClipper |
|---|---|---|---|---|
| **Twitch Chat** | Twitch IRC WebSocket | **NO (100% Free / Anonymous)** | Free / Unlimited | Reads real-time chat messages to calculate velocity spikes |
| **Twitch Stream** | Twitch Public HLS / Streamlink | **NO (100% Free / Anonymous)** | Free / Unlimited | Captures the live 720p60 stream video into the rolling buffer |
| **Twitch Metadata (Optional)** | Twitch Helix API (`api.twitch.tv`) | Optional (Client ID + Secret) | Free | Polls whether stream is online, current game title, and stream uptime |
| **YouTube** | YouTube Data API v3 | **YES (OAuth 2.0 Client ID)** | Free (10,000 quota units/day) | Uploads Shorts, sets title/description/tags, schedules `publishAt`, uploads custom thumbnail |
| **AI Titles/Descriptions** | Google Gemini API or OpenAI API | **Optional** (Free API key or Offline Fallback) | Free (Gemini Free Tier) | Generates high-CTR viral titles and descriptions based on transcript |

---

## 2. Twitch Ingestion: How It Works Without Keys

### A. Live Chat (Twitch IRC Protocol)
Twitch allows anonymous read-only access to any public chat without an account or API token:
- **Endpoint**: `wss://irc-ws.chat.twitch.tv:443`
- **Handshake**:
  ```text
  PASS SCHMOOPIE
  NICK justinfan12345
  JOIN #kaicenat
  ```
- **Advantages**:
  - No rate limits for receiving public chat messages.
  - No expiration, no OAuth refresh tokens, no ban risk.
  - Zero setup required.

### B. Live Stream Video (`streamlink`)
- `streamlink` uses Twitch's public HLS playlist endpoints to read the video chunks directly.
- **Command**:
  ```bash
  streamlink --twitch-disable-ads --twitch-low-latency twitch.tv/kaicenat 720p60 --stdout
  ```
- No Twitch login or API key required.

---

## 3. YouTube Data API v3 (Required for Auto-Upload)

To automatically upload and schedule videos on your YouTube channel, Google requires OAuth 2.0 authorization.

### Step 1: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click **Create Project** $\rightarrow$ Name it `AutoClipper`.
3. In the search bar, search for **YouTube Data API v3** and click **Enable**.

### Step 2: Configure OAuth Consent Screen
1. Go to **APIs & Services $\rightarrow$ OAuth consent screen**.
2. Select **External** and click **Create**.
3. Fill in:
   - App Name: `AutoClipper`
   - User Support Email: Your email
   - Developer Contact: Your email
4. Click **Save and Continue**.
5. Under **Scopes**, add:
   - `https://www.googleapis.com/auth/youtube.upload` (Upload videos)
   - `https://www.googleapis.com/auth/youtube` (Set thumbnails & metadata)
6. Under **Test Users**, add your personal Google/YouTube email address (this allows you to authenticate freely without undergoing Google app verification).

### Step 3: Create OAuth Client ID Credentials
1. Go to **APIs & Services $\rightarrow$ Credentials**.
2. Click **+ Create Credentials $\rightarrow$ OAuth client ID**.
3. Application Type: Select **Desktop App** (or Web Application).
4. Name: `AutoClipper-Uploader`.
5. Click **Create** $\rightarrow$ Click **Download JSON**.
6. Rename this file to `client_secrets.json` and place it in the `./config/` directory (or upload it via the dashboard).

### Step 4: First-Time Authentication Flow
- When AutoClipper boots for the first time, it will generate an authorization URL in the terminal and in the Web Dashboard.
- You click the link, log into your YouTube account, and click **Allow**.
- The app automatically receives the refresh token and saves `token.json`.
- **From then on, uploads happen 100% in the background without needing your interaction again.**

### YouTube API Quotas Explained
- Google gives **10,000 free quota units per day** (resets every midnight PST).
- **Cost per action**:
  - Video Upload: **1,600 units**
  - Set Custom Thumbnail: **50 units**
  - Update Video Metadata: **50 units**
- **Daily Capacity on Free Tier**:
  $$\frac{10,000\text{ units}}{1,650\text{ units/clip}} \approx 6\text{ YouTube Shorts per day}$$
- This is the ideal volume for high-performing Shorts channels (posting 2–4 scheduled Shorts per day).

---

## 4. AI Title & Description API (Option B)

### Recommended: Google Gemini API (Free Tier)
- **Why**: Gemini 1.5 Flash provides high quality, low latency, and is **completely free** for up to 15 requests/minute.
- **Setup**:
  1. Go to [Google AI Studio](https://aistudio.google.com/).
  2. Click **Get API Key** $\rightarrow$ Create Key.
  3. Enter the key into the AutoClipper dashboard settings or `.env` as `GEMINI_API_KEY=your_key_here`.

### Rate Limiting & Overuse Protection Engine
To guarantee zero unexpected billing and prevent 429 quota exhaustion:
1. **Per-Minute Window Limiter**:
   - Hard cap of **10 calls/minute** (well under the 15 RPM free tier boundary).
   - Uses a rolling sliding-window timestamp tracker.
2. **Daily Hard Ceiling Budget**:
   - Configurable daily limit: `AI_MAX_CALLS_PER_DAY=30` (resets every midnight).
   - Once 30 AI title calls have occurred in a single day, the AI generator locks itself down.
3. **Seamless Zero-Downtime Fallback**:
   - If either rate limit is hit, or if the API returns a network error / `429 Too Many Requests`, the pipeline **never crashes or stops clipping**.
   - It instantly and silently swaps to the **Offline Heuristic Title Generator** (extracting peak chat phrases and transcript keywords).
4. **Dashboard Quota Display**:
   - The React dashboard displays live AI quota consumption: e.g. `AI Calls Today: 4 / 30`.

### Built-in Fallback (Offline Heuristics)
If no Gemini or OpenAI key is provided, the app will **not crash or fail**. It automatically falls back to an internal title generator:
- Extracts high-frequency spoken keywords from the transcript + peak chat hype terms:
  - Example: `KAI CENAT LOSES HIS MIND 💀 #shorts`
  - Auto-generated description with stream timestamp, hashtags, and social links.

---

## 5. Security & Configuration Summary

All credentials will be stored in an isolated, git-ignored `./config/` volume:
```
config/
  ├── client_secrets.json   # Your YouTube OAuth credentials
  ├── token.json            # Auto-generated YouTube refresh token
  └── settings.json         # Channel name, posting slots, Gemini API key
```
This ensures your credentials persist safely across Docker container restarts without ever being baked into the image or exposed in git commits.
