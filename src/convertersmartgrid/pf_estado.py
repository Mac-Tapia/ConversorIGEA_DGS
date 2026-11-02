"""El estado de DIgSILENT antes de una orden, y su restitución si la orden falla (spec 064).

El servidor de DIgSILENT (019:RF-7) atiende las órdenes una detrás de otra en el mismo
proceso. Cada guion devuelve a su sitio el caso, la hora de estudio y las variaciones que
toca cuando termina bien (011:RF-26), pero una excepción a mitad lo dejaba todo como
estuviera: la orden siguiente medía con otro caso, otra hora u otra variación activa.
Aquí se toma la foto antes de la orden y, si falla, se repone (064:RF-4, RF-5).

La API de DIgSILENT señala muchos fallos con el retorno y no con una excepción:
``Activate`` devuelve distinto de 0 y el caso sigue como estaba. La primera versión no lo
miraba: anunciaba «caso «Sin» activo de nuevo» con «Con» todavía activo y escribía en «Con»
la hora de «Sin» (auditoría del 2026-11-02, H1). Ahora cada paso comprueba su retorno y
relee lo activo, la hora solo se escribe en el caso de la foto, y al final se compara la
foto entera (064:RF-10).

Solo se usan objetos de la API de DIgSILENT; las pruebas usan un doble.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FotoFallida(RuntimeError):
    """No se pudo leer el estado activo: distinto de «no hay proyecto activo» (064:RF-9)."""


class RestitucionFallida(RuntimeError):
    """El estado no quedó como en la foto; el mensaje dice qué falta (064:RF-10)."""


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


def _fallo(retorno: Any) -> bool:
    """``Activate``/``Deactivate`` de DIgSILENT: 0 es éxito; otro entero, fallo sin excepción."""
    return isinstance(retorno, int) and not isinstance(retorno, bool) and retorno != 0


@dataclass
class Foto:
    """Lo que la orden siguiente espera encontrar (064:RF-4)."""

    proyecto: Any
    caso: Any
    hora: int | None
    escenario: Any
    variaciones: list[Any] = field(default_factory=list)


def fotografiar(app: Any) -> Foto | None:
    """La foto del estado activo; ``None`` si no hay proyecto activo (nada que reponer).

    Si la API falla al leer, lanza :class:`FotoFallida` (064:RF-9): no es lo mismo que no
    tener proyecto, y quien la pide decide qué hacer sin perder la orden.
    """
    try:
        proyecto = app.GetActiveProject()
        if proyecto is None:
            return None
        caso = app.GetActiveStudyCase()
        hora = getattr(caso, 'iStudyTime', None) if caso is not None else None
        return Foto(proyecto=proyecto, caso=caso,
                    hora=int(hora) if hora is not None else None,
                    escenario=app.GetActiveScenario(),
                    variaciones=list(app.GetActiveNetworkVariations() or []))
    except Exception as exc:  # noqa: BLE001 - cualquier lectura de la API
        raise FotoFallida(f'no se pudo leer el estado de DIgSILENT: {exc}') from exc


def _diferencias(app: Any, foto: Foto) -> list[str]:
    """Lo que no coincide entre el estado activo y ``foto``, en frases."""
    ahora = fotografiar(app)
    if ahora is None or not _mismo(ahora.proyecto, foto.proyecto):
        return [f'el proyecto activo es «{_nombre(getattr(ahora, "proyecto", None))}»']
    out = []
    if not _mismo(ahora.caso, foto.caso):
        out.append(f'sigue activo el caso «{_nombre(ahora.caso)}» y no «{_nombre(foto.caso)}»')
    elif foto.hora is not None and ahora.hora != foto.hora:
        out.append(f'la hora de «{_nombre(foto.caso)}» es {ahora.hora} y no {foto.hora}')
    if not _mismo(ahora.escenario, foto.escenario):
        out.append(f'el escenario activo es «{_nombre(ahora.escenario)}» y no «{_nombre(foto.escenario)}»')
    sobran = [v for v in ahora.variaciones if not any(_mismo(v, f) for f in foto.variaciones)]
    faltan = [f for f in foto.variaciones if not any(_mismo(v, f) for v in ahora.variaciones)]
    if sobran:
        out.append('siguen activas: ' + ', '.join(_nombre(v) for v in sobran))
    if faltan:
        out.append('siguen inactivas: ' + ', '.join(_nombre(v) for v in faltan))
    return out


def restituir(app: Any, foto: Foto | None) -> list[str]:
    """Deja el caso, su hora, el escenario y las variaciones como en ``foto`` (064:RF-5).

    Devuelve lo que cambió, en frases para el registro de la orden (RF-6), y solo lo que se
    comprobó hecho. Si el proyecto activo ya no es el de la foto no toca nada: otro proyecto
    no es estado de esta orden. Si un paso no surte efecto, o el estado final no es el de la
    foto, lanza :class:`RestitucionFallida` con lo que falta (RF-10); las excepciones de la
    API también suben a quien llama, que las anota (RF-7).
    """
    if foto is None or not _mismo(app.GetActiveProject(), foto.proyecto):
        return []
    hecho: list[str] = []
    if foto.caso is not None and not _mismo(app.GetActiveStudyCase(), foto.caso):
        # Activar el caso trae su escenario y sus variaciones; lo demás se ajusta después.
        retorno = foto.caso.Activate()
        activo = app.GetActiveStudyCase()
        if _fallo(retorno) or not _mismo(activo, foto.caso):
            # Sin el caso de la foto activo, su hora no se escribe: caería en otro caso.
            raise RestitucionFallida(
                f'no se pudo activar el caso «{_nombre(foto.caso)}» (Activate devolvió {retorno!r}); '
                f'sigue activo «{_nombre(activo)}». No se escribió ninguna hora.')
        hecho.append(f'caso «{_nombre(foto.caso)}» activo de nuevo')
    caso = app.GetActiveStudyCase()
    if (caso is not None and _mismo(caso, foto.caso) and foto.hora is not None
            and int(getattr(caso, 'iStudyTime', 0) or 0) != foto.hora):
        caso.iStudyTime = foto.hora
        if int(getattr(caso, 'iStudyTime', 0) or 0) != foto.hora:
            raise RestitucionFallida(f'la hora de «{_nombre(caso)}» no quedó en {foto.hora}')
        hecho.append(f'hora de estudio repuesta a {foto.hora}')
    actual = app.GetActiveScenario()
    if not _mismo(actual, foto.escenario):
        retorno = (foto.escenario.Activate() if foto.escenario is not None
                   else actual.Deactivate())
        ahora = app.GetActiveScenario()
        if _fallo(retorno) or not _mismo(ahora, foto.escenario):
            raise RestitucionFallida(
                f'no se pudo dejar el escenario «{_nombre(foto.escenario)}» (devolvió {retorno!r}); '
                f'sigue «{_nombre(ahora)}»')
        hecho.append(f'escenario «{_nombre(foto.escenario)}» en lugar de «{_nombre(actual)}»')
    activas = list(app.GetActiveNetworkVariations() or [])
    sobran = [v for v in activas if not any(_mismo(v, f) for f in foto.variaciones)]
    faltan = [f for f in foto.variaciones if not any(_mismo(v, f) for v in activas)]
    malas = [_nombre(v) for v in sobran if _fallo(v.Deactivate())]
    malas += [_nombre(v) for v in faltan if _fallo(v.Activate())]
    if malas:
        raise RestitucionFallida('DIgSILENT no cambió las variaciones: ' + ', '.join(malas))
    if sobran:
        hecho.append('variaciones desactivadas: ' + ', '.join(_nombre(v) for v in sobran))
    if faltan:
        hecho.append('variaciones activadas de nuevo: ' + ', '.join(_nombre(v) for v in faltan))
    # 064:RF-10: la foto entera, releída; lo hecho solo se anuncia si el estado coincide.
    diferencias = _diferencias(app, foto)
    if diferencias:
        raise RestitucionFallida('el estado no quedó como al empezar: ' + '; '.join(diferencias)
                                 + (f' (se hizo: {"; ".join(hecho)})' if hecho else ''))
    return hecho
