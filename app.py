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
        show = plex.library.section('TV Shows').get(show_name)
        last_seen_season = season
        last_seen_episode = episode - 1
        
        # Kontext: Anzahl + letzte 8 Episoden
        watched_count = sum(1 for s in show.seasons() for ep in s.episodes() if ep.isWatched and (s.index < last_seen_season or (s.index == last_seen_season and ep.index <= last_seen_episode)))
        recent_eps = []
        for s in range(max(1, last_seen_season-1), last_seen_season + 1):
            season_obj = show.season(s)
            for ep in sorted(season_obj.episodes()[:last_seen_episode+1 if s == last_seen_season else None], key=lambda e: e.index, reverse=True)[:4]:
                if ep.isWatched:
                    recent_eps.append(f"S{s}E{ep.index}: {ep.title}{' – ' + ep.summary[:80] if ep.summary else ''}")
        
        context = f"{watched_count} Episoden gesehen. Letzte: {' | '.join(recent_eps)}"
        
        prompt = f"""PRÄZISE "MERKE-DIR!" für {show_name} – ERINNERUNG für S{season}E{episode}?

Kontext (bis S{season}E{last_seen_episode}):
{context}

**PRÄZISE Details** (250-350 Wörter):
- **Handlung**: 3-4 konkrete, aktuelle Plot-Points (wer hat was gemacht? Welche Enthüllungen?)
- **Charaktere**: 5-7 Schlüsselpersonen (Name + 1 präziser Status/Satz)
- **Cliffhanger**: 3-5 spezifische offene Fragen (nicht vage!)

DEUTSCH. Bullet-Points. Konkret & handlungsrelevant. KEIN SPOILER!"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
