"""047:RF-11 a RF-15 — metodología de maestro/alumno sin promoción ficticia."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_curriculo_y_derivados_no_cruzan_particiones():
    """047:RF-11 / 047:RF-12 — cada plantilla permanece en su partición; no son humanos."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, particionar_registros
    registros, manifiesto = preparar_corpus({}, [], por_familia=3)
    p = particionar_registros(registros, PoliticaEvaluacion(modo='agente'))
    assert p.entrenamiento and p.calibracion and p.prueba
    assert manifiesto['maestro']['votos_por_anotacion'] == 1
    assert not manifiesto['maestro']['logits_del_maestro_disponibles']
    assert all(r['quality'] != 'gold_human' for r in registros)


def test_muestra_humana_pequena_no_se_disfraza_de_200():
    """047:RF-13 — conservar el denominador real sin bloquear solo por ser menor de 200."""
    from convertersmartgrid.asistente.destilacion_integral import decidir_promocion
    m = {'acierto_tarea': 1.0, 'f1_datos': 1.0, 'ejemplos': 9999}
    r = decidir_promocion(m, {**m, 'ejemplos': 5}, {'convertir': m}, None)
    assert r['status'] == 'RECHAZADO' and not r['gates']['approved']
    assert r['ordenes_humanas'] == 5 and r['confirmacion_obligatoria']


def test_mala_familia_no_se_oculta_en_media():
    """047:RF-13 — una familia bajo puerta no se compensa con una media perfecta."""
    from convertersmartgrid.asistente.destilacion_integral import decidir_promocion
    m = {'acierto_tarea': 1.0, 'f1_datos': 1.0, 'ejemplos': 250}
    r = decidir_promocion(m, m, {'convertir': {**m, 'acierto_tarea': .5}}, None)
    assert r['status'] == 'RECHAZADO' and not r['gates']['approved']


def test_archivo_de_corpus_alterado_no_entrena(tmp_path):
    """047:RF-12 / 047:RF-14 — la huella incluye etiquetas, plantillas y custodias."""
    from convertersmartgrid.asistente.destilacion_integral import guardar_corpus, leer_corpus, preparar_corpus
    filas, meta = preparar_corpus({}, [], por_familia=2)
    guardar_corpus(tmp_path, filas, meta)
    assert leer_corpus(tmp_path)[1]['dataset_hash'] == meta['dataset_hash']
    ruta = tmp_path / 'corpus.json'
    datos = json.loads(ruta.read_text(encoding='utf-8')); datos[0]['tarea'] = 'estado'
    datos[0]['texto'] += ' alteracion'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(ValueError, match='integridad'):
        leer_corpus(tmp_path)


def test_semillas_se_eligen_por_seleccion_sin_test():
    """047:RF-12 — el selector no recibe métricas de prueba."""
    from convertersmartgrid.asistente.destilacion_integral import elegir_candidato
    filas = [{'semilla': 11, 'metodo': 'supervisado', 'seleccion': {'macro_tarea': .9, 'f1_datos': .8}},
             {'semilla': 23, 'metodo': 'destilado', 'seleccion': {'macro_tarea': .95, 'f1_datos': .85}}]
    assert elegir_candidato(filas)['semilla'] == 23


def test_guardado_estandar_conserva_temperatura(tmp_path, monkeypatch):
    """047:RF-14 — guardar pesos por la API vigente no descarta la calibración."""
    from convertersmartgrid.asistente import transformer as tr
    from convertersmartgrid.asistente.tareas import TAREAS
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    cfg = tr.Configuracion(dim=8, capas=1, cabezas=2, epocas=1)
    red = tr.construir_red(4, {'tarea': len(TAREAS)}, cfg, len(tr.ETIQUETAS))
    modelo = tr.ModeloOrdenes(red, {'a': 3}, sorted(TAREAS), cfg, temperatura=2.5)
    version = tr.guardar(modelo, {})
    meta = json.loads((tr.raiz_modelos() / version / 'modelo.json').read_text(encoding='utf-8'))
    assert meta['temperatura'] == 2.5


def test_cobertura_incompleta_no_aprueba():
    """047:RF-13 — cien por ciento en una sola tarea no certifica el catálogo completo."""
    from convertersmartgrid.asistente.destilacion_integral import decidir_promocion
    m = {'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 200}
    assert decidir_promocion(m, m, {'estado': m}, {'estado': m, 'convertir': m})['status'] == 'RECHAZADO'


def test_correccion_conflictiva_no_desaparece():
    """047:RF-11 / 047:RF-13 — duplicar el texto no autoriza ignorar nuevas entidades."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    filas = [{'texto': 'convierte AB101', 'tarea': 'convertir', 'datos': [], 'origen': 'confirmado'},
             {'texto': 'convierte AB101', 'tarea': 'convertir', 'datos': [(9, 14, 'alimentadores')], 'origen': 'corregido'}]
    with pytest.raises(ValueError, match='contradictorias'):
        preparar_corpus({}, filas, por_familia=1)


def test_conflictos_del_generador_quedan_en_cuarentena():
    """047:RF-11 / 047:RF-13 — se audita la expansión completa, no solo un lote diminuto."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.evaluacion_modelos import texto_canonico
    filas, meta = preparar_corpus({}, [], por_familia=80)
    assert meta['cuarentena_sintetica_conflictos'] > 0
    assert not any(texto_canonico(r['texto']) == 'quiero que convierte todos los alimentadores' for r in filas)


def test_cli_informe_json_funciona_con_stdout_ascii(tmp_path):
    """047:RF-14 — el estado real no se convierte en error por la consola de Windows."""
    herramienta = Path(__file__).resolve().parents[1] / 'tools/asistente_destilar.py'
    env = {**os.environ, 'PYTHONIOENCODING': 'ascii', 'CSG_ASISTENTE_DATA': str(tmp_path / 'datos')}
    r = subprocess.run([sys.executable, str(herramienta), 'preparar', '--destino', str(tmp_path / 'corpus'),
                        '--por-familia', '1'], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout
    assert json.loads(r.stdout)['ok']


def test_casos_funcionales_cubren_catalogo_sin_usar_train():
    """047:RF-15 — el ensayo amplio no se limita a tres órdenes fáciles."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus, casos_funcionales
    from convertersmartgrid.asistente.tareas import TAREAS
    filas, _ = preparar_corpus({}, [], por_familia=2)
    casos = casos_funcionales(filas)
    assert {r['tarea'] for r in casos} == set(TAREAS)
    assert all(r['particion'] == 'prueba' for r in casos)


def test_reapertura_sin_predicciones_no_acredita_exito(tmp_path):
    """047:RF-14 — all([]) no acredita que un alumno se reabrió y funcionó."""
    from convertersmartgrid.asistente.destilacion_integral import verificar_reapertura
    (tmp_path / 'readback.json').write_text(json.dumps({'textos': [], 'predicciones': []}), encoding='utf-8')
    with pytest.raises(ValueError, match='predicciones'):
        verificar_reapertura(tmp_path)
