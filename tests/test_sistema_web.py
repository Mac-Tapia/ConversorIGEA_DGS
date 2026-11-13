"""022:RF-56 — ``tools/sistema_web.py``: un sistema eléctrico de punta a punta por la web."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from apoyo import cargar_herramienta
from openpyxl import Workbook


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
        if ruta == '/demanda/centrales':                                 # 022:RF-88
            return {'centrales': [
                {'medidor': 'CT_X', 'kv': 22.9, 'set': 'SET 31', 'tramo': 'PI102'},
                {'medidor': 'CT_Y', 'kv': 10.0, 'set': 'SET 31', 'tramo': ''}]}
        raise AssertionError(ruta)

    def post(self, ruta, **kw):
        self.llamadas.append(('POST', ruta))
        if ruta == '/demanda/cabecera/buscar':
            # 022:RF-88: la central del perfil va en el tramo; la otra, en su barra.
            assert kw['json']['centrales_tramo'] == {'CT_X': 'PI102'}, kw['json']
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
        if trabajo['id'] == '/powerfactory/caso-base':
            return {'status': 'done', 'result': {'feeders': [
                {'feeder': 'F', 'status': getattr(self, 'caso_base', 'VERIFICADO')}]}}
        if trabajo['id'] == '/demanda/cabecera/buscar':
            return {'id': 'max', 'status': 'done', 'result': {
                'barras': [{'clave': 'SET 31 10 kV', 'kw': 5456.3, 'fecha': '2026-07-21 18:45',
                            'alimentadores': ['PI101', 'PI102']}],
                'resultados': [{'medidor': 'L-PI102', 'alimentador': 'PI102', 'kw': 1000.0},
                               {'medidor': 'L-PI141', 'error': 'sin dato'},
                               # 022:RF-88: la central en tramo, no al plan.
                               {'medidor': 'CT_X', 'alimentador': 'Central PI102', 'kw': 50.0}]}}
        if trabajo['id'].endswith('/aplicar'):
            return {'status': 'done', 'result': {
                'sistema': {'sin_medidor': ['PI101']}, 'informes': self.informes}}
        return {'status': 'done', 'result': {}}


LIBROS = {'medidores': Path('libros/m.xlsx'), 'cabecera': Path('libros/cab'),
          'clientes': Path('libros/cli'), 'suministros': Path('libros/cualquier-nombre.xlsx')}
T_2025 = datetime(2025, 3, 1, 10, 15)


def _correr(herramienta, web, **kw):
    return herramienta.correr(web, 'Pisco', demanda_dir=Path('libros'),
                              periodo=kw.get('periodo', '2026-07'),
                              reconvertir=kw.get('reconvertir', False), transformadores=False,
                              tension_pu=None, bancos=True, libros=LIBROS)


def test_con_un_anio_entero_no_cruza_un_mes_y_sube_cada_libro(herramienta):
    """025:RF-25 — ``--periodo 2025``: la máxima del año; el cruce del plan va por el mes de
    cada máxima, así que no se manda un cruce de mes; cada libro va a su hueco y la
    cabecera se indexa por año."""
    web = WebFalsa(informes=[VALIDO])
    assert _correr(herramienta, web, periodo='2025') == 0
    rutas = [r for _m, r in web.llamadas]
    assert '/demanda/clientes/cruzar' not in rutas
    assert all(f'/demanda/{t}/path' in rutas for t in LIBROS)
    assert '/demanda/cabecera/indexar' in rutas


def test_los_libros_se_reconocen_por_su_contenido(herramienta, tmp_path):
    """025:RF-25b, RF-25c — sin nombres de carpeta de ninguna empresa; lo dado por opción
    manda; sin medición de cabecera no se sigue."""
    def libro(path, filas):
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        for f in filas:
            wb.active.append(f)
        wb.save(path)

    libro(tmp_path / 'x' / 'rel.xlsx', [['Codigo Alimentador', 'Medidor'], ['F1', 'M1']])
    libro(tmp_path / 'y' / '2025' / 'm.xlsx', [['Local Time', 'kW tot'], [T_2025, 1.0]])
    (tmp_path / 'z').mkdir()
    _libro_suministros(tmp_path / 'z' / 'padron.xlsx', 2)
    libros, _avisos = herramienta.libros_de_la_demanda(tmp_path)
    assert libros['medidores'] == tmp_path / 'x' / 'rel.xlsx'
    assert libros['cabecera'] == tmp_path / 'y'
    assert libros['suministros'] == tmp_path / 'z' / 'padron.xlsx'
    otro = tmp_path / 'otra cabecera'
    libros, _ = herramienta.libros_de_la_demanda(tmp_path, {'cabecera': otro})
    assert libros['cabecera'] == otro
    vacia = tmp_path / 'vacia'
    vacia.mkdir()
    with pytest.raises(herramienta.DemandaError, match='medición de cabecera'):
        herramienta.libros_de_la_demanda(vacia)


def _libro_suministros(path: Path, cantidad: int) -> None:
    libro = Workbook()
    hoja = libro.active
    hoja.append(['Suministro Act', 'SED', 'RADIAL'])
    for indice in range(cantidad):
        hoja.append([f'NIS-{indice}', f'SED-{indice}', f'AL-{indice}'])
    libro.save(path)


def test_el_libro_de_suministros_se_descubre_por_contenido(herramienta, tmp_path):
    """004:RF-58/RF-59 — cualquier nombre sirve y, con varios compatibles, se usa el que contiene
    más suministros actuales en vez de fijar un nombre o bloquear la ejecución."""
    carpeta = tmp_path / '3.-suministrocliente'
    carpeta.mkdir()
    _libro_suministros(carpeta / 'copia-con-nombre-arbitrario.xlsx', 1)
    vigente = carpeta / 'entrega-sin-fecha.xlsx'
    _libro_suministros(vigente, 3)
    libro_invalido = Workbook()
    libro_invalido.save(carpeta / 'notas.xlsx')

    assert herramienta.resolver_libro_suministros(tmp_path) == vigente


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
        '/powerfactory/caso-base') < rutas.index('/demanda/ajuste/plan') < rutas.index('/demanda/ajuste/t/aplicar')
    salida = capsys.readouterr().out
    assert 'Proyecto: P_PISCO' in salida and 'Sin medidor (demanda del archivo): PI101' in salida
    assert '1 válido(s), 0 con fallos.' in salida


def test_sin_caso_base_verificado_lo_dice_y_sigue(herramienta, capsys):
    """015:RF-13 — el guion hace el paso 1.1; si no queda verificado lo dice, y nada para el flujo."""
    web = WebFalsa(informes=[VALIDO])
    web.caso_base = 'NO_VERIFICADO'
    assert _correr(herramienta, web) == 0
    assert '/demanda/ajuste/plan' in [r for _m, r in web.llamadas]
    assert 'sin verificar' in capsys.readouterr().out


def test_sin_calibracion_valida_pide_los_transformadores(herramienta, capsys):
    """083:RF-8 — con SED fijas sobre su transformador y fichas propuestas, se cambian y se repite sin la opción."""
    malo = {'feeder': 'PI102', 'cuadrado': False, 'status': 'NO_CONVERGE', 'flujos': 3, 'fijas_sobre_su_transformador': [
        {'sed': 'S1', 'propuesta': {'kva': 250}, 'transformadores': ['T1']}]}
    web = WebFalsa(informes=[malo])
    _correr(herramienta, web)
    assert ('POST', '/demanda/ajuste/t/transformadores') in web.llamadas
    assert '083:RF-8' in capsys.readouterr().out


def test_retoma_el_proyecto_ya_importado(herramienta):
    """022:RF-56 — con el proyecto del sistema ya en el espacio no se vuelve a convertir; con
    ``--reconvertir``, sí."""
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    assert ('POST', '/convert/sistema') not in web.llamadas
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    _correr(herramienta, web, reconvertir=True)
    assert ('POST', '/convert/sistema') in web.llamadas


def test_al_retomar_tambien_verifica_el_caso_base(herramienta, capsys):
    """086:RF-13 — retomar no importa de nuevo, pero el «Caso base» se verifica igual, antes del plan."""
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    rutas = [r for _m, r in web.llamadas]
    assert '/powerfactory/flow' not in rutas
    assert rutas.count('/powerfactory/caso-base') == 1
    assert rutas.index('/powerfactory/caso-base') < rutas.index('/demanda/ajuste/plan')
    assert 'Caso base: done VERIFICADO' in capsys.readouterr().out


def test_al_retomar_la_verificacion_que_no_se_puede_pedir_no_para(herramienta, capsys):
    """086:RF-13, 015:RF-13 — si la web rechaza la verificación se dice y se sigue: nada bloquea aquí."""
    web = WebFalsa(proyecto='P_PISCO', informes=[VALIDO])
    original = web.post

    def post(ruta, **kw):
        if ruta == '/powerfactory/caso-base':
            raise RuntimeError('POST /powerfactory/caso-base: 400 sin vínculo')
        return original(ruta, **kw)

    web.post = post
    assert _correr(herramienta, web) == 0
    salida = capsys.readouterr().out
    assert 'sin verificar' in salida and 'sin vínculo' in salida


class WebConProyectoBorrado(WebFalsa):
    """El vínculo de la web nombra un proyecto que ya no está en DIgSILENT (PE10 de prueba, 2026-11-10)."""

    def post(self, ruta, **kw):
        if ruta == '/powerfactory/caso-base':
            self.pedido = kw['json']['project']
        return super().post(ruta, **kw)

    def esperar(self, trabajo):
        if trabajo['id'] == '/powerfactory/caso-base' and self.pedido == 'P_BORRADO':
            self.esperados.append(trabajo['id'])
            return {'status': 'done', 'result': {'feeders': [
                {'feeder': 'F', 'status': 'NO_VERIFICADO', 'proyecto_ausente': True,
                 'motivo': "No existe el proyecto 'P_BORRADO'"}]}}
        return super().esperar(trabajo)


def test_018_rf17_un_proyecto_borrado_se_importa_de_nuevo(herramienta, capsys):
    """018:RF-17 — se convierte de nuevo desde la fuente cargada, se importa y se calibra el proyecto nuevo."""
    web = WebConProyectoBorrado(proyecto='P_BORRADO', informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    rutas = [r for _m, r in web.llamadas]
    assert rutas.count('/powerfactory/caso-base') == 2
    assert (rutas.index('/powerfactory/caso-base') < rutas.index('/convert/sistema') < rutas.index('/powerfactory/flow')
            < rutas.index('/demanda/ajuste/plan'))
    # Si la importación no deja un proyecto nuevo, para: no calibra lo que no existe.
    web = WebConProyectoBorrado(proyecto='P_BORRADO', informes=[VALIDO])
    web.esperar_original = web.esperar
    web.esperar = lambda t: ({'status': 'failed', 'error': 'sin licencia'} if t['id'] == '/powerfactory/flow'
                             else web.esperar_original(t))
    assert _correr(herramienta, web) == 2
    assert '/demanda/ajuste/plan' not in [r for _m, r in web.llamadas]
    salida = capsys.readouterr().out
    assert 'ya no está en DIgSILENT' in salida and 'Proyecto: P_PISCO' in salida


def test_018_rf16_el_informe_de_un_proyecto_sin_activar():
    """018:RF-16 — la aceptación escribe el motivo y si el proyecto falta, antes de salir con el código 2."""
    pa = cargar_herramienta('powerfactory_acceptance.py', 'aceptacion_rf16')

    class App:
        def GetActiveProject(self):
            return None

    pa._activate_project_by_path = lambda *_a: None
    info = pa.activate_existing_project(App(), 'BORRADO', 'F')
    informe = pa.informe_sin_activar(info)
    assert informe['proyecto_ausente'] is True and informe['status'] == 'NO_VERIFICADO'
    assert "No existe el proyecto 'BORRADO'" in informe['error']

    def falla(*_a):
        raise RuntimeError('licencia ocupada')

    pa._activate_project_by_path = falla
    informe = pa.informe_sin_activar(pa.activate_existing_project(App(), 'P', 'F'))
    assert informe['proyecto_ausente'] is False and 'licencia ocupada' in informe['error']


def test_importar_verifica_una_sola_vez(herramienta):
    """086:RF-13 — el mismo paso para importar y para retomar: no se verifica dos veces."""
    web = WebFalsa(informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    assert [r for _m, r in web.llamadas].count('/powerfactory/caso-base') == 1


def test_reconstruir_verifica_el_proyecto_nuevo(herramienta):
    """086:RF-13 — ``--reconstruir`` importa otra vez y entraba por «retomar»: se calibraba sin verificar lo nuevo."""
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None, reconvertir=False,
                              transformadores=False, tension_pu=None, bancos=True, reconstruir=['PI101'],
                              libros=LIBROS) == 0
    rutas = [r for _m, r in web.llamadas]
    assert rutas.count('/powerfactory/caso-base') == 1
    assert rutas.index('/powerfactory/flow') < rutas.index('/powerfactory/caso-base') < rutas.index('/demanda/ajuste/plan')


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
                              solo=['pi102'], libros={**LIBROS, 'suministros': Path('l/s.xlsx')}) == 0
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None, reconvertir=False,
                              transformadores=False, tension_pu=None, bancos=True,
                              solo=['PI101'], libros={**LIBROS, 'suministros': Path('l/s.xlsx')}) == 2
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
    """022:RF-61, 004:RF-60 — ``--reconstruir`` manda los pedidos y las medidas a la conversión por
    sistema, importa de nuevo y calibra el proyecto nuevo."""
    web = WebFalsa(proyecto='P', informes=[VALIDO])
    enviados, suministros = [], []
    original = web.post

    def post(ruta, **kw):
        if ruta == '/convert/sistema':
            enviados.append(kw['json'])
        if ruta == '/demanda/suministros/path':
            suministros.append(kw['json']['path'])
        return original(ruta, **kw)

    web.post = post
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('l'), periodo=None,
                              reconvertir=False, transformadores=False, tension_pu=None,
                              bancos=True, reconstruir=['PI101'],
                              libros={**LIBROS, 'suministros': Path('l/s.xlsx')}) == 0
    assert enviados and enviados[0]['reconstruir'] == {'PI101': pytest.approx(4456.3)}
    # 004:RF-60 — el libro explícito sigue en la vuelta tras reconvertir.
    assert suministros == [str(Path('l/s.xlsx'))] * 2
    assert ('POST', '/powerfactory/flow') in web.llamadas
    assert [r for _m, r in web.llamadas].count('/demanda/ajuste/plan') == 1


def test_escanea_antes_de_calibrar_y_la_central_toma_su_barra(herramienta, monkeypatch, capsys):
    """028:RF-15 — el sistema se escanea antes del plan; la central del perfil sin barra va al
    plan con la del generador que encontró el escaneo."""
    from convertersmartgrid import perfil_empresa

    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda *a, **k: {})
    monkeypatch.setattr(perfil_empresa, 'centrales_termicas', lambda _d: {
        'PI102': {'generacion': 'CT_X', 'llegada': 'CT_L', 'salida': 'CT_S'}})

    class ConEscaneo(WebFalsa):
        planes: list = []

        def post(self, ruta, **kw):
            if ruta == '/demanda/ajuste/plan':
                self.llamadas.append(('POST', ruta))
                self.planes.append(kw['json'])
                return {'token': 't', 'avisos': []}
            return super().post(ruta, **kw)

        def esperar(self, trabajo):
            if trabajo['id'] == '/powerfactory/escanear':
                self.esperados.append(trabajo['id'])
                return {'status': 'done', 'result': {
                    'resumen': {'PI102': {'generadores': 1, 'bancos': 0, 'cargas_cambiadas': 0}},
                    'alimentadores': {'PI102': {'generadores': [
                        {'barra': 'N5', 'en_servicio': True, 'origen': 'operador'}]}}}}
            return super().esperar(trabajo)

    web = ConEscaneo(informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    rutas = [r for _m, r in web.llamadas]
    assert rutas.index('/powerfactory/escanear') < rutas.index('/demanda/ajuste/plan')
    [plan] = web.planes
    assert plan['centrales']['PI102']['nodo'] == 'N5'
    assert 'escaneo PI102: 1 generador(es)' in capsys.readouterr().out


def test_no_espera_al_trabajo_que_lo_lanzo(herramienta, monkeypatch):
    """028:RF-21 — lanzado por el botón «Recalibrar», no se espera a sí mismo: el trabajo que lo
    lanzó sigue en curso mientras recalibra (Chincha no empezaba nunca, 2026-10-28)."""
    monkeypatch.setenv('CSG_TRABAJO_PROPIO', 'v')
    web = WebFalsa(informes=[VALIDO])
    assert _correr(herramienta, web) == 0
    assert 'v' not in web.esperados


class WebRed(WebFalsa):
    def __init__(self, red, grupo, *, importado=False, fallo=None):
        super().__init__(proyecto='P_RED' if importado else None, informes=[VALIDO])
        self.red, self.grupo, self.fallo = red, grupo, fallo
        self.enviados = {}

    def get(self, ruta, **kw):
        if ruta == '':
            return {'loaded': True, 'jobs': [],
                    'pf_projects': {self.grupo: self.proyecto} if self.proyecto else {}}
        if ruta == '/demanda/sistema':
            assert kw['params']['todos'] is True
            return {'sistema': {'grupo': self.grupo, 'alimentadores': self.red,
                                'medidores': {a: [f'L-{a}'] for a in self.red}}}
        if ruta == '/demanda/centrales':
            return {'centrales': []}
        return super().get(ruta, **kw)

    def post(self, ruta, **kw):
        self.llamadas.append(('POST', ruta))
        self.enviados[ruta] = kw.get('json')
        if ruta == '/powerfactory/flow' and self.fallo != ruta:
            self.proyecto = 'P_RED'
        if ruta == '/demanda/ajuste/plan':
            return {'token': 't'}
        return {'id': ruta, 'title': ruta}

    def esperar(self, trabajo):
        ruta = trabajo['id']
        if self.fallo == ruta:
            return {'id': ruta, 'status': 'failed', 'error': 'fallo deliberado'}
        if ruta == '/convert':
            return {'status': 'done', 'result': (
                {'status': 'ok'} if len(self.red) > 1 else
                {'status': None, 'summary': {'status': 'completed', 'ok': 1, 'failed': 0, 'skipped': 0}})}
        return super().esperar(trabajo)


def _correr_red(herramienta, web, **kw):
    return herramienta.correr(web, None, demanda_dir=Path('libros'), periodo='2026-07',
                              reconvertir=False, transformadores=False, tension_pu=None,
                              bancos=True, libros=LIBROS, red=web.red, **kw)


@pytest.mark.parametrize('red,nombre,grupo', [
    (['PI102'], None, 'PI102'),
    (['PI102', 'PI101'], None, 'PI102_PI101'),
    (['PI102', 'PI101'], ' Red Pisco / prueba ', 'Red_Pisco___prueba'),
])
def test_red_convierte_importa_y_usa_maximas_individuales(herramienta, red, nombre, grupo):
    """028:RF-25 / 028:RF-24 — ``--red`` convierte, importa y calibra uno o varios
    alimentadores, unidos en un proyecto si son varios, con la máxima de cada uno."""
    web = WebRed(red, grupo)
    assert _correr_red(herramienta, web, grupo=nombre) == 0
    assert web.enviados['/convert'] == {
        'feeders': red, 'unir': len(red) > 1, 'nombre': grupo if len(red) > 1 else ''}
    assert web.enviados['/powerfactory/flow'] == {'feeders': [grupo]}
    assert web.enviados['/demanda/cabecera/buscar']['por_barra'] is False
    assert ('POST', '/convert/sistema') not in web.llamadas


def test_red_recalibra_sin_reconvertir(herramienta):
    """028:RF-25 — con el proyecto ya importado, recalibra sin reconvertir."""
    web = WebRed(['PI102', 'PI101'], 'RED', importado=True)
    assert _correr_red(herramienta, web, grupo='RED') == 0
    assert '/convert' not in web.enviados and '/powerfactory/flow' not in web.enviados


@pytest.mark.parametrize('ruta', ['/convert', '/powerfactory/flow',
                                  '/demanda/cabecera/indexar', '/demanda/clientes/indexar',
                                  '/powerfactory/escanear', '/demanda/cabecera/buscar',
                                  '/powerfactory/projects'])
def test_red_no_calibra_si_falla_un_paso_previo(herramienta, ruta):
    web = WebRed(['PI102'], 'PI102', fallo=ruta)
    assert _correr_red(herramienta, web) == 2
    assert '/demanda/ajuste/plan' not in web.enviados


def test_red_reconstruir_se_rechaza_antes_de_convertir(herramienta):
    web = WebRed(['PI102'], 'PI102')
    assert _correr_red(herramienta, web, reconstruir=['PI102']) == 2
    assert not web.enviados


def test_sin_validacion_nativa_o_trabajo_fallido_no_es_exito(herramienta):
    web = WebRed(['PI102'], 'PI102', fallo='/demanda/ajuste/t/aplicar')
    assert _correr_red(herramienta, web) == 2
    assert herramienta._resumen({'result': {'informes': [
        {**VALIDO, 'validacion_posterior_nativa': {}}]}}) == (0, 1)


@pytest.mark.parametrize('status,summary', [
    ('completed', {'ok': 0, 'failed': 1, 'skipped': 0}),
    ('completed', {'ok': 0, 'failed': 0, 'skipped': 1}),
    ('cancelled', {'ok': 1, 'failed': 0, 'skipped': 0}),
])
def test_red_no_importa_conversion_individual_sin_resultado_util(herramienta, status, summary):
    web = WebRed(['PI102'], 'PI102')
    esperar = web.esperar

    def resultado(trabajo):
        if trabajo['id'] == '/convert':
            return {'status': 'done', 'result': {'status': None, 'summary': {**summary, 'status': status}}}
        return esperar(trabajo)

    web.esperar = resultado
    assert _correr_red(herramienta, web) == 2
    assert '/powerfactory/flow' not in web.enviados


@pytest.mark.parametrize('criterio', [None, 'maximo_mes'])
def test_el_criterio_de_las_fijas_va_al_cruce_y_al_plan(herramienta, criterio):
    """039:RF-1 — ``--criterio-fijas`` (por defecto «coincidente») va al cruce de clientes y al
    plan del ajuste, como lo manda el front."""
    class Web(WebFalsa):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.cuerpos: dict[str, dict | None] = {}

        def post(self, ruta, **kw):
            self.cuerpos[ruta] = kw.get('json')
            return super().post(ruta, **kw)

    web = Web(informes=[VALIDO])
    extra = {'criterio_fijas': criterio} if criterio else {}
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('libros'), periodo='2026-07',
                              reconvertir=False, transformadores=False, tension_pu=None,
                              bancos=True, libros=LIBROS, **extra) == 0
    esperado = criterio or 'coincidente'
    assert web.cuerpos['/demanda/clientes/cruzar']['criterio'] == esperado
    assert web.cuerpos['/demanda/ajuste/plan']['criterio_fijas'] == esperado


@pytest.mark.parametrize('a_su_maxima', [None, [], ['11', '14']])
def test_los_clientes_a_su_maxima_van_al_cruce_y_al_plan(herramienta, a_su_maxima):
    """039:RF-16, 039:RF-17 — ``--a-su-maxima`` va al cruce y al plan; sin la opción no se manda y la web usa la
    selección guardada en el espacio; vacía, ninguno."""
    class Web(WebFalsa):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.cuerpos: dict[str, dict | None] = {}

        def post(self, ruta, **kw):
            self.cuerpos[ruta] = kw.get('json')
            return super().post(ruta, **kw)

    web = Web(informes=[VALIDO])
    assert herramienta.correr(web, 'Pisco', demanda_dir=Path('libros'), periodo='2026-07',
                              reconvertir=False, transformadores=False, tension_pu=None,
                              bancos=True, libros=LIBROS, a_su_maxima=a_su_maxima) == 0
    for ruta in ('/demanda/clientes/cruzar', '/demanda/ajuste/plan'):
        if a_su_maxima is None:
            assert 'a_su_maxima' not in web.cuerpos[ruta]
        else:
            assert web.cuerpos[ruta]['a_su_maxima'] == a_su_maxima


def test_con_proyecto_espera_el_que_corre_o_lo_lanza(herramienta, capsys, tmp_path):
    """042:RF-31 — Pisco: se espera el «Con proyecto» ya lanzado; si no hay, se lanza; el resumen queda escrito."""
    class Web:
        def __init__(self, jobs):
            self.jobs, self.lanzados = jobs, []

        def get(self, ruta):
            return {'jobs': self.jobs}

        def post(self, ruta, json=None):
            self.lanzados.append((ruta, json))
            return {'id': 'nuevo', 'status': 'queued'}

        def esperar(self, trabajo, limite_s=0):
            return {'id': trabajo['id'], 'status': 'done', 'result': {'escalera': {'alimentadores': [
                {'alimentador': 'F1', 'ya_cumple': True}, {'alimentador': 'F2', 'elegida': 'terna hasta L9'},
                {'alimentador': 'F3'}]}}}

    corre = Web([{'id': 'j1', 'kind': 'obras_con_proyecto', 'title': 'Optimizar «Con proyecto» · P', 'status': 'running'}])
    herramienta._RESUMEN[:] = [tmp_path / 'r.json']
    assert herramienta.con_proyecto(corre, 'P', ['F1', 'F2', 'F3']) == 0 and not corre.lanzados
    salida = capsys.readouterr().out
    assert 'se espera el trabajo j1' in salida and 'F1: ya cumple' in salida and 'F2: obra terna hasta L9' in salida
    assert 'F3: ninguna variante cumple' in salida and (tmp_path / 'r.json').is_file()
    vacia = Web([])
    herramienta._RESUMEN[:] = []
    assert herramienta.con_proyecto(vacia, 'P', ['F1'], tipo_cambio=3.495) == 0
    assert vacia.lanzados == [('/pf/obras/con-proyecto', {'project': 'P', 'feeders': ['F1'], 'escalera_primero': True,
                                                          'tipo_cambio': 3.495})]


def test_con_proyecto_no_adopta_un_trabajo_terminado_y_pasa_el_capex(herramienta):
    """042:RF-31, 042:RF-7 — un «Con proyecto» ya terminado no cuenta: se lanza otro, con su libro CAPEX."""
    class Web:
        lanzado = None

        def get(self, ruta):
            return {'jobs': [{'id': 'viejo', 'kind': 'obras_con_proyecto', 'title': '· P', 'status': 'done'}]}

        def post(self, ruta, json=None):
            Web.lanzado = json
            return {'id': 'nuevo', 'status': 'queued'}

        def esperar(self, trabajo, limite_s=0):
            return {'id': trabajo['id'], 'status': 'done', 'result': {}}

    herramienta._RESUMEN[:] = []
    assert herramienta.con_proyecto(Web(), 'P', ['F1'], capex='libro.xlsx') == 0
    assert Web.lanzado['capex'] == 'libro.xlsx'


def test_083_rf31_el_plan_pide_los_transformadores_en_la_misma_pasada(herramienta):
    """083:RF-31 — sin ``--transformadores`` (que simula antes), el plan pide que el guion cambie en la misma
    pasada las fijas sobre su transformador; ya no hace falta un intento fallido para cambiarlas."""
    web = WebFalsa(informes=[VALIDO])
    enviados = []
    original = web.post

    def post(ruta, **kw):
        if ruta == '/demanda/ajuste/plan':
            enviados.append(kw['json'])
        return original(ruta, **kw)

    web.post = post
    assert _correr(herramienta, web) == 0
    assert enviados and enviados[0]['transformadores_automaticos'] is True


def test_aplica_las_cargas_nuevas_del_libro_antes_de_con_proyecto(herramienta, tmp_path, capsys):
    """007:RF-40, 042:RF-31 — con `--cargas-nuevas`, el plan con el libro sobre el último ajuste del proyecto y solo sus
    alimentadores, aplicado por la web como el paso 3. Pisco de prueba (2026-11-07): «Con proyecto» no tenía cargas."""
    libro = tmp_path / 'nuevas.xlsx'
    libro.write_bytes(b'xlsx')
    llamadas = []

    class Web:
        def get(self, ruta, **kw):
            llamadas.append(('GET', ruta, kw))
            return {'ajuste': {'id': 'disco:abc123'}}

        def post(self, ruta, **kw):
            llamadas.append(('POST', ruta, kw))
            if ruta == '/lote/plan':
                return {'token': 'T1', 'nuevas': [{'sed': 'PI_3', 'alimentador': 'AL209'}, {'sed': 'PI_4', 'alimentador': 'AL209'},
                                                  {'sed': 'X', 'alimentador': 'NA205'}], 'n_nuevas': 3, 'row_errors': [],
                        'avisos': [], 'applicable': True}
            return {'id': 'J1', 'title': 'Aplicar cargas'}

        def esperar(self, trabajo, limite_s=0):
            return {'id': trabajo['id'], 'status': 'done', 'result': {}}

    assert herramienta.aplicar_cargas_nuevas(Web(), 'P', ['AL209', 'PA217'], libro) == 0
    get, plan, aplicar = llamadas
    assert get[1] == '/demanda/ajuste/ultimo' and get[2]['params'] == {'project': 'P'}
    assert plan[1] == '/lote/plan' and plan[2]['data'] == {'project': 'P', 'feeders': ['AL209', 'PA217'],
                                                           'ajuste_job_id': 'disco:abc123'}
    assert 'create_file' in plan[2]['files'] and aplicar[1] == '/lote/T1/apply'
    assert '2 cargas nuevas de AL209, PA217 (de 3 del libro)' in capsys.readouterr().out


def test_con_proyecto_sin_proyecto_sigue_tras_calibrar(herramienta, monkeypatch, tmp_path):
    """042:RF-31 — `--con-proyecto` sin `--proyecto`: calibra y sigue con el proyecto recién calibrado, con sus cargas.
    CA101 + CHN102 (098 T6, 2026-11-08): calibraba y terminaba sin «Con proyecto»."""
    hechos = []

    class Web:
        def __init__(self, *a, **k):
            pass

        def get(self, ruta, **kw):
            return {'pf_projects': {'CA101_CHN102': 'P_CAL'}}

    monkeypatch.setattr(herramienta, 'Web', Web)
    monkeypatch.setattr(herramienta, 'libros_de_la_demanda', lambda d, dados: ({}, []))
    monkeypatch.setattr(herramienta, 'correr', lambda *a, **k: hechos.append('calibra') or 0)
    monkeypatch.setattr(herramienta, 'aplicar_cargas_nuevas', lambda web, p, f, libro: hechos.append(('cargas', p, f)) or 0)
    monkeypatch.setattr(herramienta, 'con_proyecto', lambda web, p, f, **k: hechos.append(('con', p, f, k['rehacer_obras'])) or 0)
    base = ['--espacio', 'E', '--red', 'CA101', 'CHN102', '--grupo', 'CA101_CHN102', '--demanda-dir', str(tmp_path),
            '--con-proyecto', 'CA101', 'CHN102', '--rehacer-obras']
    assert herramienta.main(base + ['--cargas-nuevas', str(tmp_path / 'n.xlsx')]) == 0
    assert hechos == ['calibra', ('cargas', 'P_CAL', ['CA101', 'CHN102']), ('con', 'P_CAL', ['CA101', 'CHN102'], True)]
    hechos.clear()
    monkeypatch.setattr(herramienta, 'correr', lambda *a, **k: hechos.append('calibra') or 2)
    assert herramienta.main(base) == 2 and hechos == ['calibra']


def test_un_trabajo_interrumpido_cuenta_como_terminado(herramienta):
    """086:RF-9 — tras un reinicio de la web el trabajo cortado queda «interrumpido»: el cliente no lo espera para siempre."""
    assert 'interrumpido' in herramienta.TERMINADOS


class WebConCarpeta(WebRed):
    """La carpeta de DIgSILENT ya tiene proyectos, y el espacio, ningún vínculo (copia de PA217, 2026-11-13)."""

    def __init__(self, red, grupo, carpeta, *, fuente='txt', **kw):
        super().__init__(red, grupo, **kw)
        self.carpeta, self.fuente = list(carpeta), fuente

    def get(self, ruta, **kw):
        respuesta = super().get(ruta, **kw)
        if ruta == '':
            respuesta['source_mode'] = self.fuente
        return respuesta

    def esperar(self, trabajo):
        if trabajo['id'] == '/powerfactory/projects' and self.fallo != trabajo['id']:
            return {'status': 'done', 'result': {'folder': 'C', 'exists': True, 'projects': [
                {'name': n.rsplit('/', 1)[-1], 'path': n, 'feeders': []} for n in self.carpeta]}}
        return super().esperar(trabajo)


def test_005_rf24_sin_vinculo_no_importa_encima_de_un_proyecto_del_grupo(herramienta, capsys):
    """005:RF-24 — sin vínculo y sin ``--reconvertir``, un proyecto del grupo con sello anterior en la carpeta no se
    importa de nuevo: la importación lo habría borrado (005:RF-22) y era el ya trabajado por el usuario."""
    web = WebConCarpeta(['PA217'], 'PA217', ['20261112-113130_CSG_TXT_PA217', 'OTRO_A_MANO'])
    assert _correr_red(herramienta, web) == 2
    assert '/powerfactory/flow' not in web.enviados, 'importar habría borrado 20261112-113130_CSG_TXT_PA217'
    assert '/demanda/ajuste/plan' not in web.enviados
    salida = capsys.readouterr().out
    assert '20261112-113130_CSG_TXT_PA217' in salida and '--reconvertir' in salida


def test_005_rf24_lo_que_la_importacion_no_borraria_no_la_impide(herramienta):
    """005:RF-24 — otra fuente, otro grupo, uno a mano o uno en una subcarpeta no los borra la 005:RF-22: se importa."""
    web = WebConCarpeta(['PA217'], 'PA217', ['20261112-113130_CSG_MDB_PA217', '20261112-113130_CSG_TXT_PA2170',
                                             'PA217', 'SUB/20261112-113130_CSG_TXT_PA217'])
    assert _correr_red(herramienta, web) == 0
    assert '/powerfactory/flow' in web.enviados


def test_005_rf24_con_reconvertir_se_importa_y_se_sabe(herramienta):
    """005:RF-24 — ``--reconvertir`` es la orden de reemplazarlo: no se pregunta ni se lee la carpeta."""
    web = WebConCarpeta(['PA217'], 'PA217', ['20261112-113130_CSG_TXT_PA217'])
    assert herramienta.correr(web, None, demanda_dir=Path('libros'), periodo='2026-07', reconvertir=True,
                              transformadores=False, tension_pu=None, bancos=True, libros=LIBROS,
                              red=web.red) == 0
    assert '/powerfactory/flow' in web.enviados


def test_005_rf24_si_no_se_puede_leer_la_carpeta_no_se_importa_a_ciegas(herramienta, capsys):
    """005:RF-24 — sin la lista de la carpeta no se sabe qué borraría la importación: se para."""
    web = WebConCarpeta(['PA217'], 'PA217', [], fallo='/powerfactory/projects')
    assert _correr_red(herramienta, web) == 2
    assert '/powerfactory/flow' not in web.enviados


class WebBorradoConCarpeta(WebConProyectoBorrado):
    """018:RF-17 con la carpeta: el vínculo nombra un proyecto que ya no está, pero hay otra versión del grupo."""

    def get(self, ruta, **kw):
        respuesta = super().get(ruta, **kw)
        if ruta == '':
            respuesta['source_mode'] = 'txt'
        return respuesta

    def esperar(self, trabajo):
        if trabajo['id'] == '/powerfactory/projects':
            return {'status': 'done', 'result': {'projects': [
                {'name': '20261112-113130_CSG_TXT_SISTEMA_PISCO', 'path': '20261112-113130_CSG_TXT_SISTEMA_PISCO'}]}}
        return super().esperar(trabajo)


def test_005_rf24_el_proyecto_borrado_no_se_reimporta_encima_de_otra_version(herramienta, capsys):
    """005:RF-24, 018:RF-17 — al reimportar el vínculo que ya no existe, la otra versión del grupo tampoco se borra."""
    web = WebBorradoConCarpeta(proyecto='P_BORRADO', informes=[VALIDO])
    assert _correr(herramienta, web) == 2
    assert ('POST', '/powerfactory/flow') not in web.llamadas
    assert '20261112-113130_CSG_TXT_SISTEMA_PISCO' in capsys.readouterr().out
