"""El cliente OAuth de cada proveedor y la conexión de la cuenta (spec 109, T3 y T5).

T3 (``-k config``): el cliente sale de ``config/nube.json``, fuera del repositorio (109:RF-18); sin él, la web dice
«Sin cuenta conectada: configure config/nube.json», que falta registrar la aplicación, y no ofrece conectar (109:RF-19).
Todo con el proveedor simulado y sin sockets. Los módulos de la nube se piden con ``_mod``: si aún no existen, la prueba
cae por aserción y no por ``ModuleNotFoundError``.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from nube_simulada import NubeSimulada, sin_sockets  # noqa: F401

pytest.importorskip('fastapi')
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.usefixtures('sin_sockets')
RAIZ = Path(__file__).resolve().parents[1]
OAUTH = 'convertersmartgrid.adaptadores.nube.oauth'
CUENTAS = 'convertersmartgrid.adaptadores.nube.cuentas'
NUBE_API = 'convertersmartgrid.presentacion.web.nube_api'

CONFIG_COMPLETA = {
    'google': {'id_cliente': 'cliente-prueba.apps.googleusercontent.com', 'secreto': 'GOCSPX-solo-de-prueba',
               'uri_retorno': 'http://127.0.0.1:8765/nube/retorno'},
    'microsoft': {'id_cliente': '00000000-0000-0000-0000-000000000109', 'inquilino': 'common',
                  'uri_retorno': 'http://localhost:8765/nube/retorno'},
}


def _mod(ruta: str):
    """El módulo ``ruta``, con una aserción que dice cuál falta (109, T3 a T5)."""
    partes = ruta.split('.')
    for i in range(2, len(partes) + 1):
        assert importlib.util.find_spec('.'.join(partes[:i])) is not None, f'falta el módulo {".".join(partes[:i])}'
    return importlib.import_module(ruta)


def _config(tmp_path: Path, datos) -> Path:
    ruta = tmp_path / 'config' / 'nube.json'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding='utf-8')
    return ruta


def _app(tmp_path: Path, config: Path, sim: NubeSimulada | None = None, **kw):
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    Cuentas = _mod(CUENTAS).Cuentas
    registrar_rutas_nube = _mod(NUBE_API).registrar_rutas_nube
    store = WorkspaceStore(tmp_path / 'web')
    cuentas = Cuentas(config=config, cofre=tmp_path / 'cofre', adaptador=sim or NubeSimulada())
    app = FastAPI()

    def ws_or_404(wid):
        from fastapi import HTTPException

        ws = store.get(wid)
        if ws is None:
            raise HTTPException(404, 'Espacio de trabajo no encontrado.')
        return ws

    registrar_rutas_nube(app, ws_or_404=ws_or_404, submit=kw.get('submit'), asignar_entrada=None,
                         validar_entrada=None, reemplazar_libros=None, cuentas=cuentas)
    return TestClient(app), store, cuentas


# --------------------------------------------------------------------------- T3: config
def test_config_sin_fichero_dice_que_falta_registrar_y_no_ofrece_conectar(tmp_path):
    """109:RF-19 — sin config/nube.json: «Sin cuenta conectada…», conectar se rechaza y lo local sigue."""
    cliente, store, _ = _app(tmp_path, tmp_path / 'config' / 'nube.json')
    r = cliente.get('/api/nube/proveedores')
    assert r.status_code == 200
    filas = {p['nombre']: p for p in r.json()['proveedores']}
    assert set(filas) == {'google', 'microsoft'}
    for fila in filas.values():
        assert fila['registrado'] is False and fila['se_puede_conectar'] is False
        assert fila['motivo'].startswith('Sin cuenta conectada: configure config/nube.json'), fila['motivo']
        assert 'registrar la aplicación' in fila['motivo']
    ws = store.create()
    r = cliente.post(f'/api/workspaces/{ws.id}/nube/google/conectar', json={})
    assert r.status_code == 409 and 'registrar la aplicación' in r.json()['detail']
    assert store.get(ws.id) is not None


def test_config_de_un_solo_proveedor(tmp_path):
    """109:RF-18, RF-19 — Google registrado y Microsoft no: solo Google se ofrece."""
    ruta = _config(tmp_path, {'google': CONFIG_COMPLETA['google']})
    filas = {p['nombre']: p for p in _app(tmp_path, ruta)[0].get('/api/nube/proveedores').json()['proveedores']}
    assert filas['google']['registrado'] is True and filas['google']['se_puede_conectar'] is True
    assert filas['microsoft']['registrado'] is False and 'OneDrive' in filas['microsoft']['motivo']


def test_config_rota_o_con_retorno_ajeno_no_se_ofrece(tmp_path):
    """109:RF-18, RF-19 — un fichero ilegible, sin identificador o con un retorno que no es de esta máquina."""
    leer_clientes = _mod(OAUTH).leer_clientes
    assert leer_clientes(_config(tmp_path, '{roto')).errores
    malo = {'google': {**CONFIG_COMPLETA['google'], 'uri_retorno': 'https://ajeno.example.net/nube/retorno'},
            'microsoft': {**CONFIG_COMPLETA['microsoft'], 'id_cliente': ''}}
    leidos = leer_clientes(_config(tmp_path, malo))
    assert leidos.clientes == {}
    assert 'esta máquina' in leidos.errores['google'] and 'identificador' in leidos.errores['microsoft']


def test_config_rota_no_tumba_la_web(tmp_path):
    """109:RF-19 — con un config/nube.json ilegible, la web sigue respondiendo y dice por qué no ofrece conectar."""
    cliente, _store, _ = _app(tmp_path, _config(tmp_path, '{roto'))
    r = cliente.get('/api/nube/proveedores')
    assert r.status_code == 200
    for fila in r.json()['proveedores']:
        assert fila['se_puede_conectar'] is False and 'nube.json' in fila['motivo']


def test_config_el_secreto_no_sale_en_la_respuesta(tmp_path):
    """109:RF-18 — el secreto del cliente, si lo hay, nunca vuelve en una respuesta de la web."""
    cliente, _, _ = _app(tmp_path, _config(tmp_path, CONFIG_COMPLETA))
    texto = cliente.get('/api/nube/proveedores').text
    assert 'GOCSPX' not in texto and CONFIG_COMPLETA['google']['id_cliente'] not in texto


def test_config_local_ignorada_y_ejemplo_versionado():
    """109:RF-18 — config/nube.json y secretos/ quedan fuera del repositorio; el ejemplo sí entra, sin datos reales."""
    leer_clientes = _mod(OAUTH).leer_clientes
    for ruta in ('config/nube.json', 'secretos/nube/w1/google-x.dpapi'):
        r = subprocess.run(['git', 'check-ignore', '-q', '--no-index', ruta], cwd=RAIZ)
        assert r.returncode == 0, f'{ruta} no está en .gitignore'
    ejemplo = RAIZ / 'config' / 'nube.example.json'
    assert ejemplo.is_file(), 'falta config/nube.example.json'
    assert subprocess.run(['git', 'check-ignore', '-q', '--no-index', 'config/nube.example.json'],
                          cwd=RAIZ).returncode == 1
    datos = json.loads(ejemplo.read_text(encoding='utf-8'))
    assert set(datos) >= {'google', 'microsoft'}
    assert leer_clientes(ejemplo).clientes == {}, 'el ejemplo no puede funcionar tal cual'


def test_config_el_instructivo_explica_el_modo_de_prueba():
    """109:RF-18 — el registro de prueba: Google en «Testing» con usuarios de prueba y Azure con cuentas personales."""
    texto = (RAIZ / 'docs' / 'NUBE_REGISTRO_OAUTH.md')
    assert texto.is_file(), 'falta docs/NUBE_REGISTRO_OAUTH.md'
    texto = texto.read_text(encoding='utf-8')
    for pieza in ('Testing', '100 usuarios de prueba', 'cuentas personales', 'config\\nube.json', 'drive.file',
                  'Files.Read', 'revocar'):
        assert pieza in texto, pieza


# --------------------------------------------------------------------------- T5: OAuth con PKCE
def _q(url: str) -> dict:
    from urllib.parse import parse_qs, urlsplit

    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _conectar(cliente, wid: str, proveedor: str, cuerpo: dict | None = None) -> str:
    r = cliente.post(f'/api/workspaces/{wid}/nube/{proveedor}/conectar', json=cuerpo or {})
    assert r.status_code == 200, r.text
    return r.json()['url']


def _conectado(tmp_path, proveedor='google', cuenta='ana@ejemplo.org'):
    sim = NubeSimulada()
    cliente, store, cuentas = _app(tmp_path, _config(tmp_path, CONFIG_COMPLETA), sim)
    ws = store.create()
    vuelta = sim.autorizar(_conectar(cliente, ws.id, proveedor), cuenta)
    r = cliente.get('/nube/retorno', params=vuelta, follow_redirects=False)
    assert r.status_code == 303 and 'nube=conectada' in r.headers['location'], r.text
    return sim, cliente, store, cuentas, ws, vuelta


def _cofre():
    return _mod('convertersmartgrid.adaptadores.nube_cofre')


def test_la_url_pide_solo_los_permisos_de_la_tarea(tmp_path):
    """109:RF-1 — drive.file en Google; Files.Read al conectar y Files.ReadWrite solo al publicar en Microsoft."""
    cliente, store, _ = _app(tmp_path, _config(tmp_path, CONFIG_COMPLETA))
    ws = store.create()
    g = _q(_conectar(cliente, ws.id, 'google'))
    assert g['scope'].split() == ['openid', 'email', 'https://www.googleapis.com/auth/drive.file']
    assert g['code_challenge_method'] == 'S256' and len(g['code_challenge']) >= 43 and g['state']
    assert g['redirect_uri'] == CONFIG_COMPLETA['google']['uri_retorno']
    m = _q(_conectar(cliente, ws.id, 'microsoft'))
    assert 'Files.Read' in m['scope'].split() and 'Files.ReadWrite' not in m['scope']
    assert 'offline_access' in m['scope'].split()
    mp = _q(_conectar(cliente, ws.id, 'microsoft', {'publicar': True}))
    assert 'Files.ReadWrite' in mp['scope'].split()
    for q in (g, m, mp):
        assert not any(k in q for k in ('password', 'contrasena', 'contraseña'))


def test_conectar_guarda_solo_el_refresco_en_el_cofre_y_nada_en_la_respuesta(tmp_path):
    """109:RF-1, RF-2 — la vuelta canjea el código con PKCE; el token no sale en ninguna respuesta."""
    sim, cliente, _store, _cuentas, ws, _ = _conectado(tmp_path)
    cred = _cofre().leer(ws.id, 'google', raiz=tmp_path / 'cofre')
    assert cred is not None and cred.refresco in sim.refresco and cred.cuenta == 'ana@ejemplo.org'
    estado = cliente.get(f'/api/workspaces/{ws.id}/nube/cuentas')
    assert estado.status_code == 200, estado.text
    fila = next(c for c in estado.json()['cuentas'] if c['nombre'] == 'google')
    assert fila['conectada'] is True and fila['cuenta'] == 'ana@ejemplo.org'
    for token in [*sim.acceso, *sim.refresco]:
        assert token not in estado.text
    assert not any('password' in k.lower() or 'contrase' in k.lower() for k in fila)


@pytest.mark.parametrize('caso', ['repetido', 'caducado', 'otro_espacio', 'inventado'])
def test_state_repetido_caducado_o_ajeno_se_rechaza(tmp_path, caso):
    """109:RF-1 — un state se usa una vez, caduca a los 10 min y es del espacio y el proveedor que lo pidieron."""
    if caso == 'repetido':
        _sim, cliente, _store, _cuentas, ws, vuelta = _conectado(tmp_path)
        _cofre().borrar(ws.id, 'google', raiz=tmp_path / 'cofre')
        r = cliente.get('/nube/retorno', params=vuelta, follow_redirects=False)
        assert r.status_code == 303 and 'nube=error' in r.headers['location']
        assert _cofre().leer(ws.id, 'google', raiz=tmp_path / 'cofre') is None
        return
    oauth = _mod(OAUTH)
    assert hasattr(oauth, 'Estados') and hasattr(oauth, 'EstadoInvalido'), 'faltan Estados y EstadoInvalido (T5)'
    ahora = [0.0]
    estados = oauth.Estados(reloj=lambda: ahora[0])
    state, _desafio = estados.emitir('wA', 'google', 'leer')
    with pytest.raises(oauth.EstadoInvalido):
        if caso == 'caducado':
            ahora[0] = 601.0
            estados.consumir(state)
        elif caso == 'otro_espacio':
            estados.consumir(state, wid='wB')
        else:
            estados.consumir('inventado-' + state)


def test_desconectar_revoca_y_conserva_copias_y_recibos(tmp_path):
    """109:RF-14 — se revoca en Google, se borra la credencial y las copias y los recibos siguen."""
    sim, cliente, _store, _cuentas, ws, _ = _conectado(tmp_path)
    refresco = _cofre().leer(ws.id, 'google', raiz=tmp_path / 'cofre').refresco
    copia = ws.root / 'nube' / 'copias' / ('a' * 64) / 'RED.txt'
    recibo = ws.root / 'nube' / 'recibos' / 'publicacion-x.json'
    for f in (copia, recibo):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('se conserva', encoding='utf-8')
    r = cliente.delete(f'/api/workspaces/{ws.id}/nube/google')
    assert r.status_code == 200 and r.json()['revocado'] is True
    assert refresco in sim.revocados
    assert _cofre().leer(ws.id, 'google', raiz=tmp_path / 'cofre') is None
    assert copia.read_text(encoding='utf-8') == recibo.read_text(encoding='utf-8') == 'se conserva'


def test_desconectar_microsoft_dice_como_retirar_el_consentimiento(tmp_path):
    """109:RF-14 — Microsoft no tiene revocación estándar: se borra la credencial y se dice dónde retirarlo."""
    _sim, cliente, _store, _cuentas, ws, _ = _conectado(tmp_path, 'microsoft')
    r = cliente.delete(f'/api/workspaces/{ws.id}/nube/microsoft').json()
    assert r['revocado'] is False and 'cuenta de Microsoft' in r['aviso']
    assert _cofre().leer(ws.id, 'microsoft', raiz=tmp_path / 'cofre') is None


def test_un_verificador_que_no_es_el_del_desafio_no_conecta(tmp_path):
    """109:RF-1 — PKCE: el código solo se canjea con el verificador de su desafío."""
    oauth = _mod(OAUTH)
    for nombre in ('Estados', 'intercambiar', 'transporte_oauth', 'url_autorizacion'):
        assert hasattr(oauth, nombre), f'falta oauth.{nombre} (T5)'
    PermisoCaducado = _mod('convertersmartgrid.adaptadores.nube.proveedor').PermisoCaducado
    sim = NubeSimulada()
    cliente_oauth = oauth.leer_clientes(_config(tmp_path, CONFIG_COMPLETA)).clientes['google']
    state, desafio = oauth.Estados().emitir('w1', 'google', 'leer')
    vuelta = sim.autorizar(oauth.url_autorizacion(cliente_oauth, state, desafio, 'leer'))
    with pytest.raises(PermisoCaducado):
        oauth.intercambiar(cliente_oauth, oauth.transporte_oauth('google', adaptador=sim), vuelta['code'],
                           'otro-verificador')


def test_conectar_y_desconectar_solo_desde_el_navegador(tmp_path):
    """109:RF-15 — con el token de un programa (el asistente, una herramienta) ni se conecta ni se desconecta."""
    _sim, cliente, _store, _cuentas, ws, _ = _conectado(tmp_path)
    for metodo, ruta in (('post', f'/api/workspaces/{ws.id}/nube/google/conectar'),
                         ('delete', f'/api/workspaces/{ws.id}/nube/google')):
        for cabecera in ({'X-CSG-Token': 'tok-prog'}, {'Authorization': 'Bearer x'}):
            extra = {'json': {}} if metodo == 'post' else {}
            r = getattr(cliente, metodo)(ruta, headers=cabecera, **extra)
            assert r.status_code == 403, (metodo, cabecera, r.text)
    assert _cofre().leer(ws.id, 'google', raiz=tmp_path / 'cofre') is not None, 'un programa desconectó la cuenta'


def test_permiso_de_enviar_correo_con_el_alcance_minimo():
    """109:RF-1 — para la 110: solo enviar (gmail.send, Mail.Send), sin leer el buzón ni los ficheros."""
    oauth = _mod(OAUTH)
    assert hasattr(oauth, 'PERMISOS'), 'falta oauth.PERMISOS (T5)'
    assert oauth.PERMISOS['google']['enviar'] == ('openid', 'email', 'https://www.googleapis.com/auth/gmail.send')
    assert oauth.PERMISOS['microsoft']['enviar'] == ('openid', 'email', 'offline_access', 'Mail.Send')


def test_conectar_para_enviar_y_el_token_de_acceso_se_renueva(tmp_path):
    """109:RF-1, RF-2 — conectar con «enviar» pide solo eso; Cuentas.acceso da el token en memoria y lo renueva."""
    sim = NubeSimulada()
    cliente, store, cuentas = _app(tmp_path, _config(tmp_path, CONFIG_COMPLETA), sim)
    assert hasattr(cuentas, 'acceso'), 'falta Cuentas.acceso (T5)'
    PermisoCaducado = _mod('convertersmartgrid.adaptadores.nube.proveedor').PermisoCaducado
    ws = store.create()
    url = _conectar(cliente, ws.id, 'microsoft', {'alcance': 'enviar'})
    alcance = _q(url)['scope'].split()
    assert 'Mail.Send' in alcance and not any(a.startswith('Files.') for a in alcance)
    cliente.get('/nube/retorno', params=sim.autorizar(url), follow_redirects=False)
    primero = cuentas.acceso(ws.id, 'microsoft')
    assert primero in sim.acceso
    assert cuentas.acceso(ws.id, 'microsoft') == primero
    renovado = cuentas.acceso(ws.id, 'microsoft', renovar=True)
    assert renovado != primero and renovado in sim.acceso
    with pytest.raises(PermisoCaducado):
        cuentas.acceso(store.create().id, 'microsoft')
