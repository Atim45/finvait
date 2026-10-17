from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .database import connect

USER_TIMEZONE = ZoneInfo("Asia/Kolkata")

def _start_of_month(day: date) -> date:
    return day.replace(day=1)


def _previous_month(day: date) -> date:
    first = _start_of_month(day)
    return first - timedelta(days=1)


def _parse_period(query: str) -> tuple[date, date, str]:
    today = datetime.now(USER_TIMEZONE).date()
    text = query.lower()
    if any(word in text for word in ("week", "hafte", "hafta", "saptah")):
        start = today - timedelta(days=today.weekday())
        return start, today + timedelta(days=1), "this week"
    if any(word in text for word in ("last month", "pichhle mahine", "pichle mahine")):
        previous = _previous_month(today)
        return _start_of_month(previous), _start_of_month(today), "last month"
    return _start_of_month(today), today + timedelta(days=1), "this month"


def _rows(start: date, end: date) -> list[dict[str, Any]]:
    start_iso = datetime.combine(start, datetime.min.time(), USER_TIMEZONE).astimezone(timezone.utc).isoformat()
    end_iso = datetime.combine(end, datetime.min.time(), USER_TIMEZONE).astimezone(timezone.utc).isoformat()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, amount_paise, category, payment_method, merchant, description,
                   source, status, occurred_at
            FROM transactions
            WHERE occurred_at >= ? AND occurred_at < ?
              AND transaction_type = 'expense'
              AND status NOT IN ('needs_confirmation', 'possible_duplicate')
            ORDER BY occurred_at
            """,
            (start_iso, end_iso),
        ).fetchall()
    return [dict(row) for row in rows]


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + row["amount_paise"]
    return {
        "total_paise": sum(row["amount_paise"] for row in rows),
        "count": len(rows),
        "by_category_paise": by_category,
    }


def get_finance_answer(query: str) -> dict[str, Any]:
    start, end, label = _parse_period(query)
    current_rows = _rows(start, end)
    current = _summarize(current_rows)
    unresolved_count = _unresolved_count(start, end)

    if label == "this week":
        duration = end - start
        previous_start = start - duration
        previous_end = start
        previous_label = "previous week"
    else:
        current_month = _start_of_month(start)
        previous_month = _previous_month(start)
        previous_start = _start_of_month(previous_month)
        # Compare matching day ranges rather than a partial month with a full one.
        days_elapsed = max(1, (end - start).days)
        previous_end = min(
            current_month,
            previous_start + timedelta(days=days_elapsed),
        )
        previous_label = "same period last month" if label == "this month" else "month before last"
    previous_rows = _rows(previous_start, previous_end)
    previous = _summarize(previous_rows)
    difference = current["total_paise"] - previous["total_paise"]
    category_deltas = {
        category: current["by_category_paise"].get(category, 0)
        - previous["by_category_paise"].get(category, 0)
        for category in set(current["by_category_paise"]) | set(previous["by_category_paise"])
    }
    increased = sorted(
        ((category, amount) for category, amount in category_deltas.items() if amount > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    decreased = sorted(
        ((category, amount) for category, amount in category_deltas.items() if amount < 0),
        key=lambda item: item[1],
    )
    subscriptions = _subscription_changes()
    emis = _category_total(current_rows, "emi")
    rupees = lambda paise: f"₹{paise / 100:,.0f}"
    direction = "zyada" if difference > 0 else "kam" if difference < 0 else "barabar"
    if not current_rows:
        answer = f"{label.title()} ke liye abhi koi expense record nahi mila."
    else:
        answer = (
            f"{label.title()} mein aapne {rupees(current['total_paise'])} kharch kiye "
            f"({current['count']} recorded transactions). {previous_label.title()} ke "
            f"{rupees(previous['total_paise'])} ke muqable {rupees(abs(difference))} {direction}."
        )
        if increased or decreased:
            reasons = []
            if increased:
                reasons.append(
                    "badha: " + ", ".join(f"{name} {rupees(value)}" for name, value in increased[:3])
                )
            if decreased:
                reasons.append(
                    "kam hua: " + ", ".join(f"{name} {rupees(abs(value))}" for name, value in decreased[:3])
                )
            answer += " Category-wise " + "; ".join(reasons) + "."
    if subscriptions:
        answer += " Subscription change: " + subscriptions[0]["text"] + "."
    if emis:
        answer += f" Is period mein recorded EMI payment {rupees(emis)} hai."
    if unresolved_count:
        answer += (
            f" {unresolved_count} transaction{'s' if unresolved_count != 1 else ''} "
            "review ke liye pending hai; unhe total mein include nahi kiya."
        )

    return {
        "answer": answer,
        "period": {"label": label, "start": start.isoformat(), "end_exclusive": end.isoformat()},
        "current": current,
        "comparison": {
            "label": previous_label,
            "total_paise": previous["total_paise"],
            "difference_paise": difference,
            "category_deltas_paise": category_deltas,
        },
        "subscription_changes": subscriptions,
        "emi_total_paise": emis,
        "unresolved_review_count": unresolved_count,
        "evidence_transaction_ids": [row["id"] for row in current_rows],
        "comparison_evidence_transaction_ids": [row["id"] for row in previous_rows],
        "demo_data_notice": "Sample records are illustrative." if any(
            row["source"] == "demo_seed" for row in current_rows
        ) else None,
    }


def _category_total(rows: list[dict[str, Any]], category: str) -> int:
    return sum(row["amount_paise"] for row in rows if row["category"] == category)


def _unresolved_count(start: date, end: date) -> int:
    start_iso = datetime.combine(start, datetime.min.time(), USER_TIMEZONE).astimezone(timezone.utc).isoformat()
    end_iso = datetime.combine(end, datetime.min.time(), USER_TIMEZONE).astimezone(timezone.utc).isoformat()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total FROM transactions
            WHERE occurred_at >= ? AND occurred_at < ?
              AND status IN ('needs_confirmation', 'possible_duplicate')
            """,
            (start_iso, end_iso),
        ).fetchone()
    return int(row["total"])


def _subscription_changes() -> list[dict[str, Any]]:
    today = datetime.now(USER_TIMEZONE).date()
    current_month = _start_of_month(today)
    previous_month = _previous_month(today)
    current = _rows(_start_of_month(current_month), today + timedelta(days=1))
    previous = _rows(_start_of_month(previous_month), current_month)
    current_by_merchant = {
        row["merchant"]: row["amount_paise"]
        for row in current
        if row["category"] == "subscriptions" and row["merchant"]
    }
    previous_by_merchant = {
        row["merchant"]: row["amount_paise"]
        for row in previous
        if row["category"] == "subscriptions" and row["merchant"]
    }
    changes = []
    for merchant in current_by_merchant.keys() & previous_by_merchant.keys():
        old, new = previous_by_merchant[merchant], current_by_merchant[merchant]
        if old != new:
            changes.append(
                {
                    "merchant": merchant,
                    "previous_amount_paise": old,
                    "current_amount_paise": new,
                    "difference_paise": new - old,
                    "text": f"{merchant} ka charge ₹{old / 100:.0f} se ₹{new / 100:.0f} hua",
                }
            )
    return changes
