"""Si el «Caso base» no converge, se busca la causa y se corrige lo reconstruible (spec 081).

Usuario, 2026-11-03: «nada debe bloquear, eso ya está definido, debes dar solución, el conversor,
para eso están los oráculos». Y 2026-10-17: «no se acepta una respuesta de que no converge». Bajar
la demanda por igual (015:RF-38) esconde la causa: 057 lo midió del 90 % al 10 % sin converger.

El bucle no sabe de DIgSILENT: ``medir`` y los corregidores los pone el guion, que es quien
escribe, y DIgSILENT confirma con su flujo. Lo que queda sin solución se dice con su causa, su elemento y
qué hacer; nunca se para por ello.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

FASES, ISLA, DATOS, DEMANDA, DESCONOCIDA = 'fases', 'isla', 'datos', 'demanda', 'desconocida'
#: Vueltas de corregir y medir: cada una ha de traer una corrección nueva.
VUELTAS = 6

_MENSAJE_FASES = re.compile(r'no\.?\s*of\s*phases\s*\((\d)\)[^.\n]*?no\.?\s*of\s*phases\s*\((\d)\)', re.IGNORECASE)
_MENSAJE_ISLA = re.compile(r'isolated|unsupplied|not\s+supplied|no\s+reference|sin\s+referencia|\bisla\b|sin\s+camino', re.IGNORECASE)
_MENSAJE_DATOS = re.compile(r'error\s+in\s+load\s+flow\s+data|sin\s+impedancia|sin\s+tipo', re.IGNORECASE)
_MENSAJE_DEMANDA = re.compile(r'diverg|excess|demand|exceso|voltage\s+collapse|no_converge|no converge', re.IGNORECASE)

QUE_HACER = {
    FASES: 'reconvierta con la spec 054 o cambie el tipo del elemento a las fases de su barra.',
    ISLA: 'conecte la isla a una fuente o déjela fuera de servicio; no se inventa una conexión.',
    DATOS: 'complete el dato del elemento con su ficha y reconvierta.',
    DEMANDA: 'revise la demanda del elemento o la capacidad aguas arriba (015:RF-38).',
    DESCONOCIDA: 'lea el historial de DIgSILENT: pruebe cada isla sola para ver la barra de mayor error.',
}


@dataclass(frozen=True)
class Causa:
    tipo: str
    detalle: str
    elementos: tuple[str, ...] = ()


@dataclass
class Resolucion:
    estado: str = 'no_converge'
    vueltas: int = 0
    anotaciones: list[dict[str, Any]] = field(default_factory=list)
    queda: list[dict[str, Any]] = field(default_factory=list)
    historial: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def clasificar_causas(mensajes: str, *, hallazgos_fases: Iterable[str] = (),
                      oraculo: Iterable[str] = ()) -> list[Causa]:
    """Las causas de un flujo que no converge, de la más concreta a la más general (081:RF-25).

    ``mensajes`` es lo que dice DIgSILENT; ``hallazgos_fases``, lo de ``comprobacion_fases``, y
    ``oraculo``, lo que halló el flujo independiente antes de importar.
    """
    oraculo = [str(x) for x in oraculo]
    texto = '\n'.join([mensajes or '', *oraculo])
    causas: list[Causa] = []
    hallazgos = tuple(hallazgos_fases)
    fases = _MENSAJE_FASES.search(texto)
    if hallazgos or fases:
        causas.append(Causa(FASES, fases.group(0) if fases else f'{len(hallazgos)} elemento(s) con fases que su barra no lleva', hallazgos))
    for tipo, patron in ((ISLA, _MENSAJE_ISLA), (DATOS, _MENSAJE_DATOS), (DEMANDA, _MENSAJE_DEMANDA)):
        visto = patron.search(texto)
        if visto:
            linea = next((x for x in texto.splitlines() if patron.search(x)), visto.group(0))
            causas.append(Causa(tipo, linea.strip()[:300]))
    return causas or [Causa(DESCONOCIDA, 'ni DIgSILENT ni el oráculo dicen la causa.')]


def resolver(medir: Callable[[], Mapping[str, Any]],
             corregidores: Mapping[str, Callable[[Causa], list[dict[str, Any]]]],
             *, vueltas: int = VUELTAS) -> Resolucion:
    """Medir, corregir lo reconstruible y volver a medir (081:RF-26 a RF-29).

    ``medir`` devuelve ``{estado, mensajes, hallazgos_fases, oraculo}``; cada corregidor, las
    anotaciones ``{elemento, antes, despues, regla, evidencia}`` de lo que cambió. Se para al
    converger o cuando ninguna causa trae una corrección nueva: repetir la misma no ayuda.
    """
    res = Resolucion()
    vistas: set[tuple] = set()
    for vuelta in range(vueltas + 1):
        medida = medir()
        res.vueltas = vuelta
        res.historial.append({'paso': vuelta, 'estado': medida.get('estado'),
                              'accion': 'medir' if vuelta == 0 else 'volver a medir tras corregir',
                              'return_code': medida.get('return_code')})
        if medida.get('estado') == 'converge':
            res.estado = 'converge'
            res.queda = []
            return res
        causas = clasificar_causas(str(medida.get('mensajes') or ''),
                                   hallazgos_fases=medida.get('hallazgos_fases') or (),
                                   oraculo=medida.get('oraculo') or ())
        res.queda = [{'causa': c.tipo, 'detalle': c.detalle, 'elementos': list(c.elementos),
                      'que_hacer': QUE_HACER[c.tipo]} for c in causas]
        corregido = False
        for causa in causas:
            corregir = corregidores.get(causa.tipo)
            if corregir is None or vuelta == vueltas:
                continue
            nuevas = [a for a in corregir(causa) if _clave(a) not in vistas]
            if nuevas:
                vistas.update(_clave(a) for a in nuevas)
                res.anotaciones.extend(nuevas)
                corregido = True
                break
        if not corregido:
            return res
    return res


def _clave(anotacion: Mapping[str, Any]) -> tuple:
    return (anotacion.get('elemento'), str(anotacion.get('antes')), str(anotacion.get('despues')))


def texto_de_resolucion(resolucion: Mapping[str, Any]) -> list[str]:
    """Lo que se le dice al operador, una línea por corrección y por causa que queda."""
    lineas = [f"Corregido {a.get('elemento')}: {a.get('antes')} → {a.get('despues')} ({a.get('regla')})."
              for a in resolucion.get('anotaciones') or []]
    lineas += [f"Queda {q['causa']}: {q['detalle']}"
               + (f" ({', '.join(q['elementos'][:5])})" if q.get('elementos') else '') + f" Qué hacer: {q['que_hacer']}"
               for q in resolucion.get('queda') or []]
    return lineas
