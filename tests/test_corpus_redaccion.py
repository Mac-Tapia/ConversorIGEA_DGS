"""Spec 072, T9: los entregables de otra empresa enseñan a redactar, con revisión humana y nunca como verdad eléctrica."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.asistente.corpus_redaccion import (
    CorpusRedaccionError,
    ejemplos_para_entrenar,
    pendientes,
    registrar_revision,
    resumen,
    sin_cifras,
)

RAIZ = Path(__file__).resolve().parents[1]


def _fragmento(n: int, texto: str, *, empresa: str = 'Empresa de prueba', location: str = 'document') -> dict:
    # 072:RF-20: la empresa, el expediente y el texto son casos de prueba del conversor.
    return {'record_id': f'r{n}', 'empresa': empresa, 'relative_path': f'PIDE X/4.2 Informe PIDE/{n}.docx',
            'location': location, 'periodo': '2026', 'entregable': '4.2', 'text': texto}


@pytest.fixture
def corpus(tmp_path):
    frags = [_fragmento(1, '3.1 CRITERIOS DE EVALUACIÓN\nLa caída de tensión en la barra B12 es de 7,5 % con 1 250 kW.'),
             _fragmento(2, 'El VAN del proyecto asciende a US$ 1 234 567 con una TIR de 14,2 %.'),
             _fragmento(3, 'Tabla de cifras', location='sheet:F01')]
    ruta = tmp_path / 'fragments.jsonl'
    ruta.write_text('\n'.join(json.dumps(f, ensure_ascii=False) for f in frags) + '\n', encoding='utf-8')
    return tmp_path, frags


def test_sin_revision_humana_nada_entra(corpus):
    """072:RF-19 — un fragmento sin revisar, o con un origen distinto de humano y maestro, no entra."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    assert ejemplos_para_entrenar(registro, frags) == []
    # 072:RF-48: solo «humano» o «maestro» (revisor independiente); otro origen no se registra.
    with pytest.raises(CorpusRedaccionError, match='origen'):
        registrar_revision(registro, frags[0], revisor='maestro', origen='codex', aprobado=True, uso='redaccion')
    with pytest.raises(CorpusRedaccionError, match='revisor'):
        registrar_revision(registro, frags[0], revisor=' ', origen='humano', aprobado=True, uso='redaccion')
    assert not registro.exists()


def test_solo_redaccion_y_formato_nunca_verdad_electrica(corpus):
    """072:RF-19 — el uso es redactar o dar formato; «verdad eléctrica» o cualquier otro se rechaza."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    for uso in ('verdad_electrica', 'calculo', ''):
        with pytest.raises(CorpusRedaccionError, match='uso'):
            registrar_revision(registro, frags[0], revisor='ing. revisor', origen='humano', aprobado=True, uso=uso)


def test_aprobado_entra_sin_sus_cifras_y_con_su_procedencia(corpus):
    """072:RF-19 — lo aprobado entra con las cifras ocultas: aprende la forma, no los valores de otra red."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    fila = registrar_revision(registro, frags[0], revisor='ing. revisor', origen='humano', aprobado=True,
                              uso='redaccion', fecha='2026-11-06', nota='estructura de la sección 3.1')
    registrar_revision(registro, frags[1], revisor='ing. revisor', origen='humano', aprobado=False, uso='redaccion',
                       fecha='2026-11-06', nota='cifras de otra empresa sin forma útil')
    assert fila['huella_texto'] and fila['verdad_electrica'] is False
    ejemplos = ejemplos_para_entrenar(registro, frags)
    assert [e['record_id'] for e in ejemplos] == ['r1']
    texto = ejemplos[0]['texto']
    assert 'CRITERIOS DE EVALUACIÓN' in texto and '7,5' not in texto and '1 250' not in texto and 'B12' not in texto
    assert ejemplos[0]['uso'] == 'redaccion' and ejemplos[0]['verdad_electrica'] is False
    assert ejemplos[0]['revisor'] == 'ing. revisor' and ejemplos[0]['fuente'].endswith('1.docx')


def test_la_ultima_revision_manda_y_un_texto_cambiado_la_invalida(corpus):
    """072:RF-19 — el registro es solo de añadir: la última decisión manda; si el texto cambió, hay que revisarlo otra vez."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    registrar_revision(registro, frags[0], revisor='a', origen='humano', aprobado=True, uso='formato')
    registrar_revision(registro, frags[0], revisor='b', origen='humano', aprobado=False, uso='formato')
    assert ejemplos_para_entrenar(registro, frags) == []
    registrar_revision(registro, frags[0], revisor='c', origen='humano', aprobado=True, uso='formato')
    cambiado = [dict(frags[0], text=frags[0]['text'] + ' añadido')]
    assert ejemplos_para_entrenar(registro, cambiado) == []
    assert [p['record_id'] for p in pendientes(registro, cambiado)] == ['r1']
    assert len(registro.read_text(encoding='utf-8').splitlines()) == 3


def test_resumen_y_pendientes(corpus):
    """072:RF-19 — el registro dice cuánto se revisó, cuánto se aprobó y qué queda; las hojas no son redacción."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    assert [p['record_id'] for p in pendientes(registro, frags)] == ['r1', 'r2']
    registrar_revision(registro, frags[0], revisor='a', origen='humano', aprobado=True, uso='redaccion')
    r = resumen(registro, frags)
    assert r == {'fragmentos': 2, 'revisados': 1, 'aprobados': 1, 'rechazados': 0, 'pendientes': 1,
                 'por_uso': {'redaccion': 1}, 'revisores': ['a']}


def test_sin_cifras():
    """072:RF-19 — números, porcentajes, montos y códigos de elementos se ocultan; las palabras quedan."""
    assert sin_cifras('La barra B12 baja a 0,93 p.u. con 3 500 kW (14,2 %) en 2027') == \
        'La barra ‹código› baja a ‹n› p.u. con ‹n› kW (‹n› %) en ‹n›'
    assert sin_cifras('3.1 CRITERIOS') == '‹n› CRITERIOS'


@pytest.mark.parametrize('fuera_del_checkout', [False, True])
def test_herramienta_registra_y_exporta(corpus, tmp_path, fuera_del_checkout):
    """072:RF-19 — la herramienta lista lo pendiente, registra decisiones humanas y exporta lo aprobado."""
    carpeta, _frags = corpus
    decisiones = tmp_path / 'decisiones.json'
    decisiones.write_text(json.dumps([{'record_id': 'r1', 'aprobado': True, 'uso': 'redaccion', 'nota': 'n'}]),
                          encoding='utf-8')
    herramienta = RAIZ / 'tools' / 'corpus_redaccion_pide.py'
    entorno = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    if fuera_del_checkout:
        # Simula la disposición entregada: el guion tiene paquete disponible,
        # pero no existe src junto a él. No se crea otro entorno ni se instala.
        destino = tmp_path / 'programa' / 'tools' / herramienta.name
        destino.parent.mkdir(parents=True)
        shutil.copyfile(herramienta, destino)
        herramienta = destino
        entorno['PYTHONPATH'] = str(RAIZ / 'src')
        assert not (destino.parents[1] / 'src').exists()
    base = [sys.executable, str(herramienta), '--dataset', str(carpeta)]
    r = subprocess.run(base + ['--decisiones', str(decisiones), '--revisor', 'ing. revisor'],
                       capture_output=True, text=True, encoding='utf-8', env=entorno)
    assert r.returncode == 0, r.stdout + r.stderr
    salida = tmp_path / 'ejemplos.jsonl'
    r = subprocess.run(base + ['--exportar', str(salida)], capture_output=True, text=True, encoding='utf-8', env=entorno)
    assert r.returncode == 0, r.stdout + r.stderr
    filas = [json.loads(x) for x in salida.read_text(encoding='utf-8').splitlines()]
    assert [f['record_id'] for f in filas] == ['r1'] and 'Aprobados: 1' in r.stdout
    sin_revisor = subprocess.run(base + ['--decisiones', str(decisiones)], capture_output=True, text=True,
                                 encoding='utf-8', env=entorno)
    assert sin_revisor.returncode == 2 and 'revisor' in sin_revisor.stdout


# --- 072:RF-48 a RF-50 (T25): origen de cada decisión, nombres ocultos y puente al corpus sellado ---------------------
# Todos los nombres son ficticios (072:RF-20): ninguna empresa, sede ni instalación real.

import inspect  # noqa: E402

from convertersmartgrid.aplicacion.asistente import corpus_redaccion as cr  # noqa: E402

CATALOGO = {'empresa': ['Electro Ficticia'], 'sede': ['Villa Quimera'], 'instalacion': ['Laguna Azul']}


def _con_catalogo(texto, catalogo):
    assert 'catalogo' in inspect.signature(sin_cifras).parameters, 'sin_cifras no admite un catálogo de nombres'
    return sin_cifras(texto, catalogo=catalogo)


def _registrar(registro, fragmento, **k):
    try:
        return registrar_revision(registro, fragmento, **k)
    except CorpusRedaccionError as exc:
        pytest.fail(f'la decisión no se registró: {exc}')


def test_origen_maestro_entra_con_su_origen_y_codex_no(corpus):
    """072:RF-48 — lo aprobado por el revisor independiente entra marcado «maestro»; otro origen nunca entra."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    fila = _registrar(registro, frags[0], revisor='agente de prueba', origen='maestro', aprobado=True,
                      uso='redaccion', fecha='2026-11-20', nota='propuesta')
    assert fila['origen'] == 'maestro' and fila['revisor'] == 'agente de prueba'
    ejemplos = ejemplos_para_entrenar(registro, frags)
    assert [(e['record_id'], e['origen'], e['revisor']) for e in ejemplos] == [('r1', 'maestro', 'agente de prueba')]
    # Una fila con otro origen (escrita a mano en el registro de solo añadir) no entra, aunque diga «aprobado».
    with registro.open('a', encoding='utf-8') as f:
        f.write(json.dumps({**fila, 'record_id': 'r2', 'huella_texto': cr.huella_texto(frags[1]['text']),
                            'origen': 'codex'}, ensure_ascii=False) + '\n')
    assert [x['record_id'] for x in ejemplos_para_entrenar(registro, frags)] == ['r1']
    _registrar(registro, frags[0], revisor='ing. revisor', origen='humano', aprobado=True, uso='redaccion')
    [e] = ejemplos_para_entrenar(registro, frags)
    assert e['origen'] == 'humano'
    assert [json.loads(x)['origen'] for x in registro.read_text(encoding='utf-8').splitlines()] == \
        ['maestro', 'codex', 'humano']


def _herramienta(carpeta, *extra):
    return subprocess.run([sys.executable, str(RAIZ / 'tools' / 'corpus_redaccion_pide.py'), '--dataset', str(carpeta),
                           *extra], capture_output=True, text=True, encoding='utf-8')


def test_herramienta_aplica_decisiones_con_su_origen(corpus, tmp_path):
    """072:RF-48 — `--origen` se guarda en cada decisión; un fichero del maestro no se registra como humano."""
    carpeta, frags = corpus
    registro = carpeta / 'revision_redaccion.jsonl'
    decisiones = tmp_path / 'decisiones.json'
    decisiones.write_text(json.dumps([
        {'record_id': 'r1', 'aprobado': True, 'uso': 'redaccion', 'nota': 'limpia', 'origen': 'maestro',
         'revisor': 'agente de prueba', 'fecha': '2026-11-20', 'huella_texto': cr.huella_texto(frags[0]['text'])},
        {'record_id': 'r2', 'aprobado': False, 'uso': 'redaccion', 'nota': 'cifras', 'origen': 'maestro',
         'revisor': 'agente de prueba', 'fecha': '2026-11-20'}]), encoding='utf-8')
    humano = _herramienta(carpeta, '--decisiones', str(decisiones), '--revisor', 'ing. revisor')
    assert humano.returncode == 2 and 'origen' in humano.stdout, humano.stdout + humano.stderr
    assert not registro.exists()
    maestro = _herramienta(carpeta, '--decisiones', str(decisiones), '--origen', 'maestro')
    assert maestro.returncode == 0, maestro.stdout + maestro.stderr
    filas = [json.loads(x) for x in registro.read_text(encoding='utf-8').splitlines()]
    assert [(f['record_id'], f['origen'], f['revisor'], f['fecha']) for f in filas] == [
        ('r1', 'maestro', 'agente de prueba', '2026-11-20'), ('r2', 'maestro', 'agente de prueba', '2026-11-20')]
    salida = tmp_path / 'ejemplos.jsonl'
    exportado = _herramienta(carpeta, '--exportar', str(salida))
    assert exportado.returncode == 0, exportado.stdout + exportado.stderr
    exportados = [json.loads(x) for x in salida.read_text(encoding='utf-8').splitlines()]
    assert [(e['record_id'], e['origen']) for e in exportados] == [('r1', 'maestro')]
    assert 'Aprobados: 1' in exportado.stdout and 'Exportables: 1 (humano: 0, maestro: 1)' in exportado.stdout
    otra = tmp_path / 'otra.json'
    otra.write_text(json.dumps([{'record_id': 'r1', 'aprobado': True, 'uso': 'redaccion', 'huella_texto': '0' * 64}]),
                    encoding='utf-8')
    cambiado = _herramienta(carpeta, '--decisiones', str(otra), '--revisor', 'ing. revisor')
    assert cambiado.returncode == 2 and 'huella' in cambiado.stdout
    assert _herramienta(carpeta, '--decisiones', str(otra), '--origen', 'codex').returncode == 2
    assert len(registro.read_text(encoding='utf-8').splitlines()) == 2


def test_sin_cifras_oculta_los_nombres_del_catalogo():
    """072:RF-49 — empresa, sede e instalación del catálogo se ocultan, sin distinguir mayúsculas ni tildes."""
    texto = 'Electro Ficticia atiende la sede de Villa Quimera desde la SET Laguna Azul con 12 kW.'
    assert _con_catalogo(texto, CATALOGO) == \
        '‹empresa› atiende la sede de ‹sede› desde la SET ‹instalación› con ‹n› kW.'
    assert _con_catalogo('ELECTRO FICTÍCIA y villa quimera', CATALOGO) == '‹empresa› y ‹sede›'
    assert _con_catalogo('Pueblo Ñandú y Ñandúes', ['Pueblo Ñandú']) == '‹nombre› y Ñandúes'
    assert sin_cifras('3.1 CRITERIOS') == '‹n› CRITERIOS'


def test_sin_cifras_oculta_nombres_por_patrones_genericos():
    """072:RF-49 — sin catálogo, «SET <Nombre>», la central, la sede y la razón social «S.A.A.» o «S.A.» se ocultan."""
    assert _con_catalogo('La SET Puerto Imaginario alimenta a Compañía Inventada del Norte S.A.A. y a Servicios '
                         'Ficticios S.A. en su red.', None) == \
        'La SET ‹instalación› alimenta a ‹empresa› y a ‹empresa› en su red.'
    assert _con_catalogo('La Central Térmica Monte Falso entrega a la S.E.T. RÍO SUPUESTO.', None) == \
        'La Central Térmica ‹instalación› entrega a la S.E.T. ‹instalación›.'
    assert _con_catalogo('En la sede regional de Valle Supuesto se proyecta.', None) == \
        'En la sede regional de ‹sede› se proyecta.'
    llano = 'Se considera la SET existente y la barra de la subestación; SE MUESTRA LA DEMANDA.'
    assert _con_catalogo(llano, None) == llano


def test_exportar_oculta_la_empresa_del_fragmento_y_el_catalogo(corpus):
    """072:RF-49 — lo exportado oculta la empresa del propio fragmento y los nombres del catálogo del espacio."""
    carpeta, _frags = corpus
    frag = _fragmento(7, 'Empresa de prueba entrega la SET Laguna Azul y la sede de Villa Quimera.')
    registro = carpeta / 'revision.jsonl'
    _registrar(registro, frag, revisor='ing. revisor', origen='humano', aprobado=True, uso='redaccion')
    assert 'catalogo' in inspect.signature(ejemplos_para_entrenar).parameters
    [e] = ejemplos_para_entrenar(registro, [frag], catalogo=CATALOGO)
    assert e['texto'] == '‹empresa› entrega la SET ‹instalación› y la sede de ‹sede›.'


def _corpus_sellable(tmp_path):
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    textos = ['La caída de tensión de la SET Laguna Azul se evalúa con 7,5 % en máxima demanda.',
              'Electro Ficticia presenta su plan de inversiones en la sede de Villa Quimera.',
              'CRITERIOS DE EVALUACIÓN',
              'El estudio de Compañía Inventada S.A.A. considera 3 alternativas.',
              'Párrafo que aprueba el revisor independiente.',
              'Texto rechazado por la persona que revisa.',
              'Texto de un origen no declarado.']
    frags = [dict(_fragmento(i, t), relative_path=f'PIDE X/{i % 3}.docx') for i, t in enumerate(textos)]
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    registro = carpeta / 'revision_redaccion.jsonl'
    for f, uso in zip(frags[:4], ('redaccion', 'redaccion', 'formato', 'redaccion')):
        _registrar(registro, f, revisor='ing. revisor', origen='humano', aprobado=True, uso=uso, fecha='2026-11-20')
    fila = _registrar(registro, frags[4], revisor='agente de prueba', origen='maestro', aprobado=True,
                      uso='redaccion')
    _registrar(registro, frags[5], revisor='ing. revisor', origen='humano', aprobado=False, uso='redaccion')
    with registro.open('a', encoding='utf-8') as f:
        f.write(json.dumps({**fila, 'record_id': 'r6', 'huella_texto': cr.huella_texto(frags[6]['text']),
                            'origen': 'codex'}, ensure_ascii=False) + '\n')
    return carpeta, frags


def test_sellar_solo_lo_aprobado_y_anonimizado(tmp_path):
    """072:RF-50 — el corpus sellado lleva lo aprobado, humano o del maestro con su origen, sin cifras ni nombres."""
    sellar = getattr(cr, 'sellar_corpus_redaccion', None)
    auditar = getattr(cr, 'auditar_corpus_redaccion', None)
    assert callable(sellar) and callable(auditar), 'no hay puente del corpus aprobado al corpus sellado'
    carpeta, frags = _corpus_sellable(tmp_path)
    destino = tmp_path / 'sellado'
    meta = sellar(carpeta, destino, catalogo=CATALOGO)
    assert meta['tipo_corpus'] == 'redaccion_pide' and meta['verdad_electrica'] is False
    for nombre in ('dataset_manifest.json', 'corpus_auditoria.json', 'entrenamiento.jsonl', 'prueba.jsonl'):
        assert (destino / nombre).is_file(), nombre
    filas = json.loads((destino / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    assert sorted(f['fragmento'] for f in filas) == ['r0', 'r1', 'r2', 'r3', 'r4']
    todo = json.dumps(filas, ensure_ascii=False)
    for prohibido in ('Electro Ficticia', 'Villa Quimera', 'Laguna Azul', 'Compañía Inventada', 'Empresa de prueba',
                      'rechazado', 'no declarado'):
        assert prohibido not in todo, prohibido
    assert not any(c.isdigit() for f in filas for c in f['respuesta'])
    assert {f['fragmento']: f['revision']['origen'] for f in filas} == {
        'r0': 'humano', 'r1': 'humano', 'r2': 'humano', 'r3': 'humano', 'r4': 'maestro'}
    assert meta['por_origen'] == {'humano': 4, 'maestro': 1}
    informe = auditar(destino)
    assert informe['ok'] is True and informe['ejemplos'] == 5 and informe['resultados_electricos'] == 0
    assert informe['por_origen'] == {'humano': 4, 'maestro': 1}
    with pytest.raises(ValueError, match='existente'):
        sellar(carpeta, destino, catalogo=CATALOGO)
    parte = destino / 'entrenamiento.jsonl'
    parte.write_text(parte.read_text(encoding='utf-8').replace('‹sede›', 'Villa Quimera'), encoding='utf-8')
    with pytest.raises(ValueError):
        auditar(destino)


def test_sellar_sin_origen_declarado_se_niega_y_con_maestro_sella(corpus, tmp_path):
    """072:RF-50 — una aprobación de origen no admitido no sella nada; una del maestro sí, marcada «maestro»."""
    sellar = getattr(cr, 'sellar_corpus_redaccion', None)
    assert callable(sellar), 'no hay puente del corpus aprobado al corpus sellado'
    carpeta, frags = corpus
    registro = carpeta / 'revision_redaccion.jsonl'
    fila = _registrar(registro, frags[0], revisor='agente de prueba', origen='maestro', aprobado=True,
                      uso='redaccion')
    registro.write_text(json.dumps({**fila, 'origen': 'codex'}, ensure_ascii=False) + '\n', encoding='utf-8')
    with pytest.raises(CorpusRedaccionError, match='origen'):
        sellar(carpeta, tmp_path / 'sellado')
    assert not (tmp_path / 'sellado').exists()
    _registrar(registro, frags[0], revisor='agente de prueba', origen='maestro', aprobado=True, uso='redaccion')
    meta = sellar(carpeta, tmp_path / 'sellado')
    assert meta['por_origen'] == {'maestro': 1}


def test_herramienta_sella_con_catalogo(tmp_path):
    """072:RF-50 — `--sellar` con `--catalogo` deja el corpus sellado que lee `asistente_qlora.py`."""
    carpeta, _frags = _corpus_sellable(tmp_path)
    catalogo = tmp_path / 'catalogo.json'
    catalogo.write_text(json.dumps(CATALOGO), encoding='utf-8')
    destino = tmp_path / 'sellado'
    r = _herramienta(carpeta, '--catalogo', str(catalogo), '--sellar', str(destino))
    assert r.returncode == 0, r.stdout + r.stderr
    meta = json.loads((destino / 'dataset_manifest.json').read_text(encoding='utf-8'))
    assert meta['tipo_corpus'] == 'redaccion_pide' and meta['por_particion']['entrenamiento'] == 5
    assert meta['por_origen'] == {'humano': 4, 'maestro': 1}
    assert 'Villa Quimera' not in (destino / 'entrenamiento.jsonl').read_text(encoding='utf-8')


def test_reparto_por_tamano_no_deja_el_documento_mayor_fuera_del_entrenamiento():
    """072:RF-52 — cada documento entero en una partición, por su tamaño: el mayor entrena y las apartadas no pasan
    de su décima parte (caso real: diez documentos, uno de 444 de 704, que el reparto por huella dejó en selección)."""
    repartir = getattr(cr, 'repartir_documentos', None)
    assert callable(repartir), 'el reparto del sellado sigue por la huella del documento'
    tamanos = {f'g{i}': n for i, n in enumerate((444, 217, 19, 10, 9, 2, 1, 1, 1, 0))}
    tamanos = {g: n for g, n in tamanos.items() if n}
    parte = repartir(tamanos)
    assert set(parte) == set(tamanos)
    por = {}
    for g, p in parte.items():
        por[p] = por.get(p, 0) + tamanos[g]
    assert parte['g0'] == 'entrenamiento' and parte['g1'] == 'entrenamiento'
    assert por['entrenamiento'] >= 0.9 * sum(tamanos.values())
    assert all(por.get(p, 0) > 0 for p in ('seleccion', 'calibracion', 'prueba'))
    assert repartir(dict(reversed(list(tamanos.items())))) == parte, 'el reparto depende del orden de llegada'
    assert set(repartir({'a': 3, 'b': 2, 'c': 1}).values()) == {'entrenamiento'}
