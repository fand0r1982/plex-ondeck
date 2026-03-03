import os
from fastapi import FastAPI, Request  # Request hinzugefügt!
from fastapi.responses import HTMLResponse  # Fix: Aus responses!
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from plexapi.server import PlexServer
from openai import OpenAI

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not plex:
        return HTMLResponse("<h1>Plex Token fehlt!</h1>")
    
    try:
        # FIX 1: Nur echte On-Deck (hat watched + unwatched)
        ondeck = plex.library.section('On Deck').items()[:20]  # Top 20 On-Deck!
        items = []
        for item in ondeck:
            if item.type == 'episode':
                show = item.show()
                items.append({
                    'title': show.title.replace(" ", "_").replace("'", "").replace(",", ""),  # Clean URL
                    'season': item.seasonNumber,
                    'episode': item.episodeNumber,
                    'ep_title': item.title,
                    'show_grandparent': show.title
                })
        return templates.TemplateResponse("index.html", {"request": request, "ondeck": items})
    except Exception as e:
        return HTMLResponse(f"<h1>Fehler: {str(e)}. Section 'On Deck'?<br>Plex Libraries checken.</h1>[file:127]")

@app.get("/summary/{title}/{season}/{episode}")
async def get_summary(title: str, season: int, episode: int):
    if not OPENAI_KEY:
        return {"error": "OpenAI Key fehlt"}
    
    client = OpenAI(api_key=OPENAI_KEY)
    # FIX 2: Bessere Summary mit prev Folgen
    show_name = title.replace("_", " ")
    prompt = f"Gib eine spoilerfreie Zusammenfassung der wichtigsten Ereignisse und Charaktere bis {show_name} S{season}E{episode}, damit ich direkt mit der nächsten Folge einsteigen kann. 200 Wörter max."
    
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return {"summary": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
