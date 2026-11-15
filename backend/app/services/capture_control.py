
from contextlib import contextmanager
from threading import Condition

from fastapi import HTTPException


_condition = Condition()
_suspended = False
_active_operations = 0


@contextmanager
def capture_operation():
    """
    Registra una operación de captura.
    Si existe una restauración activa, rechaza nuevas operaciones.
    """
    global _active_operations

    with _condition:
        if _suspended:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "CAPTURE_SUSPENDED",
                    "message": "La captura está suspendida por una operación de restauración.",
                    "action": "Espera a que finalice la restauración e inténtalo nuevamente."
                }
            )

        _active_operations += 1

    try:
        yield
    finally:
        with _condition:
            _active_operations -= 1
            _condition.notify_all()


@contextmanager
def suspend_capture():
    """
    Suspende nuevas capturas y espera a que terminen
    las operaciones que ya estaban en curso.
    """
    global _suspended

    with _condition:
        if _suspended:
            raise RuntimeError("Ya existe una operación de restauración.")

        _suspended = True

        try:
            while _active_operations > 0:
                _condition.wait()

        except BaseException:
            _suspended = False
            _condition.notify_all()
            raise

    try:
        yield
    finally:
        with _condition:
            _suspended = False
            _condition.notify_all()


def capture_status():
    with _condition:
        return {
            "suspended": _suspended,
            "activeOperations": _active_operations
        }
from fastapi import Depends


def capture_guard():
    """Dependencia que protege una operación durante la restauración."""
    with capture_operation():
        yield