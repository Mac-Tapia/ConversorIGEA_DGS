"""022:RF-56 — ``tools/sistema_web.py``: un sistema eléctrico de punta a punta por la web."""
from __future__ import annotations

from pathlib import Path

import pytest

from apoyo import cargar_herramienta


@pytest.fixture(scope='module')
def herramienta():
    return cargar_herramienta('sistema_web.py', 'sistema_web_prueba')


class WebFalsa:
    """Responde como la web: el espacio, los trabajos y la demanda de un sistema."""

    def __init__(self, proyecto=None, informes=None):
        self.llamadas: list[tuple[str, str]] = []
        self.proyecto = proyecto
        self.informes = informes or []
        self.esperados: list[str] = []

    def get(self, ruta, **kw):
        self.llamadas.append(('GET', ruta))
        if ruta == '':
            return {'loaded': True, 'jobs': [{'id': 'v', 'title': 'viejo', 'status': 'running'}],
                    'pf_projects': {'SISTEMA_PISCO': self.proyecto} if self.proyecto else {}}
        if ruta == '/demanda/sistema':
            return {'sistema': {'grupo': 'SISTEMA_PISCO', 'alimentadores': ['PI102', 'PI101'],
                                'medidores': {'PI102': ['L-PI102'], 'PI101': []}}}
        raise AssertionError(ruta)

    def post(self, ruta, **kw):
        self.llamadas.append(('POST', ruta))
        if ruta == '/powerfactory/flow':
            self.proyecto = 'P_PISCO'
        if ruta == '/demanda/ajuste/plan':
            assert kw['json']['medidores'] == ['L-PI102']
            return {'token': 't', 'avisos': ['PI101 sin medidor']}
        return {'id': ruta, 'title': ruta}

    def esperar(self, trabajo):
        self.esperados.append(trabajo['id'])
        if trabajo['id'] == '/convert/sistema':
            return {'status': 'done', 'result': {'status': 'ok', 'group': 'SISTEMA_PISCO'}}
        if trabajo['id'] == '/demanda/cabecera/buscar':
            return {'id': 'max', 'status': 'done', 'result': {
                'barras': [{'clave': 'SET 31 10 kV', 'kw': 5456.3, 'fecha': '2026-07-21 18:45',
                            'alimentadores': ['PI101', 'PI102']}],
                'resultados': [{'medidor': 'L-PI102', 'alimentador': 'PI102', 'kw': 1000.0},
                               {'medidor': 'L-PI141', 'error': 'sin dato'}]}}
        if trabajo['id'].endswith('/aplicar'):
            return {'status': 'done', 'result': {
                'sistema': {'sin_medidor': ['PI101']}, 'informes': self.informes}}
        return {'status': 'done', 'result': {}}


def _correr(herramienta, web, **kw):
    return herramienta.correr(web, 'Pisco', demanda_dir=Path('libros'), periodo='2026-07',
                              reconvertir=kw.get('reconvertir', False), transformadores=False,
                              tension_pu=None, bancos=True)


VALIDO = {'feeder': 'PI102', 'cuadrado': True, 'status': 'OK', 'flujos': 5,
          'desvio': {'kw': 0.0}, 'validacion_posterior_nativa': {'status': 'VALIDO'}}


def test_convierte_importa_y_calibra_el_sistema(herramienta, capsys):
    """022:RF-56 — sin proyecto del sistema: espera lo que corre, convierte, importa y
    calibra con los medidores que dio la máxima; dice los sin medidor."""
    web = WebFalsa(informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    assert web.esperados[0] == 'v', 'primero lo que estaba en curso'
    rutas = [r for _m, r in web.llamadas]
    assert rutas.index('/convert/sistema') < rutas.index('/powerfactory/flow') < rutas.index(
        '/demanda/ajuste/plan') < rutas.index('/demanda/ajuste/t/aplicar')
    salida = capsys.readouterr().out
    assert 'Proyecto: P_PISCO' in salida and 'Sin medidor (demanda del archivo): PI101' in salida
    assert '1 válido(s), 0 con fallos.' in salida


def test_retoma_el_proyecto_ya_importado(herramienta):
    """022:RF-56 — con el proyecto del sistema ya en el espacio no se vuelve a convertir; con
    ``--reconvertir``, sí."""
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    assert ('POST', '/convert/sistema') not in web.llamadas
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    _correr(herramienta, web, reconvertir=True)
    assert ('POST', '/convert/sistema') in web.llamadas


def test_con_fallos_lo_dice_y_sale_con_1(herramienta, capsys):
    """022:RF-56 — un alimentador con remedios y validación que falla da código 1 y su
    primer flujo con lo que dijo DIgSILENT."""
    malo = {'feeder': 'PI102', 'cuadrado': False, 'status': 'FALLO_VALIDACION_NATIVA',
            'flujos': 18, 'desvio': {'kw': 0.0},
            'remedios': [{'remedio': 'adaptación automática del modelo'}],
            'historial': [{'converge': False, 'motivo': 'Newton algorithm stagnated'}],
            'validacion_posterior_nativa': {'status': 'REQUIERE_DISTRIBUCION'}}
    assert _correr(herramienta, WebFalsa(proyecto='P', informes=[malo])) == 1
    salida = capsys.readouterr().out
    assert 'Newton algorithm stagnated' in salida and 'adaptación automática' in salida


def test_la_web_que_corta_se_reintenta(herramienta, monkeypatch):
    """022:RF-56 — un corte de la conexión mientras la web trabaja no corta la cadena
    (Pisco, 2026-10-18: «WinError 10054» a mitad de la conversión)."""
    import requests

    web = herramienta.Web('http://web', 'e', reintentos=3, pausa=0)
    respuestas = [requests.ConnectionError('10054'),
                  type('R', (), {'status_code': 200, 'json': lambda self: {'ok': 1}})()]
    monkeypatch.setattr(web.http, 'request', lambda *a, **k: (
        (_ for _ in ()).throw(respuestas.pop(0)) if isinstance(respuestas[0], Exception)
        else respuestas.pop(0)))
    assert web.get('') == {'ok': 1}


def test_solo_una_parte_del_sistema(herramienta):
    """022:RF-56 — ``--alimentadores`` calibra solo esos, para aislar el que no deja converger;
    sin medidores elegidos no hay qué calibrar."""
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None, reconvertir=False,
                              transformadores=False, tension_pu=None, bancos=True,
                              solo=['pi102']) == 0
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None, reconvertir=False,
                              transformadores=False, tension_pu=None, bancos=True,
                              solo=['PI101']) == 2
    assert ('POST', '/demanda/ajuste/plan') not in web.llamadas


def test_medida_para_reconstruir(herramienta):
    """022:RF-59 — con medidor, la suya; sin medidor, la de su barra menos las de los demás
    (TM101 en SET 22: 6 792 − 6 858 = −66 kW, que no pasa carga)."""
    maxima = {'resultados': [
        {'alimentador': 'TM105', 'kw': 3482.0}, {'alimentador': 'TM106', 'kw': 3133.0},
        {'alimentador': 'TM104', 'kw': 31.0}, {'alimentador': 'TM103', 'kw': 97.0},
        {'alimentador': 'TM102', 'kw': 115.0}, {'alimentador': 'X', 'error': 'sin dato'}]}
    medidas = herramienta.medidas_de(maxima)
    assert medidas['TM106'] == 3133.0 and 'X' not in medidas
    barras = [{'kw': 6792.0,
               'alimentadores': ['TM101', 'TM102', 'TM103', 'TM104', 'TM105', 'TM106']}]
    assert herramienta.medida_de('TM106', medidas, barras) == 3133.0
    assert herramienta.medida_de('TM101', medidas, barras) == pytest.approx(-66.0)
    assert herramienta.medida_de('ZZ', medidas, barras) == 0.0


def test_reconstruir_reconvierte_con_las_medidas(herramienta):
    """022:RF-61 — ``--reconstruir`` manda los pedidos y las medidas a la conversión por
    sistema, importa de nuevo y calibra el proyecto nuevo."""
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    enviados = []
    original = web.post

    def post(ruta, **kw):
        if ruta == '/convert/sistema':
            enviados.append(kw['json'])
        return original(ruta, **kw)

    web.post = post
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None,
                              reconvertir=False, transformadores=False, tension_pu=None,
                              bancos=True, reconstruir=['PI101']) == 0
    assert enviados and enviados[0]['reconstruir'] == {'PI101': pytest.approx(4456.3)}
    assert ('POST', '/powerfactory/flow') in web.llamadas
    assert [r for _m, r in web.llamadas].count('/demanda/ajuste/plan') == 1
