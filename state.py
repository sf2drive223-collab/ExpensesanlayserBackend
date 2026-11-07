"""Validate expense input before writing it to MongoDB."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ExpenseInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    item_name: str = Field(min_length=1, max_length=150)
    date: date
    category: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
