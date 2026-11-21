"""047:RF-43 / RF-52 a RF-56 — la medida de la T11, tras las contradicciones fundadas y por base (MEJ24c), es con el
conjunto 047e.

El 047d ya orientó el diagnóstico (cifras con marcas, valores inventados, totales frente a precios por unidad), así que
no vale para la aceptación: la medida usa `docs/REVISION_ROLES_CASOS_047e.json`, declarado antes de medir con las mismas
reglas que los anteriores. Aquí no hay Ollama: el cliente es falso y prueba el camino de la herramienta.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from test_revision_conjunto_047b import (  # noqa: F401  (``ollama_falso`` es un fixture)
    HUELLAS_EMPRESAS, RAZON_SOCIAL, _herramienta, _huella_sin_declaracion, _leer, _main, ollama_falso)

RAIZ = Path(__file__).resolve().parents[1]
E047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047e.json'
PREVIOS = [RAIZ / 'docs' / f'REVISION_ROLES_CASOS_047{s}.json' for s in ('b', 'c', 'd')]
#: Declarada el 2026-11-21 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047E = '649863d4f383978a1e1e62984a4aa7b95140a76c556078a057b667adae0ae5da'


def _t11() -> str:
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    texto = tareas.read_text(encoding='utf-8')
    assert '- [ ] T11.' in texto, 'la spec 047 no tiene la tarea de la medida con el 047e'
    return texto.split('- [ ] T11.', 1)[1].split('\n- [', 1)[0]


def test_conjunto_047e_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T11, con la fecha y la orden de la medida."""
    herramienta = _herramienta()
    assert E047.is_file(), 'no está el conjunto 047e'
    contenido = json.loads(E047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(E047.name) == HUELLA_047E
    assert _huella_sin_declaracion(contenido) == HUELLA_047E, 'el conjunto 047e cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047E and declaracion['fecha'] == '2026-11-21'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(E047) == HUELLA_047E
    t11 = _t11()
    assert HUELLA_047E in t11 and '2026-11-21' in t11
    assert '--conjunto docs/REVISION_ROLES_CASOS_047e.json' in t11, 'la T11 no deja la orden de la medida con el 047e'
    assert '047d' in t11 and 'no vale para la aceptación' in t11


def test_conjunto_047e_nuevo_seis_y_seis_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 6 sanos y 6 con un error, nada del 047 al 047d, nombres opacos y sin empresas."""
    herramienta = _herramienta()
    casos = _leer(herramienta, E047)
    assert len(casos) == 12
    assert sum(c['defecto'] is None for c in casos) == 6 and sum(c['defecto'] is not None for c in casos) == 6
    assert {c['defecto'] for c in casos if c['defecto']} == herramienta.DEFECTOS - {None}
    previos = _leer(herramienta, herramienta.CONJUNTO) + [c for r in PREVIOS for c in _leer(herramienta, r)]
    assert not {c['propuesta']['accion'] for c in previos} & {c['propuesta']['accion'] for c in casos}
    assert not {t for c in previos for t in c['evidencia'].values()} & {t for c in casos for t in c['evidencia'].values()}
    assert not {c['id'] for c in previos} & {c['id'] for c in casos}
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


def test_medida_047e_con_cifras_variadas_y_bases(tmp_path, ollama_falso):
    """047:RF-52 / RF-55 — el 047e trae cifras con miles en punto, coma o espacio, moneda delante y precios por unidad o
    por kilómetro, en sanos y con error; la herramienta lo mide y cuenta lo descartado."""
    herramienta = _herramienta()
    casos = _leer(herramienta, E047)
    textos = [t for c in casos for t in c['evidencia'].values()]
    assert any(re.search(r'\d\.\d{3}(?!\d)', t) for t in textos) and any(re.search(r'\d,\d{3}(?!\d)', t) for t in textos)
    assert any(re.search(r'\d \d{3}', t) for t in textos) and any(re.search(r'\$\s?\d|USD \d', t) for t in textos)
    por_unidad = re.compile(r'por unidad|c/u|por kilómetro|/km')
    for defecto in (None, 'coste'):
        assert any(por_unidad.search(t) for c in casos if c['defecto'] == defecto for t in c['evidencia'].values())
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(E047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == E047.name and informe['conjunto_sha256'] == HUELLA_047E
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['contradicciones_descartadas'] == 0 and informe[modo]['decisiones_recalculadas'] == 0
