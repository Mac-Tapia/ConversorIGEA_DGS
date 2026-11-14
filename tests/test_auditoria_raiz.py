"""Spec 036: instalación consistente, fallo real del lanzador e inventario de la raíz."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

import pytest
from packaging.requirements import Requirement

from convertersmartgrid.web.runtime import missing_dependencies

RAIZ = Path(__file__).resolve().parents[1]


def _nombres(declaraciones):
    return {Requirement(linea).name.lower().replace('_', '-') for linea in declaraciones
            if linea.strip() and not linea.lstrip().startswith(('#', '-'))}


def test_la_instalacion_conserva_la_vigilancia_de_memoria():
    """036:RF-1 — la instalación documentada y ambos extras web instalan el vigilante."""
    requisitos = _nombres((RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines())
    extras = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    assert 'psutil' in requisitos
    assert all('psutil' in _nombres(extras[grupo]) for grupo in ('web', 'all'))


def test_el_arranque_detecta_que_falta_el_vigilante():
    """036:RF-1 — faltar psutil obliga al lanzador a preparar el entorno, no a degradarlo."""
    def importar(nombre):
        if nombre == 'psutil':
            raise ModuleNotFoundError(nombre)
        return object()

    assert missing_dependencies(importar) == ('psutil',)


def test_el_corpus_pdf_tiene_su_dependencia_declarada():
    """036:RF-2 — el extractor que usa PdfReader se puede instalar desde el contrato."""
    requisitos = _nombres((RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines())
    extras = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    assert 'pypdf' in requisitos
    assert all('pypdf' in _nombres(extras[grupo]) for grupo in ('pide', 'all'))


def _pdf_con_texto(texto):
    """PDF mínimo con su tabla de referencias correcta: pypdf no sabe escribir texto."""
    contenido = f'BT /F1 12 Tf 10 50 Td ({texto}) Tj ET'.encode('ascii')
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 100] /Contents 4 0 R '
        b'/Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(contenido), contenido),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    salida = bytearray(b'%PDF-1.4\n')
    posiciones = []
    for numero, objeto in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b'%d 0 obj\n%s\nendobj\n' % (numero, objeto)
    inicio = len(salida)
    salida += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objetos) + 1)
    salida += b''.join(b'%010d 00000 n \n' % pos for pos in posiciones)
    salida += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objetos) + 1, inicio)
    return bytes(salida)


def test_el_extractor_del_corpus_saca_el_texto_de_un_pdf(tmp_path):
    """036:RF-2 — el extractor real devuelve el texto localizado, no solo el número de páginas.

    La prueba de `test_pide_dataset` usa una página en blanco: habría pasado igual con un
    lector que no sacase ninguna palabra (auditoría del arranque, 2026-11-02).
    """
    from convertersmartgrid.pide_dataset import cargar_contrato, extraer_archivo, inventariar

    raiz = tmp_path / 'corpus'
    raiz.mkdir()
    (raiz / 'informe.pdf').write_bytes(_pdf_con_texto('Maxima demanda del sistema'))
    contrato = cargar_contrato(RAIZ / 'config' / 'pide_universal_2017.json')
    extraido = extraer_archivo(inventariar(raiz, 'EMPRESA DEMO', contrato)[0], raiz, max_chars=200)
    assert extraido.status == 'ok'
    assert extraido.assets[0]['pages'] == 1
    assert [(f['location'], f['text']) for f in extraido.fragments] == [
        ('page:1', 'Maxima demanda del sistema')]


#: Comprobador falso que da el entorno por bueno y pide compilar el front.
RUNTIME_PIDE_COMPILAR = 'import sys\nraise SystemExit(1 if "--front" in sys.argv else 0)\n'


def _lanzar_aislado(tmp_path, fallo, *, runtime=RUNTIME_PIDE_COMPILAR, con_npm=True, con_paquetes=True):
    """Ejecuta cmd.exe y el batch real; los servicios externos quedan fuera del ensayo."""
    shutil.copyfile(RAIZ / 'run_gui.bat', tmp_path / 'run_gui.bat')
    entorno = tmp_path / '.venv'
    scripts = entorno / 'Scripts'
    scripts.mkdir(parents=True)
    # El launcher CPython de Windows usa el home real indicado por pyvenv.cfg.
    shutil.copyfile(sys.executable, scripts / 'python.exe')
    shutil.copyfile(Path(sys.prefix) / 'pyvenv.cfg', entorno / 'pyvenv.cfg')
    paquete = tmp_path / 'src' / 'convertersmartgrid' / 'web'
    paquete.mkdir(parents=True)
    (paquete.parent / '__init__.py').write_text('', encoding='ascii')
    (paquete / '__init__.py').write_text('', encoding='ascii')
    (paquete / 'runtime.py').write_text(runtime, encoding='ascii')
    (paquete / '__main__.py').write_text(
        'from pathlib import Path\nPath("servidor_iniciado").write_text("iniciado")\n', encoding='ascii')
    front = tmp_path / 'frontend'
    (front / 'dist').mkdir(parents=True)
    (front / 'dist' / 'index.html').write_text('compilacion anterior', encoding='ascii')
    if con_paquetes:
        (front / 'node_modules').mkdir()
    if con_npm:
        (scripts / 'npm.cmd').write_text(
            '@echo off\n'
            'echo %1>>"%~dp0npm_calls.txt"\n'
            f'if "%1"=="{fallo}" exit /b 23\n'
            'exit /b 0\n', encoding='ascii')
    # Sin npm solo queda lo imprescindible de Windows: el npm de la máquina respondería.
    resto = os.environ['PATH'] if con_npm else str(Path(os.environ['SystemRoot']) / 'System32')
    env = {**os.environ, 'PATH': str(scripts) + os.pathsep + resto, 'PYTHONDONTWRITEBYTECODE': '1'}
    resultado = subprocess.run(
        [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', r'.\run_gui.bat'],
        cwd=tmp_path, env=env, input='\n', text=True, capture_output=True, timeout=60)
    registro = scripts / 'npm_calls.txt'
    llamadas = registro.read_text(encoding='ascii').splitlines() if registro.exists() else []
    return resultado, llamadas


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_un_fallo_de_npm_no_abre_una_interfaz_anterior(tmp_path):
    """036:RF-3; 065:RF-8 — el batch real no inicia servidor si falla la compilación."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'run')
    assert llamadas == ['run'], resultado.stdout + resultado.stderr
    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert not (tmp_path / 'servidor_iniciado').exists()
    # Sin el motivo, el operador solo ve una ventana que se cierra (la segunda mitad de RF-3).
    assert 'No se abre una compilacion anterior' in resultado.stdout


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_sin_paquetes_del_front_no_los_instala_al_arrancar(tmp_path):
    """086:RF-39; 036:RF-3 — arrancar no ejecuta «npm ci»: dice que falta, y no abre una interfaz anterior."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'ninguno', con_paquetes=False)
    assert llamadas == [], resultado.stdout + resultado.stderr
    assert resultado.returncode != 0
    assert 'npm ci' in resultado.stdout
    assert not (tmp_path / 'servidor_iniciado').exists()


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_sin_npm_el_lanzador_dice_que_falta_y_no_abre(tmp_path):
    """036:RF-3 — no poder instalar porque falta Node.js es el mismo fallo, con su motivo."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'ninguno', con_npm=False)
    assert llamadas == []
    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert not (tmp_path / 'servidor_iniciado').exists()
    assert 'no se encuentra Node.js' in resultado.stdout


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_sin_el_vigilante_no_arranca_una_web_degradada(tmp_path):
    """036:RF-1; 086:RF-39 — si el comprobador dice que falta psutil, no se instala ni se inicia el servidor: lo dice."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'ninguno', runtime='raise SystemExit(1)\n')
    assert llamadas == []
    assert resultado.returncode == 1, resultado.stdout + resultado.stderr
    assert not (tmp_path / 'servidor_iniciado').exists()
    assert 'Este lanzador no instala nada' in resultado.stdout


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_el_lanzador_sigue_abriendo_tras_npm_correcto(tmp_path):
    """036:RF-3 — controlar el error no bloquea el camino que compila correctamente."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'ninguno')
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert llamadas == ['run']
    assert (tmp_path / 'servidor_iniciado').is_file()


# --------------------------------------------------- inventario y documentos (T4)

INFORME = RAIZ / 'docs' / 'AUDITORIA_RAIZ_2026-11-03.md'
DOCUMENTOS_VIVOS = ('README.md', 'VNR-GIS.md', 'CODIGO_FUENTE.md', 'docs/ARQUITECTURA.md',
                    'docs/MANUAL_DE_USO.md', 'docs/MANUAL_COMANDOS.md', 'docs/constitution.md',
                    '.claude/skills/convertersmartgrid-backend/SKILL.md')


def test_el_informe_cubre_cada_carpeta_versionada():
    """036 T4 — una carpeta de la raíz que entra en git entra en el inventario."""
    versionadas = {p.parts[0] for p in map(Path, subprocess.run(
        ['git', 'ls-files'], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout.splitlines()) if len(p.parts) > 1}
    filas = set(re.findall(r'^\| `([^`/]+)/` \|', INFORME.read_text(encoding='utf-8'), re.M))
    assert versionadas <= filas, f'Carpetas de la raíz fuera del informe: {sorted(versionadas - filas)}'


@pytest.mark.parametrize('documento', (*DOCUMENTOS_VIVOS, 'docs/AUDITORIA_RAIZ_2026-11-03.md'))
def test_los_enlaces_locales_de_los_documentos_existen(documento):
    """036 T4 — los enlaces relativos de los documentos vivos llevan a un fichero real."""
    ruta = RAIZ / documento
    enlaces = re.findall(r'\]\(([^)\s]+)', ruta.read_text(encoding='utf-8'))
    locales = {e.split('#')[0] for e in enlaces if not e.startswith(('http', '#', 'mailto'))}
    rotos = sorted(e for e in locales if e and not (ruta.parent / e).exists())
    assert not rotos, f'{documento}: {rotos}'


@pytest.mark.parametrize('documento', DOCUMENTOS_VIVOS)
def test_ningun_documento_manda_a_la_carpeta_de_datos_retirada(documento):
    """036 T4 — los datos salieron del proyecto el 2026-11-02: ninguna orden los busca dentro."""
    texto = (RAIZ / documento).read_text(encoding='utf-8')
    assert not re.search(r'(?<![\w_])referencia[\\/]', texto), documento


def test_el_manual_explica_el_verificador_de_arquitectura():
    """036 T4 — los tres comprobadores de la arquitectura se encuentran desde el manual."""
    manual = (RAIZ / 'docs' / 'MANUAL_COMANDOS.md').read_text(encoding='utf-8')
    for herramienta in ('tools/arquitectura.py', 'verify_architecture_links.py',
                        'verify_interactive_architecture.mjs'):
        assert herramienta in manual


def test_una_spec_cumplida_no_cita_un_documento_que_no_existe():
    """036 T4 — el plan de esta spec citaba un informe que nunca llegó a confirmarse."""
    sys.path.insert(0, str(RAIZ / 'tools'))
    try:
        import estado_specs
    finally:
        sys.path.pop(0)
    rotos = []
    for spec in estado_specs.leer_specs(RAIZ):
        if spec.estado != 'cumplida':
            continue
        for fichero in ('spec.md', 'plan.md', 'tasks.md'):
            ruta = spec.carpeta / fichero
            citas = re.findall(r'`(docs/[\w./-]+\.(?:md|json))`',
                               ruta.read_text(encoding='utf-8') if ruta.is_file() else '')
            rotos += [f'{spec.numero}/{fichero}: {c}' for c in citas if not (RAIZ / c).is_file()]
    assert not rotos, rotos


# --------------------------------------------------- ningún conjunto de evaluación en lo que lo juzga (097:RF-20)
# Caso real (D077, 2026-11-13): 231 de las 308 preguntas de la calibración de la abstención del 077 estaban literales en
# `docs/PREGUNTAS_MAESTRO_076.md`, que el corpus 077 indexaba; ninguna prueba miraba qué textos del corpus son examen. El
# usuario decidió (opción A) que el documento se queda en el corpus (076 T8): la calibración sale de otras preguntas.

CONJUNTO_076 = 'docs/asistente/preguntas_entregables.jsonl'
#: El reparto «corpus» de la 076 es corpus por decisión del usuario (076:RF-29): lo que examina al 077 es el «sellado».
SELLADO_076 = (CONJUNTO_076, 'sellado')


@pytest.fixture(scope='module')
def frags_de_los_corpus(tmp_path_factory):
    """Los trozos de los dos corpus del asistente, una vez por módulo y sin tocar la carpeta de la web."""
    from convertersmartgrid.asistente import indice

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('CSG_ASISTENTE_DATA', str(tmp_path_factory.mktemp('asistente')))
        yield {c: indice.fragmentos(RAIZ, c) for c in (indice.CORPUS_047, indice.CORPUS_AMPLIADO)}


@pytest.mark.parametrize('corpus', ['047', '077'])
def test_ninguna_pregunta_de_evaluacion_literal_en_el_corpus_que_la_mide(frags_de_los_corpus, corpus):
    """097:RF-20 — ni la calibración ni el sellado de la 047, la 076/077 y el operador (097:RF-16) están en los trozos del
    corpus que los mide, salvo en el fichero que la pregunta cita como su fuente; en el 077, con el documento del maestro
    dentro (076:RF-29). Con la calibración formada del reparto entero, 374 fugas en el 077 (2026-11-13)."""
    from convertersmartgrid.asistente import fuga_evaluacion as fe

    textos = fe.textos_por_fichero(frags_de_los_corpus[corpus])
    maestro = 'docs/PREGUNTAS_MAESTRO_076.md'
    assert (maestro in textos) is (corpus == '077'), 'el documento del maestro va al 077 y no al 047 (076:RF-29, RF-34)'
    # El JSONL de la 076 lo nombra la prueba y no `src/` (076:RF-16); de él, solo el reparto que examina.
    otros = (SELLADO_076,) if corpus == '077' else ()
    r = fe.fugas_del_corpus(RAIZ, corpus, frags_de_los_corpus[corpus], otros)
    assert r['conjuntos'] == [*fe.CONJUNTOS_RAG[corpus], *(f'{a}#{b}' for a, b in otros)],         'falta un conjunto: la prueba no puede pasar sin mirarlo'
    assert r['comprobadas'] > 100
    assert not r['fugas'], f"{len(r['fugas'])} preguntas de evaluación en el corpus {corpus}, p. ej. {r['fugas'][:5]}"


def test_todo_conjunto_de_evaluacion_del_repositorio_se_comprueba():
    """097:RF-20 — un conjunto nuevo de `docs/` con preguntas no queda sin comprobar por olvido."""
    import json

    from convertersmartgrid.asistente import fuga_evaluacion as fe

    vistos = {r for rs in fe.CONJUNTOS_RAG.values() for r in rs}
    for p in sorted(p for patron in ('RAG_*.json', 'CONJUNTO_*.json') for p in (RAIZ / 'docs').glob(patron)):
        datos = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(datos, dict) and (datos.get('preguntas') or 'calibracion' in datos):
            assert p.relative_to(RAIZ).as_posix() in vistos, p.name
    assert (RAIZ / CONJUNTO_076).is_file()
