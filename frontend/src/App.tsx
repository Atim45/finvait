import { useEffect, useRef, useState } from "react";

type DemoExpense = {
  id: "vegetables" | "breakfast";
  transcript: string;
  amount: number;
  category: string;
  merchant: string;
  paymentMethod: string;
  time: string;
};

type Stage = "idle" | "processing" | "extracted" | "duplicate" | "resolved" | "separate";

type ProcessedExpense = {
  id: string;
  transcript: string;
  amount: number;
  category: string;
  paymentMethod: string;
  date: string;
  processedAt: string;
  origin?: "voice_note" | "illustrative" | "reviewed";
  datePrecision?: "day" | "week";
  displayLabel?: string;
  sourceNote?: string;
  extractionNote?: string;
  excludeFromSpend?: boolean;
  matchLabel?: string;
};

type DemoSmsLedgerEntry = {
  id: string;
  date: string;
  sender: string;
  message: string;
  merchant: string;
  amount: number;
};

const historyStorageKey = "finvait.processed-expenses.v1";
const historySeededKey = "finvait.processed-expenses.seeded.v1";
const subscriptionSeededKey = "finvait.processed-expenses.subscription-seeded.v1";
const duplicateSeededKey = "finvait.processed-expenses.duplicate-seeded.v1";

function todayLocalDate() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayLocalDateFor(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getWeekStart(date: Date) {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const daysSinceMonday = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - daysSinceMonday);
  return start;
}

function formatDate(date: Date) {
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function historyDateLabel(item: ProcessedExpense) {
  const date = new Date(`${item.date}T00:00:00`);
  return item.datePrecision === "week"
    ? `Week of ${date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} · exact day not provided`
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function isProcessedExpense(value: unknown): value is ProcessedExpense {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ProcessedExpense>;
  return typeof item.id === "string"
    && typeof item.transcript === "string"
    && typeof item.amount === "number"
    && Number.isFinite(item.amount)
    && item.amount > 0
    && typeof item.category === "string"
    && typeof item.paymentMethod === "string"
    && typeof item.date === "string"
    && /^\d{4}-\d{2}-\d{2}$/.test(item.date)
    && typeof item.processedAt === "string";
}

function makeHistorySeed(): ProcessedExpense[] {
  const currentWeek = getWeekStart(new Date());
  const lastWeekStart = new Date(currentWeek);
  lastWeekStart.setDate(lastWeekStart.getDate() - 7);
  const lastWeekDate = todayLocalDateFor(lastWeekStart);
  const sampleDate = (week: Date, daysAfterMonday: number) => {
    const date = new Date(week);
    date.setDate(date.getDate() + daysAfterMonday);
    return todayLocalDateFor(date);
  };
  const processedAt = new Date().toISOString();

  return [
    {
      id: "voice-gold-investment-2000-v1",
      transcript: "Filename says: invested ₹2,000 in gold",
      displayLabel: "Gold investment",
      amount: 2000,
      category: "Investment",
      paymentMethod: "Not stated",
      date: lastWeekDate,
      processedAt,
      origin: "voice_note",
      datePrecision: "week",
      sourceNote: "Invested 2000 on gold.mp3",
      extractionNote: "Whisper transcription was unclear; classified using your filename. Exact day not provided.",
      excludeFromSpend: true,
    },
    {
      id: "voice-family-support-1000-v1",
      transcript: "Filename says: paid ₹1,000 to college-going child",
      displayLabel: "College support",
      amount: 1000,
      category: "Family support",
      paymentMethod: "Not stated",
      date: lastWeekDate,
      processedAt,
      origin: "voice_note",
      datePrecision: "week",
      sourceNote: "Payed 1000 to child who is college going.mp3",
      extractionNote: "Whisper transcription was unclear; classified using your filename. Exact day not provided.",
    },
    {
      id: "voice-family-dinner-200-v1",
      transcript: "Filename says: paid ₹200 for family dinner",
      displayLabel: "Family dinner",
      amount: 200,
      category: "Dining",
      paymentMethod: "Not stated",
      date: lastWeekDate,
      processedAt,
      origin: "voice_note",
      datePrecision: "week",
      sourceNote: "Payed 200 for family dinner.mp3",
      extractionNote: "Whisper transcription was unclear; classified using your filename. Exact day not provided.",
    },
    {
      id: "voice-barber-200-v1",
      transcript: "Filename says: paid ₹200 at barber",
      displayLabel: "Barber",
      amount: 200,
      category: "Personal care",
      paymentMethod: "Not stated",
      date: lastWeekDate,
      processedAt,
      origin: "voice_note",
      datePrecision: "week",
      sourceNote: "Payed 200 ruppes at barber.mp3",
      extractionNote: "Whisper transcription was unclear; classified using your filename. Exact day not provided.",
    },
    {
      id: "sample-groceries-last-week-v1",
      transcript: "Fresh produce and pantry staples",
      amount: 350,
      category: "Groceries",
      paymentMethod: "UPI",
      date: sampleDate(lastWeekStart, 3),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      extractionNote: "Illustrative presentation entry.",
    },
    {
      id: "sample-groceries-this-week-v1",
      transcript: "Household groceries",
      amount: 450,
      category: "Groceries",
      paymentMethod: "UPI",
      date: sampleDate(currentWeek, 1),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      extractionNote: "Illustrative presentation entry.",
    },
    {
      id: "sample-transport-this-week-v1",
      transcript: "Local transport",
      amount: 120,
      category: "Transport",
      paymentMethod: "Cash",
      date: sampleDate(currentWeek, 3),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      extractionNote: "Illustrative presentation entry.",
    },
    {
      id: "sample-netflix-subscription-this-week-v1",
      transcript: "Netflix subscription",
      displayLabel: "Netflix subscription",
      amount: 149,
      category: "Subscription",
      paymentMethod: "Card",
      date: sampleDate(currentWeek, 1),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      extractionNote: "Illustrative presentation amount; replace with the actual bill.",
    },
    {
      id: "sample-openai-api-usage-this-week-v1",
      transcript: "OpenAI API usage",
      displayLabel: "OpenAI API usage",
      amount: 250,
      category: "AI services",
      paymentMethod: "Card",
      date: sampleDate(currentWeek, 3),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      extractionNote: "Illustrative presentation amount; replace with the actual usage charge.",
    },
    {
      id: "sample-online-payment-possible-duplicate-v1",
      transcript: "Online payment · ₹100.00",
      displayLabel: "Online payment · ₹100.00",
      amount: 100,
      category: "Food & dining",
      paymentMethod: "UPI",
      date: sampleDate(currentWeek, 4),
      processedAt,
      origin: "illustrative",
      datePrecision: "day",
      excludeFromSpend: true,
      matchLabel: "Possible match: breakfast voice note · ₹100.00",
    },
  ];
}

const demoSmsLedger: DemoSmsLedgerEntry[] = [
  {
    id: "video-plan-september",
    date: "2026-09-05",
    sender: "DEMO-BANK",
    message: "Recurring card payment",
    merchant: "VisionPlay",
    amount: 149,
  },
  {
    id: "video-plan-october",
    date: "2026-10-05",
    sender: "DEMO-BANK",
    message: "Recurring card payment",
    merchant: "VisionPlay",
    amount: 179,
  },
  {
    id: "music-plan-september",
    date: "2026-09-12",
    sender: "DEMO-BANK",
    message: "Monthly UPI autopay",
    merchant: "SoundSpace",
    amount: 99,
  },
  {
    id: "music-plan-october",
    date: "2026-10-12",
    sender: "DEMO-BANK",
    message: "Monthly UPI autopay",
    merchant: "SoundSpace",
    amount: 99,
  },
];

const demoSubscriptions = [
  { merchant: "VisionPlay", cadence: "Monthly · card", latest: 179, change: 30, changePercent: 20.1, status: "Price increased" },
  { merchant: "SoundSpace", cadence: "Monthly · UPI", latest: 99, change: 0, changePercent: 0, status: "Amount unchanged" },
];

const demoExpenses: DemoExpense[] = [
  {
    id: "vegetables",
    transcript: "Aaj 200 ki sabzi order kari hai",
    amount: 200,
    category: "Groceries",
    merchant: "Local vegetable shop",
    paymentMethod: "Not specified",
    time: "Today",
  },
  {
    id: "breakfast",
    transcript: "Today i spend 100 for breakfast.",
    amount: 100,
    category: "Food & dining",
    merchant: "Breakfast",
    paymentMethod: "Not specified",
    time: "Today",
  },
];

const duplicateQuestion = "Kya aapne ₹100 ka payment online, subah 10 baje kiya tha?";

function formatRupees(amount: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

function VoiceNoteCard({
  expense,
  active,
  stage,
  recording,
  onSelect,
  onFile,
}: {
  expense: DemoExpense;
  active: boolean;
  stage: Stage;
  recording: File | null;
  onSelect: () => void;
  onFile: (file: File | null) => void;
}) {
  const [recordingUrl, setRecordingUrl] = useState("");
  const [localAudioFailed, setLocalAudioFailed] = useState(false);
  const noteNumber = expense.id === "vegetables" ? "01" : "02";
  const localAudioPath = `${import.meta.env.BASE_URL}voice-notes/voice-note-${noteNumber}.mp3`;

  useEffect(() => {
    setLocalAudioFailed(false);
    if (!recording) {
      setRecordingUrl("");
      return;
    }
    const url = URL.createObjectURL(recording);
    setRecordingUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [recording]);

  const audioSource = recordingUrl || (!localAudioFailed ? localAudioPath : "");

  return (
    <article className={`note-card ${active ? "selected" : ""}`} onClick={onSelect}>
      <div className="note-topline">
        <span className="note-index">{noteNumber}</span>
        <span className={`note-state ${stage === "resolved" ? "state-done" : ""}`}>
          {stage === "resolved" ? "Reconciled" : stage === "duplicate" ? "Review needed" : "Anonymous"}
        </span>
      </div>
      <h3>Voice note {noteNumber}</h3>
      {audioSource ? (
        <audio
          className="uploaded-audio"
          controls
          src={audioSource}
          onError={() => {
            if (!recordingUrl) setLocalAudioFailed(true);
          }}
          onClick={(event) => event.stopPropagation()}
        >
          Your browser cannot play this recording.
        </audio>
      ) : (
        <label className="recording-upload" onClick={(event) => event.stopPropagation()}>
          <span className="upload-icon">↑</span>
          <span>{recording ? "Audio clip selected" : "Add an audio clip"}</span>
          <input
            type="file"
            accept="audio/*,.m4a,.ogg,.opus,.webm"
            onChange={(event) => {
              onFile(event.target.files?.[0] ?? null);
              setLocalAudioFailed(false);
            }}
          />
        </label>
      )}
      <button className="text-button" onClick={(event) => { event.stopPropagation(); onSelect(); }}>
        {active ? "Selected for demo" : "Select this voice note"} <span>→</span>
      </button>
    </article>
  );
}

export default function App() {
  const [activeId, setActiveId] = useState<DemoExpense["id"]>("breakfast");
  const [customMode, setCustomMode] = useState(false);
  const [customRecording, setCustomRecording] = useState(false);
  const [customAudio, setCustomAudio] = useState<Blob | null>(null);
  const [customTranscript, setCustomTranscript] = useState("");
  const [customTranscribing, setCustomTranscribing] = useState(false);
  const [customSeconds, setCustomSeconds] = useState(0);
  const [customError, setCustomError] = useState("");
  const [customAudioUrl, setCustomAudioUrl] = useState("");
  const [processedExpenses, setProcessedExpenses] = useState<ProcessedExpense[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [agentCopyState, setAgentCopyState] = useState("");
  const [listenLinkState, setListenLinkState] = useState("");
  const [speechAudioUrl, setSpeechAudioUrl] = useState("");
  const [speechGenerating, setSpeechGenerating] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [recordings, setRecordings] = useState<Record<string, File | null>>({});
  const [spoken, setSpoken] = useState(false);
  const [processingLabel, setProcessingLabel] = useState("Loading demo transcript");
  const [error, setError] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTickRef = useRef<number | undefined>(undefined);
  const recordingLimitRef = useRef<number | undefined>(undefined);
  const expense = demoExpenses.find((item) => item.id === activeId) ?? demoExpenses[1];
  const currentWeekStart = getWeekStart(new Date());
  const previousWeekStart = new Date(currentWeekStart);
  previousWeekStart.setDate(previousWeekStart.getDate() - 7);
  const currentWeekEnd = new Date(currentWeekStart);
  currentWeekEnd.setDate(currentWeekEnd.getDate() + 6);
  const previousWeekEnd = new Date(currentWeekStart);
  previousWeekEnd.setDate(previousWeekEnd.getDate() - 1);
  const currentWeekStartKey = todayLocalDateFor(currentWeekStart);
  const currentWeekEndKey = todayLocalDateFor(currentWeekEnd);
  const previousWeekStartKey = todayLocalDateFor(previousWeekStart);
  const previousWeekEndKey = todayLocalDateFor(previousWeekEnd);
  const thisWeekExpenses = processedExpenses.filter(
    (item) => item.date >= currentWeekStartKey && item.date <= currentWeekEndKey && !item.excludeFromSpend,
  );
  const lastWeekExpenses = processedExpenses.filter(
    (item) => item.date >= previousWeekStartKey && item.date <= previousWeekEndKey && !item.excludeFromSpend,
  );
  const lastWeekInvestments = processedExpenses.filter(
    (item) => item.date >= previousWeekStartKey && item.date <= previousWeekEndKey && item.excludeFromSpend,
  );
  const thisWeekTotal = thisWeekExpenses.reduce((total, item) => total + item.amount, 0);
  const lastWeekTotal = lastWeekExpenses.reduce((total, item) => total + item.amount, 0);
  const lastWeekVoiceNotesTotal = lastWeekExpenses
    .filter((item) => item.origin === "voice_note")
    .reduce((total, item) => total + item.amount, 0);
  const lastWeekSampleTotal = lastWeekExpenses
    .filter((item) => item.origin === "illustrative" && !item.excludeFromSpend)
    .reduce((total, item) => total + item.amount, 0);
  const thisWeekSampleTotal = thisWeekExpenses
    .filter((item) => item.origin === "illustrative" && !item.excludeFromSpend)
    .reduce((total, item) => total + item.amount, 0);
  const comparisonDifference = thisWeekTotal - lastWeekTotal;
  const comparisonPercent = lastWeekTotal > 0
    ? Math.round((comparisonDifference / lastWeekTotal) * 100)
    : null;
  const agentResponseParagraph = comparisonDifference < 0
    ? `You spent ${formatRupees(lastWeekTotal)} last week and ${formatRupees(thisWeekTotal)} this week. That's ${formatRupees(Math.abs(comparisonDifference))} less this week—nice work keeping your spending down!`
    : comparisonDifference > 0
      ? `You spent ${formatRupees(lastWeekTotal)} last week and ${formatRupees(thisWeekTotal)} this week. That's ${formatRupees(comparisonDifference)} more this week. Want to take a look at what changed?`
      : `You spent ${formatRupees(lastWeekTotal)} last week and ${formatRupees(thisWeekTotal)} this week, so your tracked spending is about the same.`;
  const spokenResponseText = agentResponseParagraph.replace(/₹\s*([\d,]+)(?:\.(\d{2}))?/g, (_, whole: string, paise?: string) => (
    `${whole.replace(/,/g, "")} rupees${paise && paise !== "00" ? ` and ${Number(paise)} paise` : ""}`
  ));

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(historyStorageKey);
      let parsed: unknown = [];
      if (stored) {
        parsed = JSON.parse(stored);
        if (!Array.isArray(parsed)) {
          throw new Error("Saved expense history has an invalid format.");
        }
      }
      const expenses = Array.isArray(parsed)
        ? (parsed as unknown[]).filter(isProcessedExpense)
        : [];
      const seeded = window.localStorage.getItem(historySeededKey) === "true";
      const subscriptionsSeeded = window.localStorage.getItem(subscriptionSeededKey) === "true";
      const duplicateSeeded = window.localStorage.getItem(duplicateSeededKey) === "true";
      const historySeeds = makeHistorySeed();
      const seedsById = new Map(historySeeds.map((item) => [item.id, item]));
      const migrated = expenses.map((item) => {
      const seed = seedsById.get(item.id);
      if (!seed) return item;
      return {
        ...seed,
        ...item,
        transcript: seed.transcript,
        displayLabel: seed.displayLabel,
        origin: seed.origin,
        sourceNote: seed.sourceNote,
        extractionNote: seed.extractionNote,
        excludeFromSpend: seed.excludeFromSpend,
        matchLabel: seed.matchLabel,
        date: item.date,
        processedAt: item.processedAt,
      };
      });
      const existingIds = new Set(migrated.map((item) => item.id));
      const subscriptionSeedIds = new Set([
        "sample-netflix-subscription-this-week-v1",
        "sample-openai-api-usage-this-week-v1",
      ]);
      const duplicateSeedIds = new Set(["sample-online-payment-possible-duplicate-v1"]);
      const imported = historySeeds.filter((item) => (
        !existingIds.has(item.id)
        && (
          !seeded
          || (!subscriptionsSeeded && subscriptionSeedIds.has(item.id))
          || (!duplicateSeeded && duplicateSeedIds.has(item.id))
        )
      ));
      const merged = [...migrated, ...imported];
      setProcessedExpenses(merged);
      if (!seeded) window.localStorage.setItem(historySeededKey, "true");
      if (!subscriptionsSeeded) window.localStorage.setItem(subscriptionSeededKey, "true");
      if (!duplicateSeeded) window.localStorage.setItem(duplicateSeededKey, "true");
    } catch {
      setHistoryError("Could not read saved expense history from this browser.");
    } finally {
      setHistoryReady(true);
    }
  }, []);

  useEffect(() => {
    if (!historyReady) return;
    try {
      window.localStorage.setItem(historyStorageKey, JSON.stringify(processedExpenses));
    } catch {
      setHistoryError("Could not save history in this browser. Check local storage availability.");
    }
  }, [historyReady, processedExpenses]);

  useEffect(() => {
    if (!customAudio) {
      setCustomAudioUrl("");
      return;
    }
    const url = URL.createObjectURL(customAudio);
    setCustomAudioUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [customAudio]);

  useEffect(() => () => {
    if (speechAudioUrl) URL.revokeObjectURL(speechAudioUrl);
  }, [speechAudioUrl]);

  useEffect(() => () => {
    window.clearTimeout(timer.current);
    window.clearInterval(recordingTickRef.current);
    window.clearTimeout(recordingLimitRef.current);
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function chooseExpense(nextId: DemoExpense["id"]) {
    window.clearTimeout(timer.current);
    setCustomMode(false);
    setActiveId(nextId);
    setStage("idle");
    setSpoken(false);
    setError("");
  }

  async function startCustomRecording() {
    setCustomMode(true);
    setCustomError("");
    setCustomTranscript("");
    setCustomAudio(null);
    setCustomSeconds(0);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setCustomError("This browser cannot record audio. Try a recent version of Chrome or Edge.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const supportedTypes = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm"];
      const mimeType = supportedTypes.find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setCustomError("The browser could not record audio. Please try again.");
        setCustomRecording(false);
        stream.getTracks().forEach((track) => track.stop());
      };
      recorder.onstop = () => {
        window.clearInterval(recordingTickRef.current);
        window.clearTimeout(recordingLimitRef.current);
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setCustomRecording(false);
        if (!blob.size) {
          setCustomError("No audio was captured. Please record again.");
          return;
        }
        setCustomAudio(blob);
      };
      recorderRef.current = recorder;
      recorder.start(250);
      setCustomRecording(true);
      recordingTickRef.current = window.setInterval(
        () => setCustomSeconds((seconds) => seconds + 1),
        1000,
      );
      recordingLimitRef.current = window.setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 60_000);
    } catch {
      setCustomError("Microphone access was not granted. Allow microphone access and try again.");
    }
  }

  function stopCustomRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function transcribeCustomAudio() {
    if (!customAudio) return;
    setCustomError("");
    setCustomTranscript("");
    setCustomTranscribing(true);
    const mimeType = customAudio.type.split(";", 1)[0] || "audio/webm";
    try {
      const response = await fetch(
        `/api/demo/transcribe-audio?mime_type=${encodeURIComponent(mimeType)}`,
        {
          method: "POST",
          headers: { "Content-Type": mimeType },
          body: customAudio,
        },
      );
      const result = await response.json() as {
        detail?: string;
        transcript?: string;
        model?: string;
      };
      if (!response.ok) {
        throw new Error(result.detail || `Transcription failed (${response.status})`);
      }
      if (!result.transcript) {
        throw new Error("The transcription service returned no text.");
      }
      setCustomTranscript(result.transcript);
    } catch (transcriptionError) {
      setCustomError(
        transcriptionError instanceof Error
          ? transcriptionError.message
          : "Could not reach the local transcription service. Make sure the backend is running.",
      );
    } finally {
      setCustomTranscribing(false);
    }
  }

  function formatRecordingTime(seconds: number) {
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function removeProcessedExpense(id: string) {
    setProcessedExpenses((current) => current.filter((item) => item.id !== id));
  }

  function clearProcessedHistory() {
    if (!window.confirm("Clear all locally saved voice-note expenses?")) return;
    setProcessedExpenses([]);
    setHistoryError("");
  }

  async function copyAgentResponse() {
    try {
      await navigator.clipboard.writeText(agentResponseParagraph);
      setAgentCopyState("Copied");
    } catch {
      setAgentCopyState("Copy failed — select the paragraph to copy it.");
    }
    window.setTimeout(() => setAgentCopyState(""), 2500);
  }

  async function copyListeningLink() {
    const listeningUrl = new URL("/listen.html", window.location.origin);
    listeningUrl.searchParams.set("text", spokenResponseText);
    try {
      await navigator.clipboard.writeText(listeningUrl.toString());
      setListenLinkState("Link copied");
    } catch {
      setListenLinkState("Copy failed");
    }
    window.setTimeout(() => setListenLinkState(""), 2500);
  }

  async function generateSpokenResponse() {
    setSpeechGenerating(true);
    setSpeechError("");
    setSpeechAudioUrl("");
    try {
      const response = await fetch("/api/demo/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: spokenResponseText }),
      });
      if (!response.ok) {
        let detail = `Speech generation failed (${response.status})`;
        try {
          const errorBody = await response.json() as { detail?: string };
          if (errorBody.detail) detail = errorBody.detail;
        } catch {
          // Keep the HTTP status as the actionable error when no JSON detail exists.
        }
        throw new Error(detail);
      }
      const audio = await response.blob();
      if (!audio.size) throw new Error("The speech model returned an empty audio file.");
      setSpeechAudioUrl(URL.createObjectURL(audio));
    } catch (error) {
      setSpeechError(error instanceof Error
        ? error.message
        : "Could not reach local speech generation. Make sure the Finvait backend is running.");
    } finally {
      setSpeechGenerating(false);
    }
  }

  function processVoiceNote() {
    window.clearTimeout(timer.current);
    setError("");
    setSpoken(false);
    setStage("processing");
    setProcessingLabel("Loading demo transcript");
    timer.current = window.setTimeout(() => {
      setProcessingLabel("Preparing sample transaction");
      timer.current = window.setTimeout(() => {
        setProcessingLabel("Checking sample payment alert");
        timer.current = window.setTimeout(() => {
          setStage(expense.id === "breakfast" ? "duplicate" : "extracted");
        }, 750);
      }, 800);
    }, 800);
  }

  function speakDuplicateQuestion() {
    if (!("speechSynthesis" in window)) {
      setError("This browser does not support spoken audio. Please use Chrome or Edge.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(duplicateQuestion);
    utterance.lang = "hi-IN";
    utterance.rate = 0.88;
    utterance.onend = () => setSpoken(true);
    utterance.onerror = () => setError("Could not play speech. Check that your device audio is enabled.");
    window.speechSynthesis.speak(utterance);
    setSpoken(true);
  }

  function resolveDuplicate(isSamePayment: boolean) {
    window.speechSynthesis.cancel();
    setSpoken(false);
    setStage(isSamePayment ? "resolved" : "separate");
  }

  const extracted = {
    amount: expense.amount,
    currency: "INR",
    category: expense.category,
    merchant: expense.merchant,
    payment_method: expense.paymentMethod,
    description: expense.transcript,
    source: "voice_note_demo",
    confidence: 0.96,
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Finvait home">
          <span className="brand-symbol">f</span>
          <span>finvait</span>
        </a>
        <div className="topbar-note"><span className="online-dot" /> VOICE FINANCE DEMO</div>
      </header>

      <section className="hero">
        <div className="eyebrow"><span className="eyebrow-line" /> MONEY, IN YOUR WORDS</div>
        <h1>Your voice.<br /><span>Your money, in focus.</span></h1>
        <p>Share a voice note. Finvait helps organize an expense and spot a possible double payment.</p>
      </section>

      <div className="demo-disclosure"><span>DEMO MODE</span> Sample results are preset · custom recordings are transcribed locally with Whisper</div>

      <section className="demo-layout">
        <aside className="notes-column">
          <div className="section-heading">
            <div><div className="eyebrow">YOUR VOICE NOTES</div><h2>Choose a recording</h2></div>
            <span className="soft-count">02</span>
          </div>
          <div className="note-list">
            {demoExpenses.map((item) => (
              <VoiceNoteCard
                key={item.id}
                expense={item}
                active={!customMode && activeId === item.id}
                stage={!customMode && activeId === item.id ? stage : "idle"}
                recording={recordings[item.id] ?? null}
                onSelect={() => chooseExpense(item.id)}
                onFile={(file) => setRecordings((current) => ({ ...current, [item.id]: file }))}
              />
            ))}
          </div>
          <p className="voice-help">Sample-note transcripts and transaction results are preset. Record a custom note to run real local speech recognition.</p>
          <button
            className={`record-custom-button ${customRecording ? "is-recording" : ""}`}
            onClick={customRecording ? stopCustomRecording : startCustomRecording}
            disabled={customTranscribing}
          >
            <span className="record-custom-icon">{customRecording ? "■" : "●"}</span>
            {customRecording ? "Stop recording" : "Record a custom voice"}
            {!customRecording && <span className="record-custom-arrow">→</span>}
          </button>
        </aside>

        <section className="workspace" aria-live="polite">
          <div className="workspace-head">
            <div><div className="eyebrow">{customMode ? "CUSTOM VOICE" : "PROCESSING WORKSPACE"}</div><h2>{customMode ? "Your recording" : stage === "duplicate" ? "One detail to confirm" : stage === "resolved" ? "Duplicate risk cleared" : stage === "separate" ? "Both expenses kept" : "Expense assistant"}</h2></div>
            <span className={`simulation-pill ${stage === "processing" || customRecording || customTranscribing ? "pill-running" : ""}`}>
              <i /> {customMode ? customRecording ? "RECORDING" : customTranscribing ? "LOCAL WHISPER" : "CUSTOM AUDIO" : stage === "processing" ? "PROCESSING" : "SIMULATED"}
            </span>
          </div>

          {customMode ? (
            <div className="custom-voice-view">
              {customRecording ? (
                <>
                  <div className="recording-indicator"><span /><span /><span /><span /><span /></div>
                  <h3>Recording your voice</h3>
                  <p className="recording-time">{formatRecordingTime(customSeconds)} <span>· 60 sec max</span></p>
                  <button className="primary-button stop-recording-button" onClick={stopCustomRecording}>Stop recording <span>■</span></button>
                </>
              ) : customTranscribing ? (
                <>
                  <div className="processing-orb"><div className="orb-core">f</div><span /><span /><span /></div>
                  <h3>Transcribing on this computer</h3>
                  <p className="custom-description">faster-whisper · local model · no API key</p>
                  <p className="custom-description">The first run downloads the model and may take a few minutes.</p>
                </>
              ) : customTranscript ? (
                <>
                  <div className="custom-result-icon">✓</div>
                  <div className="custom-transcript-card">
                    <div className="json-heading"><span>LOCALLY TRANSCRIBED</span><span>FASTER-WHISPER</span></div>
                    <p>{customTranscript}</p>
                  </div>
                  <p className="custom-description">Transcript created locally from your recording. Transaction details are not added to the spending history.</p>
                  <button className="text-button custom-again" onClick={startCustomRecording}>Record another voice note <span>↻</span></button>
                </>
              ) : customAudio ? (
                <>
                  <div className="sound-orb"><span>⌁</span></div>
                  <h3>Voice note ready</h3>
                  <p className="custom-description">Listen to your recording, then transcribe it using the local Whisper model.</p>
                  {customAudioUrl && <audio className="custom-audio-player" controls src={customAudioUrl}>Your browser cannot play this recording.</audio>}
                  <button className="primary-button" onClick={transcribeCustomAudio} disabled={customTranscribing}>Transcribe with local Whisper <span>→</span></button>
                </>
              ) : (
                <>
                  <div className="sound-orb"><span>⌁</span></div>
                  <h3>Record a custom voice note</h3>
                  <p className="custom-description">Use the button on the left to start recording. Your audio is sent only to the local backend for transcription.</p>
                  <button className="primary-button" onClick={startCustomRecording}>Start recording <span>●</span></button>
                </>
              )}
              {customError && <div className="inline-error" role="alert">{customError}</div>}
            </div>
          ) : (
          <>
          {stage === "idle" && (
            <div className="empty-workspace">
              <div className="sound-orb"><span>⌁</span></div>
              <h3>Ready when you are</h3>
              <p>Select a voice note, then run the demo to see how the expense is interpreted.</p>
              <button className="primary-button" onClick={processVoiceNote}>Process voice note <span>→</span></button>
            </div>
          )}

          {stage === "processing" && (
            <div className="processing-view">
              <div className="processing-orb"><div className="orb-core">f</div><span /><span /><span /></div>
              <p className="processing-title">{processingLabel}<b className="ellipsis">...</b></p>
              <p className="processing-subtitle">Scripted demo steps · audio is not transcribed</p>
              <div className="processing-steps">
                <div className="step-done"><i>✓</i> Voice note selected</div>
                <div className={processingLabel === "Loading demo transcript" ? "step-current" : "step-done"}><i>{processingLabel === "Loading demo transcript" ? "2" : "✓"}</i> Loading preset transcript</div>
                <div className={processingLabel === "Checking sample payment alert" ? "step-current" : ""}><i>3</i> Checking sample payment alert</div>
              </div>
            </div>
          )}

          {(stage === "extracted" || stage === "duplicate" || stage === "resolved" || stage === "separate") && (
            <div className="result-view">
              <div className="transcript-banner">
                <div className="mini-wave"><i/><i/><i/><i/><i/><i/><i/></div>
                <div><small>PRESET DEMO TRANSCRIPT</small><p>“{expense.transcript}”</p></div>
                <span className="checkmark">✓</span>
              </div>

              <div className="json-heading"><span>PRESET DEMO TRANSACTION</span><span>JSON</span></div>
              <pre className="json-card">{JSON.stringify(extracted, null, 2)}</pre>

              {stage === "duplicate" && (
                <div className="match-alert">
                  <div className="alert-top"><span className="alert-icon">!</span><div><b>Possible duplicate detected</b><small>Illustrative payment alert · not a real SMS connection</small></div></div>
                  <div className="match-record"><span className="sms-icon">₹</span><div><b>Online payment · {formatRupees(100)}</b><small>Today · 10:00 AM · sample alert</small></div><span className="match-tag">POSSIBLE MATCH</span></div>
                  <div className="assistant-question">
                    <span className="assistant-avatar">f</span>
                    <p>{duplicateQuestion}</p>
                    <button className="speak-button" aria-label="Speak question aloud" title="Speak question aloud" onClick={speakDuplicateQuestion}>
                      {spoken ? "♫" : "▶"}
                    </button>
                  </div>
                  <div className="answer-actions">
                    <button className="yes-button" onClick={() => resolveDuplicate(true)}>Yes, same payment <span>✓</span></button>
                    <button className="no-button" onClick={() => resolveDuplicate(false)}>No, keep both</button>
                  </div>
                </div>
              )}

              {stage === "resolved" && (
                <div className="resolution success-resolution">
                  <span className="resolution-icon">✓</span>
                  <div><b>Double-payment risk cleared</b><p>Marked as the same ₹100 online payment. It won’t be counted twice.</p></div>
                  <span className="demo-tag">SIMULATED</span>
                </div>
              )}

              {stage === "separate" && (
                <div className="resolution separate-resolution">
                  <span className="resolution-icon">↗</span>
                  <div><b>Kept as two separate expenses</b><p>Your voice-reported breakfast and the sample online alert stay separate.</p></div>
                  <span className="demo-tag">SIMULATED</span>
                </div>
              )}

              {stage === "extracted" && (
                <div className="resolution success-resolution">
                  <span className="resolution-icon">✓</span>
                  <div><b>Expense details extracted</b><p>No matching sample payment is configured for this recording.</p></div>
                  <span className="demo-tag">SIMULATED</span>
                </div>
              )}

              <button className="reset-button" onClick={processVoiceNote}>Replay processing <span>↻</span></button>
            </div>
          )}
          {error && <div className="inline-error" role="alert">{error}</div>}
          </>
          )}
        </section>
      </section>

      <section className="history-card">
        <div className="history-header">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> YOUR TRACKED ACTIVITY</div>
            <h2>Expense history &amp; comparison</h2>
            <p>Reviewed custom voice notes saved in this browser. Preset demo examples are excluded.</p>
          </div>
          <div className="history-meta">
            <span className="history-count">{processedExpenses.length} {processedExpenses.length === 1 ? "record" : "records"}</span>
          </div>
        </div>

        <div className="comparison-panel">
          <div className="sample-data-notice">
            <span>i</span>
            <p>Comparison includes fictional sample entries: {formatRupees(lastWeekSampleTotal)} last week and {formatRupees(thisWeekSampleTotal)} this week. Your classified voice-note spending last week is {formatRupees(lastWeekVoiceNotesTotal)}.</p>
          </div>
          <div className="comparison-heading">
            <div><b>Week-over-week spending</b><span>Calendar weeks · Monday to Sunday</span></div>
            <span className={`comparison-change ${comparisonDifference > 0 ? "change-up" : comparisonDifference < 0 ? "change-down" : ""}`}>
              {thisWeekTotal === 0 && lastWeekTotal === 0
                ? "No activity"
                : comparisonDifference === 0
                  ? "No change"
                  : `${comparisonDifference > 0 ? "↑" : "↓"} ${formatRupees(Math.abs(comparisonDifference))}${comparisonPercent !== null ? ` (${Math.abs(comparisonPercent)}%)` : " · new activity"}`}
            </span>
          </div>
          <div className="week-comparison">
            <div className="week-total">
              <div className="week-label"><span>This week</span><small>{formatDate(currentWeekStart)} – {formatDate(currentWeekEnd)}</small></div>
              <b>{formatRupees(thisWeekTotal)}</b>
              <span className="week-record-count">{thisWeekExpenses.length} reviewed {thisWeekExpenses.length === 1 ? "expense" : "expenses"}</span>
              <div className="comparison-bar"><i style={{ width: `${Math.max(thisWeekTotal, lastWeekTotal) ? Math.max(4, (thisWeekTotal / Math.max(thisWeekTotal, lastWeekTotal)) * 100) : 0}%` }} /></div>
            </div>
            <div className="week-total">
              <div className="week-label"><span>Last week</span><small>{formatDate(previousWeekStart)} – {formatDate(previousWeekEnd)}</small></div>
              <b>{formatRupees(lastWeekTotal)}</b>
              <span className="week-record-count">{lastWeekExpenses.length} reviewed {lastWeekExpenses.length === 1 ? "expense" : "expenses"}</span>
              <div className="comparison-bar previous-bar"><i style={{ width: `${Math.max(thisWeekTotal, lastWeekTotal) ? Math.max(4, (lastWeekTotal / Math.max(thisWeekTotal, lastWeekTotal)) * 100) : 0}%` }} /></div>
            </div>
          </div>
          {!lastWeekTotal && thisWeekTotal > 0 && (
            <p className="comparison-note">No reviewed expenses were recorded last week, so a percentage comparison is not available yet.</p>
          )}
          {lastWeekInvestments.length > 0 && (
            <p className="comparison-note">Investment outflows are kept separate from spending: {formatRupees(lastWeekInvestments.reduce((total, item) => total + item.amount, 0))} in gold last week.</p>
          )}
        </div>

        {historyError && <div className="inline-error" role="alert">{historyError}</div>}
        <section className="subscription-ledger">
          <div className="ledger-header">
            <div>
              <div className="eyebrow">MESSAGE ANALYSIS</div>
              <h3>SMS ledger &amp; subscriptions</h3>
            </div>
            <span className="ledger-demo-badge">ILLUSTRATIVE SMS</span>
          </div>
          <p className="ledger-description">Example bank-alert text grouped by recurring merchant. These are demo messages, not read from a connected phone.</p>
          <div className="subscription-cards">
            {demoSubscriptions.map((subscription) => (
              <article className="subscription-card" key={subscription.merchant}>
                <div className="subscription-topline"><b>{subscription.merchant}</b><span>{subscription.cadence}</span></div>
                <div className="subscription-price"><strong>{formatRupees(subscription.latest)}</strong><span>/ month</span></div>
                <div className={`subscription-change ${subscription.change > 0 ? "subscription-increased" : "subscription-steady"}`}>
                  {subscription.change > 0
                    ? `↑ ${formatRupees(subscription.change)} (${subscription.changePercent}%) since September`
                    : "No price change across these two messages"}
                </div>
              </article>
            ))}
          </div>
          <div className="sms-ledger-list">
            {demoSmsLedger.map((entry) => (
              <article className="sms-ledger-row" key={entry.id}>
                <span className="sms-ledger-icon">SMS</span>
                <div className="sms-ledger-main">
                  <b>{entry.merchant} · {formatRupees(entry.amount)}</b>
                  <span>{new Date(`${entry.date}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} · {entry.sender} · {entry.message}</span>
                </div>
                <span className="recurring-badge">RECURRING</span>
              </article>
            ))}
          </div>
        </section>

        <section className="agent-response-card">
          <div className="agent-response-heading">
            <div><div className="eyebrow">VOICE AGENT HANDOFF</div><h3>Suggested spoken response</h3></div>
            <div className="agent-response-actions">
              <button className="copy-response-button" onClick={copyAgentResponse}>{agentCopyState || "Copy paragraph"}</button>
              <button className="copy-response-button" onClick={copyListeningLink}>{listenLinkState || "Copy audio link"}</button>
              <button className="generate-speech-button" onClick={generateSpokenResponse} disabled={speechGenerating}>
                {speechGenerating ? "Generating voice…" : speechAudioUrl ? "Regenerate voice" : "Generate speech"}
              </button>
            </div>
          </div>
          <p className="agent-response-text">{agentResponseParagraph}</p>
          {speechGenerating && <p className="speech-status">Creating audio locally with Kokoro. First use downloads the model (~110 MB).</p>}
          {speechAudioUrl && (
            <div className="generated-speech">
              <div><span>Generated voice · ready to play on this device</span><a href={speechAudioUrl} download="finvait-spoken-response.wav">Download audio</a></div>
              <audio controls preload="metadata" src={speechAudioUrl}>Your browser cannot play this generated audio.</audio>
            </div>
          )}
          {speechError && <div className="inline-error" role="alert">{speechError}</div>}
          <p className="agent-response-note">This response draft deliberately discloses illustrative entries. Configure your live agent to use verified transaction/SMS data and disclose unavailable or simulated sources.</p>
        </section>

        <div className="history-list-heading">
          <b>Activity ledger</b>
          {processedExpenses.length > 0 && <button className="clear-history-button" onClick={clearProcessedHistory}>Clear history</button>}
        </div>
        {processedExpenses.length === 0 ? (
          <div className="history-empty">
            <span className="history-empty-icon">↗</span>
            <div><b>Your processed records will appear here</b><p>Record a custom note, transcribe it, review its details, and save it to build your history and comparison.</p></div>
          </div>
        ) : (
          <div className="history-list">
            {processedExpenses.map((item) => (
              <article className="history-row" key={item.id}>
                <span className="history-row-icon">₹</span>
                <div className="history-row-main">
                  <p>{item.displayLabel ?? item.transcript}</p>
                  <span>{historyDateLabel(item)} · {item.category} · {item.paymentMethod}</span>
                  {item.matchLabel && <small>{item.matchLabel}</small>}
                </div>
                <b className="history-row-amount">{formatRupees(item.amount)}</b>
                <div className="history-row-tags">
                  {item.matchLabel && <span className="possible-match-badge">POSSIBLE MATCH</span>}
                  {item.excludeFromSpend && (item.origin === "voice_note"
                    ? <span className="investment-badge">NOT SPENDING</span>
                    : <span className="pending-review-badge">NOT COUNTED</span>)}
                </div>
                <button className="remove-history-button" aria-label={`Remove ${item.category} expense`} title="Remove from history" onClick={() => removeProcessedExpense(item.id)}>×</button>
              </article>
            ))}
          </div>
        )}
        <p className="history-privacy">History is stored in this browser’s local storage. It is not synced to an account or backend.</p>
      </section>

      <footer className="footer">
        <span><span className="brand-symbol footer-symbol">f</span> FINVAIT</span>
        <span>Sample records · Presentation simulation</span>
      </footer>
    </main>
  );
}
