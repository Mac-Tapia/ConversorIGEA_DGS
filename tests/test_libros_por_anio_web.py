"""Spec 025 en la web: índice de cabecera por año como trabajo y búsqueda por periodo.

Los libros se escriben aquí, sintéticos, con nombres que no son de ninguna empresa.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _wid(client):
    return client.post('/api/workspaces').json()['id']


def _cabecera(path: Path, hojas: dict[str, tuple[datetime, float]]) -> Path:
    """Cada hoja: cuatro registros cada 15 min desde su fecha, con el pico dado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, (t0, pico) in hojas.items():
        h = wb.create_sheet(nombre)
        h.append(['Local Time', 'kW tot', 'kVAR tot'])
        for i, kw in enumerate([pico / 2, pico, pico / 3, pico / 4]):
            h.append([t0 + timedelta(minutes=15 * i), kw, kw / 5])
    wb.save(path)
    return path


def _arbol(raiz: Path) -> Path:
    _cabecera(raiz / '2025/medicion 2025.xlsx', {'M1': (datetime(2025, 5, 2), 700.0)})
    _cabecera(raiz / '2026/zona/medicion 2026.xlsx', {'M1': (datetime(2026, 3, 9), 900.0),
                                                     'M2': (datetime(2026, 4, 1), 50.0)})
    sin = openpyxl.Workbook()
    sin.active.append(['nada que ver'])
    sin.save(raiz / '2026/notas.xlsx')
    (raiz / '2025/roto.xlsx').write_bytes(b'no es un libro')
    return raiz


def _asignar_e_indexar(client, wid, carpeta: Path) -> dict:
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/path', json={'path': str(carpeta)})
    assert r.status_code == 200, r.text
    return _indexar(client, wid)


def _indexar(client, wid) -> dict:
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/indexar')
    assert r.status_code == 202, r.text
    assert r.json()['lane'] == 'engine'
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    return client.get(f'/api/workspaces/{wid}').json()['demanda']['cabecera']


def test_indice_de_cabecera_por_anio(client, tmp_path):
    """025:RF-4, 025:RF-28, 025:RF-29, 025:RF-32 — trabajo del motor; cada libro con su año, hojas y
    meses; el que no sirve, con su motivo, sin parar a los demás."""
    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    meta = _asignar_e_indexar(client, wid, carpeta)
    assert meta['anios'] == [2025, 2026] and meta['vigente'] is True
    por = {x['relativa']: x for x in meta['indice']}
    assert set(por) == {'2025/medicion 2025.xlsx', '2025/roto.xlsx',
                        '2026/notas.xlsx', '2026/zona/medicion 2026.xlsx'}
    assert (por['2025/medicion 2025.xlsx']['anio'], por['2025/medicion 2025.xlsx']['hojas'],
            por['2025/medicion 2025.xlsx']['meses']) == (2025, ['M1'], ['2025-05'])
    assert por['2026/zona/medicion 2026.xlsx']['hojas'] == ['M1', 'M2']
    assert por['2026/zona/medicion 2026.xlsx']['meses'] == ['2026-03', '2026-04']
    assert por['2025/roto.xlsx']['error'] and not por['2025/roto.xlsx']['hojas']
    assert 'fecha y kW' in por['2026/notas.xlsx']['error']
    assert str(carpeta) not in str(meta['indice'])


def test_indice_solo_reabre_lo_nuevo_o_cambiado(client, tmp_path, monkeypatch):
    """025:RF-27, 025:RF-28 — un libro sin cambios no se vuelve a abrir; uno nuevo sí."""
    from igea_dgs import demanda_medida as dm

    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    _asignar_e_indexar(client, wid, carpeta)
    abiertos: list[str] = []
    real = dm.indexar_libro_cabecera

    def contar(path, *a, **k):
        abiertos.append(Path(path).name)
        return real(path, *a, **k)

    monkeypatch.setattr(dm, 'indexar_libro_cabecera', contar)
    _indexar(client, wid)
    assert abiertos == []
    _cabecera(carpeta / '2027/nuevo.xlsx', {'M1': (datetime(2027, 1, 5), 10.0)})
    meta = _indexar(client, wid)
    assert abiertos == ['nuevo.xlsx'] and meta['anios'] == [2025, 2026, 2027]


def test_cancelar_el_indice_conserva_el_anterior(client, tmp_path):
    """025:RF-33 — cancelado a mitad, queda el índice anterior entero."""
    from igea_dgs.web import services
    from igea_dgs.web.jobs import JobCancelled

    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    antes = _asignar_e_indexar(client, wid, carpeta)
    _cabecera(carpeta / '2027/nuevo.xlsx', {'M1': (datetime(2027, 1, 5), 10.0)})
    ws = client.app.state.store.get(wid)

    class Ctx:
        vistos = 0

        def progress(self, *_a):
            pass

        def log(self, *_a):
            pass

        def check_cancel(self):
            Ctx.vistos += 1
            if Ctx.vistos > 2:
                raise JobCancelled()

    with pytest.raises(JobCancelled):
        services.demanda_cabecera_indexar(ws, Ctx())
    assert ws.demanda['cabecera']['indice'] == antes['indice']
    assert ws.demanda['cabecera']['anios'] == [2025, 2026]


def test_indice_que_cambia_mientras_se_construye(client, tmp_path, monkeypatch):
    """025:RF-31 — la carpeta cambió durante el índice: no vigente, y se pide actualizar."""
    from igea_dgs import demanda_medida as dm

    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/demanda/cabecera/path',
                       json={'path': str(carpeta)}).status_code == 200
    real = dm.indexar_libro_cabecera

    def indexar_y_cambiar(path, *a, **k):
        _cabecera(carpeta / '2026/llego tarde.xlsx', {'M9': (datetime(2026, 1, 1), 1.0)})
        return real(path, *a, **k)

    monkeypatch.setattr(dm, 'indexar_libro_cabecera', indexar_y_cambiar)
    meta = _indexar(client, wid)
    assert meta['vigente'] is False
    assert any('Actualizar índice' in a for a in meta['avisos'])


# =========================================================================== T5: por periodo
def _buscar(client, wid, periodo):
    cuerpo = {'medidores': [{'alimentador': 'A1', 'medidor': 'M1'}]}
    if periodo is not None:
        cuerpo['periodo'] = periodo
    return client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json=cuerpo)


@pytest.mark.parametrize('periodo, kw, mes', [('2025', 700.0, '2025-05'),
                                              ('2026', 900.0, '2026-03'),
                                              ('2026-03', 900.0, '2026-03')])
def test_maxima_solo_con_los_libros_de_su_anio(client, tmp_path, periodo, kw, mes):
    """025:RF-7, RF-8 — el año o el mes eligen los libros de su carpeta; nunca los de otro año."""
    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    _asignar_e_indexar(client, wid, carpeta)
    r = _buscar(client, wid, periodo)
    assert r.status_code == 202, r.text
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    (res,) = estado['result']['resultados']
    assert res['error'] is None and res['kw'] == kw and res['fecha'][:7] == mes
    assert res['libro'].startswith('medicion ' + periodo[:4])
    assert estado['result']['periodo'] == periodo
    # 025:RF-29: el libro roto de 2025 no impide buscar; se dice.
    assert any('roto.xlsx' in a for a in res['avisos']) is (periodo == '2025')


def test_sin_periodo_y_con_anios_no_busca(client, tmp_path):
    """025:RF-9 — con libros de varios años y sin periodo, se pide el año."""
    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    _asignar_e_indexar(client, wid, carpeta)
    r = _buscar(client, wid, None)
    estado = esperar_trabajo(client, r.json()) if r.status_code == 202 else None
    detalle = (estado or {}).get('error') or r.text
    assert 'elija el año' in detalle


def test_indice_no_vigente_no_busca(client, tmp_path):
    """025:RF-31 — si el índice quedó viejo, se pide actualizarlo antes de buscar."""
    carpeta = _arbol(tmp_path / 'cabecera')
    wid = _wid(client)
    _asignar_e_indexar(client, wid, carpeta)
    ws = client.app.state.store.get(wid)
    with ws.lock:
        ws.demanda['cabecera']['vigente'] = False
    r = _buscar(client, wid, '2025')
    estado = esperar_trabajo(client, r.json()) if r.status_code == 202 else None
    assert 'Actualizar índice' in ((estado or {}).get('error') or r.text)


def _clientes(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.active.title = 'Resumen'
    wb.active.append(['SUMINISTRO', 'EA_TOTAL', 'ERI_TOTAL', 'POT_MAX'])
    wb.active.append(['9011', 1.0, 1.0, 1.0])
    wb.save(path)
    return path


def _clientes_por_anio(client, tmp_path) -> tuple[str, object]:
    carpeta = tmp_path / 'clientes'
    _clientes(carpeta / '2025/0725 Grandes.xlsx')
    _clientes(carpeta / '2026/0726 Grandes.xlsx')
    wid = _wid(client)
    assert client.post(f'/api/workspaces/{wid}/demanda/clientes/path',
                       json={'path': str(carpeta)}).status_code == 200
    r = client.post(f'/api/workspaces/{wid}/demanda/clientes/indexar')
    assert esperar_trabajo(client, r.json())['status'] == 'done'
    return wid, client.app.state.store.get(wid)


def test_clientes_del_mes_de_la_maxima_en_su_subcarpeta(client, tmp_path):
    """025:RF-10 — la máxima de julio de 2025 cruza con el libro de julio de su carpeta 2025."""
    from igea_dgs.web import services

    _wid_, ws = _clientes_por_anio(client, tmp_path)
    ev = services.periodo_clientes_activo(ws, '2025-07')
    assert (ev.status, ev.period, ev.file) == ('CLIENT_PERIOD_VERIFIED', '2025-07', '0725 Grandes.xlsx')
    assert services._demanda_ruta(ws, 'clientes', periodo='2025-07').parent.name == '2025'


def test_mes_sin_libro_de_clientes_se_reparte_por_kva(client, tmp_path):
    """025:RF-11 — el mes de la máxima no tiene libro en su año: se dice y va por kVA."""
    from igea_dgs.web import services

    _wid_, ws = _clientes_por_anio(client, tmp_path)
    ev = services.periodo_clientes_activo(ws, '2025-03')
    assert ev.status == 'NO_CLIENT_BOOK'
    assert '2025-03' in ev.warning and 'kVA' in ev.warning


def test_asignar_carpeta_lista_los_anios_sin_abrir_libros(client, tmp_path, monkeypatch):
    """025:RF-4, 025:RF-32 — asignar la carpeta solo lista: años y libros, ningún libro abierto."""
    from igea_dgs import demanda_medida as dm

    carpeta = _arbol(tmp_path / 'cabecera')
    monkeypatch.setattr(dm, '_abrir', lambda *_a, **_k: pytest.fail('abrió un libro'))
    wid = _wid(client)
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera/path', json={'path': str(carpeta)})
    assert r.status_code == 200, r.text
    meta = r.json()['demanda']['cabecera']
    assert meta['anios'] == [2025, 2026]
    assert '2026/zona/medicion 2026.xlsx' in meta['libros']
