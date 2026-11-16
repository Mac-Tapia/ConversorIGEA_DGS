"""Importar de la nube: la copia fija con su huella (T7, ``-k copia``) y su entrada por la vía de una subida (T8).

Spec 109: 109:RF-3 a RF-6. Proveedor simulado, sin sockets; T8 monta el router sobre las funciones de la web real. Los
módulos de la nube se piden con ``_mod``: si aún no existen, la prueba cae por aserción y no por
``ModuleNotFoundError``.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import threading
import zipfile

import pytest

from nube_simulada import NubeSimulada, montar_web_nube, sin_sockets  # noqa: F401
from convertersmartgrid.web.jobs import JobCancelled

pytestmark = pytest.mark.usefixtures('sin_sockets')
SEMILLA = int(os.environ.get('CSG_SCALE_SEED') or random.SystemRandom().randrange(1 << 30))
FICHA = 'copia.json'


def _mod(ruta: str):
    """``convertersmartgrid.<ruta>``, con una aserción que dice cuál falta (109, T7 y T8)."""
    partes = f'convertersmartgrid.{ruta}'.split('.')
    for i in range(2, len(partes) + 1):
        assert importlib.util.find_spec('.'.join(partes[:i])) is not None, f'falta el módulo {".".join(partes[:i])}'
    return importlib.import_module('.'.join(partes))


def importar(*a, **k):
    return _mod('adaptadores.entrada.nube').importar(*a, **k)


def _errores():
    return _mod('adaptadores.nube.proveedor')

class _Ctx:
    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.avances: list[tuple[int, int]] = []

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise JobCancelled()

    def progress(self, i: int, total: int, _etiqueta: str = '') -> None:
        self.avances.append((i, total))
        if len(self.avances) == 2 and getattr(self, 'cancelar_en_el_segundo', False):
            self.cancel.set()


def _proveedor(sim, nombre):
    token = sim.dar_token(nombre)
    g, o = _mod('adaptadores.nube.google_drive'), _mod('adaptadores.nube.onedrive')
    t = _mod('adaptadores.nube.http').Transporte(g.HOSTS if nombre == 'google' else o.HOSTS,
                                                autorizacion=lambda _r: token, adaptador=sim, dormir=lambda _s: None)
    return g.GoogleDrive(t) if nombre == 'google' else o.OneDrive(t)


def _sin_copias(raiz):
    return not raiz.exists() or not [p for p in raiz.iterdir() if (p / FICHA).exists()]


# --------------------------------------------------------------------------- T7: la copia
@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_copia_inmutable_con_su_ficha(tmp_path, nombre):
    """109:RF-3 — la copia va en copias/<sha256>/ con proveedor, id, revisión, formatos, huella y tamaño."""
    import hashlib

    datos = random.Random(SEMILLA).randbytes(4321)
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'RED_2026.txt', datos)
    copia = importar(_proveedor(sim, nombre), fid, tmp_path / 'copias', _Ctx())
    sha = hashlib.sha256(datos).hexdigest()
    assert copia.carpeta == tmp_path / 'copias' / sha and copia.ruta.read_bytes() == datos
    ficha = json.loads((copia.carpeta / FICHA).read_text(encoding='utf-8'))
    assert {k: ficha[k] for k in ('proveedor', 'id', 'sha256', 'tamano', 'nombre')} == {
        'proveedor': nombre, 'id': fid, 'sha256': sha, 'tamano': len(datos), 'nombre': 'RED_2026.txt'}
    assert ficha['revision'] and ficha['formato_exportado'] is None and ficha['formato_origen']


def test_copia_de_hoja_nativa_exportada_anota_los_dos_formatos(tmp_path):
    """109:RF-5 — la hoja nativa de Google se exporta a XLSX; la ficha dice el formato de origen y el exportado."""
    sim = NubeSimulada()
    fid = sim.crear('google', 'Cabecera', nativo=True, exportado=b'PK\x03\x04xlsx')
    copia = importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias')
    assert copia.ruta.name == 'Cabecera.xlsx' and copia.ruta.read_bytes() == b'PK\x03\x04xlsx'
    assert copia.ficha['formato_origen'] == 'application/vnd.google-apps.spreadsheet'
    assert copia.ficha['formato_exportado'].endswith('spreadsheetml.sheet')


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_copia_tras_un_corte_se_reanuda_con_la_misma_revision(tmp_path, nombre):
    """109:RF-6 — un corte se reanuda con Range desde donde iba; la copia sale entera."""
    rng = random.Random(SEMILLA)
    datos = rng.randbytes(rng.randrange(3000, 9000))
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'a.bin', datos)
    sim.cortes[fid] = rng.randrange(1, len(datos) - 1)
    copia = importar(_proveedor(sim, nombre), fid, tmp_path / 'copias')
    assert copia.ruta.read_bytes() == datos, f'semilla {SEMILLA}'


@pytest.mark.parametrize('nombre', ['google', 'microsoft'])
def test_copia_no_queda_si_el_fichero_cambia_a_mitad(tmp_path, nombre):
    """109:RF-6 — la revisión cambió mientras se descargaba: ninguna copia y la causa dicha."""
    sim = NubeSimulada()
    fid = sim.crear(nombre, 'a.txt', b'x' * 5000)
    sim.cambia_a_mitad.add(fid)
    with pytest.raises(_errores().CambioAMitad, match='cambió en la nube'):
        importar(_proveedor(sim, nombre), fid, tmp_path / 'copias')
    assert _sin_copias(tmp_path / 'copias')


def test_copia_no_queda_si_la_huella_no_coincide(tmp_path, monkeypatch):
    """109:RF-6 — el proveedor da una huella distinta de la del contenido recibido: ninguna copia."""
    from convertersmartgrid.adaptadores.nube import google_drive

    sim = NubeSimulada()
    fid = sim.crear('google', 'a.txt', b'contenido')
    original = google_drive.GoogleDrive._item

    def item_con_otra_huella(self, d):
        item = original(self, d)
        return type(item)(**{**item.__dict__, 'huellas': {'sha256': '0' * 64}})

    monkeypatch.setattr(google_drive.GoogleDrive, '_item', item_con_otra_huella)
    with pytest.raises(_errores().CambioAMitad, match='huella'):
        importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias')
    assert _sin_copias(tmp_path / 'copias')


def test_copia_no_queda_si_el_corte_se_repite(tmp_path):
    """109:RF-6 — cortes repetidos: tras los reintentos, ninguna copia y la causa."""
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.bin', b'y' * 6000)

    class Cortes(dict):
        def pop(self, k, d=None):
            return 10 if k == fid else d

    sim.cortes = Cortes()
    with pytest.raises(_errores().DescargaCortada, match='se cortó'):
        importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias', reintentos=2)
    assert _sin_copias(tmp_path / 'copias')


def test_copia_se_cancela_entre_bloques_sin_dejar_nada(tmp_path):
    """109:RF-3, P7 — el trabajo se cancela entre bloques y no deja copia."""
    sim = NubeSimulada()
    fid = sim.crear('google', 'a.bin', b'z' * 8000)
    sim.cortes[fid] = 3000
    ctx = _Ctx()
    ctx.cancelar_en_el_segundo = True
    with pytest.raises(JobCancelled):
        importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias', ctx)
    assert _sin_copias(tmp_path / 'copias')


def test_copia_con_la_misma_huella_no_se_reescribe(tmp_path):
    """109:RF-3, RF-8 — la misma huella es el mismo contenido: la copia existente no se toca."""
    sim = NubeSimulada()
    a = sim.crear('google', 'a.txt', b'igual')
    b = sim.crear('google', 'b.txt', b'igual')
    p = _proveedor(sim, 'google')
    primera = importar(p, a, tmp_path / 'copias')
    antes = (primera.carpeta / FICHA).stat().st_mtime_ns
    segunda = importar(p, b, tmp_path / 'copias')
    assert segunda.carpeta == primera.carpeta and segunda.ficha['id'] == a
    assert (primera.carpeta / FICHA).stat().st_mtime_ns == antes


@pytest.mark.parametrize('remoto', ['../../fuera.txt', 'C:\\Windows\\x.txt', 'CON', 'a/b\\c.txt'])
def test_copia_con_nombre_malicioso_no_sale_de_su_carpeta(tmp_path, remoto):
    """109:RF-3 — el nombre remoto no puede sacar la copia de su carpeta."""
    sim = NubeSimulada()
    fid = sim.crear('google', remoto, b'contenido')
    copia = importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias')
    assert copia.ruta.parent == copia.carpeta and copia.carpeta.parent == tmp_path / 'copias'
    assert copia.ruta.read_bytes() == b'contenido'


def test_copia_la_ficha_se_escribe_con_la_escritura_atomica_unica(tmp_path, monkeypatch):
    """109:RF-3, 001:RF-5 — ``copia.json`` sale de ``write_json_atomic``: un corte nunca deja una ficha a medias."""
    entrada = _mod('adaptadores.entrada.nube')
    escritas = []
    original = entrada.write_json_atomic if hasattr(entrada, 'write_json_atomic') else None
    assert original is not None, 'la entrada de la nube no usa util.write_json_atomic (001:RF-5)'
    monkeypatch.setattr(entrada, 'write_json_atomic', lambda ruta, datos, **k: (escritas.append(ruta.name),
                                                                                 original(ruta, datos, **k)))
    sim = NubeSimulada()
    fid = sim.crear('google', 'RED.txt', b'contenido')
    copia = importar(_proveedor(sim, 'google'), fid, tmp_path / 'copias')
    assert escritas == [FICHA] and json.loads((copia.carpeta / FICHA).read_text(encoding='utf-8'))['id'] == fid




# --------------------------------------------------------------------------- T8: la misma vía que una subida
from synthetic_export import CRS_SINTETICO, ExportSpec, write_export  # noqa: E402


def _importar_web(web, wid, proveedor, ids, **destino):
    r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', json={'proveedor': proveedor, 'ids': ids, **destino})
    assert r.status_code == 202, r.text
    return web.esperar(r.json())


def _subir(web, wid, slot, ruta):
    with ruta.open('rb') as fh:
        return web.real.post(f'/api/workspaces/{wid}/inputs/{slot}', files={'file': (ruta.name, fh)})


def _opciones(web, wid):
    # Sin PUT /options: su respuesta lleva las entradas, y el «origin» «nube» espera el diff de api_contract (f9).
    ws = web.store.get(wid)
    with ws.lock:
        ws.options.update(include_geography=False, source_crs=CRS_SINTETICO)
        ws.save()


def _convertir(web, wid) -> dict[str, bytes]:
    _opciones(web, wid)
    estado = web.esperar(web.real.post(f'/api/workspaces/{wid}/load').json())
    assert estado['status'] == 'done', estado
    estado = web.esperar(web.real.post(f'/api/workspaces/{wid}/convert', json={'all': True}).json(), timeout=120)
    assert estado['status'] == 'done', estado
    nombres = [f['feeder'] for f in web.real.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    assert nombres
    return {n: web.real.get(f'/api/workspaces/{wid}/files/{n}.dgs', params={'download': 1}).content for n in nombres}


@pytest.mark.parametrize('proveedor', ['google', 'microsoft'])
def test_el_mismo_dgs_desde_la_nube_y_desde_la_subida(tmp_path, proveedor):
    """109:RF-4 — convertir desde la copia de la nube da el mismo DGS, byte a byte, que subir el mismo fichero."""
    rng = random.Random(SEMILLA)
    export = write_export(ExportSpec(feeders=rng.randrange(2, 5), seed=SEMILLA), tmp_path / 'export')
    with montar_web_nube(tmp_path) as web:
        subido = web.espacio()
        for slot, ruta in zip(('red', 'loads', 'equipment'), export):
            assert _subir(web, subido, slot, ruta).status_code == 200
        de_la_nube = web.espacio()
        web.conectar(de_la_nube, proveedor)
        for slot, ruta in zip(('red', 'loads', 'equipment'), export):
            fid = web.sim.crear(proveedor, ruta.name, ruta.read_bytes())
            estado = _importar_web(web, de_la_nube, proveedor, [fid], casilla=slot)
            assert estado['status'] == 'done', estado
        ws = web.store.get(de_la_nube)
        slots = ('red', 'loads', 'equipment')
        assert {s: ws.inputs[s]['origin'] for s in slots} == dict.fromkeys(slots, 'nube')
        assert all('/nube/copias/' in ws.inputs[s]['path'].replace('\\', '/') for s in slots)
        assert _convertir(web, subido) == _convertir(web, de_la_nube), f'semilla {SEMILLA}'


def _normalizar(texto, *carpetas):
    texto = str(texto or '')
    for c in carpetas:
        texto = texto.replace(str(c), '<espacio>').replace(str(c).replace('\\', '/'), '<espacio>')
    return texto


def test_vnr_con_rutas_maliciosas_rechazado_igual_que_al_subirlo(tmp_path):
    """109:RF-4 — un VNR comprimido con «../» y rutas absolutas: el mismo rechazo y el mismo mensaje que subido."""
    paquete = tmp_path / 'paquete_vnr.zip'
    with zipfile.ZipFile(paquete, 'w') as z:
        z.writestr('../../fuera.shp', b'x' * 100)
        z.writestr('C:/Windows/absoluto.dbf', b'y' * 100)
    with montar_web_nube(tmp_path) as web:
        subido, de_la_nube = web.espacio(), web.espacio()
        r = _subir(web, subido, 'vnr_package', paquete)
        web.conectar(de_la_nube, 'google')
        fid = web.sim.crear('google', paquete.name, paquete.read_bytes())
        estado = _importar_web(web, de_la_nube, 'google', [fid], casilla='vnr_package')
        if r.status_code != 200:
            assert estado['status'] == 'failed' and r.json()['detail'] in estado['error']
            return
        assert estado['status'] == 'done', estado
        cargas = []
        for wid in (subido, de_la_nube):
            _opciones(web, wid)
            cargas.append(web.esperar(web.real.post(f'/api/workspaces/{wid}/load').json()))
        carpetas = [web.store.get(w).root for w in (subido, de_la_nube)]
        assert cargas[0]['status'] == cargas[1]['status'] != 'done'
        assert _normalizar(cargas[0]['error'], *carpetas) == _normalizar(cargas[1]['error'], *carpetas)
        assert not list(tmp_path.rglob('fuera.shp'))


def test_pdf_normativo_en_un_libro_de_medicion_rechazado_igual(tmp_path):
    """109:RF-4 — un PDF normativo en el libro de clientes: el mismo rechazo que al subirlo, y el hueco intacto."""
    pdf = tmp_path / 'norma_tecnica.pdf'
    pdf.write_bytes(b'%PDF-1.7\n1 0 obj << /Title (Norma tecnica de calidad) >> endobj\n%%EOF\n')
    with montar_web_nube(tmp_path) as web:
        subido, de_la_nube = web.espacio(), web.espacio()
        with pdf.open('rb') as fh:
            r = web.real.post(f'/api/workspaces/{subido}/demanda/clientes', files={'files': (pdf.name, fh)})
        assert r.status_code >= 400
        web.conectar(de_la_nube, 'microsoft')
        fid = web.sim.crear('microsoft', pdf.name, pdf.read_bytes())
        estado = _importar_web(web, de_la_nube, 'microsoft', [fid], libro='clientes')
        assert estado['status'] == 'failed' and r.json()['detail'] in estado['error'], (r.json(), estado)
        for wid in (subido, de_la_nube):
            carpeta = web.store.get(wid).root / 'demanda' / 'clientes'
            assert not carpeta.exists() or not any(carpeta.iterdir())


def test_ninguna_fuente_nueva_se_mezcla_con_la_vigente(tmp_path):
    """109:RF-4 — un VNR de la nube en un espacio con los TXT cambia la fuente igual que subirlo: nada se mezcla."""
    export = write_export(ExportSpec(feeders=2, seed=SEMILLA), tmp_path / 'export')
    paquete = tmp_path / 'vnr.zip'
    with zipfile.ZipFile(paquete, 'w') as z:
        z.writestr('red/tramos.shp', b's' * 64)
    with montar_web_nube(tmp_path) as web:
        estados = {}
        for via in ('subida', 'nube'):
            wid = web.espacio()
            for slot, ruta in zip(('red', 'loads', 'equipment'), export):
                assert _subir(web, wid, slot, ruta).status_code == 200
            _opciones(web, wid)
            assert web.esperar(web.real.post(f'/api/workspaces/{wid}/load').json())['status'] == 'done'
            if via == 'subida':
                assert _subir(web, wid, 'vnr_package', paquete).status_code == 200
            else:
                web.conectar(wid, 'google')
                fid = web.sim.crear('google', paquete.name, paquete.read_bytes())
                assert _importar_web(web, wid, 'google', [fid], casilla='vnr_package')['status'] == 'done'
            ws = web.store.get(wid)
            estados[via] = (ws.options.get('input_mode'), bool(ws.dataset_loaded()) if hasattr(ws, 'dataset_loaded')
                            else None, sorted(ws.inputs))
        assert estados['subida'] == estados['nube'] and estados['nube'][0] == 'vnr'


# --------------------------------------------------------------------------- T8: el contrato de las respuestas
RUTAS_NUBE = (
    ('get', '/api/nube/proveedores'), ('get', '/api/workspaces/{wid}/nube/cuentas'),
    ('post', '/api/workspaces/{wid}/nube/{proveedor}/conectar'), ('delete', '/api/workspaces/{wid}/nube/{proveedor}'),
    ('post', '/api/workspaces/{wid}/nube/importar'),
)


def test_cada_ruta_de_la_nube_declara_la_forma_de_su_respuesta(tmp_path):
    """109:RF-2, RF-4 — el OpenAPI da el esquema de cada respuesta de la nube, para que ``esquema.ts`` la genere."""
    with montar_web_nube(tmp_path) as web:
        esquema = web.nube.get('/openapi.json').json()
    for metodo, ruta in RUTAS_NUBE:
        assert ruta in esquema['paths'], f'falta {ruta} en el OpenAPI'
        respuestas = esquema['paths'][ruta][metodo]['responses']
        codigo = '202' if ruta.endswith('/importar') else '200'
        contenido = respuestas[codigo].get('content', {}).get('application/json', {}).get('schema', {})
        assert '$ref' in contenido, f'{metodo.upper()} {ruta} no declara su modelo de respuesta: {contenido}'
    assert '/nube/retorno' not in esquema['paths']


def test_una_respuesta_de_la_nube_no_puede_llevar_un_token(tmp_path, monkeypatch):
    """109:RF-2 — si las cuentas devolvieran un campo que no está en el contrato (un token), la ruta no lo deja salir."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        original = web.cuentas.estado
        monkeypatch.setattr(web.cuentas, 'estado',
                            lambda w: [{**f, 'token_acceso': 'acc-secreto'} for f in original(w)])
        try:
            r = web.nube.get(f'/api/workspaces/{wid}/nube/cuentas')
        except Exception as exc:  # noqa: BLE001 - TestClient relanza el error de validación del servidor
            r = exc
        assert 'acc-secreto' not in (r.text if hasattr(r, 'text') else ''), 'el token salió en la respuesta'
        assert not hasattr(r, 'status_code') or r.status_code >= 500


@pytest.mark.parametrize('cuerpo', [{'proveedor': 'google', 'ids': ['x']},
                                    {'proveedor': 'google', 'ids': ['x'], 'casilla': 'red', 'libro': 'clientes'},
                                    {'proveedor': 'google', 'ids': ['x', 'y'], 'casilla': 'red'},
                                    {'proveedor': 'google', 'ids': ['x'], 'casilla': 'no_existe'}])
def test_importar_dice_donde_entra_y_rechaza_lo_que_no_cabe(tmp_path, cuerpo):
    """109:RF-4 — sin destino, con dos destinos, dos ficheros en una casilla o una casilla que no existe: no se encola."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', json=cuerpo)
        assert r.status_code in (404, 422), r.text
        assert not (web.store.get(wid).root / 'nube' / 'copias').exists(), 'se encoló una importación sin destino'


def test_importar_solo_desde_el_navegador(tmp_path):
    """109:RF-15 — con el token de un programa (el asistente) importar responde 403 y no encola nada."""
    with montar_web_nube(tmp_path) as web:
        wid = web.espacio()
        web.conectar(wid, 'google')
        fid = web.sim.crear('google', 'RED.txt', b'x')
        r = web.nube.post(f'/api/workspaces/{wid}/nube/importar', headers={'Authorization': 'Bearer programa'},
                          json={'proveedor': 'google', 'ids': [fid], 'casilla': 'red'})
        assert r.status_code == 403, r.text
