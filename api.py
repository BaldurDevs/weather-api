import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel, Field

from typing import List

from starlette.middleware.cors import CORSMiddleware

import main as app
api = FastAPI(
    title="Weather City Data API",
    description="Serves weather data, a CSV export, and a humidity chart for a list of cities.",
    version="v1.0.0",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AddCitiesRequest(BaseModel):
    cities: List[str] = Field(
        ...,
        min_length=1,
        description="List of city names to add to the app.",
        examples=[["Madrid", "Rome", "Cairo"]],
    )


@api.get("/")
def root():     # Basic health check / index.
    return {
        "status": "ok",
        "endpoints": ["/refresh", "/csv", "/chart", "/cities"],
    }

@api.post("/refresh")
def refresh_data():
    app.fetch_cities_data(app.INPUT_CITIES, app.DEFAULT_TIMEOUT)
    cities_data = app.process_cities_data(app.INPUT_CITIES)
    app.persist_cities_data(cities_data)
    app.generate_cities_humidity_chart(cities_data)

    return {"status": "ok", "cities_processed": len(app.INPUT_CITIES)}


@api.get("/cities")
def list_cities():
    return app.INPUT_CITIES


@api.post("/cities")
def add_cities(request: AddCitiesRequest):
    """
    Add one or more cities to the app's city list.
    Body: {"cities": ["Madrid", "Rome", "Cairo"]}

    - Skips blank names.
    - Skips names already present (case-insensitive), so calling this
      repeatedly with the same city doesn't create duplicates.
    - New cities have no weather data yet - call POST /refresh afterwards
      to fetch it for the whole list, including the new additions.
    """
    existing_names = {c["City"].strip().lower() for c in app.INPUT_CITIES}

    added = []
    skipped = []
    for raw_name in request.cities:
        name = raw_name.strip()
        if not name:
            continue
        if name.lower() in existing_names:
            skipped.append(name)
            continue
        app.INPUT_CITIES.append({"City": name})
        existing_names.add(name.lower())
        added.append(name)

    return {
        "status": "ok",
        "added": added,
        "skipped_duplicates": skipped,
        "total_cities": len(app.INPUT_CITIES),
    }

@api.get("/csv")
def download_csv():
    """
    Serve the generated CSV file for download.
    Returns 404 if it hasn't been generated yet - call POST /refresh first.
    """
    if not app.CSV_OUTPUT_PATH or not Path(app.CSV_OUTPUT_PATH).is_file():
        raise HTTPException(
            status_code=404,
            detail="CSV not found yet. Call POST /refresh first to generate it.",
        )
    return FileResponse(
        path=app.CSV_OUTPUT_PATH,
        media_type="text/csv",
        filename=os.path.basename(app.CSV_OUTPUT_PATH),
    )


@api.get("/chart")
def get_chart():
    """
    Serve the generated humidity bar chart as a PNG image.
    Returns 404 if it hasn't been generated yet - call POST /refresh first.
    """
    if not app.CHART_OUTPUT_PATH or not Path(app.CHART_OUTPUT_PATH).is_file():
        raise HTTPException(
            status_code=404,
            detail="Chart not found yet. Call POST /refresh first to generate it.",
        )
    return FileResponse(path=app.CHART_OUTPUT_PATH, media_type="image/png")

