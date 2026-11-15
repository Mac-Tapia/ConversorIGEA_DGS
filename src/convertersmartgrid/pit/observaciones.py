"""Observaciones del regulador al expediente del PIT, con su respuesta y lo que afectan (107:RF-10).

Cada observación nombra un elemento de la red, un caso del diagnóstico o una celda de un cuadro, y queda enlazada con
la traza de esa celda en el expediente: quien responde ve de dónde salió la cifra observada. Una referencia que el
expediente no conoce es un error, no una observación suelta, porque una respuesta sin su objeto no se puede revisar.
El fichero se escribe con claves ordenadas, para que el mismo registro dé el mismo fichero (determinismo).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..util import publicar_duradero  # 001:RF-5 (H14): escritura atómica y duradera, con los mismos bytes
from . import PitError

__all__ = ['AFECTA', 'Observacion', 'absolucion', 'escribir_absolucion', 'escribir_observaciones',
           'leer_observaciones', 'registrar']

AFECTA = ('elemento', 'caso', 'celda')
_FECHA = re.compile(r'\d{4}-\d{2}-\d{2}')


@dataclass(frozen=True)
class Observacion:
    numero: str
    fecha: str
    texto: str
    afecta: str
    referencia: str
    respuesta: str = ''
    #: La traza de la celda observada, o el elemento o el caso tal como están en el expediente.
    enlace: Mapping[str, Any] = field(default_factory=dict)


def registrar(datos: Iterable[Mapping[str, Any]], referencias: Mapping[str, Mapping[str, Any]]) -> list[Observacion]:
    """Valida cada observación contra lo que hay en el expediente (``referencias``: tipo → id → su traza o datos)."""
    out, numeros = [], set()
    for d in datos:
        numero = str(d.get('numero') or '').strip()
        origen = f'observación {numero or "sin número"}'
        if not numero:
            raise PitError(f'{origen}: cada observación lleva su número')
        if numero in numeros:
            raise PitError(f'{origen}: número repetido')
        numeros.add(numero)
        if not _FECHA.fullmatch(str(d.get('fecha') or '')):
            raise PitError(f'{origen}: la fecha tiene que ser AAAA-MM-DD, no {d.get("fecha")!r}')
        if not str(d.get('texto') or '').strip():
            raise PitError(f'{origen}: sin texto')
        afecta, ref = str(d.get('afecta') or ''), str(d.get('referencia') or '')
        if afecta not in AFECTA:
            raise PitError(f'{origen}: «afecta» tiene que ser uno de {AFECTA}, no {afecta!r}')
        conocidas = referencias.get(afecta) or {}
        if ref not in conocidas:
            raise PitError(f'{origen}: el expediente no tiene {afecta} {ref!r}; la observación no se puede enlazar')
        out.append(Observacion(numero, str(d['fecha']), str(d['texto']), afecta, ref,
                               str(d.get('respuesta') or ''), dict(conocidas[ref] or {})))
    return sorted(out, key=lambda o: (o.fecha, o.numero))


def escribir_observaciones(ruta: Path | str, observaciones: Iterable[Observacion]) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [asdict(o) for o in observaciones]
    # En bytes: con LF como antes (newline='\n'); un str pasaría por la traducción de fin de línea de Windows.
    publicar_duradero(ruta, (json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return ruta


def leer_observaciones(ruta: Path | str, referencias: Mapping[str, Mapping[str, Any]]) -> list[Observacion]:
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    return registrar([{k: v for k, v in d.items() if k != 'enlace'} for d in datos], referencias)


def _huella(datos: Any) -> str:
    return hashlib.sha256(json.dumps(datos, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def absolucion(datos: Iterable[Mapping[str, Any]], antes: Mapping[str, Mapping[str, Any]],
               despues: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """El documento de absolución (aclaración de 107:RF-10): cada observación con su objeto y su respuesta, y la traza
    de lo que cambió en el expediente por ella.

    ``antes`` son las referencias del expediente observado (con ellas se validan las observaciones, como en
    ``registrar``) y ``despues`` las del expediente que responde. Por cada objeto observado se compara su traza:
    ``cambiado`` (con las dos trazas y sus huellas), ``sin_cambios`` (y se dice) o ``retirado`` (ya no está). Una
    observación sin respuesta no se absuelve: es un error que la nombra.
    """
    out = []
    for o in registrar(datos, antes):
        if not o.respuesta.strip():
            raise PitError(f'observación {o.numero}: sin respuesta no hay absolución')
        previa = dict(o.enlace)
        nueva = (despues.get(o.afecta) or {}).get(o.referencia)
        if nueva is None:
            cambio = {'estado': 'retirado', 'antes': previa, 'despues': None, 'huella_antes': _huella(previa),
                      'huella_despues': None,
                      'texto': f'{o.afecta} {o.referencia} ya no está en el expediente que responde'}
        else:
            nueva = dict(nueva)
            igual = _huella(previa) == _huella(nueva)
            cambio = {'estado': 'sin_cambios' if igual else 'cambiado', 'antes': previa, 'despues': nueva,
                      'huella_antes': _huella(previa), 'huella_despues': _huella(nueva),
                      'texto': (f'{o.afecta} {o.referencia}: sin cambios en el expediente' if igual
                                else f'{o.afecta} {o.referencia}: cambió en el expediente que responde')}
        out.append({'numero': o.numero, 'fecha': o.fecha, 'texto': o.texto, 'afecta': o.afecta,
                    'referencia': o.referencia, 'respuesta': o.respuesta, 'cambio': cambio})
    return out


def escribir_absolucion(ruta: Path | str, datos: Iterable[Mapping[str, Any]], antes: Mapping[str, Mapping[str, Any]],
                        despues: Mapping[str, Mapping[str, Any]]) -> Path:
    """La absolución en JSON con claves ordenadas: el mismo registro da el mismo fichero (determinismo)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    publicar_duradero(ruta, (json.dumps(absolucion(datos, antes, despues), ensure_ascii=False, indent=1,
                                        sort_keys=True) + '\n').encode('utf-8'))
    return ruta
