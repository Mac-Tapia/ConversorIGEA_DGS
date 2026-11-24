"""La puerta del aprendizaje en alimentadores no vistos y la orden que lo confirma en DIgSILENT (spec 074, T8).

El 2026-11-21 el bloque de GPU informó que nada aplicaba ``puerta_del_aprendizaje`` sobre redes que el modelo no
vio: la política GATv2 se medía en la misma red de su entrenamiento. Aquí se declara la separación, se sella con su
huella antes de aplicar (si cambia después, la puerta no corre: elegir los no vistos tras ver el resultado sería
medir a favor) y se decide «pasa» o «archivar» con la medida de cada red (074:RF-6, RF-13, RF-14).

Nada de aquí escribe en DIgSILENT: lo que pasa se confirma por la ruta de la spec 011 en la web, solo en un proyecto
de prueba (074:RF-10). El piloto que no pasa se archiva con su medida, sin integrarlo en el flujo.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..dominio.util import write_json_atomic
from ..dominio.util import sha256_file
from .madrl_obras import (
    Accion,
    ParametrosObras,
    puerta_del_aprendizaje,
    zonas_por_alimentador,
)

ESQUEMA_MODELO = 'convertersmartgrid-madrl-modelo-v1'
ESQUEMA_SEPARACION = 'convertersmartgrid-madrl-separacion-v1'
ESQUEMA_ORDEN = 'convertersmartgrid-madrl-confirmacion-v1'
#: Solo un proyecto cuyo nombre empieza así recibe las obras aprendidas: los proyectos trabajados no se tocan en una
#: prueba (como las copias ``PRUEBA064_`` de la restitución, spec 064).
PREFIJO_PRUEBA = 'PRUEBA'
#: Las obras del piloto son las de «Con proyecto» (spec 074, alcance).
CASO_OBRAS = 'Con proyecto'
SEPARACION = 'separacion.json'


class PuertaError(ValueError):
    """Una separación, un modelo o una orden con los que la puerta no se puede aplicar."""


def _huella(datos: Any) -> str:
    crudo = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=float).encode('utf-8')
    return hashlib.sha256(crudo).hexdigest()


def huella_grafo(grafo: Mapping[str, Any]) -> str:
    """La del contenido, no la del fichero: la misma red copiada con otro nombre sigue siendo vista."""
    return _huella(grafo)


# Auditoría D.2 (2026-11-24): la huella de un fichero es una sola, la de dominio/util; este nombre queda por quien lo llama.
huella_fichero = sha256_file


def alimentadores_de(grafo: Mapping[str, Any]) -> list[str]:
    """Los agentes de una red (074:RF-11): sus cabeceras, que dicen si un alimentador ya se vio en otra captura."""
    return sorted(zonas_por_alimentador(grafo))


def red_declarada(nombre: str, grafo: Mapping[str, Any]) -> dict[str, Any]:
    return {'nombre': nombre, 'huella': huella_grafo(grafo), 'alimentadores': alimentadores_de(grafo)}


def manifiesto_modelo(*, politica: str, ocultas: int, cabezas: int, parametros: ParametrosObras,
                      entrenamiento: Sequence[Mapping[str, Any]], huella_pesos: str, **extra: Any) -> dict[str, Any]:
    """Lo que el entrenamiento deja junto a los pesos: con qué redes se entrenó y con qué límites y costos."""
    from dataclasses import asdict

    return {'esquema': ESQUEMA_MODELO, 'politica': politica, 'ocultas': ocultas, 'cabezas': cabezas,
            'parametros': asdict(parametros), 'entrenamiento': [dict(r) for r in entrenamiento],
            'huella_pesos': huella_pesos, **extra}


def parametros_de(manifiesto: Mapping[str, Any]) -> ParametrosObras:
    """Los mismos límites y costos del entrenamiento: con otros, la puerta compararía otra cosa."""
    if manifiesto.get('esquema') != ESQUEMA_MODELO:
        raise PuertaError('El modelo no trae su manifiesto del piloto: entrénelo con --modelo-salida.')
    return ParametrosObras(**manifiesto['parametros'])


def sellar_separacion(manifiesto: Mapping[str, Any], no_vistos: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """La separación entre lo visto y lo no visto, comprobada y sellada antes de aplicar nada (074:RF-13)."""
    entrenamiento = list(manifiesto.get('entrenamiento') or [])
    if not entrenamiento:
        raise PuertaError('El modelo no dice con qué redes se entrenó: sin eso no hay alimentadores «no vistos».')
    if not no_vistos:
        raise PuertaError('Falta al menos una red no vista.')
    huellas = {r['huella'] for r in entrenamiento}
    vistos = {a for r in entrenamiento for a in r.get('alimentadores') or []}
    propios: set[str] = set()
    for red in no_vistos:
        if not red.get('alimentadores'):
            raise PuertaError(f"{red['nombre']}: la red no tiene ningún alimentador con fuente.")
        if red['huella'] in huellas:
            raise PuertaError(f"{red['nombre']}: es una de las redes del entrenamiento, no una no vista.")
        repetidos = sorted(vistos.intersection(red['alimentadores']))
        if repetidos:
            raise PuertaError(f"{red['nombre']}: {len(repetidos)} de sus alimentadores ya se vieron al entrenar, "
                              f"empezando por {repetidos[0]}.")
        dobles = sorted(propios.intersection(red['alimentadores']))
        if dobles:
            raise PuertaError(f"{red['nombre']}: repite alimentadores de otra red no vista, empezando por {dobles[0]}.")
        propios.update(red['alimentadores'])
    datos = {'esquema': ESQUEMA_SEPARACION, 'modelo': manifiesto['huella_pesos'], 'parametros': manifiesto['parametros'],
             'entrenamiento': entrenamiento, 'no_vistos': [dict(r) for r in no_vistos]}
    return {**datos, 'sello': _huella(datos)}


def sello_valido(separacion: Mapping[str, Any]) -> bool:
    datos = {k: v for k, v in separacion.items() if k != 'sello'}
    return bool(separacion.get('sello')) and separacion['sello'] == _huella(datos)


def fijar_separacion(carpeta: Path, separacion: Mapping[str, Any]) -> dict[str, Any]:
    """Escribe la separación sellada; si la carpeta ya tiene otra, no la cambia: la puerta no corre con ella."""
    ruta = Path(carpeta) / SEPARACION
    if ruta.is_file():
        previa = json.loads(ruta.read_text(encoding='utf-8'))
        if not sello_valido(previa):
            raise PuertaError(f'{ruta}: la separación guardada no conserva su sello; use una carpeta nueva.')
        if previa['sello'] != separacion['sello']:
            raise PuertaError(f'{ruta}: ya hay otra separación sellada en esta carpeta; los no vistos no se cambian '
                              'después de aplicar, use una carpeta nueva.')
        return previa
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    write_json_atomic(ruta, separacion)
    return dict(separacion)


def _partes(ident: str) -> tuple[str, str] | None:
    """``ElmTerm:…\\<alimentador>.ElmNet\\<barra>.ElmTerm`` → (alimentador, barra); otra forma no se adivina."""
    _clase, _sep, ruta = str(ident).partition(':')
    trozos = [t for t in ruta.replace('/', '\\').split('\\') if t]
    redes = [t for t in trozos[:-1] if t.endswith('.ElmNet')]
    if not trozos or not redes or '.' not in trozos[-1]:
        return None
    return redes[-1].removesuffix('.ElmNet'), trozos[-1].rsplit('.', 1)[0]


def obra_de(accion: Accion, p: ParametrosObras) -> dict[str, Any] | None:
    """La obra como la guarda la web (``Obra.a_dict`` de la spec 011), o ``None`` si su ruta no dice dónde va."""
    partes = _partes(accion.elemento)
    if partes is None:
        return None
    alimentador, nombre = partes
    if accion.tipo == 'banco':
        return {'clase': 'condensador', 'alimentador': alimentador, 'casos': [CASO_OBRAS], 'barra': nombre,
                'q_kvar': round(p.banco_mvar * 1000, 3), 'escalones': 1}
    if accion.tipo == 'terna':
        return {'clase': 'terna', 'alimentador': alimentador, 'casos': [CASO_OBRAS], 'tramos': [nombre]}
    return None


def decidir(separacion: Mapping[str, Any], medidas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """«pasa» o «archivar», con la medida de cada red no vista y el sello de su separación (074:RF-6, RF-14)."""
    if not sello_valido(separacion):
        raise PuertaError('La separación no conserva su sello: la puerta no se aplica.')
    nombres = [r['nombre'] for r in separacion['no_vistos']]
    if [m['nombre'] for m in medidas] != nombres:
        raise PuertaError('Las redes medidas no son las de la separación sellada.')
    puerta = puerta_del_aprendizaje([m['aprendido'] for m in medidas], [m['referencia'] for m in medidas])
    decision = 'pasa' if puerta['sigue'] else 'archivar'
    return {'decision': decision, 'puerta': puerta, 'sello_separacion': separacion['sello'],
            'modelo': separacion['modelo'], 'medidas': [dict(m) for m in medidas],
            'integrado_en_flujo': False,
            'siguiente': ('confirmar en DIgSILENT, en un proyecto de prueba, por la ruta de las obras de la web'
                          if decision == 'pasa' else 'el piloto se archiva con esta medida, sin integrarlo en el flujo')}


def exigir_proyecto_de_prueba(espacio: str, proyecto: str) -> str:
    """El proyecto donde se confirma: uno de prueba, nunca uno ya trabajado; se comprueba antes de medir."""
    proyecto = str(proyecto or '').strip()
    if not proyecto.startswith(PREFIJO_PRUEBA):
        raise PuertaError(f'La confirmación va solo en un proyecto de prueba, cuyo nombre empieza por '
                          f'«{PREFIJO_PRUEBA}»: no en {proyecto!r}.')
    if not str(espacio or '').strip():
        raise PuertaError('Falta el espacio de trabajo de la web.')
    return proyecto


def orden_confirmacion(informe: Mapping[str, Any], *, espacio: str, proyecto: str) -> dict[str, Any]:
    """Los pasos de la web que confirman lo elegido en DIgSILENT: guardar las obras, simularlas y aplicarlas (074:RF-10)."""
    if informe.get('decision') != 'pasa':
        raise PuertaError('Solo se confirma en DIgSILENT lo que pasa la puerta; lo demás se archiva.')
    proyecto = exigir_proyecto_de_prueba(espacio, proyecto)
    obras, sin_sitio = [], []
    for m in informe['medidas']:
        for o in m.get('obras_aprendidas') or []:
            (obras if o.get('obra') else sin_sitio).append(o)
    if sin_sitio:
        raise PuertaError(f'{len(sin_sitio)} obras no dicen su alimentador ni su barra en DIgSILENT, empezando por '
                          f"{sin_sitio[0]['elemento']}: no se adivinan.")
    if not obras:
        raise PuertaError('Lo aprendido no elige ninguna obra: no hay nada que confirmar en DIgSILENT.')
    feeders = sorted({o['obra']['alimentador'] for o in obras})
    datos = {'esquema': ESQUEMA_ORDEN, 'sello_separacion': informe['sello_separacion'], 'modelo': informe['modelo'],
             'espacio': espacio, 'proyecto': proyecto, 'feeders': feeders, 'obras': [o['obra'] for o in obras],
             'pasos': ['POST /api/workspaces/{espacio}/obras, una por obra',
                       'POST /api/workspaces/{espacio}/pf/obras/simular con project, feeders e ids',
                       'POST /api/workspaces/{espacio}/pf/obras/aplicar con los mismos']}
    return {**datos, 'huella': _huella(datos)}


def orden_valida(orden: Mapping[str, Any], separacion: Mapping[str, Any]) -> None:
    """Antes de tocar DIgSILENT: la orden íntegra, de esta separación y para un proyecto de prueba."""
    datos = {k: v for k, v in orden.items() if k != 'huella'}
    if orden.get('esquema') != ESQUEMA_ORDEN or orden.get('huella') != _huella(datos):
        raise PuertaError('La orden de confirmación no conserva su huella: prepárela de nuevo con la puerta.')
    if not sello_valido(separacion) or orden['sello_separacion'] != separacion['sello']:
        raise PuertaError('La orden no es de la separación sellada de su carpeta.')
    if not str(orden.get('proyecto') or '').startswith(PREFIJO_PRUEBA):
        raise PuertaError(f'La confirmación va solo en un proyecto de prueba («{PREFIJO_PRUEBA}…»).')
