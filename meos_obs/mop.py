"""Parser und In-Memory-Zustand für das MeOS Online Protocol (MOP).

MeOS liefert über den Informationsserver (``/meos?difference=zero`` bzw.
``/meos?difference=<id>``) ein ``MOPComplete``- oder ``MOPDiff``-Dokument.
Zeiten sind in Zehntelsekunden angegeben, ``st`` ist die Tageszeit.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# Status-Codes aus MeOS (oRunner.h, enum RunnerStatus)
STATUS_UNKNOWN = 0
STATUS_OK = 1
STATUS_NO_TIMING = 2
STATUS_MP = 3
STATUS_DNF = 4
STATUS_DQ = 5
STATUS_MAX = 6
STATUS_OUT_OF_COMPETITION = 15
STATUS_DNS = 20
STATUS_CANCEL = 21
STATUS_NOT_COMPETING = 99

STATUS_TEXT = {
    STATUS_UNKNOWN: "",
    STATUS_OK: "OK",
    STATUS_NO_TIMING: "o. Zeit",
    STATUS_MP: "Fehlst.",
    STATUS_DNF: "Aufg.",
    STATUS_DQ: "Disq.",
    STATUS_MAX: "Zeitüb.",
    STATUS_OUT_OF_COMPETITION: "a.K.",
    STATUS_DNS: "n. gest.",
    STATUS_CANCEL: "abgem.",
    STATUS_NOT_COMPETING: "n. teilg.",
}


class MopError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def unpack_int_int(text: str | None) -> list[list[int]]:
    """``"1;1,2,3;;4,5"`` -> ``[[1], [1, 2, 3], [], [4, 5]]``"""
    if not text:
        return []
    return [[_int(x) for x in part.split(",") if x.strip()] for part in text.split(";")]


def unpack_radio(text: str | None) -> dict[int, int]:
    """``"31,5230;45,9910"`` -> ``{31: 5230, 45: 9910}``"""
    result: dict[int, int] = {}
    for part in (text or "").split(";"):
        if "," in part:
            ctrl, t = part.split(",", 1)
            result[_int(ctrl)] = _int(t)
    return result


@dataclass
class Control:
    id: int
    name: str = ""
    offline: bool = False


@dataclass
class ClassInfo:
    id: int
    name: str = ""
    order: int = 0
    radio: list[list[int]] = field(default_factory=list)
    length: int = 0


@dataclass
class Organization:
    id: int
    name: str = ""
    nat: str = ""


@dataclass
class BaseEntry:
    id: int
    name: str = ""
    org: int = 0
    cls: int = 0
    stat: int = STATUS_UNKNOWN
    prel: bool = False
    st: int = -1
    rt: int = 0
    bib: str = ""
    nat: str = ""


@dataclass
class Competitor(BaseEntry):
    card: int = 0
    competing: bool = False
    radio: dict[int, int] = field(default_factory=dict)
    it: int = 0
    tstat: int = 0
    # Zeitpunkt (time.time()), zu dem wir den Zieleinlauf erstmals gesehen haben.
    # 0.0 = schon beim ersten Laden vorhanden (nicht als "neu" markieren).
    finished_seen: float | None = None
    # Zeitpunkt, zu dem ein Funkposten erstmals in den Live-Daten auftauchte.
    # Wie bei finished_seen bedeutet 0.0: beim ersten Laden schon vorhanden.
    radio_seen: dict[int, float] = field(default_factory=dict)

    @property
    def finish_tod(self) -> int:
        return self.st + self.rt if self.st >= 0 and self.rt > 0 else -1


@dataclass
class Team(BaseEntry):
    legs: list[list[int]] = field(default_factory=list)


TICKER_STATUSES = {STATUS_OK, STATUS_NO_TIMING, STATUS_MP, STATUS_DQ, STATUS_MAX, STATUS_OUT_OF_COMPETITION}


def has_finished(c: Competitor) -> bool:
    """Läufer gilt als im Ziel (für Ticker/Highlight)."""
    if c.stat not in TICKER_STATUSES:
        return False
    return c.rt > 0 or c.stat in (STATUS_MP, STATUS_DQ)


class MopState:
    def __init__(self) -> None:
        self.competition: dict[str, str] = {}
        self.controls: dict[int, Control] = {}
        # Manuell vorgegebene Funkposten, falls MeOS keine radio-Attribute an
        # den Klassen übermittelt.
        self.radio_controls: set[int] = set()
        self.classes: dict[int, ClassInfo] = {}
        self.orgs: dict[int, Organization] = {}
        self.competitors: dict[int, Competitor] = {}
        self.teams: dict[int, Team] = {}
        self.version = 0
        self.last_update: float | None = None
        self._loaded_once = False

    def clear(self) -> None:
        self.competition = {}
        self.controls.clear()
        self.classes.clear()
        self.orgs.clear()
        self.competitors.clear()
        self.teams.clear()

    def apply(self, data: bytes | str) -> str | None:
        """Wendet ein MOP-Dokument an. Gibt ``nextdifference`` zurück."""
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise MopError(f"Ungültiges XML: {exc}") from exc

        kind = _local(root.tag)
        if kind not in ("MOPComplete", "MOPDiff"):
            raise MopError(f"Unerwartetes Wurzelelement: {kind}")
        complete = kind == "MOPComplete"

        seen_before = {cid: c.finished_seen for cid, c in self.competitors.items()}
        radios_before = {cid: set(c.radio) for cid, c in self.competitors.items()}
        radio_seen_before = {cid: dict(c.radio_seen) for cid, c in self.competitors.items()}
        if complete:
            self.clear()

        handlers = {
            "competition": self._apply_competition,
            "ctrl": self._apply_ctrl,
            "cls": self._apply_cls,
            "org": self._apply_org,
            "cmp": self._apply_cmp,
            "tm": self._apply_tm,
        }
        for el in root:
            handler = handlers.get(_local(el.tag))
            if handler:
                handler(el, complete)

        now = time.time()
        for c in self.competitors.values():
            if c.finished_seen is None:
                c.finished_seen = seen_before.get(c.id)
            if has_finished(c):
                if c.finished_seen is None:
                    c.finished_seen = now if self._loaded_once else 0.0
            else:
                c.finished_seen = None

            previous_radios = radios_before.get(c.id, set())
            previous_seen = radio_seen_before.get(c.id, {})
            c.radio_seen = {
                ctrl: previous_seen.get(ctrl, now if self._loaded_once and ctrl not in previous_radios else 0.0)
                for ctrl in c.radio
            }

        self._loaded_once = True
        self.version += 1
        self.last_update = now
        return root.get("nextdifference")

    @staticmethod
    def _is_delete(el: ET.Element) -> bool:
        return el.get("delete") == "true"

    def _apply_competition(self, el: ET.Element, complete: bool) -> None:
        self.competition = {
            "name": (el.text or "").strip(),
            "date": el.get("date", ""),
            "organizer": el.get("organizer", ""),
            "homepage": el.get("homepage", ""),
            "zerotime": el.get("zerotime", ""),
        }

    def _apply_ctrl(self, el: ET.Element, complete: bool) -> None:
        cid = _int(el.get("id"))
        if self._is_delete(el):
            self.controls.pop(cid, None)
            return
        self.controls[cid] = Control(cid, (el.text or "").strip(), el.get("offline") == "true")

    def _apply_cls(self, el: ET.Element, complete: bool) -> None:
        cid = _int(el.get("id"))
        if self._is_delete(el):
            self.classes.pop(cid, None)
            return
        self.classes[cid] = ClassInfo(
            id=cid,
            name=(el.text or "").strip(),
            order=_int(el.get("ord")),
            radio=unpack_int_int(el.get("radio")),
            length=_int(el.get("len")),
        )

    def _apply_org(self, el: ET.Element, complete: bool) -> None:
        oid = _int(el.get("id"))
        if self._is_delete(el):
            self.orgs.pop(oid, None)
            return
        self.orgs[oid] = Organization(oid, (el.text or "").strip(), el.get("nat", ""))

    @staticmethod
    def _apply_base(entry: BaseEntry, base: ET.Element | None) -> None:
        if base is None:
            return
        entry.name = (base.text or "").strip()
        entry.org = _int(base.get("org"))
        entry.cls = _int(base.get("cls"))
        entry.stat = _int(base.get("stat"))
        entry.prel = base.get("prel") == "true"
        entry.st = _int(base.get("st"), -1)
        entry.rt = _int(base.get("rt"))
        entry.bib = base.get("bib", "")
        entry.nat = base.get("nat", "")

    @staticmethod
    def _child(el: ET.Element, name: str) -> ET.Element | None:
        for child in el:
            if _local(child.tag) == name:
                return child
        return None

    def _apply_cmp(self, el: ET.Element, complete: bool) -> None:
        cid = _int(el.get("id"))
        if self._is_delete(el):
            self.competitors.pop(cid, None)
            return
        c = self.competitors.get(cid) or Competitor(cid)
        if el.get("card") is not None:
            c.card = _int(el.get("card"))
        c.competing = el.get("competing") == "true"
        self._apply_base(c, self._child(el, "base"))

        # Im Diff schickt MeOS <radio>/<input> nur, wenn sie sich geändert haben.
        radio = self._child(el, "radio")
        if radio is not None:
            c.radio = unpack_radio(radio.text)
        elif complete:
            c.radio = {}

        inp = self._child(el, "input")
        if inp is not None:
            c.it = _int(inp.get("it"))
            c.tstat = _int(inp.get("tstat"))
        elif complete:
            c.it = c.tstat = 0
        self.competitors[cid] = c

    def _apply_tm(self, el: ET.Element, complete: bool) -> None:
        tid = _int(el.get("id"))
        if self._is_delete(el):
            self.teams.pop(tid, None)
            return
        t = self.teams.get(tid) or Team(tid)
        self._apply_base(t, self._child(el, "base"))
        r = self._child(el, "r")
        if r is not None:
            t.legs = unpack_int_int(r.text)
        self.teams[tid] = t
