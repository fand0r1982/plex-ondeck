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
async def index(request: Request):
    if not plex:
        return HTMLResponse("<h1>Plex Token fehlt!</h1>")
    
    try:
        # On-Deck Items (TV-Fokus)
        ondeck_items = plex.library.onDeck()
        tv_ondeck = [item for item in ondeck_items if item.type == 'episode'][:15]
        items = []
        for item in tv_ondeck:
            show = item.show()
            items.append({
                'title': show.title.replace(" ", "_").replace("'", "").replace(",", "").replace("&", ""),
                'show_title': show.title,
                'season': item.seasonNumber,
                'episode': item.episodeNumber,
                'ep_title': item.title
            })
        return templates.TemplateResponse("index.html", {"request": request, "ondeck": items})
    except Exception as e:
        return HTMLResponse(f"<h1>Fehler: {str(e)}</h1>")

@app.get("/summary/{title}/{season}/{episode}")
async def get_summary(title: str, season: int, episode: int):
    if not OPENAI_KEY:
        return {"error": "OpenAI Key fehlt"}
    
    client = OpenAI(api_key=OPENAI_KEY)
    show_name = title.replace("_", " ")
    try:
        # Hole watched prev Episodes für Kontext
        show = plex.library.section('TV Shows').get(show_name)
        prev_episodes = []
        for s in range(1, season + 1):
            season_eps = show.season(s).episodes()
            for ep in season_eps:
                if ep.isWatched:
                    prev_episodes.append(f"S{s}E{ep.episodeNumber}: {ep.title}")
                elif ep.seasonNumber == season and ep.episodeNumber == episode:
                    break
        
        prev_summary = "; ".join(prev_episodes[-8:])  # Letzte 8 für Token-Limit
        prompt = f"""'Was bisher geschah?' für {show_name} bis S{season}E{episode}:
Vorherige Folgen: {prev_summary}
Spoilerfreie Zusammenfassung: Wichtigste Plot-Entwicklungen, Charaktere, offene Fragen & Status quo.
Für Einstieg in nächste Folge. 150-250 Wörter. Deutsch."""
        
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
