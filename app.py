import os
from fastapi import FastAPI, Request  # Request hinzugefügt!
from fastapi.responses import HTMLResponse  # Fix: Aus responses!
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from plexapi.server import PlexServer
from openai import OpenAI

app = FastAPI()
templates = Jinja2Templates(directory="templates")
# app.mount("/static", StaticFiles(directory="static"), name="static")  # Falls CSS später

PLEX_URL = os.getenv('PLEX_URL', 'http://localhost:32400')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')

if PLEX_TOKEN:
    plex = PlexServer(PLEX_URL, PLEX_TOKEN)
else:
    plex = None  # Fehler vermeiden

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):  # Request-Param!
    if not plex:
        return HTMLResponse("<h1>Plex Token fehlt!</h1>")
    
    try:
        tv = plex.library.section('TV Shows')  # Passe Section-Name an!
        ondeck = []
        for show in tv.all():
            unwatched = [ep for ep in show.episodes() if not ep.isWatched]
            if unwatched:
                first = unwatched[0]
                ondeck.append({
                    'title': show.title.replace(" ", "_"),  # URL-safe
                    'season': first.seasonNumber,
                    'episode': first.episodeNumber,
                    'ep_title': first.title
                })
        return templates.TemplateResponse("index.html", {"request": request, "ondeck": ondeck})
    except Exception as e:
        return HTMLResponse(f"<h1>Fehler: {str(e)}</h1>")

@app.get("/summary/{show}/{season}/{episode}")
async def get_summary(show: str, season: int, episode: int):
    if not OPENAI_KEY:
        return {"error": "OpenAI Key fehlt"}
    
    client = OpenAI(api_key=OPENAI_KEY)
    # Einfacher Prompt – erweitere später mit realen Episoden-Infos
    prompt = f"Gib eine knappe Zusammenfassung aller Handlung bis {show} S{season}E{episode}, damit ich die nächste Folge verstehe. Halte es spoilerfrei."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
