#!/usr/bin/env python
"""Transferencias de carga del operador en DIgSILENT: leerlas y desactivarlas mientras se calibra (spec 098).

CA101 y CHN102 (2026-11-07): el operador pasó parte de CA101 a CHN102 con dos tramos nuevos y dejó abierto el punto
que la unía a CA101. La recalibración, con medidas de antes de la transferencia, contaba en CA101 unas SED cuya
potencia entraba por CHN102 y terminó con pérdidas negativas. Por decisión del usuario, mientras se calibra se abre lo
que el operador añadió para la transferencia y se cierra el punto que abrió, para medir cada alimentador completo, y
al terminar —también si falla o se cancela— todo vuelve a como estaba. Cada cambio se anota en disco antes de hacerse
(como las aperturas de las obras, 081:RF-80): si el proceso muere, la orden siguiente lo deshace.

Lo usan ``tools/ajuste_cabecera_pf.py`` (calibración y recalibración, 098:RF-3 a RF-6) y
``tools/escanear_alimentador_pf.py`` (098:RF-9). Como orden suelta, solo lee:

    python tools/transferencia_operador_pf.py --plan plan.json --output-json transferencias.json

El plan: ``project``, ``folder``, ``feeders``, ``anio_casos`` (opcional), ``tramos_dgs`` y ``abiertos_dgs`` (los del
DGS aceptado). Códigos de salida: 0 bien, 1 error inesperado, 2 proyecto que no existe, 3 API no disponible.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:          # como orden suelta; ``tools/`` lo pone Python al ejecutarla
    sys.path.insert(0, str(RAIZ / 'src'))

from convertersmartgrid.transferencia_operador import (
    CargaRed,
    Rama,
    texto_de_zona,
    transferidas,
    zonas_transferidas,
)

#: Lo que une dos barras en serie: el camino eléctrico pasa por ello (042:RF-44, más los tramos).
CLASES_RAMA = ('ElmLne', 'ElmCoup', 'ElmTr2', 'ElmZpu', 'ElmVoltreg', 'ElmSind')
LADOS = {'ElmTr2': ('bushv', 'buslv')}


def _clave(obj) -> str:
    from cargas_pf import clave_pf

    return clave_pf(obj)


def _todos(app, clase: str) -> list:
    """Los de la clase en la red, también fuera de servicio: el tramo que el operador sacó de servicio no lo da
    ``GetCalcRelevantObjects`` (081:RF-81), y lo que graba una variación activa solo lo da él. Una pasada por clase."""
    vivos = list(app.GetCalcRelevantObjects(f'*.{clase}') or [])
    donde = app.GetProjectFolder('netdat') if hasattr(app, 'GetProjectFolder') else None
    if donde is None:
        return vivos
    vistos = {_clave(o) for o in vivos}
    return vivos + [o for o in (donde.GetContents(f'*.{clase}', 1) or []) if _clave(o) not in vistos]


def _cubiculos(obj, clase: str) -> list:
    return [c for c in (getattr(obj, a, None) for a in LADOS.get(clase, ('bus1', 'bus2'))) if c is not None]


def _interruptores(cubiculos) -> list:
    return [s for c in cubiculos for s in (c.GetContents('*.StaSwitch') or [])]


def _etiqueta(obj) -> str | None:
    from cargas_pf import alimentadores_nativos

    etiquetas = alimentadores_nativos(obj)
    return next(iter(etiquetas)) if len(etiquetas) == 1 else None


def _topologia(alims, alimentadores) -> tuple[dict[str, set[str]], dict[str, str], set[str]]:
    """Por alimentador, sus barras; por carga, quién la alimenta; y las barras de cabecera.

    Del ``ElmFeeder`` tal cual (``crudo``), sin la segunda troncal que añade ``ElmCompleto`` por la etiqueta
    (063:RF-39): eso diría que la carga es de su etiqueta aunque la alimente otro."""
    barras, de_carga, cabeceras = {}, {}, set()
    for f in alimentadores:
        elm = alims.elm.get(f)
        if elm is None:
            continue
        crudo = getattr(elm, 'crudo', elm)
        barras[f] = {_clave(t) for t in (crudo.GetObjs('ElmTerm') or [])}
        for c in crudo.GetObjs('ElmLod') or []:
            de_carga.setdefault(_clave(c), f)
        cab = getattr(getattr(crudo, 'obj_id', None), 'cterm', None)
        if cab is not None:
            cabeceras.add(_clave(cab))
    return barras, de_carga, cabeceras


def leer_transferencias(app, alims, plan: dict, interesan=None) -> tuple[list, dict]:
    """098:RF-1, RF-2: las zonas transferidas por el operador entre alimentadores del proyecto, y los objetos.

    Una pasada por las cargas y, solo si hay alguna transferida, una por cada clase de rama: un proyecto sin
    transferencias no lee nada más. ``interesan``: solo las zonas que salen de o llegan a esos alimentadores.
    """
    from cargas_pf import potencia

    alimentadores = sorted(alims.elm)
    barras, de_carga, cabeceras = _topologia(alims, alimentadores)
    cargas, objetos = [], {}
    for o in app.GetCalcRelevantObjects('*.ElmLod') or []:
        term = getattr(getattr(o, 'bus1', None), 'cterm', None)
        if term is None:
            continue
        k = _clave(o)
        p, q = potencia(o)
        cargas.append(CargaRed(k, o.loc_name, _clave(term), _etiqueta(o), de_carga.get(k), p, q))
        objetos[k] = o
    if not transferidas(cargas, alimentadores):
        return [], objetos
    de_dgs = set(plan.get('tramos_dgs') or []) or None
    abiertos = plan.get('abiertos_dgs')
    abiertos = {k: set(v) for k, v in abiertos.items()} if isinstance(abiertos, dict) else None
    ramas = []
    for clase in CLASES_RAMA:
        for o in _todos(app, clase):
            cubs = _cubiculos(o, clase)
            extremos = [getattr(c, 'cterm', None) for c in cubs]
            if len(extremos) != 2 or any(t is None for t in extremos):
                continue
            sws = _interruptores(cubs)
            cerrada = (not int(getattr(o, 'outserv', 0) or 0)
                       and not (clase == 'ElmCoup' and not int(getattr(o, 'on_off', 1) or 0))
                       and all(int(getattr(s, 'on_off', 1) or 0) for s in sws))
            en_fuente = (o.loc_name in de_dgs) if (clase == 'ElmLne' and de_dgs is not None) else None
            if abiertos is None:
                en_fuente_cerrada = None
            elif clase == 'ElmLne':
                en_fuente_cerrada = not (o.loc_name in abiertos.get('ElmLne', set())
                                         or any(s.loc_name in abiertos.get('StaSwitch', set()) for s in sws))
            elif clase == 'ElmCoup':
                en_fuente_cerrada = o.loc_name not in abiertos.get('ElmCoup', set())
            else:
                en_fuente_cerrada = True
            k = _clave(o)
            objetos[k] = o
            ramas.append(Rama(k, clase, o.loc_name, (_clave(extremos[0]), _clave(extremos[1])), bool(cerrada),
                              en_fuente, en_fuente_cerrada))
    zonas = zonas_transferidas(cargas, ramas, barras, cabeceras)
    if interesan is not None:
        interesan = set(interesan)
        zonas = [z for z in zonas if z.desde in interesan or z.hacia in interesan]
    return zonas, objetos


def equipos_de_las_zonas(app, zonas) -> list[dict[str, list[str]]]:
    """098:RF-9: bancos y generadores de cada zona, que pasaron con ella (CA101: EBC_1, EBC_2 y EBC_3).

    Una pasada por clase para todas las zonas, no una por zona."""
    from convertersmartgrid.escaneo import CLASES_GENERADOR

    de_barra = {t: i for i, z in enumerate(zonas) for t in z.terminales}
    out = [{'bancos': [], 'generadores': []} for _z in zonas]
    if not zonas:
        return out
    for clase, destino in [('ElmShnt', 'bancos')] + [(c, 'generadores') for c in CLASES_GENERADOR]:
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            term = getattr(getattr(o, 'bus1', None), 'cterm', None)
            i = de_barra.get(_clave(term)) if term is not None else None
            if i is not None:
                out[i][destino].append(o.loc_name)
    return [{k: sorted(v) for k, v in e.items()} for e in out]


# =========================================================================== registro en disco (098:RF-5)
def fichero(plan: dict) -> Path:
    """El registro de lo que se tocó para calibrar con la red de la fuente, al lado del de las aperturas (081:RF-80)."""
    from convertersmartgrid.obras_pf import fichero_aperturas

    ruta = Path(fichero_aperturas(plan))
    return ruta.with_name(ruta.stem + '_red_de_la_fuente.json')


def _leer(ruta: Path) -> list[dict]:
    from convertersmartgrid.obras_pf import leer_aperturas

    return leer_aperturas(ruta)


def _escribir(ruta: Path, entradas: list[dict]) -> None:
    from convertersmartgrid.obras_pf import escribir_aperturas

    escribir_aperturas(ruta, entradas)


def _por_ruta(app, clase: str, nombre: str, ruta: str):
    """El objeto anotado, por su nombre completo; también fuera de servicio (081:RF-81)."""
    candidatos = list(app.GetCalcRelevantObjects(f'{nombre}.{clase}') or [])
    donde = app.GetProjectFolder('netdat') if hasattr(app, 'GetProjectFolder') else None
    if donde is not None:
        candidatos += list(donde.GetContents(f'{nombre}.{clase}', 1) or [])
    if not candidatos:
        # El doble filtra el patrón solo por la clase; en DIgSILENT da lo mismo.
        candidatos = [o for o in (app.GetCalcRelevantObjects(f'*.{clase}') or []) if o.loc_name == nombre]
    for o in candidatos:
        if o.GetClassName() == clase and _clave(o) == ruta:
            return o
    return None


class RedDeLaFuente:
    """098:RF-3 a RF-6: la transferencia del operador desactivada mientras se calibra, y vuelta a poner al terminar.

    ``preparar`` en el caso donde se calibra («Sin proyecto» del año); ``restituir`` es idempotente: se llama justo
    antes de guardar la calibración, para que el escenario y lo que pasa a «Con proyecto» (014:RF-31) lleven la red del
    operador, y otra vez en el ``finally``.
    """

    def __init__(self, app, plan: dict):
        self.app, self.plan = app, plan
        self.zonas: list = []
        self.cambios: list[dict] = []          # con el objeto vivo, en el orden en que se hicieron
        self.caso = None
        self.avisos: list[tuple[set[str] | None, str]] = []   # (a qué alimentadores toca, o a todos; texto)
        self.evidencia: list[dict] = []
        self.restituida = False
        self.deshecha = False                  # desactivada y vuelta a poner antes de calibrar (098:RF-8)
        self.inicial = None
        self.pendientes: list[dict] = []

    # ------------------------------------------------------------------- al empezar
    def restituir_pendientes(self, casos: dict) -> None:
        """098:RF-5: lo que dejó una calibración que murió sin restituir, otra vez como lo tenía el operador."""
        ruta = fichero(self.plan)
        entradas = [e for e in _leer(ruta) if e.get('proyecto') in (None, self.plan.get('project'))]
        if not entradas:
            return
        por_nombre = {c.loc_name: c for c in casos.values()}
        inicial = self.app.GetActiveStudyCase()
        quedan = []
        try:
            for caso in dict.fromkeys(e.get('caso') or '' for e in entradas):
                grupo = [e for e in entradas if (e.get('caso') or '') == caso]
                if por_nombre.get(caso) is None:
                    quedan += grupo
                    continue
                por_nombre[caso].Activate()
                for e in reversed(grupo):
                    obj = _por_ruta(self.app, e['clase'], e['nombre'], e['ruta'])
                    if obj is not None:
                        setattr(obj, e['atributo'], e['valor'])
                        self.pendientes.append(e)
                escenario = self.app.GetActiveScenario()
                if escenario is not None:
                    escenario.Save()
        finally:
            if inicial is not None and self.app.GetActiveStudyCase() is not inicial:
                inicial.Activate()
        _escribir(ruta, quedan)
        if self.pendientes:
            self.avisos.append((None, 'Una calibración anterior no terminó y dejó desactivada una transferencia del operador: '
                               'vuelve a estar como la dejó (' + ', '.join(sorted({e['nombre'] for e in self.pendientes}))
                               + ') (098:RF-5).'))

    def preparar(self, alims, caso, calibrados) -> None:
        """Desactiva cada zona transferida que sale de o llega a ``calibrados`` y comprueba que volvió a su alimentador."""
        self.caso = caso
        _flujo(self.app)
        self.zonas, objetos = leer_transferencias(self.app, alims, self.plan, interesan=calibrados)
        if not self.zonas:
            return
        hacer = [z for z in self.zonas if not z.motivo]
        for z in self.zonas:
            self.avisos.append(({z.desde, z.hacia}, texto_de_zona(z)))
        if not hacer:
            return
        acciones = []
        for z in hacer:
            for r in z.abrir:
                acciones += _abrir(objetos[r.clave], r.clase)
            for r in z.cerrar:
                acciones += _cerrar(objetos[r.clave], r.clase)
        nombre_caso = getattr(caso, 'loc_name', '') or ''
        ruta = fichero(self.plan)
        registro = _leer(ruta)
        for obj, atributo, nuevo in acciones:
            antes = getattr(obj, atributo, None)
            if antes == nuevo:
                continue
            fila = {'proyecto': self.plan.get('project'), 'caso': nombre_caso, 'clase': obj.GetClassName(),
                    'nombre': obj.loc_name, 'ruta': _clave(obj), 'atributo': atributo, 'valor': antes,
                    'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
            registro.append(fila)
            self.cambios.append({**fila, 'objeto': obj, 'nuevo': nuevo})
        try:
            _escribir(ruta, registro)                      # anotado antes de tocar nada (081:RF-80)
        except OSError as exc:
            self.avisos.append((None, f'No se pudo anotar en disco la transferencia desactivada: {exc}; no se toca (098:RF-5).'))
            self.cambios = []
            return
        for c in self.cambios:
            setattr(c['objeto'], c['atributo'], c['nuevo'])
        escenario = self.app.GetActiveScenario()
        if escenario is not None:
            escenario.Save()
        _flujo(self.app)
        _reiniciar(alims)
        # Cada SED de la zona, otra vez en el alimentador de su etiqueta; si no, se deshace todo y se calibra como está.
        _barras, de_carga, _cab = _topologia(alims, sorted(alims.elm))
        malas = [c.nombre for z in hacer for c in z.cargas if de_carga.get(c.clave) != z.desde]
        if malas:
            self.avisos.append((None, 'Con la transferencia desactivada, ' + ', '.join(malas[:10])
                               + ' no volvieron a su alimentador: se deja la red como la tenía el operador y se calibra '
                               'así (098:RF-8).'))
            self.restituir()
            self.deshecha = True
            _flujo(self.app)
            _reiniciar(alims)

    # ------------------------------------------------------------------- al terminar
    def restituir(self) -> list[dict]:
        """La transferencia otra vez como la dejó el operador, en el mismo caso y escenario, con la evidencia (098:RF-5)."""
        if self.restituida or not self.cambios:
            self.restituida = True
            return self.evidencia
        activo = self.app.GetActiveStudyCase()
        if self.caso is not None and activo is not self.caso:
            self.caso.Activate()
        try:
            for c in reversed(self.cambios):
                setattr(c['objeto'], c['atributo'], c['valor'])
            escenario = self.app.GetActiveScenario()
            if escenario is not None:
                escenario.Save()
            self.evidencia = [{'clase': c['clase'], 'nombre': c['nombre'], 'atributo': c['atributo'],
                               'valor': getattr(c['objeto'], c['atributo'], None), 'esperado': c['valor'],
                               'ok': getattr(c['objeto'], c['atributo'], None) == c['valor']} for c in self.cambios]
            ruta = fichero(self.plan)
            propias = {(c['caso'], c['clase'], c['ruta'], c['atributo']) for c in self.cambios}
            _escribir(ruta, [e for e in _leer(ruta)
                             if (e.get('caso'), e.get('clase'), e.get('ruta'), e.get('atributo')) not in propias])
            self.restituida = True
        finally:
            if activo is not None and self.app.GetActiveStudyCase() is not activo:
                activo.Activate()
        return self.evidencia

    def informe(self) -> dict | None:
        """Lo que va a cada informe de la calibración (098:RF-7)."""
        if not self.zonas and not self.pendientes and not self.avisos:
            return None
        hecho = bool(self.cambios) and self.restituida and all(e['ok'] for e in self.evidencia)
        return {'zonas': [z.resumen() for z in self.zonas],
                'desactivada_mientras_se_calibra': bool(self.cambios) and not self.deshecha,
                'cambios': [{k: c[k] for k in ('caso', 'clase', 'nombre', 'atributo', 'valor', 'nuevo')}
                            for c in self.cambios],
                'restituida': hecho if self.cambios else None, 'evidencia': self.evidencia,
                'restituidas_de_una_orden_anterior': [{k: e.get(k) for k in ('caso', 'clase', 'nombre', 'atributo')}
                                                      for e in self.pendientes]}


def _abrir(obj, clase: str) -> list[tuple]:
    """Abrir como lo hace una obra (081:RF-80): un acoplador por su maniobra, lo demás fuera de servicio."""
    return [(obj, 'on_off', 0)] if clase == 'ElmCoup' else [(obj, 'outserv', 1)]


def _cerrar(obj, clase: str) -> list[tuple]:
    """Cerrar: en servicio, el acoplador y los interruptores de sus cubículos cerrados."""
    out = [(obj, 'outserv', 0)]
    if clase == 'ElmCoup':
        out.append((obj, 'on_off', 1))
    out += [(s, 'on_off', 1) for s in _interruptores(_cubiculos(obj, clase))]
    return out


def _flujo(app) -> None:
    """Los ``ElmFeeder`` dan sus objetos con la última topología calculada (021:RF-38): un flujo antes de leer."""
    try:
        app.GetFromStudyCase('ComLdf').Execute()
    except Exception:  # noqa: BLE001, S110 - sin flujo se lee la topología que haya
        pass


def _reiniciar(alims) -> None:
    """Lo que ``Alimentadores`` guardó de la red de antes de tocarla ya no vale."""
    alims._cache = {}
    alims._fuera, alims._fuera_clave = {}, None


def aviso_de_la_medida(plan: dict) -> str | None:
    """098:RF-4: con la medida de un mes desde el de la importación, la transferencia pudo estar ya en la medida.

    La transferencia del operador es de después de importar el proyecto en DIgSILENT: una medida de un mes anterior al
    de la importación es de antes; de ese mes o después no se sabe.
    """
    medida = str(((plan.get('objetivo') or {}).get('fecha')) or '')[:7]
    importado = str(plan.get('fecha_importacion') or '')[:7]
    if len(medida) == 7 and len(importado) == 7 and medida >= importado:
        return (f'La medida de cabecera es de {medida} y el proyecto se importó en {importado}: no se sabe si ya incluye '
                'la transferencia del operador; se calibra con la red de la fuente, como si fuera de antes (098:RF-4).')
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Transferencias de carga del operador entre los alimentadores de un '
                                            'proyecto de DIgSILENT, solo lectura (spec 098)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('transferencia_operador_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    from cargas_pf import Alimentadores, activar_proyecto
    from casos_pf import anio_del_plan
    from casos_pf import caso as caso_del_sistema

    try:
        proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
        if proyecto is None:
            informe, codigo = {'error': f"no existe el proyecto {plan['project']!r}"}, 2
        else:
            caso = caso_del_sistema(app, 'sin', anio_del_plan(plan))
            if caso is not None:
                caso.Activate()
            _flujo(app)
            alims = Alimentadores(app, proyecto, plan.get('feeders') or [])
            zonas, _objs = leer_transferencias(app, alims, plan)
            informe = {'project': plan['project'], 'zonas': [{**z.resumen(), **e}
                                                             for z, e in zip(zonas, equipos_de_las_zonas(app, zonas))]}
            codigo = 0
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'error': repr(exc), 'traza': traceback.format_exc()}, 1
    Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for z in informe.get('zonas') or []:
        print(f"  {z['desde']} -> {z['hacia']}: {z['n_sed']} SED, {z['kw']:,.1f} kW", flush=True)
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
