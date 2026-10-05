"""Configuration loaded from a local YAML file."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EventConfig:
    name: str | None = None
    short_name: str | None = None
    date: str | None = None
    organizer: str | None = None
    location: str | None = None
    logo: Path | None = None
    radio_controls: tuple[int, ...] = ()

    def metadata(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "name": self.name,
                "short_name": self.short_name,
                "date": self.date,
                "organizer": self.organizer,
                "location": self.location,
            }.items()
            if value
        }


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"event.{key} muss ein Text sein")
    return value.strip() or None


def load_event_config(path: Path | None) -> EventConfig:
    """Read the optional YAML file and resolve its logo relative to that file."""
    if path is None:
        return EventConfig()
    if not path.is_file():
        raise ValueError(f"Konfigurationsdatei nicht gefunden: {path}")

    with path.open(encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    if not isinstance(data, dict):
        raise ValueError("Die YAML-Konfiguration muss ein Mapping enthalten")

    event = data.get("event", {})
    if not isinstance(event, dict):
        raise ValueError("event muss ein Mapping enthalten")

    controls = event.get("radio_controls", [])
    if not isinstance(controls, list) or not all(isinstance(control, int) for control in controls):
        raise ValueError("event.radio_controls muss eine Liste ganzer Zahlen sein")

    logo_value = _optional_string(event, "logo")
    logo = (path.parent / logo_value).resolve() if logo_value else None
    if logo is not None and not logo.is_file():
        raise ValueError(f"Logo-Datei nicht gefunden: {logo}")

    return EventConfig(
        name=_optional_string(event, "name"),
        short_name=_optional_string(event, "short_name"),
        date=_optional_string(event, "date"),
        organizer=_optional_string(event, "organizer"),
        location=_optional_string(event, "location"),
        logo=logo,
        radio_controls=tuple(dict.fromkeys(controls)),
    )
