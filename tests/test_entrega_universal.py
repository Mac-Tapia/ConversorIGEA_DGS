"""Spec 086, F4: lo universal de la 1.0: moneda y bandas del perfil, plantilla neutra, perfiles entregados y qué se entrega.

Ningún nombre real se escribe aquí: los términos salen del perfil excluido o de la lista de huellas. Sin lista local las
pruebas corren igual: la lista mínima va en git, y nada se omite (la suite no acepta omitidas).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient

from apoyo import cargar_herramienta
from test_informe_docx import _estudio, _factibilidad, _texto
from test_informe_web import _espacio, client  # noqa: F401
from synthetic_export import ExportSpec, write_export

from convertersmartgrid.catalog import auditar, construir_hojas
from convertersmartgrid.cli import main as cli_main
from convertersmartgrid.informe_docx import escribir_informe_estudio, escribir_informe_factibilidad
from convertersmartgrid.informes import ConfigInforme, InformeError
from convertersmartgrid.libro_informe import comprobar_libro
from convertersmartgrid.mapa_informe import imagenes_del_estado
from convertersmartgrid.perfil_empresa import cargar_perfil, datos_perfil, moneda_informes, perfil_con_nombre, perfiles_disponibles
from convertersmartgrid.perfil_esquema import claves_del_esquema, validar_perfil
from convertersmartgrid.web.app import create_app

CE = cargar_herramienta('comprobar_entrega.py')
RAIZ = CE.RAIZ
LIMITES = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}


def _perfil_excluido(sufijo: str = '.json') -> Path:
    """El perfil de la empresa de prueba, sin escribir su nombre: el que está en el repositorio y no se entrega."""
    manifiesto = CE.leer_manifiesto()
    return next(r for r in sorted((RAIZ / 'config' / 'perfiles').glob('*.json'))
                if not CE.entra(f'config/perfiles/{r.name}', manifiesto)
                and r.name.endswith('.estructura.json') == (sufijo == '.estructura.json'))


def _config(tmp_path: Path, **informes) -> ConfigInforme:
    """Un perfil sin modelo: lo que trae una empresa que estrena el conversor."""
    return ConfigInforme.de_perfil({'estudios': LIMITES, 'informes': informes}, tmp_path)


@pytest.fixture(scope='module')
def manifiesto():
    return CE.leer_manifiesto()


@pytest.fixture(scope='module')
def informe_repositorio(manifiesto):
    return CE.comprobar(RAIZ, manifiesto, CE.cargar_terminos(RAIZ, manifiesto))


# --------------------------------------------------------------------------- RF-28
def test_informe_con_la_moneda_del_perfil(tmp_path):
    """086:RF-28 — el rótulo de las pérdidas valoradas es la moneda del perfil, no una fija."""
    config = _config(tmp_path, moneda='Bs.')
    destino = tmp_path / 'f.docx'
    escribir_informe_factibilidad(config, destino, _factibilidad(tmp_path))
    texto = _texto(destino)
    assert 'no reconocida (Bs.)' in texto and 'S/.' not in texto


def test_sin_moneda_el_informe_no_supone_ninguna(tmp_path):
    """086:RF-28 — sin moneda en el perfil, el rótulo lo dice sin escribir la de otra empresa."""
    destino = tmp_path / 'f.docx'
    escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path))
    texto = _texto(destino)
    assert 'moneda de la empresa' in texto and 'S/.' not in texto


def test_contexto_de_la_web_trae_la_moneda(client, tmp_path, monkeypatch):  # noqa: F811
    """086:RF-28 — la pantalla de informes toma la moneda del servidor."""
    perfil = tmp_path / 'p.json'
    perfil.write_text(json.dumps({'informes': {'moneda': 'Bs.'}}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    wid, _ = _espacio(client, tmp_path)
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    assert ctx['moneda'] == 'Bs.'


def test_moneda_del_perfil_validada():
    """086:RF-28 — un texto corto; otro tipo es un error del perfil, y sin ella nada se supone."""
    assert moneda_informes({'informes': {'moneda': 'S/.'}}) == 'S/.'
    assert moneda_informes({}) is None
    with pytest.raises(ValueError, match='informes.moneda'):
        moneda_informes({'informes': {'moneda': 3}})


def test_ninguna_moneda_fija_en_el_codigo(manifiesto):
    """086:RF-28 — fuera de comentarios no queda ningún símbolo de moneda de una empresa."""
    sol = re.compile(r'S/\.')
    malos = []
    for ruta, rel in CE.ficheros_de_la_entrega(RAIZ, manifiesto):
        if ruta.suffix.lower() not in ('.py', '.ts', '.tsx'):
            continue
        texto = ruta.read_text(encoding='utf-8', errors='replace')
        malos += [f'{rel}:{n}' for n, linea in enumerate(CE.lineas_de_codigo(rel, texto), 1) if sol.search(linea)]
    assert not malos, malos


def test_libro_no_escribe_la_moneda_en_sus_avisos():
    """086:RF-28 — el aviso del libro compara cifras: no necesita una unidad fija."""
    fuente = (RAIZ / 'src' / 'convertersmartgrid' / 'libro_informe.py').read_text(encoding='utf-8')
    assert 'S/.' not in fuente.split('def conclusiones_del_word')[0].split('TOLERANCIA_SOLES = ')[1]
    assert comprobar_libro is not None


# --------------------------------------------------------------------------- RF-29
def test_web_sin_nombres_de_empresa(informe_repositorio):
    """086:RF-29 — ni en los textos ni en los ejemplos de la web hay un nombre de una lista de términos."""
    malos = [f'{h.ruta}:{h.linea}' for h in informe_repositorio.en_codigo if h.ruta.startswith('frontend/')]
    assert not malos, malos


def test_web_sin_tensiones_de_una_empresa():
    """086:RF-29 — las etiquetas dicen «alta» y «media», no los niveles de una red concreta."""
    fijas = re.compile(r'(?<![\d.,])(?:22,9|13,2|60 ?kV|10 ?kV|33 ?kV|138 ?kV|220 ?kV)')
    malos = []
    for ruta in sorted((RAIZ / 'frontend' / 'src').rglob('*.ts*')):
        rel = ruta.relative_to(RAIZ).as_posix()
        texto = ruta.read_text(encoding='utf-8')
        malos += [f'{rel}:{n}' for n, linea in enumerate(CE.lineas_de_codigo(rel, texto), 1) if fijas.search(linea)]
    assert not malos, malos


def test_nucleo_y_web_sin_terminos_en_el_codigo(informe_repositorio):
    """086:RF-29 — el núcleo y la web no llevan ningún término fuera de los comentarios que neutraliza D5."""
    malos = [f'{h.ruta}:{h.linea} ({h.categoria})' for h in informe_repositorio.en_codigo]
    assert not malos, malos
    assert informe_repositorio.ficheros > 100, 'la comprobación recorrió de verdad la entrega'


# --------------------------------------------------------------------------- RF-30
def test_perfil_incompleto_dice_que_falta_y_que_funcion_afecta():
    """086:RF-30 — cada clave ausente con la función que afecta y qué hace el programa sin ella."""
    r = validar_perfil({'crs_origen': 'EPSG:32719'})
    assert r.errores == []
    por_clave = {f.clave: f for f in r.faltan}
    assert 'crs_origen' not in por_clave
    falta = por_clave['informes.moneda']
    assert falta.funcion and falta.si_falta
    assert por_clave['informes.bandas_tension_pct'].funcion
    assert por_clave['estudios.tension_min_pu'].origen == 'norma'
    assert por_clave['patron_sed_medicion'].origen == 'empresa'


def test_perfil_con_un_valor_imposible_es_un_error():
    """086:RF-30 — un tipo, una expresión o un rango mal se nombra con su clave."""
    r = validar_perfil({'crs_origen': 5, 'patron_sed_medicion': '(', 'estudios': {'tension_min_pu': 'bajo'},
                        'informes': {'bandas_tension_pct': [105, 95]}})
    claves = ' '.join(r.errores)
    for c in ('crs_origen', 'patron_sed_medicion', 'estudios.tension_min_pu', 'bandas_tension_pct'):
        assert c in claves


def test_clave_desconocida_se_avisa_sin_bloquear():
    """086:RF-30 — una errata se ve; el perfil se sigue pudiendo usar."""
    r = validar_perfil({'crs_orgen': 'EPSG:32719', '_comentario': 'x'})
    assert r.errores == [] and r.desconocidas == ['crs_orgen']


def test_el_esquema_cubre_todas_las_claves_de_un_perfil_real():
    """086:RF-30 — sin esto, una clave nueva quedaría sin validar ni documentar."""
    datos = json.loads(_perfil_excluido().read_text(encoding='utf-8'))
    r = validar_perfil(datos)
    assert r.errores == [] and r.desconocidas == []


def test_la_guia_explica_cada_clave_del_esquema():
    """086:RF-30 — la guía no se separa del esquema."""
    guia = (RAIZ / 'docs' / 'PERFIL_EMPRESA.md').read_text(encoding='utf-8')
    faltan = [c for c in claves_del_esquema() if f'`{c}`' not in guia]
    assert not faltan, faltan


def test_orden_validar_perfil(tmp_path, capsys):
    """086:RF-30 — la orden dice qué falta, sale con 0 sin bloquear, y con 1 ante un valor imposible."""
    bueno = tmp_path / 'bueno.json'
    bueno.write_text(json.dumps({'crs_origen': 'EPSG:32719'}), encoding='utf-8')
    assert cli_main(['validar-perfil', '--ruta', str(bueno)]) == 0
    salida = capsys.readouterr().out
    assert 'informes.moneda' in salida and 'Función afectada' in salida
    malo = tmp_path / 'malo.json'
    malo.write_text(json.dumps({'crs_origen': 5}), encoding='utf-8')
    assert cli_main(['validar-perfil', '--ruta', str(malo)]) == 1
    assert 'crs_origen' in capsys.readouterr().out


def test_orden_validar_perfil_sin_perfil(tmp_path, capsys, monkeypatch):
    """086:RF-30 — sin perfil no es un error: nada bloquea; dice qué decidiría la empresa."""
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'no_esta.json'))
    assert cli_main(['validar-perfil']) == 0
    assert 'crs_origen' in capsys.readouterr().out


def test_validar_no_cambia_lo_que_ya_se_puede_usar(tmp_path):
    """086:RF-30 — validar es solo una lectura: un perfil vacío sigue cargando como «sin perfil»."""
    (tmp_path / 'vacio.json').write_text('{}', encoding='utf-8')
    assert cargar_perfil(tmp_path / 'vacio.json').crs_origen is None
    assert validar_perfil({}).errores == []


# --------------------------------------------------------------------------- RF-31
@pytest.mark.parametrize('tipo', ['estudio', 'factibilidad'])
def test_sin_modelo_sale_con_la_plantilla_neutra_y_lo_dice(tmp_path, tipo):
    """086:RF-31 — sin modelo de la empresa hay informe, con plantilla neutra, y el resumen lo dice."""
    config = _config(tmp_path)
    assert config.faltan(tipo) == []
    assert config.modelo(tipo) is None
    destino = tmp_path / f'{tipo}.docx'
    if tipo == 'estudio':
        escribir_informe_estudio(config, destino, _estudio(tmp_path))
    else:
        escribir_informe_factibilidad(config, destino, _factibilidad(tmp_path))
    resumen = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    assert resumen['plantilla'] == 'neutra'
    assert any('plantilla neutra' in a for a in resumen['avisos_perfil'])
    d = docx.Document(destino)
    assert d.core_properties.author != 'python-docx'
    assert 'GT-' in d.sections[0].header.tables[0].cell(0, 0).text, 'el número va en la cabecera neutra'


def test_con_modelo_no_cambia_nada(tmp_path):
    """086:RF-31 — con modelo de la empresa, se sigue usando y no se avisa de plantilla."""
    from test_informe_docx import _config as con_modelo

    destino = tmp_path / 'e.docx'
    escribir_informe_estudio(con_modelo(tmp_path), destino, _estudio(tmp_path))
    resumen = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    assert resumen['plantilla'] == 'estudio.docx' and resumen['avisos_perfil'] == []


def test_modelo_declarado_que_no_existe_sigue_siendo_un_error(tmp_path):
    """086:RF-31 — la neutra es para quien no trae modelo; una ruta errada se dice para corregirla."""
    config = _config(tmp_path, modelo_estudio='no_esta.docx')
    with pytest.raises(InformeError, match='No existe el modelo'):
        config.modelo('estudio')


def test_el_contexto_avisa_antes_de_generar(client, tmp_path, monkeypatch):  # noqa: F811
    """086:RF-31 — el operador lo ve en la pantalla, antes de generar, y puede generar."""
    perfil = tmp_path / 'sin_modelo.json'
    perfil.write_text(json.dumps({}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    wid, _ = _espacio(client, tmp_path)
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    assert ctx['plantilla_neutra'] == {'estudio': True, 'factibilidad': True}
    assert ctx['faltan'] == {'estudio': [], 'factibilidad': []}


# --------------------------------------------------------------------------- RF-32
def test_lo_entregado_son_la_plantilla_y_la_ficticia(manifiesto):
    """086:RF-32 — el perfil de la empresa de prueba sigue en el repositorio, fuera del paquete."""
    entregados = {r.name for r, _ in CE.ficheros_de_la_entrega(RAIZ, manifiesto) if r.parent.name == 'perfiles'}
    assert entregados == {'plantilla.json', 'ficticia.json'}
    assert _perfil_excluido().stem in perfiles_disponibles(), 'en el repositorio sigue, para sus pruebas'


def test_plantilla_sin_ninguna_convencion():
    """086:RF-32 — la plantilla no supone nada: cargarla es como no tener perfil."""
    p = perfil_con_nombre('plantilla')
    assert (p.crs_origen, p.patron_sed_medicion, p.escala_diagrama, p.forma_alimentador) == (None,) * 4
    datos = json.loads((RAIZ / 'config' / 'perfiles' / 'plantilla.json').read_text(encoding='utf-8'))
    r = validar_perfil(datos)
    assert r.errores == [] and r.desconocidas == []


def test_ficticia_valida_y_completa_en_lo_que_usa_un_informe():
    """086:RF-32 — el ficticio se valida sin errores y da moneda, bandas y límites."""
    datos = json.loads((RAIZ / 'config' / 'perfiles' / 'ficticia.json').read_text(encoding='utf-8'))
    r = validar_perfil(datos)
    assert r.errores == [] and r.desconocidas == []
    assert moneda_informes(datos) and datos['crs_origen'] and datos['informes']['bandas_tension_pct']


def _solo_entregados(tmp_path: Path) -> Path:
    """La carpeta de perfiles como en un paquete: sin el de la empresa de prueba."""
    carpeta = tmp_path / 'perfiles'
    carpeta.mkdir()
    for nombre in ('plantilla.json', 'ficticia.json'):
        shutil.copy(RAIZ / 'config' / 'perfiles' / nombre, carpeta / nombre)
    return carpeta


def test_ficticia_convierte_e_informa_sin_modelos_de_empresa(tmp_path, monkeypatch):
    """086:RF-31, 086:RF-32 — de punta a punta sin DIgSILENT: se convierte y sale un informe, solo con el perfil."""
    carpeta = _solo_entregados(tmp_path)
    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text('{"perfil": "ficticia"}', encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(activo))
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.carpeta_perfiles', lambda: carpeta)

    red, cargas, equipos = write_export(ExportSpec(seed=86), tmp_path / 'txt')
    salida = tmp_path / 'salida'
    rc = cli_main(['convert', '--red', str(red), '--loads', str(cargas), '--equipment', str(equipos), '--all',
                   '--out-dir', str(salida), '--no-geography', '--perfil', 'ficticia', '--workers', '1'])
    assert rc == 0
    dgs = sorted(salida.rglob('*.dgs'))
    assert dgs, 'la conversión dejó sus DGS'
    terminos = CE.cargar_terminos(RAIZ, CE.leer_manifiesto())
    assert not CE.buscar_en_texto(dgs[0].name, dgs[0].read_text(encoding='utf-8', errors='replace'), terminos)

    config = ConfigInforme.de_perfil(datos_perfil(), tmp_path)
    assert config.faltan('factibilidad') == [] and config.moneda
    destino = tmp_path / 'factibilidad.docx'
    escribir_informe_factibilidad(config, destino, _factibilidad(tmp_path))
    texto = _texto(destino)
    assert f'no reconocida ({config.moneda})' in texto
    assert json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))['plantilla'] == 'neutra'


def test_ejemplo_de_perfil_sin_una_empresa_concreta(informe_repositorio):
    """086:RF-32 — el ejemplo que se entrega no invita a heredar el perfil de otra empresa."""
    assert not [h for h in informe_repositorio.hallazgos if h.ruta == 'config/perfil_empresa.example.json']


def test_contrato_vnr_sin_rutas_de_una_maquina(tmp_path, monkeypatch):
    """086:RF-32 — la muestra es local: va por variable, y sin ella el perfil queda «sin verificar», sin bloquear."""
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.base import TargetProfile

    ruta = RAIZ / 'config' / 'vnr_dgs_profile.json'
    assert not json.loads(ruta.read_text(encoding='utf-8')).get('sample_path')
    monkeypatch.delenv('CSG_VNR_MUESTRA_DGS', raising=False)
    assert not TargetProfile.load(ruta).verified
    muestra = tmp_path / 'muestra.dgs'
    muestra.write_text('muestra', encoding='utf-8')
    perfil = tmp_path / 'p.json'
    perfil.write_text(json.dumps({'simulator': 'x', 'object_mapping': {'schema_profile': 'y'},
                                  'sample_hash': hashlib.sha256(b'muestra').hexdigest()}), encoding='utf-8')
    monkeypatch.setenv('CSG_VNR_MUESTRA_DGS', str(muestra))
    assert TargetProfile.load(perfil).verified


# --------------------------------------------------------------------------- RF-33
def _paquete(tmp_path: Path) -> Path:
    """Un candidato pequeño, limpio, con lo que la lista admite."""
    base = tmp_path / 'candidato'
    (base / 'src' / 'convertersmartgrid').mkdir(parents=True)
    (base / 'config' / 'perfiles').mkdir(parents=True)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text('# Comentario sin casos.\nVALOR = 1\n', encoding='utf-8')
    shutil.copy(RAIZ / 'config' / 'perfiles' / 'plantilla.json', base / 'config' / 'perfiles' / 'plantilla.json')
    return base


def _empresa_de_prueba() -> str:
    return json.loads(_perfil_excluido().read_text(encoding='utf-8'))['empresa']


def _codigo_de_prueba() -> str:
    datos = json.loads(_perfil_excluido('.estructura.json').read_text(encoding='utf-8'))
    return next(n for n, t in CE._nombres_de_estructura(datos) if t == 'codigo' and re.fullmatch(r'[A-Z]{2}\d{3}', n))


def _revisar(base, manifiesto, **kw):
    return CE.comprobar(RAIZ, manifiesto, CE.cargar_terminos(RAIZ, manifiesto, **kw), candidato=base)


def test_candidato_limpio_pasa(tmp_path, manifiesto):
    """086:RF-33 — un paquete sin términos ni pesos se puede entregar."""
    informe = _revisar(_paquete(tmp_path), manifiesto)
    assert not informe.rechazado, informe.resumen()


@pytest.mark.parametrize('cambiar', [
    lambda t: t.upper(),                       # mayúsculas
    lambda t: t.replace(' ', '_'),             # dentro de un identificador
    lambda t: t.replace(' ', ''),              # junto
])
def test_candidato_con_el_nombre_de_una_empresa_se_rechaza(tmp_path, manifiesto, cambiar):
    """086:RF-33 — el nombre del perfil excluido no pasa, se escriba como se escriba."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text(f'NOMBRE = "{cambiar(_empresa_de_prueba())}"\n', encoding='utf-8')
    informe = _revisar(base, manifiesto)
    assert informe.rechazado and informe.en_codigo[0].categoria == 'empresa'


def test_candidato_con_un_codigo_de_la_red_se_rechaza(tmp_path, manifiesto):
    """086:RF-33 — tampoco un código de alimentador de la estructura excluida."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text(f'EJEMPLO = "{_codigo_de_prueba()}"\n', encoding='utf-8')
    assert _revisar(base, manifiesto).rechazado


def test_en_un_candidato_tampoco_vale_un_comentario(tmp_path, manifiesto):
    """086:RF-33 — D5: en el repositorio el comentario cita su caso, en el paquete ya no."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text(f'# Falló en {_codigo_de_prueba()}.\nVALOR = 1\n', encoding='utf-8')
    informe = _revisar(base, manifiesto)
    assert informe.rechazado and informe.en_codigo == [] and informe.en_comentarios


def test_en_el_repositorio_los_comentarios_se_cuentan_pero_no_rechazan(tmp_path):
    """086:RF-33 — CLAUDE.md pide citar el caso real; su conflicto con D5 se resuelve al empaquetar."""
    terminos = CE.Terminos()
    terminos.anadir('Compania Ejemplo', 'empresa')
    h = CE.buscar_en_texto('a.py', '# Compania Ejemplo lo pidió\nX = 1\n"""Compania Ejemplo."""\n', terminos)
    assert {x.clase for x in h} == {'comentario'}
    informe = CE.Informe(hallazgos=h)
    assert not informe.rechazado and CE.Informe(hallazgos=h, candidato=True).rechazado


def test_clases_de_lineas_mezcladas():
    """086:RF-33 — un comentario al final de una línea no esconde lo que hay antes, ni al revés."""
    terminos = CE.Terminos()
    terminos.anadir('Compania Ejemplo', 'empresa')
    py = CE.buscar_en_texto('a.py', 'X = "Compania Ejemplo"  # otra cosa\nY = 1  # Compania Ejemplo\n', terminos)
    assert [(x.linea, x.clase) for x in py if x.termino == 'compania ejemplo'] == [(1, 'codigo'), (2, 'comentario')]
    ts = CE.buscar_en_texto('a.tsx', 'const a = "Compania Ejemplo";\n// Compania Ejemplo\nconst u = "https://x"; \n', terminos)
    assert [(x.linea, x.clase) for x in ts if x.termino == 'compania ejemplo'] == [(1, 'codigo'), (2, 'comentario')]


def test_lista_local_fuera_de_git(tmp_path, manifiesto):
    """086:RF-33 — la lista completa vive fuera de git; se nombra por variable o por ruta."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text('X = "Compania Ejemplo Sur"\n', encoding='utf-8')
    assert not _revisar(base, manifiesto).rechazado, 'sin la lista, ese nombre no está prohibido'
    lista = tmp_path / 'lista.json'
    lista.write_text(json.dumps({'cliente': ['Compañía Ejemplo Sur']}), encoding='utf-8')
    informe = _revisar(base, manifiesto, lista_local=lista)
    assert informe.rechazado and informe.hallazgos[0].categoria == 'cliente'
    texto = tmp_path / 'lista.txt'
    texto.write_text('# comentario\nCompañía Ejemplo Sur\n', encoding='utf-8')
    assert _revisar(base, manifiesto, lista_local=texto).rechazado


def test_lista_local_ausente_se_dice_y_no_se_omite(tmp_path, manifiesto, monkeypatch):
    """086:RF-33 — sin lista local se comprueba con la mínima, y lo dice; una ruta errada es un error."""
    monkeypatch.delenv(CE.VARIABLE_LISTA_LOCAL, raising=False)
    terminos = CE.cargar_terminos(RAIZ, manifiesto)
    assert any('sin lista local' in o for o in terminos.origenes) and terminos.huellas
    monkeypatch.setenv(CE.VARIABLE_LISTA_LOCAL, str(tmp_path / 'no_esta.json'))
    with pytest.raises(CE.EntregaError, match='lista local'):
        CE.cargar_terminos(RAIZ, manifiesto)


def test_huella_con_sal_rechaza_sin_escribir_el_nombre(tmp_path):
    """086:RF-33 — la lista mínima en git son huellas, como las de 076:RF-6; la de 076 también vale."""
    lista = tmp_path / 'huellas.json'
    lista.write_text(json.dumps({'huellas': {'086': {'cliente': [CE.huella('Compañía Ejemplo')]},
                                             '076': {'obra': [hashlib.sha256(b'076:obra secreta').hexdigest()[:16]]}}}), encoding='utf-8')
    terminos = CE.Terminos()
    CE.leer_huellas(lista, terminos)
    assert [h.categoria for h in CE.buscar_en_texto('a.py', 'X = "COMPANIA  EJEMPLO"\n', terminos)] == ['cliente']
    assert [h.categoria for h in CE.buscar_en_texto('a.py', 'X = "Obra Secreta"\n', terminos)] == ['obra']


def test_la_lista_de_huellas_no_lleva_nombres():
    """086:RF-33 — en git solo hay huellas de 16 cifras hexadecimales."""
    datos = json.loads(CE.HUELLAS.read_text(encoding='utf-8'))
    for categorias in datos['huellas'].values():
        for lista in categorias.values():
            assert lista and all(re.fullmatch(r'[0-9a-f]{16}', h) for h in lista)


def test_palabras_corrientes_no_son_terminos():
    """086:RF-33 — un nombre de zona que es una palabra corriente no taparía los hallazgos verdaderos."""
    t = CE.Terminos()
    for p in ('Independencia', 'Pausa', 'abc', '123456'):
        t.anadir(p, 'zona')
    assert not t.planos


def test_candidato_con_una_prueba_o_un_perfil_excluido_se_rechaza(tmp_path, manifiesto):
    """086:RF-32, 086:RF-33 — lo que la lista no admite no entra, aunque no lleve términos."""
    base = _paquete(tmp_path)
    (base / 'tests').mkdir()
    (base / 'tests' / 'test_x.py').write_text('X = 1\n', encoding='utf-8')
    excluido = _perfil_excluido()
    shutil.copy(excluido, base / 'config' / 'perfiles' / excluido.name)
    motivos = {r: m for r, m in _revisar(base, manifiesto).rechazos}
    assert 'tests/test_x.py' in motivos and f'config/perfiles/{excluido.name}' in motivos


def test_salida_de_la_orden_sin_nombres(tmp_path, capsys, monkeypatch):
    """086:RF-33 — la salida son cifras; solo --detalle, fuera de git, lleva los nombres."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text(f'X = "{_empresa_de_prueba()}"\n', encoding='utf-8')
    detalle = tmp_path / 'detalle.txt'
    assert CE.main(['--candidato', str(base), '--detalle', str(detalle)]) == 2
    salida = capsys.readouterr().out
    assert CE.normalizar(_empresa_de_prueba()) not in CE.normalizar(salida)
    assert json.loads(salida)['rechazado'] is True
    assert 'motor.py:1' in detalle.read_text(encoding='utf-8')
    assert CE.main(['--candidato', str(_limpio(tmp_path))]) == 0
    assert CE.main(['--candidato', str(tmp_path / 'no_esta')]) == 1


def _limpio(tmp_path: Path) -> Path:
    base = tmp_path / 'otro'
    (base / 'src' / 'convertersmartgrid').mkdir(parents=True)
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text('VALOR = 1\n', encoding='utf-8')
    return base


def test_comentarios_pendientes_de_neutralizar_quedan_contados(informe_repositorio):
    """086:RF-33 — hoy hay comentarios con casos reales (CLAUDE.md los pide): se cuentan, y el resumen no da ningún nombre."""
    resumen = informe_repositorio.resumen()
    assert resumen['terminos']['total'] == len(informe_repositorio.hallazgos)
    assert not resumen['rechazado'], resumen['rechazos'] or resumen['terminos']
    assert CE.normalizar(_empresa_de_prueba()) not in CE.normalizar(json.dumps(resumen))


# --------------------------------------------------------------------------- RF-34
def test_lista_de_entrega_unica_y_declarativa(manifiesto):
    """086:RF-34 — T21 lee este fichero: sin pruebas, specs ni instrucciones de agentes (D4), y sin pesos."""
    for dentro in ('src/convertersmartgrid/cli.py', 'tools/cargas_pf.py', 'config/entrega.json', 'docs/PERFIL_EMPRESA.md'):
        assert CE.entra(dentro, manifiesto), dentro
    for fuera in ('tests/test_x.py', 'specs/086/spec.md', '.claude/x.md', '.git/config', 'output/x.dgs',
                  'config/perfil_empresa.json', f'config/perfiles/{_perfil_excluido().name}', 'tools/madrl_obras.py',
                  'tools/asistente_entrenar.py', 'CLAUDE.md', 'docs/constitution.md'):
        assert not CE.entra(fuera, manifiesto), fuera
    assert manifiesto['pesos_permitidos'] == []


@pytest.mark.parametrize('nombre', ['modelo.safetensors', 'pinn.pt', 'orden.gguf', 'clasificador.joblib'])
def test_candidato_con_un_peso_se_rechaza(tmp_path, manifiesto, nombre):
    """086:RF-34 — ningún peso entra sin declararse."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / nombre).write_bytes(b'\x00pesos')
    informe = _revisar(base, manifiesto)
    assert informe.rechazado and any('peso' in m for _, m in informe.rechazos)


def test_peso_renombrado_tambien_se_rechaza(tmp_path, manifiesto):
    """086:RF-34 — cambiar la extensión no lo vuelve otra cosa."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'recurso.dat').write_bytes(b'GGUF\x03\x00\x00\x00resto')
    assert _revisar(base, manifiesto).rechazado


def test_peso_declarado_solo_si_no_es_de_otra_empresa(tmp_path, manifiesto):
    """086:RF-34 — declarado con su huella y datos admisibles entra; de otra empresa o con otra huella, no."""
    base = _paquete(tmp_path)
    peso = base / 'src' / 'convertersmartgrid' / 'modelo.safetensors'
    peso.write_bytes(b'pesos publicos')
    huella = hashlib.sha256(b'pesos publicos').hexdigest()
    rel = 'src/convertersmartgrid/modelo.safetensors'

    def con(**p):
        return {**manifiesto, 'pesos_permitidos': [{'ruta': rel, 'sha256': huella, **p}]}

    assert not _revisar(base, con(entrenado_con='publico')).rechazado
    assert _revisar(base, con(entrenado_con='otra_empresa')).rechazado
    assert _revisar(base, con(entrenado_con='publico', sha256='0' * 64)).rechazado


def test_candidato_con_datos_de_una_distribuidora_se_rechaza(tmp_path, manifiesto):
    """086:RF-34 — un DGS, una base o un informe no son parte del programa."""
    base = _paquete(tmp_path)
    (base / 'src' / 'convertersmartgrid' / 'red.dgs').write_text('x', encoding='utf-8')
    (base / 'src' / 'convertersmartgrid' / 'modelo.docx').write_bytes(b'PK\x03\x04')
    motivos = dict(_revisar(base, manifiesto).rechazos)
    assert len(motivos) == 2


def test_el_repositorio_no_lleva_pesos_en_lo_que_se_entrega(informe_repositorio):
    """086:RF-34 — ni pesos ni datos en lo que entra hoy."""
    assert informe_repositorio.rechazos == []


def test_ayuda_de_la_orden():
    """086:RF-33 — la herramienta responde a --help sin DIgSILENT."""
    with pytest.raises(SystemExit) as salida:
        CE.main(['--help'])
    assert salida.value.code == 0


# --------------------------------------------------------------------------- RF-35
def test_catalogo_no_supone_una_tension_nominal():
    """086:RF-35 — sin tensión del modelo la hoja queda por rellenar, no con la de una empresa."""
    columnas, filas = construir_hojas(auditar([]))['transformadores_sed']
    assert 'kV' in ' '.join(columnas)
    from convertersmartgrid.catalog import _hoja_trafos, Auditoria

    aud = Auditoria(trafos_kva={100.0: 2})
    assert _hoja_trafos(aud, None)[0][2] == ''
    assert _hoja_trafos(aud, 13.2)[0][2] == 13.2


def test_bandas_de_los_limites_con_aviso_si_el_perfil_no_las_da(tmp_path):
    """086:RF-35 — sin bandas del perfil ni del operador, salen de la banda de calidad, y se avisa."""
    config = _config(tmp_path).con_bandas()
    assert config.bandas_tension_pct == (85.0, 90.0, 95.0, 105.0)
    assert config.bandas_cargabilidad_pct == (80.0, 90.0, 95.0, 105.0, 150.0)
    assert any('bandas' in a for a in config.avisos_perfil)
    estrecha = ConfigInforme.de_perfil({'estudios': {'tension_min_pu': 0.94, 'tension_max_pu': 1.06, 'cargabilidad_max_pct': 80}}, tmp_path).con_bandas()
    assert estrecha.bandas_tension_pct == (84.0, 89.0, 94.0, 106.0)
    assert estrecha.bandas_cargabilidad_pct == (64.0, 72.0, 76.0, 84.0, 120.0)


def test_bandas_del_operador_y_del_perfil_mandan(tmp_path):
    """086:RF-35 — lo escrito en la web pisa al perfil, y lo del perfil no lleva aviso."""
    del_perfil = _config(tmp_path, bandas_tension_pct=[90, 110], bandas_cargabilidad_pct=[50, 100]).con_bandas()
    assert del_perfil.bandas_tension_pct == (90.0, 110.0) and del_perfil.avisos_perfil == ()
    operador = del_perfil.con_bandas(tension=[92, 108])
    assert operador.bandas_tension_pct == (92.0, 108.0) and operador.bandas_cargabilidad_pct == (50.0, 100.0)
    # El aviso nombra solo la que se derivó: en el navegador decía que faltaban las dos con una ya escrita.
    media = _config(tmp_path).con_bandas(tension=[92, 108])
    assert 'bandas_cargabilidad_pct' in media.avisos_perfil[0] and 'bandas_tension_pct' not in media.avisos_perfil[0]
    with pytest.raises(InformeError, match='bandas_tension_pct'):
        del_perfil.con_bandas(tension=[108, 92])


def test_sin_limites_ni_bandas_se_piden_y_no_se_inventan(tmp_path):
    """086:RF-35 — sin límites no se derivan bandas: el formulario pide los límites primero."""
    config = ConfigInforme.de_perfil({}, tmp_path).con_bandas()
    assert config.bandas_tension_pct is None and config.faltan('estudio')[0].startswith('estudios.')


def test_bandas_de_referencia_del_mapa_salen_de_la_norma():
    """086:RF-35 — las del mapa son las de ±5 % y 100 %, no un modelo de una empresa: se comprueba con la fórmula."""
    import convertersmartgrid.mapa_informe as mapa
    from convertersmartgrid.estudios_pf import LIMITES_POR_DEFECTO
    from convertersmartgrid.informes import bandas_de_limites

    assert (mapa.BANDAS_TENSION, mapa.BANDAS_CARGA) == bandas_de_limites(LIMITES_POR_DEFECTO)
    assert imagenes_del_estado is not None


def test_transformador_con_las_bandas_del_perfil(tmp_path):
    """086:RF-35 — el dibujo del transformador también usa las bandas dadas, no unas fijas."""
    from PIL import Image
    from convertersmartgrid.mapa_informe import transformador_de_la_set

    ruta = transformador_de_la_set('T', 'S', [(10.0, 60.0)], tmp_path / 't.png', titulo='x', bandas_carga=(10, 20, 30, 40, 50))
    with Image.open(ruta) as img:
        colores = {c for _, c in img.getcolors(1 << 20)}
    assert (110, 0, 0) in colores, 'el 60 % ya es la última banda con estas bandas'


def test_contexto_ofrece_las_bandas_que_se_piden(client, tmp_path, monkeypatch):  # noqa: F811
    """086:RF-35 — el contexto dice qué bandas da el perfil; las que no, las pide la pantalla."""
    perfil = tmp_path / 'p.json'
    perfil.write_text(json.dumps({'informes': {'bandas_tension_pct': [90, 110]}}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    wid, _ = _espacio(client, tmp_path)
    ctx = client.get(f'/api/workspaces/{wid}/informes', params={'project': 'PRY', 'feeder': ['AL01']}).json()
    assert ctx['bandas'] == {'tension': [90.0, 110.0], 'cargabilidad': None}


def test_api_acepta_las_bandas_del_formulario():
    """086:RF-35 — el formulario las lleva; un valor que no es lista se rechaza con 422."""
    from convertersmartgrid.web.app import InformeEstudioIn

    base = {'project': 'P', 'alimentador': 'A', 'fecha': '2026-11-04', 'asunto': 'X'}
    assert InformeEstudioIn(**base, bandas={'tension': [90, 110]}).bandas == {'tension': [90, 110]}
    with pytest.raises(ValueError):
        InformeEstudioIn(**base, bandas={'tension': 'alto'})


def test_web_arranca_con_el_perfil_ficticio(tmp_path, monkeypatch):
    """086:RF-32 — la web sirve sus datos con el perfil ficticio, sin DIgSILENT ni modelos."""
    activo = tmp_path / 'perfil_empresa.json'
    activo.write_text('{"perfil": "ficticia"}', encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(activo))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        assert c.get('/api/health').json()['perfil_empresa']['nombre'] == 'ficticia'
