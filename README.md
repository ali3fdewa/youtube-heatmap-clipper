# 🎬 AI Viral YouTube Heatmap Clipper

Automatically detect viral moments in YouTube videos using **Most Replayed heatmap data**, then generate optimized short-form clips with **AI subtitles** and **smart cropping** — ready for TikTok, YouTube Shorts, and Instagram Reels.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-green?logo=flask&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-orange?logo=ffmpeg&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Features

- 🔥 **Heatmap Analysis** — Scrapes YouTube's "Most Replayed" data to find viral moments
- 🧠 **Viral Detection** — AI transcript analysis scores segments by virality
- ✂️ **Auto Clip Generation** — One-click export of selected segments
- 🗣️ **AI Subtitles** — Powered by `faster-whisper` with word-level timestamps
  - 📝 3-word chunking with active word **yellow highlight**
  - 🎨 Customizable font, font size, and position
- 🎯 **Smart Cropping** — Center crop, split layouts, or AI face tracking (OpenCV)
- 📐 **Multi-Format** — 9:16 (Shorts/TikTok/Reels), 1:1, 16:9, or original
- 📲 **Telegram Bot** — Send clips directly to Telegram
- 📂 **Batch Processing** — Process entire playlists or channels
- 🌐 **Web Dashboard** — Beautiful dark-themed UI with real-time progress

---

## 📸 How It Works

```
YouTube URL → Heatmap Scan → Viral Scoring → Select Segments → Generate Clips
                                                                    ↓
                                              AI Subtitles + Smart Crop + Export
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **FFmpeg** — [Download](https://ffmpeg.org/download.html) or `sudo apt install ffmpeg`
- **yt-dlp** — Installed automatically via pip

### Installation

```bash
# Clone the repo
git clone https://github.com/ali3fdewa/youtube-heatmap-clipper.git
cd youtube-heatmap-clipper

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open **http://localhost:5000** in your browser.

### 🐧 Server Deployment (Ubuntu / Debian)

On modern Debian-based systems (Debian 12+, Ubuntu 23.04+), you **must** use a virtual environment:

```bash
# Install prerequisites
sudo apt update
sudo apt install python3-full python3-venv ffmpeg -y

# Clone the repo
git clone https://github.com/ali3fdewa/youtube-heatmap-clipper.git
cd youtube-heatmap-clipper

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Open the firewall port
sudo ufw allow 5000

# Run the app
python app.py
```

> **Note:** Every time you SSH into your server, activate the venv first:
> ```bash
> cd youtube-heatmap-clipper
> source venv/bin/activate
> python app.py
> ```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `1` | Debug mode (`0` = off for production) |

```bash
# Example: run on port 8080 in production
export PORT=8080
export FLASK_DEBUG=0
python app.py
```

### 🍪 YouTube Cookies (Bot Detection Fix)

If YouTube blocks your server with *"Sign in to confirm you're not a bot"*, you need to export your browser cookies:

1. Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension
2. Go to [youtube.com](https://youtube.com) and make sure you're **logged in**
3. Click the extension icon → **Export** → save as `cookies.txt`
4. Upload `cookies.txt` to your project root on the server:
   ```bash
   scp cookies.txt user@your-server:~/youtube-heatmap-clipper/
   ```

The app **automatically detects** `cookies.txt` and passes it to yt-dlp.

### 🔧 Troubleshooting

| Error | Fix |
|-------|-----|
| `No supported JavaScript runtime` | `sudo apt install nodejs -y` |
| `Sign in to confirm you're not a bot` | Add `cookies.txt` (see above) |
| `externally-managed-environment` | Use a virtual environment (see Server Deployment) |

---

## 🏗️ Project Structure

```
youtube-heatmap-clipper/
├── app.py              # Flask web app + REST API
├── heatmap.py          # YouTube heatmap data extraction
├── clipper.py          # Video download + clip generation
├── subtitle.py         # AI subtitle engine (faster-whisper)
├── cropper.py          # Face detection + smart cropping
├── viral_detector.py   # Transcript-based viral scoring
├── telegram_bot.py     # Telegram bot integration
├── requirements.txt    # Python dependencies
├── static/
│   ├── app.js          # Frontend logic
│   └── style.css       # Custom styles
├── templates/
│   └── index.html      # Web dashboard
├── fonts/              # Custom fonts (TTF/OTF)
├── clips/              # Generated clips (gitignored)
├── downloads/          # Downloaded videos (gitignored)
└── logs/               # Application logs (gitignored)
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/api/system-check` | Check system dependencies |
| `POST` | `/api/scan` | Scan video for viral segments |
| `POST` | `/api/clips` | Generate clips from segments |
| `GET` | `/api/status/<job_id>` | Poll job progress |
| `POST` | `/api/manual-clip` | Create clip from manual time range |
| `POST` | `/api/batch` | Scan playlist/channel |
| `POST` | `/api/telegram/send` | Send clip to Telegram |
| `GET` | `/api/fonts` | List available fonts |
| `GET` | `/api/models` | List whisper models |

---

## 🗣️ Subtitle System

Subtitles use **faster-whisper** for transcription and generate **ASS (Advanced SubStation Alpha)** files with viral styling:

- **3-word chunks** — Shows 3 words at a time for readability
- **Active word highlight** — Currently spoken word appears in **yellow**
- **Customizable** — Font, font size (20–100), position (bottom/center)
- **Models** — tiny, base, small, medium, large-v3

---

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **AI/ML**: faster-whisper (speech-to-text), OpenCV (face detection)
- **Video**: FFmpeg, yt-dlp
- **Frontend**: HTML, TailwindCSS, Vanilla JS

---

## 📄 License

MIT License — feel free to use, modify, and distribute.

---

<p align="center">
  Built for short-form content creators 🚀
</p>
