"""Aufbereitung des MOP-Zustands zu anzeigefertigen Daten (JSON)."""
from __future__ import annotations

import time

from .mop import (
    STATUS_DQ,
    STATUS_MAX,
    STATUS_MP,
    STATUS_DNF,
    STATUS_NO_TIMING,
    STATUS_OK,
    STATUS_OUT_OF_COMPETITION,
    STATUS_TEXT,
    STATUS_UNKNOWN,
    ClassInfo,
    Competitor,
    MopState,
    Team,
)

NEW_SECONDS = 45
# Status, die mit Statustext am Ende der Ergebnisliste erscheinen
TAIL_STATUSES = {STATUS_MP, STATUS_DNF, STATUS_DQ, STATUS_MAX, STATUS_NO_TIMING, STATUS_OUT_OF_COMPETITION}


def fmt_time(ds: int) -> str:
    if ds <= 0:
        return ""
    s = ds // 10
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_behind(ds: int) -> str:
    return "+" + fmt_time(ds) if ds > 0 else ""


def fmt_tod(ds: int) -> str:
    if ds < 0:
        return ""
    s = (ds // 10) % 86400
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}"


def live_elapsed(runner: Competitor) -> int:
    """Laufzeit seit dem Staffelwechsel in Zehntelsekunden, falls bekannt."""
    if runner.st < 0:
        return 0
    now = time.localtime()
    now_ds = (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec) * 10
    elapsed = now_ds - runner.st
    # Ein Rennen kann über Mitternacht laufen.
    if elapsed < 0:
        elapsed += 24 * 3600 * 10
    return elapsed


def _places(values: list[int]) -> list[int]:
    """Platzierungen für eine aufsteigend sortierte Liste (gleiche Zeit = gleicher Platz)."""
    places: list[int] = []
    for i, v in enumerate(values):
        places.append(places[-1] if i and values[i - 1] == v else i + 1)
    return places


def _rank(value: int, all_values: list[int]) -> int:
    return 1 + sum(1 for v in all_values if v < value)


def _is_new(c: Competitor, now: float) -> bool:
    return bool(c.finished_seen) and now - (c.finished_seen or 0) < NEW_SECONDS


def _org_name(state: MopState, org_id: int) -> str:
    org = state.orgs.get(org_id)
    return org.name if org else ""


def _control_name(state: MopState, ctrl_id: int) -> str:
    ctrl = state.controls.get(ctrl_id)
    return ctrl.name if ctrl and ctrl.name else str(ctrl_id)


def _is_team_class(state: MopState, cls_id: int) -> bool:
    return any(t.cls == cls_id for t in state.teams.values())


def classes_list(state: MopState) -> list[dict]:
    result = []
    for cls in sorted(state.classes.values(), key=lambda c: (c.order, c.name)):
        is_team = _is_team_class(state, cls.id)
        runners = [c for c in state.competitors.values() if c.cls == cls.id]
        finished = sum(1 for c in runners if c.stat == STATUS_OK and c.rt > 0)
        running = sum(1 for c in runners if c.stat == STATUS_UNKNOWN and (c.competing or c.radio))
        if is_team:
            teams = [t for t in state.teams.values() if t.cls == cls.id]
            entries = len(teams)
            finished = sum(1 for t in teams if t.stat == STATUS_OK and t.rt > 0)
            running = sum(
                1 for t in teams
                if t.stat == STATUS_UNKNOWN and any(
                    (r := state.competitors.get(rid)) and (r.competing or r.radio or r.rt > 0)
                    for leg in t.legs for rid in leg))
        else:
            entries = len(runners)
        result.append(
            {
                "id": cls.id,
                "name": cls.name,
                "type": "team" if is_team else "individual",
                "entries": entries,
                "finished": finished,
                "running": running,
                "active": finished + running > 0,
            }
        )
    return result


def class_results(state: MopState, cls_id: int) -> dict | None:
    cls = state.classes.get(cls_id)
    if cls is None:
        return None
    if _is_team_class(state, cls_id):
        return _team_results(state, cls)
    return _individual_results(state, cls)


def _individual_results(state: MopState, cls: ClassInfo) -> dict:
    now = time.time()
    radios = cls.radio[0] if cls.radio else []
    runners = [c for c in state.competitors.values() if c.cls == cls.id]

    split_times = {
        ctrl: [c.radio[ctrl] for c in runners if ctrl in c.radio and c.stat in (STATUS_UNKNOWN, STATUS_OK)]
        for ctrl in radios
    }
    best_split = {ctrl: min(v) for ctrl, v in split_times.items() if v}

    finished = sorted((c for c in runners if c.stat == STATUS_OK and c.rt > 0), key=lambda c: c.rt)
    running = [c for c in runners if c.stat == STATUS_UNKNOWN and (c.competing or c.radio)]
    tail = [c for c in runners if c.stat in TAIL_STATUSES]

    def progress(c: Competitor) -> tuple[int, int]:
        passed = [i for i, ctrl in enumerate(radios) if ctrl in c.radio]
        if not passed:
            return (0, c.st)
        last = passed[-1]
        return (-(last + 1), c.radio[radios[last]])

    running.sort(key=progress)
    tail.sort(key=lambda c: (c.stat, c.rt or 10**9))

    def splits(c: Competitor) -> list[dict]:
        out = []
        for ctrl in radios:
            t = c.radio.get(ctrl)
            if not t:
                out.append({"time": "", "rank": None, "best": False})
                continue
            valid = c.stat in (STATUS_UNKNOWN, STATUS_OK)
            rank = _rank(t, split_times[ctrl]) if valid else None
            out.append({"time": fmt_time(t), "rank": rank, "best": rank == 1})
        return out

    def base_row(c: Competitor) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "org": _org_name(state, c.org),
            "bib": c.bib,
            "splits": splits(c),
            "new": _is_new(c, now),
        }

    rows = []
    best = finished[0].rt if finished else 0
    for c, place in zip(finished, _places([c.rt for c in finished])):
        rows.append(base_row(c) | {
            "state": "finished",
            "place": place,
            "time": fmt_time(c.rt),
            "behind": fmt_behind(c.rt - best),
            "status": "",
            "prel": c.prel,
        })
    for provisional_place, c in enumerate(running, start=len(finished) + 1):
        last_ctrl = next((ctrl for ctrl in reversed(radios) if ctrl in c.radio), None)
        info = ""
        if last_ctrl is not None:
            t = c.radio[last_ctrl]
            behind = fmt_behind(t - best_split[last_ctrl]) if last_ctrl in best_split else ""
            info = f"{_control_name(state, last_ctrl)}: {behind or 'führt'}"
        rows.append(base_row(c) | {
            "state": "running",
            "place": None,
            "provisional_place": provisional_place,
            "time": "",
            "behind": "",
            "status": "im Wald",
            "info": info.strip(),
        })
    for c in tail:
        rows.append(base_row(c) | {
            "state": "other",
            "place": None,
            "time": fmt_time(c.rt) if c.stat in (STATUS_OUT_OF_COMPETITION, STATUS_MP) else "",
            "behind": "",
            "status": STATUS_TEXT.get(c.stat, ""),
        })

    return {
        "id": cls.id,
        "name": cls.name,
        "type": "individual",
        "length": cls.length,
        "controls": [{"id": ctrl, "name": _control_name(state, ctrl)} for ctrl in radios],
        "rows": rows,
        "counts": {"finished": len(finished), "running": len(running), "entries": len(runners)},
    }


def _team_results(state: MopState, cls: ClassInfo) -> dict:
    now = time.time()
    teams = [t for t in state.teams.values() if t.cls == cls.id]
    n_legs = max((len(t.legs) for t in teams), default=0)

    def leg_runner(t: Team, leg: int) -> Competitor | None:
        if leg >= len(t.legs):
            return None
        for rid in t.legs[leg]:
            if rid in state.competitors:
                return state.competitors[rid]
        return None

    # Strecken- und Zwischenplatzierung (Gesamtzeit nach Strecke) je Strecke
    leg_times: list[list[int]] = []
    cum_times: list[list[int]] = []
    for leg in range(n_legs):
        lt, ct = [], []
        for t in teams:
            r = leg_runner(t, leg)
            if r and r.stat == STATUS_OK and r.rt > 0:
                lt.append(r.rt)
                if r.tstat in (STATUS_OK, STATUS_UNKNOWN) or leg == 0:
                    ct.append(r.it + r.rt)
        leg_times.append(lt)
        cum_times.append(ct)

    def legs_info(t: Team) -> tuple[list[dict], int, int, str, int]:
        cells = []
        done = 0
        cum = 0
        info = ""
        live_total = 0
        for leg in range(n_legs):
            r = leg_runner(t, leg)
            if r is None:
                cells.append({"name": "", "time": "", "rank": None, "cum": "", "cum_rank": None, "state": "empty"})
                continue
            cell = {"name": r.name, "time": "", "rank": None, "cum": "", "cum_rank": None,
                    "state": "waiting", "new": _is_new(r, now)}
            if r.stat == STATUS_OK and r.rt > 0:
                c = r.it + r.rt
                cell.update(state="finished", time=fmt_time(r.rt), rank=_rank(r.rt, leg_times[leg]),
                            cum=fmt_time(c), cum_rank=_rank(c, cum_times[leg]) if c in cum_times[leg] else None)
                done = leg + 1
                cum = c
            elif r.stat in TAIL_STATUSES:
                cell.update(state="other", time=STATUS_TEXT.get(r.stat, ""))
            elif r.competing or r.radio:
                cell.update(state="running", time="läuft")
                radios = cls.radio[leg] if leg < len(cls.radio) else []
                last_ctrl = next((x for x in reversed(radios) if x in r.radio), None)
                if last_ctrl is not None:
                    live_total = r.it + r.radio[last_ctrl]
                    info = f"Str. {leg + 1} · {_control_name(state, last_ctrl)}"
                    cell["time"] = f"{_control_name(state, last_ctrl)} {fmt_time(r.radio[last_ctrl])}"
                elif not info:
                    live_total = r.it + live_elapsed(r)
                    info = f"Str. {leg + 1} läuft"
            cells.append(cell)
        return cells, done, cum, info, live_total

    finished, running, tail = [], [], []
    for t in teams:
        cells, done, cum, info, live_total = legs_info(t)
        entry = (t, cells, done, cum, info, live_total)
        final_runner = leg_runner(t, n_legs - 1)
        team_finished = (
            t.stat == STATUS_OK and t.rt > 0
        ) or (
            final_runner is not None
            and final_runner.stat == STATUS_OK
            and final_runner.rt > 0
        )
        if team_finished:
            finished.append(entry)
        elif t.stat in TAIL_STATUSES:
            tail.append(entry)
        elif t.stat == STATUS_UNKNOWN and any(c["state"] != "waiting" and c["state"] != "empty" for c in cells):
            running.append(entry)

    finished.sort(key=lambda e: e[0].rt or e[3])
    def live_key(entry: tuple[Team, list[dict], int, int, str, int]) -> tuple[int, int]:
        team, _cells, done, cum, _info, _live_total = entry
        for leg in range(len(team.legs) - 1, -1, -1):
            runner = leg_runner(team, leg)
            if runner is None or not (runner.competing or runner.radio):
                continue
            radios = cls.radio[leg] if leg < len(cls.radio) else []
            passed = [index for index, control in enumerate(radios) if control in runner.radio]
            if passed:
                last = passed[-1]
                return (-(leg * 1000 + last + 1), runner.it + runner.radio[radios[last]])
            return (-(leg * 1000), runner.it if runner.it > 0 else 10**12)
        return (-done * 1000, cum if cum > 0 else 10**12)

    running.sort(key=live_key)
    tail.sort(key=lambda e: e[0].stat)

    rows = []
    best = (finished[0][0].rt or finished[0][3]) if finished else 0
    for (t, cells, _done, cum, _info, _live_total), place in zip(finished, _places([e[0].rt or e[3] for e in finished])):
        total_time = t.rt or cum
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "finished", "place": place, "time": fmt_time(total_time),
                     "behind": fmt_behind(total_time - best), "status": "",
                     "new": any(c.get("new") for c in cells)})
    for provisional_place, (t, cells, done, cum, info, live_total) in enumerate(running, start=len(finished) + 1):
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "running", "place": None, "provisional_place": provisional_place,
                     "time": fmt_time(live_total), "behind": "",
                     "status": "unterwegs", "info": info,
                     "new": any(c.get("new") for c in cells)})
    for t, cells, *_ in tail:
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "other", "place": None, "time": "", "behind": "",
                     "status": STATUS_TEXT.get(t.stat, ""), "new": False})

    return {
        "id": cls.id,
        "name": cls.name,
        "type": "team",
        "length": cls.length,
        "legs": n_legs,
        "rows": rows,
        "counts": {"finished": len(finished), "running": len(running), "entries": len(teams)},
    }


def ticker(state: MopState, limit: int = 12) -> list[dict]:
    now = time.time()
    team_of: dict[int, tuple[Team, int]] = {}
    for t in state.teams.values():
        for leg, rids in enumerate(t.legs):
            for rid in rids:
                team_of[rid] = (t, leg)

    finishers = [c for c in state.competitors.values() if c.finished_seen is not None]
    finishers.sort(key=lambda c: (c.finished_seen or 0, c.finish_tod), reverse=True)
    finishers = finishers[:limit]

    place_cache: dict[int, dict[int, int]] = {}

    def place_of(c: Competitor) -> int | None:
        if c.stat != STATUS_OK:
            return None
        if c.cls not in place_cache:
            res = class_results(state, c.cls)
            place_cache[c.cls] = {
                r["id"]: r["place"] for r in (res["rows"] if res and res["type"] == "individual" else [])
                if r["place"]
            }
        return place_cache[c.cls].get(c.id)

    items = []
    for c in finishers:
        cls = state.classes.get(c.cls)
        team = team_of.get(c.id)
        items.append({
            "id": c.id,
            "name": c.name,
            "org": _org_name(state, c.org),
            "class": cls.name if cls else "",
            "time": fmt_time(c.rt),
            "finish": fmt_tod(c.finish_tod),
            "status": "" if c.stat == STATUS_OK else STATUS_TEXT.get(c.stat, ""),
            "place": None if team else place_of(c),
            "team": f"{team[0].name} · Str. {team[1] + 1}" if team else "",
            "new": _is_new(c, now),
        })
    return items


def _runner_controls(state: MopState, runner: Competitor) -> list[int]:
    """Liefert die Funkposten der Strecke eines Läufers."""
    cls = state.classes.get(runner.cls)
    if cls is None:
        return []
    for team in state.teams.values():
        if team.cls != runner.cls:
            continue
        for leg, runner_ids in enumerate(team.legs):
            if runner.id in runner_ids:
                route = cls.radio[leg] if leg < len(cls.radio) else []
                return list(dict.fromkeys([*route, *sorted(state.radio_controls)]))
    route = cls.radio[0] if cls.radio else []
    return list(dict.fromkeys([*route, *sorted(state.radio_controls)]))


def radio_controls(state: MopState, cls_id: int) -> dict | None:
    """Funkposten einer Klasse, einschließlich der Anzahl bereits erfolgter Durchgänge."""
    cls = state.classes.get(cls_id)
    if cls is None:
        return None
    controls = list(dict.fromkeys([
        *(ctrl for leg in cls.radio for ctrl in leg),
        *sorted(state.radio_controls),
    ]))
    runners = [c for c in state.competitors.values() if c.cls == cls_id]
    return {
        "id": cls.id,
        "name": cls.name,
        "controls": [
            {
                "id": ctrl,
                "name": _control_name(state, ctrl),
                "passed": sum(ctrl in c.radio for c in runners),
            }
            for ctrl in controls
        ],
    }


def class_runners(state: MopState, cls_id: int) -> list[dict] | None:
    if cls_id not in state.classes:
        return None
    return [
        {"id": c.id, "name": c.name, "org": _org_name(state, c.org)}
        for c in sorted(
            (c for c in state.competitors.values() if c.cls == cls_id),
            key=lambda c: (c.name.casefold(), c.id),
        )
    ]


def runner_profile(state: MopState, runner_id: int) -> dict | None:
    runner = state.competitors.get(runner_id)
    if runner is None:
        return None
    cls = state.classes.get(runner.cls)
    if cls is None:
        return None

    controls = _runner_controls(state, runner)
    class_runners = [c for c in state.competitors.values() if c.cls == runner.cls]
    control_times = {
        ctrl: sorted(c.radio[ctrl] for c in class_runners if ctrl in c.radio)
        for ctrl in controls
    }
    latest = next((ctrl for ctrl in reversed(controls) if ctrl in runner.radio), None)
    if runner.stat == STATUS_OK and runner.rt:
        status = "Im Ziel"
        state_name = "finished"
    elif runner.competing or runner.radio:
        status = "Unterwegs"
        state_name = "running"
    else:
        status = STATUS_TEXT.get(runner.stat, "Noch nicht gestartet") or "Noch nicht gestartet"
        state_name = "waiting"

    return {
        "id": runner.id,
        "name": runner.name,
        "org": _org_name(state, runner.org),
        "class": cls.name,
        "bib": runner.bib,
        "state": state_name,
        "status": status,
        "start": fmt_tod(runner.st),
        "time": fmt_time(runner.rt),
        "progress": {"passed": sum(ctrl in runner.radio for ctrl in controls), "total": len(controls)},
        "latest": _control_name(state, latest) if latest is not None else "–",
        "controls": [
            {
                "id": ctrl,
                "name": _control_name(state, ctrl),
                "passed": ctrl in runner.radio,
                "time": fmt_time(runner.radio[ctrl]) if ctrl in runner.radio else "",
                "rank": _rank(runner.radio[ctrl], control_times[ctrl]) if ctrl in runner.radio else None,
            }
            for ctrl in controls
        ],
    }


def radio_view(state: MopState, cls_id: int, ctrl_id: int) -> dict | None:
    """Alle Läufer einer Klasse für einen Funkposten, getrennt nach durch/offen."""
    controls_data = radio_controls(state, cls_id)
    if controls_data is None or ctrl_id not in {c["id"] for c in controls_data["controls"]}:
        return None
    cls = state.classes[cls_id]
    runners = [c for c in state.competitors.values() if c.cls == cls_id]
    passage_times = sorted(c.radio[ctrl_id] for c in runners if ctrl_id in c.radio)

    def row(c: Competitor) -> dict:
        route = _runner_controls(state, c)
        passed = ctrl_id in c.radio
        last = next((ctrl for ctrl in reversed(route) if ctrl in c.radio), None)
        if passed:
            status = "durch"
        elif c.competing or c.radio:
            status = "unterwegs"
        elif c.stat == STATUS_OK:
            status = "Ziel ohne Durchgang"
        else:
            status = STATUS_TEXT.get(c.stat, "wartet") or "wartet"
        return {
            "id": c.id,
            "name": c.name,
            "org": _org_name(state, c.org),
            "passed": passed,
            "time": fmt_time(c.radio[ctrl_id]) if passed else "",
            "rank": _rank(c.radio[ctrl_id], passage_times) if passed else None,
            "last": _control_name(state, last) if last is not None else "–",
            "progress": f"{sum(ctrl in c.radio for ctrl in route)}/{len(route)}",
            "status": status,
        }

    rows = [row(c) for c in runners]
    passed = sorted((r for r in rows if r["passed"]), key=lambda r: (r["rank"] or 9999, r["name"]))
    open_rows = sorted((r for r in rows if not r["passed"]), key=lambda r: (r["status"] != "unterwegs", r["name"]))
    return {
        "class": cls.name,
        "control": _control_name(state, ctrl_id),
        "total": len(rows),
        "passed": passed,
        "open": open_rows,
    }


def radio_lower_third(state: MopState, cls_id: int, ctrl_id: int, limit: int = 3) -> dict | None:
    """Kompakte Teamwertung für eine Kamera an einem Funkposten."""
    cls = state.classes.get(cls_id)
    if cls is None or not _is_team_class(state, cls_id):
        return None

    teams = [team for team in state.teams.values() if team.cls == cls_id]

    def next_leg(team: Team) -> int:
        """Erste noch nicht im Ziel befindliche Staffelstrecke."""
        for leg, runner_ids in enumerate(team.legs):
            runners = [state.competitors[rid] for rid in runner_ids if rid in state.competitors]
            if not runners or not any(runner.stat == STATUS_OK and runner.rt > 0 for runner in runners):
                return leg
        return max(0, len(team.legs) - 1)

    # Der Wechsel der Anzeige erfolgt am Ziel: Sobald eine Staffel ihre
    # vorherige Strecke beendet, zeigt der Funkposten die folgende Strecke.
    current_leg = max((next_leg(team) for team in teams), default=0)
    passages: list[dict] = []
    for team in teams:
        if current_leg >= len(team.legs):
            continue
        runner = next(
            (state.competitors[rid] for rid in team.legs[current_leg] if rid in state.competitors),
            None,
        )
        if runner is None or ctrl_id not in runner.radio:
            continue
        passages.append({
            "team": team.name,
            "org": _org_name(state, team.org),
            "runner": runner.name,
            "leg": current_leg + 1,
            "legs": len(team.legs),
            "time_ds": runner.it + runner.radio[ctrl_id],
            "seen": runner.radio_seen.get(ctrl_id, 0.0),
        })

    passages.sort(key=lambda item: item["time_ds"])
    best = passages[0]["time_ds"] if passages else 0
    for place, item in zip(_places([item["time_ds"] for item in passages]), passages):
        item["place"] = place
        item["time"] = fmt_time(item["time_ds"])
        item["behind"] = fmt_behind(item["time_ds"] - best)
        del item["time_ds"]

    fresh = [item for item in passages if item["seen"] > 0]
    latest = max(fresh, key=lambda item: item["seen"]) if fresh else None
    # Die Führung bleibt dauerhaft sichtbar. Darunter wandert ein dreizeiliges
    # Fenster ohne Obergrenze durch alle nachfolgenden Platzierungen (bei Platz
    # 60 also 58, 59, 60).
    return {
        "class": cls.name,
        "control": _control_name(state, ctrl_id),
        "leader": passages[:1],
        "standings": passages[1:][-limit:],
        "latest": latest,
    }


def head_to_head(state: MopState, runner_id: int, leader_count: int = 3) -> dict | None:
    """Vergleicht einen Einzelläufer mit den aktuell führenden seiner Klasse."""
    selected = state.competitors.get(runner_id)
    if selected is None:
        return None
    cls = state.classes.get(selected.cls)
    if cls is None or _is_team_class(state, cls.id):
        return None

    class_runners = [runner for runner in state.competitors.values() if runner.cls == cls.id]
    controls = [
        ctrl for ctrl in _runner_controls(state, selected)
        if any(ctrl in runner.radio for runner in class_runners)
    ]
    finished = sorted(
        (runner for runner in class_runners if runner.stat == STATUS_OK and runner.rt > 0),
        key=lambda runner: runner.rt,
    )
    finish_ranks = {runner.id: place for runner, place in zip(finished, _places([runner.rt for runner in finished]))}

    def live_sort_key(runner: Competitor) -> tuple[int, int, str]:
        passed = [ctrl for ctrl in controls if ctrl in runner.radio]
        last_time = runner.radio[passed[-1]] if passed else 10**12
        return (-len(passed), last_time, runner.name.casefold())

    # Offizielle Zieleinläufe haben Vorrang. Solange niemand im Ziel ist,
    # bestimmt der am weitesten fortgeschrittene Läufer die Live-Spitze.
    leaders = finished if finished else sorted(
        (runner for runner in class_runners if runner.competing or runner.radio),
        key=live_sort_key,
    )
    leader_positions = {runner.id: position for position, runner in enumerate(leaders, start=1)}
    compared = [selected, *(runner for runner in leaders if runner.id != selected.id)][:leader_count + 1]

    control_times = {
        ctrl: sorted(runner.radio[ctrl] for runner in class_runners if ctrl in runner.radio)
        for ctrl in controls
    }

    def runner_status(runner: Competitor) -> str:
        if runner.id in finish_ranks:
            return f"Im Ziel · Platz {finish_ranks[runner.id]}"
        passed = [ctrl for ctrl in controls if ctrl in runner.radio]
        if passed:
            ctrl = passed[-1]
            return f"Zuletzt {_control_name(state, ctrl)} · {fmt_time(runner.radio[ctrl])}"
        if runner.competing:
            return "Unterwegs"
        return STATUS_TEXT.get(runner.stat, "Noch nicht gestartet") or "Noch nicht gestartet"

    def athlete(runner: Competitor) -> dict:
        return {
            "id": runner.id,
            "name": runner.name,
            "org": _org_name(state, runner.org),
            "selected": runner.id == selected.id,
            "leader_position": leader_positions.get(runner.id),
            "status": runner_status(runner),
            "finish_time": fmt_time(runner.rt) if runner.id in finish_ranks else "",
            "finish_rank": finish_ranks.get(runner.id),
            "splits": [
                {
                    "time": fmt_time(runner.radio[ctrl]) if ctrl in runner.radio else "",
                    "rank": _rank(runner.radio[ctrl], control_times[ctrl]) if ctrl in runner.radio else None,
                    "behind": fmt_behind(runner.radio[ctrl] - control_times[ctrl][0]) if ctrl in runner.radio else "",
                }
                for ctrl in controls
            ],
        }

    return {
        "class": cls.name,
        "selected_name": selected.name,
        "controls": [{"id": ctrl, "name": _control_name(state, ctrl)} for ctrl in controls],
        "athletes": [athlete(runner) for runner in compared],
    }


def podium(state: MopState, cls_id: int) -> dict | None:
    """Die bestätigten Top 6 einer Klasse für die Sieger-Ansicht."""
    result = class_results(state, cls_id)
    if result is None:
        return None
    top_six = [
        row for row in result["rows"]
        if row["state"] == "finished" and row["place"] and row["place"] <= 6
    ]
    places = []
    for row in top_six:
        place = {
            "place": row["place"],
            "name": row["name"],
            "org": row["org"],
            "time": row["time"],
            "behind": row["behind"],
        }
        if result["type"] == "team":
            place["runners"] = [
                leg["name"] for leg in row["legs"] if leg["name"]
            ]
        places.append(place)

    return {
        "class": result["name"],
        "type": result["type"],
        "final": len(top_six) == 6,
        "places": places,
    }


def live_news(state: MopState, limit: int = 12) -> list[dict]:
    """Zieleinläufe und Funkposten-Durchgänge aller Klassen, neueste zuerst."""
    finish_ranks: dict[int, int] = {}
    radio_ranks: dict[tuple[int, int], int] = {}
    for cls in state.classes.values():
        # Bei Staffeln beziehen sich die Zeiten auf unterschiedliche Strecken.
        # Eine gemeinsame Rangliste der einzelnen Läufer wäre dort irreführend.
        if _is_team_class(state, cls.id):
            continue
        runners = [c for c in state.competitors.values() if c.cls == cls.id]
        finish_times = sorted(c.rt for c in runners if c.stat == STATUS_OK and c.rt > 0)
        for runner in runners:
            if runner.stat == STATUS_OK and runner.rt > 0:
                finish_ranks[runner.id] = _rank(runner.rt, finish_times)
        for ctrl in {ctrl for route in cls.radio for ctrl in route} | state.radio_controls:
            passage_times = sorted(
                c.radio[ctrl]
                for c in runners
                if ctrl in c.radio and c.stat in (STATUS_UNKNOWN, STATUS_OK)
            )
            for runner in runners:
                if ctrl in runner.radio and passage_times:
                    radio_ranks[runner.id, ctrl] = _rank(runner.radio[ctrl], passage_times)

    def highlight(rank: int | None, best_label: str) -> tuple[str, str]:
        if rank == 1:
            return "best", best_label
        if rank and rank <= 3:
            return "top3", f"TOP {rank}"
        return "", ""

    events: list[tuple[float, dict]] = []
    for runner in state.competitors.values():
        cls = state.classes.get(runner.cls)
        common = {
            "runner_id": runner.id,
            "name": runner.name,
            "org": _org_name(state, runner.org),
            "class": cls.name if cls else "",
        }
        if runner.finished_seen:
            rank = finish_ranks.get(runner.id)
            style, label = highlight(rank, "NEUE BESTZEIT")
            events.append((runner.finished_seen, common | {
                "kind": "finish",
                "title": "Im Ziel",
                "detail": fmt_time(runner.rt) if runner.rt else STATUS_TEXT.get(runner.stat, ""),
                "status": "",
                "rank": rank,
                "highlight": style,
                "highlight_label": label,
                "reported_at": time.strftime("%H:%M:%S", time.localtime(runner.finished_seen)),
            }))
        for ctrl, seen_at in runner.radio_seen.items():
            if seen_at:
                rank = radio_ranks.get((runner.id, ctrl))
                style, label = highlight(rank, "BESTZEIT AM FUNKPOSTEN")
                events.append((seen_at, common | {
                    "kind": "radio",
                    "title": f"Funkposten {_control_name(state, ctrl)}",
                    "detail": fmt_time(runner.radio.get(ctrl, 0)),
                    "status": "durch",
                    "rank": rank,
                    "highlight": style,
                    "highlight_label": label,
                    "reported_at": time.strftime("%H:%M:%S", time.localtime(seen_at)),
                }))
    events.sort(key=lambda event: event[0], reverse=True)
    return [event for _, event in events[:limit]]
