from datetime import date

from pydantic import BaseModel, Field


class UserPatch(BaseModel):
    fio: str | None = Field(None, min_length=1)
    phone: str | None = Field(None, min_length=1)


class Reading(BaseModel):
    user_id: int
    gauge_id: int
    tariff_id: int
    reading_date: date
    day_kw: int = Field(ge=0)
    night_kw: int = Field(ge=0)


class Gauge(BaseModel):
    gauge_id: int = Field(ge=1)
