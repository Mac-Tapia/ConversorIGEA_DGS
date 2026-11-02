"""Contrato de limpieza diaria con archivos reales, spec062."""

import json
import os
import threading
import time

import pytest

from convertersmartgrid.web.jobs import JobManager
from convertersmartgrid.web.retencion import RetencionDiaria
from convertersmartgrid.web.workspace import WorkspaceStore

AHORA = 1_800_000_000.0
DIA = 86400


def crear_run(ws, numero, dias=8):
    rid = f'20260101T000000-{numero:012x}'
    run = ws.root / 'runs' / rid
    (run / 'originales').mkdir(parents=True)
    (run / 'originales/entrada.txt').write_text('dato real de contrato', encoding='utf-8')
    (run / 'source_manifest.json').write_text(json.dumps({
        'run_id': rid, 'mode': 'txt', 'created_at': AHORA - dias * DIA,
        'files': [],
    }), encoding='utf-8')
    for p in [*run.rglob('*'), run]:
        os.utime(p, (AHORA - dias * DIA, AHORA - dias * DIA))
    return run


def gestor(tmp_path):
    store = WorkspaceStore(tmp_path / 'web')
    store.root.mkdir(parents=True, exist_ok=True)
    jobs = JobManager(lambda *_: None)
    return store, jobs, RetencionDiaria(store, jobs, ahora=lambda: AHORA)


def test_retira_solo_ejecucion_obsoleta_y_respeta_siete_dias(tmp_path):
    """062:RF-2 062:RF-5 — no borra por nombre ni al cumplir exactamente siete días."""
    store, _, manager = gestor(tmp_path)
    ws = store.create()
    viejo, limite, nuevo = crear_run(ws, 1), crear_run(ws, 2, 7), crear_run(ws, 3, 1)
    desconocido = ws.root / 'runs/no-es-una-ejecucion'
    desconocido.mkdir()
    result = manager.revisar_si_vence()
    assert result['estado'] == 'completada'
    assert not viejo.exists() and limite.exists() and nuevo.exists() and desconocido.exists()
    assert result['eliminados'] == [str(viejo)]


def test_referencias_cruzadas_y_memoria_protegen_ejecuciones(tmp_path):
    """062:RF-4 — protege activo, cargado y referencias guardadas por otro espacio."""
    store, _, manager = gestor(tmp_path)
    ws, otro = store.create(), store.create()
    activo, cargado, referido = (crear_run(ws, n) for n in (1, 2, 3))
    ws.active_run_id = activo.name
    ws.loaded_run_id = cargado.name
    ws.save()
    otro.informes = {'resultado': str(referido / 'salida/informe.json')}
    otro.save()
    manager.revisar_si_vence()
    assert all(p.exists() for p in (activo, cargado, referido))


def test_modelos_informes_y_original_externo_se_conservan(tmp_path):
    """062:RF-5 — la antigüedad no convierte pesos o informes en basura."""
    store, _, manager = gestor(tmp_path)
    ws = store.create()
    for n, nombre in enumerate(('modelo.pt', 'informe.json', 'aceptacion_nativa.json', 'estudio.pdf'), 1):
        run = crear_run(ws, n)
        p = run / nombre
        p.write_bytes(b'contenido que se conserva')
        os.utime(p, (AHORA - 9 * DIA, AHORA - 9 * DIA))
        os.utime(run, (AHORA - 9 * DIA, AHORA - 9 * DIA))
    original = tmp_path / 'original.txt'
    original.write_bytes(b'unico original')
    run = crear_run(ws, 10)
    (run / 'originales/entrada.txt').unlink()
    os.link(original, run / 'originales/entrada.txt')
    os.utime(original, (AHORA - 9 * DIA, AHORA - 9 * DIA))
    os.utime(run / 'originales', (AHORA - 9 * DIA, AHORA - 9 * DIA))
    manager.revisar_si_vence()
    assert original.read_bytes() == b'unico original' and not run.exists()
    assert all((ws.root / 'runs' / f'20260101T000000-{n:012x}').exists() for n in range(1, 5))


def test_rechaza_redireccion_fuera_de_la_raiz(tmp_path):
    """062:RF-5 — una redirección dentro de una ejecución impide borrarla."""
    store, _, manager = gestor(tmp_path)
    ws = store.create()
    run = crear_run(ws, 1)
    externo = tmp_path / 'externo'
    externo.mkdir()
    (externo / 'dato.txt').write_text('no borrar', encoding='utf-8')
    link = run / 'redireccion'
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(externo), str(link))
    else:
        link.symlink_to(externo, target_is_directory=True)
    manager.revisar_si_vence()
    assert run.exists() and (externo / 'dato.txt').exists()


def test_temporales_antiguos_sin_referencias_y_archivos_recientes(tmp_path):
    """062:RF-6 062:RF-4 — temporales referenciados y actividad reciente se protegen."""
    store, _, manager = gestor(tmp_path)
    ws = store.create()
    folder = ws.root / 'tmp'
    folder.mkdir()
    viejo, usado, reciente = [folder / n for n in ('viejo.txt', 'usado.txt', 'reciente.txt')]
    for p in (viejo, usado, reciente):
        p.write_text('temporal', encoding='utf-8')
        os.utime(p, (AHORA - 8 * DIA, AHORA - 8 * DIA))
    os.utime(reciente, (AHORA, AHORA))
    ws.demanda['contrato'] = {'path': str(usado)}
    ws.save()
    run = crear_run(ws, 1)
    os.utime(run / 'originales/entrada.txt', (AHORA, AHORA))
    manager.revisar_si_vence()
    assert not viejo.exists() and usado.exists() and reciente.exists() and run.exists()


def test_periodicidad_persistida_y_reinicio(tmp_path):
    """062:RF-1 062:RF-7 — solo una revisión cada24h, conservada tras reiniciar."""
    store, jobs, manager = gestor(tmp_path)
    ws = store.create()
    manager.revisar_si_vence()
    run = crear_run(ws, 1)
    segundo = RetencionDiaria(store, jobs, ahora=lambda: AHORA + 100)
    assert segundo.revisar_si_vence() is None and run.exists()
    tercero = RetencionDiaria(store, jobs, ahora=lambda: AHORA + DIA + 1)
    tercero.revisar_si_vence()
    assert not run.exists()
    assert tercero.estado()['retencion_dias'] == 7


def test_trabajo_activo_aplaza_y_no_cancela(tmp_path):
    """062:RF-3 — el mantenimiento no cancela ni borra durante un trabajo."""
    store, jobs, manager = gestor(tmp_path)
    ws = store.create()
    run = crear_run(ws, 1)
    listo, soltar = threading.Event(), threading.Event()
    def trabajo(ctx):
        listo.set()
        soltar.wait(5)
    job = jobs.submit(ws.id, 'contrato', 'Contrato', trabajo)
    assert listo.wait(3)
    try:
        assert manager.revisar_si_vence()['estado'] == 'aplazada'
        assert run.exists() and not job.cancel.is_set()
    finally:
        soltar.set()
        jobs.shutdown()


def test_mantenimiento_bloquea_admision_simultanea():
    """062:RF-3 — no hay ventana entre comprobar trabajos y retirar archivos."""
    jobs = JobManager(lambda *_: None)
    dentro, salir, admitido = threading.Event(), threading.Event(), threading.Event()
    def limpiar():
        dentro.set()
        salir.wait(3)
    t = threading.Thread(target=lambda: jobs.mantenimiento_si_libre(limpiar))
    t.start()
    assert dentro.wait(2)
    def admitir():
        jobs.submit('espacio', 'contrato', 'Contrato', lambda _: None)
        admitido.set()
    otro = threading.Thread(target=admitir)
    otro.start()
    assert not admitido.wait(0.1)
    salir.set()
    t.join(3)
    otro.join(3)
    jobs.shutdown()
    assert admitido.is_set()


def test_metadatos_corruptos_no_autorizan_borrado(tmp_path):
    """062:RF-7 062:RF-4 — error de lectura de referencias se hace visible y no borra."""
    store, _, manager = gestor(tmp_path)
    ws = store.create()
    run = crear_run(ws, 1)
    (ws.root / 'conversiones.json').write_text('{roto', encoding='utf-8')
    result = manager.revisar_si_vence()
    assert run.exists() and result['estado'] == 'incompleta' and result['errores']


def test_estado_expuesto_por_monitor_y_lifespan(tmp_path):
    """062:RF-1 062:RF-8 — revisión real al arrancar y política visible por HTTP."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app
    app = create_app(tmp_path / 'web', host='127.0.0.1')
    with TestClient(app) as client:
        ws = client.post('/api/workspaces').json()
        wid = ws.get('id') or ws['workspace']['id']
        for _ in range(100):
            state = client.get(f'/api/workspaces/{wid}/asistente/monitor').json()
            if state['retencion']['ultima_revision'] is not None:
                break
            time.sleep(0.02)
        assert state['retencion']['retencion_dias'] == 7
        assert state['retencion']['intervalo_horas'] == 24
        assert state['retencion']['ultima_revision'] is not None


@pytest.mark.parametrize('contenido', ['[]', '{"terminada": NaN}', '{"terminada": true}'])
def test_resumen_corrupto_no_rompe_monitor(tmp_path, contenido):
    """062:RF-7 062:RF-8 — un JSON válido con esquema incorrecto se informa."""
    _, _, manager = gestor(tmp_path)
    manager.path.parent.mkdir()
    manager.path.write_text(contenido, encoding='utf-8')
    assert manager.estado()['error'] and manager.estado()['ultima_revision'] is None


def test_error_guardando_resumen_queda_visible(tmp_path):
    """062:RF-7 — el fallo real de E/S no se convierte en revisión exitosa."""
    _, _, manager = gestor(tmp_path)
    manager.path.parent.write_bytes(b'carpeta ocupada por archivo')
    result = manager.revisar_si_vence()
    assert result['estado'] == 'incompleta'
    assert manager.estado()['ultima_revision']['estado'] == 'incompleta'
    assert manager.estado()['error']


def test_no_escribe_resumen_mediante_redireccion(tmp_path):
    """062:RF-5 062:RF-7 — tampoco los metadatos de limpieza pueden salir de la raíz."""
    _, _, manager = gestor(tmp_path)
    exterior = tmp_path / 'exterior'
    exterior.mkdir()
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(exterior), str(manager.path.parent))
    else:
        manager.path.parent.symlink_to(exterior, target_is_directory=True)
    result = manager.revisar_si_vence()
    assert result['estado'] == 'incompleta'
    assert not list(exterior.iterdir())
