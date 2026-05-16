from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "timetable.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    TIMETABLE = json.load(f)

DIRECTIONS = list(TIMETABLE["timetable"].keys())

app = FastAPI(
    title="SRT Red Line – Lak Hok Station API",
    description=(
        "Free, open timetable API for the SRT Red Line commuter rail "
        "at Lak Hok Station (RN09), Bangkok, Thailand.\n\n"
        "Data source: official station timetable poster (updated 15/08/2023)."
    ),
    version="1.0.0",
    contact={"name": "Open Data / Community", "url": "https://github.com"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _bangkok_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=7)))


def _flat_departures(schedule: list[dict]) -> list[str]:
    return sorted(
        f"{entry['hour']:02d}:{m:02d}"
        for entry in schedule
        for m in entry["minutes"]
    )


def _next_departure(schedule: list[dict], from_time: str | None = None) -> dict | None:
    if from_time:
        try:
            ref_h, ref_m = map(int, from_time.split(":"))
        except ValueError:
            raise HTTPException(status_code=400, detail="time must be HH:MM format, e.g. 08:30")
    else:
        now = _bangkok_now()
        ref_h, ref_m = now.hour, now.minute

    ref_total = ref_h * 60 + ref_m

    candidates = sorted(
        (entry["hour"] * 60 + m, entry["hour"], m)
        for entry in schedule
        for m in entry["minutes"]
    )

    for total, h, m in candidates:
        if total > ref_total:
            return {"departure": f"{h:02d}:{m:02d}", "wait_minutes": total - ref_total}

    # Wrap to next day — return first train
    if candidates:
        total, h, m = candidates[0]
        return {
            "departure": f"{h:02d}:{m:02d}",
            "wait_minutes": (24 * 60 - ref_total) + total,
            "note": "next day",
        }

    return None


def _get_schedule(direction: str) -> list[dict]:
    if direction not in TIMETABLE["timetable"]:
        raise HTTPException(
            status_code=404,
            detail=f"Direction '{direction}' not found. Valid keys: {DIRECTIONS}",
        )
    return TIMETABLE["timetable"][direction]["schedule"]


@app.get("/", tags=["Info"])
def root():
    return {
        "name": "SRT Red Line – Lak Hok Station API",
        "station": TIMETABLE["station"],
        "timetable_updated": TIMETABLE["updated"],
        "docs": "/docs",
        "endpoints": {
            "full_timetable": "GET /timetable",
            "by_direction":   "GET /timetable/{direction}",
            "next_train":     "GET /next?direction=lak_hok_to_krung_thep_aphiwat&time=08:30",
            "all_departures": "GET /departures?direction=lak_hok_to_rangsit",
            "directions":     "GET /directions",
        },
    }


@app.get("/directions", tags=["Info"])
def list_directions():
    return {
        "directions": [
            {"key": key, "label": TIMETABLE["timetable"][key]["direction"]}
            for key in DIRECTIONS
        ]
    }


@app.get("/timetable", tags=["Timetable"])
def full_timetable():
    return TIMETABLE


@app.get("/timetable/{direction}", tags=["Timetable"])
def timetable_by_direction(direction: str):
    _get_schedule(direction)  # validates direction
    return TIMETABLE["timetable"][direction]


@app.get("/departures", tags=["Timetable"])
def all_departures(
    direction: str = Query(..., description="Direction key, e.g. lak_hok_to_rangsit"),
):
    schedule = _get_schedule(direction)
    departures = _flat_departures(schedule)
    return {
        "direction": TIMETABLE["timetable"][direction]["direction"],
        "departures": departures,
        "total": len(departures),
    }


@app.get("/next", tags=["Live"])
def next_train(
    direction: str = Query(..., description="Direction key"),
    time: Optional[str] = Query(None, description="Reference time HH:MM (Bangkok). Defaults to now."),
):
    schedule = _get_schedule(direction)
    result = _next_departure(schedule, from_time=time)

    if not result:
        raise HTTPException(status_code=404, detail="No departures found.")

    now_bkk = _bangkok_now()
    return {
        "direction": TIMETABLE["timetable"][direction]["direction"],
        "queried_time": time or now_bkk.strftime("%H:%M"),
        "bangkok_now": now_bkk.strftime("%H:%M") if not time else None,
        **result,
    }
