# Finvait — voice expense demo

A small presenter-led prototype for demonstrating a Hindi/Hinglish voice-first finance assistant:

1. Choose one of two sample voice-note transcripts: “Aaj 200 ki sabzi order kari hai” or “Today i spend 100 for breakfast.”
2. Run the staged, simulated processing flow and show the illustrative structured expense JSON.
3. For the breakfast example, show an explicitly labelled sample payment alert, play the Hindi confirmation question through browser speech, and choose whether to treat it as the same payment or keep both records.

The two preset voice notes use scripted transcripts and results. Their audio files play locally in the browser; the preset processing does not transcribe them. The optional custom recording flow below does real local speech transcription. The demo does **not** read SMS or email, connect to a bank, or persist simulated results. Browser speech depends on the device's available speech synthesis voices.

The optional **Record a custom voice** flow captures audio in the browser and sends it to the local FastAPI backend, where `faster-whisper` transcribes it on the same computer. It requires no API key. The transcript is displayed but is not turned into a saved transaction; audio itself is not retained. The weekly comparison shows the named presentation voice-note records and clearly marked illustrative entries, and compares calendar weeks (Monday–Sunday).

The **Generate speech** action synthesizes the suggested agent response with [Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx), an open-source MIT-licensed local inference runtime using the Apache-2.0 Kokoro model. The Finvait backend downloads the int8 model (~108 MB) and voice pack (~26 MB) on first use, caches them under `backend\data\kokoro\`, and returns a WAV for the browser to play. No speech API key is used. Use **Copy audio link** to create a standalone `/listen.html` link; it opens a minimal audio-only page and generates the speech when opened, without loading the full Finvait site. Open the demo from its LAN address before copying the link so it can be shared with another device on the same Wi-Fi. The browser may require a tap on the audio play control. First-time model download requires internet access. The default voice is English (`af_sarah`); Kokoro also has Hindi voices, but this English response currently uses the English voice.

On the first page load, the comparison imports the four named finance audio files currently in `frontend\public\voice-notes\` as prior-week entries and adds three clearly marked illustrative entries to make both week totals visible. The supplied filenames are used as the correction because the local Whisper transcript for these short clips was unclear; exact transaction dates were not provided, so those four entries are assigned to last week without claiming a particular day. The gold purchase is categorized as an investment and excluded from spending totals. Synthetic amounts are visibly identified as **SAMPLE** and called out in the comparison notice. The SMS subscription panel and its generated user-facing agent response are also explicitly illustrative; no SMS is connected or read. These starter rows are seeded once in local storage; remove individual rows or use **Clear history** if needed.

## Local Whisper transcription setup

The open-source [whisperflow-local](https://github.com/cth9191/whisperflow-local) project is a Windows dictation app licensed under MIT and uses `faster-whisper`. Finvait uses the same open-source transcription engine in its existing backend; it does not install or run that separate desktop app, its CUDA-only large-v3-turbo configuration, or its optional Ollama cleanup model. The Finvait default is the multilingual `base` model running on CPU with int8 quantization.

Install backend dependencies and start the backend in a separate terminal:

```powershell
pip install -r backend\requirements.txt
uvicorn app.main:app --app-dir backend --reload --port 8000
```

The Vite development server proxies `/api` requests to `http://127.0.0.1:8000`. The first transcription downloads the selected model from Hugging Face and may take a few minutes; after that, transcription runs locally without sending audio to an external API. The model can be changed with `LOCAL_WHISPER_MODEL` (for example, `tiny`, `base`, or `small`). Microphone recording requires browser permission and a secure context such as `localhost`.

## Add anonymous voice-note audio

To use your own recordings, copy them into `frontend\public\voice-notes\` with these names:

- `voice-note-01.mp3` for the first anonymous note
- `voice-note-02.mp3` for the second anonymous note

The page automatically plays a file at that path when present. Alternatively, use **Add an audio clip** on either note to select a file from your computer. Keep recordings free of private details: browser-served files are publicly accessible to anyone who can reach the site. Local voice-note audio files are excluded from Git by default.

## Run the presentation

Requirements: Node.js 20.19+.

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). To create a production build:

```powershell
npm run build
```

## Prototype boundaries

- The payment alert is illustrative and is not retrieved from an SMS inbox.
- The “same payment” and “keep both” actions change only the presentation state; they do not change a financial ledger.
- The custom voice recorder uses real local Whisper transcription and saves reviewed transaction details only in the current browser. It does not synchronize records to an account or backend. WhatsApp ingestion and live phone calls are outside this presentation flow.
- This repository also contains an earlier FastAPI/SQLite and Retell integration prototype. The Finvait presentation screen does not currently call those services.

Do not use the scripted experience as a real financial record or present its sample data as live account activity.
