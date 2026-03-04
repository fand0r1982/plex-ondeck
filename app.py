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
        
        # DETALLIERTE letzte 8 Episoden (FULL summaries!)
        for s in range(season - 1 if season > 1 else 1, season + 1):
            if s > len(show.seasons()): break
            season_obj = show.season(s)
            eps_shown = 0
            for ep in season_obj.episodes():
                if ep.isWatched and eps_shown < 8:
                    ep_info = f"S{s}E{ep.episodeNumber}: {ep.title}"
                    if ep.summary:
                        ep_info += f" | SUMMARY: {ep.summary}"  # FULL Ep-Summary!
                    prev_episodes.append(ep_info)
                    eps_shown += 1
                if ep.seasonNumber == season and ep.episodeNumber == episode:
                    break
        
        context = "\n".join(prev_episodes)
        
        prompt = f"""DETAILLIERTE ERINNERUNGSSTÜTZE für {show_name} S{season}E{episode} – WAS WEIßT DU AUS DEN LETZTEN EPISODEN?

**EXAKTER, detaillierter Kontext** (letzte 3 GESEHENE Episoden, bis S{season}E{last_seen_episode}):
{context}

**ERZEUGE** (DEUTSCH, 350-500 Wörter):
- **Spezifische Ereignisse**: Was sind die 5-10 wichtigsten,konkreten Geschehnisse der letzten 3 Episoden, die man benötigt, um die kommende Episode zu verstehen?
- **Erinnerungspunkte**: Woran genau sollte man sich erinnern? (Bullet-Points mit Details)
- **Status Quo**: Aktuelle Situation aller Hauptfiguren nach letzter Episode

**WICHTIGST**: 
- VOLLE SPOILER der gesehenen Episoden OK
- ABSOLUT KEIN SPOILER für S{season}E{episode}
- Konkret & detailreich: Namen, Orte, Dialog-Referenzen, Twist-Aufzählung"""

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=1000,
        )
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
