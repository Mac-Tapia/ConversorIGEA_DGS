"""042:RF-114: la obra de «Obra aparte» se aplica en «Con proyecto» con las obras exactas que midió la escalera."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from convertersmartgrid.presentacion.web import services
from convertersmartgrid.presentacion.web.services import UserError

NOMBRE = 'bancos según perfil 2×450 kvar en 12726, 12651'
OBRAS = [{'clase': 'condensador', 'alimentador': 'LL202', 'casos': ['Con proyecto'], 'barra': b, 'q_kvar': 450.0,
          'escalones': 1} for b in ('12726', '12651')]


def _espacio(tmp_path):
    planes = tmp_path / 'planes'
    planes.mkdir()
    (planes / 'escalera_evaluar_aaa.json').write_text(json.dumps({
        'project': 'P_LL202', 'variantes': [{'nombre': 'bancos 1×450 kvar', 'obras': OBRAS[:1]},
                                            {'nombre': NOMBRE, 'obras': OBRAS}]}), encoding='utf-8')
    (planes / 'escalera_evaluar_bbb.json').write_text(json.dumps({
        'project': 'OTRO', 'variantes': [{'nombre': NOMBRE, 'obras': [{**OBRAS[0], 'barra': 'X'}]}]}), encoding='utf-8')
    return SimpleNamespace(plans_dir=planes)


def test_042_rf114_las_obras_de_la_variante_son_las_medidas(tmp_path):
    """042:RF-114 — las obras exactas de la variante, del proyecto y del alimentador pedidos; si no están, se dice."""
    ws = _espacio(tmp_path)
    assert services.obras_de_la_variante(ws, 'P_LL202', 'LL202', NOMBRE) == OBRAS
    with pytest.raises(UserError, match='vuelva a proponer'):
        services.obras_de_la_variante(ws, 'P_LL202', 'LL203', NOMBRE)
    with pytest.raises(UserError):
        services.obras_de_la_variante(ws, 'P_LL202', 'LL202', 'otra variante')


def test_042_rf114_se_aplican_como_obras_del_operador(tmp_path, monkeypatch):
    """042:RF-114 — se guardan en el espacio y se aplican (no se simulan) solo esas, en su alimentador."""
    ws = _espacio(tmp_path)
    guardadas, llamada = [], {}

    def anadir(_ws, o):
        guardadas.append(o)
        return {'id': f'id{len(guardadas)}', **o}

    def ejecutar(_ws, _ctx, project, feeders, ids, otro, *, simular, **kw):
        llamada.update(project=project, feeders=feeders, ids=ids, simular=simular, kw=kw)
        return {'informe': {}}

    monkeypatch.setattr(services, 'obra_anadir', anadir)
    monkeypatch.setattr(services, 'obras_ejecutar', ejecutar)
    ctx = SimpleNamespace(log=lambda *_: None)
    services.aplicar_obra_aparte(ws, ctx, 'P_LL202', 'LL202', NOMBRE)
    assert guardadas == OBRAS
    assert llamada == {'project': 'P_LL202', 'feeders': ['LL202'], 'ids': ['id1', 'id2'], 'simular': False, 'kw': {}}
