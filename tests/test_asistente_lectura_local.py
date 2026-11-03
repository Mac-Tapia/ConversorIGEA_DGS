"""Spec 077: con un LLM local se lee todo lo local, salvo secretos, lo sellado y el examen humano. Con datos inventados."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from convertersmartgrid.asistente import corpus_proyecto, indice
from convertersmartgrid.asistente import lectura_proyecto as lp
from convertersmartgrid.asistente import ollama as modulo_ollama
from convertersmartgrid.asistente.equipo import LecturaGobernada

RAIZ = Path(__file__).resolve().parents[1]
DATO = 'CODIGO-ZX9981 de la empresa Ficticia'
SECRETO = 'VALOR-QUE-NO-DEBE-SALIR'


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.delenv('CSG_LLM_RAICES', raising=False)
    monkeypatch.delenv('CSG_DEMANDA_DIR', raising=False)
    repo = tmp_path / 'repo'
    for carpeta in ('output/informes', 'input', 'config/perfiles', '.agents/coordination', '.cursor/skills', 'frontend/dist', 'docs/asistente',
                    '.git', '.venv/Lib', 'node_modules/x', 'src/convertersmartgrid/asistente', 'tools', 'specs/098-a', '__pycache__', 'maestro_real'):
        (repo / carpeta).mkdir(parents=True)
    for rel in ('output/informes/resultado.md', 'input/entrada.csv', 'config/perfil_empresa.json', 'config/perfiles/una.json',
                '.agents/coordination/ACTIVE.md', '.cursor/skills/x.md', 'frontend/dist/app.js', 'otra.md', 'maestro_real/textos.txt',
                '.venv/Lib/nota.txt', 'node_modules/x/leeme.md', '__pycache__/nota.txt', '.git/HEAD'):
        (repo / rel).write_text(DATO + ' en ' + rel, encoding='utf-8')
    for rel in ('.env', 'docs/.env.local', 'config/credentials.json', 'tools/secrets.py', 'clave.pem', 'id_rsa', '.npmrc', '.git/config',
                'docs/RAG_ABSTENCION_SELLADO_099.json', 'docs/CONJUNTO_X_099.json', 'docs/EVALUACION_X_099.json', 'docs/CALIBRACION_X_099.json',
                'output/evaluacion_final.json', 'src/convertersmartgrid/asistente/prueba_sellada.py', 'src/convertersmartgrid/asistente/ordenes_fijas.py',
                'docs/asistente/filas.jsonl', 'output/ejemplos.jsonl', 'maestro_real/etiquetas.jsonl', 'output/etiquetas_v2.jsonl'):
        (repo / rel).write_text(SECRETO, encoding='utf-8')
    (repo / lp.OPENAPI).write_text(json.dumps({'paths': {}}), encoding='utf-8')
    return repo


@pytest.fixture
def raiz_datos(tmp_path, monkeypatch):
    raiz = tmp_path / 'BaseFicticia'
    (raiz / 'sub').mkdir(parents=True)
    (raiz / 'sub/RED_(1).txt').write_text(DATO + '\n', encoding='utf-8')
    (raiz / 'ejemplos.jsonl').write_text(SECRETO, encoding='utf-8')
    (raiz / '.env').write_text(SECRETO, encoding='utf-8')
    monkeypatch.setenv('CSG_LLM_RAICES', str(raiz))
    return raiz


LOCAL = lp.Politica(True)
LEIBLES = ['output/informes/resultado.md', 'input/entrada.csv', 'config/perfil_empresa.json', 'config/perfiles/una.json',
           '.agents/coordination/ACTIVE.md', '.cursor/skills/x.md', 'frontend/dist/app.js', 'otra.md', 'maestro_real/textos.txt',
           'OUTPUT/informes/resultado.md']
SECRETOS = ['.env', '.ENV', 'docs/.env.local', 'config/credentials.json', 'tools/secrets.py', 'clave.pem', 'id_rsa', '.npmrc', '.git/config']
SELLADOS = ['docs/RAG_ABSTENCION_SELLADO_099.json', 'docs/CONJUNTO_X_099.json', 'docs/EVALUACION_X_099.json', 'docs/CALIBRACION_X_099.json',
            'output/evaluacion_final.json', 'src/convertersmartgrid/asistente/prueba_sellada.py',
            'src/convertersmartgrid/asistente/ordenes_fijas.py', 'docs/asistente/filas.jsonl']
EXAMEN = ['output/ejemplos.jsonl', 'maestro_real/etiquetas.jsonl', 'output/etiquetas_v2.jsonl']


@pytest.mark.parametrize('rel', LEIBLES)
def test_todo_el_arbol_con_llm_local(repo, rel):
    """077:RF-51 — con LLM local se lee el árbol entero; con la restringida, no."""
    assert DATO in lp.leer_fichero(repo, rel, politica=LOCAL)['texto']
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, rel)


def test_fuera_del_arbol_sigue_cerrado(repo, tmp_path):
    """077:RF-51 — abrir el árbol no abre lo demás: `..` y absolutas sin raíz se rechazan, también por unión."""
    (tmp_path / 'fuera.md').write_text(SECRETO, encoding='utf-8')
    for ruta in ('../fuera.md', 'docs/../../fuera.md', str(tmp_path / 'fuera.md'), '\\\\servidor\\c\\x.md', 'output/x.md::$DATA', 'CONFIG~1/x'):
        with pytest.raises(lp.RutaRechazada):
            lp.leer_fichero(repo, ruta, politica=LOCAL)
    (tmp_path / 'fuera_dir').mkdir()
    (tmp_path / 'fuera_dir/x.md').write_text(SECRETO, encoding='utf-8')
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(repo / 'output/enlace'), str(tmp_path / 'fuera_dir')], check=True, capture_output=True)
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, 'output/enlace/x.md', politica=LOCAL)
    assert lp.buscar_texto(repo, SECRETO, politica=LOCAL)['coincidencias'] == []


def test_raices_configuradas(repo, raiz_datos, tmp_path, monkeypatch):
    """077:RF-52 — una raíz de `CSG_LLM_RAICES`, de `CSG_DEMANDA_DIR` o del perfil se lee por su ruta, y sin ella no."""
    politica = lp.politica_local()
    assert raiz_datos in politica.raices
    r = lp.leer_fichero(repo, f'{raiz_datos.as_posix()}/sub/RED_(1).txt', politica=politica)
    assert DATO in r['texto'] and r['es_dato']
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, f'{raiz_datos.as_posix()}/sub/RED_(1).txt', politica=LOCAL)
    with pytest.raises(lp.RutaRechazada):
        lp.leer_fichero(repo, f'{raiz_datos.as_posix()}/sub/RED_(1).txt')
    monkeypatch.delenv('CSG_LLM_RAICES')
    monkeypatch.setenv('CSG_DEMANDA_DIR', str(raiz_datos))
    assert raiz_datos in lp.politica_local().raices
    monkeypatch.delenv('CSG_DEMANDA_DIR')
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda: {'raices_llm': [str(raiz_datos)]})
    assert raiz_datos in lp.politica_local().raices


def test_sin_rutas_fijas_en_el_codigo():
    """077:RF-52 — ninguna carpeta de datos escrita en el código que decide las raíces."""
    fuente = (RAIZ / 'src/convertersmartgrid/asistente/lectura_proyecto.py').read_text(encoding='utf-8')
    arbol = ast.parse(fuente)
    funcion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == 'raices_configuradas')
    textos = [n.value for n in ast.walk(funcion) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [t for t in textos if ':/' in t or ':\\' in t or t.startswith('~')]


@pytest.mark.parametrize('rel', SECRETOS)
def test_secretos_nunca(repo, rel):
    """077:RF-53 — credenciales y secretos, con ninguna política, también en cualquier carpeta."""
    with pytest.raises(lp.RutaRechazada) as exc:
        lp.leer_fichero(repo, rel, politica=LOCAL)
    assert SECRETO not in str(exc.value)


@pytest.mark.parametrize('rel', SELLADOS)
def test_sellados_nunca(repo, rel):
    """077:RF-54 — los conjuntos sellados y sus resultados, con ninguna política."""
    with pytest.raises(lp.RutaRechazada, match='sellado'):
        lp.leer_fichero(repo, rel, politica=LOCAL)


def test_sellados_reales(repo):
    """077:RF-54 — los ficheros reales de lo sellado y el conjunto de la 076 quedan fuera; el OpenAPI, dentro."""
    for rel in ('docs/RAG_ABSTENCION_SELLADO_047.json', 'docs/CONJUNTO_ABSTENCION_SELLADO_077.json', 'docs/EVALUACION_ABSTENCION_047.json',
                'docs/CALIBRACION_ABSTENCION_047.json', 'docs/asistente/preguntas_entregables.jsonl', 'docs/asistente/hechos_web.jsonl'):
        assert lp.motivo_de_rechazo(rel, LOCAL), rel
    assert lp.motivo_de_rechazo(lp.OPENAPI, LOCAL) is None
    # Código que evalúa, sin datos sellados: sigue legible.
    assert lp.motivo_de_rechazo('src/convertersmartgrid/asistente/evaluacion_rag.py', LOCAL) is None


@pytest.mark.parametrize('rel', EXAMEN)
def test_examen_humano_nunca(repo, rel):
    """077:RF-55 — `ejemplos.jsonl` y `etiquetas*.jsonl`: son la prueba humana y su parte reservada."""
    with pytest.raises(lp.RutaRechazada, match='examen humano'):
        lp.leer_fichero(repo, rel, politica=LOCAL)


def test_exclusiones_tambien_en_raices_y_por_nombre(repo, raiz_datos):
    """077:RF-53 / 077:RF-55 — dentro de una raíz, por ruta absoluta, por nombre suelto y por búsqueda."""
    politica = lp.politica_local()
    for nombre in ('ejemplos.jsonl', '.env'):
        with pytest.raises(lp.RutaRechazada):
            lp.leer_fichero(repo, f'{raiz_datos.as_posix()}/{nombre}', politica=politica)
    assert lp.buscar_texto(repo, SECRETO, politica=politica)['coincidencias'] == []
    negadas = lp.nombradas_en(repo, 'abre ejemplos.jsonl y .env y etiquetas.jsonl', politica)
    assert not negadas['pedidas'] and len(negadas['rechazadas']) == 3


def test_enlace_duro_a_un_secreto(repo):
    """077:RF-53 — un enlace duro a un secreto no lo abre, aunque su nombre sea inocente."""
    import os

    os.link(repo / '.env', repo / 'output/nota.md')
    with pytest.raises(lp.RutaRechazada, match='enlace duro'):
        lp.leer_fichero(repo, 'output/nota.md', politica=LOCAL)
    assert lp.buscar_texto(repo, SECRETO, politica=LOCAL)['coincidencias'] == []


def test_lo_que_no_aporta_solo_por_nombre(repo):
    """077:RF-56 — `.venv`, `node_modules`, `.git` y cachés: se leen si se nombran, una búsqueda no entra."""
    for rel in ('.venv/Lib/nota.txt', 'node_modules/x/leeme.md', '__pycache__/nota.txt', '.git/HEAD'):
        assert DATO in lp.leer_fichero(repo, rel, politica=LOCAL)['texto']
    rutas = {c['ruta'] for c in lp.buscar_texto(repo, 'CODIGO-ZX9981', politica=LOCAL)['coincidencias']}
    assert 'otra.md' in rutas and not {r for r in rutas if r.startswith(('.venv', 'node_modules', '__pycache__', '.git'))}
    (repo / '.venv/Lib/modulo.pyc').write_bytes(b'\x00\x01binario')
    assert lp.leer_fichero(repo, '.venv/Lib/modulo.pyc', politica=LOCAL)['texto'] == ''


@pytest.mark.parametrize('cfg,esperado', [
    (None, True), ({}, True), ({'modelo': 'llama3.1:8b'}, True), ({'url': 'http://127.0.0.1:11434'}, True),
    ({'host': 'localhost:11434'}, True), ({'url': 'http://[::1]:11434'}, True),
    ({'url': 'http://192.168.1.20:11434'}, False), ({'host': 'servidor.empresa.pe'}, False),
    ({'url': 'http://127.0.0.1@servidor.empresa.pe'}, False), ({'url': 'http://localhost.servidor.pe'}, False),
    ({'url': 'https://ollama.com'}, False), ({'modelo': 'gpt-oss:120b-cloud'}, False), ({'modelo': 'x:CLOUD'}, False),
])
def test_si_el_llm_es_local(tmp_path, monkeypatch, cfg, esperado):
    """077:RF-57 — otro servidor en `ollama.json` o un modelo en la nube no es local."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    if cfg is not None:
        (tmp_path / 'ollama.json').write_text(json.dumps(cfg), encoding='utf-8')
    local, motivo = modulo_ollama.destino_llm()
    assert local is esperado and bool(motivo) is not esperado


@pytest.mark.parametrize('contenido', ['{roto', '[1, 2]', '"texto"'])
def test_configuracion_ilegible_no_abre(tmp_path, monkeypatch, contenido):
    """077:RF-58 — si no se puede leer, no se supone local: `leer_json` lo daría por vacío."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    (tmp_path / 'ollama.json').write_text(contenido, encoding='utf-8')
    assert modulo_ollama.destino_llm()[0] is False


def test_cliente_configurado_no_sale_de_la_maquina(tmp_path, monkeypatch):
    """077:RF-57 — `cliente_configurado` no atiende una dirección de `ollama.json`, y el cliente rechaza otro servidor."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    (tmp_path / 'ollama.json').write_text(json.dumps({'url': 'http://192.168.1.20:11434'}), encoding='utf-8')
    assert modulo_ollama.cliente_configurado().url == modulo_ollama.URL_LOCAL
    with pytest.raises(modulo_ollama.OllamaNoLocal):
        modulo_ollama.ClienteOllama('http://192.168.1.20:11434')


class _SinOllama:
    modelo = 'falso'

    def modelos(self):
        return None


def _pregunta_web(repo, monkeypatch, texto, **k):
    from convertersmartgrid.web import services

    monkeypatch.setattr('convertersmartgrid.asistente.ollama.cliente_configurado', _SinOllama)
    monkeypatch.setattr(services, 'project_root', lambda: repo)
    return services.asistente_pregunta(texto, **k)


def test_web_abre_con_llm_local_y_restringe_si_no(repo, tmp_path, monkeypatch):
    """077:RF-51 / 077:RF-57 — la misma pregunta lee con LLM local; con otro servidor se rechaza y se avisa."""
    r = _pregunta_web(repo, monkeypatch, 'que dice output/informes/resultado.md')
    assert any(c['fuente'] == 'output/informes/resultado.md:1' for c in r['citas'])
    (tmp_path / 'almacen').mkdir(exist_ok=True)
    (tmp_path / 'almacen/ollama.json').write_text(json.dumps({'url': 'http://192.168.1.20:11434'}), encoding='utf-8')
    r = _pregunta_web(repo, monkeypatch, 'que dice output/informes/resultado.md')
    assert not r['citas'] and 'CODIGO-ZX9981' not in json.dumps(r, ensure_ascii=False)
    assert 'lectura restringida' in r['texto'] and '192.168.1.20' in r['texto']


class _WS:
    id = 'esp'


def test_lo_leido_no_sale_a_internet(repo, monkeypatch):
    """077:RF-59 — tras leer un dato, la búsqueda bloquea su código, su nombre y su fichero, también desde otro espacio."""
    from convertersmartgrid.asistente import internet
    from convertersmartgrid.web import asistente_consultas, services

    monkeypatch.setattr(asistente_consultas, '_LEIDOS', set())
    _pregunta_web(repo, monkeypatch, 'que dice otra.md', espacio='otro')
    salidas = []

    def abrir(peticion, _t):
        salidas.append(peticion.full_url)
        raise OSError('sin red en la prueba')

    original = internet.Buscador.__init__
    monkeypatch.setattr(internet.Buscador, '__init__', lambda self, ids=(), **k: original(self, ids, abrir=abrir))
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda _ws: {'alimentadores': [], 'proyecto': [], 'sistema': []})
    for consulta in ('algoritmo CODIGO-ZX9981 reparto', 'empresa Ficticia reparto'):
        r = services.asistente_buscar(_WS(), consulta)
        assert r['bloqueada'] and 'No se buscó' in r['texto']
    assert salidas == []
    services.asistente_buscar(_WS(), 'flujo de potencia radial')
    assert salidas, 'lo técnico en minúsculas sigue saliendo'


def test_lo_leido_de_codigo_no_bloquea(repo, monkeypatch):
    """077:RF-59 — leer código del proyecto no es leer un dato: no se bloquea nada por ello."""
    from convertersmartgrid.web import asistente_consultas

    monkeypatch.setattr(asistente_consultas, '_LEIDOS', set())
    (repo / 'docs/GUIA.md').write_text('# Guía\n\nFlujo de Potencia.\n', encoding='utf-8')
    _pregunta_web(repo, monkeypatch, 'que dice docs/GUIA.md')
    assert asistente_consultas._LEIDOS == set()


def test_sin_camino_a_internet():
    """077:RF-60 — ni las lecturas ni el índice importan nada de red, y `pregunta` no toca el buscador."""
    prohibidos = {'socket', 'urllib', 'requests', 'httpx', 'http', 'aiohttp'}
    for rel in ('asistente/lectura_proyecto.py', 'asistente/corpus_proyecto.py', 'asistente/indice.py'):
        arbol = ast.parse((RAIZ / 'src/convertersmartgrid' / rel).read_text(encoding='utf-8'))
        importados = {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        importados |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        assert not importados & (prohibidos | {'internet'}), rel
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    arbol = ast.parse(fuente)
    funcion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == 'asistente_pregunta')
    cuerpo = ast.get_source_segment(fuente, funcion)
    assert 'Buscador' not in cuerpo and 'internet' not in cuerpo


def _modulo_mcp():
    import importlib.util

    spec = importlib.util.spec_from_file_location('mcp_conversor', RAIZ / 'tools/mcp_conversor.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_mcp_restringido_por_defecto():
    """081:RF-63 / 077:RF-61 / 077:RF-62 — el MCP abre lo local solo con su opción explícita, y su ayuda lo dice."""
    fuente = (RAIZ / 'tools/mcp_conversor.py').read_text(encoding='utf-8')
    assert 'politica_local(texto_pdf) if args.datos_locales else RESTRINGIDA' in fuente
    r = subprocess.run([sys.executable, str(RAIZ / 'tools/mcp_conversor.py'), '--help'], capture_output=True, encoding='utf-8', check=False, timeout=60)
    assert r.returncode == 0 and '--datos-locales' in r.stdout
    doc = (RAIZ / 'docs/MCP_CONVERSOR.md').read_text(encoding='utf-8')
    assert '--datos-locales' in doc and 'nube' in doc
    assert _modulo_mcp().SIN_PAQUETE == 3


def test_politica_no_es_un_argumento_del_modelo(repo):
    """077:RF-61 — ni el LLM ni un cliente MCP pueden pedir la política abierta."""
    lector = LecturaGobernada(repo, registrar=lambda _f: None)
    with pytest.raises(lp.ArgumentoInvalido):
        lector.ejecutar('leer_fichero', {'ruta': 'otra.md', 'politica': LOCAL})
    with pytest.raises(lp.ArgumentoInvalido):
        lector.ejecutar('leer_fichero', {'ruta': 'otra.md', 'datos_locales': True})
    with pytest.raises(lp.RutaRechazada):
        lector.ejecutar('leer_fichero', {'ruta': 'output/informes/resultado.md'})


def test_excel_por_su_lector(repo):
    """077:RF-63 — un libro se lee por hojas y filas, no como bytes."""
    import openpyxl

    libro = openpyxl.Workbook()
    libro.active.title = 'Primera'
    libro.active.append(['Codigo', 'Valor'])
    libro.active.append(['ZX9981', 12.5])
    libro.create_sheet('Segunda').append(['otra hoja'])
    libro.save(repo / 'input/libro.xlsx')
    r = lp.leer_fichero(repo, 'input/libro.xlsx', politica=LOCAL)
    assert r['hojas'] == ['Primera', 'Segunda'] and r['formato'] == 'excel'
    assert 'Codigo | Valor' in r['texto'] and 'ZX9981 | 12.5' in r['texto'] and r['total_lineas'] == 2
    assert 'otra hoja' in lp.leer_fichero(repo, 'input/libro.xlsx', hoja='Segunda', politica=LOCAL)['texto']
    with pytest.raises(lp.ArgumentoInvalido, match='Primera'):
        lp.leer_fichero(repo, 'input/libro.xlsx', hoja='No hay', politica=LOCAL)


def test_pdf_por_su_lector(repo):
    """077:RF-64 — un PDF va por el lector del proyecto; uno ilegible dice por qué, sin bytes."""
    (repo / 'input/carta.pdf').write_bytes(b'%PDF-falso')
    bueno = lp.Politica(True, lector_pdf=lambda _p: ('Primera linea\nSegunda linea', 1, 'texto', []))
    r = lp.leer_fichero(repo, 'input/carta.pdf', 2, politica=bueno)
    assert r['texto'] == 'Segunda linea' and r['formato'] == 'pdf' and r['metodo'] == 'texto'

    def roto(_p):
        raise ValueError('sin cabecera')

    r = lp.leer_fichero(repo, 'input/carta.pdf', politica=lp.Politica(True, lector_pdf=roto))
    assert r['texto'] == '' and 'sin cabecera' in r['indicacion']
    assert lp.leer_fichero(repo, 'input/carta.pdf', politica=LOCAL)['texto'] == ''


@pytest.mark.parametrize('nombre,marca', [('base.mdb', 'POST /api/workspaces'), ('copia.bak', 'lector'), ('pesos.safetensors', 'lector'), ('raro.dat', 'lector')])
def test_binarios_dicen_que_hacer(repo, nombre, marca):
    """077:RF-65 — Access y otros binarios no devuelven basura: dicen qué ruta usar."""
    (repo / 'input' / nombre).write_bytes(b'\x00\x01\x02Standard Jet DB\x00' * 50)
    r = lp.leer_fichero(repo, f'input/{nombre}', politica=LOCAL)
    assert r['texto'] == '' and marca in r['indicacion'] and 'Jet' not in r['indicacion']


def test_binario_nombrado_en_la_pregunta(repo, monkeypatch):
    """077:RF-65 — en la web, el operador recibe la indicación y no un «No lo sé» sin más."""
    (repo / 'input/base.mdb').write_bytes(b'\x00\x01Jet')
    r = _pregunta_web(repo, monkeypatch, 'que trae input/base.mdb')
    assert 'POST /api/workspaces' in r['texto'] and not r['citas']


def test_datos_locales_no_se_indexan(repo, raiz_datos):
    """077:RF-66 — nada de `output/`, `input/`, `config/` ni de las raíces entra en el índice."""
    rels = {f.fuente.rsplit(':', 1)[0] for f in indice.fragmentos(repo, indice.CORPUS_AMPLIADO)}
    assert not [r for r in rels if r.startswith(('output/', 'input/', 'config/', '.agents/', '.cursor/', 'maestro_real/'))]
    assert not [r for r in rels if raiz_datos.as_posix() in r]
    assert all(lp.motivo_de_rechazo(p.relative_to(RAIZ).as_posix()) is None for p in corpus_proyecto.ficheros_extra(RAIZ))
    assert not any(lp.excluido_siempre(f.fuente.rsplit(':', 1)[0]) for f in indice.fragmentos(RAIZ, indice.CORPUS_AMPLIADO))


def test_busqueda_con_topes_y_lo_dice(repo, raiz_datos, monkeypatch):
    """077:RF-67 — corta por resultados y por tiempo, y lo dice; dentro de una raíz solo con esa raíz."""
    politica = lp.politica_local()
    (repo / 'input/muchos.txt').write_text('\n'.join(f'{DATO} {i}' for i in range(100)), encoding='utf-8')
    r = lp.buscar_texto(repo, 'CODIGO-ZX9981', tope=3, politica=politica)
    assert len(r['coincidencias']) == 3 and r['cortada'] == 'resultados' and '3 resultados' in r['aviso']
    dentro = lp.buscar_texto(repo, 'CODIGO-ZX9981', dentro=raiz_datos.as_posix(), politica=politica)
    assert {c['ruta'].rsplit('/', 1)[-1] for c in dentro['coincidencias']} == {'RED_(1).txt'} and dentro['cortada'] is None
    monkeypatch.setattr(lp, 'TOPE_SEGUNDOS_BUSQUEDA', 0.0)
    r = lp.buscar_texto(repo, 'CODIGO-ZX9981', politica=politica)
    assert r['cortada'] == 'tiempo' and r['truncado'] and 'cortada' in r['aviso']


def test_fichero_grande_sin_cargarlo(repo, monkeypatch):
    """077:RF-68 — un rango de un fichero mayor que el tope sale sin leerlo entero en memoria."""
    (repo / 'input/grande.txt').write_text('\n'.join(f'fila {i}' for i in range(5000)), encoding='utf-8')
    monkeypatch.setattr(lp, 'TOPE_TAMANO', 100)
    original = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda self: pytest.fail(f'cargó entero {self}') if self.name == 'grande.txt' else original(self))
    r = lp.leer_fichero(repo, 'input/grande.txt', 11, 13, politica=LOCAL)
    assert r['texto'].splitlines() == ['fila 10', 'fila 11', 'fila 12'] and not r['truncado'] and r['total_lineas'] is None


def test_texto_ansi(repo):
    """077:RF-68 — un TXT en ANSI, como los de un exportador, se lee con sus tildes."""
    (repo / 'input/ansi.txt').write_bytes('Descripción de la línea\n'.encode('cp1252'))
    r = lp.leer_fichero(repo, 'input/ansi.txt', politica=LOCAL)
    assert r['texto'] == 'Descripción de la línea' and r['codificacion'] == 'cp1252'
