"""Spec 076: preguntas por entregable, con su fuente comprobada, su reparto sellado y su hoja de revisión.

Las pruebas leen solo el repositorio: ni datos de la distribuidora, ni DIgSILENT, ni GPU. Los nombres privados
de clientes van como huellas con sal, para poder rechazarlos sin escribirlos aquí (076:RF-6).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict

import pytest

from apoyo import cargar_herramienta

PE = cargar_herramienta('preguntas_entregables.py')
RAIZ = PE.RAIZ

#: Huellas del contenido, fijadas al escribir el conjunto; cambiarlas es cambiar el conjunto (076:RF-7, RF-9).
#: 081:RF-70 (2026-11-03): catalogo_parametros-003, -004 y operacion_web-031, y los dos hechos del catálogo, revisados
#: porque el aviso «Reconvierta…» que citaban se corrigió; lo sellado no cambia.
HUELLA_CONJUNTO = '7a2ef176bd0cc04358b12f34057171376b85c53e20c7aff36b64d88f16c79875'
HUELLA_SELLADO = 'f6186156a2863c8734f100466a630b5720b0781336279dad0331c2bd13b2a00e'
HUELLA_HECHOS = 'cf9e05488d73c44b2c2a16f033edb41588779968ea419d9fe81e5f6c41b7b50d'

#: sha256('076:' + texto normalizado)[:16] de nombres de clientes y obras que solo salen en los casos de prueba.
NOMBRES_PRIVADOS = frozenset({'1d409437293f8e90', '3498bf03a218f2c3', '3e59bdab0a823374', '442eea8a24c9cc8b', 'a1a7c9ecc9d9117c',
                               'b1bcb0e7a64793e8', 'c207484c9b5d789b'})


@pytest.fixture(scope='module')
def filas():
    return PE.leer_jsonl(PE.DATASET)


@pytest.fixture(scope='module')
def hechos():
    return PE.leer_jsonl(PE.HECHOS)


def _fila(**extra):
    return {'id': 'x-1', 'entregable': 'x', 'aspecto': 'criterio', 'pregunta': '¿y esto?', 'tipo': 'con_respuesta',
            'respuesta_esperada': 'Sale del perfil.', 'estado_fuente': 'cumplida', 'origen': 'sintetico_maestro',
            'revisado_por_operador': False, 'grupo_parafrasis': 'x-1', 'reparto': 'corpus',
            'fuentes': [{'fichero': 'docs/constitution.md', 'linea': 10, 'ancla': 'Determinismo', 'rf': None}], **extra}


# ----------------------------------------------------------------- filas
def test_cada_fila_con_sus_campos(filas):
    """076:RF-1 — todos los campos, con su vocabulario, sintéticas y sin revisar al nacer salvo marca."""
    assert filas
    for f in filas:
        assert not PE.errores_de_forma(f), f['id']
    assert len({f['id'] for f in filas}) == len(filas)


def test_una_pregunta_por_criterio_y_estilo_de_operador(filas):
    """076:RF-1 — sin plantillas repetidas: ni la misma frase, ni el mismo arranque en todas."""
    textos = [PE.normalizar(f['pregunta']) for f in filas]
    assert len(set(textos)) == len(textos), [t for t, n in Counter(textos).items() if n > 1][:5]
    arranques = Counter(' '.join(t.split()[:3]) for t in textos)
    assert arranques.most_common(1)[0][1] < 0.05 * len(textos), arranques.most_common(3)
    # Parte con faltas y frases cortas, como escribe el operador.
    cortas = sum(len(t.split()) <= 8 for t in textos)
    assert cortas >= 0.15 * len(textos)
    assert sum(bool(PE.FALTAS.search(t)) for t in textos) >= 0.10 * len(textos)
    # Sin el «¿» de apertura ni mayúscula, como se teclea en el chat.
    assert sum(not f['pregunta'].startswith('¿') for f in filas) >= 0.30 * len(filas)


def test_minimos_por_entregable_y_tema(filas):
    """076:RF-2, 076:RF-17 — 12 y 3 por entregable, 20 y 5 por tema, y repartidas por aspecto."""
    cuenta = defaultdict(Counter)
    aspectos = defaultdict(set)
    for f in filas:
        cuenta[f['entregable']][f['tipo']] += 1
        if f['tipo'] == 'con_respuesta':
            aspectos[f['entregable']].add(f['aspecto'])
    assert set(PE.ENTREGABLES) | set(PE.TEMAS) == set(cuenta)
    for e in PE.ENTREGABLES:
        assert cuenta[e]['con_respuesta'] >= 12 and cuenta[e]['sin_respuesta'] >= 3, (e, cuenta[e])
    for t in PE.TEMAS:
        assert cuenta[t]['con_respuesta'] >= 20 and cuenta[t]['sin_respuesta'] >= 5, (t, cuenta[t])
    assert {'flujo_conversor', 'arquitectura', 'estudios', 'tipos_de_informe', 'operacion_web'} <= set(PE.TEMAS)
    for e, a in aspectos.items():
        assert len(a) >= 3, (e, a)


def test_sin_respuesta_lleva_su_motivo_y_lo_que_falta_se_dice(filas):
    """076:RF-3 — quien pregunte por algo que no está recibe que aún no está, con el motivo."""
    for f in filas:
        if f['tipo'] == 'sin_respuesta':
            assert f.get('motivo_sin_respuesta'), f['id']
    solo = [f for f in filas if f['estado_fuente'] == 'solo_especificada']
    assert solo
    for f in solo:
        assert re.search(r'(aun|todavia) no|no esta|no hay|no existe|solo especificad', PE.normalizar(f['respuesta_esperada'])), f['id']


# ----------------------------------------------------------------- fuentes
def test_cada_fuente_existe_en_la_revision(filas, hechos):
    """076:RF-4 — fichero, línea con su ancla en la revisión fijada, ancla en el árbol y RF definido."""
    errores = PE.errores_de_fuentes(filas) + PE.errores_de_fuentes(hechos)
    assert not errores, errores[:20]


def test_una_fuente_mala_se_rechaza():
    """076:RF-4 — línea, ancla, fichero o RF inventados no pasan."""
    assert not PE.errores_de_fuentes([_fila(fuentes=[{'fichero': 'docs/constitution.md', 'linea': 10,
                                                      'ancla': 'Determinismo', 'rf': None}])])
    for mala in ({'fichero': 'docs/no_existe.md', 'linea': 1, 'ancla': 'x', 'rf': None},
                 {'fichero': 'docs/constitution.md', 'linea': 11, 'ancla': 'Determinismo', 'rf': None},
                 {'fichero': 'docs/constitution.md', 'linea': 99999, 'ancla': 'Determinismo', 'rf': None},
                 {'fichero': 'docs/constitution.md', 'linea': 10, 'ancla': 'Determinismo', 'rf': '999:RF-1'},
                 {'fichero': 'docs/constitution.md', 'linea': 10, 'ancla': 'Determinismo', 'rf': '063:RF-9999'}):
        assert PE.errores_de_fuentes([_fila(fuentes=[mala])]), mala


def test_con_respuesta_sin_fuentes_no_vale():
    """076:RF-4 — una respuesta sin fuente es justo lo que este conjunto evita."""
    assert PE.errores_de_fuentes([_fila(fuentes=[])])


def test_cifras_de_la_respuesta_en_la_fuente(filas):
    """076:RF-5 — ninguna cifra de una respuesta esperada está fuera de sus fuentes."""
    errores = PE.errores_de_cifras(filas)
    assert not errores, errores[:20]


def test_una_cifra_inventada_se_rechaza():
    """076:RF-5 — el «sin cifras que no estén en la fuente» se comprueba, no se promete."""
    bien = _fila(respuesta_esperada='Sin cifras.')
    mal = _fila(respuesta_esperada='Tarda 4242 horas.')
    assert not PE.errores_de_cifras([bien])
    assert PE.errores_de_cifras([mal])


# ----------------------------------------------------------------- nombres
def _prohibidos():
    return PE.nombres_del_perfil(), PE.PATRONES_REALES, NOMBRES_PRIVADOS


def test_ningun_nombre_real(filas, hechos):
    """076:RF-6 — ni empresas, ni códigos del perfil, ni patrones, ni los nombres privados con huella."""
    nombres, patrones, privados = _prohibidos()
    assert len(nombres) > 50, 'la lista negativa se deriva del perfil y no puede quedar vacía'
    reglas = PE.leer_jsonl(PE.REGLAS)
    errores = PE.errores_de_nombres(filas + hechos + reglas, nombres, patrones, privados)
    assert not errores, errores[:20]


@pytest.mark.parametrize('texto', ['El codigo AB123 es de otro', 'en la barra de 60 kV de PA217'])
def test_un_codigo_real_se_rechaza(texto):
    """076:RF-6 — el patrón de alimentador no necesita la lista."""
    assert PE.errores_de_nombres([_fila(pregunta=texto)], set(), PE.PATRONES_REALES, frozenset())


def test_un_nombre_del_perfil_y_uno_privado_se_rechazan():
    """076:RF-6 — con la lista derivada y con la huella, también si cambia de mayúsculas y tildes."""
    assert PE.errores_de_nombres([_fila(pregunta='¿y en Zona Fíctia?')], {'zona fictia'}, (), frozenset())
    privado = hashlib.sha256('076:cliente ficticio'.encode()).hexdigest()[:16]
    assert PE.errores_de_nombres([_fila(pregunta='¿el CLIENTE ficticio?')], set(), (), frozenset({privado}))


def test_nada_de_datos_privados_en_las_rutas(filas):
    """076:RF-6 — ninguna fuente sale de `output/`, de `maestro_real/` ni de libros."""
    for f in filas:
        for s in f['fuentes']:
            assert not re.search(r'(^|/)(output|maestro_real)/|\.(xlsx|xlsb|xls|mdb|bak|pdf)$', s['fichero']), s


def test_las_fuentes_no_se_comparan(filas):
    """076:RF-18 — TXT, MDB y VNR-GIS son independientes: ninguna fila las compara ni pide la misma fecha."""
    for f in filas:
        t = PE.normalizar(f['pregunta'])
        nombres = sum(bool(re.search(p, t)) for p in (r'\btxt\b', r'\bmdb\b|\baccess\b', r'\bvnr\b'))
        if nombres >= 2:
            assert not re.search(r'compar|mezcl|mejor|diferenc|igual que', t) or f['tipo'] == 'sin_respuesta', f['id']


# ----------------------------------------------------------------- huella y reparto
def test_huella_fijada(filas, hechos):
    """076:RF-7 — el contenido no cambia sin cambiar aquí su huella."""
    assert PE.huella(filas) == HUELLA_CONJUNTO
    assert PE.huella([f for f in filas if f['reparto'] == 'sellado']) == HUELLA_SELLADO
    assert PE.huella(hechos) == HUELLA_HECHOS


def test_huella_no_depende_de_los_finales_de_linea(tmp_path, filas):
    """076:RF-7 — Git en Windows puede sacar CRLF: sigue siendo el mismo conjunto."""
    ruta = tmp_path / 'crlf.jsonl'
    ruta.write_bytes(''.join(json.dumps(f, ensure_ascii=False) + '\r\n' for f in filas).encode('utf-8'))
    assert PE.huella(PE.leer_jsonl(ruta)) == HUELLA_CONJUNTO


def test_reparto_declarado_y_sin_solape(filas):
    """076:RF-8 — el método en el docstring, reproducible, y ningún grupo ni respuesta en los dos lados."""
    assert 'sha256' in PE.repartir.__doc__ and PE.SAL_REPARTO in PE.repartir.__doc__
    calculado = PE.repartir(filas)
    assert {f['id']: f['reparto'] for f in filas} == calculado
    lados = defaultdict(set)
    for f in filas:
        lados[f['grupo_parafrasis']].add(f['reparto'])
    assert all(len(v) == 1 for v in lados.values())
    cor = {PE.normalizar(f['respuesta_esperada']) for f in filas if f['reparto'] == 'corpus'}
    sel = {PE.normalizar(f['respuesta_esperada']) for f in filas if f['reparto'] == 'sellado'}
    assert not cor & sel, sorted(cor & sel)[:5]
    assert not ({PE.normalizar(f['pregunta']) for f in filas if f['reparto'] == 'corpus'}
                & {PE.normalizar(f['pregunta']) for f in filas if f['reparto'] == 'sellado'})


def test_cada_entregable_con_sellado_de_los_dos_tipos(filas):
    """076:RF-8 — sin esto no se podría medir la abstención por entregable."""
    for e in PE.ENTREGABLES + PE.TEMAS:
        de_e = [f for f in filas if f['entregable'] == e and f['reparto'] == 'sellado']
        assert {'con_respuesta', 'sin_respuesta'} == {f['tipo'] for f in de_e}, e


def test_hay_grupos_de_parafrasis(filas):
    """076:RF-8 — un grupo con varias frases cae entero a un lado: para eso se reparte por grupos."""
    grupos = Counter(f['grupo_parafrasis'] for f in filas)
    assert sum(n > 1 for n in grupos.values()) >= 10


def test_revisar_no_toca_la_huella(filas):
    """076:RF-9 — la marca del operador queda fuera: revisar lo sellado no lo cambia."""
    marcadas = [{**f, 'revisado_por_operador': True, 'revision': {'veredicto': 'incorrecta', 'correccion': 'x'}} for f in filas]
    assert PE.huella(marcadas) == PE.huella(filas)
    otra = [{**filas[0], 'respuesta_esperada': filas[0]['respuesta_esperada'] + ' y más'}] + filas[1:]
    assert PE.huella(otra) != PE.huella(filas)


# ----------------------------------------------------------------- reglas, contradicciones, alcance
def test_reglas_del_operador_aparte_y_sin_darlas_por_hechas(filas):
    """076:RF-14 — lo de las memorias que el código no confirma no se mezcla con lo comprobado."""
    reglas = PE.leer_jsonl(PE.REGLAS)
    assert reglas
    for r in reglas:
        assert r['estado_fuente'] == 'regla_operador_sin_codigo' and r['revisado_por_operador'] is False
        assert re.search(r'sin confirmar|no se da por hech', PE.normalizar(r['respuesta_esperada']))
    assert not [f for f in filas if f['estado_fuente'] == 'regla_operador_sin_codigo']


def test_contradicciones_con_sus_dos_fuentes():
    """076:RF-15 — cada contradicción cita el documento y el código; se anota, manda el código."""
    h = json.loads(PE.HUECOS.read_text(encoding='utf-8'))
    assert h['contradicciones']
    for c in h['contradicciones']:
        assert c['documento'] and c['codigo'] and c['nota']
    assert not PE.errores_de_fuentes([
        {'id': f'contradiccion-{i}', 'fuentes': [c['documento'], c['codigo']], 'tipo': 'con_respuesta'}
        for i, c in enumerate(h['contradicciones'])])


def test_no_entra_al_rag_ni_a_entrenar():
    """076:RF-16 — nada de `src/` lee este conjunto, y los sellados del RAG siguen como en la revisión fijada."""
    for ruta in (RAIZ / 'src').rglob('*.py'):
        assert 'preguntas_entregables' not in ruta.read_text(encoding='utf-8', errors='ignore'), ruta
    for ruta in sorted((RAIZ / 'docs').glob('RAG_*.json')):
        rel = ruta.relative_to(RAIZ).as_posix()
        fijado = subprocess.run(['git', 'show', f'{PE.REVISION}:{rel}'], cwd=RAIZ, capture_output=True, check=True).stdout
        assert json.loads(fijado) == json.loads(ruta.read_text(encoding='utf-8')), rel


def test_bancos_y_valle_queda_pendiente(filas):
    """076:RF-26 — sin 073 en la rama no hay filas de «bancos y valle», y el informe lo dice."""
    assert not [f for f in filas if 'valle' in f['entregable']]
    h = json.loads(PE.HUECOS.read_text(encoding='utf-8'))
    assert any('073' in p for p in h['pendientes'])
    assert 'bancos y valle' in PE.informe_md(filas, h).lower()


# ----------------------------------------------------------------- hoja de revisión
def _hoja(tmp_path, filas, marcas):
    """Exporta y escribe marcas; ``marcas``: id → (marca, corrección)."""
    from openpyxl import load_workbook

    ruta = tmp_path / 'hoja.xlsx'
    PE.exportar(filas, [], ruta)
    libro = load_workbook(ruta)
    hoja = libro.active
    cab = [c.value for c in hoja[1]]
    for fila in hoja.iter_rows(min_row=2):
        i = fila[cab.index('id')].value
        if i in marcas:
            fila[cab.index('¿correcta? s/n')].value = marcas[i][0]
            fila[cab.index('corrección')].value = marcas[i][1]
    libro.save(ruta)
    return ruta


def _conjunto(tmp_path, n=4):
    ruta = tmp_path / 'c.jsonl'
    filas = [_fila(id=f'x-{i}', grupo_parafrasis=f'x-{i}', pregunta=f'¿pregunta {i}?') for i in range(n)]
    PE.escribir_jsonl(ruta, filas)
    return ruta, filas


def test_exportar_con_sus_columnas(tmp_path, filas):
    """076:RF-10 — pregunta, respuesta esperada, fuente, «¿correcta? s/n» y corrección."""
    from openpyxl import load_workbook

    ruta = tmp_path / 'h.xlsx'
    PE.exportar(filas[:5], [], ruta)
    hoja = load_workbook(ruta).active
    assert [c.value for c in hoja[1]] == ['id', 'pregunta', 'respuesta esperada', 'fuente', '¿correcta? s/n', 'corrección']
    assert hoja.max_row == 6
    assert re.search(r'\w+:\d+', hoja['D2'].value)


def test_exportar_va_a_output_fuera_de_git():
    """076:RF-10 — el destino por defecto está en `output/`, que git ignora."""
    assert PE.HOJA.relative_to(RAIZ).parts[0] == 'output'
    r = subprocess.run(['git', 'check-ignore', '-q', PE.HOJA.as_posix()], cwd=RAIZ, check=False)
    assert r.returncode == 0


def test_importar_marca_solo_lo_marcado_y_no_duplica(tmp_path):
    """076:RF-11, RF-12 — lo no marcado sigue sin revisar; importar dos veces da lo mismo."""
    ruta, filas = _conjunto(tmp_path)
    hoja = _hoja(tmp_path, filas, {'x-0': ('s', None), 'x-1': ('N', 'era otra cosa')})
    assert PE.importar(hoja, ruta) == {'correctas': 1, 'incorrectas': 1, 'sin_marca': 2}
    leidas = {f['id']: f for f in PE.leer_jsonl(ruta)}
    assert len(leidas) == 4
    assert leidas['x-0']['revisado_por_operador'] is True and leidas['x-0']['revision']['veredicto'] == 'correcta'
    assert leidas['x-1']['revision'] == {'veredicto': 'incorrecta', 'correccion': 'era otra cosa'}
    # La respuesta esperada no se pisa: la corrección va aparte, y lo sellado sigue igual.
    assert leidas['x-1']['respuesta_esperada'] == filas[1]['respuesta_esperada']
    assert leidas['x-2']['revisado_por_operador'] is False and 'revision' not in leidas['x-2']
    antes = ruta.read_bytes()
    PE.importar(hoja, ruta)
    assert ruta.read_bytes() == antes


@pytest.mark.parametrize('marca', ['tal vez', 'x', '1', 'ok'])
def test_marca_que_no_se_entiende_rechaza_toda_la_hoja(tmp_path, marca):
    """076:RF-27 — ni una fila a medias: una marca dudosa no se adivina."""
    ruta, filas = _conjunto(tmp_path)
    hoja = _hoja(tmp_path, filas, {'x-0': ('s', None), 'x-1': (marca, None)})
    antes = ruta.read_bytes()
    with pytest.raises(PE.HojaError, match='x-1'):
        PE.importar(hoja, ruta)
    assert ruta.read_bytes() == antes


def test_id_desconocido_o_repetido_rechaza(tmp_path):
    """076:RF-11, RF-27 — una fila que no es de este conjunto, o repetida, no entra."""
    from openpyxl import load_workbook

    ruta, filas = _conjunto(tmp_path)
    hoja = _hoja(tmp_path, filas, {'x-0': ('s', None)})
    libro = load_workbook(hoja)
    hoja_xl = libro.active
    hoja_xl.append(['x-0', '', '', '', 's', None])
    libro.save(hoja)
    with pytest.raises(PE.HojaError, match='x-0'):
        PE.importar(hoja, ruta)
    hoja = _hoja(tmp_path, filas, {})
    libro = load_workbook(hoja)
    libro.active.append(['no-existe', '', '', '', 's', None])
    libro.save(hoja)
    with pytest.raises(PE.HojaError, match='no-existe'):
        PE.importar(hoja, ruta)


def test_sin_marca_no_es_humana_y_ninguna_es_orden(tmp_path, filas):
    """076:RF-12 — 068:RF-30: revisada o no, una fila nunca cuenta como orden confirmada del operador."""
    assert all(not f['revisado_por_operador'] or f.get('revision') for f in filas)
    assert PE.humanas(filas) == [f for f in filas if f['revisado_por_operador']]
    marcada = {**filas[0], 'revisado_por_operador': True, 'revision': {'veredicto': 'correcta', 'correccion': ''}}
    assert PE.humanas([marcada]) == [marcada]
    assert PE.ordenes_confirmadas([marcada]) == []
    assert all(f['origen'] == 'sintetico_maestro' for f in filas)


def test_informe_por_entregable_al_dia(filas):
    """076:RF-13 — filas, con y sin respuesta y huecos por entregable; el fichero es el generado."""
    h = json.loads(PE.HUECOS.read_text(encoding='utf-8'))
    texto = PE.informe_md(filas, h)
    for e in PE.ENTREGABLES + PE.TEMAS:
        assert f'## {e}' in texto
        assert h['huecos'].get(e), e
    assert PE.INFORME.read_text(encoding='utf-8').replace('\r\n', '\n') == texto


# ----------------------------------------------------------------- hechos de la web
def test_cada_hecho_con_componente_y_ruta_comprobada(hechos):
    """076:RF-19 — la ruta existe en `web/app.py`, y la función de `api.ts` es la que el componente llama."""
    assert hechos
    errores = PE.errores_de_hechos(hechos)
    assert not errores, errores[:20]
    assert {h['clase'] for h in hechos} == {'boton', 'casilla'}
    assert len({h['id'] for h in hechos}) == len(hechos)


def test_el_catalogo_cubre_los_botones_del_front(hechos):
    """076:RF-19 — cada botón con acción propia de `frontend/src/components` está, o se declara excluido con motivo."""
    cubiertos = {(h['componente'], h['fuentes'][0]['linea']) for h in hechos}
    faltan = [b for b in PE.botones_del_front() if b not in cubiertos and b not in PE.excluidos_del_catalogo()]
    assert not faltan, faltan[:30]


def test_un_hecho_con_ruta_inventada_se_rechaza(hechos):
    """076:RF-19 — no se supone un botón por su nombre."""
    malo = {**hechos[0], 'ruta': 'POST /api/workspaces/{wid}/inventada'}
    assert PE.errores_de_hechos([malo])
    malo = {**hechos[0], 'api': 'noExisteEnApi'}
    assert PE.errores_de_hechos([malo])


def test_generar_es_determinista_byte_a_byte(hechos):
    """076:RF-20 — misma semilla, misma salida, también en otro proceso; otra semilla, otra muestra."""
    a = PE.generar_texto(hechos, semilla=7, cuantas=40)
    assert a == PE.generar_texto(hechos, semilla=7, cuantas=40)
    assert a != PE.generar_texto(hechos, semilla=8, cuantas=40)
    salidas = []
    for semilla_hash in ('1', '2'):
        r = subprocess.run([sys.executable, str(RAIZ / 'tools' / 'preguntas_entregables.py'), 'generar',
                            '--semilla', '7', '--cuantas', '40', '--salida', '-'], capture_output=True, check=True,
                           env={**__import__('os').environ, 'PYTHONHASHSEED': semilla_hash, 'PYTHONIOENCODING': 'utf-8'})
        salidas.append(r.stdout)
    assert salidas[0] == salidas[1] and salidas[0].decode('utf-8').replace('\r\n', '\n') == a


def test_la_respuesta_sale_del_hecho(hechos):
    """076:RF-21 — para todo sorteo, la respuesta es la del campo del hecho, y con sus fuentes."""
    por_id = {h['id']: h for h in hechos}
    for semilla in (1, 2, 3):
        for f in PE.generar(hechos, semilla=semilla, cuantas=len(hechos) * 2):
            h = por_id[f['hecho']]
            assert f['respuesta_esperada'] == PE.respuesta_de(h, f['aspecto'])
            assert f['fuentes'] == h['fuentes']


def test_marcadores_inventados_no_reales(hechos):
    """076:RF-20 — los marcadores no tienen forma de código real, y lo generado pasa la lista negativa."""
    filas = PE.generar(hechos, semilla=11, cuantas=len(hechos) * 2)
    assert any(re.search(r'\b(ALIM|SET|PROYECTO)-[A-Z]\b', f['pregunta']) for f in filas)
    nombres, patrones, privados = _prohibidos()
    assert not PE.errores_de_nombres(filas, nombres, patrones, privados)
    assert any(f['registro'] != 'formal' for f in filas)
    assert any(f['ruido'] > 0 for f in filas)


@pytest.mark.parametrize('semilla', [0, 1, 2, 3, 99, 2026])
def test_cobertura_con_el_numero_declarado(hechos, semilla):
    """076:RF-22 — con las muestras declaradas sale cada botón y casilla, sea cual sea la semilla."""
    n = PE.muestras_para_cubrir(hechos)
    assert n == len(hechos)
    c = PE.cobertura(PE.generar(hechos, semilla=semilla, cuantas=n, para='medida'), hechos)
    assert c['faltan'] == [] and c['cubiertos'] == len(hechos)
    c = PE.cobertura(PE.generar(hechos, semilla=semilla, cuantas=n // 2, para='medida'), hechos)
    assert c['faltan']


def test_el_corpus_no_ensena_lo_sellado(filas, hechos):
    """076:RF-23 — un hecho citado por una fila sellada no entra a un corpus estocástico."""
    sellados = {f['hecho'] for f in filas if f.get('hecho') and f['reparto'] == 'sellado'}
    assert sellados
    corpus = PE.generar(hechos, semilla=5, cuantas=len(hechos) * 2, para='corpus', sellados=sellados)
    assert corpus and not {f['hecho'] for f in corpus} & sellados
    assert all(not f['hecho_visto_al_ensenar'] for f in corpus)


def test_medida_marca_lo_visto_al_ensenar(hechos):
    """076:RF-23 — separadas por hecho: lo que ya se enseñó queda marcado, y se puede excluir."""
    vistos = {hechos[0]['id'], hechos[1]['id']}
    medida = PE.generar(hechos, semilla=5, cuantas=len(hechos), para='medida', vistos=vistos)
    assert {f['hecho'] for f in medida if f['hecho_visto_al_ensenar']} == vistos
    limpia = PE.generar(hechos, semilla=5, cuantas=len(hechos), para='medida', vistos=vistos, excluir_vistos=True)
    assert not {f['hecho'] for f in limpia} & vistos


def test_las_estocasticas_no_son_humanas(hechos):
    """076:RF-24 — ni humanas ni órdenes confirmadas, y con su semilla."""
    filas = PE.generar(hechos, semilla=3, cuantas=20)
    assert all(f['origen'] == 'sintetico_estocastico' and f['revisado_por_operador'] is False and f['semilla'] == 3
               for f in filas)
    assert PE.humanas(filas) == [] and PE.ordenes_confirmadas(filas) == []


def test_lo_de_pantalla_queda_sin_comprobar(filas, hechos):
    """076:RF-25 — si un botón se ve habilitado no se afirma: se lee la condición del código y se marca."""
    for h in hechos:
        if h.get('requisito'):
            assert h['verificacion'] == 'sin_comprobar_en_navegador', h['id']
    gen = PE.generar(hechos, semilla=4, cuantas=len(hechos) * 3)
    assert any(f['aspecto'] == 'requisito' for f in gen)
    assert all(f['verificacion'] == 'sin_comprobar_en_navegador' for f in gen if f['aspecto'] == 'requisito')
    web = [f for f in filas if f['entregable'] == 'operacion_web' and f['aspecto'] == 'requisito']
    assert web and all(f['verificacion'] == 'sin_comprobar_en_navegador' for f in web)


def test_importar_del_maestro_queda_como_suya_y_no_humana(tmp_path):
    """076:RF-28 — la marca del maestro lleva su revisor, no pone «revisado_por_operador» y no cuenta como humana."""
    ruta, filas = _conjunto(tmp_path)
    huella_antes = PE.huella(filas)
    hoja = _hoja(tmp_path, filas, {'x-0': ('s', None), 'x-1': ('n', 'no lo dice el código')})
    assert PE.importar(hoja, ruta, 'maestro') == {'correctas': 1, 'incorrectas': 1, 'sin_marca': 2}
    leidas = PE.leer_jsonl(ruta)
    marcadas = [f for f in leidas if f.get('revisado_por_maestro')]
    assert len(marcadas) == 2 and all(f['revision']['revisor'] == 'maestro' and f['revisado_por_operador'] is False for f in marcadas)
    assert PE.humanas(leidas) == [] and PE.huella(leidas) == huella_antes
    with pytest.raises(PE.HojaError):
        PE.importar(hoja, ruta, 'otro')


# ----------------------------------------------------------------- entrada al corpus
def test_corpus_entra_solo_lo_marcado_si_del_reparto_corpus(filas):
    """076:RF-29, 076:RF-30 — lo marcado «sí» del reparto `corpus`; lo marcado «no» se queda fuera y sigue en el conjunto."""
    dentro = PE.filas_al_corpus(filas)
    assert dentro and all(f['reparto'] == 'corpus' and f['revision']['veredicto'] == 'correcta' for f in dentro)
    texto = PE.documento_corpus(filas)
    ids = set(re.findall(r'^## (.+)$', texto, re.M))
    assert ids == {f['id'] for f in dentro}
    fuera = [f for f in filas if f['reparto'] == 'corpus' and f['revision']['veredicto'] != 'correcta']
    assert fuera and not ids & {f['id'] for f in fuera}
    assert {f['id'] for f in fuera} <= {f['id'] for f in PE.leer_jsonl(PE.DATASET)}, 'sin borrar'


def test_corpus_sin_marca_no_entra():
    """076:RF-30 — una fila sin marca no entra."""
    fila = {'id': 'x', 'reparto': 'corpus', 'revision': None, 'revisado_por_operador': False}
    assert PE.filas_al_corpus([fila]) == []


def test_corpus_no_lleva_nada_sellado(filas):
    """076:RF-31 — ninguna fila ni grupo del reparto `sellado`, aunque esté marcado correcto, y sus preguntas no aparecen."""
    texto = PE.documento_corpus(filas)
    sellados = [f for f in filas if f['reparto'] == 'sellado']
    assert any(f['revision']['veredicto'] == 'correcta' for f in sellados)
    grupos = {f['grupo_parafrasis'] for f in sellados}
    assert not grupos & {f['grupo_parafrasis'] for f in PE.filas_al_corpus(filas)}
    assert not [f['id'] for f in sellados if f"Pregunta: {f['pregunta']}" in texto]


def test_corpus_no_cuenta_como_humana(filas):
    """076:RF-32, 068:RF-30 — cada fila dice su origen y que la marcó el maestro; ni humanas ni órdenes confirmadas."""
    texto = PE.documento_corpus(filas)
    dentro = PE.filas_al_corpus(filas)
    assert texto.count('Origen: sintetico_maestro. Marcó: maestro, no es una revisión humana.') == len(dentro)
    assert PE.humanas(dentro) == [] and PE.ordenes_confirmadas(dentro) == []


def test_corpus_documento_al_dia_y_determinista(filas, tmp_path):
    """076:RF-29, 076:RF-33 — el documento del repositorio es el de las marcas; otra marca sin regenerar es un error."""
    assert PE.errores_de_corpus(filas) == []
    assert PE.documento_corpus(list(reversed(filas))) == PE.documento_corpus(filas)
    ruta = tmp_path / 'doc.md'
    ruta.write_bytes(PE.documento_corpus(filas).encode('utf-8'))
    assert PE.errores_de_corpus(filas, ruta) == []
    otra = [dict(f) for f in filas]
    cambiada = next(f for f in otra if f['reparto'] == 'corpus' and f['revision']['veredicto'] == 'correcta')
    cambiada['revision'] = {**cambiada['revision'], 'veredicto': 'incorrecta'}
    assert PE.errores_de_corpus(otra, ruta)


def test_corpus_entra_al_ampliado_y_no_al_de_la_047():
    """076:RF-29, 076:RF-34, 077:RF-47 — está en los ficheros del índice ampliado, no en los del que se sirve hoy."""
    from convertersmartgrid.asistente import indice

    assert PE.CORPUS_MAESTRO in indice._ficheros_de(RAIZ, indice.CORPUS_AMPLIADO)
    assert PE.CORPUS_MAESTRO not in indice._ficheros_de(RAIZ, indice.CORPUS_047)
