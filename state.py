"""Validate expense input before writing it to MongoDB."""
from datetime import date as CalendarDate
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field


class ExpenseInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    item_name: str = Field(min_length=1, max_length=150)
    date: CalendarDate
    category: str = Field(min_length=1, max_length=80)
    comments: str = ""
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)


FilterAmount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]


class ExpenseFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_name: list[str] = Field(default_factory=list, max_length=100)
    date: list[CalendarDate] = Field(default_factory=list, max_length=100)
    category: list[str] = Field(default_factory=list, max_length=100)
    comments: list[str] = Field(default_factory=list, max_length=100)
    amount: list[FilterAmount] = Field(default_factory=list, max_length=100)
