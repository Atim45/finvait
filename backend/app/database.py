import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from .config import DATABASE_PATH, DEMO_MODE


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
                currency TEXT NOT NULL DEFAULT 'INR',
                category TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                merchant TEXT,
                description TEXT NOT NULL,
                transaction_type TEXT NOT NULL DEFAULT 'expense',
                source TEXT NOT NULL,
                source_ref TEXT UNIQUE,
                transcript TEXT,
                confidence REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'recorded',
                possible_duplicate_of INTEGER REFERENCES transactions(id),
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inbound_messages (
                message_id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                received_at TEXT NOT NULL,
                processed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS phone_calls (
                call_id TEXT PRIMARY KEY,
                caller_number TEXT NOT NULL,
                direction TEXT NOT NULL,
                call_status TEXT NOT NULL,
                recording_url TEXT,
                transcript TEXT,
                disconnection_reason TEXT,
                duration_ms INTEGER,
                started_at TEXT,
                ended_at TEXT,
                processing_status TEXT NOT NULL DEFAULT 'call_started',
                last_event TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_transactions_occurred_at
                ON transactions(occurred_at);
            CREATE INDEX IF NOT EXISTS idx_transactions_category
                ON transactions(category);
            """
        )
    if DEMO_MODE:
        seed_demo_transactions()


def seed_demo_transactions() -> None:
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    current_month = today.replace(day=1)
    previous_month = current_month - timedelta(days=1)
    current_day = min(today.day, 15)
    previous_day = min(current_day, previous_month.day)

    samples = [
        (current_month.replace(day=min(2, current_day)), 65000, "groceries", "upi", "BigBasket", "Groceries"),
        (current_month.replace(day=min(4, current_day)), 125000, "dining", "card", "Cafe Delhi", "Dinner"),
        (current_month.replace(day=min(6, current_day)), 79900, "subscriptions", "card", "StreamPlus", "Monthly plan"),
        (current_month.replace(day=min(8, current_day)), 180000, "transport", "upi", "Metro", "Commute"),
        (previous_month.replace(day=min(2, previous_day)), 80000, "groceries", "upi", "BigBasket", "Groceries"),
        (previous_month.replace(day=min(4, previous_day)), 70000, "dining", "card", "Cafe Delhi", "Dinner"),
        (previous_month.replace(day=min(6, previous_day)), 49900, "subscriptions", "card", "StreamPlus", "Monthly plan"),
        (previous_month.replace(day=min(8, previous_day)), 100000, "transport", "upi", "Metro", "Commute"),
        (previous_month.replace(day=min(9, previous_day)), 250000, "emi", "upi", "Vehicle loan", "Confirmed EMI"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        for when, amount, category, method, merchant, description in samples:
            connection.execute(
                """
                INSERT OR IGNORE INTO transactions
                    (amount_paise, currency, category, payment_method, merchant,
                     description, source, source_ref, occurred_at, created_at)
                VALUES (?, 'INR', ?, ?, ?, ?, 'demo_seed', ?, ?, ?)
                """,
                (
                    amount,
                    category,
                    method,
                    merchant,
                    description,
                    f"demo:{when.isoformat()}:{merchant}",
                    datetime.combine(when, datetime.min.time(), timezone.utc).isoformat(),
                    now,
                ),
            )


def insert_transaction(transaction: dict[str, Any]) -> tuple[int, bool]:
    now = datetime.now(timezone.utc).isoformat()
    source_ref = transaction.get("source_ref")
    with connect() as connection:
        existing = None
        if source_ref:
            existing = connection.execute(
                "SELECT id FROM transactions WHERE source_ref = ?", (source_ref,)
            ).fetchone()
        if existing:
            return int(existing["id"]), False

        duplicate = find_possible_duplicate(connection, transaction)
        cursor = connection.execute(
            """
            INSERT INTO transactions
                (amount_paise, currency, category, payment_method, merchant,
                 description, transaction_type, source, source_ref, transcript,
                 confidence, status, possible_duplicate_of, occurred_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction["amount_paise"],
                transaction.get("currency", "INR"),
                transaction.get("category", "uncategorized"),
                transaction.get("payment_method", "unknown"),
                transaction.get("merchant"),
                transaction.get("description", "Voice-reported expense"),
                transaction.get("transaction_type", "expense"),
                transaction.get("source", "whatsapp_voice"),
                source_ref,
                transaction.get("transcript"),
                transaction.get("confidence", 0.5),
                "possible_duplicate" if duplicate else transaction.get("status", "recorded"),
                duplicate,
                transaction.get("occurred_at", now),
                now,
            ),
        )
        return int(cursor.lastrowid), True


def find_possible_duplicate(
    connection: sqlite3.Connection, transaction: dict[str, Any]
) -> int | None:
    if transaction.get("payment_method") == "cash":
        return None
    occurred = datetime.fromisoformat(
        transaction.get("occurred_at", datetime.now(timezone.utc).isoformat())
    )
    start = (occurred - timedelta(days=1)).isoformat()
    end = (occurred + timedelta(days=1)).isoformat()
    rows = connection.execute(
        """
        SELECT id, amount_paise, payment_method, merchant, occurred_at FROM transactions
        WHERE occurred_at BETWEEN ? AND ?
          AND source != 'whatsapp_voice'
          AND status != 'possible_duplicate'
        ORDER BY ABS(amount_paise - ?) ASC
        LIMIT 20
        """,
        (start, end, transaction["amount_paise"]),
    ).fetchall()
    for row in rows:
        difference = abs(row["amount_paise"] - transaction["amount_paise"])
        merchant = (transaction.get("merchant") or "").strip().casefold()
        prior_merchant = (row["merchant"] or "").strip().casefold()
        same_merchant = bool(merchant and prior_merchant and merchant == prior_merchant)
        same_method = row["payment_method"] == transaction.get("payment_method")
        close_in_time = abs(
            (datetime.fromisoformat(row["occurred_at"]) - occurred).total_seconds()
        ) <= 3600
        similar_amount = difference <= max(100, transaction["amount_paise"] // 100)
        if (
            row["payment_method"] != "cash"
            and transaction.get("payment_method") != "cash"
            and similar_amount
            and (same_merchant or (same_method and close_in_time))
        ):
            return int(row["id"])
    return None


def list_transactions(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM transactions ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_transaction(transaction_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
    return dict(row) if row else None


def record_inbound_message(message_id: str, sender: str) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO inbound_messages
                (message_id, sender, status, received_at)
            VALUES (?, ?, 'received', ?)
            """,
            (message_id, sender, datetime.now(timezone.utc).isoformat()),
        )
        return cursor.rowcount == 1


def update_inbound_message(
    message_id: str, status: str, error_code: str | None = None
) -> None:
    with connect() as connection:
        connection.execute(
            """
            UPDATE inbound_messages
            SET status = ?, error_code = ?, processed_at = ?
            WHERE message_id = ?
            """,
            (status, error_code, datetime.now(timezone.utc).isoformat(), message_id),
        )


def save_retell_call(call: dict[str, Any], event: str) -> None:
    call_id = call.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("Retell call event is missing call_id")
    call_type = call.get("call_type")
    if call_type not in {"phone_call", "web_call"}:
        raise ValueError("Unsupported Retell call type")
    caller_number = call.get("from_number") or (
        "Browser caller" if call_type == "web_call" else None
    )
    if not isinstance(caller_number, str) or not caller_number:
        raise ValueError("Retell phone call event is missing caller number")

    def timestamp(value: Any) -> str | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()

    transcript = call.get("transcript")
    if not isinstance(transcript, str):
        transcript = None
    recording_url = call.get("recording_url")
    if not isinstance(recording_url, str):
        recording_url = None
    duration_ms = call.get("duration_ms")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        duration_ms = None

    if event == "call_started":
        processing_status = "in_progress"
    elif recording_url and transcript:
        processing_status = "recording_and_transcript_ready"
    elif recording_url:
        processing_status = "recording_ready"
    elif transcript:
        processing_status = "transcript_ready"
    else:
        processing_status = "waiting_for_recording"
    now = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO phone_calls (
                call_id, caller_number, direction, call_status, recording_url,
                transcript, disconnection_reason, duration_ms, started_at, ended_at,
                processing_status, last_event, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(call_id) DO UPDATE SET
                caller_number = excluded.caller_number,
                direction = excluded.direction,
                call_status = excluded.call_status,
                recording_url = COALESCE(excluded.recording_url, phone_calls.recording_url),
                transcript = COALESCE(excluded.transcript, phone_calls.transcript),
                disconnection_reason = COALESCE(excluded.disconnection_reason, phone_calls.disconnection_reason),
                duration_ms = COALESCE(excluded.duration_ms, phone_calls.duration_ms),
                started_at = COALESCE(excluded.started_at, phone_calls.started_at),
                ended_at = COALESCE(excluded.ended_at, phone_calls.ended_at),
                processing_status = excluded.processing_status,
                last_event = excluded.last_event,
                updated_at = excluded.updated_at
            """,
            (
                call_id,
                caller_number,
                "web" if call_type == "web_call" else (
                    call.get("direction")
                    if call.get("direction") in {"inbound", "outbound"}
                    else "unknown"
                ),
                str(call.get("call_status") or "unknown")[:40],
                recording_url,
                transcript,
                str(call.get("disconnection_reason") or "")[:100] or None,
                duration_ms,
                timestamp(call.get("start_timestamp")),
                timestamp(call.get("end_timestamp")),
                processing_status,
                event,
                now,
            ),
        )


def list_phone_calls(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM phone_calls ORDER BY COALESCE(ended_at, started_at, updated_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
