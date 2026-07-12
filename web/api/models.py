"""Pydantic response models for the API layer. Field names are snake_case
throughout — a deliberate departure from the legacy parquet-era AREA/ADDRESS
naming, since Sprint 4's Next.js frontend is a fresh consumer of this API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Locality(BaseModel):
    locality_id: int
    loc_key: str
    area: str
    city: str
    pincode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    belt_id: Optional[str] = None
    belt_size: Optional[int] = None
    as_of: Optional[datetime] = None
    icp_score: Optional[float] = None
    icp_verdict: Optional[str] = None
    gtm_action: Optional[str] = None
    serviceability_state: Optional[str] = None
    serviceability_confidence: Optional[str] = None
    archetype_ml: Optional[str] = None
    lifecycle: Optional[str] = None
    n_brands_confirmed: Optional[int] = None
    brands_confirmed_list: Optional[str] = None
    nearest_known_darkstore_km: Optional[float] = None
    blinkit_confirmed: Optional[bool] = None
    swiggy_confirmed: Optional[bool] = None
    zepto_confirmed: Optional[bool] = None
    res_avg_buy_imputed: Optional[float] = None
    price_is_imputed: Optional[bool] = None
    employer_quality: Optional[str] = None
    primary_sector: Optional[str] = None
    is_metro_connected: Optional[bool] = None
    pareto_optimal: Optional[bool] = None
    hidden_gem_v2: Optional[bool] = None
    spillover_gem: Optional[bool] = None


class Belt(BaseModel):
    belt_id: str
    city: str
    size: int
    avg_icp: Optional[float] = None
    go_count: int
    confirmed_count: int
    members: list[str]


class ShelfSnapshot(BaseModel):
    shelf_snapshot_id: int
    platform: str
    locality_id: Optional[int] = None
    city_raw: str
    locality_raw: str
    brand_searched: Optional[str] = None
    rank: Optional[int] = None
    product_name: Optional[str] = None
    pack_size: Optional[str] = None
    selling_price: Optional[float] = None
    mrp: Optional[float] = None
    discount_pct: Optional[float] = None
    stock_left: Optional[str] = None
    rating: Optional[str] = None
    reviews: Optional[str] = None
    sponsored: Optional[bool] = None
    serviceable: Optional[str] = None
    is_goat: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CompetitorSummaryRow(BaseModel):
    locality_id: int
    platform: str
    n_competitor_brands: int
    competitor_avg_price: Optional[float] = None
    goat_present: bool


class Annotation(BaseModel):
    annotation_id: int
    locality_id: int
    note: Optional[str] = None
    status: Optional[str] = None
    budget_note: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class AnnotationCreate(BaseModel):
    locality_id: int
    note: Optional[str] = None
    status: Optional[str] = None
    budget_note: Optional[float] = None
