"""068 — órdenes reales, etiquetas de plata del maestro y currículo de estilo real, sin tocar la prueba sellada.

Todo es sintético: ningún texto real del operador ni de la distribuidora entra en este fichero (P9).
"""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]
ETIQUETA_OK = {'id': 'a1', 'texto': 'has la conversion de AB101', 'tarea': 'convertir',
               'datos': {'alimentadores': ['AB101']}, 'confianza': .9,
               'quality': 'silver_maestro_texto_real', 'maestro': 'claude'}


@pytest.fixture(scope='module')
def herramienta():
    especificacion = importlib.util.spec_from_file_location(
        'asistente_ordenes_reales', RAIZ / 'tools' / 'asistente_ordenes_reales.py')
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[especificacion.name] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


def _jsonl(ruta: Path, filas) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(''.join((f if isinstance(f, str) else json.dumps(f, ensure_ascii=False)) + '\n' for f in filas),
                    encoding='utf-8')


def _usuario(texto, **extra):
    return {'type': 'user', 'message': {'role': 'user', 'content': texto}, **extra}


def _sesiones(tmp_path, raiz='D:\\obra\\proyecto'):
    """Un árbol de sesiones con cada caso que debe entrar o no."""
    claude = tmp_path / 'claude'
    _jsonl(claude / 's1.jsonl', [
        _usuario('corre el flujo de AB101'),
        _usuario('corre   el flujo de ab101'),                                     # el mismo, otra forma
        _usuario([{'type': 'text', 'text': 'has el dgs de CD202'}]),
        _usuario([{'type': 'tool_result', 'content': 'salida de herramienta larga'}]),
        _usuario('<system-reminder>recordatorio</system-reminder>'),
        _usuario('<command-name>/clear</command-name>'),
        _usuario('mensaje de una cadena lateral', isSidechain=True),
        _usuario('mensaje meta del sistema', isMeta=True),
        _usuario('hola'),                                                          # muy corto
        _usuario('x' * 401),                                                       # muy largo
        {'type': 'assistant', 'message': {'role': 'assistant', 'content': 'respuesta del asistente'}},
        'línea rota {',
    ])
    codex = tmp_path / 'codex'
    meta = {'type': 'session_meta', 'payload': {'cwd': raiz, 'source': 'vscode', 'thread_source': 'user'}}
    _jsonl(codex / '2026' / 'a.jsonl', [
        meta, {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'evalua el gemelo otra vez'}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                              'content': [{'type': 'input_text', 'text': 'contexto inyectado'}]}}])
    _jsonl(codex / '2026' / 'b.jsonl', [
        {'type': 'session_meta', 'payload': {'cwd': raiz + '\\.worktrees\\x', 'source': 'vscode'}},
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'lee los proyectos ahora'}}])
    _jsonl(codex / '2026' / 'otro.jsonl', [
        {'type': 'session_meta', 'payload': {'cwd': 'D:\\otro\\sitio', 'source': 'vscode'}},
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'orden de otro proyecto'}}])
    _jsonl(codex / '2026' / 'sub.jsonl', [
        {'type': 'session_meta', 'payload': {'cwd': raiz, 'thread_source': 'subagent',
                                             'source': {'subagent': {'thread_spawn': {}}}}},
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'encargo de un agente a otro'}}])
    return claude, codex, raiz


def _extraer(herramienta, tmp_path):
    claude, codex, raiz = _sesiones(tmp_path)
    almacen = tmp_path / 'almacen'
    _jsonl(almacen / 'ordenes.jsonl', [{'texto': 'que hay cargado', 'tarea': 'estado'}])
    assert herramienta.main(['extraer', '--almacen', str(almacen), '--claude', str(claude),
                             '--codex', str(codex), '--raiz-proyecto', raiz]) == 0
    filas = [json.loads(x) for x in (almacen / 'maestro_real' / 'textos.jsonl').read_text('utf-8').splitlines()]
    return filas, almacen


def test_extraer_reune_las_tres_fuentes(herramienta, tmp_path):
    """068:RF-1 / 068:RF-2 / 068:RF-3 — Claude Code, Codex del proyecto y el registro de órdenes."""
    filas, _ = _extraer(herramienta, tmp_path)
    por_fuente = {f['texto']: f['fuentes'] for f in filas}
    assert por_fuente['has el dgs de CD202'] == ['claude']
    assert por_fuente['evalua el gemelo otra vez'] == ['codex']
    assert por_fuente['lee los proyectos ahora'] == ['codex']
    assert por_fuente['que hay cargado'] == ['asistente']
    assert 'orden de otro proyecto' not in por_fuente


def test_extraer_descarta_lo_que_no_escribio_el_usuario(herramienta, tmp_path):
    """068:RF-4 — herramientas, recordatorios, meta, cadena lateral y etiquetas no son del usuario."""
    filas, _ = _extraer(herramienta, tmp_path)
    textos = ' | '.join(f['texto'] for f in filas)
    for ajeno in ('salida de herramienta', 'recordatorio', '/clear', 'cadena lateral', 'meta del sistema',
                  'respuesta del asistente', 'contexto inyectado'):
        assert ajeno not in textos


def test_extraer_descarta_sesiones_lanzadas_por_otro_agente(herramienta, tmp_path):
    """068:RF-5 — en una sesión hija de Codex, el «usuario» es el agente que la lanzó."""
    filas, _ = _extraer(herramienta, tmp_path)
    assert not any('encargo de un agente' in f['texto'] for f in filas)


def test_extraer_limita_la_longitud(herramienta, tmp_path):
    """068:RF-6 — menos de 5 o más de 400 caracteres no son una orden."""
    filas, _ = _extraer(herramienta, tmp_path)
    assert all(5 <= len(f['texto']) <= 400 for f in filas)
    assert not any(f['texto'] == 'hola' for f in filas)


def test_extraer_deduplica_y_cuenta(herramienta, tmp_path):
    """068:RF-7 — el mismo texto con otros espacios o mayúsculas es uno, con sus apariciones."""
    filas, _ = _extraer(herramienta, tmp_path)
    flujo = [f for f in filas if f['texto'].casefold().startswith('corre')]
    assert len(flujo) == 1 and flujo[0]['veces'] == 2


def test_extraer_separa_ordenes_de_charla(herramienta):
    """068:RF-8 — se separan sin descartar; las erratas del imperativo no lo vuelven charla."""
    assert herramienta.clase_de('has el dgs de AB101') == 'orden'
    assert herramienta.clase_de('Corre el flujo de AB101') == 'orden'
    assert herramienta.clase_de('me parece que esto ya estaba bien la semana pasada') == 'charla'
    assert herramienta.clase_de('sí') == 'charla'


def test_extraer_escribe_de_forma_atomica(herramienta, tmp_path, monkeypatch):
    """068:RF-9 — un corte al publicar deja el fichero anterior entero."""
    almacen = tmp_path / 'almacen'
    claude, codex, raiz = _sesiones(tmp_path)
    destino = almacen / 'maestro_real' / 'textos.jsonl'
    destino.parent.mkdir(parents=True)
    destino.write_text('anterior\n', encoding='utf-8')
    monkeypatch.setattr(herramienta.os, 'replace', lambda *_a: (_ for _ in ()).throw(OSError('corte')))
    with pytest.raises(OSError):
        herramienta.main(['extraer', '--almacen', str(almacen), '--claude', str(claude),
                          '--codex', str(codex), '--raiz-proyecto', raiz])
    assert destino.read_text('utf-8') == 'anterior\n'
    assert [p.name for p in destino.parent.iterdir()] == ['textos.jsonl']


# ------------------------------------------------------------------ revisión humana

def _etiquetas(almacen: Path, filas) -> None:
    _jsonl(almacen / 'maestro_real' / 'etiquetas.jsonl', filas)


def _etiqueta(texto, tarea='convertir', datos=None, id_=None, confianza=.9):
    return {'id': id_ or texto[:12], 'texto': texto, 'tarea': tarea, 'datos': datos or {}, 'confianza': confianza,
            'quality': 'silver_maestro_texto_real', 'maestro': 'claude'}


def _marcar(ruta: Path, marcas: dict[str, tuple]) -> None:
    import openpyxl
    libro = openpyxl.load_workbook(ruta)
    hoja = libro.active
    cab = {c.value: c.column for c in hoja[1]}
    for fila in range(2, hoja.max_row + 1):
        texto = hoja.cell(fila, cab['texto']).value
        if texto in marcas:
            hoja.cell(fila, cab['¿correcta? (s/n)']).value = marcas[texto][0]
            hoja.cell(fila, cab['tarea correcta']).value = marcas[texto][1] if len(marcas[texto]) > 1 else None
    libro.save(ruta)


def _revision(herramienta, tmp_path, filas):
    almacen = tmp_path / 'almacen'
    _etiquetas(almacen, filas)
    assert herramienta.main(['exportar', '--almacen', str(almacen)]) == 0
    return almacen, almacen / 'maestro_real' / 'revision.xlsx'


def _ejemplos(almacen):
    ruta = almacen / 'ejemplos.jsonl'
    return [json.loads(x) for x in ruta.read_text('utf-8').splitlines()] if ruta.is_file() else []


def test_revision_tiene_sus_columnas_y_solo_las_ordenes(herramienta, tmp_path):
    """068:RF-10 — las columnas pedidas, vacías las del operador, sin lo que el maestro descartó."""
    import openpyxl
    _, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK, _etiqueta('esto es charla', 'ninguna')])
    hoja = openpyxl.load_workbook(ruta).active
    cabecera = [c.value for c in hoja[1]]
    assert cabecera[:5] == ['texto', 'tarea propuesta', 'datos propuestos', '¿correcta? (s/n)', 'tarea correcta']
    filas = list(hoja.iter_rows(min_row=2, values_only=True))
    assert [f[0] for f in filas] == [ETIQUETA_OK['texto']]
    assert filas[0][1] == 'convertir' and 'AB101' in filas[0][2] and filas[0][3] is None and filas[0][4] is None


def test_revision_no_ejecuta_formulas(herramienta, tmp_path):
    """068:RF-11 — un mensaje que empieza por «=» es texto, nunca una fórmula de la hoja."""
    import openpyxl
    texto = '=HYPERLINK("http://x","y") corre esto'
    _, ruta = _revision(herramienta, tmp_path, [_etiqueta(texto, 'estado')])
    celda = openpyxl.load_workbook(ruta).active.cell(2, 1)
    assert celda.data_type == 's' and celda.value == texto


def test_revision_exportar_otra_vez_conserva_las_marcas(herramienta, tmp_path):
    """068:RF-12 — volver a exportar no borra el trabajo del operador."""
    import openpyxl
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK, _etiqueta('corre todo', 'estado')])
    _marcar(ruta, {ETIQUETA_OK['texto']: ('s',)})
    assert herramienta.main(['exportar', '--almacen', str(almacen)]) == 0
    filas = {f[0]: f for f in openpyxl.load_workbook(ruta).active.iter_rows(min_row=2, values_only=True)}
    assert filas[ETIQUETA_OK['texto']][3] == 's' and filas['corre todo'][3] is None


def test_revision_sin_marca_no_se_importa(herramienta, tmp_path):
    """068:RF-13 — quien nunca marca es el código: una fila sin marca no entra."""
    almacen, _ = _revision(herramienta, tmp_path, [ETIQUETA_OK, _etiqueta('corre todo', 'estado')])
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert _ejemplos(almacen) == []


@pytest.mark.parametrize('marca', ['s', 'S', 'si', 'Sí', ' sí '])
def test_revision_marcada_correcta_es_confirmado(herramienta, tmp_path, marca):
    """068:RF-14 — lo marcado entra como confirmado, con su dato en su posición."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK, _etiqueta('corre todo', 'estado')])
    _marcar(ruta, {ETIQUETA_OK['texto']: (marca,)})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    ejemplos = _ejemplos(almacen)
    assert len(ejemplos) == 1
    e = ejemplos[0]
    assert e['origen'] == 'confirmado' and e['tarea'] == 'convertir' and e['texto'] == ETIQUETA_OK['texto']
    a, b, tipo = e['datos'][0]
    assert e['texto'][a:b] == 'AB101' and tipo == 'alimentadores'


def test_revision_corregida_guarda_la_tarea_del_operador(herramienta, tmp_path):
    """068:RF-15 — con «n» y su tarea, manda el operador y solo quedan los datos que esa tarea admite."""
    fila = _etiqueta('informe de AB101 en P1', 'obras', {'alimentadores': ['AB101'], 'proyecto': ['P1']})
    almacen, ruta = _revision(herramienta, tmp_path, [fila])
    _marcar(ruta, {fila['texto']: ('n', 'estudios')})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    e = _ejemplos(almacen)[0]
    assert e['origen'] == 'corregido' and e['tarea'] == 'estudios' and len(e['datos']) == 2
    fila2 = _etiqueta('informe de AB101', 'convertir', {'alimentadores': ['AB101']}, id_='otra')
    almacen2, ruta2 = _revision(herramienta, tmp_path / 'b', [fila2])
    _marcar(ruta2, {fila2['texto']: ('n', 'proyectos')})                     # «proyectos» no lleva datos
    assert herramienta.main(['importar', '--almacen', str(almacen2)]) == 0
    assert _ejemplos(almacen2)[0]['datos'] == []


def test_revision_incorrecta_sin_tarea_no_entra(herramienta, tmp_path):
    """068:RF-16 — sin la tarea correcta no hay nada que aprender de esa fila."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK])
    _marcar(ruta, {ETIQUETA_OK['texto']: ('n',)})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert _ejemplos(almacen) == []


def test_revision_no_contradice_lo_ya_confirmado(herramienta, tmp_path, capsys):
    """068:RF-17 — dos etiquetas humanas distintas para un texto romperían ``preparar_corpus``."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK])
    previo = {'texto': ETIQUETA_OK['texto'].upper(), 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'}
    _jsonl(almacen / 'ejemplos.jsonl', [previo])
    _marcar(ruta, {ETIQUETA_OK['texto']: ('s',)})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert _ejemplos(almacen) == [previo]
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['contradicen'] == 1


def test_revision_marca_que_no_se_entiende_no_importa_nada(herramienta, tmp_path, capsys):
    """068:RF-18 — no se adivina una marca, y se nombra la fila."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK, _etiqueta('corre todo', 'estado')])
    _marcar(ruta, {ETIQUETA_OK['texto']: ('s',), 'corre todo': ('quizas',)})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 2
    assert _ejemplos(almacen) == []
    assert 'fila 3' in capsys.readouterr().out


def test_revision_fallo_a_mitad_deja_ejemplos_como_estaba(herramienta, tmp_path, monkeypatch):
    """068:RF-19 — todo o nada, conservando byte a byte lo anterior (también una línea rota)."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK])
    original = '{"texto": "carga la fuente", "tarea": "cargar_fuente", "datos": [], "origen": "confirmado"}\nlinea rota\n'
    (almacen / 'ejemplos.jsonl').write_text(original, encoding='utf-8')
    _marcar(ruta, {ETIQUETA_OK['texto']: ('s',)})
    monkeypatch.setattr(herramienta.os, 'replace', lambda *_a: (_ for _ in ()).throw(OSError('corte')))
    with pytest.raises(OSError):
        herramienta.main(['importar', '--almacen', str(almacen)])
    assert (almacen / 'ejemplos.jsonl').read_text('utf-8') == original
    monkeypatch.undo()
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert (almacen / 'ejemplos.jsonl').read_text('utf-8').startswith(original)


def test_revision_importar_dos_veces_no_duplica(herramienta, tmp_path):
    """068:RF-20 — idempotente."""
    almacen, ruta = _revision(herramienta, tmp_path, [ETIQUETA_OK])
    _marcar(ruta, {ETIQUETA_OK['texto']: ('s',)})
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert herramienta.main(['importar', '--almacen', str(almacen)]) == 0
    assert len(_ejemplos(almacen)) == 1


# ------------------------------------------------------------------ etiquetas

def test_etiqueta_valida_y_sus_campos(tmp_path):
    """068:RF-21 — la calidad nueva, su maestro y su confianza llegan al ejemplo."""
    from convertersmartgrid.asistente.maestro_real import CALIDAD, leer_etiquetas
    _etiquetas(tmp_path, [ETIQUETA_OK])
    filas, cuenta = leer_etiquetas(tmp_path)
    assert CALIDAD == 'silver_maestro_texto_real'
    assert filas[0]['maestro'] == 'claude' and filas[0]['confianza'] == .9
    a, b, tipo = filas[0]['spans'][0]
    assert filas[0]['texto'][a:b] == 'AB101' and tipo == 'alimentadores' and cuenta['validas'] == 1


def test_etiqueta_de_calidad_ajena_se_rechaza(tmp_path):
    """068:RF-21 — este fichero no puede colar un oro humano."""
    from convertersmartgrid.asistente.maestro_real import leer_etiquetas
    _etiquetas(tmp_path, [{**ETIQUETA_OK, 'quality': 'gold_human'}])
    filas, cuenta = leer_etiquetas(tmp_path)
    assert not filas and cuenta['rechazadas_calidad'] == 1


def test_etiqueta_con_tarea_desconocida_se_rechaza(tmp_path):
    """068:RF-22 — una tarea fuera del catálogo se cuenta, no se fuerza."""
    from convertersmartgrid.asistente.maestro_real import leer_etiquetas
    _etiquetas(tmp_path, [{**ETIQUETA_OK, 'tarea': 'hacer_cafe'}])
    filas, cuenta = leer_etiquetas(tmp_path)
    assert not filas and cuenta['rechazadas_tarea'] == 1


def test_etiqueta_con_dato_que_no_esta_en_el_texto_se_rechaza(tmp_path):
    """068:RF-23 — un dato inventado no se etiqueta."""
    from convertersmartgrid.asistente.maestro_real import leer_etiquetas
    _etiquetas(tmp_path, [{**ETIQUETA_OK, 'datos': {'alimentadores': ['ZZ999']}}])
    filas, cuenta = leer_etiquetas(tmp_path)
    assert not filas and cuenta['rechazadas_datos'] == 1


def test_etiqueta_ninguna_o_dudosa_no_entra_al_corpus(tmp_path):
    """068:RF-24 — «ninguna» y las dudosas no enseñan al modelo."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import leer_etiquetas
    _etiquetas(tmp_path, [_etiqueta('xq no sale esto todavia', 'ninguna'), _etiqueta('dudosa QW111 quiza', 'convertir', confianza=.5)])
    filas, cuenta = leer_etiquetas(tmp_path)
    assert cuenta['ninguna'] == 1 and cuenta['dudosas'] == 1
    corpus, _ = preparar_corpus({}, [], por_familia=1, etiquetas_reales=filas)
    assert not any(r['texto'] in {'xq no sale esto todavia', 'dudosa QW111 quiza'} for r in corpus)


# ------------------------------------------------------------------ corpus

REAL = 'porfa calibra rapido ZX123 pues'


def _real(texto=REAL, tarea='convertir', valor='ZX123'):
    from convertersmartgrid.asistente.maestro_real import datos_a_spans
    return {'texto': texto, 'tarea': tarea, 'spans': datos_a_spans(texto, {'alimentadores': [valor]} if valor else {}),
            'confianza': .9, 'maestro': 'claude'}


def _sellado(filas):
    return {r['record_id']: r for r in filas if r['particion'] != 'entrenamiento'}


def test_corpus_etiquetas_solo_en_entrenamiento(tmp_path):
    """068:RF-25 — plata real al ajuste, como respuesta del maestro."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import CALIDAD
    filas, _ = preparar_corpus({}, [], por_familia=1, etiquetas_reales=[_real()])
    reales = [r for r in filas if r['quality'] == CALIDAD]
    assert reales and all(r['particion'] == 'entrenamiento' and r['del_maestro'] for r in reales)
    assert any(r['texto'] == REAL for r in reales)
    r = next(r for r in reales if r['texto'] == REAL)
    a, b, tipo = r['datos'][0]
    assert r['texto'][a:b] == 'ZX123' and tipo == 'alimentadores'


def test_corpus_sin_fuga_por_texto_normalizado():
    """068:RF-26 — una frase de prueba, de selección, humana o fija no entra, con tildes o signos distintos."""
    from convertersmartgrid.asistente.curriculo_maestro import FAMILIAS
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import CALIDAD
    from convertersmartgrid.asistente.ordenes_fijas import generar, repartir
    from convertersmartgrid.evaluacion_modelos import texto_canonico
    base, _ = preparar_corpus({}, [], por_familia=2)
    prueba = next(r for r in base if r['particion'] == 'prueba' and not r['datos'])
    seleccion = next(r for r in base if r['particion'] == 'seleccion' and not r['datos'])
    fija = next(e for e in repartir(generar({}))[1] if not e.datos)
    assert FAMILIAS  # las columnas siguen ahí
    etiquetas = [_real(prueba['texto'].upper() + '?', 'estado', None), _real(seleccion['texto'] + ' !', 'estado', None),
                 _real('que tal lo humano', 'estado', None), _real(fija.texto, fija.tarea, None)]
    humanas = [{'texto': 'Qué tal lo humano', 'tarea': 'estado', 'datos': [], 'origen': 'confirmado'}]
    filas, meta = preparar_corpus({}, humanas, por_familia=2, etiquetas_reales=etiquetas)
    entrenamiento = {texto_canonico(r['texto']) for r in filas if r['quality'] == CALIDAD}
    assert not entrenamiento
    assert meta['etiquetas_reales']['excluidas_por_fuga'] == 4


def test_corpus_sin_fuga_por_familia():
    """068:RF-27 — la misma frase con otro código es la misma familia."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import CALIDAD, firma_familia
    base, _ = preparar_corpus({}, [], por_familia=2)
    fila = next(r for r in base if r['particion'] == 'prueba' and len(r['datos']) == 1 and r['datos'][0][2] == 'alimentadores')
    a, b, _t = fila['datos'][0]
    otro = fila['texto'][:a] + 'QQ777' + fila['texto'][b:]
    assert firma_familia(otro, [[a, a + 5, 'alimentadores']]) == firma_familia(fila['texto'], fila['datos'])
    filas, meta = preparar_corpus({}, [], por_familia=2, etiquetas_reales=[_real(otro, fila['tarea'], 'QQ777')])
    assert not [r for r in filas if r['quality'] == CALIDAD and 'QQ777' in r['texto']]
    assert meta['etiquetas_reales']['excluidas_por_fuga'] == 1


def test_corpus_deja_identica_la_prueba_sellada():
    """068:RF-28 — con todo lo nuevo, selección, calibración y prueba son las mismas filas, sin más cuarentena."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    humanas = [{'texto': 'carga la fuente', 'tarea': 'cargar_fuente', 'datos': [], 'origen': 'confirmado'}]
    vocab = {'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto X'], 'sistema': ['Valle']}
    sin, meta_sin = preparar_corpus(vocab, humanas, por_familia=4, ampliar=False)
    con, meta_con = preparar_corpus(vocab, humanas, por_familia=4, etiquetas_reales=[_real()])
    assert _sellado(sin) == _sellado(con)
    assert meta_sin['cuarentena_hash'] == meta_con['cuarentena_hash']
    assert len(con) > len(sin)


def test_corpus_nada_nuevo_coincide_con_lo_apartado():
    """068:RF-26 / 068:RF-27 — ninguna fila añadida, tampoco una variante con erratas, repite lo sellado."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import clave_texto, firma_familia
    vocab = {'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto X'], 'sistema': ['Valle']}
    filas, _ = preparar_corpus(vocab, [], por_familia=6, etiquetas_reales=[_real()])
    apartadas = [r for r in filas if r['particion'] != 'entrenamiento']
    nuevas = [r for r in filas if r.get('origen_curriculo')]
    assert nuevas and apartadas
    textos, familias = {clave_texto(r['texto']) for r in apartadas}, {firma_familia(r['texto'], r['datos']) for r in apartadas}
    assert not [r for r in nuevas if clave_texto(r['texto']) in textos or firma_familia(r['texto'], r['datos']) in familias]


def test_corpus_prueba_sellada_de_la_linea_base():
    """068:RF-28 — la huella de lo sellado antes de esta spec, con un vocabulario fijo, no cambia."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.evaluacion_modelos import huella
    filas, _ = preparar_corpus({}, [], por_familia=5, etiquetas_reales=[_real()])
    # 070:RF-72: con las tareas nuevas, lo sellado antes de esa spec es la parte histórica.
    from convertersmartgrid.asistente.destilacion_integral import es_historica
    assert huella(sorted(r['record_id'] for r in filas if es_historica(r))) == HUELLA_PRUEBA_VACIA


def test_corpus_denominadores_separados():
    """068:RF-29 — cada calidad con su cuenta en cada partición (047:RF-13)."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import CALIDAD
    filas, meta = preparar_corpus({}, [], por_familia=2, etiquetas_reales=[_real()])
    denominadores = meta['denominadores']
    assert denominadores['entrenamiento'][CALIDAD] == sum(
        r['quality'] == CALIDAD and r['particion'] == 'entrenamiento' for r in filas)
    assert CALIDAD not in denominadores['prueba'] and CALIDAD not in denominadores['seleccion']
    assert sum(sum(v.values()) for v in denominadores.values()) == len(filas)
    assert meta['etiquetas_reales']['por_tarea'] == {'convertir': 1}


def test_corpus_plata_no_cuenta_como_humana():
    """068:RF-30 — plata del maestro no es oro humano (027:RF-67, 047:RF-11)."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    _, meta = preparar_corpus({}, [], por_familia=1, etiquetas_reales=[_real()])
    assert meta['ordenes_humanas_independientes'] == 0
    assert 'gold_human' not in meta['calidades']


def test_corpus_las_escrituras_siguen_pidiendo_confirmacion(tmp_path, monkeypatch):
    """068:RF-31 — las etiquetas no entran en ``ejemplos``, de donde se cuentan las confirmadas (027:RF-19)."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.interprete import Interpretacion
    from convertersmartgrid.asistente.plan import resolver
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    _etiquetas(tmp_path, [_etiqueta(f'convierte XX{i:03d}', 'convertir') for i in range(300)])
    assert almacen.leer('ejemplos') == []
    plan = resolver(Interpretacion('convierte AB101', 'convertir', 1., 'ensayo',
                                   {'alimentadores': [{'valor': 'AB101'}]}), {'alimentadores': ['AB101']})
    assert plan.escribe and any('confirmación' in r for r in plan.razonamiento)


def test_corpus_guardado_se_relee_con_la_calidad_nueva(tmp_path):
    """068:RF-32 — ``leer_corpus`` no rechaza lo que ``preparar_corpus`` acaba de escribir."""
    from convertersmartgrid.asistente.destilacion_integral import guardar_corpus, leer_corpus, preparar_corpus
    filas, meta = preparar_corpus({}, [], por_familia=1, etiquetas_reales=[_real()])
    guardar_corpus(tmp_path, filas, meta)
    assert leer_corpus(tmp_path)[1]['dataset_hash'] == meta['dataset_hash']


def test_corpus_las_herramientas_leen_las_etiquetas(tmp_path):
    """068:RF-33 — el camino real de ``preparar`` usa el almacén local."""
    datos = tmp_path / 'datos'
    _etiquetas(datos, [{**ETIQUETA_OK, 'texto': REAL, 'datos': {'alimentadores': ['ZX123']}}])
    import os
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'CSG_ASISTENTE_DATA': str(datos),
           'PYTHONPATH': str(RAIZ / 'src')}
    r = subprocess.run([sys.executable, str(RAIZ / 'tools/asistente_destilar.py'), 'preparar',
                        '--destino', str(tmp_path / 'corpus'), '--por-familia', '1'],
                       env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert r.returncode == 0, r.stderr + r.stdout
    assert json.loads(r.stdout)['etiquetas_reales']['usadas'] == 1
    fuente = (RAIZ / 'tools/asistente_entrenar.py').read_text(encoding='utf-8')
    assert 'etiquetas_reales=' in fuente


def test_corpus_determinista():
    """068:RF-34 — mismas entradas, mismo corpus."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    a = preparar_corpus({'alimentadores': ['AB101']}, [], por_familia=2, etiquetas_reales=[_real()])
    b = preparar_corpus({'alimentadores': ['AB101']}, [], por_familia=2, etiquetas_reales=[_real()])
    assert a[1]['dataset_hash'] == b[1]['dataset_hash']


# ------------------------------------------------------------------ currículo y erratas

def test_curriculo_estilo_real_cubre_cada_tarea():
    """068:RF-35 — al menos doce frases por tarea, y solo entrenan."""
    from convertersmartgrid.asistente.curriculo_maestro import ESTILO_REAL
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.tareas import TAREAS
    assert set(ESTILO_REAL) == set(TAREAS)
    assert all(len(set(v)) >= 12 for v in ESTILO_REAL.values())
    filas, _ = preparar_corpus({}, [], por_familia=2)
    estilo = [r for r in filas if r.get('origen_curriculo') == 'estilo_real']
    assert estilo and all(r['particion'] == 'entrenamiento' and r['del_maestro'] for r in estilo)


def test_curriculo_estilo_real_sin_nombres_reales():
    """068:RF-36 — los datos van entre llaves; ningún código con forma de alimentador en el código versionado."""
    from convertersmartgrid.asistente.curriculo_maestro import ESTILO_REAL
    from convertersmartgrid.asistente.tareas import TAREAS
    for tarea, frases in ESTILO_REAL.items():
        for frase in frases:
            assert not re.search(r'\b[A-Za-z]{2,3}\d{3}\b', frase), frase
            assert set(re.findall(r'\{(\w+)\}', frase)) <= {d.tipo for d in TAREAS[tarea].datos}, frase


def test_curriculo_familias_siguen_con_sus_cuatro_columnas():
    """068:RF-37 — la posición en ``FAMILIAS`` decide la partición; alargarla cambiaría la prueba."""
    from convertersmartgrid.asistente.curriculo_maestro import FAMILIAS
    from convertersmartgrid.evaluacion_modelos import huella
    from convertersmartgrid.asistente.tareas import TAREAS_HASTA_069
    assert all(len(v) == 4 for v in FAMILIAS.values())
    # 070:RF-72, RF-74: solo cambió una frase de entrenar; ni la selección, ni la calibración, ni la prueba.
    assert huella({t: FAMILIAS[t][1:] for t in TAREAS_HASTA_069}) == HUELLA_FAMILIAS_APARTADAS


def test_curriculo_erratas_deterministas_y_observadas():
    """068:RF-38 — misma semilla, misma variante; hay erratas de las reales, como «has» por «haz»."""
    import random
    from convertersmartgrid.asistente.maestro_real import con_erratas
    from convertersmartgrid.asistente.sinteticos import Ejemplo
    e = Ejemplo('haz el dgs del sistema electrico', 'convertir', [])
    a = [con_erratas(e, random.Random(i)).texto for i in range(200)]
    b = [con_erratas(e, random.Random(i)).texto for i in range(200)]
    assert a == b and len(set(a)) > 10
    assert any(x.startswith('has ') for x in a)
    assert e.texto == 'haz el dgs del sistema electrico'
    assert any(x != e.texto for x in a)


def test_curriculo_erratas_con_el_espacio_corrido():
    """068:RF-38 — «d etension», como en los mensajes reales, sin tocar el dato de al lado."""
    import random
    from convertersmartgrid.asistente.maestro_real import con_erratas
    from convertersmartgrid.asistente.sinteticos import Ejemplo
    e = Ejemplo('revisa de tension en AB101', 'flujo', [(21, 26, 'alimentadores')])
    variantes = [con_erratas(e, random.Random(i), prob=.6) for i in range(400)]
    assert any(' etension' in v.texto or 'd e' in v.texto for v in variantes)
    assert all(v.texto[v.datos[0][0]:v.datos[0][1]] == 'AB101' for v in variantes)


def test_curriculo_erratas_no_mueven_los_datos():
    """068:RF-39 — cada dato sigue señalando su valor, intacto."""
    import random
    from convertersmartgrid.asistente.maestro_real import con_erratas
    from convertersmartgrid.asistente.sinteticos import Ejemplo
    texto = 'calibra el sistema Valle Alto con las mediciones de 2026-07 en el proyecto AB101_CD202'
    e = Ejemplo(texto, 'sistema_completo', [(19, 29, 'sistema'), (52, 59, 'periodo'), (75, 86, 'proyecto')])
    assert [e.texto[a:b] for a, b, _t in e.datos] == ['Valle Alto', '2026-07', 'AB101_CD202']
    for i in range(300):
        v = con_erratas(e, random.Random(i))
        assert [v.texto[a:b] for a, b, _t in v.datos] == ['Valle Alto', '2026-07', 'AB101_CD202']
        assert [t for *_x, t in v.datos] == ['sistema', 'periodo', 'proyecto']


def test_curriculo_erratas_solo_en_entrenamiento():
    """068:RF-40 — ni selección ni calibración ni prueba reciben variantes."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    filas, _ = preparar_corpus({}, [], por_familia=2, etiquetas_reales=[_real()])
    con_errata = [r for r in filas if r.get('aumentado') == 'erratas']
    assert con_errata and all(r['particion'] == 'entrenamiento' for r in con_errata)
    assert not any(r.get('aumentado') for r in filas if r['particion'] != 'entrenamiento')


def test_curriculo_fijas_con_su_huella():
    """068:RF-41 — las 200 fijas y su prueba, con los valores anteriores a esta spec (027:RF-65, RF-66)."""
    from convertersmartgrid.asistente import ordenes_fijas as of
    fijas = of.generar({})
    assert of.huella(fijas) == '41f7ab110ac35c0b' and len(fijas) == 200
    assert of.huella(of.repartir(fijas)[1]) == HUELLA_FIJAS_PRUEBA


def test_curriculo_puertas_intactas():
    """068:RF-42 — ni política ni puertas se tocan para llegar."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion
    p = PoliticaEvaluacion(modo='agente')
    assert dict(p.puertas_por_familia) == {'acierto_tarea': .95, 'f1_datos': .85}
    assert p.hash == HUELLA_POLITICA


def test_extraer_no_carga_librerias_pesadas():
    """068:RF-1 — la herramienta corre sin torch: el equipo tiene poca memoria y la GPU es del integrador."""
    import os
    ruta = str(RAIZ / 'tools/asistente_ordenes_reales.py')
    codigo = '\n'.join(('import runpy, sys', 'sys.argv = ["x", "--help"]', 'try:',
                        f'    runpy.run_path({ruta!r}, run_name="__main__")', 'except SystemExit:', '    pass',
                        'print("torch" in sys.modules)'))
    env = {**os.environ, 'PYTHONPATH': str(RAIZ / 'src'), 'PYTHONIOENCODING': 'utf-8'}
    r = subprocess.run([sys.executable, '-c', codigo], env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.stdout.strip().endswith('False'), r.stdout + r.stderr


# Valores de antes de esta spec, medidos sobre el commit f72e46cb con las mismas entradas.
HUELLA_PRUEBA_VACIA = '415e425a481ddfb0bd3af7bdeb042cf82fa3f23fda1ef97f95b8b2f955d502f3'
HUELLA_FAMILIAS_APARTADAS = 'e9162f14716150cc9c1748c30adda47ce22dc8418880bce3293aa65f694f307c'
HUELLA_FIJAS_PRUEBA = '16b563b6381b2386'
HUELLA_POLITICA = 'd996a254903807e96892d08469947dc43b7be10124a8653cb17ff960ea47e894'
