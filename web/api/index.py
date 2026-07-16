"""GOAT Life API — FastAPI app for all Sprint 3 endpoints.

Deployed as a single Vercel Python serverless function; web/vercel.json
rewrites /api/* to this file. Run locally with:
    cd web/api && uvicorn index:app --reload
"""
import logging
import os
import sys
from typing import Optional

import psycopg2.errors
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

# vercel dev's Python runtime imports this file by path without adding its
# own directory to sys.path, so sibling modules (queries, shelf_changes,
# db, models) 404 with ModuleNotFoundError unless we add it ourselves.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import queries
import shelf_changes
from db import get_connection
from models import (
    Annotation, AnnotationCreate, Belt, CompetitorBreadth, CompetitorSummaryRow, Freshness,
    GoatDisplaced, Locality, PriceChange, ProductEvent, RankIntrusion, RankMoved, ShelfChanges,
    ShelfSnapshot, ShelfTrends, TrendSeries,
)

logger = logging.getLogger("goatlife_api")

app = FastAPI(title="GOAT Life API")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/api/localities", response_model=list[Locality])
def get_localities():
    conn = get_connection()
    try:
        return queries.fetch_localities(conn)
    finally:
        conn.close()


@app.get("/api/belts", response_model=list[Belt])
def get_belts():
    conn = get_connection()
    try:
        rows = queries.fetch_localities(conn)
    finally:
        conn.close()
    return queries.compute_belts(rows)


@app.get("/api/competitor/history", response_model=list[ShelfSnapshot])
def get_competitor_history(
    locality_id: Optional[int] = Query(default=None),
    platform: Optional[str] = Query(default=None),
):
    conn = get_connection()
    try:
        return queries.fetch_competitor_history(conn, locality_id=locality_id, platform=platform)
    finally:
        conn.close()


@app.get("/api/competitor/summary", response_model=list[CompetitorSummaryRow])
def get_competitor_summary():
    conn = get_connection()
    try:
        return queries.fetch_competitor_summary(conn)
    finally:
        conn.close()


@app.get("/api/annotations", response_model=list[Annotation])
def get_annotations(locality_id: Optional[int] = Query(default=None)):
    conn = get_connection()
    try:
        return queries.fetch_annotations(conn, locality_id=locality_id)
    finally:
        conn.close()


@app.post("/api/annotations", response_model=Annotation, status_code=201)
def create_annotation(body: AnnotationCreate):
    conn = get_connection()
    try:
        try:
            return queries.insert_annotation(
                conn, body.locality_id, body.note, body.status, body.budget_note
            )
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise HTTPException(status_code=404, detail="locality not found")
    finally:
        conn.close()


@app.get("/api/meta/freshness", response_model=Freshness)
def get_freshness():
    conn = get_connection()
    try:
        return queries.fetch_freshness(conn)
    finally:
        conn.close()


@app.get("/api/shelf/changes", response_model=ShelfChanges)
def get_shelf_changes(platform: str = Query(default="blinkit_goatlife")):
    conn = get_connection()
    try:
        newest_id, second_id = queries.fetch_latest_two_scrape_run_ids(conn, platform)
        if second_id is None:
            return {
                "platform": platform, "status": "insufficient_history",
                "narrative": ["First week of tracking — no prior week to compare against yet."],
            }
        rows_new = queries.fetch_snapshot_rows(conn, newest_id)
        rows_old = queries.fetch_snapshot_rows(conn, second_id)
        drop_calendar = queries.fetch_drop_calendar(conn)
        brand_defence_rate = queries.fetch_brand_defence_rate(conn, newest_id)
    finally:
        conn.close()

    changes = shelf_changes.detect_changes(rows_new, rows_old, drop_calendar=drop_calendar)
    narrative = shelf_changes.generate_narrative_summary(changes)
    return {
        "platform": platform, "status": "ok",
        "new_run_id": newest_id, "old_run_id": second_id,
        "narrative": narrative,
        "brand_defence_rate": brand_defence_rate,
        "conquest_breadth": shelf_changes.conquest_breadth(changes),
        "goat_displaced": changes["goat_displaced"],
        "rank_intrusions": changes["rank_intrusions"],
        "goat_gone": shelf_changes.goat_gone_unique(changes),
        "new_products": changes["new_products"],
        "gone_products": changes["gone_products"],
        "rank_moved": changes["rank_moved"],
        "price_changes": changes["price_changes"],
    }


@app.get("/api/shelf/trends", response_model=ShelfTrends)
def get_shelf_trends(platform: str = Query(default="blinkit_goatlife")):
    conn = get_connection()
    try:
        return queries.fetch_shelf_trends(conn, platform)
    finally:
        conn.close()


@app.get("/api/shelf/snapshot", response_model=list[ShelfSnapshot])
def get_shelf_snapshot(platform: str = Query(...)):
    conn = get_connection()
    try:
        newest_id, _ = queries.fetch_latest_two_scrape_run_ids(conn, platform)
        if newest_id is None:
            return []
        return queries.fetch_current_snapshot(conn, newest_id)
    finally:
        conn.close()
