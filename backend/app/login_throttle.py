"""Limitador de intentos fallidos de login para una instancia FastAPI.

En producción horizontal es necesaria una implementación compartida (Redis,
proxy/gateway) y controles adicionales por cuenta; este mecanismo local
es una defensa complementaria, no una garantía distribuida.
"""
from collections import defaultdict, deque
from math import ceil
from threading import RLock
from time import monotonic

from fastapi import HTTPException


WINDOW_SECONDS = 300
MAX_PER_USER_AND_IP = 5
MAX_PER_IP = 20


class LoginThrottle:
    def __init__(self):
        self._lock = RLock()
        self._identity = defaultdict(deque)
        self._ip = defaultdict(deque)

    def clear(self):
        """Uso exclusivo de pruebas aisladas."""
        with self._lock:
            self._identity.clear()
            self._ip.clear()

    @staticmethod
    def _trim(entries, now):
        while entries and entries[0] <= now - WINDOW_SECONDS:
            entries.popleft()

    def check(self, ip: str, username: str):
        now = monotonic()
        with self._lock:
            by_identity = self._identity[(ip, username)]
            by_ip = self._ip[ip]
            self._trim(by_identity, now)
            self._trim(by_ip, now)
            if len(by_identity) >= MAX_PER_USER_AND_IP or len(by_ip) >= MAX_PER_IP:
                a = WINDOW_SECONDS - (now - by_identity[0]) if len(by_identity) >= MAX_PER_USER_AND_IP else 0
                b = WINDOW_SECONDS - (now - by_ip[0]) if len(by_ip) >= MAX_PER_IP else 0
                raise HTTPException(
                    status_code=429,
                    detail="Demasiados intentos. Intenta de nuevo más tarde.",
                    headers={"Retry-After": str(max(1, ceil(max(a, b))))},
                )

    def failure(self, ip: str, username: str):
        now = monotonic()
        with self._lock:
            self._trim(self._identity[(ip, username)], now)
            self._trim(self._ip[ip], now)
            self._identity[(ip, username)].append(now)
            self._ip[ip].append(now)
            # Evitar crecimiento ilimitado con nombres inventados.
            if len(self._identity) > 10_000:
                for key, entries in list(self._identity.items()):
                    self._trim(entries, now)
                    if not entries:
                        del self._identity[key]
            if len(self._ip) > 10_000:
                for key, entries in list(self._ip.items()):
                    self._trim(entries, now)
                    if not entries:
                        del self._ip[key]

    def success(self, ip: str, username: str):
        with self._lock:
            self._identity.pop((ip, username), None)


login_throttle = LoginThrottle()
