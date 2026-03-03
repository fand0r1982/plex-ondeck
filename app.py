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
        prev_episodes = []
        last_seen_season = season
        last_seen_episode = episode - 1  # Letzte *gesehene* vor der neuen
        
        # Sammle ALLE watched Episoden bis zur letzten gesehenen
        for s in range(1, last_seen_season + 1):
            season_obj = show.season(s)
            for ep in season_obj.episodes():
                if ep.isWatched and (s < last_seen_season or ep.episodeNumber <= last_seen_episode):
                    ep_info = f"S{s}E{ep.episodeNumber}: '{ep.title}'"
                    if ep.summary:
                        ep_info += f" ({ep.summary[:120]})"
                    prev_episodes.append(ep_info)
        
        # Komprimierter Kontext: Letzte 15 Episoden + Gesamtzahl
        recent_prev = prev_episodes[-15:]
        total_seen = len(prev_episodes)
        full_context = f"Gesamt {total_seen} Episoden gesehen. Letzte: {' | '.join(recent_prev)}"
        
        prompt = f"""FOLGENÜBERGREIFENDE "Was bisher geschah?" für {show_name} – AKTUELLER STAND nach EXAKT den gesehenen Folgen bis S{season}E{last_seen_episode}.

Kontext (ALLE gesehenen Episoden):
{full_context}

**WICHTIG:**
- KEINE Infos zur anstehenden S{season}E{episode}! Nur bis letzte gesehen.
- Synthetisiere GESAMT-handlung über ALLE Staffeln/Folgen hinweg.
- Fokussiere aktuellen Plot-Status, nicht chronologische Recap pro Folge.

Struktur (DEUTSCH, 500-800 Wörter):
1. **Gesamt-Handlungsstand** (detailliert: Hauptstränge, wie sie sich entwickelt haben)
2. **Charaktere – Aktueller Status** (Bullet-Points: Entwicklung, Beziehungen, Ziele, Geheimnisse)
3. **Offene Fragen/Cliffhanger** (5-8 Punkte aus letzten Episoden)
4. **Themen/Motivationen** (kurz)

Immersiv, spoilerfrei für nächste Folge, aber tiefgehend für perfekten Einstieg."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.6
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
