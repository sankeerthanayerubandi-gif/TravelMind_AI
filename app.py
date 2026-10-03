from __future__ import annotations

import json
import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.graph.workflow import run_agentic_workflow
from backend.services.core import convert_currency, get_weather, save_trip
from backend.services.places import DemoPlaceProvider, Place, wikipedia_image
from backend.services.phase5 import booking_links, crowd_level, group_profile, invite_code
from backend.services.journey import budget_breakdown, journey_options, provider_search_url
from backend.utils.helpers import money

st.set_page_config(page_title="TravelMind 3D", page_icon="🌍", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --ink:#f3f7ff; --muted:#9aacc6; --violet:#8c6dff; --cyan:#36d7e9; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:radial-gradient(circle at 15% 0%,rgba(70,56,150,.28),transparent 32%),radial-gradient(circle at 90% 10%,rgba(20,164,180,.18),transparent 30%),#07111f; color:var(--ink); }
.block-container { padding:2rem 3.5rem 4rem; max-width:1500px; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif; letter-spacing:-.03em; }
.hero h1 { font-size:clamp(2.8rem,6vw,5.9rem); line-height:.93; margin:.45rem 0 .9rem; background:linear-gradient(105deg,#fff 15%,#b9c8ff 45%,#72ebf0 90%); -webkit-background-clip:text; color:transparent; }
.hero p { color:#a8b8d2; font-size:1.08rem; max-width:700px; }
.eyebrow { color:#7ee7f2; text-transform:uppercase; letter-spacing:.18em; font-size:.72rem; font-weight:700; }
.glass { background:linear-gradient(145deg,rgba(25,43,72,.82),rgba(9,19,34,.80)); border:1px solid rgba(152,174,220,.15); border-radius:24px; padding:1.2rem; box-shadow:0 18px 60px rgba(0,0,0,.22); }
.metric { color:#90a7c8; font-size:.78rem; text-transform:uppercase; letter-spacing:.11em; }
.metric strong { display:block; color:#f6f8ff; font-family:'Space Grotesk'; font-size:1.55rem; margin-top:.3rem; }
.card-title { color:#fff; font-size:1.08rem; font-weight:700; margin-bottom:.25rem; }
.card-sub { color:#9aacc6; font-size:.88rem; line-height:1.45; }
.pill { display:inline-block; border:1px solid rgba(126,231,242,.24); color:#91edf3; border-radius:999px; padding:.25rem .65rem; font-size:.74rem; margin:.12rem; background:rgba(54,215,233,.07); }
.agent { display:flex; gap:.7rem; align-items:flex-start; padding:.6rem 0; border-bottom:1px solid rgba(255,255,255,.07); }
.dot { width:9px; height:9px; background:#58e0c2; border-radius:50%; margin-top:.35rem; box-shadow:0 0 12px #58e0c2; }
section[data-testid="stSidebar"] { background:rgba(6,15,28,.95); border-right:1px solid rgba(157,182,235,.12); }
.stButton>button,.stDownloadButton>button { border-radius:12px; border:1px solid rgba(143,114,255,.45); background:linear-gradient(135deg,#7055e9,#3b8fb5); color:#fff; font-weight:700; }
.place-card { min-height:220px; }
.small-note { color:#93a7c4; font-size:.82rem; }
</style>
""", unsafe_allow_html=True)

BASE = Path(__file__).parent
provider = DemoPlaceProvider(BASE / "backend" / "data" / "demo_places.csv", enable_live_search=True)

for key, default in {
    "trip": None, "saved_trips": [], "page": "Command Center", "origin": "", "present_location": "",
    "album": None, "album_photos": [], "group_members": [], "chat_messages": [],
    "selected_place_ids": [], "search_query": "", "planner_destination": "Kyoto, Japan",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

T = {"nav": "Navigate", "plan": "Plan My Trip", "explore": "Explore", "generate": "Generate itinerary", "replan": "Replan itinerary", "today": "Today", "save": "Save trip", "search": "Search", "details": "View details"}

@st.cache_data(ttl=86400, show_spinner=False)
def image_for(name: str) -> str | None:
    return wikipedia_image(name)


def render_place(place: Place, key_prefix: str, allow_add: bool = True) -> None:
    with st.container(border=True):
        image = image_for(place.name)
        if image:
            st.image(image, use_container_width=True)
        else:
            st.markdown(f"<div class='glass place-card'><div class='eyebrow'>{place.category}</div><h3>{place.name}</h3><p class='card-sub'>No verified image is available; details below come from {place.source}.</p></div>", unsafe_allow_html=True)
        st.markdown(f"**{place.name}** · `{place.category}` · {place.city}, {place.country}")
        st.caption(place.description)
        st.write(f"Visit: {place.estimated_visit_duration or 'Not available'} min · Best time: {place.best_time_to_visit} · Hours: {place.opening_hours}")
        st.caption(f"Source: {place.source} · Location: {place.latitude:.4f}, {place.longitude:.4f}")
        st.link_button("Open map", place.map_url)
        crowd = crowd_level(place)
        st.caption(f"Crowd: {crowd['label']} · {crowd['basis']}")
        with st.expander("Stay · food · transport"):
            for label, url in booking_links(f"{place.city}, {place.country}", place.name).items():
                st.link_button(f"Find {label}", url, key=f"{key_prefix}-booking-{place.id}-{label}")
        if allow_add and st.button("Add to current trip", key=f"add-{key_prefix}-{place.id}"):
            if place.id not in st.session_state.selected_place_ids:
                st.session_state.selected_place_ids.append(place.id)
            st.success(f"Added {place.name} to the current trip.")


def render_itinerary(trip: dict) -> None:
    st.success(f"Workflow complete · {trip['status']}")
    if trip.get("origin") or trip.get("present_location"):
        st.info(f"Journey context · Starting from: {trip.get('origin') or 'Not specified'} · Present location: {trip.get('present_location') or 'Not specified'} → Destination: {trip.get('destination')}")
    st.markdown("### Book the journey around your itinerary")
    booking_destination = trip.get("destination", "")
    b1, b2, b3, b4 = st.columns(4)
    for col, label in zip((b1, b2, b3, b4), ("Stays", "Food", "Transport", "Rental cars")):
        with col:
            st.link_button(f"Find {label}", booking_links(booking_destination, booking_destination)[label])
    st.markdown("### How will I get there?")
    st.caption("Origin and destination are kept separate. Costs and durations below are estimates, not live fares or availability.")
    for option in journey_options(trip.get("origin", ""), booking_destination, trip.get("currency", "INR")):
        with st.expander(f"{option['name']} · {option['duration_hours']} h · {option['estimated_cost']:,.0f} estimated · {option['changes']} changes"):
            st.write(f"Convenience: **{option['convenience']}** · {option['source_status']}")
            for segment in option["segments"]:
                st.write(f"**{segment['vehicle']}** · Board: {segment['board']} → Get down: {segment['drop']} · {segment['duration']} · {segment['cost']:,.0f} estimated")
            k1, k2, k3 = st.columns(3)
            k1.link_button("Search bus", provider_search_url("bus", booking_destination))
            k2.link_button("Search trains", provider_search_url("train", booking_destination))
            k3.link_button("Check flights", provider_search_url("flight", booking_destination))
    cost = budget_breakdown(
        transport=min((o["estimated_cost"] for o in journey_options(trip.get("origin", ""), booking_destination)), default=0),
        nights=max(0, trip.get("days", 1) - 1), nightly_stay=900,
        travelers=trip.get("traveler_count", 1), days=trip.get("days", 1),
        activities=sum(float(day.get("estimated_day_cost", 0)) for day in trip.get("itinerary", [])),
    )
    st.markdown("### Transparent trip cost estimate")
    st.caption("Estimated model · prices may change · no availability is claimed.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Per person estimate", f"{cost['per_person']:,.0f}")
    c2.metric("Group estimate", f"{cost['group_total']:,.0f}")
    c3.metric("Emergency buffer", f"{cost['emergency']:,.0f}")
    st.write({"Transport": cost["transport"], "Stay": cost["stay"], "Food": cost["food"], "Local transport": cost["local_transport"], "Activities": cost["activities"]})
    added = [place for place in provider.places if place.id in st.session_state.selected_place_ids]
    if added:
        st.info("Added to this trip: " + ", ".join(place.name for place in added))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Destination", trip["destination"])
    m2.metric("Days", trip["days"])
    m3.metric("Estimated cost", money(trip["estimated_total"], trip["currency"]))
    m4.metric("Mode", "Adaptive" if "replan" in trip["status"] else "Verified")
    if trip.get("replan_reason"):
        st.info(f"Replanned because: {trip['replan_reason']}")
    for day in trip["itinerary"]:
        with st.expander(f"DAY {day['day']} · {day['date']} · {day['title']}", expanded=day["day"] == 1):
            st.write(day["notes"])
            st.caption(f"Estimated day cost: {trip['currency']} {day['estimated_day_cost']:.2f} · {day['transit']}")
            for index, stop in enumerate(day["stops"]):
                st.markdown(f"**{index + 1}. {stop['name']}** · {stop['category']} · {stop['start_time']}–{stop['end_time']}")
                st.caption(f"{stop['description']} · Visit {stop['recommended_duration_min']} min · Travel from previous stop {stop['travel_time_from_previous_min']} min")
                st.caption(f"Food suggestion: {stop['food_suggestion']} · Opening: {stop['opening_hours']} · Fee: {stop['entry_fee'] or 'Not available'} {stop['currency']}")
                map_col, remove_col = st.columns([3, 1])
                with map_col:
                    st.link_button("Map this place", stop["map_url"], key=f"map-{trip['created_at']}-{day['day']}-{index}")
                with remove_col:
                    if st.button("Remove", key=f"remove-{trip['created_at']}-{day['day']}-{index}"):
                        day["stops"].pop(index)
                        st.rerun()
    points = [stop for day in trip["itinerary"] for stop in day["stops"] if stop.get("latitude") and stop.get("longitude")]
    if points:
        st.subheader("Route map")
        st.map(pd.DataFrame(points).rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
    st.download_button("Download itinerary JSON", json.dumps(trip, indent=2, ensure_ascii=False), file_name="travelmind_itinerary.json", mime="application/json")
    share_text = "\n".join(
        [f"TravelMind itinerary: {trip['destination']} · {trip['days']} days"]
        + [f"Day {day['day']}: " + ", ".join(stop["name"] for stop in day["stops"]) for day in trip["itinerary"]]
    )
    st.download_button("Share itinerary summary", share_text, file_name="travelmind_share.txt", mime="text/plain")


with st.sidebar:
    st.markdown("## ◈ TravelMind 3D")
    st.caption("Autonomous multi-agent travel intelligence")
    pages = ["Command Center", "World Explorer", "Trip Studio", "Group Planner", "My Trip", "Travel Toolkit"]
    st.session_state.page = st.radio(T["nav"], pages, index=pages.index(st.session_state.page) if st.session_state.page in pages else 0)
    st.markdown("---")
    st.markdown("**System status**")
    st.markdown("🟢 Planner online  \n🟢 Place provider cached  \n🟢 Live search fallback ready")
    st.caption("Demo data is labelled. Optional live services fail safely.")

page = st.session_state.page

if page == "Command Center":
    st.markdown('<div class="hero"><div class="eyebrow">Autonomous travel intelligence · abstract-aligned prototype</div><h1>PLAN.<br>EXPLORE.<br>ADAPT.</h1><p>TravelMind coordinates discovery, planning, verification, monitoring, and replanning into one personalized travel workflow.</p></div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    for col, label, value in [(c1, "Places indexed", f"{len(provider.places)} demo + live search"), (c2, "Planning agents", "5"), (c3, "Plan modes", "Today + custom"), (c4, "API keys required", "0")]:
        with col: st.markdown(f'<div class="glass metric">{label}<strong>{value}</strong></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.55, 1])
    with left:
        st.markdown('<div class="glass"><div class="card-title">🌐 World pulse</div><div class="card-sub">Verified coordinates from the local catalog.</div>', unsafe_allow_html=True)
        df = pd.DataFrame([p.to_dict() for p in provider.places])
        fig = go.Figure(go.Scattergeo(lon=df.longitude, lat=df.latitude, text=df.name, mode="markers+text", textposition="top center", marker=dict(size=10, color=df.popularity_score, colorscale=[[0, "#36d7e9"], [1, "#8c6dff"]], line=dict(width=1, color="#fff"))))
        fig.update_geos(showland=True, landcolor="#12243a", showocean=True, oceancolor="#081629", showcountries=True, countrycolor="#29405d", bgcolor="rgba(0,0,0,0)", projection_type="orthographic")
        fig.update_layout(height=450, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", font_color="#b9c8dd", showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="glass"><div class="card-title">⚡ Agent activity</div><div class="card-sub">The autonomous loop is ready to act.</div>', unsafe_allow_html=True)
        events = (st.session_state.trip or {}).get("agent_events", [{"agent": "Supervisor", "detail": "Waiting for a trip brief."}, {"agent": "Discovery", "detail": "Provider standing by."}, {"agent": "Verifier", "detail": "Constraints ready."}])
        for event in events:
            st.markdown(f'<div class="agent"><span class="dot"></span><div><b>{event["agent"]}</b><br><span class="card-sub">{event["detail"]}</span></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

elif page == "World Explorer":
    st.markdown('<div class="eyebrow">Global place discovery</div><h1>World Explorer</h1>', unsafe_allow_html=True)
    query = st.text_input("Search destinations or attractions", value=st.session_state.search_query, placeholder="Try Araku, Paris, beach, museum, mountain...")
    st.session_state.search_query = query
    a, b, c = st.columns(3)
    with a: category = st.selectbox("Category", ["All"] + sorted({p.category for p in provider.places}))
    with b: country = st.selectbox("Country", ["All"] + sorted({p.country for p in provider.places}))
    with c: live = st.checkbox("Allow live OpenStreetMap search", value=True)
    provider.enable_live_search = live
    results = provider.search(query, category, country)
    st.caption(f"{len(results)} places surfaced · results without verified facts are clearly labelled")
    if not results:
        st.warning("No place found. Try a city, country, or landmark name.")
    for row in range(0, len(results), 2):
        cols = st.columns(2)
        for col, place in zip(cols, results[row:row + 2]):
            with col: render_place(place, f"explore-{row}")

elif page == "Trip Studio":
    st.markdown('<div class="eyebrow">Plan → verify → monitor → replan</div><h1>Trip Studio</h1>', unsafe_allow_html=True)
    with st.form("trip_form"):
        left, right = st.columns(2)
        with left:
            origin = st.text_input("Where are you travelling from?", value=st.session_state.origin, placeholder="e.g. Visakhapatnam, India")
            present_location = st.text_input("Your present location", value=st.session_state.present_location, placeholder="Optional: current city or hotel")
            destination = st.text_input("Destination / city / country", value=st.session_state.planner_destination, help="Examples: Meghalaya, Kyoto, Araku, Paris")
            date_mode = st.radio("Start date", ["Today", "Tomorrow", "Custom date"], horizontal=True)
            custom_date = st.date_input("Custom start date", value=date.today() + timedelta(days=7), disabled=date_mode != "Custom date")
            days = st.slider("Trip duration (days)", 1, 14, 4)
            travelers = st.number_input("Number of travelers", 1, 20, 2)
        with right:
            budget_tier = st.selectbox("Budget level", ["Low", "Medium", "High"])
            budget_per_person = st.number_input("Maximum budget per person", min_value=0.0, max_value=100000.0, value=1800.0, step=100.0, help="The planner uses this as a planning ceiling; actual prices may change.")
            currency = st.selectbox("Display currency", ["EUR", "USD", "INR", "GBP"])
            pace = st.select_slider("Travel pace", options=["Relaxed", "Balanced", "Intensive"], value="Balanced")
            available_hours = st.slider("Available hours per day", 2.0, 16.0, 8.0, 0.5)
        interests = st.multiselect("Interests / preferences", ["Nature", "Culture", "Food", "Adventure", "Shopping"], default=["Nature", "Culture"])
        generate = st.form_submit_button(T["generate"], use_container_width=True)
    if generate:
        start_date = date.today() if date_mode == "Today" else date.today() + timedelta(days=1) if date_mode == "Tomorrow" else custom_date
        st.session_state.planner_destination = destination
        st.session_state.origin = origin
        st.session_state.present_location = present_location
        request = {"origin": origin, "present_location": present_location, "destination": destination, "start_date": start_date, "days": days, "travelers": travelers, "budget": budget_per_person * travelers, "budget_per_person": budget_per_person, "budget_tier": budget_tier, "currency": currency, "pace": pace, "available_hours": available_hours, "interests": interests, "selected_place_ids": st.session_state.selected_place_ids}
        with st.spinner("Creating your personalized trip with Supervisor, Discovery, Planner, and Verifier agents..."):
            try:
                st.session_state.trip = run_agentic_workflow(request, provider)
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Planner could not complete safely: {exc}")
    trip = st.session_state.trip
    if trip:
        render_itinerary(trip)
        if st.button(T["save"], key="save-trip"):
            st.session_state.saved_trips = save_trip(trip, st.session_state.saved_trips)
            st.success("Trip saved in this session.")
        st.subheader(T["replan"])
        replan_request = st.text_area("What should change?", placeholder="Examples: remove museums, add beaches, make it cheaper, add food places, I have only 4 hours")
        if st.button(T["replan"], key="replan-trip"):
            if not replan_request.strip():
                st.warning("Describe at least one change request.")
            else:
                with st.spinner("Replanning the route around your new constraint..."):
                    try:
                        st.session_state.trip = run_agentic_workflow({**trip, "replan_request": replan_request}, provider, replan_request)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Replanning failed safely: {exc}")

elif page == "Group Planner":
    st.markdown('<div class="eyebrow">Consensus over convenience</div><h1>AI Group Trip Planner</h1>', unsafe_allow_html=True)
    st.caption("Build a fair group brief from every traveller instead of planning only for the trip owner.")
    with st.form("group_member_form"):
        name = st.text_input("Member name", placeholder="e.g. Ananya")
        budget_member = st.number_input("Member budget", min_value=0.0, value=500.0, step=50.0)
        interests_member = st.multiselect("Interests", ["Nature", "Culture", "Food", "Adventure", "Shopping", "Relaxation"], default=["Nature"])
        must_visit = st.text_input("Must-visit places", placeholder="Comma-separated")
        avoid = st.text_input("Avoid / low priority", placeholder="Comma-separated")
        add_member = st.form_submit_button("Add member preference", use_container_width=True)
    if add_member and name.strip():
        st.session_state.group_members.append({"name": name.strip(), "budget": budget_member, "interests": interests_member, "must_visit": must_visit, "avoid": avoid})
        st.success(f"Added {name.strip()} to the group brief.")
    if st.session_state.group_members:
        profile = group_profile(st.session_state.group_members)
        st.write("**Members:** " + ", ".join(m["name"] for m in st.session_state.group_members))
        c1,c2,c3 = st.columns(3)
        c1.metric("Members", profile["members"])
        c2.metric("Combined stated budget", f"{profile['budget']:,.0f}")
        c3.metric("Must-visit places", len(profile["must_visit"]))
        st.info("Common preferences: " + (", ".join(profile["common"]) or "No common preference yet."))
        if profile["conflicts"]: st.warning("Preferences to balance: " + ", ".join(profile["conflicts"]))
        if profile["must_visit"]: st.success("Consensus places: " + ", ".join(profile["must_visit"]))
        if st.button("Generate fair group itinerary", use_container_width=True):
            st.session_state.group_profile = profile
            st.success("Group brief is ready. Open Trip Studio to generate the route using the destination, budget, pace, and shared preferences.")
        if st.button("Clear group members"):
            st.session_state.group_members = []
            st.rerun()
    else:
        st.info("Add at least two traveller preferences to make the plan genuinely group-aware.")

elif page == "My Trip":
    st.markdown('<div class="eyebrow">Your private trip workspace</div><h1>My Trip</h1>', unsafe_allow_html=True)
    trip = st.session_state.trip
    if not trip:
        st.info("Generate a route in Trip Studio first.")
    else:
        st.write(f"**{trip['destination']}** · {trip['days']} days · {trip.get('origin') or 'Origin not specified'} → destination")
        t1,t2,t3 = st.tabs(["Album", "Bookings", "My Favorites"])
        with t1:
            if not st.session_state.album:
                if st.button("Create private trip album", use_container_width=True):
                    seed = f"{trip['destination']}|{trip['created_at']}"
                    code = invite_code(seed)
                    st.session_state.album = {"name": f"{trip['destination']} memories", "code": code, "members": ["Owner"], "revoked": False}
                    st.success("Private album created for this session.")
            else:
                album = st.session_state.album
                st.subheader(album["name"])
                st.caption("Session-private demo album. External authentication/storage is required for multi-user production access.")
                st.code(f"Join code: {album['code']}")
                invite = f"{st.context.url if hasattr(st, 'context') else 'TravelMind'}?album={album['code']}"
                st.text_input("Invite link", invite, disabled=True)
                uploads = st.file_uploader("Upload trip photos", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True, key="album_uploads")
                if uploads:
                    existing = {item["name"] for item in st.session_state.album_photos}
                    for file in uploads:
                        if file.name not in existing and file.size <= 25 * 1024 * 1024:
                            suffix = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "jpg"
                            safe_name = f"TravelMind_{trip['destination'].replace(' ', '-')}_Day-1_Owner_{len(st.session_state.album_photos)+1}.{suffix}"
                            st.session_state.album_photos.append({"name": safe_name, "original_name": file.name, "bytes": file.getvalue(), "mime": file.type, "uploader": "Owner", "favorite": False, "date": date.today().isoformat(), "day": 1})
                    st.success(f"{len(uploads)} upload(s) processed. Files over 25 MB are rejected.")
                for index, photo in enumerate(st.session_state.album_photos):
                    col, act = st.columns([4,1])
                    with col:
                        st.image(photo["bytes"], width=220)
                        st.write(f"**{photo['name']}** · uploaded by {photo['uploader']} · Day {photo.get('day', 1)} · {photo.get('date', 'Upload date')}")
                        st.caption("Original-quality download · membership is required in a production private-storage deployment.")
                    with act:
                        photo["favorite"] = st.checkbox("Favorite", value=photo["favorite"], key=f"fav-{index}")
                        st.download_button("Save", photo["bytes"], file_name=photo["name"], key=f"download-{index}")
                        st.code(f"Share album/photo: {album['code']}/{index}", language=None)
                if st.session_state.album_photos:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                        for photo in st.session_state.album_photos:
                            archive.writestr(f"TravelMind_{trip['destination'].replace(' ', '-')}_Album/Day-{photo.get('day', 1)}/{photo['name']}", photo["bytes"])
                    st.download_button("Download All as ZIP", zip_buffer.getvalue(), file_name=f"TravelMind_{trip['destination'].replace(' ', '-')}_Album.zip", mime="application/zip")
        if st.button("Download Trip for Offline Use", use_container_width=True):
            offline = {"trip": trip, "origin": st.session_state.origin, "present_location": st.session_state.present_location, "saved_places": st.session_state.selected_place_ids, "offline_status": "OFFLINE CACHED", "note": "Live prices, availability, weather, and location are not included unless retrieved before download."}
            st.download_button("Save offline trip package", json.dumps(offline, indent=2, ensure_ascii=False), file_name="travelmind_offline_trip.json", mime="application/json")
        with t2:
            st.subheader("External booking workspace")
            st.caption("These links open legitimate provider/search pages. TravelMind does not claim a reservation or take payment.")
            first_stop = trip["itinerary"][0]["stops"][0]["name"] if trip["itinerary"] and trip["itinerary"][0]["stops"] else trip["destination"]
            for label, url in booking_links(trip["destination"], first_stop).items(): st.link_button(f"Find {label} near {first_stop}", url, use_container_width=True)
        with t3:
            favorites = [p for p in st.session_state.album_photos if p["favorite"]]
            if favorites:
                for p in favorites: st.write("♥ " + p["name"])
            else: st.info("Favorite album photos to see them here.")

elif page == "Travel Toolkit":
    st.markdown('<div class="eyebrow">Useful trip utilities</div><h1>Travel Toolkit</h1>', unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="glass"><div class="card-title">☁ Weather snapshot</div>', unsafe_allow_html=True)
        city_place = st.selectbox("Place for weather", provider.places, format_func=lambda p: f"{p.city} · {p.name}")
        weather = get_weather(city_place.city, city_place.latitude, city_place.longitude)
        if weather["temperature"] is None: st.warning(weather["condition"])
        else: st.metric("Temperature", f"{weather['temperature']}°C", weather["condition"])
        st.caption(f"Humidity {weather['humidity'] if weather['humidity'] is not None else 'Not available'}% · Wind {weather['wind'] if weather['wind'] is not None else 'Not available'} km/h · {weather['source']}")
        st.markdown('</div><br>', unsafe_allow_html=True)
        st.markdown('<div class="glass"><div class="card-title">◎ Currency converter</div>', unsafe_allow_html=True)
        amount = st.number_input("Amount", 1.0, 100000.0, 100.0)
        x, y = st.columns(2)
        with x: src = st.selectbox("From", ["EUR", "USD", "GBP", "JPY", "INR"])
        with y: tgt = st.selectbox("To", ["EUR", "USD", "GBP", "JPY", "INR"], index=1)
        result = convert_currency(amount, src, tgt)
        st.metric("Converted", f"{result['converted']:,.2f} {tgt}", f"Rate {result['rate']} · {result['source_name']}")
        st.markdown('</div>', unsafe_allow_html=True)
    with b:
        st.markdown('<div class="glass"><div class="card-title">◌ Crowd-aware discovery</div>', unsafe_allow_html=True)
        crowd_filter = st.selectbox("Show", ["Any", "Less crowded", "Moderate", "Busy"])
        for place in provider.places:
            crowd = crowd_level(place)
            if crowd_filter != "Any" and crowd["label"] != crowd_filter: continue
            st.write(f"**{place.name}** · {crowd['label']} · {place.city}")
            st.caption(crowd["basis"])
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="glass"><div class="card-title">TravelMind Assistant</div>', unsafe_allow_html=True)
        for msg in st.session_state.chat_messages: st.caption(f"{msg['role']}: {msg['text']}")
        question = st.text_input("Ask about this trip", placeholder="What can I do near my destination?")
        if st.button("Ask assistant") and question.strip():
            q = question.lower()
            destination = (st.session_state.trip or {}).get("destination", st.session_state.planner_destination)
            if "crowd" in q or "quiet" in q: answer = f"For {destination}, filter the crowd-aware list for Less crowded; labels are catalog estimates, not live crowd data."
            elif "budget" in q or "cheap" in q: answer = "Use Travel Toolkit currency and open the external Food/Stays search links from My Trip for lower-cost options."
            elif "day" in q and st.session_state.trip: answer = "Your current itinerary is shown in Trip Studio; use Replan itinerary to change a day with a written constraint."
            else: answer = f"For {destination}, open World Explorer for verified places and My Trip for stays, food, transport, and album actions."
            st.session_state.chat_messages += [{"role":"You","text":question},{"role":"Assistant","text":answer}]
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<br><div style='text-align:center;color:#667b9c;font-size:.78rem'>TRAVELMIND 3D · PLAN WITH CONFIDENCE · ADAPT WITH INTELLIGENCE</div>", unsafe_allow_html=True)
