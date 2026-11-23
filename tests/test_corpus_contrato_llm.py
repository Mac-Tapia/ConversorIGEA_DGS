"""047:RF-69 a RF-74 (MEJ34): el corpus v7 del alumno destilado cubre el contrato vigente entero.

Caso real (2026-11-21): el corpus de órdenes v6 (065, resellado por 047:RF-57) cubría 27 de las 67 tareas de ``TAREAS``;
un alumno entrenado con él no conocía calibrar, escanear, la escalera de obras, el PIT, la nube ni la biblioteca
normativa, y no se podía poner en uso. Estas pruebas arman un v6 sintético con la misma forma (contextos, fuentes
resueltas, política y órdenes humanas reservadas) y comprueban que el v7 cubre las 67 tareas en las cuatro particiones,
sin nombres reales, con sus orígenes declarados, sus fuentes custodiadas por sha256, la prueba y la selección fijadas
antes de sellar y el prompt del contrato vigente.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.aplicacion.asistente import corpus_contrato_llm as cc
from convertersmartgrid.aplicacion.asistente import llm_destilacion as llm
from convertersmartgrid.aplicacion.asistente.tareas import (PERFILES_ALUMNO, TAREAS, TAREAS_HASTA_069, sistema_alumno,
                                                            sistema_alumno_contrato)
from convertersmartgrid.aplicacion.evaluacion_modelos import huella, texto_canonico

#: Un nombre «real» de mentira: el detector de la prueba lo marca; ningún fichero del v7 puede llevarlo.
NOMBRE = 'EMPRESAX'


def detector(texto: str) -> list[str]:
    return ['empresa'] if NOMBRE.lower() in texto.lower() else []


def _fichero(carpeta: Path, nombre: str, contenido: str) -> Path:
    ruta = carpeta / nombre
    ruta.write_text(contenido, encoding='utf-8')
    return ruta


@pytest.fixture
def base_v6(tmp_path):
    """Un corpus sellado v6 sintético: sus contextos citan las fuentes por su ruta histórica, ya retirada, y el
    manifiesto las resuelve por su sha256 a la custodia del 065 (``resellado.fuentes_resueltas``)."""
    custodia = tmp_path / 'custodia_065'
    custodia.mkdir()
    fuentes = {}
    for clave, nombre in (('red', 'red.txt'), ('loads', 'cargas.txt'), ('equipment', 'equipos.txt'),
                          ('estructura', 'estructura.pdf'), ('mediciones', 'mediciones.xlsx'),
                          ('nuevos_clientes', 'nuevos.xlsx')):
        fuentes[clave] = llm.custodiar(_fichero(custodia, nombre, f'registro sintético de {clave}'),
                                       localizador='archivo completo')
    espacio = llm.custodiar(_fichero(custodia, 'workspace.json', '{"pf_project_bindings": {}}'),
                            localizador='archivo completo')
    politica = llm.custodiar(_fichero(custodia, 'politica.md', 'P9/P11: custodia local'),
                             localizador='P9/P11: custodia local y resultados comprobados')
    historica = 'D:/retirada/' + NOMBRE + '/'

    def antes(e: dict) -> dict:
        return {**e, 'ruta': historica + Path(e['ruta']).name}

    contextos = []
    for i, parte in enumerate([p for p in llm.PARTICIONES for _ in range(2)]):
        proyecto = f'{NOMBRE}_PROY_{parte}'
        contextos.append({
            'network_id': f'NET_{NOMBRE}{i:02d}', 'alimentador': f'{NOMBRE}{i:02d}', 'source_fingerprint': 'f' * 64,
            'particion': parte,
            'seds': [{'valor': f'S{i}{k}', 'section': f'SEC_{i}_{k}', 'device': f'DEV_{i}_{k}'} for k in range(3)],
            'proyectos': [{'valor': proyecto, 'fuente': {**antes(espacio), 'localizador': f'pf_project_bindings/{proyecto}'}}],
            'sistema': {'valor': f'{NOMBRE} SUR {i}', 'pagina': 1, 'linea': f'SE00{i:02d} {NOMBRE} SUR 1 X EN SERVICIO'},
            'periodos': ['2025-01'], 'ruta': historica + 'nuevos.xlsx',
            'fuentes': {k: antes(v) for k, v in fuentes.items()}})
    base = tmp_path / 'corpus_v6'
    base.mkdir()
    humanas = [{'texto': 'reentrena la pinn', 'tarea': 'gemelo_entrenar', 'datos': [], 'origen': 'confirmado'}]
    ev_contextos = llm.custodiar(_fichero(base, 'contextos_fuente.json', json.dumps(contextos)), localizador='contextos_fuente')
    ev_humanas = llm.custodiar(_fichero(base, 'humanas_reservadas.json', json.dumps(humanas)),
                               localizador='humanas_reservadas_archivo')
    resueltas = [{'origen': historica + Path(e['ruta']).name, 'resuelta': e['ruta'], 'sha256': e['sha256'], 'bytes': e['bytes']}
                 for e in (*fuentes.values(), espacio, politica)]
    meta = {'schema_version': 2, 'dataset_hash': 'hash-v6', 'prompt_hash': huella(sistema_alumno()),
            'por_tarea': {'prueba': dict.fromkeys(TAREAS_HASTA_069, 1)}, 'contextos_fuente': ev_contextos,
            'humanas_reservadas_archivo': ev_humanas, 'politica_custodiada': {'copia': antes(politica)},
            'resellado': {'fuentes_resueltas': resueltas}, 'fuentes_manifest': {'conteos_reales': {'alimentadores': 8}}}
    _fichero(base, 'dataset_manifest.json', json.dumps(meta))
    return base


@pytest.fixture
def v7(base_v6, tmp_path):
    fuente = tmp_path / 'fuente_v7'
    cc.preparar_v7(base_v6, fuente, nombres=detector)
    sellado = tmp_path / 'corpus_v7'
    cc.sellar_v7(fuente, sellado)
    return fuente, sellado


def test_prompt_v1_conserva_su_huella_y_v2_cubre_el_contrato():
    """047:RF-69: el v1 es el de los corpus v5 y v6; el v2 nombra cada tarea del contrato vigente y cabe en el ajuste."""
    assert huella(sistema_alumno()) == '2d737fa8e6dbdc94cb7585b5ffe7f5a27d089648ee6afcc655887acce0576f33'
    contrato = sistema_alumno_contrato()
    nombradas = set(re.findall(r'^(\w+): ', contrato, flags=re.M))
    assert nombradas == set(TAREAS) and len(TAREAS) > len(TAREAS_HASTA_069)
    assert PERFILES_ALUMNO['llm_destilado_v2'][1] is TAREAS and PERFILES_ALUMNO['llm_destilado_v1'][1] is TAREAS_HASTA_069
    # Sin citas y con la primera frase: con las descripciones enteras pasaba de los 2.900 tokens del tokenizador base.
    assert not re.search(r'\d{3}:RF-\d+', contrato) and len(contrato) < 8000
    assert llm.MAX_TOKENS_PERFIL == {'llm_destilado_v1': 2048, 'llm_destilado_v2': 3072}


def test_curriculo_de_las_tareas_posteriores_con_cuatro_columnas():
    """047:RF-71: cada tarea posterior a la 069 tiene cuatro frases distintas, una por partición, con sus datos."""
    nuevas = set(TAREAS) - set(TAREAS_HASTA_069)
    assert set(cc.CURRICULO_CONTRATO) == nuevas
    for tarea, columnas in cc.CURRICULO_CONTRATO.items():
        assert len({texto_canonico(c) for c in columnas}) == 4, tarea
        obligatorios = {d.tipo for d in TAREAS[tarea].datos if d.obligatorio}
        for c in columnas:
            usados = set(re.findall(r'\{(\w+)\}', c))
            assert obligatorios <= usados <= {d.tipo for d in TAREAS[tarea].datos}, (tarea, c)
    for tarea in TAREAS:
        apartadas = [cc.plantillas_de(tarea, p)[0] for p in llm.PARTICIONES[1:]]
        assert not {texto_canonico(t) for t in cc.plantillas_de(tarea, 'entrenamiento')} & {texto_canonico(t) for t in apartadas}


def test_v7_cubre_las_67_tareas_en_las_cuatro_particiones_con_el_prompt_vigente(v7):
    """047:RF-69, RF-74: cada partición sellada cubre el contrato; se entrena con el prompt v2 y la auditoría pasa."""
    _, sellado = v7
    meta = json.loads((sellado / 'dataset_manifest.json').read_text(encoding='utf-8'))
    assert meta['perfil_prompt'] == 'llm_destilado_v2' and meta['prompt_hash'] == huella(sistema_alumno_contrato())
    for parte in llm.PARTICIONES:
        registros, _ = llm.leer_particion_real(sellado, parte)
        assert {r['tarea'] for r in registros} - {None} == set(TAREAS), parte
    prueba, _ = llm.leer_particion_real(sellado, 'prueba')
    assert all(n == cc.PRESUPUESTO['prueba_por_tarea'] for n in meta['por_tarea']['prueba'].values())
    _, _, sistema = llm.ejemplos_de_entrenamiento(sellado)
    assert sistema == sistema_alumno_contrato()
    auditoria = cc.auditar_v7(sellado)
    with pytest.raises(ValueError, match='validador'):
        llm.auditar_fuentes_corpus(sellado)
    assert auditoria['ok'] and auditoria['observaciones_humanas_en_train'] == 0
    assert not {texto_canonico('reentrena la pinn')} & {texto_canonico(r['texto']) for r in prueba}


def test_v7_sin_nombres_reales_y_con_seudonimos_custodiados(v7):
    """047:RF-70: ningún fichero del v7 lleva el nombre; el mapa guarda solo la huella de cada original."""
    fuente, sellado = v7
    for carpeta in (fuente, sellado):
        for f in carpeta.glob('*.json*'):
            assert NOMBRE.lower() not in f.read_text(encoding='utf-8').lower(), f.name
    mapa = json.loads((fuente / 'seudonimos.json').read_text(encoding='utf-8'))
    assert mapa and all(set(m) == {'tipo', 'seudonimo', 'sha256_original'} for m in mapa)
    assert {m['tipo'] for m in mapa} >= {'alimentadores', 'proyecto', 'sistema', 'set', 'sed', 'ruta'}


def test_nombre_sin_seudonimo_no_se_prepara(base_v6, tmp_path, monkeypatch):
    """047:RF-70: si un valor de la fuente llega con su nombre, el v7 no se escribe."""
    monkeypatch.setattr(cc.Seudonimos, 'de', lambda self, tipo, original: original)
    destino = tmp_path / 'fuente_v7'
    with pytest.raises(ValueError, match='nombres reales'):
        cc.preparar_v7(base_v6, destino, nombres=detector)
    assert not destino.exists()


def test_origenes_declarados_y_sinteticos_por_particion(v7):
    """047:RF-70, 047:RF-72: cada fila declara su origen; lo sintético va con su valor declarado, uno por partición."""
    fuente, _ = v7
    filas = json.loads((fuente / 'corpus.json').read_text(encoding='utf-8'))
    meta = json.loads((fuente / 'dataset_manifest.json').read_text(encoding='utf-8'))
    assert {r['origen_declarado'] for r in filas} == {'maestro', 'sintetico_controlado'}
    por_parte = {}
    for r in filas:
        if r['tarea'] == 'normativa_agregar':
            assert r['origen_declarado'] == 'sintetico_controlado' and r['valores_sinteticos'] == ['ruta']
            (a, b, _), = r['datos']
            assert r['texto'][a:b] in meta['valores_sinteticos']['ruta']
            por_parte.setdefault(r['particion'], set()).add(r['texto'][a:b])
        if r['tarea'] == 'calibrar':
            assert r['origen_declarado'] == 'maestro' and not r['valores_sinteticos']
    assert len(por_parte) == 4 and all(len(v) == 1 for v in por_parte.values())
    assert len(set().union(*por_parte.values())) == 4
    cambiada = [dict(r) for r in filas]
    fila = next(r for r in cambiada if r['valores_sinteticos'])
    fila['origen_declarado'] = 'maestro'
    fila['record_id'] = huella({k: v for k, v in fila.items() if k != 'record_id'})
    with pytest.raises(ValueError, match='sinteticos sin declarar'):
        cc.validar_corpus_contrato(cambiada, {**meta, 'dataset_hash': huella(cambiada)})


def test_fuentes_copiadas_a_la_custodia_del_v7_por_sha256(v7):
    """047:RF-73: cada fuente de cada fila está en ``fuentes/<sha256>.bin`` del propio v7 y casa por su sha256."""
    fuente, sellado = v7
    rutas = set()
    for parte in llm.PARTICIONES:
        registros, _ = llm.leer_particion_real(sellado, parte)
        rutas |= {(f['ruta'], f['sha256']) for r in registros for f in r['fuentes']}
    assert rutas and all(Path(r).parent == (fuente / 'fuentes').resolve() and Path(r).name == s + '.bin' for r, s in rutas)


def test_fuente_que_no_casa_no_prepara(base_v6, tmp_path):
    """047:RF-73: una fuente cuya copia del 065 ya no casa por sha256 para la preparación y no deja nada escrito."""
    meta = json.loads((base_v6 / 'dataset_manifest.json').read_text(encoding='utf-8'))
    Path(meta['resellado']['fuentes_resueltas'][0]['resuelta']).write_text('otro contenido', encoding='utf-8')
    destino = tmp_path / 'fuente_v7'
    with pytest.raises(ValueError, match='sha256'):
        cc.preparar_v7(base_v6, destino)
    assert not destino.exists()


def test_apartadas_fijadas_antes_de_sellar(v7, tmp_path):
    """047:RF-74: una prueba cambiada después de prepararla no se sella, y una sellada cambiada no se lee."""
    fuente, sellado = v7
    filas = json.loads((fuente / 'corpus.json').read_text(encoding='utf-8'))
    meta = json.loads((fuente / 'dataset_manifest.json').read_text(encoding='utf-8'))
    otra = tmp_path / 'fuente_cambiada'
    otra.mkdir()
    quitada = next(i for i, r in enumerate(filas) if r['particion'] == 'prueba')
    cambiadas = filas[:quitada] + filas[quitada + 1:] + [filas[quitada]]   # mismo contenido, otro orden en la prueba
    prueba = [r for r in cambiadas if r['particion'] == 'prueba']
    assert huella(prueba) != meta['apartadas_preparadas']['prueba']
    (otra / 'corpus.json').write_text(json.dumps(cambiadas), encoding='utf-8')
    (otra / 'dataset_manifest.json').write_text(json.dumps({**meta, 'dataset_hash': huella(cambiadas)}), encoding='utf-8')
    with pytest.raises(ValueError, match='apartadas'):
        cc.sellar_v7(otra, tmp_path / 'sellado_cambiado')
    with pytest.raises(ValueError, match='validador'):
        llm.sellar_particiones(fuente, tmp_path / 'sin_validador')
    sellada = json.loads((sellado / 'dataset_manifest.json').read_text(encoding='utf-8'))
    sellada['apartadas_preparadas']['seleccion'] = 'otra'
    (sellado / 'dataset_manifest.json').write_text(json.dumps(sellada), encoding='utf-8')
    with pytest.raises(ValueError, match='apartada'):
        llm.leer_particion_real(sellado, 'seleccion')


def test_elegir_con_el_contrato_del_perfil():
    """047:RF-69 con 047:RF-60: la selección compara con las tareas del manifiesto sellado; el del v7 declara las 67 y
    con las 29 del v1 no se elige; el perfil de los informes es el que selló el corpus."""
    def informe(tareas, perfil):
        return {'particion': 'seleccion', 'dataset_hash': 'd', 'prompt_hash': 'p', 'modelo': 'm', 'modelo_digest': 'g',
                'perfil_prompt': perfil, 'metricas': {'ejemplos': 3, 'acierto_tarea': .5, 'f1_datos': .5,
                                                      'familias': {t: {'acierto_tarea': .5} for t in tareas}}}

    def manifiesto(perfil):
        tareas = llm.tareas_de_perfil(perfil)
        return {'dataset_hash': 'd', 'prompt_hash': 'p', 'perfil_prompt': perfil,
                'por_tarea': {'seleccion': {t: 3 for t in tareas}}}

    v1, v2 = manifiesto('llm_destilado_v1'), manifiesto('llm_destilado_v2')
    elegido = llm.elegir_version_llm([informe(TAREAS_HASTA_069, 'llm_destilado_v1')], manifiesto=v1)
    assert elegido['perfil_prompt'] == 'llm_destilado_v1'
    with pytest.raises(ValueError, match='incompletas'):
        llm.elegir_version_llm([informe(TAREAS_HASTA_069, 'llm_destilado_v2')], manifiesto=v2)
    with pytest.raises(ValueError, match='perfil'):
        llm.elegir_version_llm([informe(TAREAS, 'llm_destilado_v2')], manifiesto=v1)
    elegido = llm.elegir_version_llm([informe(TAREAS, 'llm_destilado_v2')], manifiesto=v2)
    assert elegido['perfil_prompt'] == 'llm_destilado_v2'
    assert elegido['tareas_selladas'] == sorted(TAREAS)
    assert elegido['no_cubiertas_por_este_sellado']['cuantas'] == 0


def test_alumno_v2_atiende_con_el_prompt_del_contrato():
    """047:RF-69: el alumno del v7 se sirve con el mismo prompt con el que se entrenó."""
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    peticiones = []

    def abrir(req, timeout):
        peticiones.append(json.loads(req.data))
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(
            {'tarea': 'calibrar', 'datos': {'proyecto': ['PROY_001']}, 'confianza': .9})}}).encode())
    c = ClienteOllama(modelo='alumno:v7', abrir=abrir, perfil_prompt='llm_destilado_v2')
    assert c.interpretar('calibra PROY_001')['tarea'] == 'calibrar'
    sistema = peticiones[0]['messages'][0]['content']
    assert sistema == sistema_alumno_contrato() and '\ncalibrar: ' in sistema and '\nnormativa_agregar: ' in sistema


def test_preparar_contrato_en_el_instalado_dice_que_falta_la_lista_de_la_entrega(tmp_path):
    """086:RF-36: el paquete lleva llm_destilar.py pero no comprobar_entrega.py; el detector lo dice, sin ModuleNotFoundError."""
    herramienta = cargar_herramienta('llm_destilar.py', 'llm_destilar_instalado')
    with pytest.raises(ValueError, match='comprobar_entrega.py'):
        herramienta.detector_de_nombres(tmp_path)
    nombres, origenes = herramienta.detector_de_nombres()   # en el repositorio la carga por su ruta
    assert callable(nombres) and isinstance(origenes, list)


def test_cli_preparar_contrato_mide_su_coste(base_v6, tmp_path, capsys, monkeypatch):
    """047:RF-69: la herramienta prepara el v7 y deja medido lo que costó, sin GPU ni llamadas a modelos."""
    # Con la lista local de la máquina de desarrollo, el propio tmp_path (bajo el perfil del usuario) es una «ruta del
    # desarrollo»: el corpus sintético nunca saldría limpio (23-11: 56 828 hallazgos, todos la ruta de la temporal).
    # Aquí se mide el coste; que un nombre real detenga el sellado lo prueba test_nombre_sin_seudonimo_no_se_prepara.
    monkeypatch.delenv('CSG_TERMINOS_PROHIBIDOS', raising=False)
    herramienta = cargar_herramienta('llm_destilar.py', 'llm_destilar_mej34')
    destino = tmp_path / 'fuente_cli'
    assert herramienta.main(['preparar-contrato', '--base', str(base_v6), '--destino', str(destino), '--sin-almacen']) == 0
    salida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert salida['ok'] and salida['tareas'] == len(TAREAS) and salida['medicion']['gpu_s'] == 0
    meta = json.loads((destino / 'dataset_manifest.json').read_text(encoding='utf-8'))
    assert meta['medicion_construccion']['llamadas_a_modelos'] == 0 and meta['medicion_construccion']['segundos'] >= 0
