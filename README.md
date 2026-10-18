# Finvait

**Your voice. Your money, in focus.**

Finvait is a voice-first personal finance assistant concept for making everyday spending easier to understand through natural conversation. It is being built around the way people actually describe expenses—in Hindi, Hinglish, and English—and aims to turn transaction records into clear, useful answers.

> **Project status:** This repository contains a working local MVP and presentation demo. Some flows use real local speech transcription; preset transaction examples and the SMS ledger are illustrative. This is not a banking app and does not connect to a user's bank or messages.

## The idea

I spent a day building with Voice AI at the **Voice AI x Fintech Buildathon at Bachatt's office**. Hosted by **Anupam Singh**, Co-founder & CEO of Digia, and **Mayank Agarwal**, Co-founder & CEO of Bachatt, the buildathon was my first hands-on introduction to building with Voice AI.

My biggest takeaway was seeing how an AI agent can understand a person's money, respond to simple voice commands, and—when explicitly authorized—eventually take action on their behalf.

I started building **Finvait** around a simple idea: instead of manually maintaining spreadsheets and categorizing every purchase, someone should be able to tell an assistant what they spent and later ask questions like:

- Where did my spending increase this week?
- Which subscriptions are taking up too much of my budget?
- How have my spending habits changed?

The goal is to turn the transactions, receipts, and records that are tedious to maintain into financial information people can access through a conversation. The MVP is still a work in progress. The user-facing demo does not yet include connected WhatsApp messaging or a live phone-call experience; backend integration prototypes are present but need configuration and end-to-end deployment.

## User flow

### Try the local demo

1. Start the backend and frontend using the instructions below.
2. Open the Vite URL, usually `http://localhost:5173`.
3. Use the main microphone control to record a short expense or choose an audio file. Recording begins only after you grant microphone permission and start it.
4. Stop the recording and choose **Transcribe locally**. The local Whisper model returns a transcript. The MVP displays the transcript but does not turn custom audio into a saved transaction.
5. To explore the scripted experience, choose a preset note and run its demo. The preset transcript, extracted transaction JSON, and possible duplicate alert are illustrative and do not come from the uploaded audio or a live SMS.
6. Review the activity history and week-over-week comparison. Starter rows and subscription messages are illustrative and are stored in this browser's local storage.
7. Use **Generate speech** to create audio for the suggested response. **Copy audio link** shares a lightweight listening page rather than the full dashboard; open that link on a device that can reach the demo host.

## How it works

```text
Voice recording or audio upload
              │
              ▼
React client ── POST audio ──► FastAPI
                                  │
                                  ▼
                       faster-whisper (local)
                                  │
                                  ▼
                       Transcript in browser

Preset examples ──► Scripted demo results and illustrative duplicate review
Activity records ──► Browser local storage ──► Calendar-week comparison
Suggested response ──► Kokoro ONNX (local) ──► WAV audio / listening link
```

The intended product principle is that calculations and transaction records should be grounded in evidence: language models may help interpret a request or explain a result, but should not invent transactions, amounts, or reasons for spending changes. The current presentation experience is a prototype, and its preset demo data is clearly distinguished from live user data.

## Technology

| Area | Technology |
| --- | --- |
| Web app | React, TypeScript, Vite |
| API | Python, FastAPI, Pydantic |
| Local speech-to-text | `faster-whisper` with a multilingual Whisper model |
| Local text-to-speech | Kokoro ONNX with an open-source Kokoro model |
| Finance backend prototype | SQLite, deterministic finance calculations |
| Optional integrations | OpenAI API, WhatsApp Cloud API, Retell |
| Tests | Pytest; TypeScript and Vite production build |

No API key is needed for the browser's local Whisper transcription or Kokoro speech generation. Optional OpenAI, WhatsApp, and Retell services require their own credentials and provider setup. Never put backend secrets in frontend code or commit a populated `.env` file.

## Repository structure

```text
.
├── backend/
│   ├── app/
│   │   ├── config.py                 # Environment-based settings
│   │   ├── database.py               # SQLite transaction and call storage
│   │   ├── finance.py                # Deterministic finance answers
│   │   ├── integrations.py           # OpenAI, WhatsApp, and Retell adapters
│   │   ├── local_speech.py           # Local Kokoro ONNX speech generation
│   │   ├── local_transcription.py    # Local faster-whisper transcription
│   │   └── main.py                   # FastAPI routes and static serving
│   ├── data/                         # Local data and cached models (not committed)
│   ├── requirements.txt
│   └── tests/                        # API and finance tests
├── frontend/
│   ├── public/
│   │   ├── listen.html               # Standalone spoken-response player
│   │   └── voice-notes/              # Optional local demo audio files
│   ├── src/
│   │   ├── App.tsx                   # Demo, recorder, history, and speech UI
│   │   ├── main.tsx                  # React entry point
│   │   └── style.css                 # Responsive Finvait styles
│   ├── package.json
│   └── vite.config.ts                # Development API proxy
├── .env.example                      # Safe configuration template
├── .gitignore
└── README.md
```

## Run locally

Requirements: **Python 3.10+** and **Node.js 20.19+**.

### 1. Configure and start the backend

From the repository root, open a terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

If PowerShell blocks virtual-environment activation, use the Python executable directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

The `.env` file is optional for the local demo. Its default settings use demo mode and local transcription. The first Whisper transcription downloads the configured model and may take a few minutes; the default is the multilingual `base` model on CPU with int8 quantization. Set `LOCAL_WHISPER_MODEL` in `.env` to `tiny`, `base`, or `small` to choose another model.

### 2. Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints, normally `http://localhost:5173`. The development server forwards `/api` requests to the local FastAPI server at `http://127.0.0.1:8000`.

For microphone access, use `localhost` or another secure browser context and allow microphone permission. On another device on the same Wi-Fi, run Vite with `npm run dev -- --host 0.0.0.0` and open the network URL it prints. The backend remains local to the host. Browser microphone access on a plain HTTP LAN address may be blocked; uploading audio does not require microphone permission.

### Optional configuration

Add provider credentials only when developing those integrations. The available variable names and their purposes are documented in `.env.example`. Keep secrets out of Git; `.env` is ignored.

## Demo notes and trust boundaries

- Preset voice-note transactions, possible duplicate-payment alerts, subscription messages, and some comparison entries are illustrative presentation data—not verified account activity or messages.
- A possible match means **needs review**; it is not a fraud determination. The scripted confirmation actions affect the demo display only.
- Custom microphone recordings and uploads are sent to the local FastAPI backend for transcription. The transcription endpoint does not persist the audio or create a transaction; the transcript is shown in the current browser session.
- The activity history is stored in browser local storage. It is not synchronized to an account or backend.
- The Kokoro model files are downloaded on first use and cached under `backend\data\kokoro\`; synthesis then runs locally. Audio is returned as a WAV. Browsers may require a user tap to play audio.
- Do not use the scripted demo as a real financial record or present its sample data as live account activity.
- The backend includes WhatsApp webhook, Retell webhook/custom-function, and finance-query routes. These are integration prototypes; they require provider credentials, public callback configuration, authorization settings, and end-to-end testing. They are not connected to the presentation screen by default.
- Subscription cancellation, payments, and other consequential actions are not performed by this MVP.

## Checks

Run the backend tests from the repository root:

```powershell
python -m pytest -q
```

Build and type-check the frontend:

```powershell
cd frontend
npm run build
```

## Looking ahead

Finvait is still a work in progress. I’m excited to keep building, learning, and exploring what Voice AI can do to make personal finance more approachable—while keeping user consent, privacy, and reliable financial records at the center.

## Acknowledgements

Thank you to **Anupam Singh**, Co-founder & CEO of Digia, and **Mayank Agarwal**, Co-founder & CEO of Bachatt, for hosting the Voice AI x Fintech Buildathon at Bachatt's office and creating space to learn by building.
