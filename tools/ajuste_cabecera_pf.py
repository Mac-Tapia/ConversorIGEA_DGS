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
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from cargas_pf import (
    Alimentadores,
    _num,
    activar_proyecto,
    cabecera_de,
    detalle_cabecera,
    error_inesperado,
    error_relectura,
    escribir_carga,
    leer_cabecera,
    leer_red,
    medir_cabecera,
    nombre_libre,
    nombre_pf,
    potencia,
)
from casos_pf import NOMBRES, casos_del_proyecto, es_de_carga_nueva, preparar_sin, sin_a_con_proyecto
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


@contextmanager
def _centrales_apagadas(app):
    """Las variaciones de central apagadas mientras se escribe dato de red (015:RF-37).

    Su etapa sigue grabando aunque se desactive y se vuelva a activar (sonda del
    2026-10-17): una marca fija o escalable escrita con ella activa queda dentro de la
    variación y la pisa cada vez que se activa. En el sistema Nasca (2026-10-18), la
    restauración de una pasada no válida dejó 167 cargas en «Central_NA205» y las fijas de
    NA203 salían escalables en la validación.
    """
    activas = [v for v in (app.GetActiveNetworkVariations() or [])
               if v.loc_name.startswith(PREFIJO_CENTRAL)]
    for v in activas:
        v.Deactivate()
    try:
        yield
    finally:
        for v in activas:
            v.Activate()


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
            escalon = _num(o, 'qcapn')
            barra, sed = _barra_y_sed(o)
            cambios.append({'banco': o.loc_name, 'barra': barra, 'sed': sed,
                            'kvar_escalon': None if escalon is None else escalon * 1000.0,
                            'antes': antes, 'despues': despues})
    return cambios


def _barra_y_sed(o) -> tuple[str | None, str | None]:
    """La barra de un banco y la SED en la que está, si está dentro de una (021:RF-11)."""
    try:
        barra = o.bus1.cterm
    except Exception:  # noqa: BLE001 - banco sin conectar
        return None, None
    padre = barra.GetParent() if hasattr(barra, 'GetParent') else None
    sed = (padre.loc_name if padre is not None and getattr(padre, 'GetClassName', lambda: '')()
           == 'ElmSubstat' else None)
    return getattr(barra, 'loc_name', None), sed


def fijar_consigna_de_la_fuente(app, pu: float, casos: list) -> list[dict]:
    """La tensión en la fuente que indica el operador, en cada red externa (021:RF-61).

    NA203 y NA205, de 22,9 kV (2026-10-17), no convergían con su carga fija: 0,906 pu en
    SE50290 con la fuente a 1,0 pu; el usuario: «puede enviar desde la fuente con 1,05 pu».
    Es dato de operación: va al escenario de cada caso (``casos``, el primero el que se
    calibra) y se guarda. Deja activo el primero y devuelve lo que cambió en él.
    """
    cambios = []
    for n, caso in enumerate(c for c in casos if c is not None):
        caso.Activate()
        for x in app.GetCalcRelevantObjects('*.ElmXnet') or []:
            antes = _num(x, 'usetp')
            if antes is not None and math.isclose(antes, pu, abs_tol=1e-6):
                continue
            x.usetp = pu
            if n == 0:
                barra, _sed = _barra_y_sed(x)
                cambios.append({'fuente': x.loc_name, 'barra': barra, 'antes': antes, 'despues': pu})
        escenario = app.GetActiveScenario()
        if escenario is not None:
            escenario.Save()
    primero = next((c for c in casos if c is not None), None)
    if primero is not None:
        primero.Activate()
    return cambios


def cambios_en_la_red(informe: dict) -> list[dict]:
    """Cada elemento de la red que cambió la calibración, con lo original y lo nuevo (020:RF-60, RF-61).

    El usuario, el 2026-10-17, tras los 6 transformadores de NA203: «todos los cambios que
    se hacen se deben reportar como original existente con su potencia instalada y el
    valor de potencia cambiada con sus respectivos códigos SED». Un transformador, como
    unidades × kVA y su total; un banco, como escalones conectados × kvar por escalón.
    """
    filas = []
    for c in (informe.get('transformadores_implementados') or {}).get('cambios') or []:
        lados = {}
        for lado, x in (('original', c['antes']), ('nuevo', c['despues'])):
            unidades, kva = x.get('unidades'), x.get('kva')
            total = unidades * kva if unidades is not None and kva is not None else None
            lados[lado] = {'descripcion': f"{unidades} × {kva:g} kVA ({x.get('tipo') or '—'})"
                           if total is not None else (x.get('tipo') or '—'),
                           'potencia': total, 'unidad': 'kVA'}
        filas.append({'sed': c['sed'], 'elemento': c['transformador'], 'clase': 'transformador',
                      **lados, 'motivo': 'transformador nuevo con su ficha (020:RF-16)'})
    for x in informe.get('consigna_fuente') or []:                     # 021:RF-62
        filas.append({'sed': x.get('barra') or '', 'elemento': x['fuente'], 'clase': 'fuente',
                      'original': {'descripcion': 'consigna de tensión'
                                   + ('' if x['antes'] is None else f" {x['antes']:.3f} pu"),
                                   'potencia': x['antes'], 'unidad': 'pu'},
                      'nuevo': {'descripcion': f"consigna de tensión {x['despues']:.3f} pu",
                                'potencia': x['despues'], 'unidad': 'pu'},
                      'motivo': 'tensión en la fuente indicada por el operador (021:RF-61)'})
    for b in informe.get('bancos_nuevos') or []:                         # 021:RF-69
        filas.append({'sed': b.get('barra') or '', 'elemento': b['banco'], 'clase': 'banco',
                      'original': {'descripcion': 'no existe', 'potencia': 0.0, 'unidad': 'kvar'},
                      'nuevo': {'descripcion': f"banco nuevo de {b['kvar']:g} kvar en {b['kv']:g} kV",
                                'potencia': b['kvar'], 'unidad': 'kvar'},
                      'motivo': 'banco que faltaba para el kVAR medido (021:RF-64)'})
    for b in informe.get('bancos_puestos_a_maxima') or []:
        q = b.get('kvar_escalon')
        lados = {}
        for lado, x in (('original', b['antes']), ('nuevo', b['despues'])):
            pasos = x.get('escalones')
            servicio = '' if x.get('en_servicio') else ', fuera de servicio'
            lados[lado] = {
                'descripcion': (f'{pasos:g} escalón(es) × {q:g} kvar{servicio}' if pasos is not None
                                and q is not None else f'{pasos} escalón(es){servicio}'),
                'potencia': (pasos * q if pasos is not None and q is not None
                             and x.get('en_servicio') else 0.0 if not x.get('en_servicio') else None),
                'unidad': 'kvar'}
        filas.append({'sed': b.get('sed') or b.get('barra') or '', 'elemento': b['banco'],
                      'clase': 'banco', **lados,
                      'motivo': 'banco existente a su máxima capacidad (015:RF-66)'})
    return filas


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
    # La variación de una central (021:RF-37) es del conversor y está activa en «Sin
    # proyecto»: se apaga mientras se escriben y se vuelve a encender, como al marcar las
    # cargas fijas o escalables. En NA203 + NA205 (2026-10-17) la de NA205 bloqueaba los
    # transformadores de NA203.
    activas = list(app.GetActiveNetworkVariations() or [])
    centrales = [v for v in activas if v.loc_name.startswith(PREFIJO_CENTRAL)]
    for v in centrales:
        v.Deactivate()
    try:
        return _implementar_transformadores(app, cargas, cambios)
    finally:
        for v in centrales:
            v.Activate()


def _implementar_transformadores(app, cargas: dict, cambios: list[dict]) -> dict:
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
        with _centrales_apagadas(app):                                  # 015:RF-37
            fallos = escribir_reparto(cargas, reparto, set(omitir) | iguales)
        for obj in apagar.values():
            obj.outserv = 1
        escenario.Save()
    resultado = {'escenario': getattr(escenario, 'loc_name', None),
                 'corregidas': len(distintas), 'fallos': fallos}
    sin.Activate()
    return resultado



# =========================================================================== central (spec 021)
#: Prefijo del generador y de la variación de la central que crea el conversor (RF-36).
PREFIJO_CENTRAL = 'Central_'


def _misma_pf(a, b) -> bool:
    try:
        return a is not None and b is not None and a.GetFullName() == b.GetFullName()
    except Exception:  # noqa: BLE001
        return a is b


def barra_de_la_central(app, elm, nodo: str):
    """La barra ``nodo`` del alimentador y la parte aguas abajo (021:RF-38, RF-39).

    El ``ElmFeeder`` da sus objetos según la última topología calculada: se corre un
    flujo antes de leer la red. Devuelve ``(barra, subárbol, aviso)`` o lanza
    ``ValueError`` con el nodo y el alimentador. Fuera del camino más largo (la troncal)
    no se rechaza: en el NA205 del TXT (sistema Nasca, 2026-10-18) ese camino va por otra
    rama, a 37 km, y la central 1720 queda en serie en la suya, a 15 km; las zonas solo
    piden lo de aguas abajo de su barra, que es lo que miden su llegada y su salida.
    """
    from cargas_pf import cabecera_de, leer_red

    from igea_dgs.troncal import TroncalError, aguas_abajo
    from igea_dgs.troncal import troncal as troncal_de

    app.GetFromStudyCase('ComLdf').Execute()
    cabecera = cabecera_de(elm)
    if cabecera is None:
        raise ValueError(f'{elm.loc_name}: el alimentador no dice su cabecera')
    barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
    barra = barras.get(nodo)
    if barra is None:
        raise ValueError(f'la barra {nodo!r} de la central no está en el alimentador {elm.loc_name}')
    red = leer_red(elm, cabecera)
    try:
        tronco = troncal_de(red, cabecera.loc_name)
        parte = aguas_abajo(red, cabecera.loc_name, nodo)
    except TroncalError as exc:
        raise ValueError(f'{elm.loc_name}: {exc}') from None
    tramos = red.por_nombre()
    en_troncal = {cabecera.loc_name} | {b for t in tronco.tramos
                                        for b in (tramos[t].desde, tramos[t].hasta)}
    aviso = (None if nodo in en_troncal else
             f'la barra {nodo!r} de la central no está en el camino más largo de {elm.loc_name}: '
             'se calibra por zonas con lo que tiene aguas abajo de ella (021:RF-38)')
    if parte.entrada is None:
        raise ValueError(f'la barra {nodo!r} es la cabecera de {elm.loc_name}: ahí no hay zona '
                         'aguas arriba')
    return barra, parte, aviso


def barra_mt_de(carga) -> str | None:
    """La barra de media de una carga: la suya o, si cuelga de una SED, la de alta de su
    transformador (con barra propia, la del alimentador; 021:RF-12)."""
    term = getattr(getattr(carga, 'bus1', None), 'cterm', None)
    if term is None:
        return None
    if float(getattr(term, 'uknom', 0) or 0) >= 1.0:
        return term.loc_name
    for cub in term.GetContents('*.StaCubic') or []:
        tr = getattr(cub, 'obj_id', None)
        if tr is not None and tr.GetClassName() == 'ElmTr2':
            alta = getattr(getattr(tr, 'bushv', None), 'cterm', None)
            if alta is not None:
                padre = alta.GetParent()
                # Sin barra propia, la de alta es la de dentro de la SED; su acoplador la une
                # a la del alimentador, que es la que está en la red.
                if padre is not None and padre.GetClassName() == 'ElmSubstat':
                    for c in alta.GetContents('*.StaCubic') or []:
                        acople = getattr(c, 'obj_id', None)
                        if acople is not None and acople.GetClassName() == 'ElmCoup':
                            for lado in ('bus1', 'bus2'):
                                otra = getattr(getattr(acople, lado, None), 'cterm', None)
                                if otra is not None and not _misma_pf(otra, alta):
                                    return otra.loc_name
                return alta.loc_name
    return term.loc_name


def cargas_por_zona(cargas: dict, aguas_abajo_barras) -> tuple[dict, dict]:
    """Las cargas de aguas arriba y las de aguas abajo de la central (021:RF-39)."""
    abajo = set(aguas_abajo_barras)
    arriba_z, abajo_z = {}, {}
    for sed, obj in cargas.items():
        (abajo_z if barra_mt_de(obj) in abajo else arriba_z)[sed] = obj
    return arriba_z, abajo_z


def variacion_de_la_central(app, feeder: str):
    """La variación de la central de ``feeder`` que creó el conversor, o ``None``."""
    carpeta = app.GetProjectFolder('scheme')
    nombre = f'{PREFIJO_CENTRAL}{feeder}'
    return next((v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])
                 if v.loc_name == nombre or v.loc_name.startswith(nombre + '(')), None)


def central_en_sin_proyecto(app, barra, feeder: str, p_kw: float, q_kvar: float) -> dict:
    """El generador de la central en su barra, con la P y Q medidas (021:RF-35, RF-36).

    Va en su variación ``Central_<alimentador>``, activa en «Sin proyecto» (y en «Con
    proyecto», que es su copia, 014), nunca en el «Caso base» (RF-37). Si ya está, solo se
    le escriben la P y la Q, en el escenario. Sonda del 2026-10-17 en una copia de NA203 +
    NA205: un ``ElmGenstat`` con ``av_mode='constq'`` inyecta lo escrito (5,0 MW y −0,4
    Mvar), y la etapa que lo crea sigue grabando aunque se desactive y active la
    variación: por eso el ajuste escribe antes la marca fija o escalable (red) y después
    crea la central.
    """
    from cargas_pf import crear_variacion, nombre_pf

    nombre = nombre_pf(f'{PREFIJO_CENTRAL}{feeder}')
    variacion = variacion_de_la_central(app, feeder)
    if variacion is not None and variacion.loc_name not in {
            v.loc_name for v in (app.GetActiveNetworkVariations() or [])}:
        variacion.Activate()
    gen = next((o for o in (app.GetCalcRelevantObjects('*.ElmGenstat') or [])
                if o.loc_name == nombre), None)
    creado = gen is None
    if creado:
        variacion, _etapa = crear_variacion(app, nombre, 'central')
        red = barra.GetParent()
        while red is not None and red.GetClassName() != 'ElmNet':
            red = red.GetParent()
        gen = (red or barra.GetParent()).CreateObject('ElmGenstat', nombre)
        cub = barra.CreateObject('StaCubic', f'Cub_{nombre}')
        gen.bus1 = cub
        gen.sgn = max(1.2 * math.hypot(p_kw, q_kvar) / 1000.0, 0.1)
        gen.av_mode = 'constq'
        gen.ip_ctrl = 0
        gen.mode_inp = 'PQ'
    gen.pgini = p_kw / 1000.0
    gen.qgini = q_kvar / 1000.0
    limpiados = _limpiar_etapa_de_la_central(variacion, gen.loc_name)
    return {'generador': gen.loc_name, 'barra': barra.loc_name, 'creado': creado,
            'variacion': getattr(variacion, 'loc_name', None), 'p_kw': p_kw, 'q_kvar': q_kvar,
            **({'cambios_ajenos_quitados': limpiados} if limpiados else {})}


def _limpiar_etapa_de_la_central(variacion, generador: str) -> int:
    """Deja en la etapa de la central solo su generador y su cubículo (021:RF-37, 015:RF-37).

    Lo demás que haya grabado (las 167 cargas de «Central_NA205» del sistema Nasca,
    2026-10-18) no es de la central y pisaba la marca fija o escalable de la red.
    """
    if variacion is None:
        return 0
    ajenos = [obj for etapa in (variacion.GetContents('*.IntSstage', 1) or [])
              for obj in (etapa.GetContents('*', 1) or [])
              if not ((obj.GetClassName() == 'ElmGenstat' and obj.loc_name == generador) or (
                  obj.GetClassName() == 'StaCubic' and obj.loc_name == f'Cub_{generador}'))]
    if not ajenos:
        return 0
    # Con la variación activa, DIgSILENT no deja borrar lo de su etapa: ``Delete`` da 1 y
    # el registro sigue (sonda en el sistema Nasca, 2026-10-18: «quitaba» 167 cargas en cada
    # ajuste y seguían ahí). Desactivada, da 0; al reactivarla, recalcula con la red.
    variacion.Deactivate()
    try:
        quitados = sum(1 for obj in ajenos if obj.Delete() == 0)
    finally:
        variacion.Activate()
    return quitados


def medir_zonas(app, elm, barra, entrada: str):
    """Flujo y lo que da cada zona (021:RF-40, RF-41, RF-44).

    Aguas arriba: lo que entra por la cabecera más lo que sale de la barra de la central
    hacia la SET (la llegada); aguas abajo: lo que sale de ella por las demás ramas. En la
    sonda, ``m:Psum:busN`` del extremo de cada línea en la barra es lo que sale de ella.
    """
    return leer_zonas(medir_cabecera(app, elm), barra, entrada)


def leer_zonas(cab, barra, entrada: str):
    """Las zonas de :func:`medir_zonas` con el último flujo y la cabecera ya leída: en
    el ajuste de un proyecto (021:RF-54) un flujo sirve a todos los alimentadores."""
    from igea_dgs.ajuste_cabecera import MedidaZonas

    if not cab.converge:
        return MedidaZonas(False, motivo=cab.motivo)
    llegada = [0.0, 0.0]
    salida = [0.0, 0.0]
    for cub in barra.GetContents('*.StaCubic') or []:
        rama = getattr(cub, 'obj_id', None)
        if rama is None or rama.GetClassName() not in ('ElmLne', 'ElmCoup', 'ElmTr2'):
            continue
        if rama.GetClassName() == 'ElmTr2':
            # Una SED en la misma barra de la central: su transformador es una salida más.
            lado = 'hv' if _misma_pf(getattr(rama, 'bushv', None), cub) else 'lv'
        else:
            lado = 1 if _misma_pf(getattr(rama, 'bus1', None), cub) else 2
        p = _num(rama, f'm:Psum:bus{lado}')
        q = _num(rama, f'm:Qsum:bus{lado}')
        if p is None:
            return MedidaZonas(False, motivo=f'sin resultados en {rama.loc_name}')
        destino = llegada if rama.loc_name == entrada else salida
        destino[0] += p * 1000.0
        destino[1] += (q or 0.0) * 1000.0
    return MedidaZonas(True, arriba_kw=cab.kw + llegada[0], arriba_kvar=cab.kvar + llegada[1],
                       abajo_kw=salida[0], abajo_kvar=salida[1],
                       cabecera_kw=cab.kw, cabecera_kvar=cab.kvar)


def _preparar_central(app, plan: dict, informe: dict, *, elm, feeder: str, cargas: dict,
                      kva: dict, fijas_libro: dict, fp_cargas, ambiguas) -> dict | tuple[dict, int]:
    """Las dos zonas de un alimentador con una central en su troncal (spec 021, RF-35 a RF-45).

    Las cargas se separan por la barra de la central: las de aguas arriba se ajustan a lo
    que entra por la cabecera y por la llegada, y las de aguas abajo a la salida, cada
    zona con su factor de escala (RF-40, RF-41). La central lleva la P y Q que medía en
    el registro de la máxima de demanda (RF-35). Devuelve lo que necesita el cuadre o
    ``(informe, código)`` si no se puede.
    """
    from igea_dgs.ajuste_cabecera import AjusteError, objetivo_zonas_de, reparto_inicial
    from igea_dgs.demanda_medida import clave_codigo

    central = plan['central']
    try:
        objetivo = objetivo_zonas_de(central['maxima'])
    except AjusteError as exc:
        return {**informe, 'error': str(exc)}, 2
    try:
        barra, parte, aviso = barra_de_la_central(app, elm, str(central.get('nodo') or '').strip())
    except ValueError as exc:
        return {**informe, 'error': str(exc)}, 2                                    # RF-38
    if aviso:
        informe['avisos'].append(aviso)
    arriba, abajo = cargas_por_zona(cargas, parte.barras)                          # RF-39
    zonas = {'arriba': arriba, 'abajo': abajo}
    # ``fijas_de`` las da por su código de SED tal como viene en el libro; se reparten por
    # la zona de la carga con ese código.
    fijas_z = {z: {k: f for k, f in fijas_libro.items()
                   if any(clave_codigo(s) == clave_codigo(f.sed) for s in c)}
               for z, c in zonas.items()}
    fuera = [f.sed for k, f in fijas_libro.items()
             if not any(k in fijas_z[z] for z in zonas)]
    try:
        repartos = {z: reparto_inicial(o, fijas_z[z], {s: potencia(c) for s, c in zonas[z].items()},
                                       kva, fp=fp_cargas)
                    for z, o in (('arriba', objetivo.arriba), ('abajo', objetivo.abajo))}
    except AjusteError as exc:
        return {**informe, 'error': f'{feeder} con central: {exc}'}, 2
    fijas = {s: f for f in fijas_libro.values() for s in cargas
             if clave_codigo(s) == clave_codigo(f.sed)}
    informe.update(
        objetivo=plan['objetivo'], tolerancia=float(plan.get('tolerancia', 0.01)),
        ambiguas=ambiguas,
        central={'barra': barra.loc_name, 'entrada': parte.entrada,
                 'generacion_kw': objetivo.generacion_kw,
                 'generacion_kvar': objetivo.generacion_kvar, 'fecha': objetivo.fecha,
                 'cargas_aguas_arriba': len(arriba), 'cargas_aguas_abajo': len(abajo)},
        omitidas=[{'sed': s, 'motivo': 'no está en el alimentador del proyecto', 'clientes': ''}
                  for s in fuera],
        criterio_cuadre='ZONAS_DE_LA_CENTRAL')
    informe['avisos'].append(
        f'{feeder} con central en {barra.loc_name}: {len(arriba)} carga(s) aguas arriba y '
        f'{len(abajo)} aguas abajo; se calibra cada zona con su factor de escala (021:RF-40, '
        'RF-41).')
    for r in repartos.values():
        informe['avisos'] += [a for a in r.avisos if a not in informe['avisos']]
    return {'objetivo': objetivo, 'barra': barra, 'parte': parte, 'zonas': zonas,
            'repartos': repartos, 'fijas': fijas}


def _ejecutar_con_central(app, plan: dict, informe: dict, *, alims, elm, feeder: str,
                          cargas: dict, kva: dict, kva_origen: dict, fijas_libro: dict,
                          fp_cargas, apagar: dict, manuales: list, ambiguas, sin, con,
                          inicial, escenario, simular: bool, cancelado) -> tuple[dict, int]:
    """El ajuste de un alimentador con una central en su troncal (spec 021, RF-35 a RF-45).

    Sin central, :func:`_ejecutar` sigue como siempre (RF-46).
    """
    from igea_dgs.ajuste_cabecera import MAX_FLUJOS, Medida, cuadrar_zonas

    zc = _preparar_central(app, plan, informe, elm=elm, feeder=feeder, cargas=cargas, kva=kva,
                           fijas_libro=fijas_libro, fp_cargas=fp_cargas, ambiguas=ambiguas)
    if isinstance(zc, tuple):
        return zc
    objetivo, barra, parte = zc['objetivo'], zc['barra'], zc['parte']
    zonas, repartos, fijas = zc['zonas'], zc['repartos'], zc['fijas']
    arriba, abajo = zonas['arriba'], zonas['abajo']
    tolerancia = informe['tolerancia']
    antes = {s: potencia_efectiva(o) for s, o in cargas.items()}
    if simular:
        informe['sed'] = (_por_sed(repartos['arriba'], arriba, kva_origen, antes, fijas)
                          + _por_sed(repartos['abajo'], abajo, kva_origen, antes, fijas))
        informe['zonas'] = {z: dict(zip(('kw', 'kvar'), r.totales())) for z, r in repartos.items()}
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
        return informe, 0

    remedios = Remedios(app)
    fallos: list[dict] = []
    con_manual = {m['sed'] for m in manuales}
    informe['escenario'] = escenario.loc_name
    try:
        # La marca fija o escalable es dato de red (015:RF-37): se escribe con la variación
        # de la central apagada, para que no caiga en su etapa, que sigue grabando.
        previa = variacion_de_la_central(app, feeder)
        if previa is not None and previa.loc_name in {
                v.loc_name for v in (app.GetActiveNetworkVariations() or [])}:
            previa.Deactivate()
        for z, r in repartos.items():
            for sed in r.demandas:
                zonas[z][sed].i_scale = 1 if sed in r.base else 0
        for obj in apagar.values():
            obj.outserv = 1
        informe['central'].update(central_en_sin_proyecto(                     # RF-35, RF-36
            app, barra, feeder, objetivo.generacion_kw, objetivo.generacion_kvar))

        def flujo(rep_arriba, rep_abajo):
            fallos.clear()
            with _centrales_apagadas(app):                              # 015:RF-37
                fallos.extend(escribir_reparto(arriba, rep_arriba, con_manual))
                fallos.extend(escribir_reparto(abajo, rep_abajo, con_manual))
            return medir_zonas(app, elm, barra, parte.entrada)

        res = cuadrar_zonas(repartos['arriba'], repartos['abajo'], objetivo, flujo,
                            tolerancia=tolerancia,
                            max_flujos=int(plan.get('max_flujos') or MAX_FLUJOS),
                            remedio=remedios.aplicar, cancelado=cancelado,
                            progreso=lambda n, m, t: print(f'  {t}'))
        m = res.medida
        informe.update(
            cuadrado=res.cuadrado, motivo=res.motivo or None, cancelado=res.cancelado,
            flujos=res.flujos, remedios=res.remedios, historial=res.historial,
            zonas=res.resumen(), fallos=list(fallos),
            cabecera=({'kw': m.cabecera_kw, 'kvar': m.cabecera_kvar}
                      if m is not None and m.converge else None))
        informe['avisos'] += [a for a in res.avisos if a not in informe['avisos']]
        if m is not None and m.converge and objetivo.cabecera_kw is not None:
            informe['avisos'].append(
                f'Cabecera calculada {m.cabecera_kw:,.1f} kW frente a {objetivo.cabecera_kw:,.1f} kW '
                f'medidos el {objetivo.fecha}, con la central dando {objetivo.generacion_kw:,.1f} kW '
                '(021:RF-44).')
        # 015:RF-47 a RF-52, por zona: cada una contra lo que entra en ella.
        validaciones = {}
        for z, rep, kw, kvar, obj_z in (
                ('arriba', res.arriba, m.arriba_kw if m else None, m.arriba_kvar if m else None,
                 objetivo.arriba),
                ('abajo', res.abajo, m.abajo_kw if m else None, m.abajo_kvar if m else None,
                 objetivo.abajo)):
            if rep is None or m is None or not m.converge or z not in res.ajustables:
                continue
            validaciones[z], _ = validar_cargas_nativas(
                zonas[z], rep, Medida(True, kw, kvar), obj_z, tolerancia, apagar=apagar,
                ajustes_flujo=ajustes_del_flujo(app),
                fp_escaladas=None if rep.todo_escala else (fp_cargas or obj_z.fp))
        informe['validacion_posterior_nativa'] = validaciones
        invalida = [z for z, v in validaciones.items() if not v['correcta']]
        if res.cuadrado and invalida:
            informe['cuadrado'] = False
            informe['status'] = 'FALLO_VALIDACION_NATIVA'
            informe['avisos'].append('La validación de lo que consumen las cargas no es '
                                     'correcta en la zona ' + ', '.join(invalida) + '.')
        elif not res.cuadrado:
            informe['status'] = ('NO_CONVERGE' if m is None or not m.converge
                                 else 'VIOLACION_FISICA')
            informe['avisos'].append(f'NO cumple el {tolerancia:.1%} en las dos zonas: '
                                     f'{res.motivo}.')
        else:
            informe['status'] = 'OK'
        if res.arriba is not None and res.abajo is not None:
            informe['sed'] = (_por_sed(res.arriba, arriba, kva_origen, antes, fijas)
                              + _por_sed(res.abajo, abajo, kva_origen, antes, fijas))
        # 015:RF-49: lo que no consume lo escrito no se guarda (como en el del proyecto).
        if res.arriba is not None and res.abajo is not None and not (res.cuadrado and invalida):
            escenario.Save()
            informe['escenarios'] = [{'escenario': escenario.loc_name,
                                      'cargas': len(cargas) - len(con_manual), 'fallos': []}]
            if con is not None:
                # 014:RF-4 y RF-31: «Con proyecto» con la misma demanda, la misma central
                # (su variación) y su P y Q en su escenario.
                informe['sin_a_con'] = sin_a_con_proyecto(app, casos_del_proyecto(app))
                informe['avisos'] += informe['sin_a_con']['avisos']
                con.Activate()
                esc_con = app.GetActiveScenario()
                if esc_con is not None:
                    fallos_con = (escribir_reparto(arriba, res.arriba, con_manual)
                                  + escribir_reparto(abajo, res.abajo, con_manual))
                    for obj in apagar.values():
                        obj.outserv = 1
                    gen = next((o for o in (app.GetCalcRelevantObjects('*.ElmGenstat') or [])
                                if o.loc_name == informe['central']['generador']), None)
                    if gen is not None:
                        gen.pgini = objetivo.generacion_kw / 1000.0
                        gen.qgini = objetivo.generacion_kvar / 1000.0
                    else:
                        informe['avisos'].append('«Con proyecto» no tiene la central: active su '
                                                 f"variación {informe['central']['variacion']}.")
                    esc_con.Save()
                    informe['escenarios'].append({'escenario': esc_con.loc_name,
                                                  'cargas': len(cargas) - len(con_manual),
                                                  'fallos': fallos_con})
                    informe['fallos'] = informe.get('fallos', []) + fallos_con
                sin.Activate()
    finally:
        if sin is not None and remedios.originales and informe.get('cuadrado'):
            informe['ajustes_del_flujo_conservados'] = remedios.aplicados()
        else:
            restituidos = remedios.restituir()
            if restituidos:
                informe['ajustes_restituidos'] = restituidos
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, (0 if informe.get('cuadrado') and not informe.get('fallos') else 2)


def _factor_minimo_sin_converger(historial, clave: str | None = None) -> float | None:
    """El menor factor de las escaladas con el que el flujo no convergió antes del primero
    que sí, o ``None`` si convergió sin remedios. En el ajuste de un proyecto el historial
    lleva un factor por alimentador (021:RF-55): ``clave`` dice cuál; NA203 + NA205
    (2026-10-17) acabó en un ``TypeError`` comparando los diccionarios."""
    menor = None
    for paso in historial or []:
        if paso.get('converge'):
            return menor
        a = paso.get('a')
        if isinstance(a, dict):
            a = a.get(clave)
        if a is not None and (menor is None or a < menor):
            menor = a
    return menor


def aviso_consumo_fisico(validacion: dict, historial=None, sobre=None,
                         clave: str | None = None) -> str | None:
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
    minimo = _factor_minimo_sin_converger(historial, clave)
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
        informe, rc = _ejecutar(app, plan, simular=simular, cancelado=cancelado, estado=estado)
    finally:
        _devolver_cargas_nuevas(app, estado)
    cambios = cambios_en_la_red(informe)                                # 020:RF-60
    if cambios:
        informe['cambios_en_la_red'] = cambios
    return informe, rc


def _preparar_alimentador(app, plan: dict, informe: dict, *, alims, feeder: str,
                          simular: bool, cancelado) -> dict | tuple[dict, int]:
    """Lo de un alimentador antes del cuadre: sus cargas, las fijas, las desconectadas, los
    cambios manuales y el reparto inicial (o ``central``, para el de zonas).

    La comparten el ajuste de un alimentador (:func:`_ejecutar`) y el de todos los de un
    proyecto a la vez (:func:`ejecutar_proyecto`, 021:RF-54). Devuelve ``(informe,
    código)`` si el alimentador no se puede calibrar.
    """
    from igea_dgs.ajuste_cabecera import AjusteError, Fija, Objetivo, fijas_de, reparto_inicial, sed_desconectadas
    from igea_dgs.demanda_medida import clave_codigo

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
    comun = dict(cargas=cargas, ambiguas=ambiguas, poblacion_nativa=poblacion_nativa,
                 apagar=apagar, desconectadas=desconectadas, avisos_desc=avisos_desc, kva=kva,
                 kva_origen=kva_origen, objetivo=objetivo, fp_cargas=fp_cargas,
                 fijas_libro=fijas_libro, manuales=manuales)
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
    if plan.get('central'):
        # Spec 021: una central en el troncal; se calibra por zonas (RF-35 a RF-45). Las fijas
        # sobre su transformador se miran antes, también con central: en NA205 (2026-10-17)
        # SE50293 pedía 1 392 kW en 125 kVA, el flujo no convergía y no se avisaba (020:RF-1).
        return {**comun, 'central': True, 'fijas': fijas, 'sobre': sobre}
    try:
        reparto = reparto_inicial(objetivo, fijas_libro,
                                  {s: potencia(o) for s, o in cargas.items()}, kva,
                                  fp=fp_cargas)
    except AjusteError as exc:
        return {**informe, 'error': str(exc), 'ambiguas': ambiguas}, 2
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
    return {**comun, 'central': False, 'reparto': reparto, 'fijas': fijas, 'sobre': sobre,
            'antes': antes, 'antes_nativo': antes_nativo, 'antes_apagar': antes_apagar}


def _ejecutar(app, plan: dict, *, simular: bool, cancelado, estado: dict) -> tuple[dict, int]:
    from igea_dgs.ajuste_cabecera import (
        MAX_FLUJOS,
        cuadrar,
        kvar_difference,
    )

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
    if plan.get('tension_fuente_pu') and not simular:                     # 021:RF-61
        informe['consigna_fuente'] = fijar_consigna_de_la_fuente(
            app, float(plan['tension_fuente_pu']), [sin, con])
        escenario = app.GetActiveScenario()
    p = _preparar_alimentador(app, plan, informe, alims=alims, feeder=feeder,
                              simular=simular, cancelado=cancelado)
    if isinstance(p, tuple):
        return p
    if p['central']:
        return _ejecutar_con_central(
            app, plan, informe, alims=alims, elm=elm, feeder=feeder, cargas=p['cargas'],
            kva=p['kva'], kva_origen=p['kva_origen'], fijas_libro=p['fijas_libro'],
            fp_cargas=p['fp_cargas'], apagar=p['apagar'], manuales=p['manuales'],
            ambiguas=p['ambiguas'], sin=sin, con=con, inicial=inicial, escenario=escenario,
            simular=simular, cancelado=cancelado)
    (cargas, ambiguas, poblacion_nativa, apagar, kva, kva_origen, objetivo, fp_cargas,
     manuales, reparto, fijas, sobre, antes, antes_nativo, antes_apagar) = (
        p[k] for k in ('cargas', 'ambiguas', 'poblacion_nativa', 'apagar', 'kva', 'kva_origen',
                       'objetivo', 'fp_cargas', 'manuales', 'reparto', 'fijas', 'sobre',
                       'antes', 'antes_nativo', 'antes_apagar'))

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
            # 014:RF-31 a RF-34: y lo demás hecho en «Sin proyecto», como los bancos a su
            # máxima capacidad (015:RF-66) o uno creado a mano.
            informe['sin_a_con'] = sin_a_con_proyecto(app, casos_del_proyecto(app))
            informe['avisos'] += informe['sin_a_con']['avisos']
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
        with _centrales_apagadas(app):                                  # 015:RF-37
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
                with _centrales_apagadas(app):
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


def ejecutar_proyecto(app, planes: list[dict], *, simular: bool = False,
                      cancelado=lambda: False) -> list[tuple[dict, int]]:
    """El ajuste de los alimentadores de un proyecto, todos a la vez (021:RF-54 a RF-60).

    El usuario, el 2026-10-17, al ir a aplicar NA203 y después NA205: «la calibración se
    debe hacer por proyecto en DIgSILENT; si es un alimentador se hace de ese y dos o más
    se hacen de todas según el proyecto, no de forma independiente». Comparten la red
    (la SET, la central de NA205, los enlaces): cuadrar uno y después otro deja al primero
    con lo que movió el segundo. Con un plan, o al simular (no hay flujos), cada uno como
    siempre (RF-60). Devuelve un ``(informe, código)`` por plan, en su orden.
    """
    bancos = any(p.get('completar_bancos') for p in planes)            # 021:RF-64
    barra = any(p.get('barra_set') for p in planes)                     # 022:RF-41b
    if simular or (len(planes) == 1 and not bancos and not barra):
        return [ejecutar(app, p, simular=simular, cancelado=cancelado) for p in planes]
    estado = {'apartadas': []}
    try:
        if bancos:
            return _con_bancos_que_faltan(app, planes, cancelado=cancelado, estado=estado)
        return _ejecutar_proyecto(app, planes, cancelado=cancelado, estado=estado)
    finally:
        _devolver_cargas_nuevas(app, estado)


def _deficit(inf: dict, plan: dict) -> tuple[float | None, float | None]:
    """(kVAR de la red, kVAR medido) del alimentador tras un cuadre (021:RF-64)."""
    zonas = inf.get('zonas') or {}
    if plan.get('central'):
        m = (plan['central'] or {}).get('maxima') or {}
        red = (None if zonas.get('arriba_kvar') is None or zonas.get('abajo_kvar') is None
               else zonas['arriba_kvar'] + zonas['abajo_kvar'])
        medido = (None if m.get('arriba_kvar') is None or m.get('abajo_kvar') is None
                  else m['arriba_kvar'] + m['abajo_kvar'])
        return red, medido
    return (inf.get('cabecera') or {}).get('kvar'), (plan.get('objetivo') or {}).get('kvar')


def _cuadro_en_kw(inf: dict, plan: dict) -> bool:
    """Si el alimentador quedó en su objetivo de kW tras la primera pasada (021:RF-64)."""
    tol = float(plan.get('tolerancia', 0.01))
    zonas = inf.get('zonas') or {}
    if plan.get('central'):
        pares = [(zonas.get('arriba_kw'), zonas.get('arriba_objetivo_kw')),
                 (zonas.get('abajo_kw'), zonas.get('abajo_objetivo_kw'))]
        return all(m is not None and o and abs(m - o) <= tol * abs(o) for m, o in pares)
    desvio = (inf.get('desvio') or {}).get('kw')
    return desvio is not None and abs(desvio) <= tol


def barras_para_bancos(red, cabecera: str, n: int) -> list[str]:
    """Las barras de la troncal más cercanas a 2k/(2n+1) de su largo (021:RF-66); una barra
    no se repite."""
    from igea_dgs.ajuste_cabecera import distancias_de_bancos
    from igea_dgs.troncal import troncal as troncal_de

    t = troncal_de(red, cabecera)
    tramos = red.por_nombre()
    puntos, d, actual = [], 0.0, cabecera
    for nombre in t.tramos:
        tramo = tramos[nombre]
        actual = tramo.hasta if tramo.desde == actual else tramo.desde
        d += tramo.largo_m
        puntos.append((d, actual))
    out: list[str] = []
    for objetivo in distancias_de_bancos(t.largo_m, n):
        libres = [(abs(x - objetivo), b) for x, b in puntos if b not in out]
        if libres:
            out.append(min(libres)[1])
    return out


def poner_bancos(app, alims, sin, base, con, pedidos: dict[str, tuple[int, float]]) -> list[dict]:
    """Los bancos que faltan, en la troncal de cada alimentador (021:RF-66, RF-67).

    Se crean en la red con las variaciones de las centrales apagadas, como los
    transformadores (020:RF-17); en servicio en los escenarios de «Sin proyecto» y «Con
    proyecto» y fuera de servicio en el del «Caso base», que sigue como se verificó.
    """
    sin.Activate()
    activas = list(app.GetActiveNetworkVariations() or [])
    centrales = [v for v in activas if v.loc_name.startswith(PREFIJO_CENTRAL)]
    for v in centrales:
        v.Deactivate()
    creados: list[dict] = []
    objetos = []
    try:
        if app.GetRecordingStage() is not None or len(centrales) < len(activas):
            raise RuntimeError('«Sin proyecto» tiene variaciones activas o una etapa grabando: '
                               'los bancos van en la red (020:RF-17).')
        for feeder, (n, kvar) in pedidos.items():
            elm = alims.elm[feeder]
            cab = cabecera_de(elm)
            barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
            for k, nombre in enumerate(barras_para_bancos(leer_red(elm, cab), cab.loc_name, n), 1):
                barra = barras[nombre]
                red = barra.GetParent()
                banco = red.CreateObject('ElmShnt', nombre_libre(red, 'ElmShnt', f'BC_CAL_{feeder}_{k}'))
                cub = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{banco.loc_name}'))
                cub.obj_id, cub.obj_bus = banco, 0
                banco.shtype = 2                               # condensador
                banco.ushnm = float(barra.uknom)
                banco.qcapn = kvar / 1000.0
                banco.ncapx = banco.ncapa = 1
                banco.i_cont, banco.iswitch = 0, 0
                objetos.append(banco.loc_name)
                creados.append({'feeder': feeder, 'banco': banco.loc_name, 'barra': nombre,
                                'kv': float(barra.uknom), 'kvar': kvar})
    finally:
        for v in centrales:
            v.Activate()
    for caso, fuera in ((base, 1), (sin, 0), (con, 0)):
        if caso is None:
            continue
        caso.Activate()
        for o in app.GetCalcRelevantObjects('*.ElmShnt') or []:
            if o.loc_name in objetos:
                o.outserv = fuera
        escenario = app.GetActiveScenario()
        if escenario is not None:
            escenario.Save()
    sin.Activate()
    return creados


def _con_bancos_que_faltan(app, planes: list[dict], *, cancelado, estado: dict) -> list[tuple[dict, int]]:
    """Calibra, pone los bancos que faltan y recalibra, en la misma ejecución (021:RF-64 a RF-68)."""
    from igea_dgs.ajuste_cabecera import bancos_que_faltan, tamano_de_banco

    primera = _ejecutar_proyecto(app, planes, cancelado=cancelado, estado=estado, solo_medir=True)
    pedidos, avisos = {}, []
    proyecto = activar_proyecto(app, planes[0]['project'], planes[0].get('folder'))
    alims = Alimentadores(app, proyecto, [p['feeder'] for p in planes])
    for plan, (inf, _rc) in zip(planes, primera):
        f = plan['feeder']
        if inf.get('error') or alims.elm.get(f) is None:
            continue
        if not _cuadro_en_kw(inf, plan):
            # Solo con el kW del alimentador en su objetivo el kVAR de la red dice lo que
            # falta: en NA205 del TXT (2026-10-18) no cuadraba y puso 10 bancos sin sentido.
            avisos.append(f'{f}: no cuadró en kW en la primera pasada; no se calcula qué '
                          'bancos faltan (021:RF-64).')
            continue
        q_red, q_medido = _deficit(inf, plan)
        cab = cabecera_de(alims.elm[f])
        kv = float(cab.uknom) if cab is not None else None
        por_tension = {float(k): float(v) for k, v in (plan.get('bancos_kvar_por_tension') or {}).items()}
        tamano = tamano_de_banco(por_tension, kv)
        if tamano is None:
            avisos.append(f'{f}: el perfil no trae tamaño de banco para {kv} kV; no se ponen (021:RF-65).')
            continue
        n = bancos_que_faltan(q_red, q_medido, tamano)
        if q_red is None:
            avisos.append(f'{f}: el flujo no convergió en la primera pasada; no se sabe qué falta.')
        elif n:
            pedidos[f] = (n, tamano)
            avisos.append(f'{f}: la red da {q_red:,.0f} kVAR frente a {q_medido:,.0f} medidos: '
                          f'{n} banco(s) de {tamano:g} kvar (021:RF-64, RF-65).')
        else:
            avisos.append(f'{f}: la red da {q_red:,.0f} kVAR frente a {q_medido:,.0f} medidos: '
                          'no falta ningún banco.')
    creados = []
    if pedidos and not cancelado():
        creados = poner_bancos(app, alims, caso_del_sistema(app, 'sin'), caso_del_sistema(app, 'base'),
                               caso_del_sistema(app, 'con'), pedidos)
    # RF-68: la calibración que vale, con los bancos y los ajustes del flujo restituidos.
    segunda = _ejecutar_proyecto(app, planes, cancelado=cancelado, estado=estado)
    for plan, (inf, _rc) in zip(planes, segunda):
        inf['bancos_nuevos'] = [b for b in creados if b['feeder'] == plan['feeder']]
        inf['avisos'] = avisos + inf['avisos']
        cambios = cambios_en_la_red(inf)                                  # RF-69
        if cambios:
            inf['cambios_en_la_red'] = cambios
    return segunda


def _nombre_barra_set(set_codigo: str, kv: float) -> str:
    """El nombre de la barra de SET en el DGS unido por SET (``combine.estructurar``)."""
    from igea_dgs.naming import sufijo_tension

    return f"B_{set_codigo.replace(' ', '')}_{sufijo_tension(kv)}"


def _centrales_de_barra(app, preps: dict, informes: dict) -> None:
    """La central medida en una barra de SET, con su P y Q en el registro de la barra (022:RF-44).

    CT_PEDREG en la barra de 10 kV de Pedregal: un generador estático en esa barra, como la
    central de 021:RF-35. Una vez por barra, aunque la compartan varios alimentadores.
    """
    hechas = set()
    terminales = None
    for f, p in preps.items():
        b = p['plan'].get('barra_set') or {}
        centrales = [c for c in b.get('centrales') or [] if c.get('kw') is not None]
        if not centrales or b.get('clave') in hechas:
            continue
        hechas.add(b.get('clave'))
        if terminales is None:
            terminales = {t.loc_name: t for t in (app.GetCalcRelevantObjects('*.ElmTerm') or [])}
        nombre = _nombre_barra_set(b['set'], float(b['kv']))
        barra = None if b.get('suelta') else terminales.get(nombre)
        if barra is None:
            informes[f]['avisos'].append(f"{b['clave']}: la barra {nombre} no está en el proyecto; "
                                         'su central no se pone (022:RF-44).')
            continue
        for c in centrales:
            hecho = central_en_sin_proyecto(app, barra, nombre.replace('B_', '', 1),
                                            float(c['kw']), float(c.get('kvar') or 0.0))
            for g in preps:
                if (preps[g]['plan'].get('barra_set') or {}).get('clave') == b['clave']:
                    informes[g].setdefault('centrales_de_barra', []).append(
                        {'medidor': c['medidor'], 'kw': c['kw'], 'kvar': c.get('kvar'), **hecho})


def _barras_frente_a_su_medidor(preps: dict, informes: dict) -> None:
    """Lo que dan las cabeceras de cada barra de SET frente a su medidor (022:RF-41b)."""
    por_barra: dict[str, list[str]] = {}
    for f, p in preps.items():
        b = p['plan'].get('barra_set')
        if b:
            por_barra.setdefault(b['clave'], []).append(f)
    for clave, feeders in por_barra.items():
        b = preps[feeders[0]]['plan']['barra_set']
        cabeceras = [(informes[f].get('cabecera') or {}).get('kw') for f in feeders]
        red = sum(cabeceras) if all(x is not None for x in cabeceras) else None
        central = sum(float(c.get('kw') or 0.0) for c in b.get('centrales') or [])
        fila = {'clave': clave, 'fecha': b.get('fecha'), 'medido_kw': b.get('kw'),
                'alimentadores_en_la_barra': b.get('alimentadores'), 'calibrados': feeders,
                'cabeceras_kw': red, 'central_kw': central or None,
                'desvio': (None if red is None or not b.get('kw') else
                           (red - central - float(b['kw'])) / abs(float(b['kw'])))}
        for f in feeders:
            informes[f]['barra_set'] = fila
            if red is not None:
                informes[f]['avisos'].append(
                    f"{clave}: las cabeceras de {', '.join(feeders)} dan {red:,.1f} kW"
                    + (f' menos {central:,.1f} kW de su central' if central else '')
                    + f" frente a {float(b['kw']):,.1f} kW del medidor de barra el {b.get('fecha')}"
                    + ('' if set(feeders) >= set(b.get('alimentadores') or []) else
                       ' (no están todos sus alimentadores)') + ' (022:RF-41b).')


def _clave_zona(feeder: str, zona: str) -> str:
    return f'{feeder}|{zona}'


def _ejecutar_proyecto(app, planes: list[dict], *, cancelado, estado: dict,
                       solo_medir: bool = False) -> list[tuple[dict, int]]:
    """``solo_medir``: cuadra y mide sin guardar nada (la primera pasada de 021:RF-64)."""
    from igea_dgs.ajuste_cabecera import (
        MAX_FLUJOS, ZONAS, AjusteError, Medida, MedidaConjunta, avisos_de_zonas,
        cuadrar_conjunto, kvar_difference, preparar_zonas)

    feeders = [p['feeder'] for p in planes]
    nombre = planes[0]['project']
    informes = {f: {'project': nombre, 'feeder': f, 'modo': 'aplicar', 'avisos': [],
                    'cancelado': False} for f in feeders}
    salida: dict[str, tuple[dict, int]] = {}

    def todos(error: str) -> list[tuple[dict, int]]:
        return [salida.get(f) or ({**informes[f], 'error': error}, 2) for f in feeders]

    if len({p['project'] for p in planes}) > 1 or len(set(feeders)) < len(feeders):
        return todos('los planes no son de un mismo proyecto con alimentadores distintos: '
                     'se calibra un proyecto cada vez (021:RF-54)')
    proyecto = activar_proyecto(app, nombre, planes[0].get('folder'))
    if proyecto is None:
        return todos(f"no existe el proyecto {nombre!r} en la carpeta "
                     f"{planes[0].get('folder')!r} de DIgSILENT")
    alims = Alimentadores(app, proyecto, feeders)
    for f in feeders:
        elm = alims.elm.get(f)
        if elm is None or getattr(elm, 'obj_id', None) is None:
            salida[f] = ({**informes[f], 'error': f'{f} no tiene ElmFeeder con cabecera en el '
                          'proyecto: no se puede medir lo que entra por ella.'}, 2)
    validos = [p for p in planes if p['feeder'] not in salida]
    if not validos:
        return todos('ningún alimentador se puede calibrar')
    # 015:RF-16, RF-17: en «Sin proyecto»; si aún no existe se crea, con todos.
    inicial = app.GetActiveStudyCase()
    sin = caso_del_sistema(app, 'sin')
    if sin is None:
        pedido = {'project': nombre, 'folder': planes[0].get('folder'),
                  'feeders': [p['feeder'] for p in validos]}
        sin_verificar = {}
        for p in validos:
            sin_verificar.update(p.get('caso_base_sin_verificar') or {})
        if any('caso_base_sin_verificar' in p for p in validos):
            pedido['caso_base_sin_verificar'] = sin_verificar
        preparado, rc = preparar_sin(app, pedido)
        if rc:
            return todos(preparado.get('error') or '«Sin proyecto» no se pudo preparar')
        for f in feeders:
            informes[f]['casos_preparados'] = preparado.get('casos')
        sin = caso_del_sistema(app, 'sin')
        inicial = app.GetActiveStudyCase()
    sin.Activate()
    con = caso_del_sistema(app, 'con')
    escenario = app.GetActiveScenario()
    if escenario is None:
        return todos(f"«{NOMBRES['sin']}» no tiene escenario de operación: la calibración se "
                     'graba en él (015:RF-26).')
    apartadas = _apartar_cargas_nuevas(app, estado)
    pu = next((float(p['tension_fuente_pu']) for p in validos if p.get('tension_fuente_pu')), None)
    consigna = fijar_consigna_de_la_fuente(app, pu, [sin, con]) if pu else []   # 021:RF-61
    escenario = app.GetActiveScenario()
    for f in feeders:
        if pu:
            informes[f]['consigna_fuente'] = consigna
    preps: dict[str, dict] = {}
    for plan in validos:
        f = plan['feeder']
        inf = informes[f]
        inf['caso'] = NOMBRES['sin']
        if apartadas:
            inf['cargas_nuevas_apartadas'] = apartadas
            inf['avisos'].append('Cargas nuevas fuera del ajuste mientras se mide (vuelven al '
                                 'terminar): ' + ', '.join(apartadas))
        p = _preparar_alimentador(app, plan, inf, alims=alims, feeder=f, simular=False,
                                  cancelado=cancelado)
        if isinstance(p, tuple):
            salida[f] = p
            continue
        p.update(plan=plan, elm=alims.elm[f], con_manual={m['sed'] for m in p['manuales']})
        if p['central']:
            zc = _preparar_central(app, plan, inf, elm=p['elm'], feeder=f, cargas=p['cargas'],
                                   kva=p['kva'], fijas_libro=p['fijas_libro'],
                                   fp_cargas=p['fp_cargas'], ambiguas=p['ambiguas'])
            if isinstance(zc, tuple):
                salida[f] = zc
                continue
            try:
                zc['repartos'], zc['quietas'] = preparar_zonas(zc['repartos']['arriba'],
                                                               zc['repartos']['abajo'])
            except AjusteError as exc:
                salida[f] = ({**inf, 'error': f'{f} con central: {exc}'}, 2)
                continue
            inf['avisos'] += avisos_de_zonas(zc['quietas'])
            p['zc'] = zc
            p['antes'] = {s: potencia_efectiva(o) for s, o in p['cargas'].items()}
        preps[f] = p
    if not preps:
        return todos('ningún alimentador se puede calibrar')
    fuera = [f for f in feeders if f not in preps]
    for f in preps:
        inf = informes[f]
        inf['calibrado_con'] = [x for x in preps if x != f]                       # RF-59
        if solo_medir:
            inf['avisos'].append('Primera pasada para medir lo que falta: no se guarda.')
        inf['escenario'] = escenario.loc_name
        inf['decision_carga_nativa'] = {'status': 'REQUIERE_DISTRIBUCION',
                                        'accion': 'CUADRAR_EL_PROYECTO', 'bloquea': False}
        inf['avisos'].append('Calibrado a la vez que ' + ', '.join(inf['calibrado_con'])
                             + ', en los mismos flujos de carga (021:RF-54).'
                             if inf['calibrado_con'] else
                             'Único alimentador del proyecto que se pudo calibrar.')
        if fuera:
            inf['avisos'].append('Fuera de la calibración del proyecto (vea su informe): '
                                 + ', '.join(fuera) + ' (021:RF-57).')
    viejos = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or [])
                    if v.loc_name.startswith('Ajuste_'))
    for f, p in preps.items():
        inf = informes[f]
        if viejos:
            inf['variaciones_de_ajustes_previos'] = viejos
            inf['avisos'].append('Ajustes de antes de la spec 015 activos en «Sin proyecto» (no '
                                 'se tocan; la calibración va al escenario): ' + ', '.join(viejos))
        if not p['central']:
            al_maximo = bancos_a_su_maxima_capacidad(alims, f)                    # 015:RF-66
            if al_maximo:
                inf['bancos_puestos_a_maxima'] = al_maximo
                inf['avisos'].append(
                    'Bancos existentes puestos a su máxima capacidad (todos los escalones, en '
                    'servicio): ' + ', '.join(c['banco'] for c in al_maximo) + ' (015:RF-66).')

    # Un factor por alimentador, o por zona si tiene central (RF-55).
    repartos, objetivos, quietas = {}, {}, set()
    for f, p in preps.items():
        if p['central']:
            zc = p['zc']
            for z in ZONAS:
                repartos[_clave_zona(f, z)] = zc['repartos'][z]
                objetivos[_clave_zona(f, z)] = getattr(zc['objetivo'], z)
            quietas |= {_clave_zona(f, z) for z in zc['quietas']}
        else:
            repartos[f], objetivos[f] = p['reparto'], p['objetivo']
    tolerancia = min(float(p['plan'].get('tolerancia', 0.01)) for p in preps.values())
    max_flujos = max(int(p['plan'].get('max_flujos') or MAX_FLUJOS) for p in preps.values())
    remedios = Remedios(app)
    fallos: dict[str, list] = {f: [] for f in preps}
    invalidos: list[str] = []
    res = None
    guardado = False          # el escenario con la calibración válida, guardado
    try:
        # La marca fija o escalable es dato de red (015:RF-37): se escribe con todas las
        # variaciones de las centrales apagadas, para que la de NA203 no caiga en la etapa
        # de la central de NA205, que sigue grabando.
        # También las de las centrales de barra (022:RF-44), que no son de un alimentador.
        for v in list(app.GetActiveNetworkVariations() or []):
            if v.loc_name.startswith(PREFIJO_CENTRAL):
                v.Deactivate()
        for f, p in preps.items():
            if p['central']:
                for z, r in p['zc']['repartos'].items():
                    for sed in r.demandas:
                        p['zc']['zonas'][z][sed].i_scale = 1 if sed in r.base else 0
            else:
                for sed in p['reparto'].demandas:
                    p['cargas'][sed].i_scale = 1 if sed in p['reparto'].base else 0
            for sed, obj in p['apagar'].items():                                   # 008:RF-26
                try:
                    obj.outserv = 1
                except Exception as exc:  # noqa: BLE001 - una SED no tumba el ajuste
                    fallos[f].append({'sed': sed, 'error': f'{type(exc).__name__}: {exc}'})
        desc = {f: list(x) for f, x in fallos.items()}
        for f, p in preps.items():
            if p['central']:
                o = p['zc']['objetivo']
                informes[f]['central'].update(central_en_sin_proyecto(       # 021:RF-35, RF-36
                    app, p['zc']['barra'], f, o.generacion_kw, o.generacion_kvar))
        _centrales_de_barra(app, preps, informes)                        # 022:RF-44

        def flujo(reps):
            # Con la central activa, la carga escrita se grababa entera en su etapa, con la
            # marca escalable de otra pasada: 14 fijas de NA203 en «Central_NA205» (sistema
            # Nasca, 2026-10-18). Se escribe con las centrales apagadas (015:RF-37).
            with _centrales_apagadas(app):
                for f, p in preps.items():
                    if p['central']:
                        zs = p['zc']['zonas']
                        fallos[f] = desc[f] + [x for z in ZONAS for x in escribir_reparto(
                            zs[z], reps[_clave_zona(f, z)], p['con_manual'])]
                    else:
                        fallos[f] = desc[f] + escribir_reparto(p['cargas'], reps[f],
                                                               p['con_manual'])
            rc = app.GetFromStudyCase('ComLdf').Execute()
            if rc != 0 or not app.IsLdfValid():
                return MedidaConjunta(False, motivo=f'el flujo de carga no converge (código {rc})')
            kw, kvar, carga, extra = {}, {}, {}, {}
            for f, p in preps.items():
                cab = leer_cabecera(p['elm'])
                if p['central']:
                    mz = leer_zonas(cab, p['zc']['barra'], p['zc']['parte'].entrada)
                    if not mz.converge:
                        return MedidaConjunta(False, motivo=f'{f}: {mz.motivo}')
                    extra[f] = mz
                    for z in ZONAS:
                        kw[_clave_zona(f, z)] = getattr(mz, f'{z}_kw')
                        kvar[_clave_zona(f, z)] = getattr(mz, f'{z}_kvar')
                    continue
                if not cab.converge:
                    return MedidaConjunta(False, motivo=f'{f}: {cab.motivo}')
                ck, cq = consumo_nativo(p['cargas'])
                if ck is not None and cq is not None:
                    cab = replace(cab, carga_kw=ck, carga_kvar=cq)
                extra[f], kw[f], kvar[f], carga[f] = cab, cab.kw, cab.kvar, cab.carga_kw
            return MedidaConjunta(True, kw=kw, kvar=kvar, carga_kw=carga, extra=extra)

        res = cuadrar_conjunto(repartos, objetivos, flujo, quietas=quietas,
                               tolerancia=tolerancia, max_flujos=max_flujos,
                               remedio=remedios.aplicar, cancelado=cancelado,
                               progreso=lambda n, m, t: print(f'  {t}'))
        medidas = res.medida.extra if res.medida is not None and res.medida.converge else {}
        reps = res.repartos or {}
        fallido = next((h for h in res.historial if not h['converge']), None)
        for f, p in preps.items():
            inf = informes[f]
            inf.update(cuadrado=res.cuadrado, motivo=res.motivo or None,
                       cancelado=res.cancelado, flujos=res.flujos, remedios=res.remedios,
                       historial=res.historial, fallos=list(fallos[f]))
            if p['central']:
                ok = _cerrar_central_en_proyecto(app, f, p, inf, reps, medidas.get(f), res,
                                                 tolerancia, Medida)
            else:
                ok = _cerrar_alimentador_en_proyecto(app, alims, f, p, inf, reps.get(f),
                                                     medidas.get(f), res, tolerancia,
                                                     fallido, kvar_difference)
            if not ok:
                invalidos.append(f)
        if invalidos:
            # Una calibración del proyecto: si lo que consume una no es lo escrito, no vale
            # para ninguno y las cargas vuelven a como estaban (015:RF-49).
            for f, p in preps.items():
                inf = informes[f]
                inf['cuadrado'] = False
                if f not in invalidos:
                    inf['status'] = 'FALLO_VALIDACION_NATIVA_EN_EL_PROYECTO'
                    inf['avisos'].append('La calibración del proyecto no es válida por '
                                         + ', '.join(invalidos) + ': vuelve a como estaba.')
                if not p['central']:
                    with _centrales_apagadas(app):
                        _restaurar_cargas(p['cargas'], p['antes_nativo'], p['apagar'],
                                      p['antes_apagar'])
                    inf['calibracion_revertida'] = True
        if res.repartos is not None and not invalidos and not solo_medir:
            escenario.Save()
            guardado = res.cuadrado
            for f, p in preps.items():
                informes[f]['escenarios'] = [{'escenario': escenario.loc_name,
                                              'cargas': len(p['cargas']) - len(p['con_manual']),
                                              'fallos': []}]
            if con is not None:
                # 014:RF-31: lo hecho a mano en «Sin proyecto», también en «Con proyecto».
                sincronia = sin_a_con_proyecto(app, casos_del_proyecto(app))
                # 014:RF-4: «Con proyecto» con la misma demanda y las mismas centrales.
                con.Activate()
                esc_con = app.GetActiveScenario()
                fallos_con = {f: [] for f in preps}
                if esc_con is not None:
                    gens = {o.loc_name: o for o in (app.GetCalcRelevantObjects('*.ElmGenstat') or [])}
                    for f, p in preps.items():
                        if p['central']:
                            zs = p['zc']['zonas']
                            with _centrales_apagadas(app):              # 015:RF-37
                                fallos_con[f] = [x for z in ZONAS for x in escribir_reparto(
                                    zs[z], reps[_clave_zona(f, z)], p['con_manual'])]
                            o = p['zc']['objetivo']
                            gen = gens.get(informes[f]['central'].get('generador'))
                            if gen is not None:
                                gen.pgini = o.generacion_kw / 1000.0
                                gen.qgini = o.generacion_kvar / 1000.0
                            else:
                                informes[f]['avisos'].append(
                                    '«Con proyecto» no tiene la central: active su variación '
                                    f"{informes[f]['central'].get('variacion')}.")
                        else:
                            with _centrales_apagadas(app):              # 015:RF-37
                                fallos_con[f] = escribir_reparto(p['cargas'], reps[f],
                                                                 p['con_manual'])
                        for obj in p['apagar'].values():
                            obj.outserv = 1
                    esc_con.Save()
                for f, p in preps.items():
                    inf = informes[f]
                    inf['sin_a_con'] = sincronia
                    inf['avisos'] += sincronia['avisos']
                    if esc_con is not None:
                        inf['escenarios'].append({'escenario': esc_con.loc_name,
                                                  'cargas': len(p['cargas']) - len(p['con_manual']),
                                                  'fallos': fallos_con[f]})
                        inf['fallos'] += fallos_con[f]
                sin.Activate()
    finally:
        # 015:RF-46: un solo ComLdf para el proyecto; sus ajustes se quedan si cuadró.
        if remedios.originales and guardado:
            aplicados = remedios.aplicados()
            if con is not None:
                con.Activate()
                remedios.aplicar_en(app.GetFromStudyCase('ComLdf'), aplicados)
            for f in preps:
                informes[f]['ajustes_del_flujo_conservados'] = aplicados
                informes[f]['avisos'].append(
                    'Ajustes del flujo de carga que se quedan en «Sin proyecto»'
                    + (' y «Con proyecto»' if con is not None else '') + ' para que converja: '
                    + ', '.join(f'{k}={v}' for k, v in aplicados.items()) + ' (015:RF-46).')
        else:
            restituidos = remedios.restituir()
            if restituidos:
                for f in preps:
                    informes[f]['ajustes_restituidos'] = restituidos
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    _barras_frente_a_su_medidor(preps, informes)                        # 022:RF-41b
    for f in preps:
        inf = informes[f]
        salida[f] = (inf, 0 if inf.get('cuadrado') and not inf.get('fallos') else 2)
    for inf, _rc in salida.values():
        cambios = cambios_en_la_red(inf)                                # 020:RF-60
        if cambios:
            inf['cambios_en_la_red'] = cambios
    return [salida[f] for f in feeders]


def _cerrar_alimentador_en_proyecto(app, alims, feeder: str, p: dict, inf: dict, rep, med,
                                    res, tolerancia: float, fallido, kvar_difference) -> bool:
    """El informe de un alimentador sin central tras el cuadre del proyecto (RF-59), como el
    de :func:`_ejecutar`; ``False`` si lo que consumen sus cargas no es lo escrito."""
    objetivo = p['objetivo']
    inf['medicion_cabecera'] = detalle_cabecera(p['elm'])
    inf['bancos'] = bancos_instalados(alims, feeder)                               # 015:RF-60
    inf.update(criterio_cuadre='KW_ONLY', solo_kw=True,
               reparto_solo_kw=(rep or p['reparto']).solo_kw)
    if med is not None:
        p_cargas = med.carga_kw if med.carga_kw is not None else rep.totales()[0]
        q_cargas = med.carga_kvar if med.carga_kvar is not None else rep.totales()[1]
        q_audit = kvar_difference(med, objetivo, tolerancia)
        inf.update(
            cabecera={'kw': med.kw, 'kvar': med.kvar},
            perdidas={'kw': med.kw - p_cargas,
                      'kvar': med.kvar - q_cargas if med.kvar is not None else None},
            desvio={'kw': res.desvio(feeder), 'kvar': q_audit['diferencia_relativa']},
            consumo_cargas_efectivo=({'kw': med.carga_kw, 'kvar': med.carga_kvar}
                                     if med.carga_kw is not None else None),
            perdidas_de=('RESULTADOS_CARGAS_NATIVAS' if med.carga_kw is not None
                         else 'ENTRADAS_NOMINALES'))
        if res.cuadrado:
            inf['status'] = q_audit['status']
            inf['kvar_no_bloqueante'] = q_audit
            if q_audit['status'] == 'AVISO_KVAR':
                inf['avisos'].append(
                    'AVISO_KVAR: ajuste aceptado por kW; la red nativa DIgSILENT resulta '
                    f"{q_audit['red_nativa_kvar']:,.2f} kVAR frente a {objetivo.kvar:,.2f} kVAR. "
                    'La diferencia reactiva se informa y no bloquea.')
    if not res.cuadrado:
        inf['status'] = 'NO_CONVERGE' if med is None else 'VIOLACION_FISICA'
        inf['avisos'].append(f'NO cumple el {tolerancia:.1%} en todo el proyecto: {res.motivo}. '
                             'El escenario queda con el último reparto común que convergió.')
    valido = True
    if rep is not None and med is not None:
        validacion, _ = validar_cargas_nativas(
            p['cargas'], rep, med, objetivo, tolerancia, ambiguas=p['ambiguas'],
            apagar=p['apagar'], ajustes_flujo=ajustes_del_flujo(app),
            fp_escaladas=None if rep.todo_escala else (p['fp_cargas'] or objetivo.fp))
        inf['validacion_posterior_nativa'] = validacion
        if res.cuadrado and not validacion['correcta']:
            valido = False
            inf['status'] = 'FALLO_VALIDACION_NATIVA'
            inf['resultado_carga_nativa'] = {'status': 'FALLO_VALIDACION_NATIVA', 'bloquea': True}
            aviso = aviso_consumo_fisico(validacion, res.historial,
                                         inf.get('fijas_sobre_su_transformador'), feeder)
            if aviso:
                inf['avisos'].append(aviso)
            inf['fallos'].extend({'sed': x.get('sed'), 'error': f"validación nativa: {x.get('tipo')}",
                                  'detalle': x} for x in validacion['fallos'])
        elif res.cuadrado and not inf['fallos']:
            inf['resultado_carga_nativa'] = {'status': 'APLICADO_Y_VALIDADO', 'bloquea': False}
    if rep is not None:
        inf['sed'] = _por_sed(rep, p['cargas'], p['kva_origen'], p['antes'], p['fijas'])
        despues = _foto_cargas_nativas(p['cargas'])
        inf['relectura_cargas_nativas'] = {
            'status': ('FALLO_VALIDACION_NATIVA' if not valido else
                       'VERIFICADO_PERSISTENCIA' if not inf['fallos'] else 'AVISO_RELECTURA'),
            'antes': p['antes_nativo'], 'despues': despues, 'cantidad': len(despues),
            'poblacion': p['poblacion_nativa']}
    if fallido is not None or not res.cuadrado:
        a = (fallido or {}).get('a', {}).get(feeder)
        inf['diagnostico'] = diagnostico(alims, feeder, p['cargas'], p['kva'],
                                         p['reparto'].con_factores(a) if a is not None else None)
    if p['sobre'] and (not valido or not res.cuadrado):
        inf['sobrecarga_causa_probable'] = True
        inf['avisos'].append(aviso_sobrecarga(p['sobre']))
    cambiados = (inf.get('transformadores_implementados') or {}).get('cambios') or []
    if cambiados:
        inf['resultado_transformadores'] = resultado_transformadores(
            cambiados, p['sobre'], p['fijas'], p['cargas'],
            p['plan'].get('transformadores_sed') or {},
            calibracion_valida=bool(res.cuadrado and valido),
            validacion=inf.get('validacion_posterior_nativa'), remedios=res.remedios,
            motivo=res.motivo)
        if inf['resultado_transformadores']['status'] != 'VALIDO':
            inf['avisos'].append(inf['resultado_transformadores']['aviso'])
    return valido


def _cerrar_central_en_proyecto(app, feeder: str, p: dict, inf: dict, reps: dict, mz, res,
                                tolerancia: float, Medida) -> bool:
    """El informe de un alimentador con central tras el cuadre del proyecto (RF-59), como
    el de :func:`_ejecutar_con_central`; ``False`` si una zona no consume lo escrito."""
    zc = p['zc']
    objetivo = zc['objetivo']
    rep = {z: reps.get(_clave_zona(feeder, z)) for z in ('arriba', 'abajo')}
    inf['zonas'] = {
        'factor_arriba': rep['arriba'].a if rep['arriba'] else None,
        'factor_abajo': rep['abajo'].a if rep['abajo'] else None,
        'arriba_kw': mz.arriba_kw if mz else None, 'arriba_objetivo_kw': objetivo.arriba.kw,
        'abajo_kw': mz.abajo_kw if mz else None, 'abajo_objetivo_kw': objetivo.abajo.kw,
        'cabecera_calculada_kw': mz.cabecera_kw if mz else None,
        'arriba_kvar': mz.arriba_kvar if mz else None, 'abajo_kvar': mz.abajo_kvar if mz else None,
        'cabecera_medida_kw': objetivo.cabecera_kw, 'generacion_kw': objetivo.generacion_kw,
        'generacion_kvar': objetivo.generacion_kvar,
        'zonas_ajustadas': [z for z in ('arriba', 'abajo')
                            if _clave_zona(feeder, z) in res.ajustables]}
    inf['cabecera'] = {'kw': mz.cabecera_kw, 'kvar': mz.cabecera_kvar} if mz else None
    if mz is not None and objetivo.cabecera_kw is not None:
        inf['avisos'].append(
            f'Cabecera calculada {mz.cabecera_kw:,.1f} kW frente a {objetivo.cabecera_kw:,.1f} kW '
            f'medidos el {objetivo.fecha}, con la central dando {objetivo.generacion_kw:,.1f} kW '
            '(021:RF-44).')
    validaciones = {}
    if mz is not None:
        for z, kw, kvar, obj_z in (('arriba', mz.arriba_kw, mz.arriba_kvar, objetivo.arriba),
                                   ('abajo', mz.abajo_kw, mz.abajo_kvar, objetivo.abajo)):
            if rep[z] is None or _clave_zona(feeder, z) not in res.ajustables:
                continue
            validaciones[z], _ = validar_cargas_nativas(
                zc['zonas'][z], rep[z], Medida(True, kw, kvar), obj_z, tolerancia,
                apagar=p['apagar'], ajustes_flujo=ajustes_del_flujo(app),
                fp_escaladas=None if rep[z].todo_escala else (p['fp_cargas'] or obj_z.fp))
    inf['validacion_posterior_nativa'] = validaciones
    invalida = [z for z, v in validaciones.items() if not v['correcta']]
    if res.cuadrado and invalida:
        inf['status'] = 'FALLO_VALIDACION_NATIVA'
        inf['avisos'].append('La validación de lo que consumen las cargas no es correcta en la '
                             'zona ' + ', '.join(invalida) + '.')
    elif not res.cuadrado:
        inf['status'] = 'NO_CONVERGE' if mz is None else 'VIOLACION_FISICA'
        inf['avisos'].append(f'NO cumple el {tolerancia:.1%} en todo el proyecto: {res.motivo}.')
    else:
        inf['status'] = 'OK'
    if rep['arriba'] is not None and rep['abajo'] is not None:
        inf['sed'] = (_por_sed(rep['arriba'], zc['zonas']['arriba'], p['kva_origen'], p['antes'], zc['fijas'])
                      + _por_sed(rep['abajo'], zc['zonas']['abajo'], p['kva_origen'], p['antes'], zc['fijas']))
    return not (res.cuadrado and invalida)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Ajuste de las demandas a la máxima de cabecera')
    # 021:RF-54: varios ``--plan`` (uno por alimentador del proyecto, cada uno con su
    # ``--output-json`` en el mismo orden) se calibran a la vez.
    p.add_argument('--plan', required=True, action='append')
    p.add_argument('--output-json', required=True, action='append')
    p.add_argument('--simular', action='store_true', help='Reparto sin escribir (RF-20)')
    p.add_argument('--cancel-file', help='Si aparece, termina el flujo en curso (RF-22)')
    args = p.parse_args(argv)
    if len(args.plan) != len(args.output_json):
        p.error('un --output-json por cada --plan, en el mismo orden')

    def escribir(ruta, informe) -> None:
        Path(ruta).write_text(json.dumps(informe, indent=2, ensure_ascii=False, default=str)
                              + '\n', encoding='utf-8')

    planes, salidas, codigos = [], [], []
    for ruta_plan, ruta_salida in zip(args.plan, args.output_json):
        plan = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
        blocked = native_action_block_report(plan, 'ajuste')
        if blocked:
            escribir(ruta_salida, blocked)
            print(blocked['error'])
            codigos.append(2)
            continue
        planes.append(plan)
        salidas.append(ruta_salida)
    if not planes:
        return max(codigos)
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
        resultados = ejecutar_proyecto(app, planes, simular=args.simular,
                                       cancelado=lambda: bool(flag and flag.exists()))
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        # «Ajustar SI213 a la máxima» (2026-10-10) acabó con el código 1 y sin informe: la
        # web solo podía decir «vea el Registro». La traza sigue yendo al Registro.
        traceback.print_exc()
        resultados = [(error_inesperado(plan, args.simular, exc), 1) for plan in planes]
    for ruta, (informe, codigo) in zip(salidas, resultados):
        escribir(ruta, informe)
        print(f'Informe: {ruta}')
        codigos.append(codigo)
    return max(codigos)


if __name__ == '__main__':
    raise SystemExit(main())
