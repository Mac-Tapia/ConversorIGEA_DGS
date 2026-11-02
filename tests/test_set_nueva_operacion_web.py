"""063:RF-36 a RF-38: intervención explícita de una SET existente por el carril nativo."""
from fastapi.testclient import TestClient

from apoyo import esperar_trabajo
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app


def test_operacion_set_se_encola_en_powerfactory_sin_recrear_set(tmp_path, monkeypatch):
    """063:RF-36, 063:RF-38: la lectura/intervención usa el único carril de PowerFactory."""
    vistos = []

    def ejecutar(ws, ctx, project, feeders, **opciones):
        vistos.append((project, feeders, opciones))
        return {'project': project, 'accion': opciones['accion'], 'aceptada': False}

    monkeypatch.setattr(services, 'set_nueva_operacion', ejecutar, raising=False)
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as client:
        wid = client.post('/api/workspaces').json()['id']
        r = client.post(f'/api/workspaces/{wid}/pf/obras/set-nueva/operacion',
                        json={'project': 'P', 'feeders': ['F1', 'F2'], 'accion': 'diagnostico'})
        assert r.status_code == 202, r.text
        assert r.json()['lane'] == 'powerfactory'
        fin = esperar_trabajo(client, r.json())
        assert fin['status'] == 'done', fin
        assert vistos[0][0:2] == ('P', ['F1', 'F2'])
        assert vistos[0][2]['cambios'] == []
        assert 'alimentadores_nuevos' not in vistos[0][2]
        r = client.post(f'/api/workspaces/{wid}/pf/obras/set-nueva/operacion',
                        json={'project': 'P', 'accion': 'borrar_set'})
        assert r.status_code == 422


def test_formularios_de_set_existente_y_set_nueva_conservan_su_contrato():
    """042:RF-6, 063:RF-38: operar una SET no recibe parámetros de creación de otra SET."""
    from convertersmartgrid.web.app import ObrasIn, SetNuevaOperacionIn

    assert ObrasIn(project='P').alimentadores_nuevos == 4
    assert 'alimentadores_nuevos' not in SetNuevaOperacionIn(project='P').model_dump()
