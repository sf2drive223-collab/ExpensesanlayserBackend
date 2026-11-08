import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import AutoReconnect

from main import add_expense, get_expenses
from state import ExpenseFilters, ExpenseInput
from tools import list_expenses


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

    def test_comments_are_optional_and_saved_with_multiple_lines(self):
        self.assertEqual(ExpenseInput(**self.payload()).comments, "")
        note = "Lunch with family\nPaid by card — café"
        collection = Mock()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(expenses=collection)))
        add_expense(ExpenseInput(**self.payload(comments=note)), request)
        self.assertEqual(collection.insert_one.call_args.args[0]["comments"], note)

    def test_database_failure_does_not_report_success_or_leak_details(self):
        collection = Mock()
        collection.insert_one.side_effect = AutoReconnect("private connection details")
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(expenses=collection)))
        with self.assertRaises(HTTPException) as error:
            add_expense(ExpenseInput(**self.payload()), request)
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn("private", error.exception.detail)

    def test_list_serializes_amounts_and_indicates_more_records(self):
        documents = [
            {"_id": ObjectId(), "item_name": "Lunch", "category": "Food", "date": "2026-11-08", "amount": Decimal128("0.10")},
            {"_id": ObjectId(), "item_name": "Bus", "category": "Travel", "date": "2026-11-07", "amount": Decimal128("25")},
        ]
        collection = Mock()
        collection.aggregate.return_value = [{"items": documents, "summary": [{"total": Decimal128("25.10"), "count": 2}], "years": [{"_id": "2026"}]}]
        page = list_expenses(collection, limit=1, offset=10)
        self.assertTrue(page["has_more"])
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["amount"], "0.10")
        self.assertEqual(page["items"][0]["id"], str(documents[0]["_id"]))
        self.assertEqual(page["items"][0]["date"], "2026-11-08")
        self.assertEqual(page["items"][0]["comments"], "")
        self.assertEqual(page["total_amount"], "25.10")
        self.assertEqual(page["total_count"], 2)
        self.assertEqual(page["available_years"], [2026])
        facet = collection.aggregate.call_args.args[0][0]["$facet"]
        self.assertIn({"$skip": 10}, facet["items"])
        self.assertIn({"$limit": 2}, facet["items"])
        self.assertNotIn({"$limit": 2}, facet["summary"])

    def test_list_empty_collection(self):
        collection = Mock()
        collection.aggregate.return_value = [{"items": [], "summary": [], "years": []}]
        self.assertEqual(list_expenses(collection), {"items": [], "has_more": False, "total_amount": "0.00", "total_count": 0, "available_years": [], "filter_options": {"item_name": [], "date": [], "category": [], "comments": [], "amount": []}})

    def test_list_last_page_formats_whole_amount(self):
        collection = Mock()
        documents = [
            {"_id": ObjectId(), "item_name": "Bus", "category": "Travel", "comments": "Return journey", "date": "2026-11-07", "amount": Decimal128("25")},
        ]
        collection.aggregate.return_value = [{"items": documents, "summary": [{"total": Decimal128("25"), "count": 1}], "years": [{"_id": "2026"}]}]
        page = list_expenses(collection, limit=50)
        self.assertFalse(page["has_more"])
        self.assertEqual(page["items"][0]["amount"], "25.00")
        self.assertEqual(page["items"][0]["comments"], "Return journey")

    def test_list_database_failure_does_not_leak_details(self):
        collection = Mock()
        collection.aggregate.side_effect = AutoReconnect("private connection details")
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(expenses=collection)))
        with self.assertRaises(HTTPException) as error:
            get_expenses(request, limit=50, offset=0)
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn("private", error.exception.detail)

    def test_month_filters_include_leap_day_and_handle_december(self):
        for year, month, start, end in [
            (2024, 2, "2024-02-01", "2024-03-01"),
            (2026, 12, "2026-12-01", "2027-01-01"),
            (2026, 1, "2026-01-01", "2026-02-01"),
        ]:
            with self.subTest(year=year, month=month):
                collection = Mock()
                collection.aggregate.return_value = [{"items": [], "summary": [], "years": []}]
                list_expenses(collection, year=year, month=month)
                facet = collection.aggregate.call_args.args[0][0]["$facet"]
                expected = {"$match": {"date": {"$gte": start, "$lt": end}}}
                self.assertEqual(facet["items"][0], expected)
                self.assertEqual(facet["summary"][0], expected)

    def test_month_requires_year_and_rejects_invalid_period(self):
        for year, month in [(None, 2), (2026, 0), (2026, 13), (0, 1)]:
            with self.subTest(year=year, month=month), self.assertRaises(ValueError):
                list_expenses(Mock(), year=year, month=month)
        with self.assertRaises(HTTPException) as error:
            get_expenses(SimpleNamespace(), limit=50, offset=0, year=None, month=1)
        self.assertEqual(error.exception.status_code, 422)

    def test_column_filters_combine_and_totals_use_identical_match(self):
        collection = Mock()
        collection.aggregate.return_value = [{"items": [], "summary": [], "years": []}]
        filters = ExpenseFilters(item_name=["Lunch", "Dinner"], date=["2026-11-08"], category=["Food"], comments=[""], amount=["123.45"])
        list_expenses(collection, year=2026, month=11, column_filters=filters)
        facet = collection.aggregate.call_args.args[0][0]["$facet"]
        query = facet["items"][0]["$match"]
        self.assertEqual(query["date"], {"$gte": "2026-11-01", "$lt": "2026-12-01", "$in": ["2026-11-08"]})
        self.assertEqual(query["item_name"], {"$in": ["Lunch", "Dinner"]})
        self.assertEqual(query["category"], {"$in": ["Food"]})
        self.assertEqual(query["comments"], {"$in": ["", None]})
        self.assertEqual(query["amount"]["$in"][0].to_decimal(), Decimal("123.45"))
        self.assertEqual(facet["summary"][0], facet["items"][0])
        self.assertEqual(facet["options"][0], {"$match": {"date": {"$gte": "2026-11-01", "$lt": "2026-12-01"}}})

    def test_filter_options_cover_entire_month_and_format_amounts(self):
        collection = Mock()
        collection.aggregate.return_value = [{"items": [], "summary": [], "years": [], "options": [{
            "item_name": ["snacks", "Lunch"], "date": ["2026-11-08"], "category": ["Food"], "comments": ["", "Work"], "amount": [Decimal128("100"), Decimal128("2.5")],
        }]}]
        page = list_expenses(collection, limit=1, offset=50, year=2026, month=11)
        self.assertEqual(page["filter_options"]["amount"], ["2.50", "100.00"])
        self.assertEqual(page["filter_options"]["item_name"], ["Lunch", "snacks"])
        self.assertEqual(page["filter_options"]["comments"], ["", "Work"])
        stages = collection.aggregate.call_args.args[0][0]["$facet"]["options"]
        self.assertFalse(any("$limit" in stage or "$skip" in stage for stage in stages))

    def test_invalid_filter_values_are_rejected(self):
        for payload in [{"date": ["2026-02-30"]}, {"amount": ["NaN"]}, {"amount": ["1.234"]}, {"other": ["bad"]}]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ExpenseFilters(**payload)
        with self.assertRaises(HTTPException) as error:
            get_expenses(SimpleNamespace(), limit=50, offset=0, filters='{"amount":["bad"]}')
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
