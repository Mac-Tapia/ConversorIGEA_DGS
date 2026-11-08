"""043:RF-8 — el estado visible necesita evidencia, no el fin de un proceso."""
import json

from fastapi.testclient import TestClient

from convertersmartgrid.web.app import create_app


def _conjunto_unitario(tmp_path, monkeypatch, familia='transformer'):
    """Contrato de carga: archivos de prueba; no acredita un modelo entrenado."""
    from convertersmartgrid import aprendizaje_continuo as ac
    from convertersmartgrid.model_registry import RegistroModelo
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    reg = RegistroModelo(raiz / 'model_registry')
    artefactos = tmp_path / 'artefactos'; artefactos.mkdir()
    for nombre, contenido in [('modelo.json', '{}'), ('pesos.pt', 'pesos'), ('miembro_0.pt', 'miembro')]:
        (artefactos / nombre).write_text(contenido, encoding='utf-8')
    cid = reg.registrar_candidato(familia, model_manifest={'version': 'modelo-de-contrato'},
        dataset_manifest={}, metrics={}, decision={'status': 'PROMOVIDO', 'gates': {'approved': True}},
        smoke_reload={'ok': True}, artifacts=list(artefactos.iterdir()))['candidate_id']
    ciclo = {'estado': 'terminado', 'clave': 'a' * 64, 'snapshot_id': 'b' * 64,
        'candidatos': {familia: cid}}
    resultado = ac.publicar_conjunto(raiz / 'aprendizaje', reg, ciclo,
        retencion={familia: {'retiene': True}}, conjunta={'aprobado': True}, obligatorias=[familia])
    assert resultado['publicado']
    return raiz, reg, cid, resultado['conjunto']


def test_modelo_lenguaje_lee_conjunto_sin_reescribir_puntero(tmp_path, monkeypatch):
    """050:RF-7 — el consumidor carga la versión conjunta y conserva el puntero individual."""
    from convertersmartgrid.asistente import transformer, modelos_en_uso
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    transformer.raiz_modelos().mkdir(parents=True)
    transformer.promover('legado', 'línea base')
    puntero = transformer.raiz_modelos() / 'promovido.json'
    antes = puntero.read_bytes()
    _raiz, _reg, cid, _conjunto = _conjunto_unitario(tmp_path, monkeypatch)
    version = transformer.version_promovida()
    assert version == modelos_en_uso.version_de(cid)
    assert puntero.read_bytes() == antes
    assert (transformer.raiz_modelos() / version / 'pesos.pt').read_text(encoding='utf-8') == 'pesos'


def test_modelo_lenguaje_no_reutiliza_copia_corrupta_del_conjunto(tmp_path, monkeypatch):
    """050:RF-7 — la copia materializada también se verifica antes de cargar."""
    import pytest
    from convertersmartgrid.asistente import transformer
    _conjunto_unitario(tmp_path, monkeypatch)
    version = transformer.version_promovida()
    assert version
    (transformer.raiz_modelos() / version / 'pesos.pt').write_text('alterado', encoding='utf-8')
    with pytest.raises(ValueError, match='integridad'):
        transformer.version_promovida()


def test_modelo_lenguaje_sin_miembro_no_recurre_al_heredado(tmp_path, monkeypatch):
    """050:RF-7, 050:RF-8 — un conjunto configurado exige la familia que se pide."""
    import pytest
    from convertersmartgrid.asistente import transformer
    from convertersmartgrid.aprendizaje_continuo import CicloBloqueado
    _conjunto_unitario(tmp_path, monkeypatch, 'pinn')
    with pytest.raises(CicloBloqueado, match='transformer'):
        transformer.version_promovida()


def test_pinn_lee_artefactos_del_conjunto(tmp_path, monkeypatch):
    """050:RF-7 — ruta de carga y procedencia; no ejecuta una red ni acredita exactitud."""
    from types import SimpleNamespace
    from pathlib import Path
    from convertersmartgrid.digital_twin import oraculo
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    _raiz, reg, cid, conjunto = _conjunto_unitario(tmp_path, monkeypatch, 'pinn')
    llamadas = []
    def abrir(carpeta):
        llamadas.append(carpeta)
        return SimpleNamespace(version='modelo-de-contrato')
    monkeypatch.setattr(oraculo, '_abrir_carpeta', abrir)
    bufer = BuferEpisodios(tmp_path / 'twin')
    m = oraculo.cargar(bufer)
    assert m is not None and m.candidate_id == cid and m.conjunto_id == conjunto['conjunto_id']
    carpeta = bufer.raiz / 'modelos' / cid
    assert llamadas == [carpeta] and m.version == cid
    assert (carpeta / 'miembro_0.pt').read_bytes() == (Path(reg.detalle('pinn', cid)['path']) / 'artifacts/miembro_0.pt').read_bytes()


def test_activar_individual_no_declara_exito_bajo_un_conjunto(tmp_path, monkeypatch):
    """050:RF-7 — cambiar un puntero ignorado no puede presentarse como activación."""
    import pytest
    from convertersmartgrid.aprendizaje_continuo import CicloBloqueado
    from convertersmartgrid.asistente import modelos_en_uso, transformer
    raiz, reg, _cid, conjunto = _conjunto_unitario(tmp_path, monkeypatch)
    datos = dict(model_manifest={'version': 'otro'}, dataset_manifest={}, metrics={},
        decision={'status': 'PROMOVIDO', 'gates': {'approved': True}}, smoke_reload={'ok': True},
        artifacts=list((tmp_path / 'artefactos').iterdir()))
    otro = reg.registrar_candidato('transformer', **datos)['candidate_id']
    with pytest.raises(CicloBloqueado, match='conjunto'):
        modelos_en_uso.activar('transformer', otro)
    assert not (transformer.raiz_modelos() / 'promovido.json').exists()
    assert reg.activo('transformer') is None
    from convertersmartgrid.aprendizaje_continuo import conjunto_activo
    assert conjunto_activo(raiz / 'aprendizaje')['conjunto_id'] == conjunto['conjunto_id']


def test_reversion_individual_bajo_conjunto_exige_reversion_conjunta(tmp_path, monkeypatch):
    """050:RF-7 — la reversión tampoco informa éxito sobre un puntero que no se carga."""
    import pytest
    from convertersmartgrid.aprendizaje_continuo import CicloBloqueado
    from convertersmartgrid.asistente import modelos_en_uso
    _conjunto_unitario(tmp_path, monkeypatch)
    with pytest.raises(CicloBloqueado, match='conjunto'):
        modelos_en_uso.volver_al_anterior('transformer')


def test_provisional_no_rompe_conjunto_ni_anota_activacion_falsa(tmp_path, monkeypatch):
    """050:RF-7 — una decisión provisional individual no cambia un conjunto publicado."""
    import pytest
    from convertersmartgrid.aprendizaje_continuo import CicloBloqueado
    from convertersmartgrid.asistente import modelos_en_uso
    _raiz, reg, _cid, _conjunto = _conjunto_unitario(tmp_path, monkeypatch)
    otro = reg.registrar_candidato('transformer', model_manifest={'version': 'provisional'},
        dataset_manifest={}, metrics={}, decision={'status': 'RECHAZADO', 'gates': {'approved': False}},
        smoke_reload={'ok': True}, artifacts=list((tmp_path / 'artefactos').iterdir()))['candidate_id']
    with pytest.raises(CicloBloqueado, match='conjunto'):
        modelos_en_uso.poner_provisional('transformer', otro, decidido_por='prueba', motivo='contrato')
    assert not (reg.raiz / 'transformer' / 'usos_provisionales.jsonl').exists()


def test_pinn_no_promueve_individual_bajo_conjunto(tmp_path, monkeypatch):
    """050:RF-7 — la PINN conserva el mismo contrato de publicación conjunta."""
    import pytest
    from convertersmartgrid.aprendizaje_continuo import CicloBloqueado
    from convertersmartgrid.digital_twin import oraculo
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    _conjunto_unitario(tmp_path, monkeypatch, 'pinn')
    bufer = BuferEpisodios(tmp_path / 'twin')
    (bufer.raiz / 'modelos').mkdir()
    with pytest.raises(CicloBloqueado, match='conjunto'):
        oraculo.promover(bufer, 'otro', 'prueba')
    assert not (bufer.raiz / 'modelos/promovido.json').exists()


def test_modelos_web_no_infiere_promocion(tmp_path, monkeypatch):
    """043:RF-8 — un informe sin candidato íntegro no prueba promoción."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    ruta = tmp_path / 'asistente/training/report.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({'complete': True, 'stages': [
        {'model': 'gru', 'status': 'PROMOVIDO'}]}), encoding='utf-8')
    with TestClient(create_app(tmp_path / 'web')) as client:
        respuesta = client.get('/api/asistente/modelos')
    assert respuesta.status_code == 200
    payload = respuesta.json()
    assert payload['schema_version'] == 1
    assert len(payload['familias']) == 7
    gru = next(f for f in payload['familias'] if f['familia'] == 'gru')
    assert gru['estado'] is None
    assert gru['bloqueos']
    assert not payload['complete']


def test_ausencia_de_informe_es_pendiente(tmp_path, monkeypatch):
    """043:RF-8 — la ausencia no se inventa como etapa entrenada ni rechazada."""
    from convertersmartgrid.web import services
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    payload = services.asistente_estado_modelos()
    assert all(f['estado'] is None for f in payload['familias'])
    assert not payload['complete']


def test_candidato_bloqueado_visible_sin_informe_global(tmp_path, monkeypatch):
    """043:RF-8 — la destilación registra su decisión sin fingir siete entrenamientos."""
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    datos = _payload(tmp_path)
    datos['decision'] = {'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False},
                         'fallos': ['tres órdenes humanas independientes']}
    c = registro.registrar_candidato('transformer', **datos)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['estado'] == 'BLOQUEADO_POR_DATOS' and fila['candidate_id'] == c['candidate_id']
    assert registro.activo('transformer') is None


def test_decision_reciente_no_queda_oculta_por_informe_viejo(tmp_path, monkeypatch):
    """043:RF-8 — se distingue última decisión de candidato y modelo que sigue activo."""
    import os
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    viejo = registro.registrar_candidato('transformer', **_payload(tmp_path))
    registro.promover('transformer', viejo['candidate_id'])
    reporte = raiz / 'training/report.json'; reporte.parent.mkdir()
    reporte.write_text(json.dumps({'stages': [{'model': 'transformer', 'status': 'PROMOVIDO',
                          'candidate_id': viejo['candidate_id']}]}), encoding='utf-8')
    os.utime(reporte, (1, 1))
    datos = _payload(tmp_path)
    datos['decision'] = {'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False}}
    nuevo = registro.registrar_candidato('transformer', **datos)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['estado'] == 'BLOQUEADO_POR_DATOS' and fila['candidate_id'] == nuevo['candidate_id']
    assert registro.activo('transformer')['candidate_id'] == viejo['candidate_id']


def test_consulta_modelos_no_relee_pesos_en_http(tmp_path, monkeypatch):
    """043:RF-8 — consultar estado usa manifiestos; no bloquea HTTP leyendo GB de pesos."""
    from pathlib import Path
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    candidato = registro.registrar_candidato('gru', **_payload(tmp_path))
    registro.promover('gru', candidato['candidate_id'])
    ruta = raiz / 'training/report.json'
    ruta.parent.mkdir()
    ruta.write_text(json.dumps({'complete': False, 'stages': [{
        'model': 'gru', 'status': 'PROMOVIDO', 'candidate_id': candidato['candidate_id']}]}), encoding='utf-8')
    original = Path.open
    def abrir(path, *args, **kwargs):
        if path.name == 'pesos.bin':
            pytest.fail('la petición HTTP abrió los pesos')
        return original(path, *args, **kwargs)
    import pytest
    monkeypatch.setattr(Path, 'open', abrir)
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'gru')
    assert fila['estado'] == 'PROMOVIDO'


def test_puntero_activo_corrupto_no_rompe_consulta(tmp_path, monkeypatch):
    """043:RF-8 — un registro ilegible se muestra bloqueado en vez de lanzar HTTP 500."""
    from convertersmartgrid.web import services
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    ruta = raiz / 'training/report.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({'complete': False, 'stages': [{
        'model': 'gru', 'status': 'PROMOVIDO', 'candidate_id': 'a' * 64}]}), encoding='utf-8')
    activo = raiz / 'model_registry/gru/active.json'
    activo.parent.mkdir(parents=True)
    activo.write_text('[1]', encoding='utf-8')
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'gru')
    assert fila['estado'] is None and fila['bloqueos']


def test_los_cuatro_estados_con_su_evidencia(tmp_path, monkeypatch):
    """043:RF-8 — cada estado terminal sale con su candidato y puertas; un PROMOVIDO, solo si está activo."""
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    ids = {}
    for familia, estado in (('transformer', 'PROMOVIDO'), ('clasificador', 'RECHAZADO'),
                            ('embeddings', 'BLOQUEADO_POR_DATOS'), ('qlora', 'ERROR_ENTORNO')):
        datos = _payload(tmp_path, status=estado, contenido=familia.encode())
        ids[familia] = registro.registrar_candidato(familia, **datos)['candidate_id']
    registro.promover('transformer', ids['transformer'])
    filas = {f['familia']: f for f in services.asistente_estado_modelos()['familias']}
    assert {f: filas[f]['estado'] for f in ids} == {'transformer': 'PROMOVIDO', 'clasificador': 'RECHAZADO',
                                                    'embeddings': 'BLOQUEADO_POR_DATOS', 'qlora': 'ERROR_ENTORNO'}
    assert all(filas[f]['candidate_id'] == c and filas[f]['report_path'].endswith('latest.json') for f, c in ids.items())
    assert filas['transformer']['gates']['approved'] is True and filas['clasificador']['gates']['approved'] is False
    assert filas['gru']['estado'] is None and filas['gru']['candidate_id'] is None


def test_promovido_del_registro_sin_activar_no_se_muestra_promovido(tmp_path, monkeypatch):
    """043:RF-8 — aprobar un candidato no es ponerlo en uso: sin activar, queda pendiente y dice por qué."""
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    RegistroModelo(raiz / 'model_registry').registrar_candidato('transformer', **_payload(tmp_path))
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['estado'] is None and any('sin candidato activo' in b for b in fila['bloqueos'])


def test_el_pronostico_se_ve_en_la_familia_gru(tmp_path, monkeypatch):
    """043:RF-8 — se registra por clase (046) y la web lo buscaba en ``gru``: una promoción real salía sin evidencia."""
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    from test_model_registry import _payload
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    registro = RegistroModelo(raiz / 'model_registry')
    datos = _payload(tmp_path)
    datos['model_manifest'] = {'algorithm': 'patchtst'}
    c = registro.registrar_candidato('pronostico_cabecera', **datos)['candidate_id']
    registro.promover('pronostico_cabecera', c)

    def gru():
        return next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'gru')
    assert gru()['estado'] == 'PROMOVIDO' and gru()['algorithm'] == 'patchtst' and gru()['candidate_id'] == c
    ruta = raiz / 'training/report.json'
    ruta.parent.mkdir()
    # Lo mismo desde el informe del coordinador, y otro nombre del registro no se acepta.
    import os
    from pathlib import Path
    ruta.write_text(json.dumps({'stages': [{'model': 'gru', 'status': 'PROMOVIDO', 'algorithm': 'patchtst', 'candidate_id': c,
                                            'modelo_registro': 'pronostico_cabecera'}]}), encoding='utf-8')
    futuro = Path(raiz / 'model_registry/pronostico_cabecera/latest.json').stat().st_mtime + 60
    os.utime(ruta, (futuro, futuro))
    assert gru()['estado'] == 'PROMOVIDO' and gru()['report_path'] == str(ruta)
    ruta.write_text(json.dumps({'stages': [{'model': 'gru', 'status': 'PROMOVIDO', 'candidate_id': c,
                                            'modelo_registro': 'transformer'}]}), encoding='utf-8')
    os.utime(ruta, (futuro, futuro))
    assert gru()['estado'] is None


def test_pinn_del_registro_en_uso_por_su_puntero(tmp_path, monkeypatch):
    """043:RF-8, 071:RF-5 — anotada en el registro y en uso por su puntero; si se vuelve al anterior, ya no se dice en uso."""
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion, volver_al_anterior
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.web import services
    raiz = tmp_path / 'asistente'
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'bufer'))
    from convertersmartgrid.digital_twin.buffer import raiz_buffer
    bufer = BuferEpisodios(raiz_buffer())
    registro = RegistroModelo(raiz / 'model_registry')
    versiones = []
    for version in ('v1', 'v2'):
        carpeta = bufer.raiz / 'modelos' / version
        carpeta.mkdir(parents=True)
        (carpeta / 'modelo.json').write_text(json.dumps({'cfg': {}, 'version': version}), encoding='utf-8')
        versiones.append(_decidir_promocion(bufer, carpeta, {'cfg': {}}, [], 'mae', registro=registro,
                                            reabrir=lambda _c: {'ok': True})['candidate_id'])

    def fila():
        return next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'pinn')
    assert fila()['estado'] == 'PROMOVIDO' and fila()['en_uso'] == 'v2' and fila()['candidate_id'] == versiones[1]
    assert fila()['algorithm'] == 'pinn_gnn'
    assert volver_al_anterior(bufer) == 'v1'
    assert fila()['estado'] is None and fila()['en_uso'] == 'v1'


def test_importar_nucleo_sin_adaptadores(tmp_path):
    """043:RF-8, 043:RF-11 — sin PyG, NeuralForecast, pymoo ni Pyomo el núcleo arranca y la consulta responde."""
    import subprocess
    import sys
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / 'src'
    codigo = f"""
import json, sys
VETADOS = ('torch_geometric', 'neuralforecast', 'pymoo', 'pyomo')
class Veto:
    def find_spec(self, nombre, ruta=None, destino=None):
        if nombre.split('.')[0] in VETADOS:
            raise ImportError('adaptador opcional ausente: ' + nombre)
sys.meta_path.insert(0, Veto())
sys.path.insert(0, {str(src)!r})
from fastapi.testclient import TestClient
from convertersmartgrid import sesion_web
from convertersmartgrid.web.app import create_app
from pathlib import Path
# Otro proceso no hereda lo que hace conftest.py: sin esto, la puerta de 086:RF-19 responde 401.
sesion_web.EXIGIR_SEGURIDAD = False
with TestClient(create_app(Path({str(tmp_path / 'web')!r}))) as cliente:
    r = cliente.get('/api/asistente/modelos')
print(json.dumps({{'codigo': r.status_code, 'familias': len(r.json()['familias']),
                  'cargados': [m for m in sys.modules if m.split('.')[0] in VETADOS]}}))
"""
    import os
    r = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300,
                       env={**os.environ, 'CSG_ASISTENTE_DATA': str(tmp_path / 'asistente'), 'CSG_WEB_FRONTEND': str(tmp_path / 'sin_front')})
    assert r.returncode == 0, r.stderr[-2000:]
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida['codigo'] == 200 and salida['familias'] and salida['cargados'] == []
