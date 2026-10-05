"""Simulierter MeOS-Informationsserver zum Testen ohne echtes MeOS.

Bildet ``/meos?difference=zero|<id>`` inkl. MOPComplete/MOPDiff nach und
simuliert einen Wettkampf (Einzelklassen mit Funkposten + eine Staffel)
im Zeitraffer.

Standalone:  python -m meos_obs.mock_meos --port 2009 --speed 10
"""
from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import PlainTextResponse, Response

FIRST = ["Anna", "Lena", "Marie", "Sophie", "Laura", "Julia", "Hannah", "Lea", "Clara", "Emma", "Paula", "Johanna",
         "Lukas", "Jonas", "Felix", "Paul", "Maximilian", "Leon", "Tim", "Moritz", "Jakob", "Simon", "Niklas", "Ben",
         "Elias", "David", "Tobias", "Florian", "Sebastian", "Matthias"]
LAST = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
        "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
        "Hofmann", "Hartmann", "Lange", "Schmitt", "Werner", "Krause", "Meier", "Lehmann", "Huber", "Kaiser"]
CLUBS = ["OLV Waldläufer", "TSV Kompass", "SG Orientierung Nord", "OL Team Süd", "SV Fuchsberg",
         "OLG Bergland", "TuS Postenjäger", "OC Mittelwald"]

# (id, name, Anzahl, Sollzeit in Minuten, Funkposten)
INDIVIDUAL = [
    (1, "H21", 14, 50, [31, 45, 62]),
    (2, "D21", 12, 45, [31, 50]),
    (3, "H45", 10, 48, [45, 62]),
    (4, "D16", 8, 35, [50]),
    (5, "Offen kurz", 10, 25, []),
]
RELAY_CLASS = (10, "Staffel", 3, 22, [[71], [72, 73], [74]])
CONTROLS = {31: "31", 45: "45", 50: "50", 62: "62", 71: "S1-71", 72: "S2-72", 73: "S2-73", 74: "S3-74"}

M = 600  # eine Minute in Zehntelsekunden


@dataclass
class SimRunner:
    id: int
    name: str
    org: int
    cls: int
    card: int
    st: int
    rt: int
    splits: list[tuple[int, int]]
    outcome: str  # ok | mp | dnf | dns
    readout: int
    team: int = 0
    leg: int = 0
    it: int = 0


@dataclass
class SimTeam:
    id: int
    name: str
    org: int
    cls: int
    st: int
    runners: list[SimRunner] = field(default_factory=list)


class Simulation:
    def __init__(self, speed: float = 10.0, seed: int = 42, lead_minutes: float = 2.0) -> None:
        self.speed = speed
        self.rng = random.Random(seed)
        self.zero = 10 * 3600 * 10
        self.sim0 = int(self.zero - lead_minutes * M)
        self.real0 = time.monotonic()
        self.runners: list[SimRunner] = []
        self.teams: list[SimTeam] = []
        self._build()

    def now(self) -> int:
        return self.sim0 + int((time.monotonic() - self.real0) * 10 * self.speed)

    def _name(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def _splits(self, radios: list[int], rt: int) -> list[tuple[int, int]]:
        n = len(radios)
        out = []
        for i, ctrl in enumerate(radios):
            frac = (i + 1) / (n + 1) + self.rng.uniform(-0.05, 0.05)
            out.append((ctrl, int(rt * frac)))
        return out

    def _outcome(self) -> str:
        r = self.rng.random()
        return "ok" if r < 0.80 else "mp" if r < 0.87 else "dnf" if r < 0.93 else "dns"

    def _build(self) -> None:
        rid = 1
        for offset, (cid, _name, count, minutes, radios) in enumerate(INDIVIDUAL):
            for k in range(count):
                st = self.zero + k * 2 * M + offset * 20 * 10
                rt = int(minutes * M * self.rng.uniform(0.85, 1.5))
                self.runners.append(SimRunner(
                    id=rid, name=self._name(), org=self.rng.randrange(len(CLUBS)) + 1, cls=cid,
                    card=8000000 + rid, st=st, rt=rt, splits=self._splits(radios, rt),
                    outcome=self._outcome(), readout=self.rng.randint(20, 150) * 10))
                rid += 1

        cid, _name, legs, minutes, radios = RELAY_CLASS
        rid = 1000
        for tid in range(1, 9):
            org = (tid - 1) % len(CLUBS) + 1
            team = SimTeam(id=tid, name=f"{CLUBS[org - 1]} {1 + (tid - 1) // len(CLUBS)}", org=org,
                           cls=cid, st=self.zero + 15 * M)
            leg_start = team.st
            cum = 0
            for leg in range(legs):
                rt = int(minutes * M * self.rng.uniform(0.85, 1.4))
                outcome = "mp" if (tid == 6 and leg == 1) else "ok"
                r = SimRunner(id=rid, name=self._name(), org=org, cls=cid, card=9000000 + rid, st=leg_start, rt=rt,
                              splits=self._splits(radios[leg], rt), outcome=outcome,
                              readout=self.rng.randint(20, 90) * 10, team=tid, leg=leg, it=cum)
                team.runners.append(r)
                leg_start += rt
                cum += rt
                rid += 1
            self.teams.append(team)

    # --- Zustand eines Läufers zum Zeitpunkt t -------------------------------------------
    def runner_state(self, r: SimRunner, t: int) -> dict:
        st = r.st
        if r.team:
            team = next(x for x in self.teams if x.id == r.team)
            prev = team.runners[: r.leg]
            if prev and t < prev[-1].st + prev[-1].rt:
                st = -1  # Startzeit erst nach Wechsel bekannt
        state = {"st": st, "rt": 0, "stat": 0, "competing": False, "radio": [], "it": r.it,
                 "tstat": 1 if r.leg == 0 else 0}
        if r.team and r.leg > 0:
            team = next(x for x in self.teams if x.id == r.team)
            prev_done = all(t >= p.st + p.rt for p in team.runners[: r.leg])
            state["tstat"] = 1 if prev_done else 0
            if any(p.outcome == "mp" and t >= p.st + p.rt for p in team.runners[: r.leg]):
                state["tstat"] = 3
        if st < 0 or t < r.st:
            return state
        if r.outcome == "dns":
            if t >= r.st + 10 * M:
                state["stat"] = 20
            return state

        finish = r.st + r.rt
        if r.outcome == "dnf":
            passed = r.splits[: len(r.splits) // 2]
            state["radio"] = [(c, s) for c, s in passed if t >= r.st + s]
            if t >= r.st + int(r.rt * 1.2):
                state["stat"] = 4
            else:
                state["competing"] = True
            return state

        state["radio"] = [(c, s) for c, s in r.splits if t >= r.st + s]
        delay = 0 if r.team else r.readout
        if t >= finish + delay:
            state["stat"] = 1 if r.outcome == "ok" else 3
            state["rt"] = r.rt
        else:
            state["competing"] = True
        return state

    def team_state(self, team: SimTeam, t: int) -> dict:
        last = team.runners[-1]
        done = t >= last.st + last.rt
        mp = any(r.outcome == "mp" for r in team.runners)
        total = sum(r.rt for r in team.runners)
        return {"st": team.st, "rt": total if done else 0, "stat": (3 if mp else 1) if done else 0}

    # --- XML-Snapshot ---------------------------------------------------------------------
    def snapshot(self) -> dict[str, dict]:
        t = self.now()
        snap: dict[str, dict] = {}

        def el(tag: str, attrs: dict, text: str = "") -> str:
            a = "".join(f' {k}="{escape(str(v), {chr(34): "&quot;"})}"' for k, v in attrs.items())
            return f"<{tag}{a}>{escape(text)}</{tag}>"

        snap["competition"] = {"full": el("competition", {"date": "2026-10-03", "organizer": "Demo-Verein",
                                                          "homepage": "", "zerotime": "10:00:00"},
                                          "MeOS-Demo (Simulation)")}
        for cid, name in CONTROLS.items():
            snap[f"ctrl:{cid}"] = {"full": el("ctrl", {"id": cid}, name)}
        for i, (cid, name, _n, minutes, radios) in enumerate(INDIVIDUAL):
            snap[f"cls:{cid}"] = {"full": el("cls", {"id": cid, "ord": (i + 1) * 10,
                                                     "radio": ",".join(map(str, radios)),
                                                     "len": int(minutes * 120)}, name)}
        rc = RELAY_CLASS
        snap[f"cls:{rc[0]}"] = {"full": el("cls", {"id": rc[0], "ord": 100,
                                                   "radio": ";".join(",".join(map(str, x)) for x in rc[4])}, rc[1])}
        for oid, name in enumerate(CLUBS, start=1):
            snap[f"org:{oid}"] = {"full": el("org", {"id": oid, "nat": "GER"}, name)}

        for team in self.teams:
            s = self.team_state(team, t)
            base = el("base", {"org": team.org, "cls": team.cls, "stat": s["stat"], "st": s["st"], "rt": s["rt"],
                               "bib": team.id}, team.name)
            r = el("r", {}, ";".join(str(x.id) for x in team.runners))
            snap[f"tm:{team.id}"] = {"full": f'<tm id="{team.id}">{base}{r}</tm>'}

        all_runners = self.runners + [r for tm in self.teams for r in tm.runners]
        for r in all_runners:
            s = self.runner_state(r, t)
            base = el("base", {"org": r.org, "cls": r.cls, "stat": s["stat"], "st": s["st"], "rt": s["rt"]}, r.name)
            radio = el("radio", {}, ";".join(f"{c},{v}" for c, v in s["radio"])) if s["radio"] else ""
            inp = f'<input it="{s["it"]}" tstat="{s["tstat"]}"/>'
            snap[f"cmp:{r.id}"] = {"id": r.id, "card": r.card, "competing": s["competing"],
                                   "base": base, "radio": radio, "input": inp}
        return snap

    @staticmethod
    def _cmp_xml(p: dict, prev: dict | None) -> str:
        """Wie MeOS: im Diff card/radio/input nur bei Änderung."""
        attrs = f' id="{p["id"]}"'
        if prev is None or prev["card"] != p["card"]:
            attrs += f' card="{p["card"]}"'
        if p["competing"]:
            attrs += ' competing="true"'
        body = p["base"]
        if p["radio"] and (prev is None or prev["radio"] != p["radio"]):
            body += p["radio"]
        if prev is None or prev["input"] != p["input"]:
            body += p["input"]
        return f"<cmp{attrs}>{body}</cmp>"

    @staticmethod
    def render(snap: dict[str, dict], prev: dict[str, dict] | None) -> str:
        parts = []
        if prev is not None:
            for key in prev.keys() - snap.keys():
                tag, ident = key.split(":", 1)
                parts.append(f'<{tag} id="{ident}" delete="true"/>')
        for key, val in snap.items():
            old = prev.get(key) if prev is not None else None
            if prev is not None and old == val:
                continue
            if key.startswith("cmp:"):
                parts.append(Simulation._cmp_xml(val, old))
            else:
                parts.append(val["full"])
        return "".join(parts)


class MockMeosServer:
    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.history: dict[int, dict] = {}
        self.next_id = 1

    def difference(self, what: str) -> str:
        snap = self.sim.snapshot()
        if what == "zero":
            prev = None
        else:
            try:
                prev = self.history[int(what)]
            except (ValueError, KeyError):
                return ("Error (MeOS): Unknown difference state. Use litteral 'zero' "
                        "(?difference=zero) to get complete competition")
        nid = self.next_id
        self.next_id += 1
        self.history[nid] = snap
        for old in [k for k in self.history if k < nid - 200]:
            del self.history[old]
        tag = "MOPComplete" if prev is None else "MOPDiff"
        body = Simulation.render(snap, prev)
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<{tag} xmlns="http://www.melin.nu/mop" nextdifference="{nid}">{body}</{tag}>')

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/meos")
        async def meos(request: Request) -> Response:
            q = request.query_params
            if "difference" in q:
                text = self.difference(q["difference"])
                if text.startswith("Error"):
                    return PlainTextResponse(text)
                return Response(text.encode("utf-8"), media_type="application/xml")
            if q.get("get") == "status":
                xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<MOPComplete xmlns="http://www.melin.nu/mop">'
                       '<status version="mock" eventNameId="demo" onDatabase="0" eventId="1"/></MOPComplete>')
                return Response(xml.encode("utf-8"), media_type="application/xml")
            return PlainTextResponse("Error (MeOS): Unknown request")

        return router


def create_mock_app(speed: float = 10.0, seed: int = 42) -> FastAPI:
    app = FastAPI(title="MeOS-Mock")
    app.include_router(MockMeosServer(Simulation(speed=speed, seed=seed)).router())
    return app


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="Simulierter MeOS-Informationsserver")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2009)
    p.add_argument("--speed", type=float, default=10.0, help="Zeitraffer-Faktor (Standard 10)")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    print(f"MeOS-Mock: http://{a.host}:{a.port}/meos?difference=zero")
    uvicorn.run(create_mock_app(a.speed, a.seed), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
