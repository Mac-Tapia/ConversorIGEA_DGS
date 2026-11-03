"""Spec 077: lo que el asistente puede leer del proyecto y lo que no, con un repositorio inventado."""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from convertersmartgrid.asistente import lectura_proyecto as lp
from convertersmartgrid.asistente.equipo import (
    ROLES_LECTURA,
    LecturaGobernada,
    PermisoDenegado,
    inventario_equipo,
)

RAIZ = Path(__file__).resolve().parents[1]
SECRETO = 'VALOR-QUE-NO-DEBE-SALIR'


def _openapi() -> dict:
    return {'openapi': '3.1.0', 'paths': {
        '/api/jobs/{job_id}': {'get': {'summary': 'Estado de un trabajo', 'parameters': [
            {'name': 'job_id', 'in': 'path', 'required': True}],
            'responses': {'200': {'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Trabajo'}}}}}}},
        '/api/jobs/{job_id}/cancel': {'post': {'summary': 'Cancela', 'responses': {'202': {}}}}},
        'components': {'schemas': {'Trabajo': {'properties': {'id': {}, 'status': {}}, 'required': ['id']}}}}


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'repo'
    for carpeta in ('src/pkg', 'tools', 'docs/asistente', 'docs/superpowers/specs', 'specs/098-prueba', '.claude/skills/uno',
                    'output', 'input', 'config/perfiles', '.agents/coordination', 'frontend/src', 'maestro_real'):
        (repo / carpeta).mkdir(parents=True)
    (repo / 'src/pkg/barra.py').write_text('\n'.join(f'# línea {i} del reparto' for i in range(1, 501)), encoding='utf-8')
    (repo / 'docs/GUIA.md').write_text('# Guía\n\nCómo se reinicia la web.\n', encoding='utf-8')
    (repo / 'docs/DIAGNOSTICO_X.md').write_text('# Viejo\n\nAlgo que ya no es así.\n', encoding='utf-8')
    (repo / 'docs/INFORME_2026-01-01.md').write_text('# Foto\n\nDe aquel día.\n', encoding='utf-8')
    (repo / 'docs/superpowers/specs/viejo.md').write_text('# Viejo\n', encoding='utf-8')
    (repo / 'specs/098-prueba/spec.md').write_text('# 098\n\nEstado: aprobada · Fecha\n\n- RF-1: EL SISTEMA hará algo.\n', encoding='utf-8')
    (repo / '.claude/skills/uno/SKILL.md').write_text('# Skill uno\n', encoding='utf-8')
    (repo / 'README.md').write_text('# Léame\n', encoding='utf-8')
    (repo / 'docs/asistente/openapi.json').write_text(json.dumps(_openapi(), indent=2, sort_keys=True), encoding='utf-8')
    for negro in ('output/resultado.md', 'input/entrada.json', 'config/perfil_empresa.json', '.env', 'docs/.env',
                  'config/perfiles/una.json', '.agents/coordination/ACTIVE.md', 'docs/credentials.json', 'src/secrets.py',
                  'docs/RAG_ABSTENCION_SELLADO_099.json', 'docs/EVALUACION_ABSTENCION_099.json',
                  'docs/asistente/preguntas_entregables.jsonl', 'maestro_real/ordenes.jsonl'):
        (repo / negro).write_text(SECRETO, encoding='utf-8')
    return repo


NEGRAS = ['output/resultado.md', 'input/entrada.json', 'config/perfil_empresa.json', '.env', 'docs/.env',
          'config/perfiles/una.json', '.agents/coordination/ACTIVE.md', 'docs/credentials.json', 'src/secrets.py',
          'docs/RAG_ABSTENCION_SELLADO_099.json', 'docs/EVALUACION_ABSTENCION_099.json',
          'docs/asistente/preguntas_entregables.jsonl', 'maestro_real/ordenes.jsonl']


def _salida_sin_secreto(salida) -> None:
    assert SECRETO not in json.dumps(salida, ensure_ascii=False)


def test_lee_por_rango_con_tope(tmp_path):
    """077:RF-16 — lee por rango, con un tope por lectura y lo dice."""
    repo = _repo(tmp_path)
    r = lp.leer_fichero(repo, 'src/pkg/barra.py', 3, 5)
    assert r['texto'].splitlines() == ['# línea 3 del reparto', '# línea 4 del reparto', '# línea 5 del reparto']
    assert r['fuente'] == 'src/pkg/barra.py:3' and not r['truncado'] and r['total_lineas'] == 500
    largo = lp.leer_fichero(repo, 'src/pkg/barra.py')
    assert largo['hasta'] == lp.TOPE_LINEAS and largo['truncado']
    with pytest.raises(lp.ArgumentoInvalido):
        lp.leer_fichero(repo, 'src/pkg/barra.py', 0)
    with pytest.raises(lp.ArgumentoInvalido):
        lp.leer_fichero(repo, 'src/pkg/barra.py', 5, 3)


def test_busca_literal_y_con_tope(tmp_path):
    """077:RF-17 — el texto va literal: una expresión regular no se interpreta, y hay tope."""
    repo = _repo(tmp_path)
    r = lp.buscar_texto(repo, 'línea 7 del', tope=5)
    assert [c['fuente'] for c in r['coincidencias']] == ['src/pkg/barra.py:7']
    assert lp.buscar_texto(repo, 'l.nea 7 del')['coincidencias'] == []
    assert lp.buscar_texto(repo, '(a+)+$')['coincidencias'] == []
    tope = lp.buscar_texto(repo, 'del reparto', tope=3)
    assert len(tope['coincidencias']) == 3 and tope['truncado']
    with pytest.raises(lp.ArgumentoInvalido):
        lp.buscar_texto(repo, 'ab')


@pytest.mark.parametrize('texto', [SECRETO, SECRETO.lower()])
def test_la_busqueda_no_entra_en_lo_rechazado(tmp_path, texto):
    """077:RF-17 / 077:RF-20 — ninguna búsqueda encuentra nada en la lista negra."""
    r = lp.buscar_texto(_repo(tmp_path), texto)
    assert r['coincidencias'] == []
    with pytest.raises(lp.RutaRechazada):
        lp.buscar_texto(_repo(tmp_path / 'b'), 'algo', dentro='output')


def test_api_del_openapi_sin_ninguna_peticion(tmp_path, monkeypatch):
    """077:RF-18 — sale del fichero generado: cualquier intento de red haría fallar la prueba."""
    import socket

    def prohibido(*_a, **_k):
        raise AssertionError('consultar_api no hace peticiones')

    monkeypatch.setattr(socket.socket, 'connect', prohibido)
    repo = _repo(tmp_path)
    r = lp.consultar_api(repo, '/api/jobs/{job_id}')
    assert r['existe'] and r['operaciones'][0]['metodo'] == 'GET' and r['fuente'].startswith(lp.OPENAPI + ':')
    assert r['operaciones'][0]['respuesta']['application/json'] == {
        'esquema': 'Trabajo', 'campos': ['id', 'status'], 'obligatorios': ['id']}
    assert lp.consultar_api(repo, '/api/jobs/abc123/cancel', 'post')['ruta'] == '/api/jobs/{job_id}/cancel'
    assert lp.consultar_api(repo, '/api/jobs/abc123', 'post')['operaciones'] == []
    falta = lp.consultar_api(repo, '/api/jobs')
    assert not falta['existe'] and '/api/jobs/{job_id}' in falta['parecidas']
    with pytest.raises(lp.ArgumentoInvalido):
        lp.consultar_api(repo, 'api/jobs')


def test_lista_blanca(tmp_path):
    """077:RF-19 — se lee lo de la lista blanca, y nada que no esté en ella."""
    repo = _repo(tmp_path)
    for buena in ('src/pkg/barra.py', 'docs/GUIA.md', 'specs/098-prueba/spec.md', '.claude/skills/uno/SKILL.md', 'README.md'):
        assert lp.leer_fichero(repo, buena)['texto']
    (repo / 'otra.md').write_text('fuera', encoding='utf-8')
    (repo / 'docs/plano.pdf').write_bytes(b'%PDF')
    for mala in ('otra.md', 'docs/plano.pdf', 'frontend/package-lock.json', 'config/vnr_settings.yaml'):
        with pytest.raises(lp.RutaRechazada):
            lp.leer_fichero(repo, mala)


@pytest.mark.parametrize('negra', NEGRAS)
def test_lista_negra(tmp_path, negra):
    """077:RF-20 — cada ruta de la lista negra se rechaza por las tres vías, sin contenido."""
    repo = _repo(tmp_path)
    assert (repo / negra).is_file()
    with pytest.raises(lp.RutaRechazada) as exc:
        lp.leer_fichero(repo, negra)
    assert SECRETO not in str(exc.value)
    r = lp.nombradas_en(repo, f'que dice {negra}')
    assert r['pedidas'] == [] and r['rechazadas']


@pytest.mark.parametrize('ruta', ['../fuera.md', 'docs/../../fuera.md', 'docs/../output/resultado.md', '..\\fuera.md',
                                  'docs\\..\\..\\fuera.md', 'D:/BaseDatosElectroDunas/x.txt', 'D:\\BaseDatosElectroDunas\\x.txt',
                                  'D:fuera.md', '/etc/passwd', '\\\\servidor\\c\\x.md', '//servidor/c/x.md', 'C:\\Windows\\win.ini',
                                  './docs/GUIA.md', 'docs//GUIA.md', 'docs/%2e%2e/%2e%2e/fuera.md'])
def test_rutas_que_salen(tmp_path, ruta):
    """077:RF-21 — con `..`, absolutas, de otra unidad o de red, se rechazan."""
    repo = _repo(tmp_path)
    (tmp_path / 'fuera.md').write_text(SECRETO, encoding='utf-8')
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, ruta)


def _enlazar_carpeta(enlace: Path, destino: Path) -> None:
    """Una unión de directorios: en Windows no pide privilegios, a diferencia de un enlace simbólico."""
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(enlace), str(destino)], check=True, capture_output=True)


@pytest.mark.parametrize('destino', ['fuera', 'repo/output'])
def test_union_de_directorios(tmp_path, destino):
    """077:RF-22 — una unión dentro de docs/ hacia fuera o hacia output/ se rechaza, y la búsqueda no entra."""
    repo = _repo(tmp_path)
    (tmp_path / 'fuera').mkdir()
    (tmp_path / 'fuera/resultado.md').write_text(SECRETO, encoding='utf-8')
    _enlazar_carpeta(repo / 'docs/enlace', tmp_path / destino)
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, 'docs/enlace/resultado.md')
    assert lp.buscar_texto(repo, SECRETO)['coincidencias'] == []


def test_enlace_duro(tmp_path):
    """077:RF-22 — un enlace duro es el mismo fichero con otro nombre: se rechaza por su cuenta de enlaces."""
    repo = _repo(tmp_path)
    os.link(repo / '.env', repo / 'docs/nota.md')
    with pytest.raises(lp.RutaRechazada, match='enlace duro'):
        lp.leer_fichero(repo, 'docs/nota.md')
    assert lp.buscar_texto(repo, SECRETO)['coincidencias'] == []


def test_enlace_simbolico(tmp_path):
    """077:RF-22 — un enlace simbólico al secreto también, sin depender de que la máquina deje crearlo."""
    repo = _repo(tmp_path)
    enlace = repo / 'docs/nota.md'
    try:
        enlace.symlink_to(repo / '.env')
    except OSError:
        # Sin el privilegio de Windows se comprueba la misma decisión con lo que devolvería resolve().
        original = Path.resolve

        def resuelve(self, *a, **k):
            return (repo / '.env').absolute() if self == enlace else original(self, *a, **k)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Path, 'resolve', resuelve)
            enlace.write_text('', encoding='utf-8')
            with pytest.raises(lp.RutaRechazada, match='enlace|rechazada'):
                lp.leer_fichero(repo, 'docs/nota.md')
        return
    with pytest.raises(lp.RutaRechazada, match='enlace|rechazada'):
        lp.leer_fichero(repo, 'docs/nota.md')
    assert lp.buscar_texto(repo, SECRETO)['coincidencias'] == []


@pytest.mark.parametrize('ruta', ['OUTPUT/resultado.md', 'Output/Resultado.MD', 'INPUT/entrada.json', 'CONFIG/PERFIL_EMPRESA.JSON',
                                  'Config/Perfil_Empresa.json', '.ENV', 'Docs/.Env', '.AGENTS/coordination/ACTIVE.md',
                                  'CONFIG/PERFILES/una.json', 'docs/CREDENTIALS.JSON', 'DOCS/rag_abstencion_sellado_099.JSON',
                                  'MAESTRO_REAL/ordenes.jsonl'])
def test_mayusculas(tmp_path, ruta):
    """077:RF-23 — en NTFS es el mismo fichero: las listas no distinguen mayúsculas."""
    repo = _repo(tmp_path)
    assert (repo / ruta).is_file()                          # el sistema de ficheros sí lo encuentra
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, ruta)


@pytest.mark.parametrize('ruta', ['.env::$DATA', 'docs/GUIA.md::$DATA', '.env.', '.env ', 'docs/GUIA.md.', 'docs/GUIA.md ',
                                  'CONFIG~1/perfil_empresa.json', 'OUTPUT~1/resultado.md', 'docs/GUIA.md\x00.txt', 'docs/NUL',
                                  'docs/con.md', 'docs/GUIA.md\n'])
def test_trucos_de_ntfs(tmp_path, ruta):
    """077:RF-24 — flujos alternativos, nombres cortos, punto o espacio final, nulos y dispositivos."""
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(_repo(tmp_path), ruta)


def test_sin_ninguna_escritura_ni_red():
    """077:RF-25 — el módulo no escribe, no borra y no abre la red: se comprueba sobre su código."""
    arbol = ast.parse((RAIZ / 'src/convertersmartgrid/asistente/lectura_proyecto.py').read_text(encoding='utf-8'))
    prohibidas = {'write', 'write_text', 'write_bytes', 'unlink', 'rmdir', 'mkdir', 'rename', 'replace', 'touch', 'remove',
                  'makedirs', 'system', 'popen', 'urlopen', 'request', 'get', 'post'}
    llamadas = {n.func.attr for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    # `get` y `replace` de dict y str son legítimos: solo se admiten sobre datos, nunca desde os, Path o shutil.
    sospechosas = llamadas & prohibidas - {'get', 'replace'}
    assert not sospechosas, sospechosas
    importados = {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    importados |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
    assert not importados & {'shutil', 'subprocess', 'socket', 'requests', 'httpx', 'urllib', 'tempfile'}
    modos = [n.args[0].value for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'open' and n.args]
    assert set(modos) <= {'rb'}, modos
    assert not (RAIZ / 'tools/mcp_conversor.py').read_text(encoding='utf-8').count('write_text')


def test_sellados_reales_rechazados():
    """077:RF-20 — los conjuntos y resultados sellados que hay en el repositorio no se pueden leer."""
    for rel in ('docs/RAG_ABSTENCION_SELLADO_047.json', 'docs/EVALUACION_ABSTENCION_047.json', 'docs/CONJUNTO_ABSTENCION_SELLADO_077.json',
                'docs/asistente/preguntas_entregables.jsonl', 'docs/asistente/hechos_web.jsonl'):
        assert (lp.motivo_de_rechazo(rel) or "").startswith("lista negra"), rel


def test_nombres_en_la_pregunta(tmp_path):
    """077:RF-26 / 077:RF-27 — lo que nombra una pregunta se lee; lo rechazado se dice y un nombre ambiguo no se adivina."""
    repo = _repo(tmp_path)
    (repo / 'tools/barra.py').write_text('"""Otra."""\n', encoding='utf-8')
    r = lp.nombradas_en(repo, 'que hace src/pkg/barra.py:50 y que da GET /api/jobs/{job_id} ?')
    assert ('leer_fichero', {'ruta': 'src/pkg/barra.py', 'desde': 30, 'hasta': 70}) in r['pedidas']
    assert ('consultar_api', {'ruta': '/api/jobs/{job_id}'}) in r['pedidas'] and not r['rechazadas']
    assert lp.nombradas_en(repo, 'que hace barra.py')['pedidas'] == []
    assert lp.nombradas_en(repo, 'que dice GUIA.md')['pedidas'][0][1]['ruta'] == 'docs/GUIA.md'
    negadas = lp.nombradas_en(repo, 'abre .env y D:/BaseDatosElectroDunas/x.txt y ../secreto.md')
    assert not negadas['pedidas'] and len(negadas['rechazadas']) == 3
    assert lp.nombradas_en(repo, 'como se calibra una barra de 60 kv')['pedidas'] == []
    # Lo que solo tiene forma de ruta no se lee ni se avisa: el operador no pidió ningún fichero.
    corriente = lp.nombradas_en(repo, 'la caida en kV/km y/o el 12/10/2026 de TM106/TM107 con otra.md')
    assert corriente == {'pedidas': [], 'rechazadas': []}
    assert lp.nombradas_en(repo, 'abre .ENV')['rechazadas'] == ['.ENV']


def test_gobierno_por_rol(tmp_path):
    """077:RF-33 — solo los roles de lectura leen; otro rol se rechaza y queda anotado."""
    repo, filas = _repo(tmp_path), []
    bueno = LecturaGobernada(repo, rol='operador', registrar=filas.append)
    assert bueno.ejecutar('leer_fichero', {'ruta': 'docs/GUIA.md'})['texto']
    assert 'fisica' in ROLES_LECTURA and 'cliente_mcp' in ROLES_LECTURA
    malo = LecturaGobernada(repo, rol='modelo', registrar=filas.append)
    with pytest.raises(PermisoDenegado):
        malo.ejecutar('leer_fichero', {'ruta': 'docs/GUIA.md'})
    assert filas[-1]['estado'] == 'lectura_rechazada' and filas[-1]['responsable'] == 'modelo'


def test_bitacora_sin_contenido(tmp_path):
    """077:RF-34 — cada lectura se anota con rol, herramienta, argumentos y huella, nunca con el contenido."""
    repo, filas = _repo(tmp_path), []
    salida = LecturaGobernada(repo, registrar=filas.append).ejecutar('leer_fichero', {'ruta': 'docs/GUIA.md'})
    assert filas[0]['herramienta'] == 'leer_fichero' and filas[0]['responsable'] == 'operador'
    assert filas[0]['entradas'] == {'ruta': 'docs/GUIA.md'} and filas[0]['salida_sha256']
    assert salida['texto'] not in json.dumps(filas)
    with pytest.raises(lp.RutaRechazada):
        LecturaGobernada(repo, registrar=filas.append).ejecutar('leer_fichero', {'ruta': '.env'})
    assert filas[-1]['estado'] == 'lectura_rechazada' and SECRETO not in json.dumps(filas)


def test_fuera_del_catalogo_y_con_argumentos_de_mas(tmp_path):
    """077:RF-29 — nombre o argumentos fuera del catálogo no se ejecutan."""
    gobernada = LecturaGobernada(_repo(tmp_path), registrar=lambda _f: None)
    with pytest.raises(lp.ArgumentoInvalido):
        gobernada.ejecutar('escribir_fichero', {'ruta': 'docs/GUIA.md'})
    with pytest.raises(lp.ArgumentoInvalido):
        gobernada.ejecutar('leer_fichero', {'ruta': 'docs/GUIA.md', 'modo': 'w'})
    with pytest.raises(lp.ArgumentoInvalido):
        gobernada.ejecutar('leer_fichero', {})


def test_inventario_declara_las_lecturas():
    """077:RF-35 — el inventario dice qué se lee y que ningún modelo concede permisos."""
    inventario = inventario_equipo()
    assert inventario['modelos_conceden_permisos'] is False
    lectura = inventario['lectura_proyecto']
    assert {h['nombre'] for h in lectura['herramientas']} == set(lp.HERRAMIENTAS)
    assert lectura['escribe'] is False and set(lectura['roles']) == set(ROLES_LECTURA)
    assert 'output' in lectura['lista_negra']['segmentos']


def test_catalogo_de_ordenes_sin_tareas_nuevas():
    """077:RF-36 — ninguna lectura es una tarea: el catálogo de órdenes no crece."""
    from convertersmartgrid.asistente.prueba_sellada import selladas
    from convertersmartgrid.asistente.tareas import TAREAS

    assert not set(lp.HERRAMIENTAS) & set(TAREAS)
    assert selladas()                                       # con su huella: lanza si el catálogo cambió
