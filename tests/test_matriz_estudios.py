"""Matriz estudio × motor: cada estudio de la web dice con qué motor está validado (100:RF-8 a RF-12).

Plan Maestro PM-20 (honestidad comercial): hasta el 2026-11-19 la web ofrecía cada estudio como si estuviera listo,
también los que solo tenían código y ninguna corrida de aceptación (el cortocircuito y la fiabilidad de la 012, el
PIT de la 107). La matriz sale del estado de las specs, no de lo que alguien escriba a mano.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _dominio():
    from convertersmartgrid.dominio import matriz_estudios
    return matriz_estudios


def test_100_rf8_cada_estudio_de_la_web_con_cada_motor():
    """100:RF-8 — todos los estudios del catálogo de la web y sus módulos, con una celda por motor."""
    from convertersmartgrid.aplicacion.studies import ESTUDIOS

    m = _dominio()
    tabla = m.matriz(lambda _n: 'cumplida')
    motores = [x['clave'] for x in tabla['motores']]
    assert motores == ['digsilent', 'abierto', 'pinn', 'conversor']
    por_clave = {e['clave']: e for e in tabla['estudios']}
    for e in ESTUDIOS:                       # los chips de «4.2 · Estudios» se buscan por su clave
        assert e.clave in por_clave, e.clave
        assert por_clave[e.clave]['nombre'] == e.nombre, e.clave
    for modulo in ('calibracion', 'obras', 'gemelo', 'pide', 'largo_plazo', 'pit', 'vad', 'vnr', 'pronostico'):
        assert modulo in por_clave, modulo
    for e in tabla['estudios']:
        assert [c['motor'] for c in e['celdas']] == motores, e['clave']
        for c in e['celdas']:
            assert c['estado'] in m.ESTADOS
            # Cada celda tiene evidencia o motivo: nunca un estado sin de dónde sale.
            assert c['evidencia'] or c['estado'] == 'no_disponible', (e['clave'], c)
            assert c['motivo'] or c['estado'] == 'validado', (e['clave'], c)


def test_100_rf9_validado_solo_con_todas_sus_specs_cumplidas():
    """100:RF-9 — «validado» pide cada spec de su evidencia cumplida; sin specs que leer, «sin validar»."""
    m = _dominio()

    def celda(tabla, estudio, motor):
        e = next(x for x in tabla['estudios'] if x['clave'] == estudio)
        return next(c for c in e['celdas'] if c['motor'] == motor)

    todas = m.matriz(lambda _n: 'cumplida')
    assert celda(todas, 'flujo', 'digsilent')['estado'] == 'validado'
    assert celda(todas, 'flujo', 'digsilent')['motivo'] == ''

    # Una sola spec de la evidencia sin cerrar basta para que no se diga validado.
    specs = [x['spec'] for x in celda(todas, 'calibracion', 'digsilent')['evidencia']]
    assert len(specs) > 1
    una_abierta = m.matriz(lambda n: 'implementada' if n == specs[-1] else 'cumplida')
    c = celda(una_abierta, 'calibracion', 'digsilent')
    assert c['estado'] == 'sin_validar' and c['motivo']
    assert {x['spec']: x['estado'] for x in c['evidencia']}[specs[-1]] == 'implementada'

    # Un servidor sin la carpeta specs/ no puede probar nada: todo lo validable queda «sin validar».
    sin_specs = m.matriz(lambda _n: None)
    estados = {c['estado'] for e in sin_specs['estudios'] for c in e['celdas']}
    assert 'validado' not in estados and 'sin_validar' in estados

    # «No disponible» no depende de las specs: no hay código que validar.
    assert celda(sin_specs, 'cortocircuito', 'abierto')['estado'] == 'no_disponible'
    assert celda(todas, 'cortocircuito', 'abierto')['estado'] == 'no_disponible'
    assert celda(todas, 'armonicos', 'digsilent')['estado'] == 'no_disponible'


def test_100_rf10_la_ruta_sirve_la_matriz_con_el_estado_real_de_las_specs(tmp_path, monkeypatch):
    """100:RF-10 — ``GET /api/estudios/matriz`` lee la línea ``Estado:`` de cada spec del repositorio."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.aplicacion.asistente.lectura_proyecto import estado_de_spec
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    carpetas = {d.name[:3]: d.name for d in (RAIZ / 'specs').iterdir() if (d / 'spec.md').is_file()}
    with TestClient(create_app(tmp_path / 'web')) as cliente:
        r = cliente.get('/api/estudios/matriz')
        assert r.status_code == 200, r.text
        tabla = r.json()
        esquema = cliente.get('/openapi.json').json()
    assert tabla['origen'] == 'specs'             # en el repositorio manda specs/ (RF-13)
    ref = esquema['paths']['/api/estudios/matriz']['get']['responses']['200']['content']['application/json']['schema']
    assert ref['$ref'].endswith('/MatrizEstudiosRespuesta')
    for e in tabla['estudios']:
        for c in e['celdas']:
            for ev in c['evidencia']:
                assert ev['spec'] in carpetas, (e['clave'], ev)
                assert ev['estado'] == estado_de_spec(RAIZ, carpetas[ev['spec']]), (e['clave'], ev)
            if c['evidencia']:
                cerradas = all(ev['estado'] == 'cumplida' for ev in c['evidencia'])
                assert (c['estado'] == 'validado') == cerradas, (e['clave'], c)


def test_100_rf11_textos_del_operador_sin_citas_internas():
    """100:RF-11 — nombres y motivos sin números de spec, RF ni plurales «(s)»."""
    m = _dominio()
    tabla = m.matriz(lambda _n: 'aprobada')
    textos = [x['nombre'] for x in tabla['motores']]
    for e in tabla['estudios']:
        textos.append(e['nombre'])
        textos.extend(c['motivo'] for c in e['celdas'])
    for t in textos:
        assert not re.search(r'\bRF-\d|\b\d{3}\b|spec|\(s\)|\(es\)', t, re.I), t


@pytest.mark.parametrize('clave', ['cortocircuito', 'fiabilidad', 'pit', 'vad'])
def test_100_rf12_lo_que_solo_tiene_codigo_no_se_dice_validado(clave):
    """100:RF-12 — con las specs del repositorio, lo que aún no tiene su aceptación cerrada sale «sin validar»."""
    from convertersmartgrid.aplicacion.asistente.lectura_proyecto import estado_de_spec

    m = _dominio()
    carpetas = {d.name[:3]: d.name for d in (RAIZ / 'specs').iterdir() if (d / 'spec.md').is_file()}
    tabla = m.matriz(lambda n: estado_de_spec(RAIZ, carpetas[n]) if n in carpetas else None)
    e = next(x for x in tabla['estudios'] if x['clave'] == clave)
    for c in e['celdas']:
        if any(ev['estado'] != 'cumplida' for ev in c['evidencia']):
            assert c['estado'] == 'sin_validar', (clave, c)


# ----------------------------------------------------------------- 100:RF-13, el programa instalado
# Auditoría de d8, 2026-11-19: ``config/entrega.json`` excluye ``specs/``; el programa del acceso directo decía «sin
# validar» también de lo validado. El estado viaja en ``recursos/estado_specs.json``, que escribe estado_specs.py.

RECURSO_REL = 'src/convertersmartgrid/recursos/estado_specs.json'


def test_100_rf13_el_recurso_esta_al_dia_con_specs():
    """100:RF-13 — el recurso es lo que genera ``tools/estado_specs.py --escribir``, con la huella del README."""
    import hashlib
    import json

    from apoyo import cargar_herramienta

    es = cargar_herramienta('estado_specs.py')
    actual = (RAIZ / RECURSO_REL).read_text(encoding='utf-8')
    assert actual == es.recurso(RAIZ), 'python tools/estado_specs.py --escribir'
    datos = json.loads(actual)
    readme = (RAIZ / 'specs' / 'README.md').read_text(encoding='utf-8')
    assert datos['huella_readme'] == hashlib.sha256(readme.encode('utf-8')).hexdigest()
    assert datos['estados'] == {s.numero: s.estado for s in es.leer_specs(RAIZ)}


def test_100_rf13_sin_specs_y_con_el_recurso_lo_validado_sale_validado(tmp_path):
    """100:RF-13 — sin ``specs/`` manda el recurso; sin ninguno de los dos, nada validado; la respuesta dice el origen."""
    from convertersmartgrid.presentacion.web.matriz_estudios_api import estados_de_specs

    m = _dominio()
    repo, origen_repo = estados_de_specs(RAIZ, RAIZ / RECURSO_REL)
    instalado, origen = estados_de_specs(tmp_path, RAIZ / RECURSO_REL)      # como el paquete: sin specs/
    assert (origen_repo, origen) == ('specs', 'recurso')
    con_specs, con_recurso = m.matriz(repo, origen_repo), m.matriz(instalado, origen)
    assert con_recurso['origen'] == 'recurso'
    # Mismas celdas que con specs/: el recurso está al día (prueba de arriba).
    assert con_recurso['estudios'] == con_specs['estudios']
    estados = {c['estado'] for e in con_recurso['estudios'] for c in e['celdas']}
    assert 'validado' in estados

    nada, origen_nada = estados_de_specs(tmp_path, tmp_path / 'no_esta.json')
    sin = m.matriz(nada, origen_nada)
    assert sin['origen'] == 'ninguno'
    assert 'validado' not in {c['estado'] for e in sin['estudios'] for c in e['celdas']}

    roto = tmp_path / 'roto.json'
    roto.write_text('{"estados": "x"}', encoding='utf-8')
    assert estados_de_specs(tmp_path, roto)[1] == 'ninguno'


def test_100_rf13_el_recurso_entra_en_la_entrega_y_en_la_rueda():
    """100:RF-13 — ``config/entrega.json`` lo incluye (y excluye ``specs/``) y el paquete lo declara en package-data."""
    import tomllib

    from apoyo import cargar_herramienta

    ce = cargar_herramienta('comprobar_entrega.py')
    manifiesto = ce.leer_manifiesto()
    assert ce.entra(RECURSO_REL, manifiesto)
    assert not ce.entra('specs/100-aceptacion-automatica-por-version/spec.md', manifiesto)
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'recursos/*.json' in datos['tool']['setuptools']['package-data']['convertersmartgrid']


def test_100_rf9_lo_cerrado_sin_corrida_propia_espera_a_la_aceptacion_por_version():
    """100:RF-9 — una spec cumplida cuya tarea de DIgSILENT se cerró «sin corrida propia» y pasó a la 100 no valida nada
    sola: sus celdas llevan también la 100. La lista del dominio sigue a las notas de las tareas."""
    m = _dominio()
    citadas = {n for _nombre, celdas in m.ESTUDIOS.values() for c in celdas.values()
               if isinstance(c, m.Evidencia) for n in c.specs}
    nota = re.compile(r'sin corrida propia[^\n]*aceptación automática \(spec 100\)')
    con_nota = set()
    for d in (RAIZ / 'specs').iterdir():
        tareas = d / 'tasks.md'
        if d.name[:3] in citadas and tareas.is_file() and nota.search(tareas.read_text(encoding='utf-8')):
            con_nota.add(d.name[:3])
    assert con_nota == set(m.ACEPTACION_EN_LA_100)
    for _nombre, celdas in m.ESTUDIOS.values():
        for c in celdas.values():
            if isinstance(c, m.Evidencia) and m.ACEPTACION_EN_LA_100 & set(c.specs):
                assert '100' in c.specs, c
