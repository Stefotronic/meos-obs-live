"""Fragt den MeOS-Informationsserver zyklisch per Differenzprotokoll ab."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .mop import MopError, MopState

log = logging.getLogger("meos_obs.poller")


class MeosPoller:
    def __init__(self, state: MopState, url: str, interval: float = 2.0, timeout: float = 5.0) -> None:
        self.state = state
        self.url = url
        self.interval = interval
        self.timeout = timeout
        self.connected = False
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self.requests = 0
        self._next = "zero"

    def status(self) -> dict:
        return {
            "url": self.url,
            "connected": self.connected,
            "last_ok": self.last_ok,
            "age": round(time.time() - self.last_ok, 1) if self.last_ok else None,
            "last_error": self.last_error,
            "requests": self.requests,
        }

    async def poll_once(self, client: httpx.AsyncClient) -> None:
        self.requests += 1
        try:
            resp = await client.get(self.url, params={"difference": self._next})
            resp.raise_for_status()
            body = resp.content
            if body.lstrip().startswith(b"Error"):
                # z. B. unbekannter Differenzstand nach MeOS-Neustart -> komplett neu laden
                self.last_error = body.decode("utf-8", "replace").strip()[:300]
                self._next = "zero"
                return
            self._next = self.state.apply(body) or "zero"
            self.connected = True
            self.last_ok = time.time()
            self.last_error = None
        except MopError as exc:
            self.last_error = str(exc)
            self._next = "zero"
        except httpx.HTTPError as exc:
            self.connected = False
            self.last_error = f"{type(exc).__name__}: {exc}"

        if self.last_error:
            log.warning("MeOS-Abfrage fehlgeschlagen: %s", self.last_error)

    async def run(self) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                await self.poll_once(client)
                await asyncio.sleep(self.interval)
