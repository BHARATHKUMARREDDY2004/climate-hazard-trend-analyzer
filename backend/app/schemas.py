from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import MAX_BOX_SPAN_DEG, MIN_PERIOD_YEARS, MIN_YEAR

BASELINES = {"1961-1990": (1961, 1990), "1991-2020": (1991, 2020)}


def clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    # Labels are echoed back into the UI, CSV and PDF. Keep printable text only.
    value = "".join(ch for ch in value if ch.isprintable()).strip()
    return value[:120] or None


class _Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=200)

    _clean = field_validator("label")(clean_label)


class PointRegion(_Region):
    type: Literal["point"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class BoxRegion(_Region):
    type: Literal["bbox"]
    south: float = Field(ge=-90, le=90)
    north: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    east: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _check_box(self):
        if self.north <= self.south:
            raise ValueError("north must be greater than south")
        if self.east <= self.west:
            raise ValueError("east must be greater than west (boxes across the antimeridian are not supported)")
        if self.north - self.south > MAX_BOX_SPAN_DEG or self.east - self.west > MAX_BOX_SPAN_DEG:
            raise ValueError(f"box is too large, the limit is {MAX_BOX_SPAN_DEG:g} degrees per side")
        return self


Region = Annotated[Union[PointRegion, BoxRegion], Field(discriminator="type")]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: Region
    hazard: Literal["heatwave"] = "heatwave"
    start_year: int = Field(ge=MIN_YEAR)
    end_year: int
    percentile: float = Field(default=95, ge=80, le=99.5)
    min_duration: int = Field(default=3, ge=2, le=10)
    threshold_method: Literal["fixed", "seasonal"] = "fixed"
    baseline: Literal["period", "1961-1990", "1991-2020"] = "period"

    @model_validator(mode="after")
    def _check_years(self):
        if self.end_year > date.today().year:
            raise ValueError("end_year cannot be in the future")
        if self.end_year - self.start_year + 1 < MIN_PERIOD_YEARS:
            raise ValueError(f"the time range must cover at least {MIN_PERIOD_YEARS} years")
        return self

    def baseline_years(self) -> tuple[int, int]:
        return BASELINES.get(self.baseline, (self.start_year, self.end_year))
