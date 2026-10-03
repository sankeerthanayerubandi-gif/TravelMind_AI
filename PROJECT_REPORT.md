# TravelMind 3D — Abstract-Aligned Project Report

## What was broken

The previous Streamlit version accepted only a country, selected arbitrary first records, did not use dates, interests, available hours, or budget meaningfully, and its replan action changed notes rather than the route. It also had limited search, demo-only weather, no reliable image fallback, and no explicit no-repeat allocation across days.

## What was fixed

The planner now accepts destination, Today/Tomorrow/custom date, trip duration, travelers, budget tier, total budget, currency, pace, available hours, and interests. The multi-agent workflow ranks relevant places, generates daily routes with unique attractions, approximate timings, visit durations, travel time, food suggestions, costs, map links, and route coordinates. Replan requests alter ranking and route constraints. Search supports comma-separated city/country input, verified local records, and optional live Nominatim results. Place cards use Wikipedia thumbnails only when a verified thumbnail is found. Weather, currency, saved trips, JSON export, map links, add-to-trip, and remove actions are wired into Streamlit state.

## Validation

- `python -m compileall -q .` passed.
- `pytest -q` passed: 3 tests.
- `python smoke_check.py` passed with 31 places.
- Kyoto and Araku catalog queries each resolve to five local attractions.
- Kyoto four-day route produces unique attractions on every day.
- Streamlit HTTP endpoint returns status 200.
- Browser test confirmed the Trip Studio form, Today mode, route map, day rows, save, remove, download, and replan controls render.

## Run command

```bash
cd TravelMind3D
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

## APIs and limitations

OpenStreetMap Nominatim, Open-Meteo, Frankfurter, and Wikipedia REST are optional no-key integrations. The local CSV remains the offline fallback. No payment or confirmed reservation operation is included. Multi-user database persistence and LLM generation can be added later without changing the planner/provider interfaces.
