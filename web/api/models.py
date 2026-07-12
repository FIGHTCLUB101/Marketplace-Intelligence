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
