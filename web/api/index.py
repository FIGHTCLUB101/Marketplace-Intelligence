"""GOAT Life API — FastAPI app for all Sprint 3 endpoints.

Deployed as a single Vercel Python serverless function; web/vercel.json
rewrites /api/* to this file. Run locally with:
    cd web/api && uvicorn index:app --reload
"""
import logging
from typing import Optional

import psycopg2.errors
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

import queries
from db import get_connection
from models import Annotation, AnnotationCreate, Belt, CompetitorSummaryRow, Locality, ShelfSnapshot

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
