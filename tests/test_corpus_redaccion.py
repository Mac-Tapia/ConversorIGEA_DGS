"""Spec 072, T9: los entregables de otra empresa enseñan a redactar, con revisión humana y nunca como verdad eléctrica."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from convertersmartgrid.asistente.corpus_redaccion import (
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
    """072:RF-19 — un fragmento sin revisar, o revisado por el maestro, no entra en el entrenamiento."""
    carpeta, frags = corpus
    registro = carpeta / 'revision.jsonl'
    assert ejemplos_para_entrenar(registro, frags) == []
    with pytest.raises(CorpusRedaccionError, match='humana'):
        registrar_revision(registro, frags[0], revisor='maestro', origen='maestro', aprobado=True, uso='redaccion')
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


def test_herramienta_registra_y_exporta(corpus, tmp_path):
    """072:RF-19 — la herramienta lista lo pendiente, registra decisiones humanas y exporta lo aprobado."""
    carpeta, _frags = corpus
    decisiones = tmp_path / 'decisiones.json'
    decisiones.write_text(json.dumps([{'record_id': 'r1', 'aprobado': True, 'uso': 'redaccion', 'nota': 'n'}]),
                          encoding='utf-8')
    herramienta = RAIZ / 'tools' / 'corpus_redaccion_pide.py'
    base = [sys.executable, str(herramienta), '--dataset', str(carpeta)]
    r = subprocess.run(base + ['--decisiones', str(decisiones), '--revisor', 'ing. revisor'],
                       capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stdout + r.stderr
    salida = tmp_path / 'ejemplos.jsonl'
    r = subprocess.run(base + ['--exportar', str(salida)], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stdout + r.stderr
    filas = [json.loads(x) for x in salida.read_text(encoding='utf-8').splitlines()]
    assert [f['record_id'] for f in filas] == ['r1'] and 'Aprobados: 1' in r.stdout
    sin_revisor = subprocess.run(base + ['--decisiones', str(decisiones)], capture_output=True, text=True,
                                 encoding='utf-8')
    assert sin_revisor.returncode == 2 and 'revisor' in sin_revisor.stdout
