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
from datetime import date
from pathlib import Path

from convertersmartgrid.informe_docx import (
    DatosFactibilidad,
    escribir_informe_factibilidad,
)
from convertersmartgrid.informes import Caso, ConfigInforme, Encabezado, Solicitud
from convertersmartgrid.libros_informe import DatosPerdidas
from convertersmartgrid.mapa_informe import imagenes_del_estado, ubicacion_del_cliente
from convertersmartgrid.perfil_empresa import datos_perfil

ROLES = {'sin': 'Sin proyecto', 'cargas': 'Cargas nuevas', 'con': 'Con proyecto'}


def leer_caso(ruta: Path, project: str, caso: str) -> dict:
    """Impide utilizar otro proyecto, otro caso o una captura parcial como evidencia."""
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if datos.get('project') != project:
        raise ValueError(f'{ruta.name}: no corresponde al proyecto {project}.')
    if datos.get('caso') != caso or datos.get('estudio') not in ('flujo', 'flujo_desequilibrado'):
        raise ValueError(f'{ruta.name}: no corresponde al caso o al estudio solicitado.')
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
    perfiles = datos_perfil()
    config = ConfigInforme.de_perfil(perfiles, raiz).con_limites(**plan['limites'])
    casos, pruebas, procedencia = {}, [], []
    for rol, nombre in ROLES.items():
        for modo in ('flujo', 'flujo_desequilibrado'):
            ruta = Path(plan['estudios'][rol][modo])
            d = leer_caso(ruta, project, nombre)
            if d['estudio'] != modo:
                raise ValueError(f'{ruta.name}: el modo del flujo no coincide con el plan.')
            pruebas.append((rol, modo, d))
            procedencia.append({'ruta': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest()})
            if modo == 'flujo_desequilibrado':
                casos[rol] = d
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagenes = {}
    encuadre = {'barras': [b for d in casos.values() for b in d['geo_proyecto']['barras']],
                'tramos': [t for d in casos.values() for t in d['geo_proyecto']['tramos']]}
    for rol, d in casos.items():
        clave = {'sin': 'actual', 'cargas': 'cargas', 'con': 'proyectado'}[rol]
        imagenes[clave] = imagenes_del_estado(
            d['geo_proyecto'], destino.parent / f'{destino.stem}_figuras', f'{destino.stem}_{rol}',
            estado=ROLES[rol], alimentador=plan['alcance'],
            bandas_tension=config.bandas_tension_pct, bandas_carga=config.bandas_cargabilidad_pct,
            cliente=(plan['barra'], plan['solicitud']['cliente']), red=d['red_proyecto'],
            limites=(config.limites.tension_min_pu, config.limites.tension_max_pu,
                     config.limites.cargabilidad_max_pct),
            referencia=casos['cargas'] if rol == 'con' else None,
            obras_aplicadas=plan.get('obras', ()), obras_activas=d.get('obras_activas', ()),
            vinculos_equipos=plan.get('vinculos_equipos', {}),
            encuadre=encuadre)
    sol = dict(plan['solicitud'])
    sol['fecha_solicitud'] = date.fromisoformat(sol['fecha_solicitud'])
    solicitud = Solicitud(**sol)
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
        actual=Caso.desde_medida('Estado actual', casos['sin']['red_proyecto']['medida'], config.limites),
        cargas=Caso.desde_medida('Con cargas, sin obras', casos['cargas']['red_proyecto']['medida'], config.limites),
        proyectado=Caso.desde_medida('Con proyecto', casos['con']['red_proyecto']['medida'], config.limites),
        solicitud=solicitud, codigo_punto=plan['codigo_punto'], punto_diseno=punto_diseno,
        solicitudes_vigentes=True, con_obras=bool(casos['con'].get('obras_activas')),
        libro=DatosPerdidas(**plan['perdidas_reconocidas']), imagenes=imagenes,
        fuentes=plan['fuentes'], observaciones=plan['observaciones'],
        incluir_transformador_set=False, perdidas_instantaneas=True, numero=plan.get('numero'))
    huecos = escribir_informe_factibilidad(config, destino, datos)
    if huecos:
        raise ValueError('El informe conserva huecos: ' + ', '.join(huecos))
    documento = docx.Document(destino)
    documento.add_heading('4. COMPARACIÓN DE LOS SEIS FLUJOS NATIVOS', level=1)
    t = documento.add_table(rows=1, cols=7)
    for c, texto in zip(t.rows[0].cells, ('Caso / flujo', 'Barras', 'MT mín.', 'MT máx.', 'MT fuera', 'Punto (p.u.)', 'Líneas >100 %')):
        c.text = texto
    barras_csv, equipos_csv = [], []
    for rol, modo, d in pruebas:
        red = d['red_proyecto']
        mt = red['tensiones_por_nivel']['mt']
        lineas = [e for e in red['medida']['elementos'] if e[1] == 'ElmLne']
        punto_mt = next(x for x in mt if x['nombre'] == plan['barra'])
        valores = (f'{ROLES[rol]} / {modo}', str(red['cantidad_barras']),
                   f'{min(x["u_pu"] for x in mt):.4f}', f'{max(x["u_pu"] for x in mt):.4f}',
                   str(sum(not config.limites.tension_min_pu <= x['u_pu'] <= config.limites.tension_max_pu for x in mt)),
                   f'{min(x for x in punto_mt["fases"].values() if x is not None):.4f}',
                   str(sum(e[2] > config.limites.cargabilidad_max_pct for e in lineas)))
        for c, texto in zip(t.add_row().cells, valores):
            c.text = texto
        for nivel, filas in red['tensiones_por_nivel'].items():
            barras_csv += [{'caso': ROLES[rol], 'estudio': modo, 'nivel': nivel, **x,
                            **{f'u_{f}': v for f, v in x['fases'].items()}} for x in filas]
        equipos_csv += [{'caso': ROLES[rol], 'estudio': modo, 'elemento': n, 'clase': cl, 'cargabilidad_pct': v}
                        for n, cl, v in red['medida']['elementos']]
    documento.add_paragraph('Las cifras de este cuadro abarcan el proyecto completo y los elementos '
                            'trasladados a COPARA. Los CSV anexos contienen todas las barras y equipos.')
    documento.add_heading('5. OBRAS E INCUMPLIMIENTOS DEL ESTADO CON PROYECTO', level=1)
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
    # La plantilla trae sellos de otro informe: no constituyen firmas de esta evaluación.
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

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
        for i, row in enumerate(t.rows):
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            if i == 0:
                row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            for c in row.cells:
                for p in c.paragraphs:
                    if len(t.rows) <= 6 and i < len(t.rows) - 1:
                        p.paragraph_format.keep_with_next = True
                    for run in p.runs:
                        run.font.size = Pt(9)
    documento.save(destino)
    for sufijo, filas, claves in (
        ('barras', barras_csv, ['caso', 'estudio', 'nivel', 'nombre', 'kv', 'u_pu', 'u_A', 'u_B', 'u_C']),
        ('equipos', equipos_csv, ['caso', 'estudio', 'elemento', 'clase', 'cargabilidad_pct'])):
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
