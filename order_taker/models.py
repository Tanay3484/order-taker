"""Data shapes for orders. The JSON schema from these models is sent to the
local model so its output is constrained to exactly this structure."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    name: str = Field(description="Item as the business would write it, e.g. 'chocolate cake'")
    quantity: float = Field(description="How many / how much. Use 1 if not stated.")
    unit: str = Field(default="", description="kg, pcs, box, plate... empty if none")


class Order(BaseModel):
    customer: str = Field(description="Customer name or the sender's name")
    phone: str = Field(default="", description="Phone number if mentioned")
    items: list[OrderItem]
    delivery_date: str = Field(default="", description="Delivery day as the customer wrote it, e.g. 'Sunday', 'kal', '5th Oct'")
    delivery_time: str = Field(default="", description="Time or slot if mentioned")
    address: str = Field(default="", description="Delivery address, empty for pickup / not given")
    notes: str = Field(default="", description="Special requests: eggless, less sugar, message on cake...")


class OrderBatch(BaseModel):
    orders: list[Order]


# ---- multi-agent intake (003) ----

SortKind = Literal["new_order", "change", "cancel", "question", "chit_chat"]


class SortResult(BaseModel):
    kind: SortKind
    reason: str = Field(default="", description="At most 12 words")


class DraftAction(BaseModel):
    action: Literal["new", "update", "cancel"]
    target_order_id: int | None = Field(default=None, description="ID of the existing open order for update/cancel")
    order: Order | None = Field(default=None, description="Full new details for new/update; null for cancel")


class ExtractResult(BaseModel):
    kind: SortKind = Field(description="What these messages are mostly about")
    actions: list[DraftAction]
