from pathlib import Path

from meos_obs.config import load_event_config
from meos_obs import views
from meos_obs.mock_meos import MockMeosServer, Simulation
from meos_obs.mop import ClassInfo, Competitor, MopState, Team, STATUS_OK

COMPLETE = """<?xml version="1.0" encoding="UTF-8"?>
<MOPComplete xmlns="http://www.melin.nu/mop" nextdifference="7">
<competition date="2026-10-03" organizer="X" homepage="" zerotime="10:00:00">Test-OL</competition>
<ctrl id="31">31</ctrl><ctrl id="45">45</ctrl>
<cls id="1" ord="10" radio="31,45" len="5200">H21</cls>
<org id="1">OLV Süd</org>
<cmp id="1" card="123"><base org="1" cls="1" stat="1" st="360000" rt="30000">Anna A</base>
  <radio>31,9000;45,20000</radio><input it="0" tstat="1"/></cmp>
<cmp id="2" card="124" competing="true"><base org="1" cls="1" stat="0" st="361200" rt="0">Ben B</base>
  <radio>31,8000</radio><input it="0" tstat="1"/></cmp>
</MOPComplete>"""

DIFF = """<MOPDiff xmlns="http://www.melin.nu/mop" nextdifference="8">
<cmp id="1" delete="true"/>
<cmp id="2"><base org="1" cls="1" stat="1" st="361200" rt="28000">Ben B</base></cmp>
</MOPDiff>"""


def test_event_config(tmp_path: Path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"logo")
    config_file = tmp_path / "event.yaml"
    config_file.write_text("""event:
  name: Example Event
  short_name: Example
  organizer: Example Club
  logo: logo.png
  radio_controls: [31, 45, 31]
""", encoding="utf-8")

    config = load_event_config(config_file)
    assert config.metadata() == {
        "name": "Example Event",
        "short_name": "Example",
        "organizer": "Example Club",
    }
    assert config.logo == logo.resolve()
    assert config.radio_controls == (31, 45)


def test_complete_and_diff():
    s = MopState()
    assert s.apply(COMPLETE) == "7"
    assert s.competition["name"] == "Test-OL"
    assert s.classes[1].radio == [[31, 45]]
    assert s.competitors[1].radio == {31: 9000, 45: 20000}

    res = views.class_results(s, 1)
    assert [r["name"] for r in res["rows"]] == ["Anna A", "Ben B"]
    assert res["rows"][1]["state"] == "running"
    assert res["rows"][1]["splits"][0]["rank"] == 1  # 8000 < 9000

    assert s.apply(DIFF) == "8"
    assert 1 not in s.competitors
    ben = s.competitors[2]
    assert ben.stat == 1 and ben.rt == 28000
    assert ben.radio == {31: 8000}  # radio fehlt im Diff -> bleibt erhalten
    assert ben.card == 124
    assert not ben.competing
    assert ben.finished_seen and ben.finished_seen > 0  # neu im Ziel

    res = views.class_results(s, 1)
    assert res["rows"][0]["place"] == 1 and res["rows"][0]["time"] == "46:40"
    assert views.ticker(s)[0]["name"] == "Ben B"
    news = views.live_news(s)
    assert news[0]["kind"] == "finish"
    assert news[0]["name"] == "Ben B"
    assert news[0]["rank"] == 1
    assert news[0]["highlight"] == "best"
    assert news[0]["highlight_label"] == "NEUE BESTZEIT"


def test_runner_and_radio_views():
    state = MopState()
    state.apply(COMPLETE)

    controls = views.radio_controls(state, 1)
    assert controls is not None
    assert controls["controls"] == [
        {"id": 31, "name": "31", "passed": 2},
        {"id": 45, "name": "45", "passed": 1},
    ]
    assert [runner["name"] for runner in views.class_runners(state, 1) or []] == ["Anna A", "Ben B"]

    profile = views.runner_profile(state, 2)
    assert profile is not None
    assert profile["state"] == "running"
    assert profile["progress"] == {"passed": 1, "total": 2}
    assert profile["controls"][0]["rank"] == 1
    assert not profile["controls"][1]["passed"]

    radio = views.radio_view(state, 1, 45)
    assert radio is not None
    assert [runner["name"] for runner in radio["passed"]] == ["Anna A"]
    assert radio["open"][0]["name"] == "Ben B"

    state.radio_controls = {41, 55}
    state.classes[1].radio = []
    fallback_controls = views.radio_controls(state, 1)
    assert fallback_controls is not None
    assert [control["id"] for control in fallback_controls["controls"]] == [41, 55]

    state.classes[1].radio = [[31]]
    merged_controls = views.radio_controls(state, 1)
    assert merged_controls is not None
    assert [control["id"] for control in merged_controls["controls"]] == [31, 41, 55]

    h2h = views.head_to_head(state, 2)
    assert h2h is not None
    assert h2h["class"] == "H21"
    assert [athlete["name"] for athlete in h2h["athletes"]] == ["Ben B", "Anna A"]
    assert h2h["athletes"][0]["selected"]
    assert h2h["athletes"][1]["finish_rank"] == 1

    winners = views.podium(state, 1)
    assert winners is not None
    assert winners["class"] == "H21"
    assert winners["places"] == [{
        "place": 1, "name": "Anna A", "org": "OLV Süd", "time": "50:00", "behind": "",
    }]
    assert not winners["final"]


def _as_dict(state: MopState):
    def strip(o):
        d = dict(vars(o))
        d.pop("finished_seen", None)
        d.pop("radio_seen", None)
        return d
    return (
        state.competition,
        {k: strip(v) for k, v in state.classes.items()},
        {k: strip(v) for k, v in state.competitors.items()},
        {k: strip(v) for k, v in state.teams.items()},
    )


def test_diffs_equal_complete_over_simulation():
    """Viele Diffs hintereinander müssen denselben Zustand ergeben wie ein frischer Komplettabzug."""
    sim = Simulation(speed=1.0)
    server = MockMeosServer(sim)
    t = sim.sim0
    sim.now = lambda: t  # Zeit manuell steuern

    incremental = MopState()
    nxt = incremental.apply(server.difference("zero"))
    for _ in range(130):
        t += 600  # +1 Minute
        nxt = incremental.apply(server.difference(nxt))

    fresh = MopState()
    fresh.apply(server.difference("zero"))
    assert _as_dict(incremental) == _as_dict(fresh)

    # Plausibilität der Auswertungen
    for cls in views.classes_list(fresh):
        res = views.class_results(fresh, cls["id"])
        assert res is not None
    relay = views.class_results(fresh, 10)
    assert relay["type"] == "team" and relay["legs"] == 3
    assert any(r["state"] == "finished" for r in relay["rows"])
    assert views.ticker(fresh, 5)


def test_relay_camera_lower_third():
    state = MopState()
    state.classes[10] = ClassInfo(id=10, name="Staffel")
    for number in range(1, 21):
        runner_id = 10_000 + number
        state.competitors[runner_id] = Competitor(
            id=runner_id, name=f"Läufer {number}", cls=10,
            radio={71: number * 1_000}, radio_seen={71: float(number)},
        )
        state.teams[runner_id] = Team(
            id=runner_id, name=f"Staffel {number}", cls=10, legs=[[runner_id], []],
        )

    lower_third = views.radio_lower_third(state, 10, 71)
    assert lower_third is not None
    assert lower_third["class"] == "Staffel"
    assert len(lower_third["leader"]) == 1
    assert lower_third["leader"][0]["place"] == 1
    assert len(lower_third["standings"]) == 3
    assert [row["place"] for row in lower_third["standings"]] == [18, 19, 20]
    assert lower_third["latest"] is not None
    assert lower_third["latest"]["leg"] == 1

    # Der Zieleinlauf der ersten Strecke leert die Anzeige sofort für die
    # zweite Strecke, noch bevor dort der erste Funkdurchgang vorliegt.
    state.competitors[10_001].stat = STATUS_OK
    state.competitors[10_001].rt = 10_000
    after_exchange = views.radio_lower_third(state, 10, 71)
    assert after_exchange is not None
    assert after_exchange["leader"] == []

    # Der erste Durchgang der zweiten Strecke startet deren Wertung bei 1.
    runner_id = 20_001
    state.competitors[runner_id] = Competitor(
        id=runner_id, name="Zweite Strecke", cls=10,
        radio={71: 99_000}, radio_seen={71: 99.0},
    )
    state.teams[10_001].legs[1] = [runner_id]
    next_leg = views.radio_lower_third(state, 10, 71)
    assert next_leg is not None
    assert [row["place"] for row in next_leg["leader"]] == [1]
    assert next_leg["leader"][0]["leg"] == 2


def test_relay_provisional_places_follow_official_finishers():
    state = MopState()
    state.classes[10] = ClassInfo(id=10, name="Staffel", radio=[[71]])
    state.competitors[1] = Competitor(id=1, name="Im Ziel", cls=10, stat=STATUS_OK, rt=3_600)
    state.teams[1] = Team(id=1, name="Sieger", cls=10, legs=[[1]])
    state.competitors[2] = Competitor(
        id=2, name="Unterwegs", cls=10, competing=True, radio={71: 2_000},
    )
    state.teams[2] = Team(id=2, name="Live", cls=10, legs=[[2]])

    results = views.class_results(state, 10)
    assert results is not None
    assert results["counts"]["finished"] == 1
    assert results["rows"][0]["place"] == 1
    assert results["rows"][1]["provisional_place"] == 2
    assert results["rows"][1]["time"] == "3:20"


def test_unknown_difference_returns_error():
    server = MockMeosServer(Simulation())
    assert server.difference("999").startswith("Error (MeOS)")
