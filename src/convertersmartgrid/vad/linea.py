"""La línea del VAD de punta a punta desde el caso, tramo A (spec 108, T30; RF-26).

Tras armar la empresa modelo sistema por sistema (``vad.trabajo``), la línea encadena lo que el estudio entrega con lo
que el caso trae, en el orden del TdR. Tramo B, sobre la red y las fuentes de la empresa del espacio (109:RF-25, RF-26):

a. modelo rural: la red real convertida del espacio (``modelo_rural.armar_modelo_rural``), en solo lectura;
b. dimensionamiento: la empresa modelo sobre la traza real (``dimensionamiento.dimensionar``), con ``estudio.dimensionamiento``
   del caso (rangos económicos, demanda por SED, tabla de potencias, sector, tipo de SED, factor de carga, corrosivos);
c. costo estándar: la red dimensionada valorada con el SICODI vigente de la empresa (``costos.costo_estandar``), firmado tal
   como llega, con ``estudio.costo`` (resolución, año, moneda, fuente, estructura por alimentador y código de cada SED).

Tramo A:

1. resultados: el VAD por sistema y de la empresa (``resultados_vad.calcular_vad``), con los ``resultados`` de cada
   sistema del caso (su ámbito, su moneda, los valores de las fórmulas y sus variantes);
2. PIDE: el VAD ajustado con el PIDE aprobado (``pide_vad.incorporar_pide``), con ``estudio.pide`` del caso;
3. calidad: la verificación del numeral 6.11 (``calidad.verificar_calidad``), con ``estudio.calidad``;
4. explotación: los costos estándar por rubro (``costos_explotacion.costear``), con la ``explotacion`` de cada sistema;
5. tablas: el libro de las Tablas de Resultados (``tablas_resultados.escribir_tablas``): la 13 con el VAD por sistema;
6. informes: el de Resultados Relevantes y el del Estudio (``informes``), con las cifras que salen de los pasos.

Cada paso sin su entrada se queda en «sin_entrada» con su hueco nombrado, y uno que falla no tumba a los siguientes
(P6); nada se rellena. La línea deja ``linea.json`` (el estado de cada paso) y ``contenido_informes.json`` (lo que el
Informe Definitivo vuelve a usar) en la carpeta del estudio.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..util import write_json_atomic
from . import VadError
from .estudio import cargar_estudio, carpeta_estudio

PASOS_LINEA = ('modelo_rural', 'dimensionamiento', 'costo_estandar', 'resultados', 'pide', 'calidad', 'explotacion',
               'tablas', 'informes')
LINEA = 'linea.json'
CONTENIDO = 'contenido_informes.json'
TABLAS = 'tablas_resultados.xlsx'
#: Las claves del caso: por sistema (en ``sistemas``) y del estudio (en ``estudio``).
POR_SISTEMA = ('resultados', 'explotacion')
DEL_ESTUDIO = ('dimensionamiento', 'costo', 'pide', 'calidad')
#: Apartados del Anexo 3 (Informe de Resultados Relevantes) y del Informe del Estudio que la línea llena.
APARTADO_RESULTADOS, APARTADO_CALIDAD, APARTADO_COSTOS, APARTADO_PIDE = '9', '7', '5', '12'
#: El apartado del Anexo 3 del Valor Nuevo de Reemplazo, que llena el costo estándar del tramo B.
APARTADO_VNR = '4'


def leer_estudio_del_caso(carpeta: Path | str) -> dict[str, str]:
    """Las entradas del estudio en ``sistemas.json`` (``{"estudio": {"pide": ruta, "calidad": ruta}}``), con rutas
    dentro de la carpeta del caso; sin la clave, ninguna."""
    carpeta = Path(carpeta)
    datos = json.loads((carpeta / 'sistemas.json').read_text(encoding='utf-8'))
    estudio = datos.get('estudio') if isinstance(datos, Mapping) else None
    if estudio is None:
        return {}
    if not isinstance(estudio, Mapping):
        raise VadError('sistemas.json: «estudio» tiene que ser un objeto {paso: ruta}')
    raiz = carpeta.resolve()
    salida = {}
    for paso, rel in estudio.items():
        if paso not in DEL_ESTUDIO:
            raise VadError(f'sistemas.json: «estudio» no tiene el paso {paso!r}; los del estudio son {DEL_ESTUDIO}')
        ruta = (carpeta / str(rel)).resolve()
        if not ruta.is_relative_to(raiz):
            raise VadError(f'sistemas.json: {rel} sale de la carpeta del caso')
        salida[str(paso)] = str(ruta)
    return salida


def _json(ruta: str) -> Any:
    return json.loads(Path(ruta).read_text(encoding='utf-8'))


def armar_linea(ctx: Any, espacio: Path | str, id_estudio: str, entradas: Mapping[str, Mapping[str, Any]],
                del_estudio: Mapping[str, str], registro: Any, *, fecha: str | None = None,
                exportar_pdf: Callable | None = None) -> dict[str, Any]:
    """Los pasos de la línea sobre el estudio ya armado; devuelve (y deja escrito) el estado de cada paso."""
    from .informes import Cifra, escribir_informe_estudio, escribir_resultados_relevantes
    from .tablas_resultados import TablaDatos, escribir_tablas

    estudio = cargar_estudio(espacio, id_estudio)
    carpeta = carpeta_estudio(espacio, id_estudio)
    linea: dict[str, Any] = {'estudio': estudio.id, 'pasos': {p: {'estado': 'PENDIENTE'} for p in PASOS_LINEA},
                             'terminada': False}
    resultados: dict[str, list] = {APARTADO_VNR: [], APARTADO_RESULTADOS: [], APARTADO_CALIDAD: [], APARTADO_COSTOS: [],
                                   APARTADO_PIDE: []}
    tablas: dict[str, Any] = {}
    vad = None
    red = modelo = dim = None

    def escribir() -> None:
        write_json_atomic(carpeta / LINEA, linea)

    def paso(nombre: str, i: int, fn: Callable[[], dict[str, Any] | None]) -> None:
        ctx.check_cancel()
        ctx.progress(i, len(PASOS_LINEA), nombre)
        try:
            r = fn()
        except MemoryError:
            raise
        except (VadError, ValueError, KeyError, TypeError, OSError) as exc:  # P6: un paso que falla no tumba la línea
            linea['pasos'][nombre] = {'estado': 'FAIL', 'error': f'{type(exc).__name__}: {exc}'}
            ctx.log(f'línea del VAD, {nombre}: {exc}')
        else:
            linea['pasos'][nombre] = r if r is not None else {'estado': 'OK'}
        escribir()

    def sin_entrada(motivo: str) -> dict[str, Any]:
        return {'estado': 'SIN_ENTRADA', 'motivo': motivo}

    # a. Modelo rural: la red real convertida del espacio, en solo lectura.
    def p_modelo_rural():
        nonlocal red, modelo
        from .. import fuentes_empresa as fe
        from ..adaptadores.entrada.vnr.models.canonical import CanonicalModel
        from .modelo_rural import armar_modelo_rural
        info = fe.red_del_espacio(espacio)
        if not info or not info.get('canonical'):
            return sin_entrada('el espacio no tiene su red convertida (cargue la red de la empresa en el conversor)')
        red = CanonicalModel.from_dict(json.loads((Path(espacio) / info['canonical']).read_text(encoding='utf-8')))
        modelo = armar_modelo_rural(red, registro=registro)
        return {'estado': 'OK', 'tramos': len(modelo.tramos), 'sed': len(modelo.sed), 'huecos': list(modelo.huecos),
                'red': {k: info.get(k) for k in ('fuente', 'empresa', 'huella')}}

    # b. Dimensionamiento: la empresa modelo sobre la traza real, con lo que el caso declara de su sustento.
    def p_dimensionamiento():
        nonlocal dim
        from .dimensionamiento import DemandaSed, RangoEconomico, TablaTransformadores, dimensionar
        if modelo is None:
            return sin_entrada('sin el modelo rural no hay qué dimensionar')
        if 'dimensionamiento' not in del_estudio:
            return sin_entrada('el caso no trae su sustento («estudio.dimensionamiento»: rangos, demanda, tabla, sector, '
                               'tipo de SED)')
        d = _json(del_estudio['dimensionamiento'])
        tabla = d['tabla']
        dim = dimensionar(
            modelo, registro=registro,
            cabeceras={s.feeder_id: s.node_id for s in red.sources},
            conductor_de={s.section_id: s.conductor_code for s in red.sections},
            conductores=list(red.conductor_types),
            rangos=[RangoEconomico(str(r['conductor']), float(r['desde']), float(r['hasta']), str(r['sustento']))
                    for r in d['rangos']],
            demanda={str(s): DemandaSed(float(v['kw']), float(v['kvar']), str(v['fases']), str(v['origen']))
                     for s, v in d['demanda'].items()},
            tabla=TablaTransformadores({tuple(k.split('|', 1)): tuple(float(x) for x in v)
                                        for k, v in tabla['potencias'].items()},
                                       str(tabla['huella']), frozenset(float(x) for x in tabla.get('no_normalizadas') or [])),
            sector_de={str(k): str(v) for k, v in d['sector_de'].items()},
            tipo_de_sed={str(k): str(v) for k, v in d['tipo_de_sed'].items()},
            factor_carga={str(k): float(v) for k, v in (d.get('factor_carga') or {}).items()} or None,
            corrosivos=tuple(d.get('corrosivos') or ()), fecha=fecha)
        return {'estado': 'OK' if not dim.huecos else 'INCOMPLETO', 'sed': len(dim.sed), 'tramos': len(dim.tramos),
                'huecos': list(dim.huecos)}

    # c. Costo estándar: la red dimensionada con el SICODI vigente de la empresa, firmado tal como llega.
    def p_costo_estandar():
        from .. import fuentes_empresa as fe
        from .costos import costo_estandar, firmar_sicodi, leer_sicodi_del_periodo
        if dim is None:
            return sin_entrada('sin el dimensionamiento no hay qué valorar')
        if 'costo' not in del_estudio:
            return sin_entrada('el caso no trae los datos del SICODI («estudio.costo»: resolución, año, moneda, '
                               'estructura y código de cada SED)')
        vig = fe.vigente(espacio, 'sicodi')
        if vig is None:
            return sin_entrada('la empresa no tiene su SICODI en las fuentes (clase «sicodi»)')
        d = _json(del_estudio['costo'])
        ruta = fe.ruta(espacio, vig.id)
        firma = firmar_sicodi(ruta)
        tabla, firma, huecos = leer_sicodi_del_periodo(
            ruta, huella_sicodi=firma.huella, huella_miembro=firma.huella_miembro or None,
            resolucion=str(d['resolucion']), anio=int(d['anio']), moneda=str(d['moneda']), url=str(d['url']),
            fecha_descarga=str(d['fecha_descarga']))
        if tabla is None:
            return {'estado': 'INCOMPLETO', 'motivo': 'el SICODI no se pudo leer para el periodo', 'huecos': list(huecos)}
        datos_dim = _json(del_estudio['dimensionamiento'])
        c = costo_estandar(dim, sicodi=tabla, huella_sicodi=firma.huella, firma_sicodi=firma, registro=registro,
                           sector_de={str(k): str(v) for k, v in datos_dim['sector_de'].items()},
                           estructura_de={str(k): str(v) for k, v in d['estructura_de'].items()},
                           tipo_de_sed={str(k): str(v) for k, v in datos_dim['tipo_de_sed'].items()},
                           codigo_sed={(k.split('|', 1)[0], float(k.split('|', 1)[1])): str(v)
                                       for k, v in d['codigo_sed'].items()},
                           huella_miembro=firma.huella_miembro or None, fecha=fecha)
        sistema_de = {f.feeder_id: f.system_id or f.feeder_id for f in red.feeders}
        por_sistema: dict[str, float] = {}
        for e in c.estandar:
            por_sistema[sistema_de.get(e.alimentador, e.alimentador)] = por_sistema.get(
                sistema_de.get(e.alimentador, e.alimentador), 0.0) + e.costo
        moneda = c.estandar[0].moneda if c.estandar else str(d['moneda'])
        if por_sistema:
            tablas['2'] = TablaDatos(columnas=[f'Costo estándar ({moneda})'], filas=[
                {'sistema': s, f'Costo estándar ({moneda})': round(v, 2)} for s, v in sorted(por_sistema.items())],
                motivo_sin_datos='')
            resultados[APARTADO_VNR].append(Cifra('Costo estándar de la red dimensionada', round(sum(por_sistema.values()), 2),
                                                  moneda, origen='Tabla 2'))
        return {'estado': 'OK' if not c.huecos else 'INCOMPLETO', 'elementos': len(c.estandar),
                'sin_costo': len(c.sin_costo), 'huecos': list(c.huecos), 'sicodi': vig.nombre}

    # 1. Resultados: el VAD por sistema y de la empresa.
    def p_resultados():
        nonlocal vad
        from .resultados_vad import DatosSistema, calcular_vad
        datos = []
        for sistema, e in entradas.items():
            if 'resultados' in e:
                d = _json(e['resultados'])
                datos.append(DatosSistema(sistema=sistema, ambito=str(d['ambito']), moneda=str(d['moneda']),
                                          valores={str(k): float(v) for k, v in d['valores'].items()},
                                          variantes={str(k): str(v) for k, v in (d.get('variantes') or {}).items()}))
        if not datos:
            return sin_entrada('ningún sistema del caso trae sus «resultados» (ámbito, moneda y valores de las fórmulas)')
        vad = calcular_vad(registro, datos, fecha)
        conceptos = sorted({v.concepto for s in vad.sistemas for v in s.valores})
        tablas['13'] = TablaDatos(columnas=conceptos, filas=[
            {'sistema': s.sistema, **{v.concepto: v.valor for v in s.valores}} for s in vad.sistemas],
            motivo_sin_datos='')
        for v in vad.empresa:
            resultados[APARTADO_RESULTADOS].append(Cifra(f'{v.concepto} de la empresa', v.valor,
                                                         f'{v.moneda} {v.unidad}'.strip(), origen='Tabla 13'))
        write_json_atomic(carpeta / 'resultados_vad.json', {
            'estado': vad.estado, 'motivos': list(vad.motivos),
            'sistemas': {s.sistema: [asdict(v) for v in s.valores] for s in vad.sistemas},
            'empresa': [asdict(v) for v in vad.empresa]})
        return {'estado': 'OK' if vad.estado == 'conforme' else 'INCOMPLETO', 'estado_vad': vad.estado,
                'motivos': list(vad.motivos), 'sistemas': len(vad.sistemas)}

    # 2. PIDE: el VAD ajustado con el PIDE aprobado.
    def p_pide():
        from .pide_vad import VadNivel, incorporar_pide, pide_desde_dict
        if 'pide' not in del_estudio:
            return sin_entrada('el caso no trae el PIDE aprobado («estudio.pide»)')
        d = _json(del_estudio['pide'])
        base = {str(n): VadNivel(**{k: float(x) for k, x in v.items()}) for n, v in (d.get('base') or {}).items()}
        if not base:
            return sin_entrada('el PIDE del caso no trae el VAD base por nivel («base»: {nivel: anualidad, oym, demanda})')
        inc = incorporar_pide(registro, base, pide_desde_dict(d['pide']), ambito_fonafe=d.get('ambito_fonafe'),
                              periodo=estudio.periodo, moneda=str(d.get('moneda') or ''), fecha=fecha)
        for nivel, valor in inc.vad_ajustado.items():
            resultados[APARTADO_PIDE].append(Cifra(f'VAD ajustado con el PIDE, {nivel}', valor, '', origen='PIDE aprobado'))
        return {'estado': 'OK' if inc.incorporado else 'NO_INCORPORADO', 'avisos': list(inc.avisos)}

    # 3. Calidad: la verificación del numeral 6.11.
    def p_calidad():
        from .calidad import Cliente, Interrupcion, verificar_calidad
        if 'calidad' not in del_estudio:
            return sin_entrada('el caso no trae los clientes y las interrupciones («estudio.calidad»)')
        d = _json(del_estudio['calidad'])
        clientes = [Cliente(**c) for c in d.get('clientes') or []]
        interrupciones = [Interrupcion(**{**i, 'clientes': tuple(i.get('clientes') or ())})
                          for i in d.get('interrupciones') or []]
        r = verificar_calidad(registro, clientes, interrupciones, fecha=fecha)
        cumplen = sum(1 for v in r.verificaciones if v.estado == 'cumple')
        resultados[APARTADO_CALIDAD].append(Cifra('Verificaciones que cumplen', f'{cumplen} de {len(r.verificaciones)}',
                                                  '', origen='Cuadro 21 (numeral 6.11)'))
        return {'estado': 'OK', 'verificaciones': len(r.verificaciones), 'cumplen': cumplen,
                'huecos': [f'{h.clave}: {h.motivo}' for h in r.huecos]}

    # 4. Explotación: los costos estándar por rubro.
    def p_explotacion():
        from .costos_explotacion import Partida, costear
        dimensionado: dict[str, list] = {}
        for _sistema, e in entradas.items():
            if 'explotacion' in e:
                for rubro, partidas in _json(e['explotacion']).items():
                    dimensionado.setdefault(str(rubro), []).extend(Partida(**p) for p in partidas)
        if not dimensionado:
            return sin_entrada('ningún sistema del caso trae su «explotacion» (partidas por rubro)')
        c = costear(registro, dimensionado, fecha=fecha)
        for r in c.rubros:
            if r.estandar is not None:
                resultados[APARTADO_COSTOS].append(Cifra(r.rubro.nombre, r.estandar, r.moneda, origen=f'rubro {r.rubro.clave}'))
        return {'estado': 'OK', 'totales': dict(c.totales)}

    # 5. Tablas: una hoja por tabla del registro; las que la línea no llena salen como hueco nombrado.
    def p_tablas():
        libro = escribir_tablas(registro, tablas, carpeta / TABLAS, fecha)
        return {'estado': 'OK', 'libro': str(libro.ruta), 'huecos': list(libro.huecos)}

    # 6. Informes: con las cifras que dejaron los pasos; lo que falta, hueco nombrado en el propio informe.
    def p_informes():
        contenido = {k: v for k, v in resultados.items() if v}
        rr = escribir_resultados_relevantes(registro, contenido, carpeta / 'informe_resultados_relevantes.docx',
                                            empresa=estudio.empresa, fecha=fecha)
        ie = escribir_informe_estudio(registro, {}, carpeta / 'informe_estudio.docx', empresa=estudio.empresa,
                                      exportar_pdf=exportar_pdf, fecha=fecha)
        write_json_atomic(carpeta / CONTENIDO, {
            'resultados': {k: [asdict(b) if isinstance(b, Cifra) else b for b in v] for k, v in contenido.items()},
            'estudio': {}})
        return {'estado': 'OK', 'documentos': [str(rr.docx), str(ie.docx)], 'huecos': [*rr.huecos, *ie.huecos]}

    escribir()
    for i, (nombre, fn) in enumerate(zip(PASOS_LINEA, (p_modelo_rural, p_dimensionamiento, p_costo_estandar, p_resultados,
                                                       p_pide, p_calidad, p_explotacion, p_tablas, p_informes))):
        paso(nombre, i, fn)
    ctx.progress(len(PASOS_LINEA), len(PASOS_LINEA), 'terminada')
    linea['terminada'] = True
    escribir()
    return linea


def contenido_guardado(espacio: Path | str, id_estudio: str) -> tuple[dict[str, list], dict[str, list]]:
    """Lo que la línea dejó para los informes, como bloques (``Cifra`` o texto), para el Informe Definitivo."""
    from .informes import Cifra
    ruta = carpeta_estudio(espacio, id_estudio) / CONTENIDO
    if not ruta.is_file():
        return {}, {}
    datos = json.loads(ruta.read_text(encoding='utf-8'))

    def bloques(d: Mapping[str, list]) -> dict[str, list]:
        return {k: [Cifra(**b) if isinstance(b, Mapping) else str(b) for b in v] for k, v in (d or {}).items()}
    return bloques(datos.get('resultados') or {}), bloques(datos.get('estudio') or {})
