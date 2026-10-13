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

Todo se graba en una variación nueva (RF-19), como las cargas de la spec 004.

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
from pathlib import Path

from cargas_pf import (
    Alimentadores, _num, activar_proyecto, crear_variacion, error_inesperado, error_relectura,
    escribir_carga, medir_cabecera, potencia,
)
from casos_pf import NOMBRES, ajustes_de, tres_casos

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


def cargas_sed(alims: Alimentadores, feeder: str) -> tuple[dict, list[dict]]:
    """Carga de cada SED del alimentador por su nombre; las repetidas se dejan fuera."""
    por_nombre: dict[str, list] = {}
    for obj in alims.objetos(feeder, 'ElmLod'):
        if not int(getattr(obj, 'outserv', 0) or 0):
            por_nombre.setdefault(obj.loc_name, []).append(obj)
    unicas = {n: objs[0] for n, objs in por_nombre.items() if len(objs) == 1}
    ambiguas = [{'sed': n, 'motivo': f'{len(objs)} cargas con ese nombre en {feeder}'}
                for n, objs in por_nombre.items() if len(objs) > 1]
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


def ejecutar(app, plan: dict, *, simular: bool = False, cancelado=lambda: False) -> tuple[dict, int]:
    """Simula o aplica el ajuste. Devuelve (informe, código de salida)."""
    from igea_dgs.ajuste_cabecera import (
        MAX_FLUJOS, AjusteError, Objetivo, cuadrar, fijas_de, kvar_difference, reparto_inicial,
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
    cargas, ambiguas = cargas_sed(alims, feeder)
    poblacion_nativa = {
        'algoritmo': 'SELECCION_NATIVA_DEL_ALIMENTADOR',
        'cargas_activas_unicas': len(cargas), 'nombres_ambiguos': len(ambiguas),
    }
    kva, kva_origen = kva_por_sed(cargas, plan.get('kva_entrada') or {})
    objetivo = Objetivo(**plan['objetivo'])
    # Las SED de los clientes se emparejan con las cargas por su código: las fijas toman
    # el nombre de la carga de DIgSILENT.
    fijas_libro = fijas_de(plan.get('clientes') or [], objetivo)
    try:
        reparto = reparto_inicial(objetivo, fijas_libro, kva)
    except AjusteError as exc:
        return {**informe, 'error': str(exc), 'ambiguas': ambiguas}, 2
    from igea_dgs.demanda_medida import clave_codigo
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
                   todo_escala=reparto.todo_escala, solo_kw=reparto.solo_kw)
    informe['avisos'] += reparto.avisos

    if simular:
        informe['sed'] = _por_sed(reparto, cargas, kva_origen, antes, fijas)
        informe['totales_sin_perdidas'] = dict(zip(('kw', 'kvar'), reparto.totales()))
        return informe, 0

    casos = tres_casos(app)
    inicial = app.GetActiveStudyCase()
    anteriores: list = []
    if casos:
        casos['sin'].Activate()
        informe['caso'] = NOMBRES['sin']
        # Un ajuste anterior del mismo alimentador escribiría las mismas cargas: con los
        # dos activos, cuál manda dependería del orden de las etapas.
        anteriores = ajustes_de(app, feeder)
        for v in anteriores:
            v.Deactivate()
    escenario = app.GetActiveScenario()
    if escenario is not None:
        escenario.Deactivate(0)
    remedios = Remedios(app)
    fallos: list[dict] = []
    variacion = None
    try:
        variacion, _etapa = crear_variacion(app, plan['variacion'], plan.get('stamp') or '')
        informe['variacion'] = variacion.loc_name
        # RF-18, RF-19: fija o escalable, en la variación del ajuste. Marcarlo después,
        # al preparar los estudios, lo grabaría en la variación que estuviera grabando.
        for sed, d in reparto.demandas.items():
            cargas[sed].i_scale = 0 if d.origen == 'cliente' else 1

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
            return medir_cabecera(app, elm)

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
            criterio_cuadre='KW_ONLY', solo_kw=True,
            reparto_solo_kw=(res.reparto.solo_kw if res.reparto is not None else
                             reparto.solo_kw),
            fallos=list(fallos),
        )
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
                                  not res.medida.converge else 'NO_CUADRADO_KW')
        if res.reparto is not None:
            informe['sed'] = _por_sed(res.reparto, cargas, kva_origen, antes, fijas)
            despues_nativo = _foto_cargas_nativas(cargas)
            informe['relectura_cargas_nativas'] = {
                'status': 'VERIFICADO_PERSISTENCIA' if not informe['fallos'] else 'AVISO_RELECTURA',
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
        if casos:
            # RF-54: las cargas nuevas de «Con proyecto» siguen sobre la red calibrada.
            casos['con'].Activate()
            for v in anteriores:
                v.Deactivate()
            if variacion is not None:
                variacion.Activate()
            if anteriores:
                informe['avisos'].append('Ajustes anteriores desactivados en «Sin proyecto» y '
                                         '«Con proyecto»: ' + ', '.join(v.loc_name for v in anteriores))
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
