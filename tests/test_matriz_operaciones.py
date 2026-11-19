"""026:RF-51 — matriz de operaciones del asistente derivada del código (A0 del plan de control integral).

Nada decía qué operación del asistente está probada, cuál falta y quién la lleva. La matriz se deriva del catálogo de
tareas, del inventario del equipo, de las vías directas con recibo y de las lecturas, con las tareas abiertas de las specs
del asistente leídas por el lector único de specs; separa lo declarado, lo que tiene prueba y la aceptación del dominio.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ / 'tools' / 'matriz_operaciones.py'


def _modulo():
    assert HERRAMIENTA.is_file(), '026:RF-51: no hay matriz de operaciones del asistente (tools/matriz_operaciones.py)'
    spec = importlib.util.spec_from_file_location('matriz_operaciones', HERRAMIENTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _estado_specs():
    sys.path.insert(0, str(RAIZ / 'tools'))
    try:
        import estado_specs
    finally:
        sys.path.pop(0)
    return estado_specs


def test_026_rf51_todas_las_tareas_vias_directas_y_lecturas_estan():
    """026:RF-51: una fila por tarea del catálogo, por vía directa con recibo y por lectura del proyecto."""
    from convertersmartgrid.aplicacion.asistente.equipo import inventario_equipo
    from convertersmartgrid.aplicacion.asistente.tareas import TAREAS

    m = _modulo().matriz(RAIZ)
    ops = {f['operacion'] for f in m['operaciones']}
    assert {f'tarea.{n}' for n in TAREAS} <= ops
    assert {'directa.asistente_entrenar', 'directa.mejoras.decision', 'directa.modelos_en_uso.activar'} <= ops
    lecturas = {h['nombre'] for h in inventario_equipo()['lectura_proyecto']['herramientas']}
    assert {f'lectura.{n}' for n in lecturas} <= ops
    porta = {f['operacion']: f for f in m['operaciones']}
    for n, t in TAREAS.items():
        f = porta[f'tarea.{n}']
        assert f['escribe'] == t.escribe and f['funcion'] == t.funcion


def test_026_rf51_los_niveles_no_se_mezclan():
    """026:RF-51: «con prueba que la cita» no es aceptación del dominio, que la matriz nunca da por medida."""
    from convertersmartgrid.aplicacion.asistente.equipo import inventario_equipo

    m = _modulo().matriz(RAIZ)
    assert all(f['aceptacion_dominio'] == 'no medida' for f in m['operaciones'])
    assert m['recuento']['aceptadas_en_el_dominio'] == 0
    assert m['recuento']['operaciones'] == len(m['operaciones'])
    assert m['autonomia_habilitada'] is inventario_equipo()['autonomia_habilitada']


def test_026_rf51_los_huecos_salen_del_lector_unico_de_specs():
    """026:RF-51: cada tarea abierta de 026, 047 y 070, y solo esas, es un hueco con su criterio y su responsable."""
    mod = _modulo()
    m = mod.matriz(RAIZ)
    es = _estado_specs()
    abiertas = {f'{s.numero}:{t.id}' for s in es.leer_specs(RAIZ) if s.numero in mod.SPECS_DEL_ASISTENTE
                for t in s.abiertas}
    assert {p['operacion'] for p in m['pendientes']} == abiertas
    assert all(p['estado'] == 'pendiente' and p['responsable'] for p in m['pendientes'])


def test_026_rf51_comprobar_falla_con_operacion_sin_prueba_hueco_sin_dueno_o_dueno_de_tarea_cerrada(monkeypatch):
    """026:RF-51: los tres casos que la comprobación no acepta."""
    mod = _modulo()
    m = mod.matriz(RAIZ)
    malo = {**m, 'operaciones': m['operaciones'] + [{'operacion': 'tarea.inventada', 'estado': 'declarada'}],
            'pendientes': m['pendientes'] + [{'operacion': '026:T99', 'que': 'algo', 'criterio': '', 'responsable': ''}]}
    monkeypatch.setitem(mod.RESPONSABLES, '026:T24', 'quien sea')        # T24 ya está cerrada
    texto = '\n'.join(mod.problemas(malo))
    assert 'tarea.inventada: ninguna prueba la cita' in texto
    assert '026:T99: hueco sin responsable' in texto and '026:T99: hueco sin «Hecho cuando»' in texto
    assert '026:T24: ya no está abierta' in texto


def test_026_rf51_el_arbol_pasa_la_comprobacion():
    """026:RF-51: sobre el árbol, ninguna operación sin prueba y ningún hueco sin dueño (``--comprobar`` en rc=0)."""
    mod = _modulo()
    assert mod.problemas(mod.matriz(RAIZ)) == []
    assert mod.main(['--comprobar']) == 0


def test_026_rf51_las_vias_directas_se_sacan_del_codigo(tmp_path):
    """026:RF-51: cada ``recibo_directo('…')`` del paquete es una vía directa; un texto que no es llamada, no."""
    paquete = tmp_path / 'src' / 'convertersmartgrid'
    paquete.mkdir(parents=True)
    (paquete / 'uno.py').write_text("equipo.recibo_directo('modelo.activar', responsable='op', decision='clic')\n"
                                    "x = 'recibo_directo(\"no_es_llamada\")'\n", encoding='utf-8')
    (paquete / 'dos.py').write_text("recibo_directo('reentreno', responsable='op', decision='auto')\n", encoding='utf-8')
    vias = _modulo().vias_directas(tmp_path)
    assert [v['herramienta'] for v in vias] == ['modelo.activar', 'reentreno']


def test_026_rf51_la_salida_va_a_un_fichero_fuera_de_git(tmp_path):
    """026:RF-51: ``--salida`` escribe la tabla o el JSON donde se le diga, de forma atómica."""
    mod = _modulo()
    assert mod.main(['--salida', str(tmp_path / 'm.md')]) == 0
    assert (tmp_path / 'm.md').read_text(encoding='utf-8').startswith('# Matriz de operaciones del asistente')
    assert mod.main(['--salida', str(tmp_path / 'm.json')]) == 0
    assert '"pendientes"' in (tmp_path / 'm.json').read_text(encoding='utf-8')
