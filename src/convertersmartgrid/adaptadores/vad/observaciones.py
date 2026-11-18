"""Observaciones del regulador al Estudio VAD, con su respuesta y lo que afectan (108:RF-12).

El TdR registrado dice que los documentos del informe «serán revisados y analizados por Osinergmin. De ser el caso,
serán observados de conformidad con el artículo 68 de la LCE», y que el Informe Definitivo lleva «las respuestas junto
con su sustento, así como, de ser el caso, la especificación de las modificaciones efectuadas al Estudio VAD»
(numeral 9 del anexo de los TdR registrado, `tdr-vad-2026-anexo-r033`, copia de texto de sha256 48ea8cf4…, líneas
3496-3497 y 3509-3510). Por eso cada observación se guarda con:

- su número y su fecha (los del oficio del regulador) y su texto;
- lo que afecta: tablas de resultados del registro (``vad.tablas_resultados``), formatos del anexo 2 (prefijo A, la
  empresa, o B, la empresa modelo) o cálculos que el estudio declara en ``usos``. Un destino que no existe se rechaza:
  una respuesta que apunta a una tabla inventada no se puede sustentar;
- la respuesta, su sustento y, si la respuesta cambió algo, qué cambió en cada destino.

Se guardan en ``<espacio>/vad/<id>/observaciones.json`` con la escritura atómica única (001:RF-5). El Informe
Definitivo que las usa es la T22 de la spec, no este módulo.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from ...dominio.registro_normativo import RegistroNormativo
from ...dominio.util import write_json_atomic
from ...aplicacion.vad import VadError
from ...aplicacion.vad.anexo2 import Formatos
from ...aplicacion.vad.estudio import cargar_estudio, carpeta_estudio
from .tablas_resultados import tablas_registradas

ARCHIVO = 'observaciones.json'
#: Lo que puede afectar una observación: una tabla de resultados, un formato del anexo 2 o un cálculo del estudio.
TIPOS_DESTINO = ('tabla', 'formato', 'calculo')
#: Prefijos de los formatos del anexo 2: A, la información de la empresa; B, los mismos cuadros de la empresa modelo.
_PREFIJO = re.compile(r'^[AB]-')


@dataclass(frozen=True)
class Destino:
    tipo: str
    id: str

    def texto(self) -> str:
        return f'{self.tipo} {self.id}'


@dataclass(frozen=True)
class Observacion:
    numero: str
    fecha: str
    texto: str
    afecta: tuple[Destino, ...]
    respuesta: str = ''
    sustento: str = ''
    #: Destino (``tipo id``) → qué cambió en él por la respuesta; vacío si la respuesta no cambió nada.
    cambios: Mapping[str, str] = field(default_factory=dict)

    @property
    def estado(self) -> str:
        return 'respondida' if self.respuesta else 'pendiente'


def destinos_validos(estudio_usos: Mapping[str, Sequence[str]], registro: RegistroNormativo,
                     formatos: Formatos | None, fecha: str | None = None) -> set[Destino]:
    """Lo que puede afectar una observación de este estudio: las tablas del registro, los formatos A y B del anexo 2
    transcrito y los cálculos que el estudio declara en ``usos``. Nada sale del código."""
    tablas, _ = tablas_registradas(registro, fecha)
    validos = {Destino('tabla', t['numero']) for t in tablas}
    for f in (formatos.todos() if formatos is not None else ()):
        base = _PREFIJO.sub('', f.id)
        validos |= {Destino('formato', f'A-{base}'), Destino('formato', f'B-{base}')}
    validos |= {Destino('calculo', c) for usados in estudio_usos.values() for c in usados}
    return validos


def _destino(d: Any) -> Destino:
    if isinstance(d, Destino):
        return d
    if not isinstance(d, Mapping) or d.get('tipo') not in TIPOS_DESTINO or not str(d.get('id') or '').strip():
        raise VadError(f'un destino de la observación tiene que ser {{tipo, id}} con el tipo en {TIPOS_DESTINO}: {d!r}')
    return Destino(str(d['tipo']), str(d['id']).strip())


def _fecha(valor: Any) -> str:
    try:
        return date.fromisoformat(str(valor)).isoformat()
    except ValueError as exc:
        raise VadError(f'la fecha de la observación tiene que ser AAAA-MM-DD, no {valor!r}') from exc


def _ruta(espacio: Path | str, id_estudio: str) -> Path:
    return carpeta_estudio(espacio, id_estudio) / ARCHIVO


def cargar_observaciones(espacio: Path | str, id_estudio: str) -> list[Observacion]:
    """Las observaciones guardadas del estudio, en el orden en que se registraron; sin fichero, ninguna."""
    cargar_estudio(espacio, id_estudio)
    ruta = _ruta(espacio, id_estudio)
    if not ruta.is_file():
        return []
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    return [Observacion(**{**o, 'afecta': tuple(_destino(d) for d in o['afecta']), 'cambios': dict(o['cambios'])})
            for o in datos['observaciones']]


def _guardar(espacio: Path | str, id_estudio: str, obs: Sequence[Observacion]) -> None:
    write_json_atomic(_ruta(espacio, id_estudio), {
        'estudio': id_estudio,
        'observaciones': [{**asdict(o), 'afecta': [asdict(d) for d in o.afecta]} for o in obs]})


def _rechazar_destinos(afecta: Sequence[Destino], validos: set[Destino], numero: str) -> None:
    malos = [d.texto() for d in afecta if d not in validos]
    if malos:
        raise VadError(f'la observación {numero} apunta a lo que el estudio no tiene: {", ".join(malos)} (las tablas '
                       'salen del registro, los formatos del anexo 2 transcrito y los cálculos de los usos del estudio)')


def registrar_observacion(espacio: Path | str, id_estudio: str, *, numero: str, fecha: str, texto: str,
                          afecta: Sequence[Mapping[str, str] | Destino], registro: RegistroNormativo,
                          formatos: Formatos | None = None) -> Observacion:
    """Registra una observación del regulador, todavía sin respuesta. Su número no se repite, y lo que afecta tiene
    que existir en el estudio."""
    estudio = cargar_estudio(espacio, id_estudio)
    numero = str(numero or '').strip()
    if not numero:
        raise VadError('la observación necesita el número que le da el regulador')
    if not str(texto or '').strip():
        raise VadError(f'la observación {numero} no trae texto')
    destinos = tuple(_destino(d) for d in afecta)
    if not destinos:
        raise VadError(f'la observación {numero} no dice qué tabla o qué cálculo afecta')
    _rechazar_destinos(destinos, destinos_validos(estudio.usos, registro, formatos), numero)
    previas = cargar_observaciones(espacio, id_estudio)
    if any(o.numero == numero for o in previas):
        raise VadError(f'la observación {numero} ya está registrada en el estudio {id_estudio}')
    nueva = Observacion(numero=numero, fecha=_fecha(fecha), texto=str(texto).strip(), afecta=destinos)
    _guardar(espacio, id_estudio, [*previas, nueva])
    return nueva


def responder(espacio: Path | str, id_estudio: str, numero: str, *, respuesta: str, sustento: str,
              cambios: Mapping[str, str] | None = None) -> Observacion:
    """Guarda la respuesta de una observación con su sustento. ``cambios`` dice qué cambió en cada destino que la
    observación afecta (``'tabla 12'`` → texto); un cambio en un destino que la observación no afecta se rechaza."""
    previas = cargar_observaciones(espacio, id_estudio)
    actual = next((o for o in previas if o.numero == str(numero).strip()), None)
    if actual is None:
        raise VadError(f'el estudio {id_estudio} no tiene la observación {numero}')
    if not str(respuesta or '').strip() or not str(sustento or '').strip():
        raise VadError(f'la respuesta a la observación {numero} necesita su texto y su sustento')
    cambios = {str(k).strip(): str(v).strip() for k, v in (cambios or {}).items()}
    ajenos = sorted(set(cambios) - {d.texto() for d in actual.afecta})
    if ajenos:
        raise VadError(f'la respuesta a la observación {numero} cambia lo que la observación no afecta: '
                       f'{", ".join(ajenos)}')
    vacios = sorted(k for k, v in cambios.items() if not v)
    if vacios:
        raise VadError(f'la respuesta a la observación {numero} no dice qué cambió en: {", ".join(vacios)}')
    nueva = replace(actual, respuesta=str(respuesta).strip(), sustento=str(sustento).strip(), cambios=cambios)
    _guardar(espacio, id_estudio, [nueva if o.numero == actual.numero else o for o in previas])
    return nueva


def pendientes(espacio: Path | str, id_estudio: str) -> list[Observacion]:
    """Las observaciones que todavía no tienen respuesta."""
    return [o for o in cargar_observaciones(espacio, id_estudio) if o.estado == 'pendiente']
