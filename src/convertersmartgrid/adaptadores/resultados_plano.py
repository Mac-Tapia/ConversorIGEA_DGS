"""Los resultados sobre el plano (spec 111): el estudio de una variación y lo que se pinta en el mismo trazo.

- Elección del motor (111:RF-17): DIgSILENT si hay licencia y el proyecto está vinculado a la ejecución de la fuente
  que se ve en el plano; si no, el motor abierto (pandapower). El resultado siempre dice cuál (RF-18).
- Motor abierto (RF-10, RF-11): la variación se aplica a una copia derivada del modelo (``dataclasses.replace``),
  nunca al modelo, al dataset ni a la geografía; el flujo es ``oraculo.resultados_por_elemento``. Sin convergencia no
  hay nada que pintar, y se dan los mensajes del motor. Cada resultado lleva el motor, el caso, la revisión de la red
  y la versión de la variación.
- Capas (RF-10, RF-13, RF-18): tensión por barra, corriente y cargabilidad por tramo y estado de cada equipo, con su
  unidad, su umbral (del perfil o el de por defecto, dicho), el caso, la revisión y el motor. Un incumplimiento lleva
  texto, icono, valor y umbral, no solo color. Los resultados de DIgSILENT se traducen por la identidad del plano, y
  nada se pinta si el caso o la revisión no coinciden.
- Comparación (RF-12, RF-19): dos casos por elemento sobre el mismo plano, con aviso si los motores son distintos.
- Plan de DIgSILENT (RF-2, RF-4): las ediciones de una variación con los nombres de la identidad del plano, para
  ``tools/variacion_plano_pf.py``, que las estudia en una copia del caso y lo borra todo al terminar.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from .dgs import letras_de_fase, nombre_en_pf
from ..aplicacion.estudios_pf import Limites
from ..dominio.model import FeederModel, Line, Node, SwitchingDevice
from .oraculo import resultados_por_elemento
from .plano_red import codigo_de_nombre
from ..aplicacion.variacion_plano import ConflictoVariacion, tramos_nuevos

#: Los motores que pueden dar un resultado, con las palabras que ve el operador.
MOTORES = {'DIgSILENT': 'DIgSILENT', 'abierto': 'motor abierto (pandapower)'}


#: 111:RF-29: lo que el operador puede pedir; «automatico» es la elección de siempre (RF-17).
PEDIDOS = ('automatico', 'abierto', 'DIgSILENT')


def elegir_motor(*, licencia: bool, vinculado: bool, pedido: str | None = None) -> dict[str, Any]:
    """DIgSILENT si está disponible y el proyecto está vinculado a esta red; si no, el motor abierto, con su motivo.

    ``licencia`` es que DIgSILENT esté disponible en el equipo (su API y el Python que pide); la licencia en sí solo se
    sabe al conectar (111:RF-29: el motivo decía «no hay licencia» cuando faltaba la instalación). Con ``pedido``, el
    operador elige: el abierto siempre; DIgSILENT solo si se puede, y si no, un error con su motivo (``ValueError``),
    nunca un cambio de motor callado.
    """
    puede = bool(licencia and vinculado)
    motivo = ('DIgSILENT está disponible y el proyecto está vinculado a la red cargada' if puede else
              'DIgSILENT no está disponible en este equipo' if not licencia
              else 'el proyecto de DIgSILENT no está vinculado a la red cargada')
    pedido = pedido or 'automatico'
    if pedido not in PEDIDOS:
        raise ValueError(f'motor {pedido!r} desconocido; elija entre {", ".join(PEDIDOS)}')
    if pedido == 'DIgSILENT' and not puede:
        raise ValueError(f'No se puede estudiar con DIgSILENT: {motivo}. Estudie con el motor abierto.')
    motor = 'abierto' if pedido == 'abierto' or not puede else 'DIgSILENT'
    if pedido != 'automatico':
        motivo = f'elegido por el operador ({motivo})' if motor == 'DIgSILENT' else 'elegido por el operador'
    return {'motor': motor, 'texto': MOTORES[motor], 'motivo': motivo, 'digsilent_posible': puede}


def _fase_de(model: FeederModel, letras: str, nodo: str) -> str:
    """Un código de fase de la fuente con esas letras: el de un tramo que las tenga, o el de un tramo del nodo."""
    for ln in model.lines:
        if letras_de_fase(ln.phase) == letras:
            return ln.phase
    vecino = next((ln for ln in model.lines if nodo in (ln.from_node, ln.to_node)), None)
    return vecino.phase if vecino is not None else (model.lines[0].phase if model.lines else '')


def aplicar_variacion(model: FeederModel, vista: Mapping[str, Any], variacion: Mapping[str, Any]) -> FeederModel:
    """Una copia del modelo con la variación aplicada: maniobras, tramos nuevos y equipos. El modelo no cambia."""
    estados: dict[str, str] = {}
    equipos = []
    for e in variacion['ediciones']:
        if e['tipo'] in ('maniobra', 'equipo'):
            estados[e['codigo']] = e['estado']
        if e['tipo'] == 'equipo':
            equipos.append(e)
    nodos = dict(model.nodes)
    lineas = list(model.lines)
    for t in tramos_nuevos(vista, variacion).values():
        for n in (t['desde'], t['hasta']):
            nodos.setdefault(n, Node(n, None, None, coord_inferida=True))
        largo = t['longitud_electrica_m'] if t['longitud_electrica_m'] is not None else t['longitud_gis_m']
        lineas.append(Line(section_id=t['codigo'], from_node=t['desde'], to_node=t['hasta'],
                           phase=_fase_de(model, t['fases'], t['desde']), type_key=t['conductor'],
                           source_type_code=t['conductor'], length_m=float(largo), overhead=True,
                           length_source='txt' if t['longitud_electrica_m'] is not None else 'georef'))
    por_tramo = {ln.section_id: ln for ln in lineas}

    def _estado(d: SwitchingDevice) -> SwitchingDevice:
        codigo = d.eq_number or d.eq_id or d.section_id
        return dataclasses.replace(d, on_off=1 if estados[codigo] == 'cerrado' else 0) if codigo in estados else d

    dispositivos = [_estado(d) for d in model.devices]
    for e in equipos:
        dispositivos.append(SwitchingDevice(
            kind=e['clase'], section_id=e['tramo'], location='', terminal_side=0 if e['extremo'] == 'desde' else 1,
            node_id=e['barra'], eq_id=e['codigo'], eq_number=e['codigo'], phase=por_tramo[e['tramo']].phase,
            on_off=1 if estados[e['codigo']] == 'cerrado' else 0, locked=0, eq_state=0,
            feeder=model.name, network_id=model.network_id))
    return dataclasses.replace(model, nodes=nodos, lines=lineas, devices=dispositivos,
                               section_by_id={**model.section_by_id, **{ln.section_id: ln for ln in lineas}})


def estudiar(model: FeederModel, vista: Mapping[str, Any], variacion: Mapping[str, Any] | None, *,
             caso: str | None = None, revision: str | None = None) -> dict[str, Any]:
    """El estudio con el motor abierto de una variación (o del caso, sin variación), por elemento.

    Una variación marcada porque la revisión de la red cambió no se estudia (RF-11).
    """
    if variacion is not None and variacion.get('revision_cambiada'):
        raise ConflictoVariacion('La variación se abrió sobre otra revisión de la red: no se estudia.')
    copia = aplicar_variacion(model, vista, variacion) if variacion is not None else model
    return {'motor': 'abierto', 'motor_texto': MOTORES['abierto'], 'alimentador': model.name,
            'caso': variacion['caso'] if variacion is not None else caso,
            'revision': variacion['revision'] if variacion is not None else revision,
            'variacion': variacion['id'] if variacion is not None else None,
            'version': variacion['version'] if variacion is not None else None,
            **resultados_por_elemento(copia)}


def plan_pf(vista: Mapping[str, Any], variacion: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Las ediciones de la variación con sus nombres en DIgSILENT, en el orden del diario (111:RF-2, RF-4).

    Los nombres salen de la identidad del plano (``nombre_pf`` de la vista) o, para lo nuevo, de ``dgs.nombre_en_pf``;
    nunca de otra regla. Un tramo nuevo va con sus ajustes confirmados ya aplicados y toma el tipo de un tramo del plano
    con el mismo conductor. Los ajustes no van aparte: ya están en su tramo.
    """
    def nombre(tabla: str, codigo: str) -> str:
        return next((e['nombre_pf'] for e in vista[tabla] if e['codigo'] == codigo), nombre_en_pf(codigo))

    nuevos = tramos_nuevos(vista, variacion)
    salida: list[dict[str, Any]] = []
    for e in variacion['ediciones']:
        if e['tipo'] == 'maniobra':
            salida.append({'tipo': 'maniobra', 'codigo': e['codigo'], 'nombre_pf': nombre('maniobras', e['codigo']),
                           'estado': e['estado']})
        elif e['tipo'] == 'tramo':
            t = nuevos[e['codigo']]
            modelo = next((x for x in sorted(vista['tramos'], key=lambda x: x['codigo'])
                           if x.get('tipo') == t['conductor']), None)
            if modelo is None:
                raise ConflictoVariacion(f'Ningún tramo del plano tiene el conductor {t["conductor"]}: '
                                         'DIgSILENT no tiene de dónde tomar su tipo.')
            largo = t['longitud_electrica_m'] if t['longitud_electrica_m'] is not None else t['longitud_gis_m']
            salida.append({'tipo': 'tramo', 'codigo': t['codigo'], 'nombre_pf': nombre_en_pf(t['codigo']),
                           'desde_pf': nombre('barras', t['desde']), 'hasta_pf': nombre('barras', t['hasta']),
                           'hasta_nuevo': bool(t.get('hasta_nuevo')), 'vertices': [list(p) for p in t['vertices']],
                           'longitud_km': float(largo) / 1000.0, 'tipo_de_tramo_pf': modelo['nombre_pf'],
                           'fases': t['fases']})
        elif e['tipo'] == 'equipo':
            salida.append({'tipo': 'equipo', 'codigo': e['codigo'], 'nombre_pf': nombre_en_pf(e['codigo']),
                           'clase': e['clase'], 'tramo_pf': nombre('tramos', e['tramo']), 'extremo': e['extremo'],
                           'estado': e['estado']})
    return salida


# ---------------------------------------------------------------------------- capas (111:RF-10, RF-13)

ICONO_INCUMPLE = 'alerta'


def _numero(x: float) -> str:
    """Un número como lo lee el operador: hasta cuatro decimales y coma decimal."""
    return f'{x:.4f}'.rstrip('0').rstrip('.').replace('.', ',')


def _banda_tension(u: float | None, limites: Limites) -> str:
    if u is None:
        return 'sin_tension'
    return 'baja' if u < limites.tension_min_pu else ('alta' if u > limites.tension_max_pu else 'normal')


def _banda_carga(c: float | None, limites: Limites) -> str:
    if c is None:
        return 'sin_valor'
    return 'sobrecarga' if c > limites.cargabilidad_max_pct else 'normal'


def _incumple_tension(u: float | None, limites: Limites) -> dict[str, Any] | None:
    banda = _banda_tension(u, limites)
    if banda not in ('baja', 'alta'):
        return None
    umbral = limites.tension_min_pu if banda == 'baja' else limites.tension_max_pu
    texto = (f'Tensión baja: {_numero(u)} p.u., por debajo del mínimo de {_numero(umbral)} p.u.' if banda == 'baja'
             else f'Tensión alta: {_numero(u)} p.u., por encima del máximo de {_numero(umbral)} p.u.')
    return {'texto': texto, 'icono': ICONO_INCUMPLE, 'valor': u, 'umbral': umbral}


def _incumple_carga(c: float | None, limites: Limites) -> dict[str, Any] | None:
    if _banda_carga(c, limites) != 'sobrecarga':
        return None
    umbral = limites.cargabilidad_max_pct
    return {'texto': f'Sobrecarga: {_numero(c)} %, por encima del máximo de {_numero(umbral)} %',
            'icono': ICONO_INCUMPLE, 'valor': c, 'umbral': umbral}


#: 111:RF-21: de dónde sale el umbral de cada capa con hallazgos. La tensión, de una regla de la biblioteca normativa
#: (107:RF-21). La cargabilidad de los tramos MT y BT de distribución no tiene norma publicada con un umbral (la del PIT,
#: ``pit.factor_utilizacion_max``, es de líneas MAT y AT y SET): su umbral es un criterio de la empresa, la clave
#: ``estudios.cargabilidad_max_pct`` de su perfil, y el hallazgo lo dice así, nunca como norma (orden de c2, 17-11).
CRITERIO_EMPRESA = 'perfil:'
REGLA_DE_LA_CAPA: dict[str, str] = {'tension': 'calidad.tension.tolerancia_ntcse',
                                    'cargabilidad': f'{CRITERIO_EMPRESA}estudios.cargabilidad_max_pct'}


def normas_de_las_capas(registro: Any, fecha: str | None = None, *, limites: Limites | None = None
                        ) -> dict[str, dict[str, Any]]:
    """111:RF-21: la norma de cada capa con hallazgos, leída de la biblioteca (``registro.regla``), o el criterio de la
    empresa con su origen (``limites.origen``: «perfil» o «por defecto»), o el motivo de que no haya ninguna. Ninguna
    cita se escribe en el frontend: la pestaña enseña lo que da aquí el servidor."""
    salida: dict[str, dict[str, Any]] = {}
    for capa, clave in REGLA_DE_LA_CAPA.items():
        if clave.startswith(CRITERIO_EMPRESA):
            origen = limites.origen if limites is not None else 'por defecto'
            valor = getattr(limites, 'cargabilidad_max_pct', None) if limites is not None else None
            salida[capa] = {'criterio_empresa': f'perfil: {clave[len(CRITERIO_EMPRESA):]}',
                            'origen': origen if origen != 'por defecto' or valor is None else f'por defecto, {valor:g} %'}
            continue
        try:
            vigente = registro.regla(clave, fecha)
        except Exception as exc:  # noqa: BLE001 - una regla que falta o es ambigua se nombra, no se supone
            salida[capa] = {'falta': f'La biblioteca normativa no da la regla {clave}: {exc}'}
            continue
        r, n = vigente.regla, vigente.norma
        salida[capa] = {'clave': r.clave, 'acto': n.acto, 'articulo': r.articulo_o_anexo, 'pagina': r.pagina,
                        'cita': r.cita_literal, 'estado': vigente.estado, 'obligatoria': bool(vigente.obligatoria)}
    return salida


def _no_pintable(resultado: Mapping[str, Any], motivo: str) -> dict[str, Any]:
    return {'pintable': False, 'motivo': motivo, 'mensajes': list(resultado.get('mensajes') or ()), 'capas': {},
            'motor': resultado.get('motor'), 'motor_texto': MOTORES.get(resultado.get('motor'), ''),
            'caso': resultado.get('caso'), 'revision': resultado.get('revision')}


def capas(resultado: Mapping[str, Any], *, limites: Limites, revision: str, caso: str,
          normas: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Las capas que se pintan sobre las mismas polilíneas, con su leyenda (111:RF-10, RF-13, RF-18).

    Solo se pinta lo que el motor calculó para ese caso y esa revisión de la red (RF-11). Un incumplimiento lleva
    texto, icono, valor y umbral además del color. El umbral sale del perfil (``estudios_pf.limites_de_perfil``) o es
    el de por defecto, y la leyenda dice cuál. Con ``normas`` (:func:`normas_de_las_capas`), cada incumplimiento lleva
    también la norma de la biblioteca que fija su umbral, o el motivo de que no la haya (RF-21).
    """
    if resultado.get('revision') != revision:
        return _no_pintable(resultado, 'El resultado es de otra revisión de la red: no se pinta. Vuelva a estudiar.')
    if resultado.get('caso') != caso:
        return _no_pintable(resultado, f'El resultado es de otro caso ({resultado.get("caso")}), no de {caso}.')
    if not resultado.get('convergio'):
        return _no_pintable(resultado, 'El estudio no convergió: no hay resultados que pintar.')
    motor = resultado['motor']
    comun = {'caso': caso, 'revision': revision, 'motor': motor, 'motor_texto': MOTORES[motor],
             'origen_umbral': limites.origen}

    def capa(magnitud: str, unidad: str, umbral: dict[str, float] | None, elementos: list[dict[str, Any]],
             clave: str | None = None):
        norma = dict((normas or {}).get(clave) or {}) if clave else {}

        def con_norma(e: dict[str, Any]) -> dict[str, Any]:
            if not e.get('incumple') or not norma:
                return {**e, 'motor': motor}
            return {**e, 'motor': motor, 'incumple': {**e['incumple'], 'norma': norma}}
        return {'leyenda': {'magnitud': magnitud, 'unidad': unidad, 'umbral': umbral, **comun},
                'elementos': [con_norma(e) for e in elementos]}

    tension = [{'codigo': n, 'valor': b['u_pu'], 'kv': b.get('kv'), 'banda': _banda_tension(b['u_pu'], limites),
                'incumple': _incumple_tension(b['u_pu'], limites)} for n, b in sorted(resultado['barras'].items())]
    corriente = [{'codigo': s, 'valor': t.get('i_a'), 'banda': 'sin_valor' if t.get('i_a') is None else 'calculada',
                  'incumple': None} for s, t in sorted(resultado['tramos'].items())]
    carga = [{'codigo': s, 'valor': t.get('carga_pct'), 'banda': _banda_carga(t.get('carga_pct'), limites),
              'incumple': _incumple_carga(t.get('carga_pct'), limites)} for s, t in sorted(resultado['tramos'].items())]
    estado = [{'codigo': c, 'valor': e['estado'], 'banda': e['estado'], 'incumple': None}
              for c, e in sorted((resultado.get('equipos') or {}).items())]
    return {'pintable': True, 'motivo': '', 'mensajes': list(resultado.get('mensajes') or ()), **comun,
            'capas': {
                'tension': capa('Tensión por barra', 'p.u.',
                                {'min': limites.tension_min_pu, 'max': limites.tension_max_pu}, tension, 'tension'),
                'corriente': capa('Corriente por tramo', 'A', None, corriente),
                'cargabilidad': capa('Cargabilidad por tramo', '%', {'max': limites.cargabilidad_max_pct}, carga,
                                     'cargabilidad'),
                'estado': capa('Estado de cada equipo', '', None, estado)}}


def traducir_resultados_pf(geografia: Mapping[str, Any], ident: Mapping[str, Any], *, caso: str, revision: str,
                           convergio: bool = True, mensajes: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """Los resultados de DIgSILENT (``tools/estudios_pf.geografia``) con los códigos de la fuente (111:RF-2, RF-18).

    El cruce es la identidad (``plano_red.identidad``): un nombre que no está, o que dos códigos comparten, no se pinta
    y se cuenta en ``sin_codigo``. DIgSILENT no da aquí la corriente ni el estado de las maniobras.
    """
    sin: list[str] = []
    barras: dict[str, dict[str, Any]] = {}
    for nombre, _lat, _lon, u, kv in geografia.get('barras') or ():
        codigo = codigo_de_nombre(ident, 'barra', nombre)
        if codigo is None:
            sin.append(nombre)
            continue
        barras[codigo] = {'u_pu': u, 'kv': kv}
    tramos: dict[str, dict[str, Any]] = {}
    n_barras = len(sin)
    for fila in geografia.get('tramos') or ():
        nombre, carga = fila[0], fila[2]
        codigo = codigo_de_nombre(ident, 'tramo', nombre)
        if codigo is None:
            sin.append(nombre)
            continue
        tramos[codigo] = {'i_a': None, 'carga_pct': carga, 'como_conexion': False}
    return {'motor': 'DIgSILENT', 'motor_texto': MOTORES['DIgSILENT'], 'alimentador': ident.get('alimentador'),
            'caso': caso, 'revision': revision, 'variacion': None, 'version': None, 'convergio': bool(convergio),
            'flujo': 'DIgSILENT', 'mensajes': list(mensajes), 'barras': barras if convergio else {},
            'tramos': tramos if convergio else {}, 'sed': {}, 'equipos': {},
            'sin_codigo': {'barras': n_barras, 'tramos': len(sin) - n_barras, 'nombres': sorted(sin)[:20]}}


# ------------------------------------------------------------------------- comparación (111:RF-12, RF-19)

def comparar(a: Mapping[str, Any], b: Mapping[str, Any], *, limites: Limites) -> dict[str, Any]:
    """Dos casos por elemento sobre el mismo plano: valor A, valor B, diferencia (B − A) y banda de cada uno.

    Solo se comparan dos resultados de la misma revisión de la red y que convergieron. Si los motores son distintos,
    la comparación lo dice junto a la diferencia (RF-19).
    """
    casos = [{'caso': r.get('caso'), 'variacion': r.get('variacion'), 'motor': r.get('motor')} for r in (a, b)]
    mismo_motor = a.get('motor') == b.get('motor')
    aviso = None if mismo_motor else (
        f'Los dos casos se calcularon con motores distintos ({MOTORES.get(a.get("motor"), a.get("motor"))} y '
        f'{MOTORES.get(b.get("motor"), b.get("motor"))}): la diferencia mezcla los dos motores.')
    base = {'casos': casos, 'mismo_motor': mismo_motor, 'aviso_motores': aviso, 'elementos': []}
    if a.get('revision') != b.get('revision'):
        return {**base, 'comparable': False, 'motivo': 'Los dos casos son de distinta revisión de la red: no se comparan sobre el mismo plano.'}
    if not (a.get('convergio') and b.get('convergio')):
        return {**base, 'comparable': False, 'motivo': 'Uno de los dos casos no convergió: no hay qué comparar.'}

    def resta(x: Any, y: Any) -> float | None:
        return y - x if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None

    elementos = []
    fuentes = (('tension', 'barras', 'u_pu', lambda v: _banda_tension(v, limites)),
               ('corriente', 'tramos', 'i_a', lambda v: 'sin_valor' if v is None else 'calculada'),
               ('cargabilidad', 'tramos', 'carga_pct', lambda v: _banda_carga(v, limites)),
               ('estado', 'equipos', 'estado', lambda v: v or 'sin_valor'))
    for magnitud, clase, campo, banda in fuentes:
        da, db = a.get(clase) or {}, b.get(clase) or {}
        for codigo in sorted(set(da) | set(db)):
            va = da[codigo].get(campo) if codigo in da else None
            vb = db[codigo].get(campo) if codigo in db else None
            elementos.append({'codigo': codigo, 'magnitud': magnitud, 'a': va, 'b': vb, 'diferencia': resta(va, vb),
                              'banda_a': banda(va), 'banda_b': banda(vb),
                              'solo_en': None if codigo in da and codigo in db else ('a' if codigo in da else 'b')})
    return {**base, 'comparable': True, 'motivo': '', 'elementos': elementos}
