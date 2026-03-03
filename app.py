import os
from fastapi import FastAPI, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from plexapi.server import PlexServer
from openai import OpenAI
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")  # Erstelle templates/ Ordner mit index.html
# app.mount("/static", StaticFiles(directory="static"), name="static")

PLEX_URL = os.getenv('PLEX_URL')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

plex = PlexServer(PLEX_URL, PLEX_TOKEN)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tv = plex.library.section('TV Shows')
    ondeck = []
    for show in tv.all():
        episodes = show.episodes()
        unwatched = [ep for ep in episodes if not ep.isWatched]
        if unwatched:
            first_unwatched = unwatched[0]
            ondeck.append({
                'title': show.title,
                'season': first_unwatched.seasonNumber,
                'episode': first_unwatched.episodeNumber,
                'ep_title': first_unwatched.title
            })
    return templates.TemplateResponse("index.html", {"request": request, "ondeck": ondeck})

@app.get("/summary/{show}/{season}/{episode}")
async def get_summary(show: str, season: int, episode: int):
    # Hole vorherige Episoden (vereinfacht; erweitere mit echten Titles/Zusammenfassungen)
    tv = plex.library.section('TV Shows')
    show_obj = tv.get(show)
    prev_eps = show_obj.episode(season, episode-1).title if episode > 1 else "Keine vorherigen Infos"
    prompt = f"Zusammenfasse die Handlung bis {show} S{season}E{episode-1} für Verständnis der nächsten Folge: {prev_eps}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return {"summary": response.choices[0].message.content}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)