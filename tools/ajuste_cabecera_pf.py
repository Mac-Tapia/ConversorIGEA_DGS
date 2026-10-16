#!/usr/bin/env python
"""Ajusta las demandas de un alimentador a su máxima de cabecera en DIgSILENT (spec 006).

Recibe el plan de ``services.ajuste_plan``: el proyecto, el alimentador, el objetivo (la
máxima medida), los clientes importantes cruzados de ese alimentador y el kVA de cada
SED en la entrada original. El reparto y el cuadre son de ``igea_dgs.ajuste_cabecera``;
aquí está lo que toca DIgSILENT:

- Las cargas de SED del alimentador y el kVA de cada una: el de los transformadores
  conectados a su barra y, si no hay, el de la entrada original (RF-10, RF-24).
- Lo que entra por la cabecera: el flujo de la rama del cubículo del ``ElmFeeder``.
- Los remedios del flujo de carga (RF-16): ajustes del ``ComLdf`` que se guardan antes y
  se restituyen al final, porque son del caso de estudio del operador y no de la
  variación; el informe dice cuáles hicieron falta para converger (RF-17).
- El diagnóstico cuando no converge (RF-15).

Spec 015: se calibra en «Sin proyecto», la copia del «Caso base» verificado, y solo se
cambian las cargas: demanda, estado de servicio y marca fija o escalable (RF-16, RF-20).
La demanda se escribe y se mide con el escenario de «Sin proyecto» activo, que es donde
queda; no se crea ni se apaga ninguna variación (RF-26), y el «Caso base» conserva su
demanda (RF-19). La marca fija o escalable es dato de la red en DIgSILENT y la ven todos
los casos (RF-37). Si existe «Con proyecto», su escenario recibe la misma demanda
(014:RF-4). No se comprueba nada de la red: eso es de la verificación del «Caso base»
(RF-17).

    python tools/ajuste_cabecera_pf.py --plan plan.json --output-json informe.json \\
        [--simular] [--cancel-file cancelar.flag]

Códigos de salida: 0 cuadrado (o simulado), 2 sin cuadrar o con fallos, 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import replace
from pathlib import Path

from cargas_pf import (
    Alimentadores,
    _num,
    activar_proyecto,
    detalle_cabecera,
    error_inesperado,
    error_relectura,
    escribir_carga,
    medir_cabecera,
    potencia,
)
from casos_pf import NOMBRES, es_de_carga_nueva, preparar_sin
from casos_pf import caso as caso_del_sistema

from igea_dgs.native_action import native_action_block_report

#: Tensión (p.u.) por debajo de la cual una barra cuenta como caída en el diagnóstico.
TENSION_CAIDA = 0.5
#: Elementos sobrecargados que se listan en el diagnóstico, de más a menos cargado.
MAX_SOBRECARGAS = 20
#: Lo que una carga consume en el flujo frente a lo escrito (015:RF-49): con cargas PQ
#: DIgSILENT da lo escrito a 1e-12; CA101 (2026-10-15) consumía el 73 % por u².
CONSUMO_REL = 1e-3
CONSUMO_ABS = 0.01
#: Margen del factor de potencia de las escaladas frente al pedido (015:RF-67).
FP_MARGEN = 1e-3
#: Ajustes del ``ComLdf`` que cambian lo que consume una carga (015:RF-51).
AJUSTES_QUE_CAMBIAN_EL_CONSUMO = {
    'iopt_lev': 'adaptación automática del modelo',
    'iopt_pq': 'dependencia de la tensión de las cargas',
}


# =========================================================================== lectura
def kva_en_pf(carga) -> float | None:
    """kVA de los transformadores conectados a la barra de la carga, sumados.

    En los DGS del conversor la carga de la SED cuelga de la barra de baja de su
    transformador; con varios transformadores en paralelo en la misma barra, la SED
    tiene la suma. Un ``ElmTr2`` con ``ntnum`` unidades en paralelo cuenta ``ntnum``
    veces su tipo: en PA217 (2026-10-16) SE30940 quedó con 8 × 630 kVA de la NTP
    370.400 y, sin ``ntnum``, se veía con 630 kVA al 606 %.
    """
    try:
        barra = carga.bus1.cterm
        conectados = list(barra.GetConnectedElements())
    except Exception:  # noqa: BLE001 - carga sin conectar
        return None
    total = 0.0
    for e in conectados:
        if e.GetClassName() != 'ElmTr2':
            continue
        strn = _num(getattr(e, 'typ_id', None), 'strn') if getattr(e, 'typ_id', None) else None
        if strn:
            total += strn * 1000.0 * max(1, int(_num(e, 'ntnum') or 1))
    return total or None


def _alimentadores_nativos(obj) -> set[str]:
    """Etiquetas ``p:alimentador``; PowerFactory puede releerlas como una lista."""
    try:
        valor = obj.GetAttribute('p:alimentador')
    except Exception:  # noqa: BLE001 - modelos antiguos no tienen la columna
        try:
            valor = getattr(obj, 'p:alimentador')
        except Exception:  # noqa: BLE001
            return set()
    valores = valor if isinstance(valor, (list, tuple, set)) else (valor,)
    return {str(v).strip() for v in valores if str(v or '').strip()}


def _clave_objeto_nativo(obj):
    """Identidad estable aun si la API entrega otro wrapper del mismo objeto."""
    try:
        return 'pf', str(obj.GetFullName())
    except Exception:  # noqa: BLE001 - el doble y versiones antiguas admiten id
        return 'py', id(obj)


def cargas_sed(alims: Alimentadores, feeder: str, *, audit: dict | None = None) -> tuple[dict, list[dict]]:
    """Carga de cada SED, uniendo topología y la etiqueta nativa del alimentador.

    En CA101, ``ElmFeeder.GetObjs('ElmLod')`` devolvía 95 cargas aunque el proyecto tenía
    168 ``ElmLod`` con ``p:alimentador=CA101``. La topología sigue admitiendo proyectos
    antiguos sin esa columna, pero una etiqueta no vacía y contradictoria excluye el objeto.
    """
    from igea_dgs.demanda_medida import clave_codigo

    clave_feeder = clave_codigo(feeder)
    candidatos: dict[tuple[str, object], object] = {}
    topologia = list(alims.objetos(feeder, 'ElmLod'))
    topologia_aceptada = []
    contradictorias = []
    for obj in topologia:
        etiquetas = {clave_codigo(x) for x in _alimentadores_nativos(obj)}
        if not etiquetas or clave_feeder in etiquetas:
            topologia_aceptada.append(obj)
            candidatos[_clave_objeto_nativo(obj)] = obj
        else:
            contradictorias.append(obj)
    try:
        globales = alims.app.GetCalcRelevantObjects('*.ElmLod')
    except Exception:  # noqa: BLE001 - la selección topológica sigue disponible
        globales = []
    etiquetadas = []
    for obj in globales:
        if clave_feeder in {clave_codigo(x) for x in _alimentadores_nativos(obj)}:
            etiquetadas.append(obj)
            candidatos.setdefault(_clave_objeto_nativo(obj), obj)

    por_nombre: dict[str, list] = {}
    for obj in candidatos.values():
        if not int(getattr(obj, 'outserv', 0) or 0):
            por_nombre.setdefault(obj.loc_name, []).append(obj)
    unicas = {n: objs[0] for n, objs in por_nombre.items() if len(objs) == 1}
    ambiguas = [{'sed': n, 'motivo': f'{len(objs)} cargas con ese nombre en {feeder}'}
                for n, objs in por_nombre.items() if len(objs) > 1]
    wrappers = topologia_aceptada + etiquetadas
    population = {
        'algoritmo': 'UNION_TOPOLOGIA_Y_P_ALIMENTADOR',
        'topologia_wrappers': len(topologia),
        'topologia_aceptada': len(topologia_aceptada),
        'etiqueta_wrappers': len(etiquetadas),
        'contradictorias_excluidas': len(contradictorias),
        'duplicados_colapsados': len(wrappers) - len({_clave_objeto_nativo(o) for o in wrappers}),
        'union_objetos': len(candidatos),
        'cargas_activas_unicas': len(unicas),
        'nombres_ambiguos': len(ambiguas),
    }
    cargas_sed.last_audit = population
    if audit is not None:
        audit.update(population)
    return unicas, ambiguas


def kva_por_sed(cargas: dict, kva_entrada: dict) -> tuple[dict, dict]:
    """kVA de cada SED y de dónde salió: ``pf`` o ``entrada`` (RF-10)."""
    from igea_dgs.demanda_medida import clave_codigo

    entrada = {clave_codigo(k): v for k, v in (kva_entrada or {}).items()}
    kva, origen = {}, {}
    for sed, obj in cargas.items():
        v = kva_en_pf(obj)
        if v:
            kva[sed], origen[sed] = v, 'pf'
            continue
        v = entrada.get(clave_codigo(sed))
        kva[sed], origen[sed] = (v, 'entrada') if v else (None, '')
    return kva, origen


# =========================================================================== remedios del flujo
class Remedios:
    """Ajustes del ``ComLdf`` de la escalera (RF-16): se guardan para restituirlos."""

    def __init__(self, app):
        self.ldf = app.GetFromStudyCase('ComLdf')
        self.originales: dict = {}

    def aplicar(self, nombre: str, ajustes: dict) -> list[str]:
        cambios = []
        for attr, valor in ajustes.items():
            if not self._tiene(attr):
                cambios.append(f'{attr}: no existe en esta versión de DIgSILENT')
                continue
            antes = getattr(self.ldf, attr)
            self.originales.setdefault(attr, antes)
            nuevo = antes * valor[1] if isinstance(valor, tuple) else valor
            setattr(self.ldf, attr, nuevo)
            cambios.append(f'{attr}: {antes} → {nuevo}')
            # Sin flecha ni comillas angulares: a mano, la consola de Windows es cp1252.
            print(f'  remedio "{nombre}": {attr} {antes} -> {nuevo}')
        return cambios

    def _tiene(self, attr) -> bool:
        try:
            return bool(self.ldf.HasAttribute(attr))
        except Exception:  # noqa: BLE001 - versiones sin HasAttribute
            return hasattr(self.ldf, attr)

    def aplicados(self) -> dict:
        """Los valores que dejaron los remedios, por atributo."""
        return {attr: getattr(self.ldf, attr) for attr in self.originales}

    @staticmethod
    def aplicar_en(ldf, valores: dict) -> None:
        """Los mismos ajustes en el ComLdf de otro caso (015:RF-46)."""
        for attr, valor in valores.items():
            setattr(ldf, attr, valor)

    def restituir(self) -> dict:
        for attr, valor in self.originales.items():
            setattr(self.ldf, attr, valor)
        return dict(self.originales)


# =========================================================================== diagnóstico
def diagnostico(alims: Alimentadores, feeder: str, cargas: dict, kva: dict,
                fallido=None) -> dict:
    """Por qué no converge (RF-15), con los resultados del último flujo que convergió.

    Sin ninguno convergido solo se puede mirar lo escrito: transformadores con más carga
    que su potencia, como ``SE50111`` en 260924.mdb (1.197 kW sobre 50 kVA), que dejaba su
    barra de baja en 0,6 p.u. y estancaba el Newton de toda la red.
    """
    barras = alims.objetos(feeder, 'ElmTerm')
    sin_tension, tensiones = [], []
    for b in barras:
        u = _num(b, 'm:u') if b.HasResults() else None
        if u is None or u < TENSION_CAIDA:
            sin_tension.append(b.loc_name)
        else:
            tensiones.append((u, b.loc_name))
    sobrecargas = []
    for clase in ('ElmTr2', 'ElmLne'):
        for e in alims.objetos(feeder, clase):
            carga = _num(e, 'c:loading')
            if carga is not None and carga > 100.0:
                sobrecargas.append({'elemento': e.loc_name, 'clase': clase, 'carga_pct': carga})
    sobrecargas.sort(key=lambda x: -x['carga_pct'])
    out = {'barras_sin_tension': sin_tension[:MAX_SOBRECARGAS],
           'n_barras_sin_tension': len(sin_tension),
           'sobrecargados': sobrecargas[:MAX_SOBRECARGAS]}
    if tensiones:
        u, nombre = min(tensiones)
        out['tension_minima'] = {'barra': nombre, 'u_pu': u}
    if fallido is not None:
        # El reparto que no convergió: qué SED pedían más que su transformador.
        excedidas = []
        for sed, d in fallido.demandas.items():
            k = kva.get(sed)
            s = math.hypot(d.kw, d.kvar)
            if k and s > k:
                excedidas.append({'sed': sed, 'kva': k, 'carga_kva': s})
        excedidas.sort(key=lambda x: -x['carga_kva'] / x['kva'])
        out['sed_por_encima_de_su_transformador'] = excedidas[:MAX_SOBRECARGAS]
    return out


# =========================================================================== escenario
# =========================================================================== spec 014
def cambios_manuales(cargas: dict, ultima: dict | None) -> tuple[list[dict], str | None]:
    """Cargas cuya demanda difiere de la que dejó la última calibración (014:RF-10 a RF-13).

    La demanda de ahora se lee con el escenario de «Sin proyecto» activo, que es la que
    manda. La de la calibración la guarda la web de su informe (015, T8): desde la spec
    015 la calibración no deja variación en la que leerla. Sin calibración anterior no hay
    con qué comparar (RF-13).
    """
    ultima = ultima or {}
    grabadas = ultima.get('sed') or {}
    if not grabadas:
        return [], None
    nombre = ultima.get('nombre') or 'la última calibración'
    out = []
    for sed, obj in cargas.items():
        if sed not in grabadas:
            continue
        ahora, antes = potencia_efectiva(obj), tuple(grabadas[sed])
        if all(_cerca(a, b, rel=1e-3, abs_=0.01) for a, b in zip(ahora, antes)):
            continue
        out.append({'sed': sed, 'calibracion': nombre,
                    'manual': {'kw': ahora[0], 'kvar': ahora[1]},
                    'ajuste': {'kw': antes[0], 'kvar': antes[1]}})
    return out, nombre


def _restaurar_cargas(cargas: dict, fotos: list[dict], apagar: dict, antes_apagar: dict) -> None:
    """Deja las cargas como estaban antes de calibrar (validación nativa fallida)."""
    por_sed = {f['sed']: f for f in fotos}
    for sed, obj in cargas.items():
        foto = por_sed.get(sed)
        if foto is None:
            continue
        try:
            escrita = foto.get('escrita') or {'p_kw': foto['p_kw'], 'q_kvar': foto['q_kvar']}
            escribir_carga(obj, escrita['p_kw'] / 1000.0, escrita['q_kvar'] / 1000.0)
            obj.scale0 = foto.get('scale0', 1.0)
            obj.outserv = foto['outserv']
            obj.i_scale = foto['i_scale']
        except Exception:  # noqa: BLE001 - lo que no se pueda restaurar lo dice el informe
            continue
    for sed, obj in apagar.items():
        try:
            obj.outserv = antes_apagar.get(sed, 0)
        except Exception:  # noqa: BLE001
            continue


def _apartar_cargas_nuevas(app, estado: dict) -> list[str]:
    """Saca de la red del caso activo las variaciones de carga nueva (014:RF-6, RF-7).

    Las cargas nuevas de la 007 solo existen por su variación: desactivarla en el caso en
    que se mide las deja fuera del cuadre sin escribir nada en el escenario ni en una
    etapa, y ``_devolver_cargas_nuevas`` las vuelve a dejar como estaban (RF-8).
    """
    activas = [v for v in (app.GetActiveNetworkVariations() or []) if es_de_carga_nueva(v)]
    for v in activas:
        v.Deactivate()
    if activas:
        estado['apartadas'].append((app.GetActiveStudyCase(), activas))
    return sorted(v.loc_name for v in activas)


def _devolver_cargas_nuevas(app, estado: dict) -> None:
    """RF-8: también si el ajuste falla o se cancela."""
    if not estado['apartadas']:
        return
    previo = app.GetActiveStudyCase()
    for caso, variaciones in estado['apartadas']:
        if caso is not None and app.GetActiveStudyCase() is not caso:
            caso.Activate()
        for v in variaciones:
            v.Activate()
    if previo is not None and app.GetActiveStudyCase() is not previo:
        previo.Activate()


# =========================================================================== orquestación
def bancos_instalados(alims: Alimentadores, feeder: str) -> list[dict]:
    """Bancos de condensadores del alimentador en el proyecto, tal como están (015:RF-60).

    Los del propio proyecto y nada más: en CA101 el operador los instaló a mano en barras
    nuevas («Terminal», partiendo un tramo) y el usuario pidió, el 2026-10-15, no tomar nada
    de otro proyecto ni de otro alimentador. Se toman los del ``ElmFeeder``, los etiquetados
    con el alimentador y, si el proyecto solo tiene este alimentador, todos los del cálculo,
    porque en CA101 el ``ElmFeeder`` no alcanzaba las barras de los bancos.
    """
    filas = []
    for o in _objetos_banco(alims, feeder):
        try:
            barra = o.bus1.cterm
        except Exception:  # noqa: BLE001 - banco sin conectar
            barra = None
        escalon = _num(o, 'qcapn')
        pasos = _num(o, 'ncapa') or 1.0
        q_flujo = _num(o, 'm:Qsum:bus1')
        filas.append({
            'banco': o.loc_name,
            'barra': getattr(barra, 'loc_name', None),
            'kv': getattr(barra, 'uknom', None),
            'q_nominal_kvar': None if escalon is None else escalon * pasos * 1000.0,
            'q_flujo_kvar': None if q_flujo is None else -q_flujo * 1000.0,
            'u_pu': _num(barra, 'm:u') if barra is not None else None,
            'en_servicio': not int(getattr(o, 'outserv', 0) or 0),
            'escalones': f"{int(pasos)} de {int(_num(o, 'ncapx') or pasos)}",
        })
    return sorted(filas, key=lambda x: (str(x['barra']), x['banco']))


def bancos_a_su_maxima_capacidad(alims: Alimentadores, feeder: str) -> list[dict]:
    """Cada banco existente con todos sus escalones y en servicio (015:RF-66).

    El usuario, 2026-10-15: «los bancos existentes deben trabajar a su máxima capacidad».
    Se escribe con el escenario de «Sin proyecto» activo; devuelve lo que cambió.
    """
    cambios = []
    for o in _objetos_banco(alims, feeder):
        antes = {'escalones': _num(o, 'ncapa'), 'en_servicio': not int(getattr(o, 'outserv', 0) or 0)}
        maximo = _num(o, 'ncapx')
        if maximo and (antes['escalones'] or 0) < maximo:
            o.ncapa = int(maximo)
        if not antes['en_servicio']:
            o.outserv = 0
        despues = {'escalones': _num(o, 'ncapa'),
                   'en_servicio': not int(getattr(o, 'outserv', 0) or 0)}
        if despues != antes:
            cambios.append({'banco': o.loc_name, 'antes': antes, 'despues': despues})
    return cambios


def _objetos_banco(alims: Alimentadores, feeder: str) -> list:
    """Los ``ElmShnt`` del alimentador en el proyecto (los de :func:`bancos_instalados`)."""
    from igea_dgs.demanda_medida import clave_codigo

    clave = clave_codigo(feeder)
    candidatos = {_clave_objeto_nativo(o): o for o in alims.objetos(feeder, 'ElmShnt')}
    try:
        relevantes = list(alims.app.GetCalcRelevantObjects('*.ElmShnt') or [])
    except Exception:  # noqa: BLE001 - sin cálculo, los del ElmFeeder
        relevantes = []
    solo_este = set(alims.elm) <= {feeder}
    for o in relevantes:
        if solo_este or clave in {clave_codigo(x) for x in _alimentadores_nativos(o)}:
            candidatos.setdefault(_clave_objeto_nativo(o), o)
    return list(candidatos.values())


def fijas_sobre_su_transformador(fijas: dict, kva: dict) -> list[dict]:
    """Fijas cuya demanda supera la potencia instalada de su SED (015:RF-59).

    En CA101 (2026-10-15) un cliente pedía 248 kW en SE20859, de 50 kVA (496 %), y otro
    201 kW en SE21082, de 100 kVA: o el cruce los lleva a otra SED o el
    transformador está mal. No se puede saber cuál; se nombra y se sigue calibrando.
    """
    out = []
    for sed, f in sorted(fijas.items()):
        k = kva.get(sed)
        s = math.hypot(f.kw, f.kvar)
        if k and s > k:
            out.append({'sed': sed, 'clientes': list(f.clientes), 'p_kw': f.kw,
                        'kva_carga': s, 'kva': k, 'carga_pct': 100.0 * s / k})
    return sorted(out, key=lambda x: -x['carga_pct'])


def transformadores_de(carga) -> list[dict]:
    """Los ElmTr2 de la barra de la carga, con lo que hace falta para proponer otro (020:RF-9).

    Los mismos que suma :func:`kva_en_pf`: la carga de la SED cuelga de su barra de baja.
    """
    try:
        conectados = list(carga.bus1.cterm.GetConnectedElements())
    except Exception:  # noqa: BLE001 - carga sin conectar
        return []
    out = []
    for e in conectados:
        if e.GetClassName() != 'ElmTr2':
            continue
        tipo = getattr(e, 'typ_id', None)
        at, bt = _num(tipo, 'utrn_h'), _num(tipo, 'utrn_l')
        out.append({
            'transformador': e.loc_name, 'tipo': getattr(tipo, 'loc_name', None),
            'kva': (_num(tipo, 'strn') or 0.0) * 1000.0,
            'unidades': max(1, int(_num(e, 'ntnum') or 1)),
            'kv_at': at, 'v_bt': None if bt is None else bt * 1000.0,
            'grupo': (f"{getattr(tipo, 'tr2cn_h', '') or ''}{getattr(tipo, 'tr2cn_l', '') or ''}"
                      f"{_num(tipo, 'nt2ag') or 0:g}") if tipo is not None else None,
        })
    return sorted(out, key=lambda t: t['transformador'])


def proponer_transformadores(sobre: list[dict], cargas: dict, fichas: dict | None,
                             motivo_sin_fichas: str | None = None) -> None:
    """Pone en cada SED sobrecargada sus transformadores y la propuesta (020:RF-6 a RF-12)."""
    from igea_dgs.trafos_sed import nombre_tipo, proponer

    for x in sobre:
        trs = transformadores_de(cargas[x['sed']]) if x['sed'] in cargas else []
        x['transformadores'] = trs
        if fichas is None:
            x['propuesta'] = {'kva': None, 'motivo': motivo_sin_fichas or
                              'el perfil de empresa no trae tablas de fichas de '
                              'transformadores (calibracion.transformadores_sed)'}
        elif len(trs) != 1:
            x['propuesta'] = {'kva': None, 'motivo': (
                f'la SED tiene {len(trs)} transformadores: no se sabe cuál cambiar'
                if trs else 'la SED no tiene transformador en DIgSILENT')}
        else:
            p = proponer(x['kva_carga'], trs[0]['kv_at'], fichas['tablas'],
                         fichas['umbral_carga_pct'])
            if p['kva'] is not None:
                p['tipo_nuevo'] = nombre_tipo(p['kva'], p['codigo'], trs[0]['kv_at'],
                                              trs[0]['v_bt'], trs[0]['grupo'])
            x['propuesta'] = p


#: Datos de la ficha en el tipo de DIgSILENT: atributo → (clave de la propuesta, factor).
FICHA_EN_TIPO = {'strn': ('kva', 1e-3), 'pfe': ('po_w', 1e-3), 'pcutr': ('pc_w', 1e-3),
                 'curmg': ('io_pct', 1.0), 'uktr': ('uk_pct', 1.0), 'uk0tr': ('uk_pct', 1.0)}


def _elm_tr2(carga) -> list:
    try:
        return sorted((e for e in carga.bus1.cterm.GetConnectedElements()
                       if e.GetClassName() == 'ElmTr2'), key=lambda e: e.loc_name)
    except Exception:  # noqa: BLE001 - carga sin conectar
        return []


def implementar_transformadores(app, cargas: dict, cambios: list[dict]) -> dict:
    """Los transformadores nuevos de las SED marcadas, en la red de «Sin proyecto» (020:RF-16 a RF-24).

    Se llama con «Sin proyecto» activo y antes de leer los kVA de la calibración, que así
    ya ve los nuevos. En PA217 (2026-10-16) se hizo a mano (015, T26): tipo propio copiado
    del actual (tensiones, grupo, secuencia cero) con la ficha de la NTP, y ``ntnum``
    unidades en paralelo; ningún tipo existente se toca, porque lo comparten otras SED.
    """
    from igea_dgs.demanda_medida import clave_codigo
    from igea_dgs.trafos_sed import nombre_tipo

    variaciones = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
    etapa = app.GetRecordingStage()
    if variaciones or etapa is not None:
        # 020:RF-17: lo escrito iría a esa variación y no a la red que se calibra.
        que = (f"las variaciones activas {', '.join(variaciones)}" if variaciones
               else f"la etapa {etapa.loc_name} grabando")
        return {'error': f"«{NOMBRES['sin']}» tiene {que}: los transformadores se escriben en "
                         'la red, sin variación; desactívelas y vuelva a implementar '
                         '(020:RF-17).', 'cambios': [], 'omitidas': []}
    equip = app.GetProjectFolder('equip')
    tipos = {t.loc_name: t for t in (equip.GetContents('*.TypTr2', 1) if equip else [])}
    por_clave = {clave_codigo(s): o for s, o in cargas.items()}
    hechos, omitidas = [], []
    for c in cambios:
        sed, p = c['sed'], c.get('propuesta') or {}
        carga = cargas.get(sed) or por_clave.get(clave_codigo(sed))
        trs = _elm_tr2(carga) if carga is not None else []
        if carga is None or len(trs) != 1 or trs[0].loc_name != c.get('transformador'):
            omitidas.append({'sed': sed, 'motivo': (
                'la SED no está en el alimentador' if carga is None else
                f'la SED tiene {len(trs)} transformadores (020:RF-12)' if len(trs) != 1 else
                f"su transformador es {trs[0].loc_name}, no {c.get('transformador')}: la red "
                'cambió desde la propuesta; vuelva a simular')})
            continue
        tr = trs[0]
        actual = tr.typ_id
        info = transformadores_de(carga)[0]
        nombre = nombre_tipo(p['kva'], p.get('codigo') or '', info['kv_at'], info['v_bt'],
                             info['grupo'])
        nuevo = tipos.get(nombre)
        if nuevo is not None:
            # 020:RF-21, RF-22: el tipo propio de un cambio anterior vale si tiene la ficha.
            distinto = next(((a, _num(nuevo, a), p[k] * f) for a, (k, f) in FICHA_EN_TIPO.items()
                             if not math.isclose(_num(nuevo, a) or 0.0, p[k] * f,
                                                 rel_tol=1e-4, abs_tol=1e-6)), None)
            if distinto is not None:
                a, tiene, pide = distinto
                tiene = 'nada' if tiene is None else f'{tiene:g}'
                omitidas.append({'sed': sed, 'motivo': (
                    f'ya existe el tipo {nombre} con {a}={tiene} y la ficha pide {pide:g}: '
                    'no se toca un tipo existente (020:RF-20, 020:RF-22)')})
                continue
        else:
            nuevo = actual.GetParent().AddCopy(actual, nombre)
            for a, (k, f) in FICHA_EN_TIPO.items():
                setattr(nuevo, a, p[k] * f)
            tipos[nombre] = nuevo
        antes = {'tipo': getattr(actual, 'loc_name', None), 'kva': info['kva'],
                 'unidades': info['unidades']}
        tr.typ_id = nuevo
        tr.ntnum = int(p['unidades'])
        hechos.append({'sed': sed, 'transformador': tr.loc_name, 'antes': antes,
                       'despues': {'tipo': nombre, 'kva': p['kva'], 'unidades': int(p['unidades']),
                                   'norma': p.get('norma')}})
    return {'cambios': hechos, 'omitidas': omitidas}


def resultado_transformadores(cambiados: list[dict], sobre: list[dict], fijas: dict,
                              cargas: dict, fichas: dict, *, calibracion_valida: bool,
                              validacion: dict | None, remedios, motivo) -> dict:
    """Lo que dejan los transformadores nuevos en la recalibración (020:RF-26, RF-32).

    La sobrecarga era lo que no dejaba converger ni validar (PA217, 2026-10-16: válida a
    −0,34 % tras el cambio). Si aun así la calibración no sale, ya no es la causa, y se dice
    qué sigue fallando en vez de repetir el aviso de la sobrecarga.
    """
    umbral = fichas.get('umbral_carga_pct')
    sobre_umbral = []
    for h in cambiados:
        f = fijas.get(h['sed'])
        kva = kva_en_pf(cargas[h['sed']]) if h['sed'] in cargas else None
        if f is None or not kva or umbral is None:
            continue
        pct = 100.0 * math.hypot(f.kw, f.kvar) / kva
        if pct > umbral + 1e-6:
            sobre_umbral.append({'sed': h['sed'], 'carga_pct': pct, 'kva': kva})
    motivos = []
    if not calibracion_valida:
        fallo = next((f for f in (validacion or {}).get('fallos') or []
                      if f.get('tipo') == 'CONSUMO_DISTINTO_DE_LO_ESCRITO'), None)
        if fallo:
            motivos.append(f"{fallo['cantidad']} cargas no consumen en el flujo lo que tienen "
                           'escrito')
        usados = [r['remedio'] for r in remedios or [] if r.get('cambios')]
        if usados:
            motivos.append('el flujo necesitó ' + ', '.join(usados))
        if motivo:
            motivos.append(str(motivo))
        if not motivos:
            motivos.append('la calibración no cuadra con la máxima de cabecera')
    if sobre:
        motivos.append(f'{len(sobre)} SED fija(s) siguen por encima de su potencia instalada: '
                       + ', '.join(f"{x['sed']} ({x['carga_pct']:,.0f} %)" for x in sobre[:10]))
    if sobre_umbral:
        motivos.append(f'{len(sobre_umbral)} SED cambiada(s) por encima del umbral del '
                       f'{umbral:g} %: ' + ', '.join(f"{x['sed']} ({x['carga_pct']:,.0f} %)"
                                                    for x in sobre_umbral))
    status = 'VALIDO' if not motivos else 'FALLO'
    aviso = None
    if status == 'FALLO':
        aviso = (f"TRANSFORMADORES: {len(cambiados)} cambiado(s) en «{NOMBRES['sin']}», que se "
                 'quedan, pero ' + ('la calibración no es válida' if not calibracion_valida
                                    else 'la comprobación no pasa')
                 + '; la sobrecarga ya no es la causa. Sigue fallando: ' + '; '.join(motivos)
                 + ' (020:RF-26, RF-32).')
    return {'status': status, 'calibracion_valida': calibracion_valida,
            'sobrecargadas': [x['sed'] for x in sobre], 'sobre_umbral': sobre_umbral,
            'motivos': motivos, 'aviso': aviso}


def aviso_sobrecarga(sobre: list[dict]) -> str:
    """020:RF-4: la sobrecarga como causa probable de que la calibración no salga."""
    con = sum(1 for x in sobre if (x.get('propuesta') or {}).get('kva'))
    return (f'SOBRECARGA: {len(sobre)} SED fija(s) piden más que su potencia instalada y son '
            'la causa probable de que la calibración no converja o no sea válida: '
            + ', '.join(f"{x['sed']} ({x['carga_pct']:,.0f} %)" for x in sobre[:10])
            + (f'. Hay propuesta de transformadores nuevos para {con}: márquelas e '
               'implemente los transformadores (020:RF-6).' if con else
               '. Sin propuesta de transformadores nuevos: corrija el transformador o el '
               'cruce del cliente en DIgSILENT.'))


def _por_sed(reparto, cargas, kva_origen, antes, fijas):
    filas = []
    for sed, d in reparto.demandas.items():
        apparent = math.hypot(d.kw, d.kvar)
        fija = fijas.get(sed)
        filas.append({
            'sed': sed, 'origen': d.origen, 'kva': d.kva, 'kva_de': kva_origen.get(sed) or None,
            'clientes': fija.clientes if fija else [],
            'antes': {'kw': antes[sed][0], 'kvar': antes[sed][1]},
            'despues': {
                'kw': d.kw, 'kvar': d.kvar,
                'fp': abs(d.kw) / apparent if apparent else 1.0,
            },
            'derivaciones': list(fija.derivaciones) if fija else [],
            'avisos': list(fija.avisos) if fija else [],
        })
    return filas


def factor_de_escala(obj) -> float:
    """``scale0`` de la carga: el factor de escala de DIgSILENT, normalmente 1."""
    try:
        valor = float(getattr(obj, 'scale0', 1.0))
    except (TypeError, ValueError):
        return 1.0
    return valor if math.isfinite(valor) else 1.0


def potencia_efectiva(obj) -> tuple[float, float]:
    """kW y kVAR que consume la carga: los escritos por su factor de escala (015:RF-44)."""
    p_kw, q_kvar = potencia(obj)
    k = factor_de_escala(obj)
    return p_kw * k, q_kvar * k


def escribir_reparto(cargas: dict, rep, omitir=frozenset()) -> list[dict]:
    """Escribe un reparto como DIgSILENT lo escala (015:RF-43, RF-44).

    Las fijas reciben su P y Q y factor 1; las escaladas conservan la P y la Q de su base
    (las del archivo original) y llevan todas el mismo factor de escala. ``omitir``: las
    que no se escriben (cambio manual de demanda, 014:RF-11). Devuelve los fallos.
    """
    fallos = []
    for sed, d in rep.demandas.items():
        if sed in omitir:
            continue
        obj = cargas[sed]
        try:
            if sed in rep.base:
                bp, bq = rep.base[sed]
                if not all(_cerca(a, b) for a, b in zip(potencia(obj), (bp, bq))):
                    escribir_carga(obj, bp / 1000.0, bq / 1000.0)
                obj.scale0 = rep.a
                # 014:RF-4: la base también en el escenario de este caso (CA101: «Con
                # proyecto» se quedaba con la del archivo, ver ``potencia``).
                escrita = potencia(obj)
                error = (f'scale0={factor_de_escala(obj)}, esperado {rep.a}'
                         if not math.isclose(factor_de_escala(obj), rep.a, rel_tol=1e-6)
                         else f'base {escrita[0]:.3f}/{escrita[1]:.3f} kW/kvar en el escenario, '
                              f'esperada {bp:.3f}/{bq:.3f}'
                         if not all(_cerca(a, b) for a, b in zip(escrita, (bp, bq))) else None)
            else:
                escribir_carga(obj, d.kw / 1000.0, d.kvar / 1000.0)
                obj.scale0 = 1.0
                error = error_relectura(obj, d.kw / 1000.0, d.kvar / 1000.0)
        except Exception as exc:  # noqa: BLE001 - una SED no tumba el ajuste
            error = f'{type(exc).__name__}: {exc}'
        if error:
            fallos.append({'sed': sed, 'error': error})
    return fallos


def _foto_cargas_nativas(cargas: dict) -> list[dict]:
    """Relectura efectiva P/Q/FP, estado y bandera de escala de cada carga SED."""
    fotos = []
    for sed, obj in sorted(cargas.items()):
        p_kw, q_kvar = potencia_efectiva(obj)
        apparent = math.hypot(p_kw, q_kvar)
        try:
            full_name = str(obj.GetFullName())
        except Exception:  # noqa: BLE001 - dobles y versiones antiguas
            full_name = str(getattr(obj, 'loc_name', sed))
        fotos.append({
            'sed': sed, 'full_name': full_name, 'p_kw': p_kw, 'q_kvar': q_kvar,
            'fp': abs(p_kw) / apparent if apparent else 1.0,
            'outserv': int(getattr(obj, 'outserv', 0) or 0),
            'i_scale': int(getattr(obj, 'i_scale', 0) or 0),
            'mode_inp': str(getattr(obj, 'mode_inp', '') or ''),
            'escrita': dict(zip(('p_kw', 'q_kvar'), potencia(obj))),
            'scale0': factor_de_escala(obj),
        })
    return fotos


def consumo_nativo(cargas: dict) -> tuple[float | None, float | None]:
    """Suma P/Q efectiva de todas las cargas; incompleta significa no verificable."""
    resultados = []
    for obj in cargas.values():
        p = _num(obj, 'm:Psum:bus1')
        q = _num(obj, 'm:Qsum:bus1')
        if p is None or q is None:
            return None, None
        resultados.append((p * 1000.0, q * 1000.0))
    return sum(p for p, _ in resultados), sum(q for _, q in resultados)


def ajustes_del_flujo(app) -> dict:
    """Ajustes del ``ComLdf`` activo que cambian el consumo de las cargas (015:RF-51)."""
    out = {}
    try:
        ldf = app.GetFromStudyCase('ComLdf')
    except Exception:  # noqa: BLE001 - sin caso activo no hay ajuste que nombrar
        return out
    for attr in AJUSTES_QUE_CAMBIAN_EL_CONSUMO:
        try:
            out[attr] = int(ldf.GetAttribute(attr) or 0)
        except Exception:  # noqa: BLE001 - versiones y dobles sin el atributo
            pass
    return out


def _tension_de_la_barra(obj) -> float | None:
    try:
        return _num(obj.bus1.cterm, 'm:u')
    except Exception:  # noqa: BLE001 - dobles o carga sin conectar
        return None


def _consume_lo_escrito(consumido: float, escrito: float) -> bool:
    return math.isclose(consumido, escrito, rel_tol=CONSUMO_REL, abs_tol=CONSUMO_ABS)


def _cerca(actual: float, esperado: float, *, rel: float = 1e-4,
           abs_: float = 1e-3) -> bool:
    """Comparación de relectura en kW/kVAR, más estricta que el cuadre de cabecera."""
    return math.isclose(actual, esperado, rel_tol=rel, abs_tol=abs_)


def validar_cargas_nativas(cargas: dict, reparto, medida, objetivo, tolerancia: float,
                           *, ambiguas=(), apagar=None,
                           ajustes_flujo: dict | None = None,
                           fp_escaladas: float | None = None) -> tuple[dict, object | None]:
    """Demuestra si el reparto ya existe en la red efectiva sin escribirla.

    Las fijas deben coincidir con su P/Q calculada. Las escalables no se comparan contra
    el reparto *inicial* —el cuadre cambia su factor para cubrir pérdidas—, sino que deben
    compartir un mismo factor P/base y Q/base. Finalmente el flujo nativo debe converger y
    la cabecera debe cumplir el objetivo. Devuelve también el reparto reconstruido desde
    la relectura, para informar exactamente lo que ya existe.

    015:RF-47 a RF-52: lo escrito no basta. Tras un flujo convergente cada fija tiene que
    consumir su P y su Q, y cada escalada su P por el factor de escala; si no, no es
    válida. En CA101 (2026-10-15) la relectura de lo escrito daba «válido» mientras las
    fijas consumían el 73 % por la adaptación automática del modelo del ``ComLdf``.
    """
    apagar = apagar or {}
    fallos: list[dict] = []
    if ambiguas:
        fallos.append({'tipo': 'CARGAS_AMBIGUAS', 'cantidad': len(ambiguas)})
    if not medida.converge or medida.kw is None:
        fallos.append({'tipo': 'FLUJO_NO_CONVERGE', 'detalle': medida.motivo})
    elif abs(medida.kw - objetivo.kw) > tolerancia * max(abs(objetivo.kw), 1e-9):
        fallos.append({
            'tipo': 'CABECERA_FUERA_TOLERANCIA', 'actual_kw': medida.kw,
            'objetivo_kw': objetivo.kw, 'tolerancia': tolerancia,
        })

    factores_p: list[tuple[str, float]] = []
    factores_q: list[tuple[str, float]] = []
    detalles = []
    fisicas: list[dict] = []
    sin_resultado: list[str] = []
    fp_distinto: list[dict] = []
    for sed, demanda in reparto.demandas.items():
        obj = cargas.get(sed)
        if obj is None:
            fallos.append({'tipo': 'SED_FALTANTE', 'sed': sed})
            continue
        p_kw, q_kvar = potencia_efectiva(obj)
        escalable = sed in reparto.base
        esperado_i_scale = 1 if escalable else 0
        actual_i_scale = int(getattr(obj, 'i_scale', 0) or 0)
        errores = []
        if int(getattr(obj, 'outserv', 0) or 0) != 0:
            errores.append('fuera de servicio')
        if actual_i_scale != esperado_i_scale:
            errores.append(f'i_scale={actual_i_scale}, esperado {esperado_i_scale}')
        if escalable:
            base_p, base_q = reparto.base[sed]
            if abs(base_p) <= 1e-12:
                if not _cerca(p_kw, 0.0):
                    errores.append(f'P={p_kw:.6f} kW con base P nula')
            else:
                factores_p.append((sed, p_kw / base_p))
            if abs(base_q) <= 1e-12:
                if not _cerca(q_kvar, 0.0):
                    errores.append(f'Q={q_kvar:.6f} kVAR con base Q nula')
            else:
                factores_q.append((sed, q_kvar / base_q))
        else:
            if not _cerca(p_kw, demanda.kw):
                errores.append(f'P={p_kw:.6f} kW, esperada {demanda.kw:.6f}')
            if not _cerca(q_kvar, demanda.kvar):
                errores.append(f'Q={q_kvar:.6f} kVAR, esperada {demanda.kvar:.6f}')
        # 015:RF-67: cada escalada con demanda, con el FP de las escaladas.
        if escalable and fp_escaladas is not None and p_kw > CONSUMO_ABS:
            fp_escrito = abs(p_kw) / math.hypot(p_kw, q_kvar)
            if abs(fp_escrito - fp_escaladas) > FP_MARGEN:
                errores.append(f'FP escrito {fp_escrito:.4f}, esperado {fp_escaladas:.4f}')
                fp_distinto.append({'sed': sed, 'fp': fp_escrito, 'donde': 'escrito'})
        # 015:RF-47, RF-48, RF-52: lo que consume en el flujo, frente a lo escrito.
        consumo_p = consumo_q = tension = None
        errores_fisicos = []
        if medida.converge:
            consumo_p = _num(obj, 'm:Psum:bus1')
            consumo_q = _num(obj, 'm:Qsum:bus1')
            consumo_p = None if consumo_p is None else consumo_p * 1000.0
            consumo_q = None if consumo_q is None else consumo_q * 1000.0
            tension = _tension_de_la_barra(obj)
            if consumo_p is None:
                sin_resultado.append(sed)
                errores_fisicos.append('el flujo no publica su P consumida: no verificada')
            elif not _consume_lo_escrito(consumo_p, p_kw):
                errores_fisicos.append(f'consume P={consumo_p:.3f} kW, escrita {p_kw:.3f} kW')
            if (not escalable and consumo_q is not None
                    and not _consume_lo_escrito(consumo_q, q_kvar)):
                errores_fisicos.append(
                    f'consume Q={consumo_q:.3f} kVAR, escrita {q_kvar:.3f} kVAR')
            if (escalable and fp_escaladas is not None and consumo_p is not None
                    and consumo_q is not None and consumo_p > CONSUMO_ABS):
                fp_flujo = abs(consumo_p) / math.hypot(consumo_p, consumo_q)
                if abs(fp_flujo - fp_escaladas) > FP_MARGEN:
                    errores_fisicos.append(f'FP en el flujo {fp_flujo:.4f}, esperado '
                                           f'{fp_escaladas:.4f}')
                    fp_distinto.append({'sed': sed, 'fp': fp_flujo, 'donde': 'flujo'})
            if errores_fisicos and consumo_p is not None:
                fisicas.append({
                    'sed': sed, 'clase': 'ESCALABLE' if escalable else 'FIJA',
                    'p_escrita_kw': p_kw, 'p_consumida_kw': consumo_p,
                    'q_escrita_kvar': q_kvar, 'q_consumida_kvar': consumo_q,
                    'u_pu': tension,
                })
        detalles.append({
            'sed': sed, 'clase': 'ESCALABLE' if escalable else 'FIJA',
            'p_kw': p_kw, 'q_kvar': q_kvar, 'i_scale': actual_i_scale,
            'p_consumida_kw': consumo_p, 'q_consumida_kvar': consumo_q, 'u_pu': tension,
            'correcta': not errores and not errores_fisicos,
            'errores': errores + errores_fisicos,
        })
        if errores:
            fallos.append({'tipo': 'CARGA_INCORRECTA', 'sed': sed, 'errores': errores})

    for sed, obj in apagar.items():
        if int(getattr(obj, 'outserv', 0) or 0) != 1:
            fallos.append({'tipo': 'SED_DESCONECTADA_ACTIVA', 'sed': sed})
    if fp_distinto:
        fallos.append({'tipo': 'FP_ESCALADAS_DISTINTO', 'esperado': fp_escaladas,
                       'cantidad': len(fp_distinto), 'sed': fp_distinto})
    if sin_resultado:
        fallos.append({'tipo': 'CARGAS_SIN_RESULTADO_DEL_FLUJO',
                       'cantidad': len(sin_resultado), 'sed': sin_resultado})
    causa = None
    if fisicas:
        # 015:RF-51: el ajuste del flujo que vuelve las cargas dependientes de la tensión.
        activos = [f'{AJUSTES_QUE_CAMBIAN_EL_CONSUMO[k]} ({k}={v})'
                   for k, v in (ajustes_flujo or {}).items() if v]
        causa = ('el flujo de carga tiene activa la ' + ' y la '.join(activos)
                 if activos else None)
        fallos.append({
            'tipo': 'CONSUMO_DISTINTO_DE_LO_ESCRITO', 'cantidad': len(fisicas),
            'fijas': sum(1 for f in fisicas if f['clase'] == 'FIJA'),
            'causa_probable': causa,
            'cargas': sorted(fisicas,
                             key=lambda f: -abs(f['p_escrita_kw'] - f['p_consumida_kw'])),
        })

    def factor_comun(factores, magnitud):
        if not factores:
            return None
        referencia = factores[0][1]
        distintos = [{'sed': sed, 'factor': factor} for sed, factor in factores
                     if not math.isclose(factor, referencia, rel_tol=1e-4, abs_tol=1e-6)]
        if distintos:
            fallos.append({'tipo': f'REPARTO_{magnitud}_NO_PROPORCIONAL',
                           'referencia': referencia, 'distintos': distintos})
        return referencia

    factor_p = factor_comun(factores_p, 'P')
    factor_q = factor_comun(factores_q, 'Q')
    if factor_q is not None:
        esperado_q = factor_p if reparto.solo_kw and factor_p is not None else reparto.b
        if not math.isclose(factor_q, esperado_q, rel_tol=1e-4, abs_tol=1e-6):
            fallos.append({
                'tipo': 'FACTOR_Q_INCORRECTO', 'factor_q': factor_q,
                'esperado': esperado_q, 'solo_kw': reparto.solo_kw,
            })
    # Las perdidas se demuestran con el consumo efectivo del ultimo flujo, no con
    # ``plini``. En PowerFactory una carga dependiente de tension puede consumir en
    # terminal menos que su potencia escrita; comparar cabecera contra ``plini`` daba
    # perdidas negativas falsas aun cuando todas las cargas se habian releido bien.
    total_p, total_q = consumo_nativo(cargas)
    consumo_origen = 'RESULTADOS_CARGAS_NATIVAS'
    if total_p is None:
        # Algunos modelos/dobles no publican resultados por ElmLod aunque el ComLdf si
        # publique la cabecera. En ese caso se conserva la comprobacion historica sobre
        # las entradas; cuando los resultados existen, como en CA101, siempre prevalecen.
        total_p = sum(potencia_efectiva(obj)[0] for obj in cargas.values())
        total_q = sum(potencia_efectiva(obj)[1] for obj in cargas.values())
        consumo_origen = 'ENTRADAS_CARGAS_NATIVAS'
    if medida.converge and medida.kw is not None:
        ruido = max(0.1, abs(objetivo.kw) * 1e-4)
        if medida.kw - total_p < -ruido:
            fallos.append({'tipo': 'PERDIDAS_ACTIVAS_NEGATIVAS',
                           'cabecera_kw': medida.kw, 'cargas_kw': total_p})

    # 015:RF-50: el balance físico de la cabecera, con lo que consumen las cargas.
    balance = None
    if medida.converge and medida.kw is not None:
        def suma(clase, campo):
            valores = [d[campo] for d in detalles if d['clase'] == clase]
            return None if any(v is None for v in valores) else sum(valores)

        fijas_kw = suma('FIJA', 'p_consumida_kw')
        escaladas_kw = suma('ESCALABLE', 'p_consumida_kw')
        consumido = (None if fijas_kw is None or escaladas_kw is None
                     else fijas_kw + escaladas_kw)
        balance = {
            'cabecera_kw': medida.kw,
            'fijas_consumida_kw': fijas_kw, 'fijas_escrita_kw': suma('FIJA', 'p_kw'),
            'escaladas_consumida_kw': escaladas_kw,
            'escaladas_escrita_kw': suma('ESCALABLE', 'p_kw'),
            'escrita_kw': sum(d['p_kw'] for d in detalles),
            'perdidas_kw': None if consumido is None else medida.kw - consumido,
            'ajustes_del_flujo': dict(ajustes_flujo or {}),
            'causa_probable': causa,
        }

    reconstruido = None
    if not fallos:
        a = reparto.a if factor_p is None else factor_p
        b = reparto.b if factor_q is None else factor_q
        reconstruido = reparto.con_factores(a, b)
    return {
        'status': 'VALIDO' if not fallos else 'REQUIERE_DISTRIBUCION',
        'correcta': not fallos,
        'fallos': fallos,
        'cargas': detalles,
        'factor_p': factor_p,
        'factor_q': factor_q,
        'consumo_cargas_efectivo': {'kw': total_p, 'kvar': total_q,
                                    'origen': consumo_origen},
        'balance': balance,
        'fp_escaladas': {'esperado': fp_escaladas, 'distintas': len(fp_distinto)},
        'cabecera': ({'kw': medida.kw, 'kvar': medida.kvar}
                     if medida.converge else None),
    }, reconstruido


def sincronizar_con_proyecto(app, con, sin, cargas: dict, reparto, omitir, apagar) -> dict:
    """Deja en el escenario de «Con proyecto» la demanda calibrada de «Sin proyecto» (014:RF-4).

    Solo escribe las cargas que difieren; las cambiadas a mano (``omitir``) no se tocan.
    """
    con.Activate()
    escenario = app.GetActiveScenario()
    distintas = []
    for sed, d in reparto.demandas.items():
        if sed in omitir:
            continue
        p, q = potencia_efectiva(cargas[sed])
        if not (_cerca(p, d.kw) and _cerca(q, d.kvar)):
            distintas.append(sed)
    fallos = []
    if distintas and escenario is not None:
        iguales = set(reparto.demandas) - set(distintas)
        fallos = escribir_reparto(cargas, reparto, set(omitir) | iguales)
        for obj in apagar.values():
            obj.outserv = 1
        escenario.Save()
    resultado = {'escenario': getattr(escenario, 'loc_name', None),
                 'corregidas': len(distintas), 'fallos': fallos}
    sin.Activate()
    return resultado


def _factor_minimo_sin_converger(historial) -> float | None:
    """El menor factor de las escaladas con el que el flujo no convergió antes del primero
    que sí, o ``None`` si convergió sin remedios."""
    menor = None
    for paso in historial or []:
        if paso.get('converge'):
            return menor
        a = paso.get('a')
        if a is not None and (menor is None or a < menor):
            menor = a
    return menor


def aviso_consumo_fisico(validacion: dict, historial=None, sobre=None) -> str | None:
    """El aviso de 015:RF-49 a RF-51 para el operador, o ``None`` si todas consumen bien.

    Con el ``historial`` del cuadre y las fijas ``sobre`` su transformador (RF-59) dice
    además por qué hizo falta el ajuste del flujo. En PA217 (2026-10-16) el aviso culpaba a
    ``iopt_lev`` y no al modelo: sin él no convergía ni con las escaladas al 0,5 % de su
    kVA, porque SE30940 recibía los 3800 kW de su cliente sobre un transformador de
    400 kVA (955 %); lo que hay que corregir en DIgSILENT es ese transformador o el cruce.
    """
    fallo = next((f for f in validacion.get('fallos') or []
                  if f.get('tipo') == 'CONSUMO_DISTINTO_DE_LO_ESCRITO'), None)
    if fallo is None:
        return None
    fijas = [c for c in fallo['cargas'] if c['clase'] == 'FIJA']
    partes = [f"{fallo['cantidad']} cargas no consumen en el flujo lo que tienen escrito"]
    if fijas:
        escrita = sum(c['p_escrita_kw'] for c in fijas)
        consumida = sum(c['p_consumida_kw'] for c in fijas)
        peor = fijas[0]
        tension = '' if peor['u_pu'] is None else f" a {peor['u_pu']:.3f} pu"
        partes.append(f'{len(fijas)} fijas: {escrita:,.1f} kW escritos, {consumida:,.1f} kW '
                      f"consumidos (la que más, {peor['sed']}: {peor['p_escrita_kw']:,.1f} → "
                      f"{peor['p_consumida_kw']:,.1f} kW{tension})")
    if fallo.get('causa_probable'):
        partes.append('causa probable: ' + fallo['causa_probable'])
    minimo = _factor_minimo_sin_converger(historial)
    if fallo.get('causa_probable') and minimo is not None:
        partes.append(f'sin ese ajuste el flujo no converge ni con las escaladas al '
                      f'{minimo:.1%} de su kVA, así que lo impiden las fijas')
    if sobre:
        lista = ', '.join(f"{s['sed']} {s['kva_carga']:,.0f} kVA en {s['kva']:,.0f} kVA "
                          f"({s['carga_pct']:.0f} %)" for s in sobre[:5])
        partes.append(f'{len(sobre)} SED fija(s) piden más que su transformador ({lista}): '
                      'corrija en «Sin proyecto» su transformador o el cruce del cliente '
                      'con su SED y vuelva a calibrar (015:RF-59)')
    return ('VALIDACION_FISICA: ' + '; '.join(partes)
            + '. La calibración no es válida y las cargas vuelven a como estaban (015:RF-49).')


def ejecutar(app, plan: dict, *, simular: bool = False, cancelado=lambda: False) -> tuple[dict, int]:
    """Simula o aplica el ajuste. Devuelve (informe, código de salida)."""
    estado = {'apartadas': []}
    try:
        return _ejecutar(app, plan, simular=simular, cancelado=cancelado, estado=estado)
    finally:
        _devolver_cargas_nuevas(app, estado)


def _ejecutar(app, plan: dict, *, simular: bool, cancelado, estado: dict) -> tuple[dict, int]:
    from igea_dgs.ajuste_cabecera import (
        MAX_FLUJOS,
        AjusteError,
        Fija,
        Objetivo,
        cuadrar,
        fijas_de,
        kvar_difference,
        reparto_inicial,
        sed_desconectadas,
    )
    from igea_dgs.demanda_medida import clave_codigo

    feeder = plan['feeder']
    informe = {'project': plan['project'], 'feeder': feeder,
               'modo': 'simular' if simular else 'aplicar', 'avisos': [], 'cancelado': False}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en la carpeta "
                                    f"{plan.get('folder')!r} de DIgSILENT"}, 2
    alims = Alimentadores(app, proyecto, [feeder])
    elm = alims.elm.get(feeder)
    if elm is None or getattr(elm, 'obj_id', None) is None:
        return {**informe, 'error': f'{feeder} no tiene ElmFeeder con cabecera en el proyecto: '
                                    'no se puede medir lo que entra por ella.'}, 2
    # 015:RF-16, RF-17: se calibra en «Sin proyecto», la copia del «Caso base»
    # verificado; si aún no existe se crea, y sin «Caso base» verificado no se calibra.
    # Al simular no se crea nada: se lee en el caso activo.
    inicial = app.GetActiveStudyCase()
    sin = caso_del_sistema(app, 'sin')
    if sin is None and not simular:
        pedido = {'project': plan['project'], 'folder': plan.get('folder'), 'feeders': [feeder]}
        if 'caso_base_sin_verificar' in plan:
            pedido['caso_base_sin_verificar'] = plan['caso_base_sin_verificar']
        preparado, rc = preparar_sin(app, pedido)
        if rc:
            return {**informe, 'error': preparado.get('error')}, 2
        informe['casos_preparados'] = preparado.get('casos')
        sin = caso_del_sistema(app, 'sin')
        inicial = app.GetActiveStudyCase()
    if sin is not None:
        sin.Activate()
        informe['caso'] = NOMBRES['sin']
    con = caso_del_sistema(app, 'con')
    escenario = app.GetActiveScenario()
    if escenario is None and not simular:
        # Sin escenario, lo escrito iría a la red que comparten los casos y cambiaría el
        # «Caso base» (015:RF-19).
        return {**informe, 'error': f"«{NOMBRES['sin']}» no tiene escenario de operación: "
                                    'la calibración se graba en él (015:RF-26).'}, 2
    apartadas = _apartar_cargas_nuevas(app, estado)
    if apartadas:
        informe['cargas_nuevas_apartadas'] = apartadas
        informe['avisos'].append('Cargas nuevas fuera del ajuste mientras se mide (vuelven al '
                                 'terminar): ' + ', '.join(apartadas))
    cargas, ambiguas = cargas_sed(alims, feeder)
    poblacion_nativa = dict(getattr(cargas_sed, 'last_audit', {}) or {
        'algoritmo': 'SELECCION_NATIVA_DEL_ALIMENTADOR',
        'cargas_activas_unicas': len(cargas), 'nombres_ambiguos': len(ambiguas),
    })
    # 020:RF-16 a RF-24: los transformadores nuevos que marcó el operador, antes de leer
    # los kVA, para que la calibración ya cuente con ellos (RF-25).
    if plan.get('transformadores') and not simular:
        hecho = implementar_transformadores(app, cargas, plan['transformadores'])
        informe['transformadores_implementados'] = hecho
        if hecho.get('error'):
            return {**informe, 'error': hecho['error']}, 2
        for o in hecho['omitidas']:
            informe['avisos'].append(f"{o['sed']}: transformador no cambiado: {o['motivo']}.")
        if hecho['cambios']:
            informe['avisos'].append(
                f"{len(hecho['cambios'])} transformador(es) nuevo(s) en «{NOMBRES['sin']}», en la "
                'red: ' + '; '.join(
                    f"{h['sed']} {h['antes']['unidades']} × {h['antes']['kva']:,.0f} kVA → "
                    f"{h['despues']['unidades']} × {h['despues']['kva']:g} kVA "
                    f"({h['despues']['tipo']})" for h in hecho['cambios']) + ' (020:RF-24).')
        if cancelado():
            # 020:RF-27: lo escrito queda; la calibración no llegó a correr.
            informe['cancelado'] = True
            informe['avisos'].append('Cancelado después de cambiar los transformadores: quedan '
                                     'en la red y falta calibrar (020:RF-27).')
            return informe, 0
    # RF-26: la SED cuyos clientes desmarcó todos el operador sale del reparto y su carga
    # queda fuera de servicio en el escenario; repartirle por kVA sería volver a cargarla.
    apagar, desconectadas, avisos_desc = {}, [], []
    por_clave = {clave_codigo(s): s for s in cargas}
    for sed, nis in sed_desconectadas(plan.get('desconectados') or [],
                                      plan.get('clientes') or []).items():
        nombre = por_clave.get(clave_codigo(sed))
        if nombre is None:
            avisos_desc.append(f'{sed} (clientes desmarcados {", ".join(nis)}) no está en '
                               f'{feeder}: no hay carga que desconectar.')
            continue
        apagar[nombre] = cargas.pop(nombre)
        desconectadas.append({'sed': nombre, 'clientes': nis})
    kva, kva_origen = kva_por_sed(cargas, plan.get('kva_entrada') or {})
    objetivo = Objetivo(**plan['objetivo'])
    # Las SED de los clientes se emparejan con las cargas por su código: las fijas toman
    # el nombre de la carga de DIgSILENT.
    # 015:RF-53, RF-54, RF-56: las fijas, con el EA/ERI de la tabla cruzada; las escaladas,
    # con el factor del perfil si lo hay (Electro Dunas, 0,98) y si no con el del archivo.
    fp_cargas = plan.get('factor_potencia_cargas')
    fp_min_fijas = plan.get('factor_potencia_minimo_fijas')
    informe['factor_potencia_cargas'] = {
        'fijas': ('EA/ERI del libro de clientes' if not fp_min_fijas else
                  f'EA/ERI del libro de clientes; por debajo de {fp_min_fijas:.2f}, a '
                  f'{fp_min_fijas:.2f} por su banco propio'),
        'escaladas': fp_cargas or Objetivo(**plan['objetivo']).fp,
        'escaladas_origen': 'perfil de empresa' if fp_cargas else 'máxima de cabecera',
        # 015:RF-44: la P base de cada escalada, su potencia instalada por ese factor.
        'escaladas_reparto': 'potencia instalada (kVA) de cada SED'}
    fijas_libro = fijas_de(plan.get('clientes') or [], objetivo, fp_min_fijas)
    # 015:RF-62, RF-63: los clientes compensados por su banco propio, dichos uno a uno.
    compensadas = [{'sed': f.sed, 'cliente': d['cliente'], 'p_kw': d['p_kw'],
                    **d['compensado']}
                   for f in fijas_libro.values() for d in f.derivaciones if d.get('compensado')]
    if compensadas:
        informe['fijas_compensadas'] = compensadas
        informe['avisos'].append(
            f'{len(compensadas)} cliente(s) fijo(s) con FP por debajo de {fp_min_fijas:.2f} en su '
            f'EA/ERI se escriben a {fp_min_fijas:.2f}, como compensados por su banco propio: '
            + '; '.join(f"{c['sed']} FP {c['fp_ea_eri']:.3f} → {c['fp_escrito']:.3f} "
                        f"(Q {c['q_ea_eri_kvar']:,.1f} → {c['q_escrita_kvar']:,.1f} kvar)"
                        for c in compensadas) + ' (015:RF-62).')
    # 014:RF-10 a RF-12: una demanda cambiada a mano entra fija con su valor y no se
    # sobrescribe; gana sobre el cliente importante de la misma SED.
    manuales, ultimo = cambios_manuales(cargas, plan.get('ultima_calibracion'))
    for m in manuales:
        fijas_libro[clave_codigo(m['sed'])] = Fija(
            m['sed'], m['manual']['kw'], m['manual']['kvar'],
            avisos=['cambio manual: se conserva su demanda (014:RF-10).'])
    if manuales:
        informe['cargas_manuales'] = manuales
        informe['avisos'].append(
            f'{len(manuales)} carga(s) con la demanda cambiada a mano respecto de {ultimo}: '
            'quedan fijas con su valor y no se sobrescriben: ' + '; '.join(
                f"{m['sed']} {m['manual']['kw']:.1f} kW (el ajuste dejó "
                f"{m['ajuste']['kw']:.1f} kW)" for m in manuales[:50]))
    try:
        reparto = reparto_inicial(objetivo, fijas_libro,
                                  {s: potencia(o) for s, o in cargas.items()}, kva,
                                  fp=fp_cargas)
    except AjusteError as exc:
        return {**informe, 'error': str(exc), 'ambiguas': ambiguas}, 2
    fijas = {s: f for f in fijas_libro.values() for s in cargas
             if clave_codigo(s) == clave_codigo(f.sed)}
    # 015:RF-59: un cliente que pide más que el transformador de su SED, nombrado.
    sobre = fijas_sobre_su_transformador(fijas, kva)
    # 020:RF-6 a RF-12: la propuesta de transformadores nuevos, con las fichas del perfil
    # que manda la web en el plan; se validan aquí con la misma lectura que el perfil.
    fichas, motivo_fichas = None, None
    if plan.get('transformadores_sed') is not None:
        from igea_dgs.perfil_empresa import PerfilError, transformadores_sed
        try:
            fichas = transformadores_sed(
                {'calibracion': {'transformadores_sed': plan['transformadores_sed']}})
        except PerfilError as exc:
            motivo_fichas = str(exc)
    informe['fichas_transformador_sed'] = (
        {'umbral_carga_pct': fichas['umbral_carga_pct'],
         'normas': [t['norma'] for t in fichas['tablas']], 'avisos': fichas['avisos']}
        if fichas else {'falta': motivo_fichas or 'el perfil de empresa no trae tablas de '
                        'fichas de transformadores (calibracion.transformadores_sed)'})
    if sobre:
        proponer_transformadores(sobre, cargas, fichas, motivo_fichas)
        informe['fijas_sobre_su_transformador'] = sobre
        informe['avisos'].append(
            f'{len(sobre)} SED fija(s) con más demanda que su potencia instalada; revise el '
            'cruce del cliente con su SED o el transformador: ' + '; '.join(
                f"{x['sed']} ({', '.join(x['clientes']) or 'cambio manual'}) "
                f"{x['kva_carga']:,.0f} kVA en {x['kva']:,.0f} kVA ({x['carga_pct']:,.0f} %)"
                for x in sobre))
    antes = {s: potencia_efectiva(o) for s, o in cargas.items()}
    antes_nativo = _foto_cargas_nativas(cargas)
    antes_apagar = {s: int(getattr(o, 'outserv', 0) or 0) for s, o in apagar.items()}
    desde_entrada = sorted(s for s, o in kva_origen.items() if o == 'entrada')
    if desde_entrada:
        informe['avisos'].append(f'{len(desde_entrada)} SED sin transformador con potencia en '
                                 'DIgSILENT: su kVA sale de la entrada original: '
                                 + ', '.join(desde_entrada[:50]))
    informe.update(objetivo=plan['objetivo'], tolerancia=plan.get('tolerancia', 0.01),
                   omitidas=reparto.omitidas, ambiguas=ambiguas,
                   todo_escala=reparto.todo_escala, solo_kw=reparto.solo_kw,
                   desconectadas=desconectadas)
    informe['avisos'] += avisos_desc + reparto.avisos

    if simular:
        informe['bancos'] = bancos_instalados(alims, feeder)
        informe['sed'] = _por_sed(reparto, cargas, kva_origen, antes, fijas)
        informe['totales_sin_perdidas'] = dict(zip(('kw', 'kvar'), reparto.totales()))
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
        return informe, 0
    # 015:RF-26: la calibración ya no crea ni apaga variaciones. Las de ajustes de antes de
    # la spec 015 que sigan activas no se tocan (014:RF-3); se dicen.
    viejos = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or [])
                    if v.loc_name.startswith('Ajuste_'))
    if viejos:
        informe['variaciones_de_ajustes_previos'] = viejos
        informe['avisos'].append('Ajustes de antes de la spec 015 activos en «Sin proyecto» '
                                 '(no se tocan; la calibración va al escenario): '
                                 + ', '.join(viejos))
    # 015:RF-66: los bancos existentes, a su máxima capacidad antes de medir.
    al_maximo = bancos_a_su_maxima_capacidad(alims, feeder)
    if al_maximo:
        informe['bancos_puestos_a_maxima'] = al_maximo
        informe['avisos'].append(
            'Bancos existentes puestos a su máxima capacidad (todos los escalones, en '
            'servicio): ' + ', '.join(c['banco'] for c in al_maximo) + ' (015:RF-66).')
    # Idempotencia nativa: antes de escribir una carga se demuestra si el estado efectivo
    # ya contiene el mismo reparto y cuadre.
    medida_previa = medir_cabecera(app, elm)
    validacion_previa, reparto_nativo = validar_cargas_nativas(
        cargas, reparto, medida_previa, objetivo, float(informe['tolerancia']),
        ambiguas=ambiguas, apagar=apagar, ajustes_flujo=ajustes_del_flujo(app),
        fp_escaladas=None if reparto.todo_escala else (fp_cargas or objetivo.fp),
    )
    informe['validacion_previa_nativa'] = validacion_previa
    if validacion_previa['correcta'] and reparto_nativo is not None:
        fotos = _foto_cargas_nativas(cargas)
        # Las pérdidas salen del mismo consumo efectivo con que se validó, no de
        # ``reparto_nativo.totales()`` (la ``plini`` escrita): en CA101 reabierto, con
        # NO_REDISTRIBUIR, el informe daba -846 kW de pérdidas mientras el flujo aplicado
        # sobre el mismo estado daba +499,8 kW.
        efectivo = validacion_previa.get('consumo_cargas_efectivo') or {}
        p_cargas, q_cargas = reparto_nativo.totales()
        if efectivo.get('kw') is not None:
            p_cargas, q_cargas = efectivo['kw'], efectivo.get('kvar')
        e_kw = ((medida_previa.kw - objetivo.kw) / abs(objetivo.kw)
                if objetivo.kw else medida_previa.kw - objetivo.kw)
        e_kvar = ((medida_previa.kvar - objetivo.kvar) /
                  (abs(objetivo.kvar) if objetivo.kvar else abs(objetivo.kw) or 1.0)
                  if medida_previa.kvar is not None else None)
        q_audit = kvar_difference(medida_previa, objetivo, float(informe['tolerancia']))
        informe.update(
            decision_carga_nativa={
                'status': 'YA_CARGADO_VALIDADO', 'accion': 'NO_REDISTRIBUIR',
                'bloquea': False, 'origen': 'ESTADO_EFECTIVO',
            },
            cuadrado=True, status=q_audit['status'], kvar_no_bloqueante=q_audit,
            cabecera={'kw': medida_previa.kw, 'kvar': medida_previa.kvar},
            medicion_cabecera=detalle_cabecera(elm), flujos=1, fallos=[],
            bancos=bancos_instalados(alims, feeder),
            historial=[{'flujo': 1, 'origen': 'RELECTURA_PREVIA',
                        'converge': True, 'kw': medida_previa.kw,
                        'kvar': medida_previa.kvar}],
            perdidas={'kw': medida_previa.kw - p_cargas,
                      'kvar': (medida_previa.kvar - q_cargas
                               if medida_previa.kvar is not None and q_cargas is not None
                               else None)},
            consumo_cargas_efectivo=(dict(efectivo) if efectivo.get('kw') is not None
                                     else None),
            perdidas_de=efectivo.get('origen') or 'ENTRADAS_NOMINALES',
            desvio={'kw': e_kw, 'kvar': e_kvar},
            criterio_cuadre='KW_ONLY', reparto_solo_kw=reparto_nativo.solo_kw,
            sed=_por_sed(reparto_nativo, cargas, kva_origen, antes, fijas),
            escenario=escenario.loc_name,
            relectura_cargas_nativas={
                'status': 'VERIFICADO_PERSISTENCIA', 'antes': fotos, 'despues': fotos,
                'cantidad': len(fotos), 'poblacion': poblacion_nativa,
            },
        )
        # 014:RF-4: aunque «Sin proyecto» ya esté calibrado, «Con proyecto» tiene que tener
        # la misma demanda; en CA101 (2026-10-15) consumía 3861 kW frente a 5264.
        if con is not None:
            informe['con_proyecto'] = sincronizar_con_proyecto(
                app, con, sin, cargas, reparto_nativo,
                {m['sed'] for m in manuales}, apagar)
            if informe['con_proyecto']['corregidas']:
                informe['avisos'].append(
                    f"«Con proyecto» no tenía la demanda de «Sin proyecto» en "
                    f"{informe['con_proyecto']['corregidas']} carga(s): se le escribió "
                    '(014:RF-4).')
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
        return informe, 0 if not (informe.get('con_proyecto') or {}).get('fallos') else 2
    informe['decision_carga_nativa'] = {
        'status': 'REQUIERE_DISTRIBUCION', 'accion': 'DISTRIBUIR_Y_CUADRAR',
        'bloquea': False,
    }
    remedios = Remedios(app)
    fallos: list[dict] = []
    fallos_desc: list[dict] = []
    fallo_validacion_nativa = False
    con_manual = {m['sed'] for m in manuales}
    informe['escenario'] = escenario.loc_name
    try:
        # RF-18, RF-19 de la 011 y 015:RF-37: fija o escalable. DIgSILENT guarda la marca en
        # la red que comparten los casos, no en el escenario (sonda T1 de la 015); el
        # «Caso base» la ve, pero conserva su demanda porque en él no se calibra.
        for sed in reparto.demandas:
            cargas[sed].i_scale = 1 if sed in reparto.base else 0
        # RF-26: en el escenario, como la demanda.
        for sed, obj in apagar.items():
            try:
                obj.outserv = 1
            except Exception as exc:  # noqa: BLE001 - una SED no tumba el ajuste
                fallos_desc.append({'sed': sed, 'error': f'{type(exc).__name__}: {exc}'})

        def flujo(rep):
            fallos.clear()
            # 014:RF-11: la demanda manual no se escribe.
            fallos.extend(escribir_reparto(cargas, rep, con_manual))
            medida = medir_cabecera(app, elm)
            if medida.converge:
                carga_kw, carga_kvar = consumo_nativo(cargas)
                if carga_kw is not None and carga_kvar is not None:
                    medida = replace(
                        medida, carga_kw=carga_kw, carga_kvar=carga_kvar,
                    )
            return medida

        res = cuadrar(reparto, objetivo, flujo,
                      tolerancia=float(plan.get('tolerancia', 0.01)),
                      max_flujos=int(plan.get('max_flujos') or MAX_FLUJOS),
                      remedio=remedios.aplicar, cancelado=cancelado,
                      progreso=lambda n, m, t: print(f'  {t}'))
        e_kw, e_kvar = res.errores()
        p_kw, p_kvar = res.perdidas()
        informe.update(
            cuadrado=res.cuadrado, motivo=res.motivo or None, cancelado=res.cancelado,
            flujos=res.flujos, remedios=res.remedios, historial=res.historial,
            cabecera=({'kw': res.medida.kw, 'kvar': res.medida.kvar}
                      if res.medida is not None and res.medida.converge else None),
            # «desvio» y no «error»: la web toma «error» por un fallo y mostraba un ajuste
            # que sí cuadró (SI213, −0,14 % y −0,41 %) como error con este diccionario.
            perdidas={'kw': p_kw, 'kvar': p_kvar}, desvio={'kw': e_kw, 'kvar': e_kvar},
            consumo_cargas_efectivo=(
                {'kw': res.medida.carga_kw, 'kvar': res.medida.carga_kvar}
                if res.medida is not None and res.medida.carga_kw is not None else None),
            perdidas_de=('RESULTADOS_CARGAS_NATIVAS'
                         if res.medida is not None and res.medida.carga_kw is not None
                         else 'ENTRADAS_NOMINALES'),
            criterio_cuadre='KW_ONLY', solo_kw=True,
            reparto_solo_kw=(res.reparto.solo_kw if res.reparto is not None else
                             reparto.solo_kw),
            fallos=fallos_desc + list(fallos),
        )
        informe['medicion_cabecera'] = detalle_cabecera(elm)
        # 015:RF-60: los bancos instalados, con lo que entregan en el último flujo.
        informe['bancos'] = bancos_instalados(alims, feeder)
        informe['avisos'] += [a for a in res.avisos if a not in informe['avisos']]
        if res.cuadrado and res.medida is not None:
            q_audit = kvar_difference(res.medida, objetivo, float(informe['tolerancia']))
            informe['status'] = q_audit['status']
            informe['kvar_no_bloqueante'] = q_audit
            if q_audit['status'] == 'AVISO_KVAR':
                native = q_audit['red_nativa_kvar']
                difference = q_audit['diferencia_kvar']
                detail = ('sin lectura de kVAR' if native is None else
                          f'{native:,.2f} kVAR frente a {objetivo.kvar:,.2f} kVAR '
                          f'(diferencia {difference:+,.2f} kVAR)')
                informe['avisos'].append(
                    'AVISO_KVAR: ajuste aceptado por kW; la red nativa DIgSILENT resulta '
                    f'{detail}. La diferencia reactiva se informa y no bloquea la conversión, '
                    'el ajuste ni los estudios.')
        else:
            informe['status'] = ('NO_CONVERGE' if res.medida is None or
                                  not res.medida.converge else 'VIOLACION_FISICA')
        if res.reparto is not None and res.medida is not None:
            validacion_posterior, _reparto_verificado = validar_cargas_nativas(
                cargas, res.reparto, res.medida, objetivo, float(informe['tolerancia']),
                ambiguas=ambiguas, apagar=apagar, ajustes_flujo=ajustes_del_flujo(app),
                fp_escaladas=None if res.reparto.todo_escala else (fp_cargas or objetivo.fp),
            )
            informe['validacion_posterior_nativa'] = validacion_posterior
            if res.cuadrado and not informe['fallos'] and validacion_posterior['correcta']:
                informe['resultado_carga_nativa'] = {
                    'status': 'APLICADO_Y_VALIDADO', 'bloquea': False,
                }
            elif res.cuadrado and not validacion_posterior['correcta']:
                fallo_validacion_nativa = True
                informe['resultado_carga_nativa'] = {
                    'status': 'FALLO_VALIDACION_NATIVA', 'bloquea': True,
                }
                informe['status'] = 'FALLO_VALIDACION_NATIVA'
                informe['cuadrado'] = False
                aviso = aviso_consumo_fisico(validacion_posterior, res.historial,
                                             informe.get('fijas_sobre_su_transformador'))
                if aviso:
                    informe['avisos'].append(aviso)
                informe['fallos'].extend({
                    'sed': fallo.get('sed'),
                    'error': f"validación nativa: {fallo.get('tipo')}",
                    'detalle': fallo,
                } for fallo in validacion_posterior['fallos'])
                # Una cabecera cuadrada no compensa una carga que la relectura nativa no
                # conservó: las cargas vuelven a como estaban y no queda nada para estudios.
                _restaurar_cargas(cargas, antes_nativo, apagar, antes_apagar)
                informe['calibracion_revertida'] = True
        if res.reparto is not None:
            informe['sed'] = _por_sed(res.reparto, cargas, kva_origen, antes, fijas)
            despues_nativo = _foto_cargas_nativas(cargas)
            informe['relectura_cargas_nativas'] = {
                'status': ('FALLO_VALIDACION_NATIVA' if fallo_validacion_nativa else
                           'VERIFICADO_PERSISTENCIA' if not informe['fallos'] else
                           'AVISO_RELECTURA'),
                'antes': antes_nativo, 'despues': despues_nativo,
                'cantidad': len(despues_nativo), 'poblacion': poblacion_nativa,
            }
        if any(not h['converge'] for h in res.historial) or not res.cuadrado:
            fallido = next((reparto.con_factores(h['a'], h['b'])
                            for h in res.historial if not h['converge']), None)
            informe['diagnostico'] = diagnostico(alims, feeder, cargas, kva, fallido)
        if res.cancelado:
            informe['avisos'].append('Cancelado: el escenario queda con el último reparto '
                                     'que convergió.')
        if not res.cuadrado:
            informe['avisos'].append(
                f'NO cumple el {informe["tolerancia"]:.1%}: {res.motivo}. El escenario queda '
                'con el último reparto que convergió.')
        if sobre and (fallo_validacion_nativa or not res.cuadrado):
            informe['sobrecarga_causa_probable'] = True
            informe['avisos'].append(aviso_sobrecarga(sobre))
        cambiados = (informe.get('transformadores_implementados') or {}).get('cambios') or []
        if cambiados:
            informe['resultado_transformadores'] = resultado_transformadores(
                cambiados, sobre, fijas, cargas, plan.get('transformadores_sed') or {},
                calibracion_valida=bool(res.cuadrado and not fallo_validacion_nativa),
                validacion=informe.get('validacion_posterior_nativa'),
                remedios=res.remedios, motivo=res.motivo)
            if informe['resultado_transformadores']['status'] != 'VALIDO':
                informe['avisos'].append(informe['resultado_transformadores']['aviso'])
        if res.reparto is not None and not fallo_validacion_nativa:
            escenario.Save()
            informe['escenarios'] = [{'escenario': escenario.loc_name,
                                      'cargas': len(res.reparto.demandas) - len(con_manual),
                                      'fallos': []}]
            if con is not None:
                # 014:RF-4: «Con proyecto» sigue sobre la red calibrada; su escenario es suyo.
                con.Activate()
                esc_con = app.GetActiveScenario()
                if esc_con is not None:
                    fallos_con = escribir_reparto(cargas, res.reparto, con_manual)
                    for _sed, obj in apagar.items():
                        obj.outserv = 1
                    esc_con.Save()
                    informe['escenarios'].append({'escenario': esc_con.loc_name,
                                                  'cargas': len(res.reparto.demandas) - len(con_manual),
                                                  'fallos': fallos_con})
                    informe['fallos'] += fallos_con
                sin.Activate()
    finally:
        # 015:RF-46: en «Sin proyecto», caso del sistema, los ajustes del flujo que hicieron
        # falta se quedan para que el caso siga convergiendo (CA101 desde cero, 2026-10-14:
        # cuadró con «adaptación automática del modelo» y, restituida, no convergía). Si no
        # cuadró o se revirtió, se restituyen, como en el caso del operador (006:RF-16).
        if (sin is not None and remedios.originales and informe.get('cuadrado')
                and not fallo_validacion_nativa):
            aplicados = remedios.aplicados()
            informe['ajustes_del_flujo_conservados'] = aplicados
            if con is not None:
                con.Activate()
                remedios.aplicar_en(app.GetFromStudyCase('ComLdf'), aplicados)
            informe['avisos'].append(
                'Ajustes del flujo de carga que se quedan en «Sin proyecto»'
                + (' y «Con proyecto»' if con is not None else '') + ' para que converja: '
                + ', '.join(f'{k}={v}' for k, v in aplicados.items()) + ' (015:RF-46).')
        else:
            restituidos = remedios.restituir()
            if restituidos:
                informe['ajustes_restituidos'] = restituidos
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, (0 if informe.get('cuadrado') and not informe.get('fallos') else 2)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Ajuste de las demandas a la máxima de cabecera')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    p.add_argument('--simular', action='store_true', help='Reparto sin escribir (RF-20)')
    p.add_argument('--cancel-file', help='Si aparece, termina el flujo en curso (RF-22)')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    blocked = native_action_block_report(plan, 'ajuste')
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('ajuste_cabecera_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    flag = Path(args.cancel_file) if args.cancel_file else None
    try:
        informe, codigo = ejecutar(app, plan, simular=args.simular,
                                   cancelado=lambda: bool(flag and flag.exists()))
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        # «Ajustar SI213 a la máxima» (2026-10-10) acabó con el código 1 y sin informe: la
        # web solo podía decir «vea el Registro». La traza sigue yendo al Registro.
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, args.simular, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
