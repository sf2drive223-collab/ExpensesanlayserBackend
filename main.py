"""Expense API. Run on port 8001 alongside the trading backend."""
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Annotated
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pydantic import ValidationError
from state import ExpenseFilters, ExpenseInput
from tools import list_expenses, save_expense

# Keep the single .env in the frontend folder, as requested. Only Python
# reads its MongoDB credentials; the app calls this API.
ENV_PATH = Path(__file__).resolve().parent.parent / "Expensesanlayser" / ".env"
load_dotenv(ENV_PATH)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    names = ("MONGODB_URI", "DATABASE_NAME", "EXPENSES_COLLECTION")
    settings = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(
            f"Set {', '.join(missing)} in the hosting environment "
            f"or, for local development, in {ENV_PATH}"
        )
    client = MongoClient(settings["MONGODB_URI"], serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=10000)
    try:
        client.admin.command("ping")
        app.state.expenses = client[settings["DATABASE_NAME"]][settings["EXPENSES_COLLECTION"]]
        yield
    finally:
        client.close()


app = FastAPI(title="Expense Analyser API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:8081,http://localhost:8082").split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/expenses", status_code=status.HTTP_201_CREATED)
def add_expense(expense: ExpenseInput, request: Request):
    try:
        return save_expense(request.app.state.expenses, expense)
    except PyMongoError:
        logger.error("MongoDB expense write failed.")
        raise HTTPException(status_code=503, detail="Could not confirm the expense was saved. Check the database before trying again.") from None


@app.get("/expenses")
def get_expenses(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    year: Annotated[int | None, Query(ge=1, le=9998)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    filters: Annotated[str | None, Query(max_length=100000)] = None,
):
    if month is not None and year is None:
        raise HTTPException(status_code=422, detail="Select a year with the month.")
    try:
        column_filters = ExpenseFilters.model_validate_json(filters) if filters else ExpenseFilters()
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid column filters.") from None
    try:
        return list_expenses(request.app.state.expenses, limit=limit, offset=offset, year=year, month=month, column_filters=column_filters)
    except PyMongoError:
        logger.error("MongoDB expense read failed.")
        raise HTTPException(status_code=503, detail="Could not load expenses. Please try again.") from None
