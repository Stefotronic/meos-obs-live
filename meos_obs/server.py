"""FastAPI-App: JSON-API, OBS-Overlay und Regie-Seite."""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import views
from .config import EventConfig
from .mop import MopState
from .poller import MeosPoller

STATIC = Path(__file__).parent / "static"


class DisplayConfig(BaseModel):
    mode: str = "auto"  # "auto" (Rotation) | "fixed" (feste Klasse)
    fixed_class: int | None = None
    rotate_classes: list[int] = []  # leer = alle aktiven Klassen
    page_seconds: int = 15
    show_ticker: bool = True
    ticker_count: int = 10
    hide_empty: bool = True
    skip_counter: int = 0


class DisplayUpdate(BaseModel):
    mode: str | None = None
    fixed_class: int | None = None
    rotate_classes: list[int] | None = None
    page_seconds: int | None = None
    show_ticker: bool | None = None
    ticker_count: int | None = None
    hide_empty: bool | None = None


class CurrentView(BaseModel):
    class_id: int | None = None
    class_name: str = ""
    page: int = 0
    pages: int = 0


class PodiumReveal(BaseModel):
    class_id: int
    place: int


class PodiumMode(BaseModel):
    class_id: int
    top: int


def create_app(
    meos_url: str,
    poll_interval: float = 2.0,
    demo: bool = False,
    demo_speed: float = 10.0,
    event_config: EventConfig | None = None,
) -> FastAPI:
    event_config = event_config or EventConfig()
    state = MopState()
    state.radio_controls = set(event_config.radio_controls)
    poller = MeosPoller(state, meos_url, interval=poll_interval)
    display = DisplayConfig()
    current: dict = {"view": CurrentView().model_dump(), "at": None}
    podium_reveals: dict[int, set[int]] = {}
    podium_limits: dict[int, int] = {}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(poller.run())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="MeOS → OBS", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    if demo:
        from .mock_meos import MockMeosServer, Simulation

        app.include_router(MockMeosServer(Simulation(speed=demo_speed)).router(), prefix="/mock")

    @app.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse("/control")

    @app.get("/overlay", include_in_schema=False)
    async def overlay():
        return FileResponse(STATIC / "overlay.html")

    @app.get("/runner", include_in_schema=False)
    async def runner_overlay():
        return FileResponse(STATIC / "runner.html")

    @app.get("/radio", include_in_schema=False)
    async def radio_overlay():
        return FileResponse(STATIC / "radio.html")

    @app.get("/camera-lower-third", include_in_schema=False)
    async def camera_lower_third_overlay():
        return FileResponse(STATIC / "camera-lower-third.html")

    @app.get("/news", include_in_schema=False)
    async def news_overlay():
        return FileResponse(STATIC / "news.html")

    @app.get("/head-to-head", include_in_schema=False)
    async def head_to_head_overlay():
        return FileResponse(STATIC / "head-to-head.html")

    @app.get("/podium", include_in_schema=False)
    async def podium_overlay():
        return FileResponse(STATIC / "podium.html")

    @app.get("/logo", include_in_schema=False)
    async def logo():
        if event_config.logo is None:
            raise HTTPException(404, "Kein Veranstaltungslogo konfiguriert")
        return FileResponse(event_config.logo)

    @app.get("/control", include_in_schema=False)
    async def control():
        return FileResponse(STATIC / "control.html")

    @app.get("/api/status")
    async def api_status():
        competition = {**state.competition, **event_config.metadata()}
        return {
            "meos": poller.status(),
            "competition": competition,
            "version": state.version,
            "counts": {
                "classes": len(state.classes),
                "competitors": len(state.competitors),
                "teams": len(state.teams),
            },
            "server_time": time.time(),
        }

    @app.get("/api/classes")
    async def api_classes():
        return views.classes_list(state)

    @app.get("/api/radio-controls")
    async def api_radio_controls():
        return [
            {"id": ctrl, "name": views._control_name(state, ctrl)}
            for ctrl in sorted(state.radio_controls)
        ]

    @app.get("/api/class/{cls_id}")
    async def api_class(cls_id: int):
        res = views.class_results(state, cls_id)
        if res is None:
            raise HTTPException(404, "Klasse nicht gefunden")
        return res

    @app.get("/api/class/{cls_id}/runners")
    async def api_class_runners(cls_id: int):
        res = views.class_runners(state, cls_id)
        if res is None:
            raise HTTPException(404, "Klasse nicht gefunden")
        return res

    @app.get("/api/class/{cls_id}/controls")
    async def api_class_controls(cls_id: int):
        res = views.radio_controls(state, cls_id)
        if res is None:
            raise HTTPException(404, "Klasse nicht gefunden")
        return res

    @app.get("/api/camera-lower-third/{cls_id}/{ctrl_id}")
    async def api_camera_lower_third(cls_id: int, ctrl_id: int):
        res = views.radio_lower_third(state, cls_id, ctrl_id)
        if res is None:
            raise HTTPException(404, "Staffelklasse oder Funkposten nicht gefunden")
        return res

    @app.get("/api/runner/{runner_id}")
    async def api_runner(runner_id: int):
        res = views.runner_profile(state, runner_id)
        if res is None:
            raise HTTPException(404, "Läufer nicht gefunden")
        return res

    @app.get("/api/radio/{cls_id}/{ctrl_id}")
    async def api_radio(cls_id: int, ctrl_id: int):
        res = views.radio_view(state, cls_id, ctrl_id)
        if res is None:
            raise HTTPException(404, "Funkposten oder Klasse nicht gefunden")
        return res

    @app.get("/api/head-to-head/{runner_id}")
    async def api_head_to_head(runner_id: int):
        res = views.head_to_head(state, runner_id)
        if res is None:
            raise HTTPException(404, "Läufer nicht gefunden oder keine Einzelklasse")
        return res

    @app.get("/api/podium/{cls_id}")
    async def api_podium(cls_id: int):
        res = views.podium(state, cls_id)
        if res is None:
            raise HTTPException(404, "Klasse nicht gefunden")
        res["revealed"] = sorted(podium_reveals.get(cls_id, set()))
        res["top_limit"] = podium_limits.get(cls_id, 6)
        return res

    @app.get("/api/podium/mode/{cls_id}")
    async def get_podium_mode(cls_id: int):
        if cls_id not in state.classes:
            raise HTTPException(404, "Klasse nicht gefunden")
        return {"class_id": cls_id, "top": podium_limits.get(cls_id, 6)}

    @app.post("/api/podium/mode")
    async def set_podium_mode(mode: PodiumMode):
        if mode.class_id not in state.classes:
            raise HTTPException(404, "Klasse nicht gefunden")
        if mode.top not in (3, 6):
            raise HTTPException(400, "top muss 3 oder 6 sein")
        podium_limits[mode.class_id] = mode.top
        return {"class_id": mode.class_id, "top": mode.top}

    @app.post("/api/podium/reveal")
    async def reveal_podium(reveal: PodiumReveal):
        if reveal.class_id not in state.classes:
            raise HTTPException(404, "Klasse nicht gefunden")
        if reveal.place not in range(1, 7):
            raise HTTPException(400, "place muss zwischen 1 und 6 sein")
        podium_reveals.setdefault(reveal.class_id, set()).add(reveal.place)
        return {"class_id": reveal.class_id, "revealed": sorted(podium_reveals[reveal.class_id])}

    @app.post("/api/podium/reset/{cls_id}")
    async def reset_podium(cls_id: int):
        if cls_id not in state.classes:
            raise HTTPException(404, "Klasse nicht gefunden")
        podium_reveals.pop(cls_id, None)
        return {"class_id": cls_id, "revealed": []}

    @app.get("/api/ticker")
    async def api_ticker(limit: int = 12):
        return views.ticker(state, max(1, min(limit, 50)))

    @app.get("/api/news")
    async def api_news(limit: int = 12):
        return views.live_news(state, max(1, min(limit, 50)))

    @app.get("/api/display")
    async def get_display():
        return {"config": display.model_dump(), "current": current}

    @app.post("/api/display")
    async def set_display(update: DisplayUpdate):
        nonlocal display
        data = update.model_dump(exclude_unset=True)
        if "mode" in data and data["mode"] not in ("auto", "fixed"):
            raise HTTPException(400, "mode muss 'auto' oder 'fixed' sein")
        if "page_seconds" in data:
            data["page_seconds"] = max(3, min(int(data["page_seconds"]), 300))
        if "ticker_count" in data:
            data["ticker_count"] = max(1, min(int(data["ticker_count"]), 30))
        display = display.model_copy(update=data)
        return display.model_dump()

    @app.post("/api/display/skip")
    async def skip():
        display.skip_counter += 1
        return display.model_dump()

    @app.post("/api/display/current")
    async def set_current(view: CurrentView):
        current["view"] = view.model_dump()
        current["at"] = time.time()
        return {"ok": True}

    return app
