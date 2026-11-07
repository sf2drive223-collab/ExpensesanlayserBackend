import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import AutoReconnect

from main import add_expense
from state import ExpenseInput


class ExpenseTests(unittest.TestCase):
    def payload(self, **changes):
        return {"item_name": " Lunch ", "date": "2026-11-07", "category": " Food ", "amount": "123.45", **changes}

    def test_save_preserves_exact_amount_and_local_date(self):
        collection = Mock()
        inserted_id = ObjectId()
        collection.insert_one.return_value.inserted_id = inserted_id
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(expenses=collection)))
        response = add_expense(ExpenseInput(**self.payload()), request)
        self.assertEqual(response["id"], str(inserted_id))
        document = collection.insert_one.call_args.args[0]
        self.assertEqual(document["amount"].to_decimal(), Decimal("123.45"))
        self.assertEqual(document["date"], "2026-11-07")
        self.assertEqual(document["item_name"], "Lunch")
        self.assertEqual(document["category"], "Food")
        self.assertIsNotNone(document["created_at"].tzinfo)
        collection.insert_one.assert_called_once()

    def test_invalid_expenses_are_rejected(self):
        for changes in [
            {"item_name": "  "}, {"category": "  "},
            {"amount": "0"}, {"amount": "-1"}, {"amount": "1.234"},
            {"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "not a number"},
            {"amount": "10000000000.00"}, {"date": "2026-02-30"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ExpenseInput(**self.payload(**changes))

    def test_database_failure_does_not_report_success_or_leak_details(self):
        collection = Mock()
        collection.insert_one.side_effect = AutoReconnect("private connection details")
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(expenses=collection)))
        with self.assertRaises(HTTPException) as error:
            add_expense(ExpenseInput(**self.payload()), request)
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn("private", error.exception.detail)


if __name__ == "__main__":
    unittest.main()
