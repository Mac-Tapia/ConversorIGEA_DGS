"""047:RF-43 / RF-50 — la medida de la T10, tras las contradicciones estructuradas (MEJ24b), es con el conjunto 047d.

El 047c ya orientó el diagnóstico (comprobaciones que coinciden escritas como contradicciones), así que no vale para la
aceptación: la medida usa `docs/REVISION_ROLES_CASOS_047d.json`, declarado antes de medir con las mismas reglas que el
047b y el 047c. Aquí no hay Ollama: el cliente es falso y prueba el camino de la herramienta; no acredita ningún LLM.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from test_revision_conjunto_047b import (  # noqa: F401  (``ollama_falso`` es un fixture)
    HUELLAS_EMPRESAS, RAZON_SOCIAL, _herramienta, _huella_sin_declaracion, _leer, _main, ollama_falso)

RAIZ = Path(__file__).resolve().parents[1]
D047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047d.json'
PREVIOS = [RAIZ / 'docs' / f'REVISION_ROLES_CASOS_047{s}.json' for s in ('b', 'c')]
#: Declarada el 2026-11-21 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047D = '2da22130778488aa9e2a71583e6799c30fb41ce403796a5d6261fbb1a50887cc'


def _t10() -> str:
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    texto = tareas.read_text(encoding='utf-8')
    assert '- [ ] T10.' in texto, 'la spec 047 no tiene la tarea de la medida con el 047d'
    return texto.split('- [ ] T10.', 1)[1].split('\n- [', 1)[0]


def test_conjunto_047d_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T10, con la fecha y la orden de la medida."""
    herramienta = _herramienta()
    assert D047.is_file(), 'no está el conjunto 047d'
    contenido = json.loads(D047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(D047.name) == HUELLA_047D
    assert _huella_sin_declaracion(contenido) == HUELLA_047D, 'el conjunto 047d cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047D and declaracion['fecha'] == '2026-11-21'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(D047) == HUELLA_047D
    t10 = _t10()
    assert HUELLA_047D in t10 and '2026-11-21' in t10
    assert '--conjunto docs/REVISION_ROLES_CASOS_047d.json' in t10, 'la T10 no deja la orden de la medida con el 047d'
    assert '047c' in t10 and 'no vale para la aceptación' in t10


def test_conjunto_047d_nuevo_seis_y_seis_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 6 sanos y 6 con un error, nada del 047, el 047b ni el 047c, nombres opacos y sin empresas."""
    herramienta = _herramienta()
    casos = _leer(herramienta, D047)
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


def test_medida_047d_cuenta_lo_descartado(tmp_path, ollama_falso):
    """047:RF-50 — el informe de la medida con el 047d dice cuántas contradicciones descartó el código y cuántas
    decisiones recalculó; con un revisor que no anota ninguna, cero."""
    herramienta = _herramienta()
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(D047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == D047.name and informe['conjunto_sha256'] == HUELLA_047D
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo].get('contradicciones_descartadas') == 0
        assert informe[modo].get('decisiones_recalculadas') == 0
        # 047:RF-77 (MEJ24d): los defectos de coste los halla el código solo, sin el LLM.
        fallidas = informe[modo].get('comprobaciones_fallidas')
        assert informe[modo]['falsas_alarmas'] == 0 and fallidas == 2, 'el código no comprueba el coste'
        assert informe[modo]['perdidos'] == 6 - fallidas
