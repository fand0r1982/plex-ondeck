import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from plexapi.server import PlexServer
from openai import OpenAI

app = FastAPI()
templates = Jinja2Templates(directory="templates")

PLEX_URL = os.getenv('PLEX_URL', 'http://host.docker.internal:32400')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')

plex = PlexServer(PLEX_URL, PLEX_TOKEN) if PLEX_TOKEN else None

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):  # FIX: Vollständige async def
    if not plex:
        return HTMLResponse("<h1>Plex Token fehlt!</h1>")
    
    try:
        # FIX 1: Echtes On-Deck (plex.library.onDeck() – nur angefangene!) [web:14][web:131]
        ondeck_items = plex.library.onDeck()  # Globale On-Deck-Liste!
        tv_ondeck = [item for item in ondeck_items if item.type == 'episode'][:20]
        items = []
        for item in tv_ondeck:
            show = item.show()
            if item.seasonNumber > 0 and item.episodeNumber > 1:  # Nur nicht S1E1!
                items.append({
                    'title': show.title.replace(" ", "_").replace("'", "").replace(",", "").replace("&", ""),
                    'season': item.seasonNumber,
                    'episode': item.episodeNumber,
                    'ep_title': item.title,
                    'show_title': show.title
                })
        return templates.TemplateResponse("index.html", {"request": request, "ondeck": items})
    except Exception as e:
        return HTMLResponse(f"<h1>Fehler: {str(e)}</h1><p>On-Deck API testen.</p>")

@app.get("/summary/{title}/{season}/{episode}")
async def get_summary(title: str, season: int, episode: int):
    if not OPENAI_KEY:
        return {"error": "OpenAI Key fehlt"}
    client = OpenAI(api_key=OPENAI_KEY)
    show_name = title.replace("_", " ")
    prompt = f"Spoilerfreie Zusammenfassung für Einstieg in '{show_name}' S{season}E{episode}: Wichtigste Plot-Points, Charaktere und Status quo nach vorherigen Folgen. Kurz (150 Wörter)."
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
