"""004:RF-109, RF-110 — la importación del ``.pfd`` desde la web devuelve los vínculos del proyecto con los ficheros de su
expediente, por su contenido y con su evidencia.

Auditoría D.3 (2026-11-24): ``adaptadores/pfd_vinculos.py`` tenía sus pruebas (T28) pero ningún flujo lo llamaba, y la
web no enseñaba los vínculos que pide la prueba real (T30). Sin DIgSILENT: el diagnóstico es un JSON escrito a mano.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from convertersmartgrid.presentacion.web import services


def _expediente(tmp_path: Path) -> Path:
    carpeta = tmp_path / 'expediente'
    carpeta.mkdir()
    (carpeta / 'proyecto.pfd').write_bytes(b'no se lee')
    (carpeta / 'memoria.txt').write_text('La memoria describe el caso Z_CASO_2031 y el alimentador Z_ALIM_7.', encoding='utf-8')
    (carpeta / 'otro.txt').write_text('Un texto que no nombra nada del proyecto.', encoding='utf-8')
    return carpeta / 'proyecto.pfd'


def test_004_rf109_la_importacion_devuelve_los_vinculos_por_contenido(tmp_path, monkeypatch):
    pfd = _expediente(tmp_path)
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: SimpleNamespace(sets={'Z_SET_1': None}))
    informe = {'proyectos': [{'proyecto': 'Z_PRY', 'casos': [{'caso': 'Z_CASO_2031'}],
                              'red': {'alimentadores': ['Z_ALIM_7']}}]}
    vinculos = services.pfd_vinculos_del_expediente(SimpleNamespace(), pfd.parent, informe)
    assert [v['proyecto'] for v in vinculos] == ['Z_PRY']
    hallados = {(v['tipo'], v['nombre'], v['fichero']) for v in vinculos[0]['vinculos']}
    assert ('caso', 'Z_CASO_2031', 'memoria.txt') in hallados and ('alimentador', 'Z_ALIM_7', 'memoria.txt') in hallados
    assert not any(f == 'otro.txt' for _t, _n, f in hallados), 'un fichero que no nombra nada no se vincula'
    v = next(x for x in vinculos[0]['vinculos'] if x['nombre'] == 'Z_CASO_2031')
    assert v['sha256'] and 'Z_CASO_2031' in v['texto'], '004:RF-110: cada vínculo lleva su evidencia'
    assert 'set «Z_SET_1»' in vinculos[0]['sin_vinculo'], 'lo que ningún fichero nombra se dice'


def test_004_rf109_sin_carpeta_del_expediente_no_hay_vinculos(tmp_path):
    assert services.pfd_vinculos_del_expediente(SimpleNamespace(), tmp_path / 'no_existe', {'proyectos': [{'proyecto': 'P'}]}) == []


def test_004_rf109_la_accion_de_importar_los_incluye_en_su_resultado():
    import inspect
    fuente = inspect.getsource(services.pfd_importar)
    assert "pfd_vinculos_del_expediente(ws, expediente, informe, ctx) if expediente else []" in fuente


def test_004_rf109_la_ruta_del_expediente_solo_en_local_y_existente(tmp_path, monkeypatch):
    """La carpeta del expediente es una ruta de este equipo: con la web sin host conocido se rechaza (403), y una carpeta
    que no existe da 400 antes de encolar nada."""
    from fastapi.testclient import TestClient
    from convertersmartgrid.presentacion.web.app import create_app
    app = create_app(tmp_path / 'web', host='127.0.0.1')
    with TestClient(app) as cliente:
        wid = cliente.post('/api/workspaces', json={'name': 'exp'}).json()['id']
        r = cliente.post(f'/api/workspaces/{wid}/pf/pfd', files={'file': ('p.pfd', b'x')},
                         data={'expediente': str(tmp_path / 'no_existe')})
        assert r.status_code == 400 and 'expediente' in r.text
