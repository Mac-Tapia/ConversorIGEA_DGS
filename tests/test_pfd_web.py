"""Spec 004, T36: importar un ``.pfd`` desde la web (004:RF-118) con su diagnóstico de avisos agrupados (004:RF-117).

El guion es un falso de ``tools/pfd_diagnostico.py`` que escribe un informe con la misma forma; el de verdad se prueba
contra ``fake_pf`` en ``test_pfd_diagnostico.py``. Lo que se prueba aquí es qué manda la web y qué hace con la respuesta.
Nombres y avisos sorteados; ningún nombre de empresa ni de fichero real.
"""
from __future__ import annotations

import json
import random
import string

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from apoyo import esperar_trabajo  # noqa: E402
from apoyo_pf_web import guion_falso  # noqa: E402,F401
from test_estudios_pf_web import client  # noqa: E402,F401

SEMILLA = random.randrange(1 << 30)

PFD_FALSO = r'''
import argparse, hashlib, json, sys
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--pfd'); p.add_argument('--output-json'); p.add_argument('--carpeta')
p.add_argument('--reimportar', action='store_true')
a = p.parse_args()
pfd = Path(a.pfd)
datos = json.loads(pfd.read_bytes().decode('utf-8'))
informe = {'esquema': 'csg-pfd-diagnostico-v1', 'fichero': pfd.name, 'carpeta': a.carpeta,
           'sha256': hashlib.sha256(pfd.read_bytes()).hexdigest(), 'modo': 'reimportado' if a.reimportar else 'importado',
           'argv': sys.argv[1:], 'avisos': datos['avisos_fichero'], 'errores': datos.get('errores', []),
           'proyectos': [{'proyecto': pfd.stem + '_p', 'caso_activo': 'C1', 'casos': [{}] * datos['casos'],
                          'escenarios': [{}] * 2, 'variaciones': [{}] * 3, 'exportacion_reducida': False,
                          'red': {'redes': [{'red': 'R1', 'alimentadores': ['A', 'B']}]},
                          'avisos': datos['avisos_proyecto']}]}
informe['codigo'] = datos.get('codigo', 0)
Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
Path(a.output_json).with_suffix('.txt').write_text('Diagnóstico\n', encoding='utf-8')
sys.exit(informe['codigo'])
'''


def _nombre(rnd, n=6):
    return ''.join(rnd.choice(string.ascii_uppercase + string.digits) for _ in range(n))


@pytest.fixture()
def pfd_falso(guion_falso):
    (guion_falso / 'falso_pfd_diagnostico.py').write_text(PFD_FALSO, encoding='utf-8')
    return guion_falso


def _subir(client, wid, nombre, contenido: dict | bytes, **data):
    cuerpo = contenido if isinstance(contenido, bytes) else json.dumps(contenido).encode('utf-8')
    return client.post(f'/api/workspaces/{wid}/pf/pfd', data=data,
                       files={'file': (nombre, cuerpo, 'application/octet-stream')})


def test_el_pfd_se_sube_al_espacio_y_se_diagnostica_en_la_carpeta_de_su_empresa(client, pfd_falso):
    """004:RF-118, 004:RF-117 — el ``.pfd`` subido queda en el espacio y se importa con ``pfd_diagnostico.py`` en el
    carril de DIgSILENT, en la carpeta de la empresa del espacio; el resultado resume cada proyecto y agrupa los avisos
    iguales con sus veces, sin perder ninguno."""
    from convertersmartgrid.presentacion.web import services

    rnd = random.Random(SEMILLA)
    wid = client.post('/api/workspaces').json()['id']
    repetido, unico = f'Aviso {_nombre(rnd)}.', f'Aviso {_nombre(rnd)}.'
    veces = rnd.randint(2, 6)
    casos = rnd.randint(1, 9)
    nombre = f'{_nombre(rnd)}.pfd'
    r = _subir(client, wid, nombre, {'casos': casos, 'avisos_fichero': [unico],
                                     'avisos_proyecto': [repetido] * veces + [unico]})
    assert r.status_code == 202, r.text
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done' and estado['lane'] == 'powerfactory', (SEMILLA, estado)
    ws = client.app.state.store.get(wid)
    assert (ws.root / services.CARPETA_PFD / nombre).is_file(), SEMILLA
    resumen = estado['result']['resumen']
    assert resumen['fichero'] == nombre and resumen['carpeta'] == services.destino_carpeta(ws).carpeta, SEMILLA
    assert resumen['proyectos'][0]['casos'] == casos and resumen['proyectos'][0]['alimentadores'] == 2, SEMILLA
    assert resumen['avisos'] == [{'aviso': unico, 'veces': 2}, {'aviso': repetido, 'veces': veces}], SEMILLA
    assert resumen['total_avisos'] == veces + 2, SEMILLA
    assert estado['result']['informe_texto'], SEMILLA
    r = _subir(client, wid, nombre, {'casos': 1, 'avisos_fichero': [], 'avisos_proyecto': []}, reimportar='true')
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done' and estado['result']['resumen']['modo'] == 'reimportado', (SEMILLA, estado)


def test_un_fichero_que_no_es_pfd_se_rechaza_sin_encolar(client, pfd_falso):
    """004:RF-118 — un fichero que no es ``.pfd`` se rechaza al subirlo (400), sin trabajo; un nombre con carpetas o
    reservado por Windows se guarda con un nombre seguro."""
    from convertersmartgrid.presentacion.web import services

    wid = client.post('/api/workspaces').json()['id']
    r = _subir(client, wid, 'red.dgs', b'x')
    assert r.status_code == 400 and '.pfd' in r.json()['detail'], r.text
    assert not client.get(f'/api/workspaces/{wid}').json().get('jobs'), 'no debía encolar nada'
    assert services.nombre_del_pfd('../otra/CON.pfd') == 'pfd_CON.pfd'
    assert services.nombre_del_pfd('a b+c.PFD') == 'a_b_c.pfd'


def test_un_pfd_que_no_se_importa_deja_el_trabajo_fallido_con_su_causa(client, pfd_falso):
    """004:RF-118, 086:RF-133 — si el guion sale con un código distinto de 0, el trabajo queda fallido con el error del
    informe, no «done»."""
    wid = client.post('/api/workspaces').json()['id']
    r = _subir(client, wid, 'ROTO.pfd', {'casos': 0, 'avisos_fichero': [], 'avisos_proyecto': [], 'codigo': 4,
                                          'errores': ['ComPfdimport no dejó ningún proyecto']})
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'failed', estado
    assert 'ComPfdimport no dejó ningún proyecto' in estado['error'] and 'ROTO.pfd' in estado['error'], estado['error']
