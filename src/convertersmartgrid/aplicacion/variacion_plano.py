"""La variación del plano (spec 111): lo que el operador propone sobre la red, guardado en el espacio y nunca en el
caso base.

- Una variación es un diario de ediciones con versión, la revisión de la red de la que parte (``plano_red.revision_red``)
  y el caso. Se guarda con la escritura atómica única en ``<espacio>/variaciones_plano/<id>.json`` (P6). El DGS, la
  geografía y la fuente nunca se escriben (111:RF-4, RF-5).
- Toda regla de la edición vive aquí, en el servidor; el navegador solo la pide (111:RF-15).
- Ediciones: abrir o cerrar una maniobra (RF-4) y trazar un tramo nuevo, con sus vértices tal como se dibujaron, la
  longitud GIS geodésica y la longitud eléctrica aparte (RF-5).
- Reglas de la edición (RF-6, RF-7): dos tramos solo se unen por un nodo o un equipo comunes, nunca por cruzarse
  en el plano; el ajuste de un extremo a un nodo cercano es una propuesta con su distancia, con el radio
  ``editor_ajuste_m`` del perfil (sin perfil, 5 m, y se dice), y solo se aplica confirmado.
- Equipos insertados (RF-8): tensión, fases y conexión validadas antes de aceptarlos; si algo falta, la respuesta lo
  lista y el equipo no entra.
- Diario (RF-9): deshacer y rehacer las ediciones mientras la variación no esté confirmada; al confirmarla, el diario
  queda cerrado.
- Una edición con una versión vieja o sobre otra revisión de la red es un conflicto: no se aplica y la variación se
  conserva, marcada si la revisión cambió (no se estudia).
"""
from __future__ import annotations

import json
import math
import re
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..dominio.util import write_json_atomic

CARPETA = 'variaciones_plano'
FORMATO = 'convertersmartgrid-variacion-plano-v1'
ESTADOS_MANIOBRA = ('abierto', 'cerrado')
#: Las clases de equipo que se pueden insertar en un tramo: las maniobras que el DGS escribe como StaSwitch.
CLASES_EQUIPO = ('seccionador', 'interruptor', 'reconectador', 'seccionalizador', 'fusible')
#: Radio de ajuste sin perfil (111:RF-7); la propuesta dice que es el de por defecto.
RADIO_AJUSTE_POR_DEFECTO_M = 5.0
#: Diferencia de tensión que aún es «la misma tensión» (redondeos de kV de la fuente).
_TOLERANCIA_KV = 0.01
_ID = re.compile(r'^[0-9a-f]{16}$')


class VariacionError(ValueError):
    """Una edición que no se acepta, con el motivo en una frase y, si aplica, la lista de lo que falta."""

    def __init__(self, motivo: str, *, faltan: list[str] | tuple[str, ...] = ()):
        super().__init__(motivo)
        self.faltan = list(faltan)


class ConflictoVariacion(VariacionError):
    """La versión o la revisión de la red cambiaron desde que se leyó la variación (la API responde 409)."""


def ruta_de(espacio: Path | str, vid: str) -> Path:
    if not _ID.match(str(vid)):
        raise VariacionError(f'Identificador de variación no válido: {vid!r}.')
    return Path(espacio) / CARPETA / f'{vid}.json'


def _guardar(espacio: Path | str, v: Mapping[str, Any]) -> None:
    ruta = ruta_de(espacio, v['id'])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(ruta, v)


def leer(espacio: Path | str, vid: str) -> dict[str, Any]:
    ruta = ruta_de(espacio, vid)
    if not ruta.is_file():
        raise VariacionError(f'No existe la variación {vid}.')
    return json.loads(ruta.read_text(encoding='utf-8'))


def listar(espacio: Path | str, *, alimentador: str | None = None) -> list[dict[str, Any]]:
    """Las variaciones guardadas en el espacio (de un alimentador, si se da), de la más antigua a la más reciente.

    Es lo guardado de verdad: el navegador puede recordar cuál miraba, pero la lista sale de aquí (111:RF-4).
    """
    carpeta = Path(espacio) / CARPETA
    filas = []
    for ruta in carpeta.glob('*.json') if carpeta.is_dir() else ():
        if not _ID.match(ruta.stem):
            continue
        v = json.loads(ruta.read_text(encoding='utf-8'))
        if alimentador is None or v.get('alimentador') == alimentador:
            filas.append((ruta.stat().st_mtime_ns, v['id'], v))
    return [v for _t, _i, v in sorted(filas, key=lambda f: (f[0], f[1]))]


def nueva(espacio: Path | str, *, revision: str, caso: str, alimentador: str) -> dict[str, Any]:
    """Abre una variación vacía sobre una revisión de la red y un caso."""
    v = {'formato': FORMATO, 'id': secrets.token_hex(8), 'alimentador': alimentador, 'caso': caso,
         'revision': revision, 'revision_cambiada': False, 'version': 0, 'estado': 'abierta',
         'ediciones': [], 'deshechas': []}
    _guardar(espacio, v)
    return v


def _comprobar_turno(espacio: Path | str, v: dict[str, Any], version: int, revision: str) -> None:
    if revision != v['revision']:
        v['revision_cambiada'] = True
        _guardar(espacio, v)
        raise ConflictoVariacion('La revisión de la red cambió desde que se abrió la variación: se conserva, sin '
                                 'estudiarse; ábrala de nuevo sobre la red actual.')
    if int(version) != int(v['version']):
        raise ConflictoVariacion(f'La variación va por la versión {v["version"]}, no por la {version}: '
                                 'vuelva a leerla antes de editar.')


def tramos_nuevos(vista: Mapping[str, Any], v: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Los tramos nuevos de la variación, con los ajustes confirmados ya aplicados a su extremo y a su vértice."""
    coordenadas = {b['codigo']: [b['lat'], b['lon']] for b in vista['barras'] if b['lat'] is not None}
    nuevos: dict[str, dict[str, Any]] = {}
    for e in v['ediciones']:
        if e['tipo'] == 'tramo':
            nuevos[e['codigo']] = {**e, 'vertices': [list(p) for p in e['vertices']]}
        elif e['tipo'] == 'ajuste':
            tramo = nuevos[e['tramo']]
            tramo[e['extremo']] = e['nodo']
            tramo[f"{e['extremo']}_nuevo"] = False
            tramo['vertices'][0 if e['extremo'] == 'desde' else -1] = coordenadas[e['nodo']]
    return nuevos


def _estado(vista: Mapping[str, Any], v: Mapping[str, Any]) -> dict[str, Any]:
    """Lo que la variación deja hasta ahora: estado de cada maniobra, nodos, tramos y equipos nuevos."""
    maniobras = {m['codigo']: m['estado'] for m in vista['maniobras']}
    nodos = {b['codigo'] for b in vista['barras']}
    tramos = {t['codigo']: t for t in vista['tramos']}
    nuevos = tramos_nuevos(vista, v)
    for e in v['ediciones']:
        if e['tipo'] == 'maniobra':
            maniobras[e['codigo']] = e['estado']
        elif e['tipo'] == 'equipo':
            maniobras[e['codigo']] = e['estado']
    for codigo, e in nuevos.items():
        nodos |= {e['desde'], e['hasta']}
        tramos[codigo] = e
    return {'maniobras': maniobras, 'nodos': nodos, 'tramos': tramos, 'tramos_nuevos': nuevos}


def _maniobra(edicion: Mapping[str, Any], estado: Mapping[str, Any]) -> dict[str, Any]:
    codigo = str(edicion.get('codigo') or '')
    if codigo not in estado['maniobras']:
        raise VariacionError(f'La maniobra {codigo!r} no está en el plano.')
    nuevo = edicion.get('estado')
    if nuevo not in ESTADOS_MANIOBRA:
        raise VariacionError(f'El estado de una maniobra es abierto o cerrado, no {nuevo!r}.')
    return {'tipo': 'maniobra', 'codigo': codigo, 'estado': nuevo, 'antes': estado['maniobras'][codigo]}


def longitud_gis_m(vertices: list[list[float]]) -> float:
    """La longitud geodésica (WGS84) de una polilínea de vértices ``[lat, lon]``."""
    from pyproj import Geod

    return float(Geod(ellps='WGS84').line_length([p[1] for p in vertices], [p[0] for p in vertices]))


def _vertices(valor: Any) -> list[list[float]]:
    if not isinstance(valor, (list, tuple)) or len(valor) < 2:
        raise VariacionError('Un tramo nuevo necesita al menos dos vértices.')
    salida = []
    for p in valor:
        try:
            lat, lon = (float(x) for x in p)
        except (TypeError, ValueError) as exc:
            raise VariacionError(f'Vértice no válido: {p!r}; cada uno es [latitud, longitud].') from exc
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise VariacionError(f'Vértice con coordenadas imposibles: {p!r}.')
        salida.append([lat, lon])
    return salida


def _tramo(edicion: Mapping[str, Any], vista: Mapping[str, Any], estado: Mapping[str, Any]) -> dict[str, Any]:
    codigo = str(edicion.get('codigo') or '').strip()
    if not codigo:
        raise VariacionError('Un tramo nuevo necesita su código.')
    if codigo in estado['tramos']:
        raise VariacionError(f'El tramo {codigo!r} ya existe en el plano.')
    desde = edicion.get('desde')
    if desde not in estado['nodos']:
        raise VariacionError(f'El nodo de origen {desde!r} no está en el plano.')
    hasta = edicion.get('hasta')
    if hasta is not None and hasta not in estado['nodos']:
        raise VariacionError(f'El nodo de destino {hasta!r} no está en el plano; déjelo vacío para crear uno.')
    vertices = _vertices(edicion.get('vertices'))
    conductor = edicion.get('conductor')
    if conductor not in vista['tipos_de_linea']:
        raise VariacionError(f'El conductor {conductor!r} no está en el catálogo de la red.')
    fases = str(edicion.get('fases') or '')
    if not fases or set(fases) - set('ABC') or len(set(fases)) != len(fases):
        raise VariacionError(f'Las fases de un tramo son letras A, B y C sin repetir, no {fases!r}.')
    electrica = edicion.get('longitud_electrica_m')
    if electrica is not None:
        if isinstance(electrica, bool) or not isinstance(electrica, (int, float)) \
                or not math.isfinite(electrica) or electrica <= 0:
            raise VariacionError(f'La longitud eléctrica tiene que ser un número positivo de metros, no {electrica!r}.')
        electrica = float(electrica)
    destino = hasta if hasta is not None else f'{codigo}_FIN'
    return {'tipo': 'tramo', 'codigo': codigo, 'desde': desde, 'hasta': destino, 'hasta_nuevo': hasta is None,
            'conecta': sorted({desde, destino}), 'cruza_sin_unir': cruces_sin_union(vertices, {desde, destino}, estado),
            'vertices': vertices, 'conductor': conductor, 'fases': ''.join(sorted(fases)),
            'longitud_gis_m': longitud_gis_m(vertices), 'longitud_electrica_m': electrica,
            'longitud_electrica_origen': 'operador' if electrica is not None else 'gis'}


def _orientacion(a: list[float], b: list[float], c: list[float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _se_cruzan(a: list[float], b: list[float], c: list[float], d: list[float]) -> bool:
    """Cruce propio de dos segmentos en el plano (tocarse en un extremo no es cruzarse)."""
    return (_orientacion(a, b, c) * _orientacion(a, b, d) < 0) and (_orientacion(c, d, a) * _orientacion(c, d, b) < 0)


def cruces_sin_union(vertices: list[list[float]], nodos: set[str], estado: Mapping[str, Any]) -> list[str]:
    """Los tramos del plano que la polilínea cruza sin compartir con ella un nodo (111:RF-6): se dicen y no se unen."""
    salida = []
    for codigo, tramo in estado['tramos'].items():
        if {tramo['desde'], tramo['hasta']} & nodos:
            continue
        otros = tramo.get('vertices') or []
        if any(_se_cruzan(a, b, c, d) for a, b in zip(vertices, vertices[1:]) for c, d in zip(otros, otros[1:])):
            salida.append(codigo)
    return sorted(salida)


def radio_ajuste(perfil: Mapping[str, Any] | None) -> tuple[float, str]:
    """El radio de ajuste: ``editor_ajuste_m`` del perfil o, sin él, el de por defecto (y se dice)."""
    valor = (perfil or {}).get('editor_ajuste_m')
    if isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor) and valor > 0:
        return float(valor), 'perfil'
    return RADIO_AJUSTE_POR_DEFECTO_M, 'por defecto'


def _distancia_m(a: list[float], b: list[float]) -> float:
    from pyproj import Geod

    return float(Geod(ellps='WGS84').inv(a[1], a[0], b[1], b[0])[2])


def proponer_ajuste(vista: Mapping[str, Any], v: Mapping[str, Any], punto: list[float], *,
                    perfil: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """111:RF-7 — el nodo del plano más cercano a ``punto`` como propuesta, si cae dentro del radio de ajuste.

    No cambia nada: devuelve el nodo (o ``None``), la distancia del desplazamiento y el radio con su origen.
    """
    punto = _vertices([punto, punto])[0]
    radio, origen = radio_ajuste(perfil)
    cercano, distancia = None, None
    for b in vista['barras']:
        if b['lat'] is None:
            continue
        d = _distancia_m(punto, [b['lat'], b['lon']])
        if distancia is None or d < distancia:
            cercano, distancia = b['codigo'], d
    dentro = distancia is not None and distancia <= radio
    return {'punto': punto, 'nodo': cercano if dentro else None, 'distancia_m': distancia if dentro else None,
            'mas_cercano': cercano, 'distancia_mas_cercano_m': distancia, 'radio_m': radio, 'radio_origen': origen}


def _ajuste(edicion: Mapping[str, Any], vista: Mapping[str, Any], estado: Mapping[str, Any],
            perfil: Mapping[str, Any] | None) -> dict[str, Any]:
    tramo = estado['tramos_nuevos'].get(edicion.get('tramo'))
    if tramo is None:
        raise VariacionError('Solo se ajusta el extremo de un tramo nuevo de esta variación.')
    extremo = edicion.get('extremo')
    if extremo not in ('desde', 'hasta'):
        raise VariacionError('El extremo que se ajusta es «desde» o «hasta».')
    barras = {b['codigo']: b for b in vista['barras'] if b['lat'] is not None}
    nodo = edicion.get('nodo')
    if nodo not in barras:
        raise VariacionError(f'El nodo {nodo!r} no está en el plano.')
    if edicion.get('confirmado') is not True:
        raise VariacionError('El ajuste es una propuesta: confírmelo para aplicarlo.')
    radio, origen = radio_ajuste(perfil)
    vertice = tramo['vertices'][0 if extremo == 'desde' else -1]
    distancia = _distancia_m(vertice, [barras[nodo]['lat'], barras[nodo]['lon']])
    if distancia > radio:
        raise VariacionError(f'El nodo está a {distancia:.1f} m, fuera del radio de ajuste ({radio:g} m, {origen}).')
    return {'tipo': 'ajuste', 'tramo': tramo['codigo'], 'extremo': extremo, 'nodo': nodo, 'antes': tramo[extremo],
            'desplazamiento_m': distancia, 'radio_m': radio, 'radio_origen': origen}


def _equipo(edicion: Mapping[str, Any], vista: Mapping[str, Any], estado: Mapping[str, Any]) -> dict[str, Any]:
    """111:RF-8 — un equipo entra solo con su clase, su tramo, su tensión, sus fases y su estado; si no, lista lo que falta."""
    faltan: list[str] = []
    codigo = str(edicion.get('codigo') or '').strip()
    if not codigo:
        faltan.append('código: falta')
    elif codigo in estado['maniobras']:
        faltan.append(f'código: {codigo} ya existe en el plano')
    clase = edicion.get('clase')
    if clase not in CLASES_EQUIPO:
        faltan.append(f'clase: una de {", ".join(CLASES_EQUIPO)}' + (f', no {clase!r}' if clase else ''))
    tramo = estado['tramos'].get(edicion.get('tramo'))
    if tramo is None:
        faltan.append('tramo: el tramo del plano donde se conecta' +
                      (f' ({edicion.get("tramo")!r} no está)' if edicion.get('tramo') else ''))
    extremo = edicion.get('extremo') or 'desde'
    if extremo not in ('desde', 'hasta'):
        faltan.append('extremo: «desde» o «hasta» del tramo')
    kv = edicion.get('tension_kv')
    if isinstance(kv, bool) or not isinstance(kv, (int, float)) or not math.isfinite(kv) or kv <= 0:
        faltan.append('tensión: la tensión nominal en kV')
    elif abs(float(kv) - float(vista['kv'])) > _TOLERANCIA_KV * float(vista['kv']):
        faltan.append(f'tensión: {kv:g} kV no es la de la red ({float(vista["kv"]):g} kV)')
    fases = str(edicion.get('fases') or '')
    if not fases:
        faltan.append('fases: faltan')
    elif set(fases) - set('ABC') or len(set(fases)) != len(fases):
        faltan.append(f'fases: letras A, B y C sin repetir, no {fases!r}')
    elif tramo is not None and set(fases) - set(tramo['fases']):
        faltan.append(f'fases: el tramo {tramo["codigo"]} solo tiene {tramo["fases"]}')
    if edicion.get('estado') not in ESTADOS_MANIOBRA:
        faltan.append('estado: el estado normal, abierto o cerrado')
    if faltan:
        raise VariacionError('El equipo no se acepta: ' + '; '.join(faltan) + '.', faltan=faltan)
    return {'tipo': 'equipo', 'codigo': codigo, 'clase': clase, 'tramo': tramo['codigo'], 'extremo': extremo,
            'barra': tramo[extremo], 'tension_kv': float(kv), 'fases': ''.join(sorted(fases)),
            'estado': edicion['estado']}


def _exigir_abierta(v: Mapping[str, Any], accion: str) -> None:
    if v['estado'] != 'abierta':
        raise VariacionError(f'La variación ya está confirmada: no {accion}.')


def editar(espacio: Path | str, vid: str, edicion: Mapping[str, Any], *, version: int, revision: str,
           vista: Mapping[str, Any], perfil: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Valida una edición contra la vista y lo ya editado, y la añade al diario con una versión más."""
    v = leer(espacio, vid)
    _comprobar_turno(espacio, v, version, revision)
    _exigir_abierta(v, 'se edita')
    estado = _estado(vista, v)
    tipo = edicion.get('tipo')
    if tipo == 'maniobra':
        normalizada = _maniobra(edicion, estado)
    elif tipo == 'tramo':
        normalizada = _tramo(edicion, vista, estado)
    elif tipo == 'ajuste':
        normalizada = _ajuste(edicion, vista, estado, perfil)
    elif tipo == 'equipo':
        normalizada = _equipo(edicion, vista, estado)
    else:
        raise VariacionError(f'Edición desconocida: {tipo!r}.')
    v['ediciones'].append(normalizada)
    v['deshechas'] = []
    v['version'] += 1
    _guardar(espacio, v)
    return v


def _paso_del_diario(espacio: Path | str, vid: str, version: int, revision: str, accion: str) -> dict[str, Any]:
    v = leer(espacio, vid)
    _comprobar_turno(espacio, v, version, revision)
    _exigir_abierta(v, accion)
    return v


def deshacer(espacio: Path | str, vid: str, *, version: int, revision: str) -> dict[str, Any]:
    """Quita la última edición de una variación sin confirmar; queda para rehacerla (111:RF-9)."""
    v = _paso_del_diario(espacio, vid, version, revision, 'se deshace')
    if not v['ediciones']:
        raise VariacionError('No hay ninguna edición que deshacer.')
    v['deshechas'].append(v['ediciones'].pop())
    v['version'] += 1
    _guardar(espacio, v)
    return v


def rehacer(espacio: Path | str, vid: str, *, version: int, revision: str) -> dict[str, Any]:
    """Devuelve la última edición deshecha; una edición nueva vacía lo que se podía rehacer (111:RF-9)."""
    v = _paso_del_diario(espacio, vid, version, revision, 'se rehace')
    if not v['deshechas']:
        raise VariacionError('No hay ninguna edición que rehacer.')
    v['ediciones'].append(v['deshechas'].pop())
    v['version'] += 1
    _guardar(espacio, v)
    return v


def confirmar(espacio: Path | str, vid: str, *, version: int, revision: str) -> dict[str, Any]:
    """Cierra el diario: la variación queda confirmada y ya no se edita, deshace ni rehace (111:RF-9)."""
    v = _paso_del_diario(espacio, vid, version, revision, 'se confirma otra vez')
    v['estado'] = 'confirmada'
    v['deshechas'] = []
    v['version'] += 1
    _guardar(espacio, v)
    return v
