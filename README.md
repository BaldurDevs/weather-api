# Weather City Data App

Fetches current weather (temperature, humidity, wind speed) for a list of
cities, using the free [Open-Meteo](https://open-meteo.com/en/docs) weather
and geocoding APIs (no API key required). Processes the data with pandas,
exports it to CSV, generates a humidity bar chart with matplotlib, and
exposes everything through a FastAPI web API.

## Requirements

- Python 3.10+
- Internet access (to call the Open-Meteo APIs)

## 1. Set up a virtual environment

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**Windows (cmd):**

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

You'll know it's active because the terminal prompt shows `(venv)` at the
start of the line. To turn it off later, just run `deactivate`.

## 2. Install dependencies

With the virtual environment active:

```bash
pip install -r requirements.txt
```

## 3. Configure environment variables

Copy the example file and fill in the values:

```bash
cp .env.example .env
```

`.env` should contain:

```
WEATHER_APP_TIMEOUT=10
CSV_FILE_PATH=city_weather.csv
CHART_FILE_PATH=temperature_chart.png
OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
GEOCODING_URL=https://geocoding-api.open-meteo.com/v1/search
```

**All five variables are required** - `main.py` reads them with
`os.getenv()` and no fallback defaults, so a missing variable becomes
`None` and breaks the app at runtime. Double-check `.env` is filled in
completely before running anything below.

## 4. Run it

There are two ways to use the app: as a one-off script, or as a running API.

### Option A — Run once as a script

Fetches weather for the 5 default cities, saves `city_weather.csv`, and
generates `temperature_chart.png`, then exits.

```bash
python main.py
```

### Option B — Run as a web API

Starts a persistent server so you can hit endpoints on demand.

```bash
uvicorn api:api --reload --host 0.0.0.0
```

Then open **http://127.0.0.1:8000/docs** for an interactive Swagger UI
where you can try every endpoint from the browser, or use `curl`:

| Method | Endpoint  | What it does                                                          |
|--------|-----------|------------------------------------------------------------------------|
| GET    | `/`       | Health check / lists available endpoints                              |
| POST   | `/refresh`| Re-fetches weather for all current cities, rebuilds the CSV and chart |
| GET    | `/cities` | Lists the cities currently tracked by the app                        |
| POST   | `/cities` | Adds new cities (JSON body, see below)                               |
| GET    | `/csv`    | Downloads `city_weather.csv`                                          |
| GET    | `/chart`  | Returns the humidity bar chart as a PNG image                        |

```bash
# 1. Add cities (optional - 10 default cities are preloaded)
curl -X POST http://127.0.0.1:8000/cities \
  -H "Content-Type: application/json" \
  -d '{"cities": ["Madrid", "Rome", "Cairo"]}'

# 2. Fetch weather + regenerate the CSV and chart
curl -X POST http://127.0.0.1:8000/refresh

# 3. Download the results
curl http://127.0.0.1:8000/csv --output city_weather.csv
curl http://127.0.0.1:8000/chart --output chart.png
```

**Note:** `/cities` changes only live in memory. Restarting the server
(or `--reload` picking up a code change) resets the city list back to the
10 defaults - it doesn't persist added cities to disk.

## Output columns (CSV)

| Column              | Meaning                          |
|---------------------|-----------------------------------|
| City                | City name                        |
| Latitude / Longitude| Resolved via the geocoding API   |
| Temperature (C)/(F) | Current temperature              |
| Humidity (%)        | Current relative humidity        |
| Wind speed (km/h)/(mph) | Current wind speed           |
| Error               | Populated if that city's request failed |

Rows are sorted by humidity, lowest first.

## Project structure

```
.
├── api.py                 # FastAPI app logic
├── main.py                # Pipeline (fetch/process/persist/chart)
├── requirements.txt        # Python dependencies
├── .env.example            # Template for required environment variables
├── city_weather.csv        # Generated output (after running)
└── temperature_chart.png   # Generated chart (after running)
```