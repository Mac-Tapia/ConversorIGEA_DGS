"""Spec 110 sobre la 109: el token sale de la cuenta conectada del espacio y el permiso de lectura, de su proveedor.

Dos niveles: un doble de ``Cuentas`` con la forma de cada tarjeta de la 109 (la de R4, sin ``permisos`` ni
``proveedor``, y la completa), y la ``Cuentas`` real de la 109 conectada contra su nube simulada. Ninguna prueba abre
la red ni inicia un OAuth real.
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json

import pytest

from correo_simulado import sin_red  # noqa: F401
from nube_simulada import NubeSimulada, sin_sockets  # noqa: F401

from convertersmartgrid.adaptadores.nube.oauth import PERMISOS
from convertersmartgrid.adaptadores.nube.proveedor import PermisoCaducado, SinAcceso
from convertersmartgrid.correo import CuentaNoConectada

MODULO = 'convertersmartgrid.correo.de_la_109'


@pytest.fixture(autouse=True)
def _sin_red(sin_red, sin_sockets):  # noqa: F811
    yield


def _m():
    """El adaptador; una aserción, y no un ImportError, si todavía no existe (rojo por caso)."""
    assert importlib.util.find_spec(MODULO) is not None, f'falta {MODULO}'
    return importlib.import_module(MODULO)


class Proveedor:
    def __init__(self, falla=None):
        self.falla, self.llamadas = falla, []

    def conceder_lectura(self, item_id, destinatarios):
        self.llamadas.append((item_id, tuple(destinatarios)))
        if self.falla:
            raise self.falla
        return [{'destinatario': d, 'id_remoto': f'p{i}', 'rol': 'reader'} for i, d in enumerate(destinatarios)]


class CuentasR4:
    """La forma de ``Cuentas`` de la 109 en R4: ``cuenta`` y ``acceso``; ni ``permisos`` ni ``proveedor``."""

    def __init__(self, cuenta='operador@empresa-a.test', caducado=False):
        self._cuenta, self.caducado, self.pedidos = cuenta, caducado, []

    def cliente(self, proveedor):
        return object()  # registrado en este equipo

    def cuenta(self, wid, proveedor):
        return self._cuenta

    def acceso(self, wid, proveedor, renovar=False):
        self.pedidos.append((wid, proveedor))
        if self.caducado:
            raise PermisoCaducado('revocado')
        return 'tok-109'


class CuentasCompleta(CuentasR4):
    """Con ``permisos`` (109-R9) y ``proveedor`` (109-R5)."""

    def __init__(self, cuenta='operador@empresa-a.test', permisos='openid email https://www.googleapis.com/auth/gmail.send',
                 caducado=False, proveedor=None):
        super().__init__(cuenta, caducado)
        self._permisos, self._proveedor = permisos, proveedor or Proveedor()

    def permisos(self, wid, proveedor):
        if self.caducado:
            raise PermisoCaducado('revocado')
        return self._permisos

    def proveedor(self, wid, proveedor):
        return self._proveedor


def test_la_interfaz_de_la_109_es_la_que_usa_la_110():
    """110:RF-2 — contrato con la 109-R4: ``Cuentas.cuenta(wid, p)``, ``Cuentas.acceso(wid, p, renovar=False)`` y
    ``iniciar(..., alcance=)``; si la 109 cambia una firma, esta prueba lo dice antes que un envío."""
    from convertersmartgrid.adaptadores.nube.cuentas import Cuentas

    _m()
    assert list(inspect.signature(Cuentas.cuenta).parameters) == ['self', 'wid', 'proveedor']
    assert list(inspect.signature(Cuentas.cliente).parameters) == ['self', 'proveedor']
    acceso = inspect.signature(Cuentas.acceso).parameters
    assert list(acceso) == ['self', 'wid', 'proveedor', 'renovar'] and acceso['renovar'].default is False
    assert 'alcance' in inspect.signature(Cuentas.iniciar).parameters


def test_el_permiso_de_enviar_es_el_de_la_109():
    """110:RF-2 — el alcance «enviar» de la 109: gmail.send y Mail.Send, sin leer el buzón ni los ficheros."""
    assert _m().PERMISO_ENVIAR == {'google': 'https://www.googleapis.com/auth/gmail.send', 'microsoft': 'Mail.Send'}
    for p in ('google', 'microsoft'):
        assert not any(x in ' '.join(PERMISOS[p]['enviar']) for x in ('readonly', 'modify', 'Read', 'Files.', 'drive'))


@pytest.mark.parametrize('cuentas', [CuentasR4(), CuentasCompleta()], ids=['r4', 'completa'])
def test_token_de_la_cuenta_conectada(cuentas):
    """110:RF-2 — el token es el de la cuenta del espacio, sin distinguir mayúsculas en la dirección."""
    assert _m().CredencialesDeLa109(cuentas, 'w').token('google', 'Operador@Empresa-A.test', 'enviar') == 'tok-109'
    assert cuentas.pedidos == [('w', 'google')]


def test_con_permisos_de_la_109_microsoft_con_mail_send():
    """110:RF-2 — con ``Cuentas.permisos``, Microsoft vale con ``Mail.Send``."""
    ms = CuentasCompleta(permisos='openid email offline_access Mail.Send')
    assert _m().CredencialesDeLa109(ms, 'w').token('microsoft', 'operador@empresa-a.test', 'x') == 'tok-109'


@pytest.mark.parametrize('cuentas', [CuentasR4(cuenta=None), CuentasR4(cuenta='otra@empresa-a.test'), CuentasR4(caducado=True),
                                     CuentasCompleta(permisos='openid email https://www.googleapis.com/auth/drive.file'),
                                     CuentasCompleta(caducado=True)],
                         ids=['sin_cuenta', 'otra_cuenta', 'revocada_r4', 'sin_permiso', 'revocada'])
def test_sin_cuenta_otra_cuenta_sin_permiso_o_revocada(cuentas):
    """110:RF-2, RF-9 — en cualquiera de esos casos, «conecte o vuelva a conectar la cuenta» y ningún token."""
    with pytest.raises(CuentaNoConectada):
        _m().CredencialesDeLa109(cuentas, 'w').token('google', 'operador@empresa-a.test', 'x')


def test_un_proveedor_que_no_es_de_correo_no_da_token():
    """110:RF-2 — solo Google y Microsoft."""
    with pytest.raises(CuentaNoConectada):
        _m().CredencialesDeLa109(CuentasR4(), 'w').token('smtp', 'operador@empresa-a.test', 'x')


def test_conceder_lectura_a_esos_destinatarios():
    """110:RF-10 — el permiso de la 109 a los destinatarios exactos, con su recibo."""
    prov = Proveedor()
    r = _m().CompartidorDeLa109(CuentasCompleta(proveedor=prov), 'w').conceder_lectura('google:abc', ['a@x.test', 'b@x.test'])
    assert r == {'estado': 'concedido', 'motivo': '', 'id': 'p0,p1'}
    assert prov.llamadas == [('abc', ('a@x.test', 'b@x.test'))]


@pytest.mark.parametrize('expediente,falla', [('abc', None), ('smtp:abc', None), ('google:abc', SinAcceso('no'))],
                         ids=['sin_proveedor', 'proveedor_ajeno', 'error_de_la_109'])
def test_conceder_lectura_que_no_queda_concedida(expediente, falla):
    """110:RF-10 — sin proveedor en el expediente o con un error de la 109: rechazado, y el correo no sale."""
    r = _m().CompartidorDeLa109(CuentasCompleta(proveedor=Proveedor(falla)), 'w').conceder_lectura(expediente, ['a@x.test'])
    assert r['estado'] == 'rechazado' and r['id'] is None


def test_con_la_109_de_r4_un_enlace_se_rechaza_antes_del_correo():
    """110:RF-10 — la 109-R4 aún no comparte (``Cuentas.proveedor`` llega con su T6): el permiso queda rechazado y
    se dice por qué; ``envios.enviar`` no manda el correo sin permiso concedido."""
    m = _m()
    r = m.CompartidorDeLa109(CuentasR4(), 'w').conceder_lectura('google:abc', ['a@x.test'])
    assert r == {'estado': 'rechazado', 'motivo': m.SIN_COMPARTIR, 'id': None}


def test_sin_config_nube_dice_que_configure_y_no_da_token(tmp_path, monkeypatch):
    """110:RF-2 — la ``Cuentas`` real de la 109 sin ``config/nube.json`` (nada registrado en este equipo): «Sin cuenta
    conectada: configure config/nube.json», sin abrir la red ni leer el cofre."""
    from convertersmartgrid.adaptadores.nube.cuentas import Cuentas

    m = _m()
    monkeypatch.setenv('CSG_SALIDA_NUBE', '1')
    cuentas = Cuentas(config=tmp_path / 'config' / 'nube.json', cofre=tmp_path / 'cofre', adaptador=NubeSimulada())
    with pytest.raises(CuentaNoConectada, match='Sin cuenta conectada: configure config/nube.json'):
        m.CredencialesDeLa109(cuentas, 'w1').token('google', 'operador@empresa-a.test', 'enviar')
    assert not (tmp_path / 'cofre').exists()


def test_con_la_cuentas_real_de_la_109_el_token_es_el_de_su_nube(tmp_path, monkeypatch):
    """110:RF-2 — la ``Cuentas`` real de la 109, conectada con «enviar» contra su nube simulada: el token que da la
    110 es uno de los que emitió la nube, y otro espacio no tiene cuenta."""
    from convertersmartgrid.adaptadores.nube.cuentas import Cuentas

    m = _m()
    monkeypatch.setenv('CSG_SALIDA_NUBE', '1')  # la salida de la nube encendida para esta prueba (contra el simulado)
    config = tmp_path / 'config' / 'nube.json'
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({'google': {'id_cliente': 'cliente-prueba.apps.googleusercontent.com',
                                             'secreto': 'GOCSPX-solo-de-prueba',
                                             'uri_retorno': 'http://127.0.0.1:8765/nube/retorno'}}), encoding='utf-8')
    sim = NubeSimulada()
    cuentas = Cuentas(config=config, cofre=tmp_path / 'cofre', adaptador=sim)
    url = cuentas.iniciar('w1', 'google', alcance='enviar')
    assert 'gmail.send' in url and 'drive' not in url
    vuelta = sim.autorizar(url, cuenta='operador@empresa-a.test')
    cuentas.completar(vuelta['state'], vuelta['code'])
    token = m.CredencialesDeLa109(cuentas, 'w1').token('google', 'operador@empresa-a.test', 'enviar')
    assert token in sim.acceso
    with pytest.raises(CuentaNoConectada):
        m.CredencialesDeLa109(cuentas, 'w2').token('google', 'operador@empresa-a.test', 'enviar')
