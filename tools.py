"""Core expense persistence logic."""
from datetime import datetime, timezone
from bson.decimal128 import Decimal128
from state import ExpenseFilters, ExpenseInput


def list_expenses(collection, limit: int = 50, offset: int = 0,
                  year: int | None = None, month: int | None = None,
                  column_filters: ExpenseFilters | None = None) -> dict:
    query = {}
    if month is not None and year is None:
        raise ValueError("Select a year with the month.")
    if year is not None:
        if not 1 <= year <= 9998 or (month is not None and not 1 <= month <= 12):
            raise ValueError("Invalid year or month.")
        start = f"{year:04d}-{month or 1:02d}-01"
        end_year = year + (month is None or month == 12)
        end_month = 1 if month is None or month == 12 else month + 1
        query = {"date": {"$gte": start, "$lt": f"{end_year:04d}-{end_month:02d}-01"}}

    period_query = {key: dict(value) for key, value in query.items()}
    filters = column_filters or ExpenseFilters()
    for field in ("item_name", "category", "comments"):
        values = getattr(filters, field)
        if values:
            query[field] = {"$in": values + ([None] if field == "comments" and "" in values else [])}
    if filters.date:
        query.setdefault("date", {})["$in"] = [value.isoformat() for value in filters.date]
    if filters.amount:
        query["amount"] = {"$in": [Decimal128(value) for value in filters.amount]}

    # One query returns a page and a total over ALL matching records.
    result = next(iter(collection.aggregate([{"$facet": {
        "items": [
            {"$match": query},
            {"$sort": {"date": -1, "created_at": -1, "_id": -1}},
            {"$skip": offset}, {"$limit": limit + 1},
            {"$project": {"item_name": 1, "date": 1, "category": 1, "comments": 1, "amount": 1}},
        ],
        "summary": [
            {"$match": query},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ],
        "options": [
            {"$match": period_query},
            {"$group": {
                "_id": None,
                "item_name": {"$addToSet": "$item_name"},
                "date": {"$addToSet": "$date"},
                "category": {"$addToSet": "$category"},
                "comments": {"$addToSet": {"$ifNull": ["$comments", ""]}},
                "amount": {"$addToSet": "$amount"},
            }},
        ],
        "years": [
            {"$match": {"date": {"$regex": r"^\d{4}-\d{2}-\d{2}$"}}},
            {"$group": {"_id": {"$substrBytes": ["$date", 0, 4]}}},
            {"$sort": {"_id": -1}},
        ],
    }}])), {"items": [], "summary": [], "years": []})
    documents = result["items"]
    items = []
    for document in documents[:limit]:
        amount = document["amount"]
        if isinstance(amount, Decimal128):
            amount = amount.to_decimal()
        items.append({
            "id": str(document["_id"]),
            "item_name": document["item_name"],
            "date": document["date"],
            "category": document["category"],
            "comments": document.get("comments", ""),
            "amount": format(amount, ".2f"),
        })
    summary = result["summary"][0] if result["summary"] else {"total": 0, "count": 0}
    total = summary["total"]
    if isinstance(total, Decimal128):
        total = total.to_decimal()
    options = result.get("options", [])
    raw_options = options[0] if options else {}
    filter_options = {
        field: sorted(raw_options.get(field, []), key=str.casefold)
        for field in ("item_name", "date", "category", "comments")
    }
    amounts = [value.to_decimal() if isinstance(value, Decimal128) else value for value in raw_options.get("amount", [])]
    filter_options["amount"] = [format(value, ".2f") for value in sorted(set(amounts))]
    return {
        "items": items, "has_more": len(documents) > limit,
        "total_amount": format(total, ".2f"), "total_count": summary["count"],
        "available_years": [int(entry["_id"]) for entry in result["years"]],
        "filter_options": filter_options,
    }


def save_expense(collection, expense: ExpenseInput) -> dict:
    document = {
        "item_name": expense.item_name,
        "date": expense.date.isoformat(),
        "category": expense.category,
        "comments": expense.comments,
        "amount": Decimal128(expense.amount),
        "created_at": datetime.now(timezone.utc),
    }
    result = collection.insert_one(document)
    return {"id": str(result.inserted_id), "message": "Expense saved successfully."}
