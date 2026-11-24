"""047:RF-43 / RF-47 — la medida de la T8 tras la corrección del 2026-11-21 (MEJ24) es con el conjunto 047c.

El 047b ya orientó el diagnóstico de MEJ24 (qwen3:8b: falsas alarmas, un perdido y dictámenes favorables con listas
pendientes), así que la medida que cierra la T8 usa `docs/REVISION_ROLES_CASOS_047c.json`, declarado antes de medir con
las mismas reglas que el 047b. Aquí no hay Ollama: el cliente es falso y prueba el camino de la herramienta y lo que
guarda el informe; no acredita la calidad de ningún LLM.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

from test_revision_conjunto_047b import (  # noqa: F401  (``ollama_falso`` es un fixture)
    HUELLAS_EMPRESAS, RAZON_SOCIAL, _herramienta, _huella_sin_declaracion, _leer, _main, ollama_falso)
from apoyo import bloque_de_tarea

RAIZ = Path(__file__).resolve().parents[1]
C047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047c.json'
B047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047b.json'
#: Declarada el 2026-11-21 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047C = '04f19184a45fed27966a880bd0f89a23d819db6836da22f13e3ab79ecd618d88'


def test_conjunto_047c_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T8 de la spec, con la fecha y su orden."""
    herramienta = _herramienta()
    contenido = json.loads(C047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(C047.name) == HUELLA_047C
    assert _huella_sin_declaracion(contenido) == HUELLA_047C, 'el conjunto 047c cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047C and declaracion['fecha'] == '2026-11-21'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(C047) == HUELLA_047C
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    t8 = bloque_de_tarea(tareas.read_text(encoding='utf-8'), 'T8')
    assert HUELLA_047C in t8 and '2026-11-21' in t8
    assert '--conjunto docs/REVISION_ROLES_CASOS_047c.json' in t8, 'la T8 no deja la orden de la medida con el 047c'


def test_conjunto_047c_nuevo_seis_y_seis_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 6 sanos y 6 con un error, ninguna propuesta ni evidencia del 047 ni del 047b, nombres opacos."""
    herramienta = _herramienta()
    casos = _leer(herramienta, C047)
    assert len(casos) == 12
    assert sum(c['defecto'] is None for c in casos) == 6 and sum(c['defecto'] is not None for c in casos) == 6
    assert {c['defecto'] for c in casos if c['defecto']} == herramienta.DEFECTOS - {None}
    previos = _leer(herramienta, herramienta.CONJUNTO) + _leer(herramienta, B047)
    assert not {c['propuesta']['accion'] for c in previos} & {c['propuesta']['accion'] for c in casos}
    assert not {t for c in previos for t in c['evidencia'].values()} & {t for c in casos for t in c['evidencia'].values()}
    texto = json.dumps([{k: c[k] for k in ('id', 'propuesta', 'evidencia')} for c in casos], ensure_ascii=False).lower()
    assert 'sano' not in texto and 'defecto' not in texto
    palabras = re.findall(r'[a-záéíóúñ]+', texto)
    for n in range(1, 5):
        for i in range(len(palabras) - n + 1):
            assert hashlib.sha256(' '.join(palabras[i:i + n]).encode('utf-8')).hexdigest()[:16] not in HUELLAS_EMPRESAS
    assert not RAZON_SOCIAL.search(texto)
    for caso in herramienta.materializar(casos, tmp_path):
        assert not re.search(r'sano|defecto', caso['contexto'].project)
    assert all(not re.search(r'sano|defecto', f.name) for f in tmp_path.iterdir())


def test_medida_047c_guarda_el_tope_y_lo_que_se_corto(tmp_path, ollama_falso):
    """047:RF-47 — el informe dice con qué tope se midió, cuántos tokens usó la intervención más larga y cuántas llegaron
    al tope; el tope por omisión es el de la revisión (1024), no 512."""
    from convertersmartgrid.aplicacion.asistente import revision_roles
    herramienta = _herramienta()
    assert herramienta.TOKENS == revision_roles.TOKENS == 1024
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(C047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == C047.name and informe['conjunto_sha256'] == HUELLA_047C and informe['tokens'] == 1024
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['tokens_tope'] == 1024
        assert informe[modo]['max_tokens_salida'] == 10 and informe[modo]['en_tope'] == 0
    salida2 = tmp_path / 'informe_10.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(C047), '--salida', str(salida2),
                               '--tokens', '10']) == 0
    informe = json.loads(salida2.read_text(encoding='utf-8'))
    assert informe['equipo']['tokens_tope'] == 10 and informe['equipo']['en_tope'] == informe['equipo']['intervenciones']


@pytest.mark.parametrize('tokens', ['0', '4097'])
def test_tope_fuera_de_rango_no_se_mide(tmp_path, ollama_falso, tokens):
    """047:RF-47 — el tope es un parámetro con su rango: fuera de él, ni se pregunta al LLM ni se escribe informe."""
    herramienta = _herramienta()
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(C047), '--salida', str(salida),
                               '--tokens', tokens]) == 2
    assert not salida.exists() and not ollama_falso
