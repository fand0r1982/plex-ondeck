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
        
        # FIX: HARTE GRENZE – NUR watched Episoden bis episode-1
        prev_episodes = []
        for s in range(1, season + 1):
            season_obj = show.season(s)
            for ep in season_obj.episodes():
                # FIX: episodeNumber + STRICT watched-check + STOP bei aktueller
                if ep.isWatched and ep.seasonNumber < season:
                    prev_episodes.append(f"S{ep.seasonNumber}E{ep.episodeNumber}: {ep.title}")
                elif ep.isWatched and ep.seasonNumber == season and ep.episodeNumber < episode:
                    prev_episodes.append(f"S{ep.seasonNumber}E{ep.episodeNumber}: {ep.title}")
                elif ep.seasonNumber == season and ep.episodeNumber == episode:
                    break  # STOPP! Keine aktuelle Folge!
        
        watched_count = len(prev_episodes)
        recent_prev = prev_episodes[-10:]  # Nur 10 zuletzt
        context = f"{watched_count} Episoden gesehen. Letzte 10: {' | '.join(recent_prev)}"
        
        prompt = f"""PRÄZISE "MERKE-DIR!" für {show_name} – NUR BIS S{season}E{episode-1}!

Kontext (STRICT bis letzte GESEHENE):
{context}

**ABSOLUT KEIN SPOILER** für S{season}E{episode}! Nur Handlung bis {context[-1]}.

250-350 Wörter, DEUTSCH:
• **Handlung**: 3-4 aktuelle Plot-Points (konkret: wer? was? wie?)
• **Charaktere**: 5-7 Personen (Name + präziser Status)
• **Cliffhanger**: 3-5 offene Fragen

Bullet-Points, konkret!"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.4  # Präziser
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
