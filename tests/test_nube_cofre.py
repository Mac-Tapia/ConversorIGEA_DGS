"""El cofre de las credenciales de la nube: DPAPI del usuario, por espacio y proveedor (spec 109, T4; 109:RF-2).

``_cofre()`` importa ``convertersmartgrid.adaptadores.nube_cofre`` con una aserción: si aún no existe, la prueba cae por aserción.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import sys

import pytest

from nube_simulada import sin_sockets  # noqa: F401

pytestmark = [pytest.mark.usefixtures('sin_sockets'),
              pytest.mark.skipif(sys.platform != 'win32', reason='DPAPI solo existe en Windows (P8)')]

# Ficticio y corto: el checklist trata como secreto un token de 12 caracteres o más.
TOKEN = 'ref-1//0gX'


def _cofre():
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.nube_cofre') is not None, 'falta convertersmartgrid.adaptadores.nube_cofre'
    return importlib.import_module('convertersmartgrid.adaptadores.nube_cofre')


def test_guarda_cifrado_y_solo_el_token_de_refresco(tmp_path):
    """109:RF-2 — el fichero no lleva el token ni la cuenta en claro; dentro solo va el de refresco."""
    nube_cofre = _cofre()
    ruta = nube_cofre.guardar('w1', 'google', 'ana@ejemplo.org', TOKEN, raiz=tmp_path)
    assert ruta.parent == tmp_path / 'secretos' / 'nube' / 'w1'
    assert ruta.name.startswith('google-') and ruta.suffix == '.dpapi'
    crudo = ruta.read_bytes()
    assert TOKEN.encode() not in crudo and b'ana@ejemplo.org' not in crudo
    cred = nube_cofre.leer('w1', 'google', raiz=tmp_path)
    assert cred is not None and cred.refresco == TOKEN and cred.cuenta == 'ana@ejemplo.org'
    assert TOKEN not in repr(cred), 'el token no puede salir en una traza'
    claro = json.loads(nube_cofre.descifrar(crudo, nube_cofre.entropia('w1', 'google')))
    assert set(claro) == {'cuenta', 'refresco'}


def test_el_cofre_de_un_espacio_no_se_descifra_con_la_entropia_de_otro(tmp_path):
    """109:RF-2 — con la entropía de otro espacio o de otro proveedor, DPAPI no lo abre."""
    nube_cofre = _cofre()
    ruta = nube_cofre.guardar('wA', 'microsoft', 'ana@empresa-a.example', TOKEN, raiz=tmp_path)
    for wid, prov in (('wB', 'microsoft'), ('wA', 'google')):
        with pytest.raises(nube_cofre.CofreIlegible):
            nube_cofre.descifrar(ruta.read_bytes(), nube_cofre.entropia(wid, prov))
    otro = tmp_path / 'secretos' / 'nube' / 'wB'
    otro.mkdir(parents=True)
    shutil.copy2(ruta, otro / ruta.name)
    assert nube_cofre.leer('wB', 'microsoft', raiz=tmp_path) is None


def test_una_cuenta_nueva_retira_la_anterior_del_mismo_espacio(tmp_path):
    """109:RF-2 — una credencial por espacio y proveedor: conectar otra cuenta retira la de antes."""
    nube_cofre = _cofre()
    primera = nube_cofre.guardar('w1', 'google', 'a@x.example', TOKEN, raiz=tmp_path)
    segunda = nube_cofre.guardar('w1', 'google', 'b@x.example', TOKEN + 'b', raiz=tmp_path)
    assert not primera.exists() and segunda.exists()
    assert nube_cofre.leer('w1', 'google', raiz=tmp_path).cuenta == 'b@x.example'


def test_borrar_solo_toca_su_espacio_y_proveedor(tmp_path):
    """109:RF-2, RF-14 — desconectar una cuenta no toca la del otro espacio."""
    nube_cofre = _cofre()
    nube_cofre.guardar('w1', 'google', 'a@x.example', TOKEN, raiz=tmp_path)
    nube_cofre.guardar('w2', 'google', 'b@y.example', TOKEN + 'b', raiz=tmp_path)
    assert nube_cofre.borrar('w1', 'google', raiz=tmp_path) is True
    assert nube_cofre.leer('w1', 'google', raiz=tmp_path) is None
    assert nube_cofre.leer('w2', 'google', raiz=tmp_path).cuenta == 'b@y.example'
    assert nube_cofre.borrar('w1', 'google', raiz=tmp_path) is False


@pytest.mark.parametrize('wid', ['../fuera', 'a/b', '', 'C:'])
def test_un_espacio_con_ruta_rara_se_rechaza(tmp_path, wid):
    """109:RF-2 — el identificador del espacio no puede sacar el cofre de su carpeta."""
    nube_cofre = _cofre()
    with pytest.raises(ValueError):
        nube_cofre.guardar(wid, 'google', 'a@x.example', TOKEN, raiz=tmp_path)


def test_la_copia_de_datos_no_lleva_los_secretos():
    """109:RF-2 — ninguna raíz de copia_datos.raices_de_datos contiene secretos/ (la copia viaja a Drive)."""
    from convertersmartgrid.presentacion.web.copia_datos import raices_de_datos

    nube_cofre = _cofre()
    cofre = nube_cofre.ruta_cofre().resolve()
    assert cofre.name == 'secretos'
    for nombre, raiz in raices_de_datos().items():
        raiz = raiz.resolve()
        assert not cofre.is_relative_to(raiz), f'la raíz «{nombre}» ({raiz}) contiene el cofre'
