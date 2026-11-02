"""El estado de DIgSILENT antes de una orden, y su restitución si la orden falla (spec 064).

El servidor de DIgSILENT (019:RF-7) atiende las órdenes una detrás de otra en el mismo
proceso. Cada guion devuelve a su sitio el caso, la hora de estudio y las variaciones que
toca cuando termina bien (011:RF-26), pero una excepción a mitad lo dejaba todo como
estuviera: la orden siguiente medía con otro caso, otra hora u otra variación activa.
Aquí se toma la foto antes de la orden y, si falla, se repone (064:RF-4, RF-5).

Solo se usan objetos de la API de DIgSILENT; las pruebas usan un doble.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _nombre(obj: Any) -> str:
    return str(getattr(obj, 'loc_name', '') or '') if obj is not None else '(ninguno)'


def _mismo(a: Any, b: Any) -> bool:
    """Dos referencias de DIgSILENT al mismo objeto: la API puede dar envoltorios distintos."""
    if a is None or b is None:
        return a is b
    if a is b:
        return True
    try:
        return a.GetFullName() == b.GetFullName()
    except Exception:  # noqa: BLE001 - un doble sin ``GetFullName``
        return False


@dataclass
class Foto:
    """Lo que la orden siguiente espera encontrar (064:RF-4)."""

    proyecto: Any
    caso: Any
    hora: int | None
    escenario: Any
    variaciones: list[Any] = field(default_factory=list)


def fotografiar(app: Any) -> Foto | None:
    """La foto del estado activo; ``None`` sin proyecto activo (no hay nada que reponer)."""
    try:
        proyecto = app.GetActiveProject()
    except Exception:  # noqa: BLE001 - sin conexión útil, no hay foto
        return None
    if proyecto is None:
        return None
    caso = app.GetActiveStudyCase()
    hora = getattr(caso, 'iStudyTime', None) if caso is not None else None
    return Foto(proyecto=proyecto, caso=caso,
                hora=int(hora) if hora is not None else None,
                escenario=app.GetActiveScenario(),
                variaciones=list(app.GetActiveNetworkVariations() or []))


def restituir(app: Any, foto: Foto | None) -> list[str]:
    """Deja el caso, su hora, el escenario y las variaciones como en ``foto`` (064:RF-5).

    Devuelve lo que cambió, en frases para el registro de la orden (RF-6). Si el proyecto
    activo ya no es el de la foto no toca nada: otro proyecto no es estado de esta orden.
    Las excepciones de la API suben a quien llama, que las anota (RF-7).
    """
    if foto is None or not _mismo(app.GetActiveProject(), foto.proyecto):
        return []
    hecho: list[str] = []
    if foto.caso is not None and not _mismo(app.GetActiveStudyCase(), foto.caso):
        # Activar el caso trae su escenario y sus variaciones; lo demás se ajusta después.
        foto.caso.Activate()
        hecho.append(f'caso «{_nombre(foto.caso)}» activo de nuevo')
    caso = app.GetActiveStudyCase()
    if caso is not None and foto.hora is not None and int(getattr(caso, 'iStudyTime', 0) or 0) != foto.hora:
        caso.iStudyTime = foto.hora
        hecho.append(f'hora de estudio repuesta a {foto.hora}')
    actual = app.GetActiveScenario()
    if not _mismo(actual, foto.escenario):
        if foto.escenario is not None:
            foto.escenario.Activate()
        elif actual is not None:
            actual.Deactivate()
        hecho.append(f'escenario «{_nombre(foto.escenario)}» en lugar de «{_nombre(actual)}»')
    activas = list(app.GetActiveNetworkVariations() or [])
    sobran = [v for v in activas if not any(_mismo(v, f) for f in foto.variaciones)]
    faltan = [f for f in foto.variaciones if not any(_mismo(v, f) for v in activas)]
    for v in sobran:
        v.Deactivate()
    for v in faltan:
        v.Activate()
    if sobran:
        hecho.append('variaciones desactivadas: ' + ', '.join(_nombre(v) for v in sobran))
    if faltan:
        hecho.append('variaciones activadas de nuevo: ' + ', '.join(_nombre(v) for v in faltan))
    return hecho
