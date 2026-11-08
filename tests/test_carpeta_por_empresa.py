"""Spec 081: una carpeta de DIgSILENT por empresa; nada se bloquea por no saberla. Nombres inventados y sorteados."""
from __future__ import annotations

import json
import random
import re
import string
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.carpeta_pf import (
    LARGO_MAXIMO, NOMBRE_POR_DEFECTO, asegurar_carpeta, carpeta_de_empresa, decidir_carpeta, nombre_libre, validar_nombre,
)
from convertersmartgrid.powerfactory_binding import ProjectBindingError
from convertersmartgrid.web import services

RAIZ = Path(__file__).resolve().parents[1]
_AZAR = random.Random(81)


def _nombre():
    return 'Dist ' + ''.join(_AZAR.choices(string.ascii_uppercase, k=6))


def _perfil_carpeta():
    return 'carpeta_propia'


def _espacio(fuente=None, operador=None, vinculos=None):
    return SimpleNamespace(inventory={'provenance': {'company': fuente}}, options={'empresa_espacio': operador},
                           pf_project_bindings=vinculos or {}, vinculos_compartidos=None)


@pytest.fixture
def perfil(monkeypatch):
    def poner(datos):
        monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda *a, **k: datos)
        monkeypatch.setattr(services, 'carpeta_pf', _perfil_carpeta)
    return poner


@pytest.mark.parametrize('semilla', range(5))
def test_regla_de_la_fuente_o_del_operador(semilla):
    """081:RF-50 — la fuente manda; si no dice, el operador. Con cualquier nombre: ninguno está en el código."""
    azar = random.Random(semilla)
    uno, otro = f'Empresa {azar.randint(1, 9999)}', f'Otra {azar.randint(1, 9999)}'
    d = decidir_carpeta(uno, otro, (), _perfil_carpeta, hay_perfil=False)
    assert (d.carpeta, d.empresa, d.origen, d.supuesto) == (uno, uno, 'fuente', False)
    d = decidir_carpeta('', otro, (), _perfil_carpeta, hay_perfil=False)
    assert (d.carpeta, d.empresa, d.origen, d.supuesto) == (otro, otro, 'operador', False)


def test_regla_la_del_perfil_y_otra_empresa():
    """081:RF-52 — la suya sin distinguir mayúsculas, a la carpeta del perfil; otra, a la de su nombre."""
    propia, ajena = _nombre(), _nombre()
    assert decidir_carpeta(propia.lower(), None, (propia,), _perfil_carpeta, hay_perfil=True).carpeta == 'carpeta_propia'
    assert decidir_carpeta(ajena, None, (propia,), _perfil_carpeta, hay_perfil=True).carpeta == ajena
    # El fallo real: un perfil sin código daba la del perfil aunque la fuente dijera otra empresa.
    assert decidir_carpeta(ajena, None, (None,), _perfil_carpeta, hay_perfil=True).carpeta == ajena


def test_nombre_raro_no_impide_importar():
    """081:RF-52 — el nombre siempre es válido: ni con caracteres no admitidos ni largo hay error."""
    for raro in ('Dist. del Sur/Norte', 'A' * 90, ' .* ', 'Dist: "X"?'):
        carpeta = carpeta_de_empresa(raro)
        assert validar_nombre(carpeta) == carpeta and len(carpeta) <= LARGO_MAXIMO
    d = decidir_carpeta('Dist. 1', None, (), _perfil_carpeta, hay_perfil=False)
    assert d.carpeta == 'Dist_ 1' and 'Dist_ 1' in d.aviso


def test_sin_saber_la_empresa_no_bloquea():
    """081:RF-53 — el supuesto del perfil y, sin perfil, la neutra; los dos lo dicen."""
    d = decidir_carpeta(None, ' ', ('X',), _perfil_carpeta, hay_perfil=True)
    assert (d.carpeta, d.origen, d.supuesto) == ('carpeta_propia', 'perfil', True) and 'se supone' in d.aviso
    d = decidir_carpeta(None, None, (), lambda: NOMBRE_POR_DEFECTO, hay_perfil=False)
    assert (d.carpeta, d.origen, d.supuesto) == (NOMBRE_POR_DEFECTO, 'sin_empresa', True) and 'neutra' in d.aviso


def test_perfil_roto_no_afecta_a_otra_empresa(monkeypatch):
    """081:RF-52 — con el perfil ilegible y una empresa conocida, su carpeta y sin error."""
    from convertersmartgrid.perfil_empresa import PerfilError

    def roto(*_a, **_k):
        raise PerfilError('roto')

    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', roto)
    monkeypatch.setattr(services, 'carpeta_pf', lambda: pytest.fail('no hace falta la del perfil'))
    nombre = _nombre()
    assert services.carpeta_de(_espacio(nombre)) == nombre


def test_carpeta_mal_escrita_no_da_error():
    """081:RF-61 — empresa desconocida: la neutra y el aviso con lo que está mal; empresa conocida: la de su nombre."""
    from convertersmartgrid.carpeta_pf import CarpetaError

    def mal():
        raise CarpetaError("carpeta 'a/b' mal escrita")

    d = decidir_carpeta(None, None, ('X',), mal, hay_perfil=True)
    assert (d.carpeta, d.origen, d.supuesto) == (NOMBRE_POR_DEFECTO, 'sin_empresa', True) and "'a/b'" in d.aviso
    assert decidir_carpeta('X', None, ('X',), mal, hay_perfil=True).carpeta == 'X'


def test_el_espacio_guarda_la_empresa_aparte_de_la_fuente(tmp_path, perfil):
    """081:RF-51 — por la ruta de opciones; un TXT sin empresa va a la que indicó. No se confunde con ``source_company``."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import app as app_mod

    perfil({'codigo_empresa': 'PROPIA'})
    cliente = TestClient(app_mod.create_app(tmp_path))
    wid = cliente.post('/api/workspaces').json()['id']
    nombre = _nombre()
    r = cliente.put(f'/api/workspaces/{wid}/options', json={'empresa_espacio': nombre})
    assert r.status_code == 200, r.text
    assert r.json()['options']['empresa_espacio'] == nombre and r.json()['options']['source_company'] is None
    ws = cliente.app.state.store.get(wid)
    assert services.destino_carpeta(ws).carpeta == nombre and services.destino_carpeta(ws).origen == 'operador'
    # Guardado de verdad: al volver a leer el espacio sigue.
    assert json.loads((ws.root / 'workspace.json').read_text(encoding='utf-8'))['options']['empresa_espacio'] == nombre


def test_lo_ya_importado_se_lee_de_su_vinculo(perfil):
    """081:RF-54 — aunque cambie la empresa del espacio: lo importado sigue donde está."""
    perfil({'codigo_empresa': 'PROPIA'})
    vinculo = {'P': {'project': 'P', 'folder': 'Empresa Antigua'}}
    ws = _espacio('Empresa Nueva', vinculos=vinculo)
    assert services.carpeta_de(ws, 'P') == 'Empresa Antigua'
    assert services.carpeta_de(ws, 'SIN_VINCULO') == 'Empresa Nueva' == services.carpeta_de(ws)


def test_el_espacio_retira_empresa_explicita_sin_borrar_otras_opciones(tmp_path, perfil):
    """081:RF-51, 081:RF-53 — null explícito retira la empresa; omitirla la conserva."""
    from fastapi.testclient import TestClient
    from convertersmartgrid.web.app import create_app
    perfil({})
    with TestClient(create_app(tmp_path)) as cliente:
        wid = cliente.post('/api/workspaces').json()['id']
        base = f'/api/workspaces/{wid}'
        r = cliente.put(base + '/options', json={'empresa_espacio': _nombre(), 'workers': 1})
        assert r.status_code == 200
        nombre = r.json()['options']['empresa_espacio']
        r = cliente.put(base + '/options', json={'export_tsv': True})
        assert r.json()['options']['empresa_espacio'] == nombre
        r = cliente.put(base + '/options', json={'empresa_espacio': None})
        assert r.status_code == 200 and r.json()['options']['empresa_espacio'] is None
        leido = cliente.get(base).json()['options']
        assert leido['empresa_espacio'] is None and leido['workers'] == 1 and leido['export_tsv'] is True
        ws = cliente.app.state.store.get(wid)
        assert json.loads((ws.root / 'workspace.json').read_text(encoding='utf-8'))['options']['empresa_espacio'] is None
        assert services.destino_carpeta(ws).supuesto is True


def test_vinculo_ilegible_no_bloquea(perfil, monkeypatch):
    """081:RF-54, 081:RF-53 — si el registro no se puede leer, la de la regla."""
    perfil({'codigo_empresa': 'PROPIA'})

    def falla(*_a):
        raise ProjectBindingError('X', 'ilegible')

    monkeypatch.setattr('convertersmartgrid.powerfactory_binding.vinculo_guardado', falla)
    assert services.carpeta_de(_espacio('Empresa Nueva'), 'P') == 'Empresa Nueva'


def test_ningun_plan_sale_sin_la_carpeta_de_su_vinculo():
    """081:RF-54 — todo plan con proyecto pasa por ``carpeta_de(ws, proyecto)``; ``carpeta_pf`` solo la usa la regla."""
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert not re.findall(r"'project': (?:project|proyecto)[^\n]*'folder': carpeta_de\(ws\)", fuente)
    assert "'--pf-carpeta', carpeta_de(ws, project), '--source-dgs'" in fuente
    usos = [m for m in re.findall(r'^.*\bcarpeta_pf\b(?!\.py).*$', fuente, re.M) if 'from ..carpeta_pf' not in m]
    assert [u for u in usos if 'def carpeta_pf' not in u and u.strip() != 'return carpeta_pf()'] == []


def test_no_se_ofrece_el_proyecto_de_otra_empresa(tmp_path, perfil):
    """081:RF-55 — la lectura de proyectos es de su carpeta; otra carpeta, otro inventario."""
    perfil({'codigo_empresa': 'PROPIA'})
    raiz = tmp_path / 'espacios'
    otra = raiz / 'otra'
    otra.mkdir(parents=True)
    (otra / 'workspace.json').write_text(json.dumps({'pf_inventory': {'folder': 'Empresa B', 'projects': [{'name': 'PB'}], 'leido': 1}}), encoding='utf-8')
    (raiz / 'mio').mkdir()
    ws = _espacio('Empresa A')
    ws.root = raiz / 'mio'
    assert services._lectura_mas_reciente_de_la_carpeta(ws) is None


class _Carpeta:
    def __init__(self, nombre, clase='IntFolder', hijos=None):
        self.loc_name, self.clase, self.hijos, self.borrados = nombre, clase, list(hijos or []), []

    def GetClassName(self):
        return self.clase

    def GetContents(self):
        return list(self.hijos)

    def CreateObject(self, clase, nombre):
        nuevo = _Carpeta(nombre, clase)
        self.hijos.append(nuevo)
        return nuevo


def test_crea_su_carpeta_y_no_mueve_nada():
    """081:RF-56 — existe o se crea (005:RF-5); un proyecto ya colocado en otra carpeta se queda donde está."""
    ajeno = _Carpeta('P_de_otra', 'IntPrj')
    de_otra = _Carpeta('Empresa A', hijos=[ajeno])
    usuario = _Carpeta('usuario', 'IntUser', [de_otra])
    nueva = asegurar_carpeta(usuario, 'Empresa B')
    assert nueva.loc_name == 'Empresa B' and asegurar_carpeta(usuario, 'Empresa B') is nueva
    assert de_otra.hijos == [ajeno] and asegurar_carpeta(usuario, 'Empresa A') is de_otra
    assert nombre_libre(nueva, 'P_de_otra') == 'P_de_otra', 'cada carpeta tiene sus nombres'


def test_se_dice_en_la_estructura_y_al_importar():
    """081:RF-53 — en el plan a la vista y en el resultado de la importación, también el supuesto."""
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert "perfil_no_aplicado['carpeta_destino'] = asdict(destino)" in fuente and "'carpeta': asdict(destino)," in fuente
    assert 'ctx.log(destino.aviso)' in fuente
    assert 'estructura?.carpeta_destino?.aviso' in (RAIZ / 'frontend/src/components/FeedersPanel.tsx').read_text(encoding='utf-8')
