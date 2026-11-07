"""Core expense persistence logic."""
from datetime import datetime, timezone
from bson.decimal128 import Decimal128
from state import ExpenseInput


def save_expense(collection, expense: ExpenseInput) -> dict:
    document = {
        "item_name": expense.item_name,
        "date": expense.date.isoformat(),
        "category": expense.category,
        "amount": Decimal128(expense.amount),
        "created_at": datetime.now(timezone.utc),
    }
    result = collection.insert_one(document)
    return {"id": str(result.inserted_id), "message": "Expense saved successfully."}
