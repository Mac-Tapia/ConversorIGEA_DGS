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

Todo se graba en una variación nueva (RF-19), como las cargas de la spec 004, y el
resultado también en el escenario de operación (RF-27, RF-28): con el escenario activo,
la potencia de las cargas que manda es la suya, no la de la variación.

Spec 011: si el proyecto ya tiene los casos «Caso base», «Sin proyecto» y «Con proyecto»,
el ajuste se hace en «Sin proyecto» (RF-51), los ajustes anteriores del alimentador se
desactivan allí y en «Con proyecto», y la variación nueva queda activa en los dos (RF-54).
El «Caso base» no se toca (RF-53). Cada carga queda marcada en su variación como fija
(cliente importante, no escala) o escalable (repartida por kVA), para que ningún estudio
que escale cargas mueva la demanda medida de los clientes (RF-18, RF-19).

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
    crear_variacion,
    detalle_cabecera,
    error_inesperado,
    error_relectura,
    escribir_carga,
    grabar_en_escenario,
    medir_cabecera,
    potencia,
)
from casos_pf import NOMBRES, ajustes_de, tres_casos

from igea_dgs.native_action import native_action_block_report

#: Tensión (p.u.) por debajo de la cual una barra cuenta como caída en el diagnóstico.
TENSION_CAIDA = 0.5
#: Elementos sobrecargados que se listan en el diagnóstico, de más a menos cargado.
MAX_SOBRECARGAS = 20


# =========================================================================== lectura
def kva_en_pf(carga) -> float | None:
    """kVA de los transformadores conectados a la barra de la carga, sumados.

    En los DGS del conversor la carga de la SED cuelga de la barra de baja de su
    transformador; con varios transformadores en paralelo en la misma barra, la SED
    tiene la suma.
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
            total += strn * 1000.0
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
def al_escenario(app, informe, casos, escenario, elm, filas, apagar, medida, tolerancia) -> list:
    """El resultado también en los escenarios y la cabecera con ellos (RF-27 a RF-30).

    SI213 (2026-10-12) cuadró a 1.621,8 kW con el escenario apagado y «Verificar la
    convergencia», con el «Operation Scenario» restaurado, medía 229,2 kW: el escenario
    guardaba las demandas de antes. El escenario base es la red ajustada (usuario), y
    con los tres casos se graba en los tres: «Sin proyecto» y «Con proyecto» son copias.
    Devuelve los fallos de escritura.
    """
    grabados = []
    if escenario is not None:
        escenario.Activate()
        grabados.append(grabar_en_escenario(app, filas, apagar))
    if casos:
        donde = app.GetActiveStudyCase()
        for rol in ('con', 'base'):
            casos[rol].Activate()
            grabados.append(grabar_en_escenario(app, filas, apagar))
        donde.Activate()
    grabados = [g for g in grabados if g]
    informe['escenarios'] = grabados
    if escenario is not None:
        con_esc = medir_cabecera(app, elm)
        if not con_esc.converge:
            informe['avisos'].append(f'Con el escenario {escenario.loc_name} activo, '
                                     f'{con_esc.motivo}.')
        else:
            informe['cabecera_con_escenario'] = {'kw': con_esc.kw, 'kvar': con_esc.kvar}
            if medida is not None and medida.converge and any(
                    abs(a - b) > tolerancia * max(abs(b), 1e-9)
                    for a, b in ((con_esc.kw, medida.kw), (con_esc.kvar, medida.kvar))):
                informe['avisos'].append(
                    f'Con el escenario {escenario.loc_name} activo la cabecera da '
                    f'{con_esc.kw:.1f} kW y {con_esc.kvar:.1f} kVAR, no los {medida.kw:.1f} kW '
                    f'y {medida.kvar:.1f} kVAR del ajuste: el escenario no tomó las demandas.')
    return [f for g in grabados for f in g['fallos']]


# =========================================================================== orquestación
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


def _foto_cargas_nativas(cargas: dict) -> list[dict]:
    """Relectura efectiva P/Q/FP, estado y bandera de escala de cada carga SED."""
    fotos = []
    for sed, obj in sorted(cargas.items()):
        p_kw, q_kvar = potencia(obj)
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


def _cerca(actual: float, esperado: float, *, rel: float = 1e-4,
           abs_: float = 1e-3) -> bool:
    """Comparación de relectura en kW/kVAR, más estricta que el cuadre de cabecera."""
    return math.isclose(actual, esperado, rel_tol=rel, abs_tol=abs_)


def validar_cargas_nativas(cargas: dict, reparto, medida, objetivo, tolerancia: float,
                           *, ambiguas=(), apagar=None) -> tuple[dict, object | None]:
    """Demuestra si el reparto ya existe en la red efectiva sin escribirla.

    Las fijas deben coincidir con su P/Q calculada. Las escalables no se comparan contra
    el reparto *inicial* —el cuadre cambia su factor para cubrir pérdidas—, sino que deben
    compartir un mismo factor P/base y Q/base. Finalmente el flujo nativo debe converger y
    la cabecera debe cumplir el objetivo. Devuelve también el reparto reconstruido desde
    la relectura, para informar exactamente lo que ya existe.
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
    for sed, demanda in reparto.demandas.items():
        obj = cargas.get(sed)
        if obj is None:
            fallos.append({'tipo': 'SED_FALTANTE', 'sed': sed})
            continue
        p_kw, q_kvar = potencia(obj)
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
        detalles.append({
            'sed': sed, 'clase': 'ESCALABLE' if escalable else 'FIJA',
            'p_kw': p_kw, 'q_kvar': q_kvar, 'i_scale': actual_i_scale,
            'correcta': not errores, 'errores': errores,
        })
        if errores:
            fallos.append({'tipo': 'CARGA_INCORRECTA', 'sed': sed, 'errores': errores})

    for sed, obj in apagar.items():
        if int(getattr(obj, 'outserv', 0) or 0) != 1:
            fallos.append({'tipo': 'SED_DESCONECTADA_ACTIVA', 'sed': sed})

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
        total_p = sum(potencia(obj)[0] for obj in cargas.values())
        total_q = sum(potencia(obj)[1] for obj in cargas.values())
        consumo_origen = 'ENTRADAS_CARGAS_NATIVAS'
    if medida.converge and medida.kw is not None:
        ruido = max(0.1, abs(objetivo.kw) * 1e-4)
        if medida.kw - total_p < -ruido:
            fallos.append({'tipo': 'PERDIDAS_ACTIVAS_NEGATIVAS',
                           'cabecera_kw': medida.kw, 'cargas_kw': total_p})

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
        'cabecera': ({'kw': medida.kw, 'kvar': medida.kvar}
                     if medida.converge else None),
    }, reconstruido


def ejecutar(app, plan: dict, *, simular: bool = False, cancelado=lambda: False) -> tuple[dict, int]:
    """Simula o aplica el ajuste. Devuelve (informe, código de salida)."""
    from igea_dgs.ajuste_cabecera import (
        MAX_FLUJOS,
        AjusteError,
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
    cargas, ambiguas = cargas_sed(alims, feeder)
    poblacion_nativa = dict(getattr(cargas_sed, 'last_audit', {}) or {
        'algoritmo': 'SELECCION_NATIVA_DEL_ALIMENTADOR',
        'cargas_activas_unicas': len(cargas), 'nombres_ambiguos': len(ambiguas),
    })
    # RF-26: la SED cuyos clientes desmarcó todos el operador sale del reparto y su carga
    # queda fuera de servicio en la variación; repartirle por kVA sería volver a cargarla.
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
    fijas_libro = fijas_de(plan.get('clientes') or [], objetivo)
    try:
        reparto = reparto_inicial(objetivo, fijas_libro, kva)
    except AjusteError as exc:
        return {**informe, 'error': str(exc), 'ambiguas': ambiguas}, 2
    fijas = {s: f for f in fijas_libro.values() for s in cargas
             if clave_codigo(s) == clave_codigo(f.sed)}
    antes = {s: potencia(o) for s, o in cargas.items()}
    antes_nativo = _foto_cargas_nativas(cargas)
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
        informe['sed'] = _por_sed(reparto, cargas, kva_origen, antes, fijas)
        informe['totales_sin_perdidas'] = dict(zip(('kw', 'kvar'), reparto.totales()))
        return informe, 0

    casos = tres_casos(app)
    inicial = app.GetActiveStudyCase()
    if casos:
        casos['sin'].Activate()
        informe['caso'] = NOMBRES['sin']
    # Idempotencia nativa: antes de desactivar ajustes, crear una variación o escribir una
    # carga, se demuestra si el estado efectivo ya contiene el mismo reparto y cuadre.
    ajustes = ajustes_de(app, feeder)
    medida_previa = medir_cabecera(app, elm)
    validacion_previa, reparto_nativo = validar_cargas_nativas(
        cargas, reparto, medida_previa, objetivo, float(informe['tolerancia']),
        ambiguas=ambiguas, apagar=apagar,
    )
    variacion_reutilizada = None
    intentos_reutilizacion = []
    escenario_previo = app.GetActiveScenario()
    variaciones_activas_previas = list(app.GetActiveNetworkVariations() or [])
    # Al reabrir PowerFactory la variacion puede seguir persistida pero inactiva. Antes
    # de redistribuir, se activa cada ajuste existente (mas reciente primero) y se somete
    # a exactamente la misma relectura P/Q/i_scale + ComLdf. Existir por nombre no basta.
    if not validacion_previa['correcta'] and ajustes:
        if escenario_previo is not None:
            escenario_previo.Deactivate(0)
        for candidata in reversed(ajustes):
            for ajuste in ajustes:
                ajuste.Deactivate()
            candidata.Activate()
            medida_candidata = medir_cabecera(app, elm)
            validacion_candidata, reparto_candidato = validar_cargas_nativas(
                cargas, reparto, medida_candidata, objetivo, float(informe['tolerancia']),
                ambiguas=ambiguas, apagar=apagar,
            )
            intentos_reutilizacion.append({
                'variacion': candidata.loc_name,
                'correcta': validacion_candidata['correcta'],
                'fallos': validacion_candidata['fallos'],
            })
            if validacion_candidata['correcta'] and reparto_candidato is not None:
                variacion_reutilizada = candidata
                medida_previa = medida_candidata
                validacion_previa = validacion_candidata
                reparto_nativo = reparto_candidato
                break
        if variacion_reutilizada is None:
            for ajuste in ajustes:
                ajuste.Deactivate()
            for anterior in variaciones_activas_previas:
                anterior.Activate()
            if escenario_previo is not None:
                escenario_previo.Activate()
    informe['validacion_previa_nativa'] = validacion_previa
    if intentos_reutilizacion:
        informe['reutilizacion_variaciones_existentes'] = intentos_reutilizacion
    if validacion_previa['correcta'] and reparto_nativo is not None:
        fotos = _foto_cargas_nativas(cargas)
        p_cargas, q_cargas = reparto_nativo.totales()
        e_kw = ((medida_previa.kw - objetivo.kw) / abs(objetivo.kw)
                if objetivo.kw else medida_previa.kw - objetivo.kw)
        e_kvar = ((medida_previa.kvar - objetivo.kvar) /
                  (abs(objetivo.kvar) if objetivo.kvar else abs(objetivo.kw) or 1.0)
                  if medida_previa.kvar is not None else None)
        q_audit = kvar_difference(medida_previa, objetivo, float(informe['tolerancia']))
        informe.update(
            decision_carga_nativa={
                'status': 'YA_CARGADO_VALIDADO', 'accion': 'NO_REDISTRIBUIR',
                'bloquea': False,
                'origen': ('VARIACION_EXISTENTE_REACTIVADA'
                           if variacion_reutilizada is not None else 'ESTADO_EFECTIVO'),
            },
            cuadrado=True, status=q_audit['status'], kvar_no_bloqueante=q_audit,
            cabecera={'kw': medida_previa.kw, 'kvar': medida_previa.kvar},
            medicion_cabecera=detalle_cabecera(elm), flujos=1, fallos=[],
            historial=[{'flujo': 1, 'origen': 'RELECTURA_PREVIA',
                        'converge': True, 'kw': medida_previa.kw,
                        'kvar': medida_previa.kvar}],
            perdidas={'kw': medida_previa.kw - p_cargas,
                      'kvar': (medida_previa.kvar - q_cargas
                               if medida_previa.kvar is not None else None)},
            desvio={'kw': e_kw, 'kvar': e_kvar},
            criterio_cuadre='KW_ONLY', reparto_solo_kw=reparto_nativo.solo_kw,
            sed=_por_sed(reparto_nativo, cargas, kva_origen, antes, fijas),
            variacion=(variacion_reutilizada.loc_name if variacion_reutilizada is not None
                       else ajustes[-1].loc_name if ajustes else None),
            variacion_reutilizada=(variacion_reutilizada.loc_name
                                   if variacion_reutilizada is not None
                                   else ajustes[-1].loc_name if ajustes else None),
            relectura_cargas_nativas={
                'status': 'VERIFICADO_PERSISTENCIA', 'antes': fotos, 'despues': fotos,
                'cantidad': len(fotos), 'poblacion': poblacion_nativa,
            },
        )
        binding_reread = dict((plan.get('project_binding') or {}).get('native_reread') or {})
        informe['relectura_proyecto_vinculado'] = binding_reread
        informe['relectura_bancos'] = dict(binding_reread.get('capacitor_reread') or {})
        if escenario_previo is not None and app.GetActiveScenario() is None:
            escenario_previo.Activate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
        return informe, 0
    informe['decision_carga_nativa'] = {
        'status': 'REQUIERE_DISTRIBUCION', 'accion': 'DISTRIBUIR_Y_CUADRAR',
        'bloquea': False,
    }
    try:
        variaciones_inicio = list(app.GetActiveNetworkVariations() or [])
    except Exception:  # noqa: BLE001 - versiones antiguas: se restaura lo conocido
        variaciones_inicio = []
    # Un ajuste anterior del mismo alimentador escribiría las mismas cargas: con los dos
    # activos, cuál manda dependería del orden de las etapas. Y se desactivan también sin
    # los tres casos: SI213 (2026-10-12, un solo «Study Case») tenía tres ajustes activos
    # con etapas en la misma fecha, y con varias así PF deja grabando la que ya grababa
    # (manual 16.5), ninguna: el cuarto ajuste no llegó a grabar.
    anteriores = ajustes_de(app, feeder)
    for v in anteriores:
        v.Deactivate()
    escenario = app.GetActiveScenario()
    if escenario is not None:
        escenario.Deactivate(0)
    remedios = Remedios(app)
    fallos: list[dict] = []
    fallos_desc: list[dict] = []
    variacion = None
    fallo_validacion_nativa = False
    try:
        variacion, _etapa = crear_variacion(app, plan['variacion'], plan.get('stamp') or '')
        informe['variacion'] = variacion.loc_name
        # RF-18, RF-19: fija o escalable, en la variación del ajuste. Marcarlo después,
        # al preparar los estudios, lo grabaría en la variación que estuviera grabando.
        for sed in reparto.demandas:
            # ``origen=cliente`` describe de dónde salió la demanda, no si finalmente
            # quedó fija. RF-13 coloca también esas SED en ``reparto.base``.
            cargas[sed].i_scale = 1 if sed in reparto.base else 0
        # RF-26: en la variación, para que volver a marcar el cliente y ajustar de nuevo
        # la deje en servicio al desactivar este ajuste.
        for sed, obj in apagar.items():
            try:
                obj.outserv = 1
            except Exception as exc:  # noqa: BLE001 - una SED no tumba el ajuste
                fallos_desc.append({'sed': sed, 'error': f'{type(exc).__name__}: {exc}'})

        def flujo(rep):
            fallos.clear()
            for sed, d in rep.demandas.items():
                obj = cargas[sed]
                try:
                    escribir_carga(obj, d.kw / 1000.0, d.kvar / 1000.0)
                    error = error_relectura(obj, d.kw / 1000.0, d.kvar / 1000.0)
                except Exception as exc:  # noqa: BLE001 - una SED no tumba el ajuste
                    error = f'{type(exc).__name__}: {exc}'
                if error:
                    fallos.append({'sed': sed, 'error': error})
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
                ambiguas=ambiguas, apagar=apagar,
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
                informe['fallos'].extend({
                    'sed': fallo.get('sed'),
                    'error': f"validación nativa: {fallo.get('tipo')}",
                    'detalle': fallo,
                } for fallo in validacion_posterior['fallos'])
                # Una cabecera cuadrada no compensa una carga que la relectura nativa no
                # conservó. La variación defectuosa no queda disponible para estudios.
                nombre_revertido = getattr(variacion, 'loc_name', None)
                if variacion is not None:
                    try:
                        variacion.Delete()
                        informe['variacion_revertida'] = nombre_revertido
                        variacion = None
                    except Exception as exc:  # noqa: BLE001 - el informe bloquea igualmente
                        informe['fallos'].append({
                            'sed': None,
                            'error': f'no se pudo retirar la variación inválida: '
                                     f'{type(exc).__name__}: {exc}',
                        })
                try:
                    activas = list(app.GetActiveNetworkVariations() or [])
                except Exception:  # noqa: BLE001
                    activas = []
                for activa in activas:
                    if activa not in variaciones_inicio:
                        activa.Deactivate()
                for anterior in variaciones_inicio:
                    anterior.Activate()
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
            binding_reread = dict((plan.get('project_binding') or {}).get('native_reread') or {})
            informe['relectura_proyecto_vinculado'] = binding_reread
            informe['relectura_bancos'] = dict(binding_reread.get('capacitor_reread') or {})
        if any(not h['converge'] for h in res.historial) or not res.cuadrado:
            fallido = next((reparto.con_factores(h['a'], h['b'])
                            for h in res.historial if not h['converge']), None)
            informe['diagnostico'] = diagnostico(alims, feeder, cargas, kva, fallido)
        if res.cancelado:
            informe['avisos'].append('Cancelado: la variación queda con el último reparto '
                                     'que convergió.')
        if not res.cuadrado:
            informe['avisos'].append(
                f'NO cumple el {informe["tolerancia"]:.1%}: {res.motivo}. La variación queda '
                'con el último reparto que convergió.')
        if res.reparto is not None and not fallo_validacion_nativa:
            filas = [(s, cargas[s], d.kw / 1000.0, d.kvar / 1000.0)
                     for s, d in res.reparto.demandas.items()]
            informe['fallos'] += al_escenario(app, informe, casos, escenario, elm, filas,
                                              list(apagar.items()), res.medida,
                                              float(informe['tolerancia']))
    finally:
        restituidos = remedios.restituir()
        if restituidos:
            informe['ajustes_restituidos'] = restituidos
        # También si algo revienta: el escenario del operador no se queda apagado.
        if escenario is not None and app.GetActiveScenario() is None:
            escenario.Activate()
            informe['avisos'].append(
                f'El escenario {escenario.loc_name} vuelve a estar activo: sus demandas '
                'mandan sobre las de la variación mientras esté activo.')
        if casos and not fallo_validacion_nativa:
            # RF-54: las cargas nuevas de «Con proyecto» siguen sobre la red calibrada.
            casos['con'].Activate()
            for v in anteriores:
                v.Deactivate()
            if variacion is not None:
                variacion.Activate()
            if anteriores:
                informe['avisos'].append('Ajustes anteriores desactivados en «Sin proyecto» y '
                                         '«Con proyecto»: ' + ', '.join(v.loc_name for v in anteriores))
        elif anteriores and not fallo_validacion_nativa:
            informe['avisos'].append('Ajustes anteriores desactivados en el caso activo: '
                                     + ', '.join(v.loc_name for v in anteriores))
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
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de DIgSILENT no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: no se pudo conectar a DIgSILENT: {exc}')
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
