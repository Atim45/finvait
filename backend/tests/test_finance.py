from datetime import date, datetime, timezone

from app import database
from app.finance import get_finance_answer


def test_cash_transaction_is_not_matched_as_digital_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    database.initialize_database()
    occurred = datetime.now(timezone.utc).isoformat()
    first_id, _ = database.insert_transaction(
        {
            "amount_paise": 45000,
            "category": "dining",
            "payment_method": "upi",
            "description": "Dinner",
            "source": "bank_import",
            "occurred_at": occurred,
        }
    )
    cash_id, _ = database.insert_transaction(
        {
            "amount_paise": 45000,
            "category": "dining",
            "payment_method": "cash",
            "description": "Dinner",
            "source": "whatsapp_voice",
            "occurred_at": occurred,
        }
    )
    assert first_id != cash_id
    assert database.get_transaction(cash_id)["possible_duplicate_of"] is None


def test_summary_contains_evidence_and_deterministic_total(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    database.initialize_database()
    today = date.today()
    occurred = datetime.combine(today, datetime.min.time(), timezone.utc).isoformat()
    database.insert_transaction(
        {
            "amount_paise": 12345,
            "category": "groceries",
            "payment_method": "cash",
            "description": "Market vegetables",
            "source": "whatsapp_voice",
            "occurred_at": occurred,
        }
    )
    result = get_finance_answer("Is mahine kitna kharch hua?")
    assert result["current"]["total_paise"] == 12345
    assert result["evidence_transaction_ids"]


def test_possible_digital_duplicate_is_held_out_of_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    database.initialize_database()
    occurred = datetime.now(timezone.utc).isoformat()
    database.insert_transaction(
        {
            "amount_paise": 45000,
            "category": "dining",
            "payment_method": "upi",
            "merchant": "Cafe",
            "description": "Cafe payment",
            "source": "bank_import",
            "occurred_at": occurred,
        }
    )
    duplicate_id, _ = database.insert_transaction(
        {
            "amount_paise": 45000,
            "category": "dining",
            "payment_method": "upi",
            "merchant": "Cafe",
            "description": "Reported cafe payment",
            "source": "whatsapp_voice",
            "occurred_at": occurred,
        }
    )
    duplicate = database.get_transaction(duplicate_id)
    assert duplicate["status"] == "possible_duplicate"
    assert duplicate["possible_duplicate_of"] is not None
    result = get_finance_answer("Is mahine kitna kharch hua?")
    assert result["current"]["total_paise"] == 45000
    assert result["unresolved_review_count"] == 1


def test_whatsapp_source_reference_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", str(tmp_path / "idempotent.db"))
    monkeypatch.setattr(database, "DEMO_MODE", False)
    database.initialize_database()
    payload = {
        "amount_paise": 25000,
        "category": "groceries",
        "payment_method": "cash",
        "description": "Vegetables",
        "source": "whatsapp_voice",
        "source_ref": "wamid.example",
    }
    first_id, first_created = database.insert_transaction(payload)
    replay_id, replay_created = database.insert_transaction(payload)
    assert first_id == replay_id
    assert first_created is True
    assert replay_created is False
