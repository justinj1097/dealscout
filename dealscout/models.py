"""Data shapes passed between the agents. Every agent must answer in one of these shapes (structured
outputs), so the app can check the answer with code before anyone sees it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- what the user asks for
class Criteria(BaseModel):
    industry: str = Field(description="Industry, e.g. 'Aerospace & Defense'")
    focus: str = Field("", description="Optional sub-sector or theme, e.g. 'space', 'defense electronics'")
    min_value_usd_m: float = Field(500, description="Smallest deal size in $ millions")
    months_back: int = Field(12, description="Only deals announced in the last N months")
    region: str = Field("Global")
    deal_types: list[str] = Field(default_factory=lambda: ["M&A"])
    priority: Literal["Biggest deals", "Most talked-about", "Best for interviews", "Most recent"] = "Best for interviews"
    num_deals: int = Field(5, ge=1, le=8)
    note: str = Field("", description="Anything else the user typed (untrusted user text)")


# ---------------------------------------------------------------- Scout agent output
class Deal(BaseModel):
    acquirer: str
    target: str
    deal_type: str = Field(description="e.g. Acquisition, Merger, LBO / take-private, Carve-out, Minority stake")
    announced_date: str = Field(description="YYYY-MM-DD if known, else YYYY-MM")
    status: str = Field(description="Announced, Pending, Closed, or Terminated")
    value_usd_m: float | None = Field(description="Headline deal / enterprise value in $ millions; null if not disclosed")
    value_quote: str = Field(description="Exact sentence from the source that states the value; empty if undisclosed")
    ev_ebitda: float | None = Field(description="EV/EBITDA multiple if a source states it, else null")
    ev_revenue: float | None = Field(description="EV/Revenue multiple if a source states it, else null")
    multiple_quote: str = Field(description="Exact text stating the multiple, or the revenue/EBITDA figure used; empty if none")
    buyer_advisors: list[str] = Field(description="Banks advising the buyer, as named in a source")
    seller_advisors: list[str] = Field(description="Banks advising the seller/target, as named in a source")
    strategic_rationale: str = Field(description="One or two sentences: why the buyer did this deal")
    source_url: str = Field(description="URL of the best source (press release or filing preferred)")
    source_title: str


class ScoutReport(BaseModel):
    deals: list[Deal]
    search_notes: str = Field(description="One sentence on how the search went (e.g. few deals in window)")


# ---------------------------------------------------------------- Fact-Checker agent output
class Check(BaseModel):
    deal_index: int
    verdict: Literal["confirmed", "partly confirmed", "conflict", "could not confirm"]
    confirmed_value_usd_m: float | None
    advisors_confirmed: bool
    buyer_advisors_found: list[str] = Field(description="Banks advising the buyer, named in YOUR source; empty if none found")
    seller_advisors_found: list[str] = Field(description="Banks advising the seller/target, named in YOUR source; empty if none found")
    independent_source_url: str = Field(description="A DIFFERENT source than the Scout's, or empty")
    note: str = Field(description="One short sentence: what matched or what conflicted")


class CheckReport(BaseModel):
    checks: list[Check]


# ---------------------------------------------------------------- Analyst agent output
class DealTake(BaseModel):
    deal_index: int
    why_it_matters: str = Field(description="One sentence a banker would say about why this deal matters")
    interview_angle: str = Field(description="One sentence: how to use it in an interview")


class AnalystReport(BaseModel):
    takes: list[DealTake]
    industry_theme: str = Field(description="One sentence tying the deals together into a trend")


# ---------------------------------------------------------------- Pitch Coach agent output
class KeyNumber(BaseModel):
    label: str
    value: str


class QA(BaseModel):
    question: str
    answer: str


class Pitch(BaseModel):
    headline: str
    sixty_second_pitch: str = Field(description="About 150 words, spoken style, first person ('A deal I've been following...')")
    key_numbers: list[KeyNumber]
    why_it_makes_sense: list[str]
    risks: list[str]
    interview_questions: list[QA]
