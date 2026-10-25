"""Spec 026, T9: vigilancia de trabajos, modelos, resultados y suite."""
from __future__ import annotations

from datetime import datetime

from igea_dgs.asistente import almacen
from igea_dgs.asistente.vigilancia import (
    Vigilante,
    correr_suite,
    revisar_calidad,
    revisar_modelos,
    revisar_trabajos,
    toca_suite,
)
from igea_dgs.web import services
from igea_dgs.web.app import _cerrar_entrenamiento_vigilado


def _t(i, kind, status, *, start=None, end=None, lane='engine', error=None, created=0.0, result=None):
    return {'id': i, 'kind': kind, 'title': f'{kind} {i}', 'status': status, 'lane': lane, 'error': error,
            'created_at': created, 'started_at': start, 'finished_at': end, 'result': result}


def test_fallos_largos_y_colas_paradas():
    """026:RF-22 — avisa de fallos, de trabajos que tardan mucho más que su mediana y de colas
    paradas; solo el 4002 se reintenta, y una vez."""
    trabajos = [_t('a', 'pide', 'done', start=0, end=100), _t('b', 'pide', 'done', start=0, end=120),
                _t('c', 'pide', 'running', start=1000),
                _t('d', 'flujo', 'failed', error='DIgSILENT devolvió 4002 al conectar'),
                _t('e', 'flujo', 'failed', error='no converge'),
                _t('f', 'cargas', 'queued', lane='powerfactory', created=0)]
    avisos = {a.clave: a for a in revisar_trabajos(trabajos, ahora=2000)}
    assert 'largo:c' in avisos and avisos['fallo:d'].accion == 'reintentar' and avisos['fallo:e'].accion is None
    assert 'cola:f' in avisos
    otra = {a.clave: a for a in revisar_trabajos(trabajos, ahora=2000, reintentados={'d'})}
    assert otra['fallo:d'].accion is None


def test_modelos_y_calidad():
    """026:RF-23 / 026:RF-24 — con bastante nuevo se reentrena; los resultados malos dan un
    aviso con la orden que los trataría, que el operador confirma."""
    acciones = {a.accion for a in revisar_modelos(episodios_nuevos=12, ordenes_nuevas=25)}
    assert acciones == {'entrenar_gemelo', 'entrenar_asistente'}
    assert not revisar_modelos(episodios_nuevos=2, ordenes_nuevas=3)
    r = {'project': 'P1', 'feeders': ['A1'], 'medidas': {'A1': {'converge': False}},
         'resultados': [{'error_pct': 3.5}], 'violaciones': [{'barra': 'B1'}]}
    avisos = {a.clave.split(':')[0]: a for a in revisar_calidad([_t('x', 'estudios', 'done', result=r)])}
    assert set(avisos) == {'converge', 'calibracion', 'norma'}
    assert avisos['norma'].propuesta == 'haz el pide de P1 A1' and avisos['converge'].propuesta.startswith('verifica')


def test_el_vigilante_actua_una_vez(tmp_path, monkeypatch):
    """026:RF-22 / 026:RF-23 — cada vuelta actúa sobre lo nuevo y no repite avisos."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    hechos = []
    v = Vigilante(listar_trabajos=lambda: [_t('d', 'flujo', 'failed', error='4002')],
                  reintentar=lambda i: hechos.append(('reintentar', i)),
                  entrenar_gemelo=lambda: hechos.append('gemelo'), entrenar_asistente=lambda: hechos.append('asis'),
                  contar_nuevos=lambda: (15, 0), repo=tmp_path)
    temprano = datetime(2026, 10, 24, 9)
    assert len(v.tic(fecha=temprano)) == 2 and v.tic(fecha=temprano) == []
    assert hechos == [('reintentar', 'd'), 'gemelo'] and len(almacen.leer('avisos')) == 2


def test_el_corte_avanza_solo_si_el_entrenamiento_termina_bien(tmp_path, monkeypatch):
    """026:RF-20 / 026:RF-23 — un proceso fallido conserva los ejemplos pendientes para que la
    vigilancia pueda reintentarlos; solo el éxito avanza el corte."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    marcados = []
    monkeypatch.setattr(services, 'asistente_marcar_entrenado', marcados.append)

    class Proceso:
        def __init__(self, codigo):
            self.codigo = codigo

        def wait(self):
            return self.codigo

    _cerrar_entrenamiento_vigilado(Proceso(2), False, 'asistente_entrenar')
    assert marcados == []
    aviso = almacen.leer('avisos')[-1]
    assert aviso['nivel'] == 'error' and 'datos nuevos quedan pendientes' in aviso['texto']

    _cerrar_entrenamiento_vigilado(Proceso(0), True, 'digital_twin_entrenar')
    assert marcados == [True]


def test_suite_nocturna_con_el_rf_de_cada_fallo(tmp_path, monkeypatch):
    """026:RF-25 — una vez por noche; lo que falla sale con el RF que cita la prueba."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    assert not toca_suite(datetime(2026, 10, 24, 15), None)
    assert toca_suite(datetime(2026, 10, 24, 23), '2026-10-23T23:00:00')
    assert not toca_suite(datetime(2026, 10, 24, 23), '2026-10-24T22:10:00')
    repo = tmp_path / 'repo'
    (repo / 'tests').mkdir(parents=True)
    (repo / 'tests' / 'test_x.py').write_text(
        'def test_bien():\n    """099:RF-1 — pasa."""\n\n\ndef test_mal():\n    """099:RF-2 — falla."""\n'
        '    assert False\n', encoding='utf-8')
    r = correr_suite(repo, argumentos=('-q', '-rs', '-p', 'no:cacheprovider', 'tests'))
    assert r['codigo'] == 1 and '1 failed' in r['resumen']
    assert r['fallidas'][0]['prueba'].startswith('tests/test_x.py::test_mal') and r['fallidas'][0]['rf'] == ['099:RF-2']
    assert almacen.leer('suite')[-1]['resumen'] == r['resumen']
