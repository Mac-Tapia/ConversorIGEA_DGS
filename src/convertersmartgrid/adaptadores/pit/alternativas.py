"""Alternativas de transmisión mutuamente excluyentes y su comparación (107:RF-5, 107:RF-8).

Cada alternativa es un conjunto de cambios sobre la red del área (altas con su costo, bajas), y todas se evalúan con
la **misma demanda y el mismo motor**, que el resultado fija con su huella. Se valora:

- la inversión con ``costos_fuentes.valorar_obra`` (ámbito ``transmision``), o con un módulo del libro CAPEX de la
  empresa (``set_nueva.leer_modulos_pit``), que es de la empresa y no oficial, y así se rotula;
- el COyM **por elemento**: su costo de inversión por el porcentaje de ``pit.coym_pct`` del registro vigente en cada
  año (la 217-2013 lo define así, art. 17.2 y 17.3). Si la regla da un cuadro por ubicación y nivel de tensión (la
  163-2021), cada elemento toma el de su ubicación (``ubicacion`` del elemento o, si no la trae, la del área en el
  perfil: ``pit.areas[].ubicacion``) y su nivel; un transformador, el de su mayor tensión (17.3), con un aviso si es
  elevador, porque la 163-2021 dice «lado primario». Un año sin porcentaje publicado, o un elemento sin ubicación o
  sin nivel en el cuadro, es un hueco nombrado: la alternativa queda incompleta (aclaración de 107:RF-5);
- las pérdidas del flujo de cada año y, si el registro da su precio (``pit.precio_perdidas``) y sus horas
  equivalentes (``pit.horas_perdidas``), su valor;
- la confiabilidad según la matriz de motores (con el abierto, la potencia sin servir en el peor N-1);
- el valor presente con ``pide_economia.frc`` y ``van``, con la tasa (``pit.tasa_actualizacion``) y la vida útil
  (``pit.vida_util_anios``) del registro.

Lo que falta deja la alternativa **incompleta y fuera de la comparación**, nunca con un 0 (por eso no se usa
``costo_anual``, que suma como 0 lo que falta). Una regla que no obliga se usa como referencia y se dice (107:RF-8), y
una regla con pendientes en el registro (``pendientes``) se usa con un aviso que los nombra; su verificación
(``verificacion``: fecha, resultado y fuentes), si la tiene, va con la regla en el resultado (aclaración de RF-8).
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from ...aplicacion import costos_fuentes
from ...aplicacion.pide_economia import frc, van
from ...dominio.registro_normativo import ReglaAmbigua, RegistroError, RegistroNormativo
from ...dominio.pit import PitError
from .motores import capacidad, ejecutar
from ...aplicacion.pit.red_area import RedArea

__all__ = ['Comparacion', 'ResultadoAlternativa', 'aplicar', 'evaluar']

_REGLAS = ('pit.tasa_actualizacion', 'pit.vida_util_anios', 'pit.coym_pct')
_REGLAS_PERDIDAS = ('pit.precio_perdidas', 'pit.horas_perdidas')


@dataclass
class ResultadoAlternativa:
    nombre: str
    completa: bool
    motivos: list[str] = field(default_factory=list)
    inversion: dict[str, float] = field(default_factory=dict)
    inversion_detalle: dict[str, Any] = field(default_factory=dict)
    #: COyM del primer año con COyM en el flujo, por moneda (lo que lee el resumen ejecutivo).
    coym_anual: dict[str, float] = field(default_factory=dict)
    #: COyM de cada año del flujo, por moneda, y su detalle por elemento (porcentaje, nivel, ubicación y norma).
    coym_por_anio: dict[int, dict[str, float]] = field(default_factory=dict)
    coym_detalle: list[dict[str, Any]] = field(default_factory=list)
    #: Huecos nombrados (``regla``, ``anio``, ``elemento``, ``causa``): lo que falta en la norma o en los datos.
    huecos: list[dict[str, Any]] = field(default_factory=list)
    perdidas_mw: dict[int, float] = field(default_factory=dict)
    perdidas_valor: dict[int, float] = field(default_factory=dict)
    confiabilidad: dict[str, Any] = field(default_factory=dict)
    anualidad: dict[str, float] = field(default_factory=dict)
    valor_presente: dict[str, float] = field(default_factory=dict)
    violaciones: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Comparacion:
    motor: str
    demanda_huella: str
    reglas: dict[str, dict[str, Any]]
    alternativas: list[ResultadoAlternativa]
    orden: list[str]
    fuera_de_comparacion: list[str]
    avisos: list[str] = field(default_factory=list)
    cancelado: bool = False

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def aplicar(red: RedArea, cambios: Iterable[Mapping[str, Any]]) -> RedArea:
    """La red con las altas y sin las bajas de una alternativa; la red de partida no cambia."""
    nueva = copy.deepcopy(red)
    for c in cambios:
        if c.get('accion') == 'baja':
            eid = str(c['elemento'])
            for tipo, lista in nueva.elementos.items():
                nueva.elementos[tipo] = [e for e in lista if e['id'] != eid]
        elif c.get('accion') == 'alta':
            e = dict(c['elemento'])
            e.setdefault('area', red.area)
            nueva.elementos.setdefault(str(e['tipo']), []).append(e)
        else:
            raise PitError(f'cambio con acción {c.get("accion")!r}: las alternativas dan altas y bajas')
    return nueva


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None) -> dict[str, Any] | None:
    """La regla vigente, o ``None`` si el registro no la trae. Una regla ambigua (varias normas vigentes a la vez y la
    más reciente no modifica a las demás, RN-AMB) no es una regla que falte: ``ReglaAmbigua`` sube, para que la
    alternativa lo diga con las normas que la traen en vez de «falta la regla»."""
    try:
        r = registro.regla(clave, fecha)
    except ReglaAmbigua:
        raise
    except RegistroError:
        return None
    return {'clave': clave, 'valor': r.regla.valor, 'norma': r.norma.acto, 'estado': r.estado,
            'obligatoria': r.obligatoria, 'articulo_o_anexo': r.regla.articulo_o_anexo, 'pagina': r.regla.pagina,
            'vigencia_desde': r.norma.vigencia_desde, 'vigencia_hasta': r.norma.vigencia_hasta,
            'pendientes': [dict(x) for x in r.regla.pendientes],
            'verificacion': dict(r.regla.verificacion) if r.regla.verificacion else None}


def _aviso_pendientes(r: Mapping[str, Any]) -> list[str]:
    """Un aviso por cada pendiente de la regla en el registro (aclaración de 107:RF-8)."""
    valor = 'su cuadro' if isinstance(r['valor'], Mapping) else r['valor']
    return [f'{r["clave"]} = {valor} de {r["norma"]}, con un pendiente: {p["descripcion"]} (aclaración de 107:RF-8)'
            for p in r.get('pendientes') or ()]


#: Elevador: el lado primario no es el de mayor tensión (la 163-2021 dice «lado primario»; la 217-2013, «mayor»).
_ELEVADOR = 'elevador'
_TRAFOS = ('trafo2', 'trafo3')


def _kv_del_elemento(e: Mapping[str, Any], red: RedArea) -> tuple[float | None, float | None]:
    """(mayor tensión, tensión del lado primario) del elemento; ``None`` si no se sabe. Fuera de los transformadores,
    las dos son la del elemento (``kv``) o la de su barra."""
    if e.get('tipo') in _TRAFOS:
        kvs = [float(e[k]) for k in ('vn_hv_kv', 'vn_mv_kv', 'vn_lv_kv') if e.get(k) not in (None, '')]
        if not kvs:
            return None, None
        elevador = str(e.get('funcion') or '').strip().lower() == _ELEVADOR
        return max(kvs), (min(kvs) if elevador else max(kvs))
    if e.get('kv') not in (None, ''):
        return float(e['kv']), float(e['kv'])
    barras = {b['id']: b for b in red.de_tipo('barra')}
    for clave in ('desde', 'barra', 'hv'):
        b = barras.get(str(e.get(clave)))
        if b is not None and b.get('kv') not in (None, ''):
            return float(b['kv']), float(b['kv'])
    return None, None


def _nivel(kv: float, niveles: Iterable[Mapping[str, Any]], e: Mapping[str, Any]) -> tuple[str | None, str]:
    """El nivel del cuadro en que cae ``kv``, o ``None`` con la causa: fuera de los rangos, o un nivel que el cuadro
    reserva a las celdas de alimentadores de MT dentro de las SET y el elemento no lo es."""
    for n in niveles:
        desde, hasta = n.get('kv_desde'), n.get('kv_hasta')
        if desde is not None and (kv < desde or (kv == desde and not n.get('desde_incluido'))):
            continue
        if hasta is not None and (kv > hasta or (kv == hasta and not n.get('hasta_incluido'))):
            continue
        celda_mt = (e.get('tipo') == 'celda' and bool(e.get('set'))
                    and str(e.get('funcion') or '').strip().lower() == 'alimentador')
        if n.get('solo') == 'celda_alimentador_mt_en_set' and not celda_mt:
            return None, (f'{kv:g} kV es del nivel {n["nivel"]}, que el cuadro da solo para celdas de alimentadores '
                          'de MT dentro de las SET')
        return str(n['nivel']), ''
    return None, f'{kv:g} kV no cae en ningún nivel de tensión del cuadro'


def _pct_del_elemento(valor: Any, e: Mapping[str, Any], red: RedArea, ubicacion: str
                      ) -> tuple[float | None, dict[str, Any], str, str]:
    """(porcentaje, detalle, causa si falta, aviso). Un número vale para todos los elementos; un cuadro, según la
    ubicación y el nivel de tensión del elemento."""
    if not isinstance(valor, Mapping):
        return float(valor), {}, '', ''
    zona = str(e.get('ubicacion') or ubicacion or '').strip().lower()
    porcentajes = valor.get('porcentajes') or {}
    if not zona:
        return None, {}, ('sin ubicación geográfica (costa, sierra o selva): ni el elemento («ubicacion») ni el área '
                          '(pit.areas[].ubicacion del perfil) la declaran, y no se supone'), ''
    if zona not in porcentajes:
        return None, {}, f'la ubicación «{zona}» no está en el cuadro ({sorted(porcentajes)})', ''
    mayor, primario = _kv_del_elemento(e, red)
    if mayor is None:
        return None, {}, 'sin tensión nominal: no se sabe su nivel en el cuadro', ''
    niveles = valor.get('niveles') or ()
    nivel, causa = _nivel(mayor, niveles, e)
    if nivel is None:
        return None, {}, causa, ''
    pct = float(porcentajes[zona][nivel])
    detalle = {'ubicacion': zona, 'nivel': nivel, 'kv': mayor,
               'codigo': ((valor.get('codigos') or {}).get(zona) or {}).get(nivel)}
    aviso = ''
    if e.get('tipo') in _TRAFOS and primario != mayor:
        # El nivel del primario, como lo leería la nota (**): sin la restricción de las celdas de MT.
        nivel_p, _ = _nivel(primario, [{k: v for k, v in n.items() if k != 'solo'} for n in niveles], e)
        pct_p = porcentajes[zona].get(nivel_p) if nivel_p else None
        segun_163 = f'{primario:g} kV, {nivel_p or "sin nivel en el cuadro"}' + (
            f', {float(pct_p):g} %' if pct_p is not None else '')
        aviso = (f'{e["id"]}: transformador elevador; se toma el nivel de su mayor tensión ({mayor:g} kV, {nivel}, '
                 f'{pct:g} %) según el art. 17.3 de la RCD 217-2013-OS/CD, y la nota (**) de la RCD 163-2021-OS/CD '
                 f'dice «lado primario» ({segun_163}): discrepancia entre las dos normas')
        detalle['aviso'] = aviso
    return pct, detalle, '', aviso


def _coym(res: ResultadoAlternativa, cambios: Iterable[Mapping[str, Any]], red: RedArea,
          registro: RegistroNormativo, anios: list[int], ubicacion: str) -> tuple[list[dict[str, Any]], list[str]]:
    """COyM de cada año del flujo, elemento por elemento (aclaración de 107:RF-5). Devuelve las reglas usadas y los
    avisos; lo que falta va a ``res.huecos`` y a ``res.motivos``."""
    elementos = {str(c['elemento']['id']): c['elemento'] for c in cambios if c.get('accion') == 'alta'}
    oficiales = (res.inversion_detalle.get('oficial') or {}).get('valorados') or ()
    ci = [(str(x['elemento']), float(x['costo']), x['moneda'])
          for x in [*oficiales, *(res.inversion_detalle.get('empresa') or ())]]
    usadas: dict[str, dict[str, Any]] = {}
    avisos: list[str] = []

    def hueco(anio: int, elemento: str | None, causa: str) -> None:
        res.huecos.append({'regla': 'pit.coym_pct', 'anio': anio, 'elemento': elemento, 'causa': causa})
        donde = f'{anio}' + (f', {elemento}' if elemento else '')
        res.motivos.append(f'pit.coym_pct ({donde}): {causa}')

    # El COyM entra en el flujo desde el año 1 (11.3 de la 217-2013); con un solo año, el de ese año.
    for anio in (anios[1:] or anios):
        # El porcentaje tiene que estar publicado todo el año, con el mismo cuadro: no se prorratea ni se supone.
        ini = _regla(registro, 'pit.coym_pct', f'{anio}-01-01')
        fin = _regla(registro, 'pit.coym_pct', f'{anio}-12-31')
        if ini is None or fin is None:
            dia = f'{anio}-01-01' if ini is None else f'{anio}-12-31'
            hueco(anio, None, f'sin porcentaje de COyM publicado para el {dia} (ninguna norma del registro lo da '
                              'vigente ese día): el año queda con su hueco y no se supone ningún porcentaje')
            continue
        if ini['norma'] != fin['norma']:
            hueco(anio, None, f'el año cambia de cuadro de COyM ({ini["norma"]} y {fin["norma"]}): prorratearlos no lo '
                              'dice la norma')
            continue
        usadas[ini['norma']] = ini
        por_moneda: dict[str, float] = {}
        for eid, costo, moneda in ci:
            pct, detalle, causa, aviso = _pct_del_elemento(ini['valor'], elementos.get(eid, {'id': eid}), red,
                                                           ubicacion)
            if pct is None:
                hueco(anio, eid, causa)
                continue
            if aviso and aviso not in avisos:
                avisos.append(aviso)
            coym = costo * pct / 100
            por_moneda[moneda] = por_moneda.get(moneda, 0.0) + coym
            res.coym_detalle.append({'anio': anio, 'elemento': eid, 'ci': costo, 'moneda': moneda, 'pct': pct,
                                     'coym': coym, 'norma': ini['norma'], **detalle})
        res.coym_por_anio[anio] = por_moneda
    return list(usadas.values()), avisos


def _inversion(cambios, tablas) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    oficiales, motivos, empresa = [], [], []
    for c in cambios:
        if c.get('accion') != 'alta':
            continue
        e = c['elemento']
        if c.get('modulo_pit'):
            m = c['modulo_pit']
            if not m.get('moneda'):
                motivos.append(f'{e["id"]}: el módulo del libro CAPEX no dice su moneda')
                continue
            empresa.append({'elemento': e['id'], 'costo': float(m['costo']), 'moneda': m['moneda'],
                            'fuente': 'libro CAPEX de la empresa (no oficial)', 'descripcion': m.get('descripcion'),
                            'huella': str(m.get('huella') or '')})
        elif c.get('costo'):
            oficiales.append({'elemento': e['id'], 'ambito': 'transmision', **c['costo']})
        else:
            motivos.append(f'{e["id"]}: sin costo declarado (ni módulo estándar ni módulo del libro CAPEX)')
    detalle: dict[str, Any] = {'empresa': empresa}
    total: dict[str, float] = {}
    if oficiales:
        if 'transmision' not in tablas:
            motivos.append('sin fuente de costos de transmisión para los módulos estándar')
        else:
            v = costos_fuentes.valorar_obra(oficiales, {'transmision': tablas['transmision']})
            detalle['oficial'] = v
            motivos += [f'{x["elemento"]}: {x["motivo"]}' for x in v['sin_costo']]
            for moneda, monto in v['total_por_moneda'].items():
                total[moneda] = total.get(moneda, 0.0) + monto
    for x in empresa:
        total[x['moneda']] = total.get(x['moneda'], 0.0) + x['costo']
    if len(total) > 1:
        motivos.append(f'la inversión está en {sorted(total)}: sumarlas exigiría un tipo de cambio no declarado')
    return total, detalle, motivos


def _huella(datos: Any) -> str:
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def evaluar(red: RedArea, alternativas: Iterable[Mapping[str, Any]], demanda: Mapping[int, Mapping[str, tuple]],
            anios: Iterable[int], registro: RegistroNormativo, tablas: Mapping[str, Any], *,
            fecha: str | None = None, motor: str = 'abierto', cancel: threading.Event | None = None,
            ubicacion: str = '') -> Comparacion:
    """Evalúa las alternativas con la misma demanda y el mismo motor, y las ordena por valor presente.

    ``ubicacion`` es la del área en el perfil (``pit.areas[].ubicacion``: costa, sierra o selva), para el cuadro del
    COyM; un elemento que declare la suya la usa en su lugar. Sin ninguna de las dos, el COyM por cuadro es un hueco."""
    from ...dominio.pit import norma
    # 107:RF-20: la comparación dentro del horizonte de la norma (3.14), y sus reglas citadas (5.9.3, 11.3, 17.2, 24.2).
    anios, avisos_norma = norma.anios_de_alternativas(registro, anios, fecha)
    citadas, avisos_citadas = norma.reglas_citadas(registro, fecha)
    reglas, ambiguas = {}, {}
    for c in _REGLAS + _REGLAS_PERDIDAS + tuple(citadas) + (norma.N1,):
        try:
            r = _regla(registro, c, fecha)
        except ReglaAmbigua as exc:
            ambiguas[c] = str(exc)  # justificado: se nombra en los motivos de cada alternativa, abajo (RN-AMB)
            continue
        if r is not None:
            reglas[c] = r
    comp = Comparacion(motor, _huella({a: demanda.get(a) for a in anios}), reglas, [], [], [])
    comp.avisos += avisos_norma + avisos_citadas
    solo_citadas = set(citadas) | {norma.N1}  # se citan o acotan el N-1; ningún número de la comparación sale de ellas
    for clave, r in sorted(reglas.items()):
        if not r['obligatoria'] and clave not in solo_citadas:
            comp.avisos.append(f'{clave} = {r["valor"]} de {r["norma"]} ({r["estado"]}) se usa como referencia, '
                               'no como obligatoria (107:RF-8)')
    for clave in ('pit.tasa_actualizacion', 'pit.vida_util_anios'):
        if clave in reglas:
            comp.avisos += _aviso_pendientes(reglas[clave])
    valorar_perdidas = all(c in reglas for c in _REGLAS_PERDIDAS)
    if not valorar_perdidas:
        comp.avisos.append('el registro no da el precio ni las horas de las pérdidas: se comparan en MW, sin valorar')
    conf = capacidad(motor, 'confiabilidad')
    nombres = set()
    for alt in alternativas:
        if cancel is not None and cancel.is_set():
            comp.cancelado = True
            comp.avisos.append('evaluación cancelada entre alternativas')
            break
        nombre = str(alt['nombre'])
        if nombre in nombres:
            raise PitError(f'la alternativa {nombre!r} está dos veces')
        nombres.add(nombre)
        cambios = list(alt.get('cambios') or ())
        res = ResultadoAlternativa(nombre, True)
        res.inversion, res.inversion_detalle, motivos = _inversion(cambios, tablas)
        res.motivos += motivos
        res.motivos += [ambiguas[c] if c in ambiguas else f'falta la regla {c} en el registro normativo'
                        for c in _REGLAS if c not in reglas]
        if 'pit.coym_pct' in reglas and not motivos:
            usadas, avisos = _coym(res, cambios, red, registro, anios, ubicacion)
            for r in usadas:
                comp.avisos += [a for a in _aviso_pendientes(r) if a not in comp.avisos]
            comp.avisos += [a for a in avisos if a not in comp.avisos]
        red_alt = aplicar(red, cambios)
        peor = 0.0
        for anio in anios:
            cargas = demanda.get(anio)
            if not cargas:
                res.motivos.append(f'el año {anio} no tiene demanda: la alternativa no se evalúa en él')
                continue
            base = ejecutar('flujo', red_alt, cargas, motor=motor)['resultado']
            if not base.converge:
                res.motivos.append(f'el flujo del año {anio} no converge: {base.mensaje}')
                continue
            res.perdidas_mw[anio] = base.perdidas_mw
            if valorar_perdidas:
                res.perdidas_valor[anio] = (base.perdidas_mw * float(reglas['pit.horas_perdidas']['valor'])
                                            * float(reglas['pit.precio_perdidas']['valor']))
            candidatos = [e['id'] for t in ('linea', 'trafo2', 'trafo3') for e in red_alt.de_tipo(t)]
            exigen, aviso_n1 = norma.elementos_con_n1(registro, base.flujos, candidatos, fecha)
            if aviso_n1 and aviso_n1 not in comp.avisos:
                comp.avisos.append(aviso_n1)
            for eid in exigen:
                r = ejecutar('n_1', red_alt, cargas, motor=motor, fuera=[eid])['resultado']
                peor = max(peor, r.p_sin_servir_mw if r.converge else float('inf'))
        res.confiabilidad = {'motor': motor, 'alcance': conf.alcance, 'texto': conf.texto,
                             'p_sin_servir_peor_n_1_mw': peor}
        if not res.motivos:
            tasa = float(reglas['pit.tasa_actualizacion']['valor'])
            vida = int(reglas['pit.vida_util_anios']['valor'])
            primero = (anios[1:] or anios)[0]
            for moneda, ci in res.inversion.items():
                res.coym_anual[moneda] = res.coym_por_anio[primero].get(moneda, 0.0)
                res.anualidad[moneda] = ci * frc(tasa, vida)
                perdidas = [res.perdidas_valor.get(a, 0.0) if valorar_perdidas else 0.0 for a in anios]
                # Año 0: la inversión y las pérdidas de ese año; desde el 1, COyM y pérdidas (11.3 de la 217-2013).
                flujos = [ci + perdidas[0]] + [res.coym_por_anio[a].get(moneda, 0.0) + p
                                               for a, p in zip(anios[1:], perdidas[1:])]
                res.valor_presente[moneda] = van(flujos, tasa)
        res.completa = not res.motivos
        comp.alternativas.append(res)
    completas = [a for a in comp.alternativas if a.completa]
    monedas = {m for a in completas for m in a.valor_presente}
    if len(monedas) > 1:
        comp.avisos.append(f'las alternativas completas están en {sorted(monedas)}: no se ordenan sin tipo de cambio')
        comp.orden = []
    else:
        moneda = next(iter(monedas), None)
        comp.orden = [a.nombre for a in sorted(completas, key=lambda a: (a.valor_presente.get(moneda, 0.0), a.nombre))]
    comp.fuera_de_comparacion = [a.nombre for a in comp.alternativas if not a.completa]
    return comp
