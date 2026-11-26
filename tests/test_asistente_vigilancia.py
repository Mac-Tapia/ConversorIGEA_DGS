"""Spec 026, T9: vigilancia de trabajos, modelos, resultados y suite."""
from __future__ import annotations

from datetime import datetime

from convertersmartgrid.aplicacion.asistente import almacen
from convertersmartgrid.aplicacion.asistente.vigilancia import (
    Vigilante,
    correr_suite,
    revisar_calidad,
    revisar_modelos,
    revisar_trabajos,
    toca_suite,
)
from convertersmartgrid.presentacion.web import services
from convertersmartgrid.presentacion.web.app import _cerrar_entrenamiento_vigilado


def _t(i, kind, status, *, start=None, end=None, lane='engine', error=None, created=0.0, result=None):
    return {'id': i, 'kind': kind, 'title': f'{kind} {i}', 'status': status, 'lane': lane, 'error': error,
            'created_at': created, 'started_at': start, 'finished_at': end, 'result': result}


def test_fallos_largos_y_colas_paradas():
    """026:RF-22 — avisa de fallos, de trabajos que tardan mucho más que su mediana y de colas
    paradas; solo el 4002 de lo que solo lee se reintenta (086:RF-26), y una vez."""
    trabajos = [_t('a', 'pide', 'done', start=0, end=100), _t('b', 'pide', 'done', start=0, end=120),
                _t('c', 'pide', 'running', start=1000),
                _t('d', 'pf_projects', 'failed', error='DIgSILENT devolvió 4002 al conectar'),
                _t('e', 'pf_projects', 'failed', error='no converge'),
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
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    hechos = []
    v = Vigilante(listar_trabajos=lambda: [_t('d', 'pf_projects', 'failed', error='4002')],
                  reintentar=lambda i: hechos.append(('reintentar', i)),
                  entrenar_gemelo=lambda: hechos.append('gemelo'), entrenar_asistente=lambda: hechos.append('asis'),
                  contar_nuevos=lambda: (15, 0), repo=tmp_path)
    temprano = datetime(2026, 10, 24, 9)
    assert len(v.tic(fecha=temprano)) == 2 and v.tic(fecha=temprano) == []
    assert hechos == [('reintentar', 'd'), 'gemelo'] and len(almacen.leer('avisos')) == 2


def test_el_corte_avanza_solo_si_el_entrenamiento_termina_bien(tmp_path, monkeypatch):
    """026:RF-20 / 026:RF-23 — un proceso fallido conserva los ejemplos pendientes para que la
    vigilancia pueda reintentarlos; solo el éxito avanza el corte."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
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


def _sin_abortar(revisar, *args):
    """Lo que devuelve la revisión, o la excepción con la que abortó (para fallar por aserción, no por error)."""
    try:
        return revisar(*args)
    except Exception as exc:  # noqa: BLE001 - la prueba quiere ver la excepción como dato
        return exc


def test_alimentadores_como_texto_o_como_diccionario():
    """086:RF-136 — el resultado de «Verificar el Caso base» trae cada alimentador como un diccionario con su
    nombre en ``feeder``; la vigilancia toma el nombre y propone la orden con él, sin abortar la vuelta."""
    r = {'project': 'P1', 'feeders': [{'feeder': 'A1', 'status': 'NO_VERIFICADO', 'flujo': {'converged': False}},
                                      'A2', {'alimentador': 'A3'}, {'sin_nombre': 1}, 7],
         'violaciones': [{'barra': 'B1'}]}
    avisos = _sin_abortar(revisar_calidad, [_t('v', 'pf_verificar_base', 'done', result=r)])
    assert not isinstance(avisos, Exception), f'la revisión abortó: {avisos!r}'
    por_tipo = {a.clave.split(':')[0]: a for a in avisos}
    assert por_tipo['converge'].propuesta == 'verifica el caso base de P1 A1 A2 A3'
    assert por_tipo['norma'].propuesta == 'haz el pide de P1 A1 A2 A3'


def test_un_trabajo_con_otra_forma_no_aborta_la_vuelta():
    """086:RF-137 — un trabajo cuya forma no se puede revisar se salta con un aviso que lo nombra, y los demás
    trabajos de la misma vuelta se revisan igual (fallos, reintentos y calidad)."""
    raro = _t('r', 'estudios', 'parcial', result={'pendientes': ['A1 sin medir']})
    sin_titulo = {'id': 's', 'kind': 'pf_projects', 'status': 'failed', 'error': '4002'}
    buenos = [_t('d', 'pf_projects', 'failed', error='DIgSILENT devolvió 4002 al conectar'),
              _t('x', 'estudios', 'done', result={'project': 'P1', 'feeders': ['A1'], 'medidas': {'converge': False}})]
    calidad = _sin_abortar(revisar_calidad, [raro, *buenos])
    assert not isinstance(calidad, Exception), f'la revisión de calidad abortó: {calidad!r}'
    claves = {a.clave: a for a in calidad}
    assert 'converge:x' in claves and claves['revision:r'].trabajo == 'r'
    assert '«estudios r»' in claves['revision:r'].texto and 'vigilancia.py:' in claves['revision:r'].texto
    trabajos = _sin_abortar(revisar_trabajos, [sin_titulo, *buenos], 2000)
    assert not isinstance(trabajos, Exception), f'la revisión de trabajos abortó: {trabajos!r}'
    claves = {a.clave: a for a in trabajos}
    assert claves['fallo:d'].accion == 'reintentar' and claves['revision:s'].trabajo == 's'


def test_el_fallo_de_la_vuelta_dice_su_linea_una_vez_por_causa(tmp_path, monkeypatch):
    """086:RF-138 — el aviso «la vigilancia falló» lleva el fichero y la línea de la traza, y una causa que se
    repite en cada vuelta se avisa una sola vez; otra causa se avisa aparte. Del 24-10 al 26-11 quedaron 3391
    avisos idénticos, uno por minuto, sin decir dónde fallaba."""
    import threading

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    vueltas = []
    listo = threading.Event()

    def listar():
        vueltas.append(1)
        if len(vueltas) >= 6:
            listo.set()
        if len(vueltas) <= 3:
            raise TypeError('sequence item 0: expected str instance, dict found')
        raise KeyError('title')

    v = Vigilante(listar_trabajos=listar, reintentar=lambda i: None, entrenar_gemelo=lambda: None,
                  entrenar_asistente=lambda: None, contar_nuevos=lambda: (0, 0), repo=tmp_path, intervalo_s=0.01)
    hilo = v.arrancar()
    try:
        assert listo.wait(10), 'la vigilancia no dio seis vueltas'
    finally:
        v.parar()
        hilo.join(5)
    fallos = [a for a in almacen.leer('avisos') if a['texto'].startswith('la vigilancia falló')]
    assert len(fallos) == 2, [a['texto'] for a in fallos]
    assert all('test_asistente_vigilancia.py:' in a['texto'] for a in fallos)
    assert 'TypeError' in fallos[0]['texto'] and 'KeyError' in fallos[1]['texto']


def test_suite_nocturna_con_el_rf_de_cada_fallo(tmp_path, monkeypatch):
    """026:RF-25 — una vez por noche; lo que falla sale con el RF que cita la prueba."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
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
