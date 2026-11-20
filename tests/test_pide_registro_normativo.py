"""072:RF-47 — el ranking del PIDE cita su norma con el estado legal del registro normativo.

Auditoría PM-09 del Plan Maestro: la priorización del PIDE citaba como norma los criterios prepublicados con la
RM 428-2017-MEM/DM sin consultar el registro normativo, que el PIT y el VAD sí consultan. Estas pruebas usan registros
sintéticos (títulos, citas y huellas inventados para la prueba) y el registro real solo para comprobar que la RM 428
sigue como proyecto. Ninguna empresa, alimentador ni SED real.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from openpyxl import load_workbook

from convertersmartgrid.aplicacion import pide_economia as ec
from convertersmartgrid.aplicacion.pide import escribir_formatos
from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
ACTO = 'RM 428-2017-MEM/DM'
PREPUBLICADA = 'criterio de una norma prepublicada (sin vigencia comprobada)'
HEURISTICO = 'heurístico, no conforme'
H = 'c' * 64

INFORME = {'anios': [
    {'anio': 0, 'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.90, 'problemas': [
        {'tipo': 'tension', 'elemento': 'B9', 'valor': 0.90, 'limite': 0.95, 'causa': 'caida_de_tension',
         'evidencia': 'e', 'kv': 10.0, 'alimentador': 'F1'}]},
    {'anio': 4, 'cabeceras_kw': {'F1': 1170.0}, 'vm_min': 0.88, 'problemas': [
        {'tipo': 'tension', 'elemento': 'B9', 'valor': 0.88, 'limite': 0.95, 'causa': 'caida_de_tension',
         'evidencia': 'e', 'kv': 10.0, 'alimentador': 'F1'}]}]}
PLAN = {'tasa_regulada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20, 'anios_pide': [4, 5, 6, 7],
        'pesos_art_15_3': {'subsanacion_calidad': 1}}
COSTOS = {'bancos': {'costo_unitario': 3500.0, 'unidad': 'Und', 'obras': 1, 'denominacion': 'Banco'}}


def _registro(tmp_path, estado, **norma):
    datos = {'acto': ACTO, 'titulo': 'Criterios de prueba del PIDE', 'estado_juridico': estado, **norma,
             'reglas': [{'clave': 'vinculo.pide.criterios_en_consulta', 'valor': 'prueba', 'pagina': '1',
                         'articulo_o_anexo': 'art. 1', 'cita_literal': '«cita de prueba»',
                         'interpretacion': 'motivo de prueba del registro'}]}
    if estado in ('vigente_comprobada', 'modificada'):
        datos.setdefault('sha256', H)
    carpeta = tmp_path / f'registro_{estado}'
    carpeta.mkdir()
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [datos]}),
                                    encoding='utf-8')
    return cargar_registro(carpeta)


def _propuesta(registro, **kw):
    assert 'registro' in inspect.signature(ec.propuesta_pide).parameters, \
        'propuesta_pide no recibe el registro normativo: el ranking no consulta el estado legal de su norma'
    return ec.propuesta_pide(INFORME, PLAN, costos=COSTOS, bancos_kvar={10.0: 300.0}, registro=registro, **kw)


def _traza():
    traza = getattr(ec, 'traza_normativa_pide', None)
    assert traza is not None, 'falta la traza normativa del ranking del PIDE (072:RF-47)'
    return traza


def test_prepublicada_nunca_sale_como_vigente(tmp_path):
    """072:RF-47 — con la norma «prepublicada», cada peso y criterio lo dice y nada la presenta como vigente."""
    p = _propuesta(_registro(tmp_path, 'prepublicada', fecha_publicacion='2001-03-10'))
    n = p.get('normativa')
    assert n, 'la propuesta no lleva la base normativa del ranking'
    assert n['acto'] == ACTO and n['estado'] == 'prepublicada' and n['vigente'] is False
    assert n['leyenda'] == PREPUBLICADA and 'vigente' not in n['leyenda']
    assert n['motivo'] and n['cita'].startswith(ACTO)
    criterios = {c['criterio']: c for c in n['criterios']}
    assert {'costo_kw', 'costo_kwh', 'costo_usuario', 'costo_km', 'subsanacion_calidad'} <= set(criterios)
    assert criterios['subsanacion_calidad']['peso'] == 1
    for c in criterios.values():
        assert c['norma'] == ACTO and c['estado'] == 'prepublicada' and c['leyenda'] == PREPUBLICADA
        assert c['vigente'] is False and c['articulo']
    assert p['obras'] and all(o['normativa']['estado'] == 'prepublicada'
                              and o['normativa']['leyenda'] == PREPUBLICADA for o in p['obras'])


def test_vigente_comprobada_con_su_clausula(tmp_path):
    """072:RF-47 — la vigencia sale de la cláusula de la norma registrada."""
    n = _propuesta(_registro(tmp_path, 'vigente_comprobada', vigencia_desde='2001-01-01'))['normativa']
    assert n['estado'] == 'vigente_comprobada' and n['vigente'] is True
    assert n['vigencia_desde'] == '2001-01-01' and 'cláusula' in n['vigencia_motivo']
    assert 'prepublicada' not in n['leyenda'] and HEURISTICO not in n['leyenda']
    assert all(c['vigente'] is True for c in n['criterios'])


def test_art_109_solo_si_la_norma_calla(tmp_path):
    """072:RF-47 — sin cláusula de vigencia, rige desde el día siguiente de su publicación (art. 109)."""
    traza = _traza()
    registro = _registro(tmp_path, 'vigente_comprobada', fecha_publicacion='2001-03-10')
    n = traza(registro, '2001-03-11')
    assert n['vigencia_desde'] == '2001-03-11' and '109' in n['vigencia_motivo'] and n['vigente'] is True
    antes = traza(registro, '2001-03-10')
    assert antes['vigente'] is False and antes['leyenda'].startswith(HEURISTICO) and antes['motivo']


def test_no_verificada_y_sin_registro_son_heuristicos(tmp_path):
    """072:RF-47 — una norma sin texto comprobado, o sin registro, deja el criterio como heurístico con su motivo."""
    n = _propuesta(_registro(tmp_path, 'no_verificada'))['normativa']
    assert n['estado'] == 'no_verificada' and n['vigente'] is False
    assert n['leyenda'] == HEURISTICO and 'no_verificada' in n['motivo']
    sin = _propuesta(None)['normativa']
    assert sin['vigente'] is False and sin['leyenda'] == HEURISTICO and 'registro normativo' in sin['motivo']


def test_la_traza_no_cambia_el_ranking(tmp_path):
    """072:RF-47 — solo trazabilidad: prioridades, puntajes e inversiones iguales con y sin registro."""
    con = _propuesta(_registro(tmp_path, 'prepublicada'))
    sin = ec.propuesta_pide(INFORME, PLAN, costos=COSTOS, bancos_kvar={10.0: 300.0})
    clave = [(o['codigo'], o['prioridad'], o['puntaje'], o['ci'], o['descartada']) for o in con['obras']]
    assert clave == [(o['codigo'], o['prioridad'], o['puntaje'], o['ci'], o['descartada']) for o in sin['obras']]
    assert con['formatos'] == sin['formatos']


def test_el_libro_de_formatos_lleva_la_base_normativa(tmp_path):
    """072:RF-47 — el entregable en Excel dice el estado legal de cada criterio, sin presentarlo como vigente."""
    assert 'normativa' in inspect.signature(escribir_formatos).parameters, \
        'el libro de formatos del PIDE no recibe la base normativa del ranking'
    p = _propuesta(_registro(tmp_path, 'prepublicada'))
    ruta = escribir_formatos(tmp_path / 'pide.xlsx', p['formatos'], [], normativa=p['normativa'])
    libro = load_workbook(ruta)
    assert 'Base normativa' in libro.sheetnames
    celdas = [str(c) for fila in libro['Base normativa'].iter_rows(values_only=True) for c in fila if c is not None]
    assert ACTO in celdas and 'prepublicada' in celdas and PREPUBLICADA in celdas
    assert 'vigente' not in celdas and 'vigente_comprobada' not in celdas


def test_el_modulo_de_priorizacion_dice_el_estado(tmp_path):
    """072:RF-47 — el documento de priorización cita la norma con su estado y su leyenda."""
    from convertersmartgrid.adaptadores.informes_planeamiento import DatosPlaneamiento, _priorizacion

    assert 'normativa' in DatosPlaneamiento.__dataclass_fields__, \
        'el módulo de priorización no recibe la base normativa del ranking'
    p = _propuesta(_registro(tmp_path, 'prepublicada'))
    textos: list[str] = []

    class _Escritor:
        def titulo(self, t):
            textos.append(t)

        def parrafo(self, t):
            textos.append(t)

        def tabla(self, cabecera, filas):
            textos.extend(str(c) for f in filas for c in f)

    datos = DatosPlaneamiento(estudio=SimpleNamespace(detalle_pide=[4, 5, 6, 7]), formatos={},
                              obras=p['obras'], normativa=p['normativa'])
    _priorizacion(_Escritor(), datos)
    texto = ' '.join(textos)
    assert ACTO in texto and PREPUBLICADA in texto


def test_el_registro_real_tiene_los_criterios_como_proyecto():
    """072:RF-47 — con el registro del repositorio, la RM 428-2017-MEM/DM sale como prepublicada."""
    n = _traza()(cargar_registro(RAIZ / 'config' / 'normativa'), None)
    assert n['acto'] == ACTO and n['estado'] == 'prepublicada' and n['vigente'] is False
    assert n['leyenda'] == PREPUBLICADA
