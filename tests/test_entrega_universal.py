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

from convertersmartgrid.aplicacion.catalog import auditar, construir_hojas
from convertersmartgrid.presentacion.cli import main as cli_main
from convertersmartgrid.adaptadores.informe_docx import escribir_informe_estudio, escribir_informe_factibilidad
from convertersmartgrid.adaptadores.informes import ConfigInforme, InformeError
from convertersmartgrid.adaptadores.libro_informe import comprobar_libro
from convertersmartgrid.adaptadores.mapa_informe import imagenes_del_estado
from convertersmartgrid.dominio.perfil_empresa import cargar_perfil, datos_perfil, moneda_informes, perfil_con_nombre, perfiles_disponibles
from convertersmartgrid.adaptadores.perfil_esquema import claves_del_esquema, validar_perfil
from convertersmartgrid.presentacion.web.app import create_app

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
    fuente = (RAIZ / 'src' / 'convertersmartgrid' / 'adaptadores/libro_informe.py').read_text(encoding='utf-8')
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
    monkeypatch.setattr('convertersmartgrid.dominio.perfil_empresa.carpeta_perfiles', lambda: carpeta)

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


def test_las_sales_se_calculan_al_cambiar_las_huellas_y_no_en_cada_ventana():
    """086:RF-111 — construir la rueda pedía 1,8 millones de veces el conjunto ordenado de las sales: una por ventana."""
    t = CE.Terminos()
    t.huellas[('s1', 'a' * 16)] = 'empresa'
    primera = t.sales
    assert t.sales is primera, 'las sales se recalculan en cada consulta'
    t.huellas[('s0', 'b' * 16)] = 'zona'
    assert t.sales == ('s0', 's1') and t.sales is t.sales
    t.huellas = {('s2', 'c' * 16): 'zona', ('s3', 'd' * 16): 'zona'}
    assert t.sales == ('s2', 's3'), 'otro diccionario de huellas, otras sales'


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
    """086:RF-34 — T21 lee este fichero: sin pruebas, specs ni instrucciones de agentes (D4), y sin pesos.

    086:RF-15 (orden del usuario, 2026-11-13: «nada debería estar apagado ni bloqueado»): los guiones que lanza el
    programa para entrenar entran; sin ellos el instalado respondía «No se encuentra el guion» al entrenar."""
    for dentro in ('src/convertersmartgrid/presentacion/cli.py', 'tools/cargas_pf.py', 'config/entrega.json', 'docs/PERFIL_EMPRESA.md',
                   'tools/asistente_entrenar.py'):
        assert CE.entra(dentro, manifiesto), dentro
    for fuera in ('tests/test_x.py', 'specs/086/spec.md', '.claude/x.md', '.git/config', 'output/x.dgs',
                  'config/perfil_empresa.json', f'config/perfiles/{_perfil_excluido().name}', 'tools/madrl_obras.py',
                  'CLAUDE.md', 'docs/constitution.md'):
        assert not CE.entra(fuera, manifiesto), fuera
    # 086:RF-34 (usuario, 2026-11-13): solo los dos modelos públicos del complemento de IA, nunca uno del proyecto.
    assert {p['modelo'] for p in manifiesto['pesos_permitidos']} == {'intfloat/multilingual-e5-base', 'qwen3:8b'}
    assert all(p['entrenado_con'] == 'publico' and p['ruta'].startswith('modelos/') for p in manifiesto['pesos_permitidos'])


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
    from convertersmartgrid.aplicacion.catalog import _hoja_trafos, Auditoria

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
    import convertersmartgrid.adaptadores.mapa_informe as mapa
    from convertersmartgrid.aplicacion.estudios_pf import LIMITES_POR_DEFECTO
    from convertersmartgrid.adaptadores.informes import bandas_de_limites

    assert (mapa.BANDAS_TENSION, mapa.BANDAS_CARGA) == bandas_de_limites(LIMITES_POR_DEFECTO)
    assert imagenes_del_estado is not None


def test_transformador_con_las_bandas_del_perfil(tmp_path):
    """086:RF-35 — el dibujo del transformador también usa las bandas dadas, no unas fijas."""
    from PIL import Image
    from convertersmartgrid.adaptadores.mapa_informe import transformador_de_la_set

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
    from convertersmartgrid.presentacion.web.app import InformeEstudioIn

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


# --------------------------------------------------------------------------- RF-33: lanzamiento (L1, U5)
def _otra_empresa(tmp_path: Path) -> Path:
    """La lista local de una segunda distribuidora, inventada: los nombres reales viven fuera de git (U5)."""
    lista = tmp_path / 'lista_local.json'
    lista.write_text(json.dumps({'empresa': ['Compañía Ejemplo Norte'], 'paquete, base o corpus': ['CEJN25_V2', 'PIDECEJN'],
                                 'codigo de alimentador o SET': ['QZX202']}), encoding='utf-8')
    return lista


@pytest.mark.parametrize('comentario', [
    lambda e, o: f'# Falló en {e}, con su red.\nVALOR = 1\n',                       # la empresa del perfil excluido
    lambda e, o: f'"""Caso real: el paquete {o["paquete"]} de su copia."""\nVALOR = 1\n',  # el paquete de la otra
    lambda e, o: f'# Medido en {o["codigo"]}: calibrado bajo el límite.\nVALOR = 1\n',  # su alimentador
    lambda e, o: '# 086:RF-76: lo pidió Compañía Ejemplo\n# Norte (T32).\nVALOR = 1\n',  # partido por el salto de línea
])
def test_086_rf33_un_comentario_de_cualquiera_de_las_dos_empresas_rechaza_la_entrega(tmp_path, manifiesto, comentario):
    """086:RF-33 — L1 (2026-11-14): en el rc6 pasaron comentarios con el paquete, el corpus y los códigos de otra distribuidora."""
    base = _paquete(tmp_path)
    otra = {'paquete': 'CEJN25_V2', 'codigo': 'QZX202'}
    (base / 'src' / 'convertersmartgrid' / 'motor.py').write_text(comentario(_empresa_de_prueba(), otra), encoding='utf-8')
    informe = _revisar(base, manifiesto, lista_local=_otra_empresa(tmp_path), final=True)
    assert informe.rechazado and informe.en_codigo == [] and informe.en_comentarios


def test_086_rf33_el_candidato_final_sin_lista_local_es_un_error(tmp_path, manifiesto, monkeypatch, capsys):
    """086:RF-33 — L1: sin lista local, el final no se comprueba (error, salida 1); uno de prueba lo avisa y sigue."""
    monkeypatch.delenv(CE.VARIABLE_LISTA_LOCAL, raising=False)
    with pytest.raises(CE.EntregaError, match='lista local'):
        CE.cargar_terminos(RAIZ, manifiesto, final=True)
    assert any('sin lista local' in o and 'prueba' in o for o in CE.cargar_terminos(RAIZ, manifiesto).origenes)
    assert CE.main(['--candidato', str(_paquete(tmp_path)), '--final']) == 1
    assert 'lista local' in capsys.readouterr().err


def test_086_rf33_neutralizar_quita_el_nombre_partido_y_las_cifras_de_su_linea(tmp_path):
    """086:RF-33, D5 — L1: un nombre partido entre dos líneas pasaba, y con él las cifras reales de su línea."""
    terminos = CE.Terminos()
    terminos.anadir('Compañía Ejemplo Norte', 'empresa')
    terminos.anadir('QZX202', 'codigo de alimentador o SET')
    texto = ('X = 1  # 086:RF-76: sin cargas nuevas. Compañía Ejemplo\n'
             '# Norte QZX202 (T32, 2026-11-12): calibrado a 0,568 p.u. con 374 de 849 SED.\n'
             'Y = "0,568"\n')
    nuevo, n = CE.neutralizar('a.py', texto, terminos)
    assert n and not CE.buscar_en_texto('a.py', nuevo, terminos)
    lineas = nuevo.splitlines()
    assert lineas[0].startswith('X = 1  # 086:RF-76') and lineas[2] == 'Y = "0,568"', 'el código y el requisito no cambian'
    assert '0,568' not in lineas[1] and '374' not in lineas[1] and '849' not in lineas[1]
    assert 'T32' in lineas[1] and '2026-11-12' in lineas[1], 'la fecha y la tarea se quedan'


def test_086_rf33_las_huellas_cubren_paquetes_y_codigos_de_cada_empresa():
    """086:RF-33 — L1: la lista mínima en git ya no es de una sola empresa: lleva paquetes, corpus y códigos de alimentador."""
    huellas = json.loads(CE.HUELLAS.read_text(encoding='utf-8'))['huellas']['086']
    assert {'empresa', 'paquete, base o corpus', 'codigo de alimentador o SET'} <= set(huellas)
    assert len(huellas['codigo de alimentador o SET']) >= 50 and len(huellas['empresa']) > 23, 'la de una sola empresa tenía 23'


def test_086_rf33_el_codigo_entregado_no_cita_a_otras_distribuidoras(manifiesto):
    """086:RF-33 — L1: lo que se entrega del repositorio, sin lista local, no tiene ningún término de las huellas en el código."""
    informe = CE.comprobar(RAIZ, manifiesto, CE.cargar_terminos(RAIZ, manifiesto))
    assert not informe.en_codigo, informe.resumen()


# --------------------------------------------------------------------------- 107:RF-11 (T17)
#: El PIT y el registro normativo, universales: lo que vale para un área, una empresa o un periodo sale del perfil o del
#: registro, nunca del código (107 T17).
_UNIVERSALES_107 = ('src/convertersmartgrid/dominio/pit', 'src/convertersmartgrid/aplicacion/pit',
                    'src/convertersmartgrid/adaptadores/pit', 'src/convertersmartgrid/dominio/registro_normativo.py')


def test_107_rf11_el_detector_ve_tensiones_anios_tasas_y_areas_escritas_en_el_codigo():
    """107:RF-11 (T17) — el detector de valores fijos ve una tensión, un año, una tasa y un número de área escritos en el
    código, y no lo que va en un comentario o en un docstring, que D5 neutraliza al empaquetar."""
    assert hasattr(CE, 'valores_fijos'), 'comprobar_entrega.py no tiene el detector de valores fijos (107 T17)'
    codigo = ("LIMITE = '66 kV'\n"
              "ANIO = 2099\n"
              "TASAS = {'tasa_descuento': 0.07}\n"
              "AREA = 'AD-99'\n"
              "MENSAJE = 'un 7,5 % del total'\n"
              "# 66 kV, 2099 y AD-99 en un comentario no cuentan\n"
              "def f():\n"
              "    '''Ni en el docstring: 13,8 kV desde 2098, al 9 %.'''\n"
              "    return 'de 0 a 100 %'\n")
    hallados = CE.valores_fijos('x.py', codigo)
    assert {(n, c) for n, c, _ in hallados} == {(1, 'tension'), (2, 'anio'), (3, 'tasa'), (4, 'area'), (5, 'tasa')}, \
        hallados
    assert CE.valores_fijos('x.py', 'LIMITES = registro.valor("pit.tension_min_kv")\n') == []


def test_107_rf11_pit_y_registro_normativo_sin_valores_de_un_area_una_empresa_o_un_periodo(manifiesto):
    """107:RF-11 (T17) — ni el paquete pit/ ni registro_normativo.py llevan en su código una tensión, un año, una tasa o
    un número de área: salen del registro o del perfil. Los dos entran en la entrega, así que la búsqueda de nombres y
    titulares de 086:RF-29 (test_nucleo_y_web_sin_terminos_en_el_codigo) también los recorre."""
    assert hasattr(CE, 'valores_fijos'), 'comprobar_entrega.py no tiene el detector de valores fijos (107 T17)'
    ficheros = []
    for rel in _UNIVERSALES_107:
        ruta = RAIZ / rel
        ficheros += sorted(ruta.rglob('*.py')) if ruta.is_dir() else [ruta]
    assert len(ficheros) > 10, 'la comprobación recorrió de verdad el paquete pit/'
    fuera, malos = [], []
    for ruta in ficheros:
        rel = ruta.relative_to(RAIZ).as_posix()
        if not CE.entra(rel, manifiesto):
            fuera.append(rel)
        malos += [f'{rel}:{n} ({clase}: {trozo})' for n, clase, trozo in CE.valores_fijos(rel, ruta.read_text(encoding='utf-8'))]
    assert not fuera, f'fuera de la entrega, sin la búsqueda de términos: {fuera}'
    assert not malos, malos


# --------------------------------------------------------------------------- nombres reales de config (107, v2 de c3)
#: Donde están los nombres reales: las transcripciones oficiales del registro y de las modificaciones del PIT. Solo ahí
#: pueden estar; ni src/ ni tests/ los escriben como literales.
CARPETAS_CON_NOMBRES = ('config/normativa', 'config/pit/modificaciones')
#: Claves de esas transcripciones cuyo valor es el nombre de un titular o de una instalación.
CLAVES_CON_NOMBRE = ('titular', 'instalacion')
#: NOMBRES-001: los nombres que van como CLAVES de un diccionario bajo estas claves (p. ej. valor['empresas']).
CLAVES_DICT_DE_NOMBRES = ('empresas',)
#: NOMBRES-001: y el último tramo de una «clave» de regla cuando lleva mayúsculas (…causa_del_cambio.<Empresa>): las
#: claves del registro van en minúsculas, así que un tramo con mayúscula es un nombre propio.
#: NOMBRES-COM: tres formas más de los nombres de EMPRESA (titular, claves de «empresas» y tramo de una «clave»):
#: (1) la forma sin espacios («Electro X» → «electrox»); (2) el primer tramo distintivo (no genérico, con
#: NOMBRES_MIN_LETRAS letras como mínimo); (3) la sigla o código de empresa de los perfiles reales de config/perfiles.
#: Los perfiles ficticios o de plantilla no cuentan. Siempre palabra entera, nunca subcadena.
GENERICAS_PRIMER_TRAMO = {'electro', 'luz', 'empresa', 'sociedad', 'compania', 'consorcio', 'energia', 'electrica',
                          'servicios', 'municipal', 'red', 'distribuidora', 'emp', 'empresas'}
CARPETA_PERFILES = 'config/perfiles'
#: NOMBRES-TST v2: los sitios y clientes reales de los casos de prueba (no son empresas, pero son igual de reales).
#: FIX-NOMBRES-HUELLAS (c2 y el usuario, 16-11): el repositorio es público y config solo lleva la HUELLA de su nombre y
#: de su forma pegada (``_huella_nombre``), con el caso y la procedencia; el nombre está en la lista local, fuera de git.
ARCHIVO_SITIOS = 'config/casos_de_prueba/sitios.json'
#: NOMBRES-CAT: los códigos de empresa de los paquetes VNR-GIS públicos (grupos vigentes de Osinergmin), por su HUELLA
#: (FIX-NOMBRES-HUELLAS): ni el código ni su paquete, su dirección o su base se escriben en el repositorio.
#: Se buscan en MAYÚSCULAS y como palabra entera: un código puede ser también una palabra del lenguaje en minúsculas.
#: Valen desde 3 letras (por debajo de NOMBRES_MIN_LETRAS): son identificadores exactos, no palabras.
ARCHIVO_CODIGOS_VNR = 'config/vnr/codigos_empresa_vnr.json'
PERFILES_FICTICIOS = {'ficticia.json', 'plantilla.json'}
#: Longitud mínima del nombre que se busca: con menos de 4 letras, las siglas coinciden con palabras y abreviaturas
#: corrientes (p. ej. «SE», «AT», «MT») y la comprobación daría falsos positivos sin valor.
NOMBRES_MIN_LETRAS = 4
#: Palabras comunes que coinciden con un nombre de config y no lo identifican: no se buscan, cada una con su motivo.
EXCEPCIONES_NOMBRES = {
    'porvenir': 'palabra común del castellano («el porvenir»); como nombre de SET solo identifica junto a su SET',
}
#: Literales ya presentes antes de esta comprobación, en pruebas ajenas a la 107-T-DESBLOQUEO, con su motivo y su
#: responsable: no se esconden, se listan hasta que su dueño las pase a leer de config. El nombre va por su huella
#: (los 16 primeros hexadecimales del sha256 del nombre normalizado), para no escribirlo aquí tampoco.
NOMBRES_TOLERADOS = {}  # VACÍA desde NOMBRES-001: la spec 001 usa nombres sintéticos neutros
#: NOMBRES-001 (decisión (b) de c3): lo que el escáner AMPLIADO halló fuera de la spec 001, CONGELADO por tarjeta y
#: responsable, con su TIPO leído de cada aparición («logica»: decide el comportamiento; «comentario»: solo en un
#: comentario o docstring). NOMBRES-SRC = lógica de src (f4); NOMBRES-COM = comentarios y docstrings de src y de tests
#: (2e); NOMBRES-TST = lógica de tests (2e). El trinquete la trata como a NOMBRES_TOLERADOS: solo encoge. La genera
#: APOYO_6C/nombres001/generar_pendientes.py; el nombre va por su huella, nunca escrito.
NOMBRES_PENDIENTES_POR_TARJETA = {}  # VACÍA desde NOMBRES-TST: NOMBRES-COM y NOMBRES-TST la vaciaron
#: El TRINQUETE (NOMBRES-REG, orden de c3): NOMBRES_TOLERADOS solo encoge. Un nombre nuevo, o uno en un fichero que no
#: está en la tabla, salta en test_ningun_nombre_real_de_config_en_src_ni_en_tests; una entrada cuyo nombre ya no está
#: en su fichero (porque su dueño lo limpió o el fichero desapareció) salta en
#: test_el_trinquete_no_deja_tolerados_que_sobran, y hay que quitarla: la tabla no puede volver a crecer escondida tras
#: una entrada vieja. Las de tests/test_pit_registro.py (RN-AMB y VAD-FE26) salieron en NOMBRES-REG: la prueba ya lee
#: los nombres del registro y los fija por su huella.
_PREFIJO_SET = re.compile(r'^(?:SET|SE|S\.E\.)\s+(?:M?AT/(?:AT|MT)(?:/MT)?\s+)?', re.I)


def _sin_tildes(texto):
    import unicodedata
    return unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode().casefold()


def _nombres_de_config(raiz):  # noqa: C901 (recorrido de las transcripciones, una sola pasada)
    """Los nombres de las transcripciones de config, normalizados: titular e instalación (sin «SET AT/MT»), las claves
    de los diccionarios bajo CLAVES_DICT_DE_NOMBRES (sin el paréntesis) y el último tramo con mayúscula de una «clave»."""
    crudos, empresas = set(), set()

    def recorrer(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in CLAVES_CON_NOMBRE and isinstance(v, str):
                    crudos.add(_PREFIJO_SET.sub('', v.strip()))
                    if k == 'titular':
                        empresas.add(v.strip())
                elif k in CLAVES_DICT_DE_NOMBRES and isinstance(v, dict):
                    nuevas = {re.sub(r'\s*\(.*?\)\s*', ' ', clave).strip() for clave in v}
                    crudos.update(nuevas)
                    empresas.update(nuevas)
                elif k == 'clave' and isinstance(v, str):
                    tramo = v.rsplit('.', 1)[-1]
                    if any(c.isupper() for c in tramo):
                        crudos.add(tramo)
                        empresas.add(tramo)
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)

    for carpeta in CARPETAS_CON_NOMBRES:
        for f in sorted((raiz / carpeta).rglob('*.json')):
            recorrer(json.loads(f.read_text(encoding='utf-8')))
    for e in {_sin_tildes(x).strip() for x in empresas}:
        partes = e.split()
        if len(partes) > 1:
            crudos.add(e.replace(' ', ''))
            if partes[0] not in GENERICAS_PRIMER_TRAMO:
                crudos.add(partes[0])
    for f in sorted((raiz / CARPETA_PERFILES).glob('*.json')) if (raiz / CARPETA_PERFILES).is_dir() else ():
        if f.name not in PERFILES_FICTICIOS:
            _codigos_de_empresa(json.loads(f.read_text(encoding='utf-8')), crudos)
    nombres = {_sin_tildes(n).strip() for n in crudos}
    return {n for n in nombres if sum(c.isalpha() for c in n) >= NOMBRES_MIN_LETRAS and n not in EXCEPCIONES_NOMBRES}


def _codigos_de_alimentador(raiz):
    """Los códigos reales de alimentador de los perfiles de estructura de config (``alimentadores[].codigo``),
    normalizados: las pruebas los leen de aquí en vez de escribirlos (NOMBRES-TST v2)."""
    salida = set()

    def recorrer(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == 'alimentadores' and isinstance(v, list):
                    salida.update(_sin_tildes(a['codigo']).strip() for a in v if isinstance(a, dict) and a.get('codigo'))
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)

    for f in sorted((raiz / CARPETA_PERFILES).glob('*.estructura.json')) if (raiz / CARPETA_PERFILES).is_dir() else ():
        if f.name.split('.')[0] + '.json' not in PERFILES_FICTICIOS:
            recorrer(json.loads(f.read_text(encoding='utf-8')))
    return salida


def _codigos_vnr(raiz):
    """Las huellas de los códigos de empresa del catálogo VNR de config (``_huella_nombre`` del código en minúsculas)."""
    f = raiz / ARCHIVO_CODIGOS_VNR
    if not f.is_file():
        return set()
    return {p['huella'] for g in json.loads(f.read_text(encoding='utf-8'))['grupos'] for p in g['paquetes']}


def _hallar_codigos(huellas, texto):
    """Las huellas de los códigos que aparecen en ``texto`` en MAYÚSCULAS como palabra entera (frontera no
    alfanumérica: el guion bajo separa, así que «X_COD_25» delata el código). En minúsculas no: un código puede ser
    también una palabra corriente del lenguaje."""
    vistas = {_huella_nombre(m.group(0).casefold())
              for m in re.finditer(r'(?<![A-Za-z0-9])[A-Z0-9]{3,}(?![A-Za-z0-9])', texto)}
    return sorted(vistas & set(huellas))


#: Palabras de un sitio que se prueban juntas: los de los casos tienen una o dos; tres deja margen.
SITIOS_MAX_PALABRAS = 3


def _sitios_de_casos(raiz):
    """Las huellas de los sitios de los casos de ARCHIVO_SITIOS: la de su nombre y, si tiene varias palabras, la de su
    forma pegada."""
    f = raiz / ARCHIVO_SITIOS
    if not f.is_file():
        return set()
    return {h for s in json.loads(f.read_text(encoding='utf-8'))['sitios'] for h in s['huellas']}


def _hallar_sitios(huellas, texto):
    """Las huellas de los sitios que aparecen en ``texto`` como palabras enteras, sin tildes ni mayúsculas: cada tramo de
    hasta SITIOS_MAX_PALABRAS palabras, separadas por un espacio, se compara por su huella. La forma pegada de un nombre
    («PampaNandu») es una sola palabra del texto y se compara así; dos palabras distintas no se pegan."""
    huellas = set(huellas)
    plano = _sin_tildes(texto)
    trozos = [(m.group(0), m.start(), m.end()) for m in re.finditer(r'[a-z0-9]+', plano)]
    vistas = set()
    for i in range(len(trozos)):
        for n in range(1, min(SITIOS_MAX_PALABRAS, len(trozos) - i) + 1):
            # Las palabras de un nombre van separadas solo por espacios: «pampa, nandu» no es «pampa nandu».
            if n > 1 and plano[trozos[i + n - 2][2]:trozos[i + n - 1][1]].strip(' '):
                break
            vistas |= {_huella_nombre(' '.join(t for t, _a, _b in trozos[i:i + n]))} & huellas
    return sorted(vistas)


def _codigos_de_empresa(x, salida):
    """Los valores de «codigo_empresa» de un perfil (la sigla de la empresa)."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k == 'codigo_empresa' and isinstance(v, str) and v.strip():
                salida.add(v.strip())
            _codigos_de_empresa(v, salida)
    elif isinstance(x, list):
        for v in x:
            _codigos_de_empresa(v, salida)


def _hallar_nombres(nombres, texto):
    """Cada nombre que aparece en ``texto`` como palabra completa, sin distinguir tildes ni mayúsculas. La frontera es
    «no alfanumérico» (NOMBRES-COM): el guion bajo separa, así que «X_SIGLA_24» delata la sigla; nunca una subcadena."""
    plano = _sin_tildes(texto)
    return sorted(n for n in nombres if re.search(r'(?<![a-z0-9])' + re.escape(n) + r'(?![a-z0-9])', plano))


def _huella_nombre(nombre):
    """La huella con que NOMBRES_TOLERADOS guarda un nombre normalizado: los 16 primeros hexadecimales de su sha256."""
    return hashlib.sha256(nombre.encode()).hexdigest()[:16]


def _pares_en_src_y_tests(raiz):
    """Cada (fichero, huella del nombre) de config que aparece en los .py de src/ y tests/ de ``raiz``."""
    nombres, codigos, sitios = _nombres_de_config(raiz), _codigos_vnr(raiz), _sitios_de_casos(raiz)
    pares = set()
    for carpeta in ('src', 'tests'):
        for f in sorted((raiz / carpeta).rglob('*.py')):
            rel = f.relative_to(raiz).as_posix()
            texto = f.read_text(encoding='utf-8')
            pares |= {(rel, _huella_nombre(n)) for n in _hallar_nombres(nombres, texto)}
            pares |= {(rel, h) for h in _hallar_sitios(sitios, texto)}
            pares |= {(rel, h) for h in _hallar_codigos(codigos, texto)}
    return pares


def _nombres_en_src_y_tests(raiz, tolerados=None):
    """Los pares hallados que la tabla de tolerados no cubre: nombres o ficheros nuevos."""
    tolerados = {**NOMBRES_TOLERADOS, **NOMBRES_PENDIENTES_POR_TARJETA} if tolerados is None else tolerados
    return sorted(p for p in _pares_en_src_y_tests(raiz) if p not in tolerados)


def _tolerados_que_sobran(raiz, tolerados=None):
    """El trinquete: las entradas de la tabla cuyo nombre ya no está en su fichero. Deben salir de la tabla."""
    tolerados = {**NOMBRES_TOLERADOS, **NOMBRES_PENDIENTES_POR_TARJETA} if tolerados is None else tolerados
    pares = _pares_en_src_y_tests(raiz)
    return sorted(k for k in tolerados if k not in pares)


def _es_huella(x):
    return isinstance(x, str) and re.fullmatch(r'[0-9a-f]{16}', x) is not None


def test_el_escaner_ve_los_sitios_de_los_casos(tmp_path):
    """NOMBRES-TST v2 (f4, c3) y FIX-NOMBRES-HUELLAS (c2) — los sitios y clientes reales de los casos de prueba están en
    config POR SU HUELLA, con su tipo, su caso y su procedencia, y sin su nombre; el escáner los ve escritos en un valor,
    con otras mayúsculas o tildes, y en su forma pegada: ni src/ ni tests/ los pueden escribir."""
    datos = json.loads((RAIZ / ARCHIVO_SITIOS).read_text(encoding='utf-8'))
    assert datos['esquema'] == 'sitios_de_casos_v2' and datos['sitios']
    for sitio in datos['sitios']:
        assert 'nombre' not in sitio, 'el nombre del sitio no va en el repositorio, solo su huella'
        assert sitio['tipo'] in ('cliente', 'SET') and sitio['caso'] and sitio['procedencia'], sitio
        assert sitio['huellas'] and all(_es_huella(h) for h in sitio['huellas']), sitio
    # Un sitio inventado, con la misma forma: el escáner lo ve solo, con tildes o sin ellas y pegado; nunca dentro de
    # otra palabra.
    falso = {'esquema': 'sitios_de_casos_v2', 'sitios': [{'huellas': [_huella_nombre('pampa nandu'),
                                                                      _huella_nombre('pampanandu')],
                                                          'tipo': 'cliente', 'caso': 'sintético', 'procedencia': '-'}]}
    for nombre, texto in (('suelto', "CLIENTE = 'PAMPA ÑANDÚ'\n"), ('pegado', "CLIENTE = 'PampaNandu'\n"),
                          ('dentro', "CLIENTE = 'pampa nanduti'\n"),
                          # Dos palabras del código que, pegadas, darían el nombre: no son el nombre.
                          ('partido', "for pampa, nandu in pares:\n    pass\nx = 'pampa' + 'nandu'\n")):
        raiz = _raiz_con_config(tmp_path / nombre, texto)
        (raiz / ARCHIVO_SITIOS).write_text(json.dumps(falso), encoding='utf-8')
        vistos = {h for _f, h in _pares_en_src_y_tests(raiz)}
        visto = bool({_huella_nombre('pampa nandu'), _huella_nombre('pampanandu')} & vistos)
        assert visto == (nombre in ('suelto', 'pegado')), (nombre, vistos)


def _raiz_con_config(tmp_path, prueba):
    """Una raíz con la config que lee el escáner y un tests/ con una sola prueba sintética."""
    import shutil
    for c in ('config/normativa', 'config/pit/modificaciones', 'config/perfiles', 'config/casos_de_prueba', 'config/vnr'):
        if (RAIZ / c).is_dir():
            shutil.copytree(RAIZ / c, tmp_path / c)
    (tmp_path / 'src').mkdir()
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_sintetico.py').write_text(prueba, encoding='utf-8')
    return tmp_path


def test_el_catalogo_vnr_trae_cada_codigo_con_su_fuente():
    """NOMBRES-CAT (c3) y FIX-NOMBRES-HUELLAS (c2) — config/vnr/codigos_empresa_vnr.json: los códigos de empresa de los
    paquetes VNR-GIS de los grupos vigentes (RCD 184-2026-OS/CD, 14 paquetes; RCD 208-2023-OS/CD, 11), cada uno por su
    huella y con el tamaño de su paquete; sin el código, ni el nombre del paquete, su dirección o su base, que lo
    escriben; sin códigos repetidos."""
    datos = json.loads((RAIZ / ARCHIVO_CODIGOS_VNR).read_text(encoding='utf-8'))
    assert datos['esquema'] == 'codigos_empresa_vnr_v2'
    por_norma = {g['norma']: g['paquetes'] for g in datos['grupos']}
    assert {n: len(v) for n, v in por_norma.items()} == {'RCD 184-2026-OS/CD': 14, 'RCD 208-2023-OS/CD': 11}
    huellas = [p['huella'] for v in por_norma.values() for p in v]
    assert len(huellas) == len(set(huellas)) == 25 and all(_es_huella(h) for h in huellas)
    for v in por_norma.values():
        for p in v:
            assert set(p) == {'huella', 'bytes_paquete'} and p['bytes_paquete'] > 0, p


def test_el_escaner_ve_cada_codigo_vnr_en_mayusculas_y_no_una_palabra_del_lenguaje(tmp_path):
    """NOMBRES-CAT (c3) y FIX-NOMBRES-HUELLAS (c2) — un código del catálogo VNR, escrito en un valor de una prueba en
    MAYÚSCULAS (solo o entre guiones bajos), salta en el trinquete por su huella; en minúsculas, donde puede ser una
    palabra corriente, no. Con códigos inventados de la misma forma: los reales no se escriben aquí."""
    codigos = ['QZX', 'ZQW9']
    falso = {'esquema': 'codigos_empresa_vnr_v2', 'grupos': [
        {'norma': 'sintética', 'paquetes': [{'huella': _huella_nombre(c.casefold()), 'bytes_paquete': 1} for c in codigos]}]}

    def pares(nombre, prueba):
        raiz = _raiz_con_config(tmp_path / nombre, prueba)
        (raiz / ARCHIVO_CODIGOS_VNR).write_text(json.dumps(falso), encoding='utf-8')
        return {h for _f, h in _pares_en_src_y_tests(raiz)}

    vistos = pares('con', "ORIGEN = 'QZX'\nBASE = 'X_ZQW9_25'\n")
    assert {_huella_nombre(c.casefold()) for c in codigos} <= vistos, vistos
    assert not pares('minusculas', "palabra = 'qzx'\nqzxzqw9 = 1\n") & {_huella_nombre(c.casefold()) for c in codigos}
    corriente = 'def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n'
    assert not pares('sin', corriente) & {_huella_nombre(c.casefold()) for c in codigos}


def test_ningun_nombre_real_de_config_en_src_ni_en_tests():
    """107:RF-11 (v2 de c3) — los nombres de titular y de SET de las transcripciones oficiales (config/normativa y
    config/pit/modificaciones) no se escriben en src/ ni en tests/: las pruebas los leen de config."""
    assert len(_nombres_de_config(RAIZ)) > 10, 'la comprobación leyó de verdad las transcripciones'
    hallados = _nombres_en_src_y_tests(RAIZ)
    assert not hallados, hallados


def test_un_nombre_con_otra_tilde_o_en_minusculas_salta_y_una_excepcion_no():
    """107:RF-11 — la coincidencia es por palabra completa, sin tildes ni mayúsculas; una palabra de la lista de
    excepciones no salta, y una palabra que solo contiene el nombre tampoco."""
    nombres = {_sin_tildes('Pampa Ñandú')}
    assert _hallar_nombres(nombres, 'la set pampa nandu') == ['pampa nandu']
    assert _hallar_nombres(nombres, 'LA SET PAMPA ÑANDU') == ['pampa nandu']
    assert _hallar_nombres(nombres, 'pampa nanduti') == []
    excepcion = next(iter(EXCEPCIONES_NOMBRES))
    assert excepcion not in _nombres_de_config(RAIZ) and EXCEPCIONES_NOMBRES[excepcion]
    assert _hallar_nombres(_nombres_de_config(RAIZ), f'el {excepcion.upper()} del área') == []
    assert all(motivo for motivo in NOMBRES_TOLERADOS.values())


def test_el_trinquete_no_deja_tolerados_que_sobran():
    """107:RF-11 (NOMBRES-REG, trinquete de c3) — NOMBRES_TOLERADOS solo encoge: cada entrada sigue hallándose en su
    fichero; la que ya no, sobra y la prueba la nombra para que se quite."""
    sobran = _tolerados_que_sobran(RAIZ)
    assert not sobran, ('quitar de NOMBRES_TOLERADOS: su nombre ya no está en el fichero', sobran)


def _raiz_sintetica(tmp_path, ficheros):
    """Un repositorio mínimo con una transcripción de config de nombres inventados y los .py dados."""
    (tmp_path / 'config' / 'normativa').mkdir(parents=True)
    (tmp_path / 'config' / 'pit' / 'modificaciones').mkdir(parents=True)
    (tmp_path / 'config' / 'normativa' / 'x.json').write_text(json.dumps({'normas': [{'reglas': [{'valor': [
        {'titular': 'Compañía Zeta Austral', 'instalacion': 'SET AT/MT Llano Quíntuple'}]}]}]}), encoding='utf-8')
    for rel, texto in ficheros.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(texto, encoding='utf-8')
    return tmp_path


def test_el_trinquete_salta_por_un_nombre_nuevo_y_por_una_entrada_que_sobra(tmp_path):
    """107:RF-11 (NOMBRES-REG) — las dos ramas del trinquete, con nombres inventados: (1) un nombre en un fichero que
    la tabla no lista salta; (2) una entrada de la tabla cuyo fichero ya no lo tiene, o que ya no existe, sobra. Con la
    tabla justa, ninguna de las dos salta."""
    zeta, llano = _huella_nombre('compania zeta austral'), _huella_nombre('llano quintuple')
    raiz = _raiz_sintetica(tmp_path, {'src/pkg/a.py': 'X = 1\n', 'tests/test_a.py': '# la SET llano quíntuple\n',
                                      'tests/test_b.py': 'EMPRESA = "COMPAÑÍA ZETA AUSTRAL"\n'})
    justa = {('tests/test_a.py', llano): 'motivo', ('tests/test_b.py', zeta): 'motivo'}
    assert _nombres_en_src_y_tests(raiz, justa) == [] and _tolerados_que_sobran(raiz, justa) == []
    # Rama 1: un nombre en un fichero que la tabla no lista.
    (raiz / 'src' / 'pkg' / 'a.py').write_text('# Compania Zeta Austral\nX = 1\n', encoding='utf-8')
    assert _nombres_en_src_y_tests(raiz, justa) == [('src/pkg/a.py', zeta)]
    # Rama 2: el dueño limpia test_b.py y su entrada se queda: sobra. La de un fichero que no existe, también.
    (raiz / 'tests' / 'test_b.py').write_text('EMPRESA = leer_de_config()\n', encoding='utf-8')
    con_fantasma = {**justa, ('tests/test_borrado.py', llano): 'motivo'}
    assert _tolerados_que_sobran(raiz, con_fantasma) == [('tests/test_b.py', zeta), ('tests/test_borrado.py', llano)]
    assert _nombres_en_src_y_tests(raiz, con_fantasma) == [('src/pkg/a.py', zeta)], 'la rama 1 sigue aparte'


def test_el_escaner_ve_los_nombres_como_claves_de_empresas_y_como_tramo_de_una_clave(tmp_path):
    """107:RF-11 (NOMBRES-001) — el escáner lee también los nombres que van como CLAVES de un diccionario bajo
    «empresas» (sin su paréntesis) y el último tramo con mayúscula de una «clave» de regla; un tramo en minúsculas no
    es un nombre."""
    raiz = _raiz_sintetica(tmp_path, {})
    (raiz / 'config' / 'normativa' / 'y.json').write_text(json.dumps({'normas': [{'reglas': [
        {'clave': 'vad.perdidas.causa_del_cambio.Distribuidora Omega', 'valor': {'empresas': {
            'Eléctrica Sigma Norte (administrada por Omega)': 1, 'Kappa Servicios': 2}}},
        {'clave': 'vad.perdidas.factor_minusculas', 'valor': 0}]}]}), encoding='utf-8')
    nombres = _nombres_de_config(raiz)
    assert {'distribuidora omega', 'electrica sigma norte', 'kappa servicios'} <= nombres
    assert 'factor_minusculas' not in nombres and not any('administrada' in n for n in nombres)
    assert 'kappa servicios' in _hallar_nombres(nombres, '# lo entrega Kappa Servicios')  # (y su primer tramo, NOMBRES-COM)


def test_tolerados_vacia_y_pendientes_con_tipo_tarjeta_y_responsable():
    """107:RF-11 (NOMBRES-001) — NOMBRES_TOLERADOS queda vacía, y cada pendiente dice su tipo, su tarjeta y su
    responsable, con la regla de reparto de c3 y f4."""
    assert NOMBRES_TOLERADOS == {}
    assert NOMBRES_PENDIENTES_POR_TARJETA == {}, 'NOMBRES-SRC, NOMBRES-COM y NOMBRES-TST cerradas: la tabla no vuelve'
    reparto = {('logica', 'src'): ('NOMBRES-SRC', 'f4'), ('logica', 'tests'): ('NOMBRES-TST', '2e'),
               ('comentario', 'src'): ('NOMBRES-COM', '2e'), ('comentario', 'tests'): ('NOMBRES-COM', '2e')}
    for (fichero, huella), e in NOMBRES_PENDIENTES_POR_TARJETA.items():
        assert re.fullmatch(r'[0-9a-f]{16}', huella) and e['tipo'] in ('logica', 'comentario')
        assert (e['tarjeta'], e['responsable']) == reparto[(e['tipo'], fichero.split('/', 1)[0])], fichero

def test_el_escaner_ve_la_sigla_el_nombre_pegado_y_el_primer_tramo(tmp_path):
    """107:RF-11 (NOMBRES-COM) — tres formas más de un nombre de empresa: la sigla de un perfil real (no de uno
    ficticio), la forma sin espacios y el primer tramo distintivo; siempre como palabra entera (el guion bajo separa),
    nunca como subcadena, y el primer tramo genérico no cuenta."""
    raiz = _raiz_sintetica(tmp_path, {})
    (raiz / 'config' / 'normativa' / 'y.json').write_text(json.dumps({'normas': [{'reglas': [{'valor': {'empresas': {
        'Volta Riberas Altas': 1, 'Electro Quinua': 2}}}]}]}), encoding='utf-8')
    (raiz / 'config' / 'perfiles').mkdir(parents=True)
    (raiz / 'config' / 'perfiles' / 'real.json').write_text(json.dumps({'codigo_empresa': 'VRAX'}), encoding='utf-8')
    (raiz / 'config' / 'perfiles' / 'ficticia.json').write_text(json.dumps({'codigo_empresa': 'FICT'}), encoding='utf-8')
    nombres = _nombres_de_config(raiz)
    assert {'vrax', 'voltariberasaltas', 'volta', 'electroquinua'} <= nombres
    assert 'fict' not in nombres and 'electro' not in nombres, 'ni el perfil ficticio ni un primer tramo genérico'
    assert _hallar_nombres(nombres, 'copia VRAX_VNR_24.bak y Perdidas_VRAX') == ['vrax']
    assert _hallar_nombres(nombres, '# la entrega de VoltaRiberasAltas') == ['voltariberasaltas']
    assert _hallar_nombres(nombres, 'voltaje y revoltas') == [], 'nunca una subcadena'


def test_con_la_config_real_el_escaner_ve_las_tres_formas():
    """107:RF-11 (NOMBRES-COM, condición de f4) — con la config real, el escáner ve la sigla, la forma pegada y el
    primer tramo que el escáner de NOMBRES-001 dejaba pasar (se nombran por su huella, no escritos)."""
    vistas = {_huella_nombre(n) for n in _nombres_de_config(RAIZ)}
    faltan = sorted({'805e8d7fa83d918c', 'd3b53601591f64c1', '820cf85713a4a1aa'} - vistas)
    assert not faltan, ('el escáner no ve estas formas de nombres reales (huellas)', faltan)
