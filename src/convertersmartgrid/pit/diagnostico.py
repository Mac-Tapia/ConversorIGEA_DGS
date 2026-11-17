"""Diagnóstico del área por año: caso base y N-1 de cada línea y transformador (107:RF-3, 107:RF-4).

La demanda de cada año sale de la proyección (``proyeccion_anual``: filas con ``alimentador``, ``anio_calendario``,
``p_kw`` y ``q_kvar``) y se lleva a la barra de carga de su SET con la correspondencia SET → alimentadores del perfil,
en una sola pasada por las filas (nada de recorrerlas por SET ni por año). Un año sin demanda proyectada no se
extrapola: queda nombrado. Los límites vienen del registro normativo o del perfil, sin valores por defecto; un límite
que no da ninguno de los dos es un error que lo nombra. El trabajo es cancelable entre años (P7).

Tensión por barra, desde la norma (107 T7, tarjeta PIT-TEN; aclaración de RF-3 y RF-4). ``limites_de_tension`` da a
cada barra su criterio según su nivel (``pit.diagnostico.niveles_tension_rangos_kv``), si hay entrega de suministro en
ella y su tipo de red (``urbana``, ``urbano_rural``, ``rural`` o ``ser``), que vienen de la red del área o de
``pit.barras`` del perfil:

* con entrega: la tolerancia de la NTCSE (5.1.2) o, en un SER, la de la NTCSER (4.1.2), como pide la RCD 217-2013
  (12.2.1.a);
* AT sin entrega: sin límite propio; se comprueba que el rango de tomas de cada transformador AT/MT lleve su barra de
  MT a la tolerancia de la norma (12.2.1.a);
* MAT y AT sin entrega del Área de Demanda 15: los criterios de la RM 129-2009-MEM/DM (art. 10 y Primera), por la
  remisión del 12.3.2 (redacción de la RCD 018-2018-OS/CD), sobre la tensión de operación del COES
  (``tension_operacion_kv``; sin ella, hueco nombrado). El caso base y el N-1 van con el rango normal; el de
  emergencia solo si el estudio sustenta su importancia (nota 2 del art. 10) en ``pit.emergencia_rm129``, con un
  aviso que cita el sustento y la nota; entonces, entre 138 y 220 kV no hay rango y es un hueco nombrado. Obligan si su norma obliga en el registro; si no, avisan sin contar, sin tocar el código;
* MAT sin entrega de las demás áreas: la RM 129-2009 como referencia, en un aviso visible por barra con su tensión, su
  rango y su fuente, que no cuenta como violación.

Lo que falta para decidirlo es un hueco nombrado por barra; ``pit.limites`` del perfil sigue valiendo como respaldo
explícito de esa barra, con su origen y un aviso.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping

from ..registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from . import PitError
from .ambito import AreaPit
from .motores import ejecutar
from .red_area import RedArea
from .red_pandapower import ResultadoFlujo

__all__ = ['Diagnostico', 'agregar_demanda', 'diagnosticar', 'emergencia_rm129', 'limites_de_tension',
           'limites_del_estudio']

LIMITES = ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')
#: Los límites sin los que no hay diagnóstico. Los de tensión salen por barra (``limites_de_tension``); los del
#: perfil quedan como respaldo explícito (107 T7, PIT-TEN).
OBLIGADOS = ('cargabilidad_max_pct',)
#: Regla del registro que da cada límite y el factor que la lleva a la unidad del límite.
_REGLAS = {'tension_min_pu': ('pit.tension_min_pu', 1.0), 'tension_max_pu': ('pit.tension_max_pu', 1.0),
           'cargabilidad_max_pct': ('pit.factor_utilizacion_max', 100.0)}

R_NIVELES = 'pit.diagnostico.niveles_tension_rangos_kv'
R_CRITERIO = 'pit.diagnostico.tension_criterio'
R_AREA15 = 'pit.diagnostico.area15_criterios'
R_NTCSE = 'calidad.tension.tolerancia_ntcse'
R_NTCSER = 'calidad.tension.tolerancia_ntcser'
R_REFERENCIA = 'pit.area15.criterios_desempeno'
R_NOTAS = 'pit.area15.criterios_desempeno_notas'
TIPOS_RED = ('urbana', 'urbano_rural', 'rural', 'ser')
TOMAS = ('tap_side', 'tap_min', 'tap_max', 'tap_neutral', 'tap_step_percent')
_SI = {'si', 's', 'true', 'verdadero', 'x', 'yes', '1'}
_NO = {'no', 'n', 'false', 'falso', '0'}
_ALIAS_RED = {'urbano': 'urbana', 'urbanorural': 'urbano_rural', 'urbano_rurales': 'urbano_rural',
              'rurales': 'rural', 'sistema_electrico_rural': 'ser'}


def limites_del_estudio(registro: RegistroNormativo | None, perfil: Mapping[str, Any], fecha: str | None = None
                        ) -> dict[str, dict[str, Any]]:
    """Cada límite con su origen: la regla obligatoria del registro, si no el perfil (``pit.limites``), y si no la
    regla del registro como referencia, rotulada así (107:RF-8). Los de tensión no se exigen: salen por barra de la
    norma (``limites_de_tension``) y estos quedan como respaldo explícito (107 T7, PIT-TEN)."""
    propios = ((perfil.get('pit') or {}).get('limites') or {}) if isinstance(perfil, Mapping) else {}
    out = {}
    for limite in LIMITES:
        clave, factor = _REGLAS[limite]
        regla = _regla(registro, clave, fecha)
        if regla is not None and regla.obligatoria:
            out[limite] = {'valor': float(regla.regla.valor) * factor, 'origen': 'registro', 'regla': clave,
                           'norma': regla.norma.acto, 'estado': regla.estado, 'obligatoria': True}
        elif propios.get(limite) is not None:
            out[limite] = {'valor': float(propios[limite]), 'origen': 'perfil', 'regla': f'pit.limites.{limite}',
                           'obligatoria': False}
        elif regla is not None:
            out[limite] = {'valor': float(regla.regla.valor) * factor, 'origen': 'registro_referencia',
                           'regla': clave, 'norma': regla.norma.acto, 'estado': regla.estado, 'obligatoria': False}
        elif limite in OBLIGADOS:
            raise PitError(f'falta el límite {limite}: ni el registro normativo ({clave}) ni el perfil '
                           f'(pit.limites.{limite}) lo dan, y el PIT no lo supone')
    return out


def _regla(registro: RegistroNormativo | None, clave: str, fecha: str | None) -> ReglaVigente | None:
    if registro is None:
        return None
    try:
        return registro.regla(clave, fecha)
    except RegistroError:
        return None


def _norm(v: Any) -> str:
    t = unicodedata.normalize('NFKD', str(v)).encode('ascii', 'ignore').decode().strip().lower()
    return re.sub(r'[\s\-/]+', '_', t)


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _entrega(v: Any) -> bool | str | None:
    """Sí o no; ``None`` si no se declara y ``'invalido'`` si no se entiende."""
    if _vacio(v):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v) if v in (0, 1) else 'invalido'
    t = _norm(v)
    return True if t in _SI else False if t in _NO else 'invalido'


def _tipo_red(v: Any) -> str | None:
    if _vacio(v):
        return None
    t = _norm(v)
    t = _ALIAS_RED.get(t, t)
    return t if t in TIPOS_RED else 'invalido'


def _nivel(kv: Any, rangos: Mapping[str, Any]) -> str | None:
    """MAT, AT, MT o BT por la definición «Nivel de Tensión» de la 217-2013; ``None`` si no casa con ninguno."""
    try:
        kv = float(kv)
    except (TypeError, ValueError):
        return None
    if any(math.isclose(kv, float(x), rel_tol=1e-3) for x in rangos['MAT']['kv']):
        return 'MAT'
    if float(rangos['AT']['desde_kv']) <= kv < float(rangos['AT']['menor_que_kv']):
        return 'AT'
    if float(rangos['MT']['mayor_que_kv']) < kv < float(rangos['MT']['menor_que_kv']):
        return 'MT'
    if 0 < kv <= float(rangos['BT']['hasta_kv']):
        return 'BT'
    return None


def _area_demanda(pit: Mapping[str, Any], codigo: str) -> int | None:
    """El número oficial del Área de Demanda (``pit.areas[].area_demanda``); no se deduce del código."""
    for a in pit.get('areas') or ():
        if isinstance(a, Mapping) and str(a.get('codigo')) == codigo and not _vacio(a.get('area_demanda')):
            try:
                return int(a['area_demanda'])
            except (TypeError, ValueError):
                return None
    return None


def _de_regla(r: ReglaVigente, clave: str, criterio: str, normal: list[float], emergencia: list[float],
              fuente: str = '') -> dict[str, Any]:
    return {'criterio': criterio, 'normal_pu': [round(normal[0], 6), round(normal[1], 6)],
            'emergencia_pu': [round(emergencia[0], 6), round(emergencia[1], 6)], 'regla': clave,
            'norma': r.norma.acto, 'estado': r.estado, 'obligatoria': r.obligatoria,
            'origen': 'registro' if r.obligatoria else 'registro_referencia', 'cuenta': r.obligatoria,
            'fuente': fuente or f'{r.norma.acto}, {r.regla.articulo_o_anexo}'}


def _tolerancia(nivel: str, tipo: str, reglas: Mapping[str, ReglaVigente | None]
                ) -> tuple[dict[str, Any] | None, list[str]]:
    """La tolerancia de la barra con entrega (NTCSE o, en un SER, NTCSER), o lo que falta para darla."""
    if tipo == 'ser':
        r = reglas[R_NTCSER]
        if r is None:
            return None, [f'regla {R_NTCSER} del registro']
        tol = r.regla.valor.get(nivel)
        if tol is None:
            return None, [f'tolerancia de la NTCSER en {nivel} (la norma solo la da en MT y BT)']
        return _de_regla(r, R_NTCSER, 'ntcser', [1 - tol, 1 + tol], [1 - tol, 1 + tol]), []
    r = reglas[R_NTCSE]
    if r is None:
        return None, [f'regla {R_NTCSE} del registro']
    v = r.regla.valor
    tol = (v['redes_secundarias_urbano_rurales_o_rurales'] if nivel == 'BT' and tipo in ('urbano_rural', 'rural')
           else v['general'])
    return _de_regla(r, R_NTCSE, 'ntcse', [1 - tol, 1 + tol], [1 - tol, 1 + tol]), []


def emergencia_rm129(perfil: Mapping[str, Any]) -> str | None:
    """El sustento del estudio para usar en el N-1 el rango de emergencia de la RM 129-2009 (nota 2 del art. 10:
    «solo para los casos en que se demuestre su importancia»), de ``pit.emergencia_rm129``: ``{"aplica": true,
    "sustento": "<texto>"}``. ``None`` si no se declara o no aplica: entonces el N-1 va con el rango normal. Declararlo
    sin sustento es un error que lo nombra (107 T7, PIT-TEN v2)."""
    pit = (perfil.get('pit') or {}) if isinstance(perfil, Mapping) else {}
    campo = pit.get('emergencia_rm129')
    if campo is None:
        return None
    if not isinstance(campo, Mapping) or not isinstance(campo.get('aplica'), bool):
        raise PitError('pit.emergencia_rm129 tiene que ser {"aplica": true o false, "sustento": "<texto>"}, no '
                       f'{campo!r}')
    if not campo['aplica']:
        return None
    sustento = campo.get('sustento')
    if not isinstance(sustento, str) or not sustento.strip():
        raise PitError('pit.emergencia_rm129: «aplica» es true sin «sustento». La RM 129-2009 (nota 2 del art. 10) '
                       'solo deja usar el rango de emergencia si el estudio demuestra su importancia: escriba el '
                       'sustento o quite el campo, y el N-1 irá con el rango normal')
    return sustento.strip()


def _tramos_de_emergencia(tramos: Any) -> str:
    """Los tramos de tensión en que el registro da rango de emergencia, en palabras («hasta X kV y desde Y kV»)."""
    hasta = [f'hasta {float(t["hasta_kv"]):g} kV' for t in tramos if 'hasta_kv' in t]
    desde = [f'desde {float(t["desde_kv"]):g} kV' for t in tramos if 'desde_kv' in t]
    return ' y '.join(hasta + desde) or 'en ningún tramo del registro'


def _area_que_obliga(reglas: Mapping[str, ReglaVigente | None]) -> str:
    """El Área de Demanda en que obligan los criterios de la referencia, con su norma y artículo, desde el registro."""
    a = reglas.get(R_AREA15)
    if a is None:
        return f'el área que fija la regla {R_AREA15} del registro'
    return f'el Área de Demanda {a.regla.valor["area_de_demanda"]} ({a.norma.acto}, {a.regla.articulo_o_anexo})'


def _norma_que_obliga(reglas: Mapping[str, ReglaVigente | None]) -> str:
    """La norma cuyos criterios rigen en esa área, según el registro."""
    a, r = reglas.get(R_AREA15), reglas.get(R_REFERENCIA)
    if a is not None and a.regla.valor.get('norma'):
        return str(a.regla.valor['norma'])
    return r.norma.acto if r is not None else f'norma de la regla {R_REFERENCIA} del registro'


def _rm129(d: Mapping[str, Any], reglas: Mapping[str, ReglaVigente | None], en_area15: bool,
           sustento: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """Los criterios de tensión de la RM 129-2009 (art. 10 y Primera), sobre la tensión de operación del COES (nota 1),
    nunca sobre la nominal. El caso base y, por defecto, el N-1 van con el rango normal; el de emergencia solo con el
    ``sustento`` del estudio (nota 2; ``pit.emergencia_rm129``). En el Área 15 obligan si su norma obliga
    (``area15``); en las demás áreas son solo referencia (``referencia``), que se muestra y no cuenta.

    Devuelve el criterio con sus faltas parciales en ``falta``: sin tensión de operación no se compara; con el rango de
    emergencia sustentado, entre 138 y 220 kV no lo hay (decisión de interpretación del registro)."""
    r = reglas[R_REFERENCIA]
    if r is None:
        return None, [f'regla {R_REFERENCIA} del registro']
    v = r.regla.valor
    kv = d['kv']
    normal_op = [float(x) for x in v['normal_pu']]
    falta = []
    if sustento is None:
        emergencia = normal_op
    else:
        emergencia = None
        for tramo in v.get('emergencia_pu') or ():
            if ('desde_kv' in tramo and kv >= float(tramo['desde_kv']) - 1e-6) or \
                    ('hasta_kv' in tramo and kv <= float(tramo['hasta_kv']) + 1e-6):
                emergencia = [float(x) for x in tramo['rango']]
                break
        if emergencia is None:
            falta.append(f'rango de emergencia en {kv:g} kV: la {r.norma.acto} solo lo da '
                         f'{_tramos_de_emergencia(v.get("emergencia_pu") or ())}')
    fuente = str(v.get('fuente') or f'{r.norma.acto}, {r.regla.articulo_o_anexo}')
    if not en_area15:
        fuente += f'; rige solo en {_area_que_obliga(reglas)}: aquí es referencia'
    base = d.get('tension_operacion_kv')
    if base is None:
        falta.append('tension_operacion_kv (tensión de operación establecida por el COES, base del p.u. de la '
                     'RM 129-2009, nota 1 del art. 10)')
    cuenta = bool(en_area15 and r.obligatoria)
    entrada = {'criterio': 'area15' if en_area15 else 'referencia', 'regla': R_REFERENCIA, 'norma': r.norma.acto,
               'estado': r.estado, 'obligatoria': r.obligatoria, 'fuente': fuente, 'base_kv': base,
               'normal_operacion_pu': normal_op, 'emergencia_operacion_pu': emergencia, 'cuenta': cuenta,
               'origen': 'registro' if cuenta else 'registro_referencia',
               'n_1_con': 'emergencia' if sustento is not None else 'normal', 'sustento_emergencia': sustento,
               'nota_emergencia': str(v.get('emergencia_solo_si') or '')}
    if base is not None:
        k = float(base) / kv  # de p.u. de la tensión de operación a p.u. de la nominal, que es lo que da el flujo
        entrada['normal_pu'] = [round(x * k, 6) for x in normal_op]
        entrada['emergencia_pu'] = [round(x * k, 6) for x in emergencia] if emergencia is not None else None
    if falta:
        entrada['falta'] = falta
    return entrada, []


def _es_numero(v: Any) -> bool:
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return not isinstance(v, bool)


def _tomas(t: Mapping[str, Any], lados: Iterable[str]) -> tuple[dict[str, Any] | None, list[str]]:
    """Las tomas del transformador (``tap_side``, ``tap_min``, ``tap_max``, ``tap_neutral``, ``tap_step_percent``) o
    lo que les falta."""
    lados = tuple(lados)
    falta = [k for k in TOMAS if _vacio(t.get(k))]
    if falta:
        return None, falta
    malos = [f'{k}: {t[k]!r} no es un número' for k in TOMAS[1:] if not _es_numero(t[k])]
    lado = _norm(t['tap_side'])
    if lado not in ('hv', *lados):
        malos.append(f'tap_side: {t["tap_side"]!r} no es hv ni {" ni ".join(lados)}')
    if malos:
        return None, malos
    numeros = {k: float(t[k]) for k in TOMAS[1:]}
    if numeros['tap_min'] > numeros['tap_max']:
        return None, [f'tap_min {numeros["tap_min"]:g} mayor que tap_max {numeros["tap_max"]:g}']
    return {'tap_side': lado, **numeros}, []


def _alcanzable(v0: float, tomas: Mapping[str, Any], lado: str) -> tuple[float, float]:
    """Tensión de la barra del lado ``lado`` en las tomas extremas, desde la calculada en la toma neutra: la toma en AT
    divide la tensión de MT por (1 + Δ); en el propio lado la multiplica; en otro devanado no la cambia."""
    deltas = [(tomas[k] - tomas['tap_neutral']) * tomas['tap_step_percent'] / 100 for k in ('tap_min', 'tap_max')]
    if tomas['tap_side'] == 'hv':
        vals = [v0 / (1 + d) for d in deltas if 1 + d > 0] or [v0]
    elif tomas['tap_side'] == lado:
        vals = [v0 * (1 + d) for d in deltas]
    else:
        vals = [v0]
    return min(vals), max(vals)


def _operacion(b: Mapping[str, Any], extra: Mapping[str, Any]) -> float | None:
    """La tensión de operación del COES de la barra, en kV (base del p.u. de la RM 129-2009); ``None`` si no la hay."""
    v = b.get('tension_operacion_kv')
    if _vacio(v):
        v = extra.get('tension_operacion_kv')
    return float(v) if _es_numero(v) and float(v) > 0 else None


def _datos_barras(red: RedArea, declaradas: Mapping[str, Any], rangos: Mapping[str, Any] | None
                  ) -> dict[str, dict[str, Any]]:
    """Nivel, entrega y tipo de red de cada barra: de la red y, si la red no lo trae, de ``pit.barras`` del perfil."""
    datos = {}
    for b in red.de_tipo('barra'):
        extra = declaradas.get(b['id']) or {}
        crudo_e = b.get('entrega') if not _vacio(b.get('entrega')) else extra.get('entrega')
        crudo_t = b.get('tipo_red') if not _vacio(b.get('tipo_red')) else extra.get('tipo_red')
        datos[b['id']] = {'barra': b['id'], 'kv': float(b['kv']),
                          'nivel': _nivel(b['kv'], rangos) if rangos is not None else None,
                          'entrega': _entrega(crudo_e), 'tipo_red': _tipo_red(crudo_t), 'crudo': (crudo_e, crudo_t),
                          'tension_operacion_kv': _operacion(b, extra)}
    return datos


def _regulacion(red: RedArea, datos: Mapping[str, Mapping[str, Any]], reglas: Mapping[str, ReglaVigente | None],
                out: dict[str, Any], usadas: set[str]) -> dict[str, list[str]]:
    """Cada transformador AT/MT con su AT sin entrega: sus tomas y el rango de su barra de MT (12.2.1.a)."""
    reguladas: dict[str, list[str]] = {}
    for tipo, lados in (('trafo2', ('lv',)), ('trafo3', ('mv', 'lv'))):
        for t in red.de_tipo(tipo):
            hv = datos.get(t['hv'])
            mt = [(lado, datos[t[lado]]) for lado in lados if t.get(lado) in datos and datos[t[lado]]['nivel'] == 'MT']
            if hv is None or hv['nivel'] != 'AT' or hv['entrega'] is not False or not mt:
                continue
            reguladas.setdefault(hv['barra'], []).append(t['id'])
            tomas, falta = _tomas(t, lados)
            lados_out = []
            for lado, d in mt:
                if d['tipo_red'] in (None, 'invalido'):
                    falta.append(f'tipo_red de la barra de MT {d["barra"]}')
                    continue
                lim, f_lim = _tolerancia('MT', d['tipo_red'], reglas)
                if lim is None:
                    falta += f_lim
                    continue
                usadas.add(lim['regla'])
                lados_out.append({'lado': lado, 'barra': d['barra'], 'rango_pu': lim['normal_pu'],
                                  'regla': lim['regla'], 'norma': lim['norma'], 'obligatoria': lim['obligatoria'],
                                  'cuenta': lim['cuenta']})
            out['regulacion'].append({'trafo': t['id'], 'barra_at': hv['barra'], 'tomas': tomas, 'lados': lados_out,
                                      'falta': falta})
            if falta:
                out['huecos'].append({'elemento': t['id'], 'barra': hv['barra'], 'falta': falta})
    return reguladas


def _criterio_barra(d: Mapping[str, Any], reglas: Mapping[str, ReglaVigente | None], numero: int | None,
                    area15: int | None, reguladas: Mapping[str, list[str]], hay_rangos: bool,
                    sustento: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    crudo_e, crudo_t = d['crudo']
    falta: list[str] = []
    if not hay_rangos:
        falta.append(f'regla {R_NIVELES} del registro')
    elif d['nivel'] is None:
        falta.append(f'nivel de tensión: {d["kv"]:g} kV no está en {R_NIVELES}')
    if d['entrega'] is None:
        falta.append('entrega (si hay entrega de suministro en la barra)')
    elif d['entrega'] == 'invalido':
        falta.append(f'entrega: {crudo_e!r} no es sí ni no')
    if falta:
        return None, falta
    if d['entrega']:
        if d['tipo_red'] is None:
            return None, [f'tipo_red ({", ".join(TIPOS_RED)})']
        if d['tipo_red'] == 'invalido':
            return None, [f'tipo_red: {crudo_t!r} no es {", ".join(TIPOS_RED)}']
        return _tolerancia(d['nivel'], d['tipo_red'], reglas)
    if d['nivel'] in ('MAT', 'AT') and numero is not None and numero == area15:
        return _rm129(d, reglas, en_area15=True, sustento=sustento)
    if d['nivel'] == 'MAT' and numero is None:
        return None, ['número del Área de Demanda (pit.areas[].area_demanda): sin él no se sabe si rige la '
                      f'{_norma_que_obliga(reglas)} ({_area_que_obliga(reglas)}) o es solo referencia']
    if d['nivel'] == 'MAT':
        return _rm129(d, reglas, en_area15=False, sustento=sustento)
    if d['nivel'] == 'AT' and numero is None:
        return None, ['número del Área de Demanda (pit.areas[].area_demanda): sin él no se sabe si rige la referencia '
                      f'de {_area_que_obliga(reglas)}']
    if d['nivel'] == 'AT':
        propios = list(reguladas.get(d['barra'], []))
        return {'criterio': 'regulacion_transformador' if propios else 'sin_limite', 'transformadores': propios,
                'motivo': ('AT sin entrega: se comprueba el rango de tomas de sus transformadores AT/MT '
                           '(RCD 217-2013, 12.2.1.a)') if propios else
                          'AT sin entrega y sin transformador AT/MT: la 217-2013 (12.2.1.a) no le da límite'}, []
    return {'criterio': 'sin_limite', 'motivo': f'{d["nivel"]} sin entrega: la 217-2013 (12.2.1.a) solo pide la '
                                                'tolerancia donde hay entrega de suministro'}, []


def limites_de_tension(red: RedArea, area: AreaPit, registro: RegistroNormativo | None, perfil: Mapping[str, Any],
                       fecha: str | None = None) -> dict[str, Any]:
    """Por barra, su criterio de tensión desde la norma, y la regulación de los transformadores AT/MT sin entrega en
    AT (107 T7, PIT-TEN). Devuelve ``barras``, ``regulacion``, ``huecos``, ``avisos`` y ``reglas`` (las claves del
    registro usadas)."""
    pit = (perfil.get('pit') or {}) if isinstance(perfil, Mapping) else {}
    propios = pit.get('limites') or {}
    respaldo = None
    if propios.get('tension_min_pu') is not None and propios.get('tension_max_pu') is not None:
        respaldo = [float(propios['tension_min_pu']), float(propios['tension_max_pu'])]
    sustento = emergencia_rm129(perfil)
    reglas = {c: _regla(registro, c, fecha) for c in (R_NIVELES, R_CRITERIO, R_AREA15, R_NTCSE, R_NTCSER,
                                                      R_REFERENCIA, R_NOTAS)}
    rangos = reglas[R_NIVELES].regla.valor if reglas[R_NIVELES] is not None else None
    area15 = int(reglas[R_AREA15].regla.valor['area_de_demanda']) if reglas[R_AREA15] is not None else None
    numero = _area_demanda(pit, area.codigo)
    usadas = {c for c in (R_NIVELES, R_CRITERIO) if reglas[c] is not None}
    out: dict[str, Any] = {'barras': {}, 'regulacion': [], 'huecos': [], 'avisos': [], 'reglas': []}
    datos = _datos_barras(red, pit.get('barras') or {}, rangos)
    reguladas = _regulacion(red, datos, reglas, out, usadas)
    for bid, d in datos.items():
        lim, falta = _criterio_barra(d, reglas, numero, area15, reguladas, rangos is not None, sustento)
        if falta and respaldo is not None:
            lim = {'criterio': 'perfil', 'normal_pu': respaldo, 'emergencia_pu': respaldo,
                   'regla': 'pit.limites.tension_min_pu/tension_max_pu', 'origen': 'perfil', 'obligatoria': False,
                   'cuenta': True, 'fuente': 'perfil (pit.limites)', 'falta': falta}
            out['avisos'].append(f'barra {bid}: falta {"; ".join(falta)}; se usa el respaldo del perfil '
                                 f'pit.limites ({respaldo[0]:g}–{respaldo[1]:g} p.u.)')
        elif falta:
            lim = {'criterio': 'hueco', 'falta': falta}
            out['huecos'].append({'barra': bid, 'falta': falta})
        lim = dict(lim or {})
        if lim.get('criterio') == 'area15' and lim.get('falta'):
            # En el Área 15 lo que falta (la tensión de operación, el rango de emergencia) es un hueco: no se compara.
            out['huecos'].append({'barra': bid, 'falta': list(lim['falta'])})
        if lim.get('regla') in reglas:
            usadas.add(lim['regla'])
        out['barras'][bid] = {**{k: v for k, v in d.items() if k != 'crudo'}, **lim}
    if sustento is not None and any(e.get('n_1_con') == 'emergencia' for e in out['barras'].values()):
        notas = reglas[R_NOTAS].regla.valor if reglas[R_NOTAS] is not None else ()
        nota = next((n for n in notas if str(n).startswith('(2)')), '')
        if reglas[R_NOTAS] is not None:
            usadas.add(R_NOTAS)
        out['avisos'].append('el N-1 de las barras con la RM 129-2009 usa su rango de emergencia por el sustento del '
                             f'estudio (pit.emergencia_rm129): «{sustento}»; RM 129-2009-MEM/DM, art. 10, nota '
                             f'{nota or "(2): la emergencia solo si se demuestra su importancia"}')
    out['reglas'] = sorted(usadas)
    return out


def agregar_demanda(area: AreaPit, red: RedArea, filas: Iterable[Mapping[str, Any]], *,
                    factor_potencia: float | None = None) -> dict[int, dict[str, tuple[float, float]]]:
    """Año → barra de carga → (P MW, Q Mvar), sumando los alimentadores de cada SET del área. Con ``factor_potencia``
    (el de las barras de MT de la norma, 12.1.8.c), la Q de cada barra sale de su P con ese factor (107:RF-20)."""
    barras = red.barras_de_carga()
    sin_barra = [s for s in area.set_alimentadores if s not in barras]
    if sin_barra:
        raise PitError(f'las SET {sin_barra} tienen alimentadores en el perfil y ninguna barra de carga en la red')
    barra_de = {a: barras[s] for s, alims in area.set_alimentadores.items() for a in alims}
    out: dict[int, dict[str, list[float]]] = {}
    for f in filas:
        barra = barra_de.get(str(f.get('alimentador')))
        if barra is None:
            continue
        pq = out.setdefault(int(f['anio_calendario']), {}).setdefault(barra, [0.0, 0.0])
        pq[0] += float(f['p_kw']) / 1000
        pq[1] += float(f.get('q_kvar') or 0.0) / 1000
    if factor_potencia is not None:
        from .norma import q_con_factor
        return {a: {b: (pq[0], q_con_factor(pq[0], factor_potencia)) for b, pq in sorted(por.items())}
                for a, por in sorted(out.items())}
    return {a: {b: (pq[0], pq[1]) for b, pq in sorted(por.items())} for a, por in sorted(out.items())}


@dataclass
class CasoDiagnostico:
    caso: str
    fuera: tuple[str, ...]
    converge: bool
    p_sin_servir_mw: float
    sin_tension: list[str]
    violaciones: list[dict[str, Any]]
    perdidas_mw: float | None
    #: Lo que sale de su rango con una regla que no obliga (la referencia de la RM 129-2009): se muestra y no cuenta.
    referencias: list[dict[str, Any]] = field(default_factory=list)
    #: Cada comprobación del rango de tomas de un transformador AT/MT, cumpla o no (12.2.1.a).
    regulacion: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnioDiagnostico:
    anio: int
    demanda_mw: float
    base: CasoDiagnostico
    contingencias: list[CasoDiagnostico] = field(default_factory=list)


@dataclass
class Diagnostico:
    area: str
    motor: str
    limites: dict[str, dict[str, Any]]
    anios: list[AnioDiagnostico] = field(default_factory=list)
    sin_demanda: list[int] = field(default_factory=list)
    faltantes: list[dict[str, Any]] = field(default_factory=list)
    incompletos: list[str] = field(default_factory=list)
    cancelado: bool = False
    avisos: list[str] = field(default_factory=list)
    #: El criterio de tensión de cada barra y la regulación de los transformadores (``limites_de_tension``).
    tension: dict[str, Any] = field(default_factory=dict)
    #: Lo que falta para dar el criterio de tensión de una barra o de un transformador: deja el diagnóstico incompleto.
    huecos_tension: list[dict[str, Any]] = field(default_factory=list)
    #: Las reglas de la norma que el diagnóstico aplicó (años, factor de potencia, N-1), para citarlas (107:RF-20).
    reglas: list[str] = field(default_factory=list)
    #: Por barra con regla de referencia: su tensión calculada, su rango y su fuente (aviso visible, no violación).
    referencias: list[dict[str, Any]] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return not (self.faltantes or self.incompletos or self.sin_demanda or self.cancelado or self.huecos_tension)

    def como_dict(self) -> dict[str, Any]:
        return {**asdict(self), 'completo': self.completo}


def _fuera(v: float, rango: list[float]) -> float | None:
    return rango[0] if v < rango[0] else rango[1] if v > rango[1] else None


def _tension_por_barra(r: ResultadoFlujo, tension: Mapping[str, Any], n_1: bool, caso: CasoDiagnostico) -> None:
    barras = tension.get('barras') or {}
    for barra, v in sorted(r.tensiones_pu.items()):
        e = barras.get(barra) or {}
        rango = e.get('emergencia_pu') if n_1 else e.get('normal_pu')
        if not rango:
            continue
        limite = _fuera(v, rango)
        if limite is None:
            continue
        item = {'elemento': barra, 'caso': caso.caso, 'magnitud': 'tension_pu', 'valor': v, 'limite': limite,
                'rango': list(rango),
                'criterio': e['criterio'], 'regla': e.get('regla'), 'origen': e.get('origen'),
                'fuente': e.get('fuente')}
        (caso.violaciones if e.get('cuenta') else caso.referencias).append(item)
    for reg in tension.get('regulacion') or ():
        if reg.get('falta') or not reg.get('tomas'):
            continue
        for lado in reg['lados']:
            v0 = r.tensiones_pu.get(lado['barra'])
            if v0 is None:
                continue
            lo, hi = _alcanzable(v0, reg['tomas'], lado['lado'])
            rango = lado['rango_pu']
            cumple = hi >= rango[0] and lo <= rango[1]
            item = {'elemento': reg['trafo'], 'caso': caso.caso, 'magnitud': 'regulacion_tension',
                    'barra': lado['barra'], 'valor': v0,
                    'alcanzable': [round(lo, 6), round(hi, 6)], 'limite': list(rango), 'regla': lado['regla'],
                    'criterio': 'regulacion_transformador', 'cumple': cumple}
            caso.regulacion.append(item)
            if not cumple:
                (caso.violaciones if lado['cuenta'] else caso.referencias).append(item)


def _violaciones(r: ResultadoFlujo, limites: Mapping[str, Mapping[str, Any]], incompletos: set[str]
                 ) -> list[dict[str, Any]]:
    """Las de cargabilidad y las barras sin tensión; las de tensión con los límites globales solo si los hay."""
    out = []
    if 'tension_min_pu' in limites and 'tension_max_pu' in limites:
        vmin, vmax = limites['tension_min_pu']['valor'], limites['tension_max_pu']['valor']
        for barra, v in sorted(r.tensiones_pu.items()):
            if v < vmin or v > vmax:
                out.append({'elemento': barra, 'magnitud': 'tension_pu', 'valor': v,
                            'limite': vmin if v < vmin else vmax})
    cmax = limites['cargabilidad_max_pct']['valor']
    for elemento, c in sorted(r.cargabilidad_pct.items()):
        if c > cmax:
            out.append({'elemento': elemento, 'magnitud': 'cargabilidad_pct', 'valor': c, 'limite': cmax,
                        'completo': elemento not in incompletos})
    for barra in r.sin_tension:
        out.append({'elemento': barra, 'magnitud': 'sin_tension', 'valor': None, 'limite': None})
    return out


def _caso(nombre: str, r: ResultadoFlujo, limites, incompletos, tension: Mapping[str, Any] | None = None,
          n_1: bool = False) -> CasoDiagnostico:
    globales = limites if tension is None else {k: v for k, v in limites.items() if not k.startswith('tension_')}
    caso = CasoDiagnostico(nombre, r.fuera, r.converge, r.p_sin_servir_mw, list(r.sin_tension),
                           _violaciones(r, globales, incompletos) if r.converge else [], r.perdidas_mw)
    if r.converge and tension is not None:
        _tension_por_barra(r, tension, n_1, caso)
    return caso


def _resumen_referencias(diag: Diagnostico, tension: Mapping[str, Any],
                         tensiones: Mapping[tuple[int, str], Mapping[str, float]]) -> None:
    """Un aviso por barra con regla de referencia que no obliga: su tensión calculada, su rango y su fuente."""
    barras = {b: e for b, e in (tension.get('barras') or {}).items()
              if e.get('criterio') in ('referencia', 'area15') and not e.get('cuenta')}
    casos = [c for a in diag.anios for c in (a.base, *a.contingencias)]
    for barra, e in sorted(barras.items()):
        valores = [t[barra] for t in tensiones.values() if barra in t]
        fuera = [x for c in casos for x in c.referencias if x['elemento'] == barra and x['magnitud'] == 'tension_pu']
        entrada = {'barra': barra, 'kv': e['kv'], 'nivel': e['nivel'], 'base_kv': e.get('base_kv'),
                   'rango_normal_pu': e.get('normal_pu'), 'rango_emergencia_pu': e.get('emergencia_pu'),
                   'rango_normal_operacion_pu': e.get('normal_operacion_pu'),
                   'rango_emergencia_operacion_pu': e.get('emergencia_operacion_pu'), 'falta': e.get('falta', []),
                   'fuente': e['fuente'], 'regla': e['regla'], 'estado': e['estado'], 'cuenta': False,
                   'casos_fuera': len(fuera), 'min_pu': min(valores, default=None),
                   'max_pu': max(valores, default=None)}
        diag.referencias.append(entrada)
        cifra = ('sin tensión calculada' if not valores
                 else f'tensión calculada {min(valores):.4f}–{max(valores):.4f} p.u. de {e["kv"]:g} kV')
        if e.get('normal_pu'):
            rango = (f'rango normal {e["normal_operacion_pu"][0]:g}–{e["normal_operacion_pu"][1]:g} p.u. de la '
                     f'tensión de operación {e["base_kv"]:g} kV ({e["normal_pu"][0]:.4f}–{e["normal_pu"][1]:.4f} '
                     'p.u. de la nominal)')
        else:
            rango = 'no se compara: falta ' + '; '.join(e.get('falta') or ())
        peor = max(fuera, key=lambda x: abs(x['valor'] - x['limite']), default=None)
        detalle = (f'; fuera de rango en {len(fuera)} caso(s), el peor {peor["valor"]:.4f} p.u. ({peor["caso"]}) '
                   f'contra {peor["limite"]:g}' if peor else '')
        diag.avisos.append(f'tensión de referencia, no cuenta como violación: barra {barra}, {cifra}; {rango}'
                           f'{detalle}; fuente: {e["fuente"]}')


def diagnosticar(area: AreaPit, red: RedArea, filas: Iterable[Mapping[str, Any]], anios: Iterable[int],
                 limites: Mapping[str, Mapping[str, Any]], *, motor: str = 'abierto',
                 cancel: threading.Event | None = None,
                 on_progress: Callable[[int, int, int], None] | None = None,
                 tension: Mapping[str, Any] | None = None, registro: Any = None) -> Diagnostico:
    """El diagnóstico del horizonte ``anios`` (los da el estudio, nunca el código). ``tension``: los límites por barra
    de ``limites_de_tension``; sin ellos, los de tensión del perfil para todas las barras (como antes de PIT-TEN)."""
    faltan = [k for k in OBLIGADOS if k not in limites]
    if tension is None:
        faltan += [k for k in ('tension_min_pu', 'tension_max_pu') if k not in limites]
    if faltan:
        raise PitError(f'faltan los límites {faltan} para el diagnóstico')
    from . import norma
    # 107:RF-20: con el registro, los años de la programación, el factor de potencia de las barras de MT y el N-1 salen
    # de la norma; sin él, como antes.
    fp = norma.factor_potencia(registro)
    demanda = agregar_demanda(area, red, filas, factor_potencia=fp)
    anios, avisos_anios = norma.anios_de_programacion(registro, anios)
    diag = Diagnostico(area.codigo, motor, {k: dict(v) for k, v in limites.items()},
                       faltantes=list(red.faltantes), incompletos=list(red.incompletos), avisos=list(red.avisos))
    diag.avisos += avisos_anios
    diag.reglas = [c for c, v in ((norma.ANIOS, norma.valor(registro, norma.ANIOS)), (norma.FACTOR_POTENCIA, fp),
                                  (norma.N1, norma.valor(registro, norma.N1))) if v is not None]
    if tension is not None:
        diag.tension = {k: v for k, v in tension.items() if k != 'avisos'}
        diag.huecos_tension = [dict(h) for h in tension.get('huecos') or ()]
        diag.avisos += list(tension.get('avisos') or ())
        diag.avisos += [f'falta para la tensión de {h.get("elemento") or h["barra"]}: {"; ".join(h["falta"])}'
                        for h in diag.huecos_tension]
    tensiones: dict[tuple[int, str], dict[str, float]] = {}
    incompletos = set(red.incompletos)
    contingencias = [e['id'] for t in ('linea', 'trafo2', 'trafo3') for e in red.de_tipo(t)]
    for i, anio in enumerate(anios):
        if cancel is not None and cancel.is_set():
            diag.cancelado = True
            diag.avisos.append(f'cancelado antes del año {anio}: quedan sin diagnosticar {anios[i:]}')
            break
        cargas = demanda.get(anio)
        if not cargas:
            diag.sin_demanda.append(anio)
            diag.avisos.append(f'el año {anio} no tiene demanda proyectada en el área {area.codigo}: no se extrapola')
        else:
            base = ejecutar('flujo', red, cargas, motor=motor)['resultado']
            tensiones[(anio, 'base')] = dict(base.tensiones_pu) if base.converge else {}
            ad = AnioDiagnostico(anio, sum(p for p, _q in cargas.values()),
                                 _caso('base', base, limites, incompletos, tension))
            exigen, aviso_n1 = norma.elementos_con_n1(registro, base.flujos, contingencias)
            if aviso_n1 and aviso_n1 not in diag.avisos:
                diag.avisos.append(aviso_n1)
            for eid in exigen:
                r = ejecutar('n_1', red, cargas, motor=motor, fuera=[eid])['resultado']
                tensiones[(anio, f'N-1 {eid}')] = dict(r.tensiones_pu) if r.converge else {}
                ad.contingencias.append(_caso(f'N-1 {eid}', r, limites, incompletos, tension, n_1=True))
            diag.anios.append(ad)
        if on_progress is not None:
            on_progress(i + 1, len(anios), anio)
    if tension is not None:
        _resumen_referencias(diag, tension, tensiones)
    return diag
