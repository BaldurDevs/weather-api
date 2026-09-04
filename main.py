import os
from pathlib import Path

import matplotlib
import requests
import pandas as pd
from typing import Dict, List
from dotenv import load_dotenv
import matplotlib.pyplot as plt

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel, Field

load_dotenv()

DEFAULT_TIMEOUT = int(os.getenv("WEATHER_APP_TIMEOUT", "10"))
CSV_OUTPUT_PATH = os.getenv("CSV_FILE_PATH")
CHART_OUTPUT_PATH = os.getenv("CHART_FILE_PATH")
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL")
GEOCODING_URL = os.getenv("GEOCODING_URL")

DEFAULT_CITIES: List[Dict] = [
    {"City": "New York"},
    {"City": "Tokyo" },
    {"City": "London" },
    {"City": "Paris" },
    {"City": "Buenos Aires" },
]

DEFAULT_COLUMNS = [
    "City",
    "Latitude",
    "Longitude",
    "Temperature (C)",
    "Temperature (F)",
    "Humidity (%)",
    "Wind speed (km/h)",
    "Wind speed (mph)",
    "Error",
]

app = FastAPI(
    title="Weather City Data API",
    description="Serves weather data, a CSV export, and a humidity chart for a list of cities.",
    version="v1.0.0",
)

class AddCitiesRequest(BaseModel):
    cities: List[str] = Field(
        ...,
        min_length=1,
        description="List of city names to add to the app.",
        examples=[["Madrid", "Rome", "Cairo"]],
    )

def fetch_city_geocode(city: Dict, timeout: int = 1):

    city_name = city["City"]
    params = {"name": city_name, "count": 1, "language": "en", "format": "json"}

    try:
        response = requests.get(GEOCODING_URL, params=params, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results")

        if not results:
            print(f"  [warn] no geocoding match found for '{city_name}'.")
            city["Error"] = f"No geocoding match found for '{city_name}'."
            return None

        result = results[0]
        city["Latitude"] = float(result["latitude"])
        city["Longitude"] = float(result["longitude"])

    except requests.exceptions.RequestException as exc:
        print(f"  [warn] retrieve geocoding failed for '{city_name}'. ERROR: {exc}")
        city["error"] = exc
        return None

def fetch_city_weather(city: Dict, timeout: int = 1):
    params = {
        "latitude": city["Latitude"],
        "longitude": city["Longitude"],
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "auto",
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        current = data.get("current", {})

        temp_c = current.get("temperature_2m")
        wind_kmh = current.get("wind_speed_10m")

        city["Temperature (C)"] = temp_c
        city["Temperature (F)"] = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None


        city["Wind speed (km/h)"] = current.get("wind_speed_10m")
        city["Wind speed (mph)"] = round(wind_kmh * 0.621371, 1) if wind_kmh is not None else None

        city["Humidity (%)"] = current.get("relative_humidity_2m")

    except requests.exceptions.RequestException as exc:
        print(f"  [warn] fetching weather process fail for city: {city['City']}. Error: {exc}")
        city["Error"] = str(exc)


# 1. Scrape Public Data
def fetch_cities_data(cities: List[Dict], default_timeout: int = 10):
    for city in cities:
        print(f"[info] fetching data from '{city["City"]}'...")

        fetch_city_geocode(city, default_timeout)

        if "Error" in city :
            continue

        fetch_city_weather(city, default_timeout)

# 2. Data Processing
def process_cities_data(cities: List[Dict]) -> pd.DataFrame :
    dataframe = pd.DataFrame(cities, columns=DEFAULT_COLUMNS)

    # Sort cities by humidity (lower at first)
    dataframe = dataframe.sort_values("Humidity (%)", ascending=True, na_position="last").reset_index(drop=True)

    return dataframe

# 3. Persist result
def persist_cities_data(cities_data : pd.DataFrame) -> None:
    cities_data.to_csv(CSV_OUTPUT_PATH, index=False, encoding='utf-8')

# 4. Visualize city weather data
def generate_cities_humidity_chart(cities_data : pd.DataFrame) -> None:
        matplotlib.use("Agg")  # non-interactive backend, works without a display

        # Drop cities with no temperature (failed requests) so the chart doesn't plot a gap/NaN bar.
        plot_df = cities_data.dropna(subset=["Humidity (%)"])

        fig, ax = plt.subplots(figsize=(9, 5))
        bars = ax.bar(plot_df["City"], plot_df["Humidity (%)"], color="#ff6200")

        # Label each bar with its value
        ax.bar_label(bars, fmt="%.1f°C")

        ax.set_title("Current Humidity by City")
        ax.set_xlabel("City")
        ax.set_ylabel("Humidity (%)")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        fig.savefig(CHART_OUTPUT_PATH, dpi=150)
        plt.close(fig)


@app.get("/")
def root():     # Basic health check / index.
    return {
        "status": "ok",
        "endpoints": ["/refresh", "/csv", "/chart", "/cities"],
    }

@app.post("/refresh")
def refresh_data():
    fetch_cities_data(DEFAULT_CITIES)
    cities_data = process_cities_data(DEFAULT_CITIES)
    persist_cities_data(cities_data)
    generate_cities_humidity_chart(cities_data)

    return {"status": "ok", "cities_processed": len(DEFAULT_CITIES)}


@app.get("/cities")
def list_cities():
    return DEFAULT_CITIES


@app.post("/cities")
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
    existing_names = {c["City"].strip().lower() for c in DEFAULT_CITIES}

    added = []
    skipped = []
    for raw_name in request.cities:
        name = raw_name.strip()
        if not name:
            continue
        if name.lower() in existing_names:
            skipped.append(name)
            continue
        DEFAULT_CITIES.append({"City": name})
        existing_names.add(name.lower())
        added.append(name)

    return {
        "status": "ok",
        "added": added,
        "skipped_duplicates": skipped,
        "total_cities": len(DEFAULT_CITIES),
    }

@app.get("/csv")
def download_csv():
    """
    Serve the generated CSV file for download.
    Returns 404 if it hasn't been generated yet - call POST /refresh first.
    """
    if not CSV_OUTPUT_PATH or not Path(CSV_OUTPUT_PATH).is_file():
        raise HTTPException(
            status_code=404,
            detail="CSV not found yet. Call POST /refresh first to generate it.",
        )
    return FileResponse(
        path=CSV_OUTPUT_PATH,
        media_type="text/csv",
        filename=os.path.basename(CSV_OUTPUT_PATH),
    )


@app.get("/chart")
def get_chart():
    """
    Serve the generated humidity bar chart as a PNG image.
    Returns 404 if it hasn't been generated yet - call POST /refresh first.
    """
    if not CHART_OUTPUT_PATH or not Path(CHART_OUTPUT_PATH).is_file():
        raise HTTPException(
            status_code=404,
            detail="Chart not found yet. Call POST /refresh first to generate it.",
        )
    return FileResponse(path=CHART_OUTPUT_PATH, media_type="image/png")


if __name__ == "__main__":
    load_dotenv()
    fetch_cities_data(DEFAULT_CITIES)
    cities_df = process_cities_data(DEFAULT_CITIES)
    persist_cities_data(cities_df)
    generate_cities_humidity_chart(cities_df)

    print("[info] fetching data process is done.")
