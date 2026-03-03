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
        prev_episodes = []
        last_seen_episode = episode - 1
        
        # GENAU wie vorher: Detaillierte prev + Ep-Summaries, aber STRICT bis last_seen
        for s in range(1, season + 1):
            season_obj = show.season(s)
            for ep in season_obj.episodes():
                if ep.isWatched:
                    ep_info = f"S{s}E{ep.episodeNumber}: '{ep.title}'"
                    if ep.summary:
                        ep_info += f" – {ep.summary[:120]}..."
                    prev_episodes.append(ep_info)
                elif ep.seasonNumber == season and ep.episodeNumber == last_seen_episode + 1:
                    break  # HARTER STOP vor neuer Folge
                
        recent_prev = prev_episodes[-12:]
        total_seen = len(prev_episodes)
        full_context = f"Gesamt {total_seen} Episoden gesehen. Letzte: {' | '.join(recent_prev)}"
        
        prompt = f"""DETAILLIERTE "Was bisher geschah?" für {show_name} bis S{season}E{last_seen_episode}.

Vorangegangene Folgen (alle gesehen):
{full_context}

**WICHTIG: KEINE Infos zur S{season}E{episode}! Nur bis letzte gesehen.**

Struktur (DEUTSCH, 400-600 Wörter):
1. **Letzte Episoden-Highlights** (300-400 Wörter) 
2. **Charakter-Status** (Bullet-Points)
3. **Offene Fragen** (3-5 Punkte)

Immersiv für Einstieg."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.7
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
