"""Genera Word y evidencia tabular desde los flujos completos guardados por la web.

Spec 063: reutiliza el escritor de informes, sin abrir ni modificar DIgSILENT.
El plan identifica un único proyecto y los seis informes nativos por ruta explícita.
Las fuentes privadas permanecen en el equipo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import replace
from datetime import date
from pathlib import Path, PureWindowsPath

from convertersmartgrid.informe_docx import (
    DatosFactibilidad,
    escribir_informe_factibilidad,
)
from convertersmartgrid.informes import Caso, ConfigInforme, Encabezado, Solicitud
from convertersmartgrid.libros_informe import DatosPerdidas
from convertersmartgrid.mapa_informe import imagenes_del_estado
from convertersmartgrid.perfil_empresa import datos_perfil

ROLES = {'sin': 'Sin proyecto', 'cargas': 'Cargas nuevas', 'con': 'Con proyecto'}


def leer_operacion(ruta: Path, project: str) -> dict:
    """El anexo de aceptación procede de una operación nativa aceptada y persistida."""
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if datos.get('project') != project:
        raise ValueError('La operación nativa corresponde a otro proyecto.')
    if datos.get('aceptada') is not True or datos.get('persistida') is not True:
        raise ValueError('La operación nativa no está aceptada y persistida.')
    if (datos.get('cargas_previstas_relectura') or {}).get('completa') is not True:
        raise ValueError('La operación no acredita todas las cargas previstas al releer.')
    for modo in ('flujo', 'flujo_desequilibrado'):
        if (datos.get('estudios_relectura', {}).get(modo) or {}).get('aceptada') is not True:
            raise ValueError(f'La operación no acredita {modo} tras reabrir.')
    if datos.get('restauracion_errores'):
        raise ValueError('La operación informa errores de restitución o aislamiento.')
    return datos


def validar_referencia_certificada(datos: dict) -> bool:
    """Excepción RF-38: acredita el estado final sin aceptar lecturas de la referencia fallida."""
    if (datos.get('accion') != 'aplicar' or datos.get('status') != 'OK'
            or datos.get('aceptada') is not True or datos.get('persistida') is not True
            or datos.get('error') or datos.get('restauracion_errores')):
        raise ValueError('La referencia fallida requiere una operación nativa aplicada, aceptada y persistida.')
    final = datos.get('verificacion_final') or {}
    if final.get('modelo_identico') is not True or final.get('cargas_sin_obras_verificadas') is not True:
        raise ValueError('Falta la verificación final del modelo idéntico y de las cargas sin obras.')
    if (datos.get('cargas_previstas_relectura') or {}).get('completa') is not True:
        raise ValueError('Falta el conjunto completo de cargas releídas.')
    for rol, modos in [('actual', (datos.get('estudios_referencia', {}).get('sin') or {}).get('estudios', {})),
                       ('con', datos.get('estudios_relectura') or {})]:
        for modo in ('flujo', 'flujo_desequilibrado'):
            e = modos.get(modo) or {}
            flujo, red = e.get('flujo') or {}, e.get('red_proyecto') or {}
            objetos = e.get('objetos') or {}
            if (flujo.get('converged') is not True or flujo.get('return_code') != 0
                    or flujo.get('ldf_valid') is not True or red.get('cobertura_completa') is not True
                    or red.get('balance_completo') is not True or red.get('medida', {}).get('converge') is not True
                    or not objetos.get('ElmTerm')
                    or red.get('cantidad_barras') != sum(not b.get('outserv') for b in objetos['ElmTerm'])):
                raise ValueError(f'{rol} / {modo}: no se acredita flujo válido y cobertura nativa completa.')
            if rol != 'con':
                continue
            if e.get('aceptada') is not True or e.get('incumplimientos'):
                raise ValueError(f'Con proyecto / {modo}: no está aceptado nativamente.')
            termicas = objetos.get('ElmSym') or []
            if not termicas or any(t.get('outserv') != 1 for t in termicas):
                raise ValueError('La central térmica no está acreditada fuera de servicio.')
            for clase, filas in objetos.items():
                for o in filas:
                    if o.get('outserv'):
                        continue
                    if clase == 'ElmTerm':
                        u = o.get('m:u')
                        fases = [o.get(f'm:u:{f}') for f in 'ABC']
                        if (not isinstance(u, (int, float)) or not math.isfinite(u) or not .95 <= u <= 1.05
                                or any(v is not None and (not math.isfinite(v) or not .95 <= v <= 1.05)
                                       for v in fases)):
                            raise ValueError('Con proyecto conserva una tensión ausente o fuera de los límites nativos.')
                    if clase == 'ElmLod':
                        for escrito, resultado in [('plini', 'm:Psum:bus1'), ('qlini', 'm:Qsum:bus1')]:
                            valores = (o.get(escrito), o.get('scale0'), o.get(resultado))
                            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in valores):
                                raise ValueError('Con proyecto conserva una carga con P/Q incompletos.')
                            nominal = valores[0] * valores[1]
                            if abs(valores[2] - nominal) > max(.001, abs(nominal) * .005):
                                raise ValueError('Con proyecto no conserva el consumo P/Q nominal verificado.')
                    if clase in ('ElmLne', 'ElmTr2', 'ElmTr3'):
                        carga = o.get('c:loading')
                        if carga is None or not math.isfinite(carga) or carga > 100:
                            raise ValueError('Con proyecto conserva un equipo sin cargabilidad válida o sobrecargado.')
    return True


def geografia_topologica(objetos: dict) -> dict:
    """GPS y conexiones del mismo inventario: enlaces simplificados, sin resultados de flujo."""
    from collections import Counter
    terminos = [b for b in objetos.get('ElmTerm', []) if not b.get('outserv')]
    repetidos = Counter(b['nombre'] for b in terminos)
    barras, por_ruta, faltan = [], {}, []
    for b in terminos:
        lat, lon = b.get('GPSlat'), b.get('GPSlon')
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon))
                or (lat == 0 and lon == 0) or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            faltan.append(b['ruta'])
            continue
        nombre = b['nombre'] if repetidos[b['nombre']] == 1 else b['ruta']
        fila = [nombre, lat, lon, None, b.get('uknom')]
        barras.append(fila)
        por_ruta[b['ruta']] = fila
    tramos = []
    for ln in objetos.get('ElmLne', []):
        if ln.get('outserv'):
            continue
        refs = ln.get('referencias') or {}
        extremos = [por_ruta.get((refs.get(k) or {}).get('terminal')) for k in ('bus1', 'bus2')]
        if not all(extremos):
            faltan.append(ln.get('ruta') or ln['nombre'])
            continue
        a, b = extremos
        tramos.append([ln['nombre'], [a[1:3], b[1:3]], None, a[0], b[0],
                       (refs.get('typ_id') or {}).get('nombre'), ln.get('dline')])
    vinculos = {}
    for clase, atributo in [('ElmLod', 'bus1'), ('ElmTr2', 'buslv')]:
        for o in objetos.get(clase, []):
            terminal = (o.get('referencias', {}).get(atributo) or {}).get('terminal')
            if terminal in por_ruta:
                vinculos[o['nombre']] = {'barra': por_ruta[terminal][0]}
    return {'barras': barras, 'tramos': tramos, 'acoples': [], 'cabecera': None,
            'sin_resultados_electricos': True, 'geometria': 'enlaces simplificados entre GPS de terminales',
            'elementos_sin_geografia': faltan, 'vinculos_equipos': vinculos}


def inventario_nominal(objetos: dict) -> dict:
    """Cantidades y entradas nominales; no son balances ni resultados eléctricos."""
    cargas = [c for c in objetos.get('ElmLod', []) if not c.get('outserv')]
    def nominal(campo):
        if not cargas or any(c.get(campo) is None or c.get('scale0') is None for c in cargas):
            return None
        return sum(c[campo] * c['scale0'] * 1000 for c in cargas)
    return {'barras': sum(not b.get('outserv') for b in objetos.get('ElmTerm', [])),
            'cargas': len(cargas), 'p_nominal_kw': nominal('plini'), 'q_nominal_kvar': nominal('qlini')}


def vincular_capturas_certificadas(pruebas, operacion: dict, sha: str) -> None:
    """La excepción no permite sustituir una de las seis capturas por otra lectura del proyecto."""
    for rol, modo, captura in pruebas:
        nativa = (operacion['estudios_relectura'][modo] if rol == 'con' else
                  operacion['estudios_referencia'][rol]['estudios'][modo])
        if captura.get('source_operacion_sha256') != sha:
            raise ValueError('Una captura no conserva la huella de la operación nativa certificada.')
        if captura.get('referencia_no_convergente'):
            if (rol != 'cargas' or nativa.get('flujo', {}).get('converged') is not False
                    or captura.get('objetos_nativos') != nativa.get('objetos')):
                raise ValueError('La referencia fallida no coincide con su inventario nativo certificado.')
        elif (captura.get('red_proyecto') != nativa.get('red_proyecto')
              or captura.get('geo_proyecto') != (nativa.get('geo_proyecto') or {})):
            raise ValueError('Los resultados o la geografía de una captura no coinciden con la lectura certificada.')


def caso_conservador(equilibrado: Caso, desequilibrado: Caso) -> Caso:
    """RF-38: el dictamen considera los extremos medidos de ambos flujos.

    Los balances conservan el desequilibrado. Los extremos se toman de las lecturas
    originales, sin promediar ni permitir que un modo oculte la violación del otro.
    """
    if not equilibrado.converge or not desequilibrado.converge:
        return replace(desequilibrado, converge=False)
    tensiones = dict(desequilibrado.tension_min)
    for fase, extremo in equilibrado.tension_min.items():
        if fase not in tensiones or extremo.valor < tensiones[fase].valor:
            tensiones[fase] = extremo
    cambios = {'tension_min': tensiones,
               'nodos_fuera': max(equilibrado.nodos_fuera, desequilibrado.nodos_fuera),
               'tramos_sobre': max(equilibrado.tramos_sobre, desequilibrado.tramos_sobre)}
    for campo in ('tension_max', 'cargabilidad_max', 'trafo_max'):
        valores = [v for c in (equilibrado, desequilibrado) if (v := getattr(c, campo)) is not None]
        cambios[campo] = max(valores, key=lambda v: v.valor) if valores else None
    return replace(desequilibrado, **cambios)


def leer_caso(ruta: Path, project: str, caso: str, *, operacion: dict | None = None,
              sha_operacion: str | None = None) -> dict:
    """Impide utilizar otro proyecto, otro caso o una captura parcial como evidencia."""
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if datos.get('project') != project:
        raise ValueError(f'{ruta.name}: no corresponde al proyecto {project}.')
    if datos.get('caso') != caso or datos.get('estudio') not in ('flujo', 'flujo_desequilibrado'):
        raise ValueError(f'{ruta.name}: no corresponde al caso o al estudio solicitado.')
    if datos.get('referencia_no_convergente'):
        if caso != 'Cargas nuevas' or operacion is None or operacion.get('project') != project:
            raise ValueError('La referencia fallida exige una operación nativa certificada del mismo proyecto.')
        validar_referencia_certificada(operacion)
        nativa = (operacion.get('estudios_referencia', {}).get('cargas') or {}).get('estudios', {}).get(datos['estudio']) or {}
        if (not sha_operacion or datos.get('source_operacion_sha256') != sha_operacion
                or nativa.get('flujo', {}).get('converged') is not False
                or not nativa.get('objetos') or datos.get('objetos_nativos') != nativa['objetos']):
            raise ValueError('La referencia fallida no está ligada al flujo y al inventario nativos por su huella.')
        datos['red_proyecto'] = {'medida': {'converge': False}}
        datos['geo_proyecto'] = geografia_topologica(nativa['objetos'])
        datos['inventario_nominal'] = inventario_nominal(nativa['objetos'])
        return datos
    red = datos.get('red_proyecto') or {}
    if red.get('cobertura_completa') is not True:
        raise ValueError(f'{ruta.name}: falta cobertura completa de las barras del proyecto.')
    if red.get('balance_completo') is not True:
        raise ValueError(f'{ruta.name}: el balance de potencias no está completo.')
    if datos.get('error') or not red.get('medida', {}).get('converge'):
        raise ValueError(f'{ruta.name}: el flujo no permite generar una evaluación completa.')
    return datos


def generar(plan: dict, destino: Path, raiz: Path) -> dict:
    """Escribe el informe con cifras nativas, figuras locales y anexos verificables."""
    import docx

    project = plan['project']
    operacion = None
    sha_operacion = None
    if plan.get('operacion_verificada'):
        operacion = leer_operacion(Path(plan['operacion_verificada']), project)
        sha_operacion = hashlib.sha256(Path(plan['operacion_verificada']).read_bytes()).hexdigest()
    perfiles = datos_perfil()
    config = ConfigInforme.de_perfil(perfiles, raiz).con_limites(**plan['limites'])
    casos, pruebas, procedencia = {}, [], []
    for rol, nombre in ROLES.items():
        for modo in ('flujo', 'flujo_desequilibrado'):
            ruta = Path(plan['estudios'][rol][modo])
            d = leer_caso(ruta, project, nombre, operacion=operacion, sha_operacion=sha_operacion)
            if d['estudio'] != modo:
                raise ValueError(f'{ruta.name}: el modo del flujo no coincide con el plan.')
            pruebas.append((rol, modo, d))
            procedencia.append({'ruta': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest()})
            if modo == 'flujo_desequilibrado':
                casos[rol] = d
    referencia_fallida = any(d.get('referencia_no_convergente') for _, _, d in pruebas)
    if referencia_fallida:
        validar_referencia_certificada(operacion)
        vincular_capturas_certificadas(pruebas, operacion, sha_operacion)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagenes = {}
    encuadre = {'barras': [b for d in casos.values() for b in d['geo_proyecto']['barras']],
                'tramos': [t for d in casos.values() for t in d['geo_proyecto']['tramos']]}
    for rol, d in casos.items():
        clave = {'sin': 'actual', 'cargas': 'cargas', 'con': 'proyectado'}[rol]
        imagenes[clave] = imagenes_del_estado(
            d['geo_proyecto'], destino.parent / f'{destino.stem}_figuras', f'{destino.stem}_{rol}',
            estado=(ROLES[rol] + ' · NO CONVERGE · esquema sin resultados eléctricos'
                    if d.get('referencia_no_convergente') else ROLES[rol]), alimentador=plan['alcance'],
            bandas_tension=config.bandas_tension_pct, bandas_carga=config.bandas_cargabilidad_pct,
            cliente=(plan['barra'], plan['solicitud']['cliente']), red=d['red_proyecto'],
            limites=(config.limites.tension_min_pu, config.limites.tension_max_pu,
                     config.limites.cargabilidad_max_pct),
            referencia=casos['cargas'] if rol == 'con' else None,
            obras_aplicadas=plan.get('obras', ()),
            obras_activas=d.get('variaciones_activas') or d.get('obras_activas', ()),
            vinculos_equipos=d['geo_proyecto'].get('vinculos_equipos', plan.get('vinculos_equipos', {})),
            encuadre=encuadre)
    sol = dict(plan['solicitud'])
    sol['fecha_solicitud'] = date.fromisoformat(sol['fecha_solicitud'])
    solicitud = Solicitud(**sol)
    casos_dictamen = {}
    for rol, nombre in ROLES.items():
        por_modo = {modo: Caso.desde_medida(nombre, d['red_proyecto']['medida'], config.limites)
                    for r, modo, d in pruebas if r == rol}
        casos_dictamen[rol] = caso_conservador(por_modo['flujo'], por_modo['flujo_desequilibrado'])
    punto = next(x for x in casos['con']['red_proyecto']['tensiones_por_nivel']['mt']
                 if x['nombre'] == plan['barra'])
    u = min(x for x in punto['fases'].values() if x is not None)
    kv = u * solicitud.tension_kv
    # Los kW/kvar del incremento son del plan de cargas aplicado, no de una suposición de FP.
    kw, kvar = plan['incremento_aplicado_kw'], plan['incremento_aplicado_kvar']
    punto_diseno = {'u_pu': u, 'kv_ll': kv, 'kv_ln': kv / math.sqrt(3),
                    'kw': kw, 'kvar': kvar, 'kva': math.hypot(kw, kvar),
                    'i_a': math.hypot(kw, kvar) / (math.sqrt(3) * kv)}
    datos = DatosFactibilidad(
        encabezado=Encabezado(date.fromisoformat(plan['fecha']), plan['asunto'], plan['destinatario'],
                              lugar=plan['lugar']),
        actual=casos_dictamen['sin'], cargas=casos_dictamen['cargas'], proyectado=casos_dictamen['con'],
        solicitud=solicitud, codigo_punto=plan['codigo_punto'], punto_diseno=punto_diseno,
        solicitudes_vigentes=True, con_obras=bool(casos['con'].get('obras_activas')),
        libro=DatosPerdidas(**plan['perdidas_reconocidas']), imagenes=imagenes,
        fuentes=plan['fuentes'], observaciones=plan['observaciones'],
        incluir_transformador_set=False, perdidas_instantaneas=True, numero=plan.get('numero'),
        con_proyecto_verificado=referencia_fallida)
    huecos = escribir_informe_factibilidad(config, destino, datos)
    if huecos:
        raise ValueError('El informe conserva huecos: ' + ', '.join(huecos))
    documento = docx.Document(destino)
    documento.add_heading('4. COMPARACIÓN DE LOS SEIS FLUJOS NATIVOS', level=1)
    t = documento.add_table(rows=1, cols=9)
    for c, texto in zip(t.rows[0].cells, ('Caso / flujo', 'Estado', 'Barras', 'Cargas',
                                        'P/Q nominal (kW/kvar)', 'MT mín./máx.', 'MT fuera',
                                        'Punto (p.u.)', 'Líneas >100 %')):
        c.text = texto
    barras_csv, equipos_csv = [], []
    for rol, modo, d in pruebas:
        red = d['red_proyecto']
        inv = d.get('inventario_nominal') or {}
        nominal = ('N/D' if inv.get('p_nominal_kw') is None or inv.get('q_nominal_kvar') is None
                   else f'{inv["p_nominal_kw"]:.2f} / {inv["q_nominal_kvar"]:.2f}')
        if d.get('referencia_no_convergente'):
            valores = (f'{ROLES[rol]} / {modo}', 'No converge / no evaluable sin obras',
                       str(inv['barras']), str(inv['cargas']), nominal, 'N/C', 'N/C', 'N/C', 'N/C')
            for c, texto in zip(t.add_row().cells, valores):
                c.text = texto
            for b in d['objetos_nativos'].get('ElmTerm', []):
                if not b.get('outserv'):
                    barras_csv.append({'caso': ROLES[rol], 'estudio': modo, 'nivel': 'inventario',
                                       'nombre': b['nombre'], 'kv': b.get('uknom'), 'estado_flujo': 'No converge'})
            for clase in ('ElmLne', 'ElmTr2', 'ElmTr3'):
                equipos_csv += [{'caso': ROLES[rol], 'estudio': modo, 'elemento': e['nombre'],
                                 'clase': clase, 'estado_flujo': 'No converge'}
                                for e in d['objetos_nativos'].get(clase, []) if not e.get('outserv')]
            continue
        mt = red['tensiones_por_nivel']['mt']
        lineas = [e for e in red['medida']['elementos'] if e[1] == 'ElmLne']
        punto_mt = next(x for x in mt if x['nombre'] == plan['barra'])
        valores = (f'{ROLES[rol]} / {modo}', 'Converge', str(red['cantidad_barras']),
                   str(inv.get('cargas', 'N/D')), nominal,
                   f'{min(x["u_pu"] for x in mt):.4f} / {max(x["u_pu"] for x in mt):.4f}',
                   str(sum(not config.limites.tension_min_pu <= x['u_pu'] <= config.limites.tension_max_pu for x in mt)),
                   f'{min(x for x in punto_mt["fases"].values() if x is not None):.4f}',
                   str(sum(e[2] > config.limites.cargabilidad_max_pct for e in lineas)))
        for c, texto in zip(t.add_row().cells, valores):
            c.text = texto
        for nivel, filas in red['tensiones_por_nivel'].items():
            barras_csv += [{'caso': ROLES[rol], 'estudio': modo, 'nivel': nivel, 'estado_flujo': 'Converge', **x,
                            **{f'u_{f}': v for f, v in x['fases'].items()}} for x in filas]
        equipos_csv += [{'caso': ROLES[rol], 'estudio': modo, 'elemento': n, 'clase': cl, 'cargabilidad_pct': v,
                         'estado_flujo': 'Converge'}
                        for n, cl, v in red['medida']['elementos']]
    documento.add_paragraph('Las cifras de este cuadro abarcan el proyecto completo y los elementos '
                            'trasladados a la SET nueva. P/Q nominal son entradas del inventario, no resultados '
                            'del flujo. N/C significa no calculable por falta de convergencia; no equivale '
                            'a cero. Los CSV mantienen vacías esas mediciones, sin lecturas parciales.')
    documento.add_heading('5. OBRAS Y VERIFICACIÓN DEL ESTADO CON PROYECTO', level=1)
    for texto in plan.get('diagnostico', []):
        documento.add_paragraph(texto)
    peores = sorted(casos['con']['red_proyecto']['medida']['elementos'], key=lambda e: e[2], reverse=True)[:20]
    t = documento.add_table(rows=1, cols=3)
    for c, texto in zip(t.rows[0].cells, ('Elemento', 'Clase', 'Cargabilidad (%)')):
        c.text = texto
    for nombre, clase, carga in peores:
        for c, texto in zip(t.add_row().cells, (nombre, clase, f'{carga:.2f}')):
            c.text = texto
    documento.add_heading('6. PROCEDENCIA Y FUNDAMENTO ACADÉMICO', level=1)
    for texto in plan['referencias']:
        documento.add_paragraph(texto)
    if operacion is not None:
        ruta_operacion = Path(plan['operacion_verificada'])
        procedencia.append({'ruta': str(ruta_operacion),
                            'sha256': hashlib.sha256(ruta_operacion.read_bytes()).hexdigest()})
        documento.add_heading('7. CARGAS Y VARIACIONES VERIFICADAS AL REABRIR', level=1)
        cargas = operacion['cargas_previstas_relectura']['cargas']
        documento.add_paragraph(
            f'{len(cargas)} cargas previstas conservan su demanda nominal y su variación. '
            'El anexo de conectividad identifica la fuente por rutas físicas; '
            'los nombres de los alimentadores no sustituyen esa comprobación.')
        tabla = documento.add_table(rows=1, cols=5)
        for celda, texto in zip(tabla.rows[0].cells, ('ID', 'Carga / solicitud', 'kW / kvar', 'Punto de conexión', 'Variación')):
            celda.text = texto
        for i, carga in enumerate(cargas, 1):
            valores = (str(i), carga['sed'], f"{carga['kw']:.2f} / {carga['kvar']:.2f}",
                       PureWindowsPath(carga['barra_carga']).stem,
                       PureWindowsPath(carga['variacion']).stem)
            for celda, texto in zip(tabla.add_row().cells, valores):
                celda.text = texto
        documento.add_heading('8. REGISTRO DE LAS OBRAS Y MANIOBRAS APLICADAS', level=1)
        documento.add_paragraph(
            'Las rutas completas, los cubículos y los registros de las etapas se conservan '
            'en el informe nativo de operación, identificado mediante SHA-256. '
            'Esta verificación corresponde al modelo DIgSILENT; no constituye un acta de obra en campo.')
        tabla = documento.add_table(rows=1, cols=4)
        for celda, texto in zip(tabla.rows[0].cells, ('ID', 'Elemento', 'Cambio aplicado', 'Variación propia')):
            celda.text = texto
        for i, obra in enumerate(operacion['variaciones_creadas'], 1):
            valores = (str(i), PureWindowsPath(obra['elemento']).stem,
                       '; '.join(f'{k}={PureWindowsPath(v).stem if isinstance(v, str) else (f"{v:.5f} km" if k == "dline" else v)}'
                                 for k, v in obra['atributos'].items()), obra['nombre'])
            for celda, texto in zip(tabla.add_row().cells, valores):
                celda.text = texto
    # La plantilla trae sellos de otro informe: no constituyen firmas de esta evaluación.
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    for seccion in documento.sections:
        for pie in (seccion.footer, seccion.first_page_footer, seccion.even_page_footer):
            for child in list(pie._element):
                pie._element.remove(child)
            p = pie.add_paragraph('Evaluación técnica del modelo · Página ')
            for campo in ('PAGE', 'NUMPAGES'):
                if campo == 'NUMPAGES':
                    p.add_run(' de ')
                f = OxmlElement('w:fldSimple')
                f.set(qn('w:instr'), campo)
                p._p.append(f)
    for p in documento.paragraphs:
        if p.style.name.startswith('Heading'):
            p.paragraph_format.keep_with_next = True
            p.style.font.color.rgb = RGBColor(0, 0, 0)
            # El modelo numera automáticamente los títulos; estos ya llevan su numeral.
            num = OxmlElement('w:numPr')
            ident = OxmlElement('w:numId')
            ident.set(qn('w:val'), '0')
            num.append(ident)
            p._p.get_or_add_pPr().append(num)
    for t in documento.tables:
        es_registro_obras = len(t.columns) == 4 and t.cell(0, 0).text == 'ID' and t.cell(0, 1).text == 'Elemento'
        es_registro_cargas = len(t.columns) == 5 and t.cell(0, 0).text == 'ID' and t.cell(0, 1).text == 'Carga / solicitud'
        anchos = ([0.8, 4.2, 5.4, 5.5] if es_registro_obras else
                  [0.8, 4.5, 2.1, 4.1, 4.4] if es_registro_cargas else None)
        if anchos:
            t.autofit = False
            for columna, ancho in zip(t.columns, anchos):
                columna.width = Cm(ancho)
        for i, row in enumerate(t.rows):
            if anchos:
                for celda, ancho in zip(row.cells, anchos):
                    celda.width = Cm(ancho)
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            if i == 0:
                row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            for c in row.cells:
                for p in c.paragraphs:
                    if len(t.rows) <= 6 and i < len(t.rows) - 1:
                        p.paragraph_format.keep_with_next = True
                    for run in p.runs:
                        run.font.size = Pt(8.5 if es_registro_obras else 9)
    documento.save(destino)
    for sufijo, filas, claves in (
        ('barras', barras_csv, ['caso', 'estudio', 'estado_flujo', 'nivel', 'nombre', 'kv', 'u_pu', 'u_A', 'u_B', 'u_C']),
        ('equipos', equipos_csv, ['caso', 'estudio', 'estado_flujo', 'elemento', 'clase', 'cargabilidad_pct'])):
        with destino.with_name(destino.stem + f'_{sufijo}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=claves, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(filas)
    resumen = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    resumen['procedencia'] = procedencia
    resumen['plan'] = plan
    destino.with_suffix('.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding='utf-8')
    return resumen


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', required=True, type=Path, help='Plan de los informes nativos guardados')
    p.add_argument('--salida', required=True, type=Path, help='Documento Word que se generará')
    args = p.parse_args(argv)
    try:
        resumen = generar(json.loads(args.plan.read_text(encoding='utf-8')), args.salida,
                          Path(__file__).resolve().parents[1])
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        p.exit(2, f'No se pudo generar el informe: {exc}\n')
    print(json.dumps({'informe': str(args.salida), 'factible': resumen['factible'], 'huecos': resumen['huecos']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
