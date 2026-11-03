"""Contrato del episodio del gemelo digital (spec 024, T1).

Un episodio es la evidencia de un trabajo fuente–DIgSILENT: de qué fuente salió, en qué
proyecto y caso se hizo, qué dio el flujo y si se acepta. Se guarda como JSON canónico y
su identificador es la huella SHA-256 del contenido, para que el búfer sea inmutable e
idempotente (RF-6): el mismo trabajo registrado dos veces es un solo episodio.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from ..util import esquema_vigente

#: Esquema con que se escriben los episodios nuevos (045:RF-1). El v1 solo se lee, y tal cual: su huella
#: es su identidad en el búfer y sale del contenido guardado (045:RF-2).
ESQUEMA = 'convertersmartgrid-digital-twin-episode-v2'
ESQUEMA_V1 = 'convertersmartgrid-digital-twin-episode-v1'


class Clase(StrEnum):
    """Clasificación del episodio en el búfer (RF-4, RF-5, RF-9)."""

    ACCEPTED = 'accepted'
    CONVERGED_WITH_VIOLATIONS = 'converged_with_violations'
    REJECTED = 'rejected'
    COUNTERFACTUAL = 'counterfactual'
    QUARANTINE = 'quarantine'


class Caso(StrEnum):
    """Caso de estudio: cada uno se evalúa con su criterio (RF-29 a RF-31)."""

    CASO_BASE = 'caso_base'
    SIN_PROYECTO = 'sin_proyecto'
    CON_PROYECTO = 'con_proyecto'
    CARGAS_NUEVAS = 'cargas_nuevas'


#: Los casos que conoce el esquema v1; «Cargas nuevas» (spec 037) solo existe desde el v2.
CASOS_V1 = (Caso.CASO_BASE, Caso.SIN_PROYECTO, Caso.CON_PROYECTO)

#: Lo que sale del flujo de potencia en los tres casos, con la misma definición (RF-28).
RESULTADOS_FLUJO = ('balance', 'perdidas', 'cargabilidad', 'tensiones', 'confiabilidad')

#: Alternativas de solución del PIDE, de menor a mayor intervención (RF-32). El orden de
#: prioridad que se aplica sale del perfil; esta lista solo dice cuáles existen.
ALTERNATIVAS_PIDE = ('bancos', 'reguladores', 'cambio_seccion', 'nueva_terna', 'refuerzo_red',
                     'nueva_sed', 'nuevo_alimentador', 'nueva_set')

#: Indicadores del Anexo N.º 6 que acompañan a cada obra; pueden faltar (``None``).
INDICADORES_OBRA = ('coste', 'van', 'tir', 'retorno_anios')

#: Campos de primer nivel obligatorios; ``episode_id`` es opcional en la entrada.
CAMPOS = ('schema', 'clase', 'caso', 'creado', 'fuente', 'nativo', 'accion', 'topologia',
          'flujo', 'aceptacion', 'obras', 'artefactos')
#: El v2 añade los controles y el caso nativo de la lectura (045:RF-3, RF-10).
CAMPOS_V2 = (*CAMPOS, 'contexto_fisico')
#: Las huellas de ``experimentos.ContextoExperimento`` que trae ``contexto_fisico``.
HUELLAS_CONTEXTO = ('topology_hash', 'controls_hash', 'scenario_hash')

_SHA256 = re.compile(r'^[0-9a-f]{64}$')


class EpisodioInvalido(ValueError):
    """Episodio que no cumple el contrato; ``campo`` es la ruta de lo que falla."""

    def __init__(self, campo: str, motivo: str):
        super().__init__(f'{campo}: {motivo}')
        self.campo = campo


@dataclass(frozen=True)
class Artefacto:
    """Fichero que respalda el episodio (plan, resultado, lectura nativa)."""

    rol: str
    ruta: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class Episodio:
    esquema: str
    episode_id: str
    clase: Clase
    caso: Caso
    creado: str
    fuente: dict[str, Any]
    nativo: dict[str, Any]
    accion: dict[str, Any]
    topologia: dict[str, Any]
    flujo: dict[str, Any]
    aceptacion: dict[str, Any]
    obras: tuple[dict[str, Any], ...]
    artefactos: tuple[Artefacto, ...]
    contexto_fisico: dict[str, Any] | None = None


def contenido_canonico(payload: dict[str, Any]) -> str:
    """JSON con las claves ordenadas: el orden de un diccionario no cambia el episodio, el
    de una lista sí (el de los alimentadores expresa la orientación, RF-2)."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False)


def huella_episodio(payload: dict[str, Any]) -> str:
    """SHA-256 del contenido sin su propio identificador."""
    sin_id = {k: v for k, v in payload.items() if k != 'episode_id'}
    return hashlib.sha256(contenido_canonico(sin_id).encode('utf-8')).hexdigest()


def _dict(payload: dict, campo: str) -> dict:
    valor = payload.get(campo)
    if not isinstance(valor, dict):
        raise EpisodioInvalido(campo, 'falta o no es un objeto')
    return valor


def _texto(bloque: dict, clave: str, ruta: str) -> str:
    valor = bloque.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise EpisodioInvalido(f'{ruta}.{clave}', 'falta o está vacío')
    return valor


def _sha(valor: Any, ruta: str) -> str:
    if not isinstance(valor, str) or not _SHA256.match(valor):
        raise EpisodioInvalido(ruta, 'no es una huella SHA-256 en hexadecimal')
    return valor


def _enum(tipo, valor: Any, campo: str):
    try:
        return tipo(valor)
    except ValueError:
        raise EpisodioInvalido(campo, f'«{valor}» no es uno de {[e.value for e in tipo]}') from None


def _validar_flujo(flujo: dict) -> None:
    """Cada resultado tiene unidad y valores, o dice por qué falta (RF-28): un hueco callado
    se confundiría con un cero."""
    for clave in RESULTADOS_FLUJO:
        ruta = f'flujo.{clave}'
        bloque = flujo.get(clave)
        if not isinstance(bloque, dict):
            raise EpisodioInvalido(ruta, 'falta: dé su valor o el motivo en «ausente»')
        if 'ausente' in bloque:
            _texto(bloque, 'ausente', ruta)
            continue
        _texto(bloque, 'unidad', ruta)
        if not isinstance(bloque.get('valores'), dict):
            raise EpisodioInvalido(f'{ruta}.valores', 'falta o no es un objeto')


def _validar_obras(obras: Any, caso: Caso) -> tuple[dict, ...]:
    if not isinstance(obras, list):
        raise EpisodioInvalido('obras', 'no es una lista')
    if obras and caso is Caso.CASO_BASE:
        raise EpisodioInvalido('obras', 'el «Caso base» es la red tal como está: no lleva obras')
    if obras and caso is Caso.CARGAS_NUEVAS:
        raise EpisodioInvalido('obras', '«Cargas nuevas» es un diagnóstico sin obras (045:RF-1)')
    for i, obra in enumerate(obras):
        ruta = f'obras[{i}]'
        if not isinstance(obra, dict):
            raise EpisodioInvalido(ruta, 'no es un objeto')
        if obra.get('alternativa') not in ALTERNATIVAS_PIDE:
            raise EpisodioInvalido(f'{ruta}.alternativa',
                                   f'«{obra.get("alternativa")}» no es una alternativa del PIDE')
        _texto(obra, 'elemento', ruta)
        for indicador in INDICADORES_OBRA:
            valor = obra.get(indicador)
            if valor is not None and (isinstance(valor, bool) or not isinstance(valor, int | float)):
                raise EpisodioInvalido(f'{ruta}.{indicador}', 'no es un número')
    return tuple(obras)


def _validar_artefactos(artefactos: Any) -> tuple[Artefacto, ...]:
    if not isinstance(artefactos, list):
        raise EpisodioInvalido('artefactos', 'no es una lista')
    leidos: list[Artefacto] = []
    roles: set[str] = set()
    for i, a in enumerate(artefactos):
        ruta = f'artefactos[{i}]'
        if not isinstance(a, dict):
            raise EpisodioInvalido(ruta, 'no es un objeto')
        rol = _texto(a, 'rol', ruta)
        if rol in roles:
            raise EpisodioInvalido(f'{ruta}.rol', f'rol «{rol}» repetido')
        roles.add(rol)
        tam = a.get('bytes')
        if isinstance(tam, bool) or not isinstance(tam, int) or tam < 0:
            raise EpisodioInvalido(f'{ruta}.bytes', 'no es un tamaño en bytes')
        leidos.append(Artefacto(rol, _texto(a, 'ruta', ruta), _sha(a.get('sha256'), f'{ruta}.sha256'),
                                tam))
    return tuple(leidos)


def _validar_contexto_fisico(contexto: Any, caso: Caso, clase: Clase) -> dict[str, Any]:
    """045:RF-1, RF-3: el rol y la identidad del caso nativo, con sus huellas, o por qué faltan."""
    if not isinstance(contexto, dict):
        raise EpisodioInvalido('contexto_fisico', 'falta o no es un objeto')
    if 'ausente' in contexto:
        _texto(contexto, 'ausente', 'contexto_fisico')
        if clase is Clase.ACCEPTED:
            raise EpisodioInvalido('contexto_fisico', 'un episodio aceptado exige los controles y el caso nativo')
        return contexto
    _texto(contexto, 'case_id', 'contexto_fisico')
    if contexto.get('case_role') != caso.value:
        raise EpisodioInvalido('contexto_fisico.case_role',
                               f'«{contexto.get("case_role")}» no es el caso del episodio («{caso.value}»)')
    for clave in HUELLAS_CONTEXTO:
        _sha(contexto.get(clave), f'contexto_fisico.{clave}')
    return contexto


def leer_episodio(payload: dict[str, Any]) -> Episodio:
    """Valida ``payload`` contra el contrato de su esquema y devuelve el episodio con su huella.

    Lanza ``EpisodioInvalido`` con la ruta del primer campo que falla (RF-7, RF-9). El esquema se
    conserva como está escrito (045:RF-2): normalizarlo cambiaría la huella de lo guardado.
    """
    if not isinstance(payload, dict):
        raise EpisodioInvalido('', 'el episodio no es un objeto')
    vigente = esquema_vigente(payload.get('schema'))
    if vigente not in (ESQUEMA, ESQUEMA_V1):
        raise EpisodioInvalido('schema', f'se esperaba «{ESQUEMA}» o «{ESQUEMA_V1}»')
    es_v2 = vigente == ESQUEMA
    for campo in CAMPOS_V2 if es_v2 else CAMPOS:
        if campo not in payload:
            raise EpisodioInvalido(campo, 'falta')
    clase = _enum(Clase, payload['clase'], 'clase')
    caso = _enum(Caso, payload['caso'], 'caso')
    if not es_v2 and caso not in CASOS_V1:
        raise EpisodioInvalido('caso', f'el esquema v1 no conoce el caso «{caso.value}»')
    if caso is Caso.CARGAS_NUEVAS and clase is Clase.ACCEPTED:
        # Son las cargas sin obras: dato físico para aprender, nunca una obra aceptada (045:RF-1).
        raise EpisodioInvalido('clase', '«Cargas nuevas» es un diagnóstico: no se acepta como obra')
    if not isinstance(payload['creado'], str) or not payload['creado']:
        raise EpisodioInvalido('creado', 'falta la fecha')

    fuente = _dict(payload, 'fuente')
    for clave in ('source_run_id', 'source_mode'):
        _texto(fuente, clave, 'fuente')
    _sha(fuente.get('source_fingerprint'), 'fuente.source_fingerprint')

    nativo = _dict(payload, 'nativo')
    _texto(nativo, 'project', 'nativo')
    feeders = nativo.get('feeders')
    if (not isinstance(feeders, list) or not feeders
            or not all(isinstance(f, str) and f for f in feeders)):
        raise EpisodioInvalido('nativo.feeders', 'falta la lista de alimentadores')
    # Sin reapertura y relectura no hay aceptación (contrato mínimo de la spec).
    if clase is Clase.ACCEPTED and nativo.get('reopen_verified') is not True:
        raise EpisodioInvalido('nativo.reopen_verified',
                               'un episodio aceptado exige reabrir y releer el proyecto')

    accion, topologia, aceptacion = (_dict(payload, c) for c in ('accion', 'topologia', 'aceptacion'))
    flujo = _dict(payload, 'flujo')
    _validar_flujo(flujo)
    obras = _validar_obras(payload['obras'], caso)
    artefactos = _validar_artefactos(payload['artefactos'])
    contexto = _validar_contexto_fisico(payload['contexto_fisico'], caso, clase) if es_v2 else None

    huella = huella_episodio(payload)
    if 'episode_id' in payload and payload['episode_id'] != huella:
        raise EpisodioInvalido('episode_id', 'no es la huella de su contenido')
    return Episodio(payload['schema'], huella, clase, caso, payload['creado'], fuente, nativo, accion,
                    topologia, flujo, aceptacion, obras, artefactos, contexto)


def episodio_a_dict(episodio: Episodio) -> dict[str, Any]:
    """Forma JSON del episodio, la que se guarda en el búfer."""
    return {
        **({} if episodio.contexto_fisico is None else {'contexto_fisico': episodio.contexto_fisico}),
        'schema': episodio.esquema, 'episode_id': episodio.episode_id,
        'clase': episodio.clase.value, 'caso': episodio.caso.value, 'creado': episodio.creado,
        'fuente': episodio.fuente, 'nativo': episodio.nativo, 'accion': episodio.accion,
        'topologia': episodio.topologia, 'flujo': episodio.flujo,
        'aceptacion': episodio.aceptacion, 'obras': list(episodio.obras),
        'artefactos': [{'rol': a.rol, 'ruta': a.ruta, 'sha256': a.sha256, 'bytes': a.bytes}
                       for a in episodio.artefactos],
    }
