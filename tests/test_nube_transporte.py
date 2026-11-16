"""El transporte de la nube: sin redirecciones, sin proxy del entorno, con lista de hosts, tope y Retry-After.

Spec 109, T1 (109:RF-6, RF-13, RF-16). Todo contra ``tests/nube_simulada.py``; el guardián hace fallar cualquier socket
real. Los módulos de la nube se importan con ``_nube``: si aún no existen, la prueba cae por aserción y no por
``ModuleNotFoundError`` (un rojo así prueba el comportamiento, no la falta de un fichero).
"""
from __future__ import annotations

import importlib
import importlib.util
import io
import random
import socket

import pytest

from nube_simulada import GOOGLE_API, GRAPH, NubeSimulada, quickxor, sin_sockets  # noqa: F401

pytestmark = pytest.mark.usefixtures('sin_sockets')
SEMILLA = 109


def _nube(modulo: str):
    """``convertersmartgrid.adaptadores.nube.<modulo>``, con una aserción que dice cuál falta."""
    ruta = 'convertersmartgrid.adaptadores'
    for parte in ('nube', modulo):
        ruta += '.' + parte
        assert importlib.util.find_spec(ruta) is not None, f'falta el módulo {ruta} (109, T1)'
    return importlib.import_module(ruta)


def _hosts():
    http = _nube('http')
    return http.Hosts(frozenset({GOOGLE_API, GRAPH}), ('.1drv.com', '.sharepoint.com'))


def _transporte(sim, *, token=None, esperas=None, **kw):
    http = _nube('http')
    token = token or sim.dar_token('google')
    dormir = esperas.append if esperas is not None else (lambda _s: None)
    return http.Transporte(_hosts(), autorizacion=lambda _renovar: token, adaptador=sim, dormir=dormir,
                           permitida=lambda: True, **kw)


def test_el_guardian_falla_ante_un_socket_real():
    """109:RF-16 — la prueba no puede salir a la red: un socket real revienta."""
    for direccion in (('192.0.2.1', 9), ('www.googleapis.com', 443)):     # TEST-NET-1 (RFC 5737) y un proveedor
        with pytest.raises(AssertionError, match='socket real'):
            socket.create_connection(direccion)
        with socket.socket() as s, pytest.raises(AssertionError, match='socket real'):
            s.connect(direccion)


def test_sesion_sin_entorno_ni_redirecciones():
    """109:RF-16 — sin proxy del entorno y sin seguir redirecciones."""
    t = _transporte(NubeSimulada())
    assert t.sesion.trust_env is False and t.sesion.max_redirects == 0


def test_redireccion_a_otro_host_se_rechaza(monkeypatch):
    """109:RF-16 — una redirección a otro host es HostNoPermitido y no se pide."""
    proveedor = _nube('proveedor')
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.ajeno.example:8080')
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'hola')
    sim.fallar(302, contiene=fid, cabeceras={'Location': 'https://malo.example.net/robar'})
    t = _transporte(sim)
    with pytest.raises(proveedor.HostNoPermitido, match='malo.example.net'):
        t.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')
    assert not any('malo.example.net' in u for _m, u in sim.peticiones)


def test_next_link_ajeno_se_rechaza_antes_de_pedirlo():
    """109:RF-16 — un @odata.nextLink a otro host no se sigue."""
    proveedor = _nube('proveedor')
    sim = NubeSimulada()
    sim.next_link_ajeno = True
    carpeta = sim.crear('microsoft', 'Carpeta', carpeta=True)
    for i in range(3):
        sim.crear('microsoft', f'f{i}.txt', b'x', padre=carpeta)
    t = _transporte(sim, token=sim.dar_token('microsoft'))
    pagina = t.json('GET', f'https://{GRAPH}/v1.0/me/drive/items/{carpeta}/children?$top=2')
    siguiente = pagina['@odata.nextLink']
    with pytest.raises(proveedor.HostNoPermitido):
        t.pedir('GET', siguiente)
    assert sum('malo.example.net' in u for _m, u in sim.peticiones) == 0


@pytest.mark.parametrize('url', ['http://www.googleapis.com/drive/v3/files', 'https://googleapis.com.malo.example/x',
                                 'https://evil.sharepoint.com.attacker.example/x', 'https://sharepoint.com/x'])
def test_solo_https_y_hosts_del_proveedor(url):
    """109:RF-16 — ni HTTP plano, ni un host que solo contiene el del proveedor, ni el sufijo pelado."""
    proveedor = _nube('proveedor')
    with pytest.raises(proveedor.HostNoPermitido):
        _transporte(NubeSimulada()).comprobar(url)


def test_sufijo_admite_subdominios_del_proveedor():
    """109:RF-16 — la URL de descarga de OneDrive (``*.files.1drv.com``) y la de SharePoint sí se admiten."""
    t = _transporte(NubeSimulada())
    for url in ('https://abc.files.1drv.com/y', 'https://empresa-my.sharepoint.com/subida/1'):
        assert t.comprobar(url) == url


def test_429_espera_retry_after_con_tope_de_reintentos():
    """109:RF-6 — el 429 espera su Retry-After (con tope) y, agotados los reintentos, dice la causa."""
    proveedor = _nube('proveedor')
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'hola')
    sim.fallar(429, contiene=fid, cabeceras={'Retry-After': '7'}, veces=2)
    esperas: list[float] = []
    t = _transporte(sim, esperas=esperas, espera_max_s=5)
    assert t.json('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')['id'] == fid
    assert esperas == [5, 5]
    sim.fallar(503, contiene=fid, veces=10)
    with pytest.raises(proveedor.Limitado, match='reintentos'):
        t.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')


def test_401_renueva_una_vez_y_luego_permiso_caducado():
    """109:RF-6 — un 401 pide un token nuevo una vez; si vuelve a fallar, PermisoCaducado."""
    http, proveedor = _nube('http'), _nube('proveedor')
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'hola')
    pedidos = []
    buenos = iter([sim.dar_token('google')])

    def autorizacion(renovar):
        pedidos.append(renovar)
        return next(buenos) if renovar else 'caducado'

    t = http.Transporte(_hosts(), autorizacion=autorizacion, adaptador=sim, dormir=lambda _s: None,
                        permitida=lambda: True)
    assert t.json('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')['id'] == fid
    assert pedidos == [False, True]
    t2 = http.Transporte(_hosts(), autorizacion=lambda _r: 'revocado', adaptador=sim, permitida=lambda: True)
    with pytest.raises(proveedor.PermisoCaducado, match='vuelva a conectarla'):
        t2.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')


def test_403_y_404_con_su_causa():
    """109:RF-6 — 403 y 404 se nombran."""
    proveedor = _nube('proveedor')
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'hola')
    t = _transporte(sim)
    sim.fallar(403, contiene=fid)
    with pytest.raises(proveedor.SinAcceso, match='permiso'):
        t.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')
    with pytest.raises(proveedor.NoEncontrado, match='ya no está'):
        t.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/noexiste')


def test_tope_de_bytes_y_corte(monkeypatch):
    """109:RF-6 — una descarga que pasa el tope o se corta no da nada por bueno; el tope inválido no se apaga."""
    http, proveedor = _nube('http'), _nube('proveedor')
    rng = random.Random(SEMILLA)
    datos = bytes(rng.randrange(256) for _ in range(rng.randrange(3000, 9000)))
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.bin', datos)
    t = _transporte(sim)
    url = f'https://{GOOGLE_API}/drive/v3/files/{fid}?alt=media'
    with pytest.raises(proveedor.DemasiadoGrande):
        t.bajar(url, io.BytesIO(), tope=len(datos) - 1)
    sim.cortes[fid] = len(datos) // 3
    with pytest.raises(proveedor.DescargaCortada):
        t.bajar(url, io.BytesIO())
    destino = io.BytesIO()
    assert t.bajar(url, destino) == len(datos) and destino.getvalue() == datos
    monkeypatch.setenv('CSG_NUBE_MAX_BYTES', '-3')
    with pytest.raises(ValueError, match='CSG_NUBE_MAX_BYTES'):
        http.tope_de_bytes()


#: Los errores del contrato, por su nombre: cada uno con su causa en español para el operador.
ERRORES = ('SinConexion', 'SinAcceso', 'NoEncontrado', 'PermisoCaducado', 'Limitado', 'CambioAMitad',
           'DescargaCortada', 'DemasiadoGrande', 'YaExiste', 'HostNoPermitido')


def test_cada_error_dice_su_causa():
    """109:RF-6 — cada error tipado es un ErrorNube con su causa propia; sin mensaje, el mensaje es la causa."""
    proveedor = _nube('proveedor')
    causas = set()
    for nombre in ERRORES:
        assert hasattr(proveedor, nombre), f'falta el error {nombre} en el contrato'
        clase = getattr(proveedor, nombre)
        assert issubclass(clase, proveedor.ErrorNube)
        assert clase.causa and clase.causa != proveedor.ErrorNube.causa, nombre
        assert str(clase()) == clase.causa
        assert clase('detalle', causa='otra').causa == 'otra'
        causas.add(clase.causa)
    assert len(causas) == len(ERRORES), 'dos errores con la misma causa no se distinguen'


def test_el_contrato_pide_lo_que_usan_la_entrada_y_la_salida():
    """109:RF-3, RF-9, RF-10 — el contrato ProveedorNube declara las operaciones que piden la copia y la publicación."""
    proveedor = _nube('proveedor')
    assert hasattr(proveedor, 'ProveedorNube'), 'falta el contrato ProveedorNube'
    for metodo in ('metadatos', 'listar', 'descargar', 'exportar', 'buscar_por_clave', 'subir', 'conceder_lectura',
                   'enlace_publico'):
        assert callable(getattr(proveedor.ProveedorNube, metodo, None)), metodo
    assert proveedor.PROVEEDORES == ('google', 'microsoft')
    item = proveedor.Item('google', 'id1', 'a.txt', 'r1')
    assert proveedor.Pagina((item,)).siguiente is None and item.huellas == {} and item.carpeta is False


def test_quickxor_por_bloques_igual_que_byte_a_byte(tmp_path, monkeypatch):
    """109:RF-13 — la huella QuickXorHash local, por bloques, es la misma que byte a byte, cruce de bloque incluido."""
    import hashlib

    proveedor = _nube('proveedor')
    assert hasattr(proveedor, 'huellas_de'), 'falta huellas_de en el contrato'
    rng = random.Random(SEMILLA)
    for tam in (0, 1, 159, 160, 161, rng.randrange(1000, 5000)):
        datos = rng.randbytes(tam)
        ruta = tmp_path / f'f{tam}.bin'
        ruta.write_bytes(datos)
        monkeypatch.setattr(proveedor, '_BLOQUE_QX', 160 * rng.randrange(1, 4) + rng.randrange(0, 2) * 7)
        huellas = proveedor.huellas_de(ruta)
        assert huellas['quickxor'] == quickxor(datos), f'semilla {SEMILLA}, {tam} bytes'
        assert huellas['sha256'] == hashlib.sha256(datos).hexdigest()


# --------------------------------------------------------------------------- T2: la salida «nube»
def _salidas():
    from convertersmartgrid import salidas_red

    assert 'nube' in salidas_red.SALIDAS, 'falta la salida «nube» en salidas_red.SALIDAS (109, T2)'
    return salidas_red


def test_salida_nube_declarada_con_su_variable_y_su_modulo():
    """109:RF-16 — la salida «nube» está en salidas_red con CSG_SALIDA_NUBE y el único módulo que abre la red."""
    salidas_red = _salidas()
    nube = salidas_red.SALIDAS['nube']
    assert nube.variable == 'CSG_SALIDA_NUBE'
    assert nube.modulos == ('src/convertersmartgrid/adaptadores/nube/http.py',)
    # 086:RF-69: solo las teselas se cambian desde la web; ningún RF de la 109 pide cambiar la nube allí.
    assert 'nube' not in salidas_red.CAMBIABLES_DESDE_LA_WEB


def test_ningun_otro_modulo_de_la_nube_abre_la_red():
    """109:RF-16 — en adaptadores/nube/ solo http.py tiene una sesión de requests."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'src' / 'convertersmartgrid'
    con_sesion = sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob('*.py')
                        if 'requests.Session(' in p.read_text(encoding='utf-8', errors='replace')
                        and ('nube' in p.as_posix()))
    assert con_sesion == ['adaptadores/nube/http.py']


def test_con_la_salida_apagada_no_sale_ninguna_peticion(monkeypatch, tmp_path):
    """109:RF-16, RF-17 — apagada, ni una petición llega al proveedor y lo ya descargado sigue intacto."""
    salidas_red = _salidas()
    http = _nube('http')
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'contenido importado')
    monkeypatch.setenv('CSG_SALIDA_NUBE', '1')
    t = http.Transporte(_hosts(), autorizacion=lambda _r: sim.dar_token('google'), adaptador=sim)
    copia = tmp_path / 'copia.txt'
    with copia.open('wb') as fh:
        t.bajar(f'https://{GOOGLE_API}/drive/v3/files/{fid}?alt=media', fh)
    antes = len(sim.peticiones)
    monkeypatch.setenv('CSG_SALIDA_NUBE', '0')
    with pytest.raises(salidas_red.SalidaApagada, match='CSG_SALIDA_NUBE'):
        t.pedir('GET', f'https://{GOOGLE_API}/drive/v3/files/{fid}')
    assert len(sim.peticiones) == antes
    assert copia.read_bytes() == b'contenido importado'


def test_salida_nube_se_ve_en_la_web_y_la_decide_su_variable(tmp_path, monkeypatch):
    """109:RF-16, 086:RF-69 — la web la lista con su estado y su variable, pero no la cambia: 403 y nada guardado."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app

    monkeypatch.delenv('CSG_SALIDA_NUBE', raising=False)
    monkeypatch.setenv('CSG_SALIDAS_RUTA', str(tmp_path / 'salidas.json'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        salidas_red = _salidas()
        antes = salidas_red.salida_permitida('nube')
        r = c.post('/api/salidas/nube', json={'encendida': not antes})
        assert r.status_code == 403 and 'CSG_SALIDA_NUBE' in r.json()['detail'], r.text
        assert salidas_red.salida_permitida('nube') is antes and not (tmp_path / 'salidas.json').exists()
        fila = next(s for s in c.get('/api/salidas').json()['salidas'] if s['nombre'] == 'nube')
        assert fila['cambiable'] is False and fila['variable'] == 'CSG_SALIDA_NUBE'
