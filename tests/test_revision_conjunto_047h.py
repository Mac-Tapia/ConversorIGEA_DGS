"""047:RF-43 / RF-85 a RF-88 — la medida de la T16, tras las dudas sobre el coste que comprobó el código, la acción
copiada como duda, la cantidad frente a la longitud de cada elemento y la prohibición que halla el código, es con el
conjunto 047h.

El 047g ya orientó el diagnóstico (dudas sobre un coste que cuadra, la acción como duda, una cantidad frente a una
longitud, una prohibición sin ver), así que no vale para la aceptación: la medida usa `docs/REVISION_ROLES_CASOS_047h.json`, declarado antes de medir
con las mismas reglas que los anteriores. Aquí no hay Ollama: el cliente es falso y prueba el camino de la herramienta.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from test_revision_conjunto_047b import (  # noqa: F401  (``ollama_falso`` es un fixture)
    HUELLAS_EMPRESAS, RAZON_SOCIAL, _herramienta, _huella_sin_declaracion, _leer, _main, ollama_falso)

RAIZ = Path(__file__).resolve().parents[1]
G047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047h.json'
PREVIOS = [RAIZ / 'docs' / f'REVISION_ROLES_CASOS_047{s}.json' for s in ('b', 'c', 'd', 'e', 'f', 'g')]
#: Declarada el 2026-11-23 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047H = '9664d385e0cf5c8bf16fdc306c081c79c5ceeecff45a7f327d41777a9bea1594'


def _t16() -> str:
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    texto = tareas.read_text(encoding='utf-8')
    assert '- [ ] T16.' in texto, 'la spec 047 no tiene la tarea de la medida con el 047h'
    return texto.split('- [ ] T16.', 1)[1].split('\n- [', 1)[0]


def test_conjunto_047h_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T16, con la fecha y la orden de la medida."""
    herramienta = _herramienta()
    assert G047.is_file(), 'no está el conjunto 047h'
    contenido = json.loads(G047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(G047.name) == HUELLA_047H
    assert _huella_sin_declaracion(contenido) == HUELLA_047H, 'el conjunto 047h cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047H and declaracion['fecha'] == '2026-11-23'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(G047) == HUELLA_047H
    t16 = _t16()
    assert HUELLA_047H in t16 and '2026-11-23' in t16
    assert '--conjunto docs/REVISION_ROLES_CASOS_047h.json' in t16, 'la T16 no deja la orden de la medida con el 047h'
    assert '047g' in t16 and 'no vale para la aceptación' in t16


def test_conjunto_047h_nuevo_seis_y_seis_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 6 sanos y 6 con un error, nada del 047 al 047g, nombres opacos y sin empresas."""
    herramienta = _herramienta()
    casos = _leer(herramienta, G047)
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


def test_medida_047h_con_cifras_de_otras_formas(tmp_path, ollama_falso):
    """047:RF-76 / RF-77 — el 047h trae costes por partidas, por unidad, por km y totales en sanos y con error; con un
    revisor que lo aprueba todo, la comprobación del coste no da ninguna falsa alarma en los sanos."""
    herramienta = _herramienta()
    casos = _leer(herramienta, G047)
    marcas = re.compile(r'c/u|cada uno|por unidad|/km|por km|en total|[Pp]artidas')
    for defecto in (None, 'coste'):
        assert any(marcas.search(t) for c in casos if c['defecto'] == defecto for t in c['evidencia'].values())
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(G047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == G047.name and informe['conjunto_sha256'] == HUELLA_047H
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['falsas_alarmas'] == 0 and informe[modo]['sin_respuesta'] == 0
        assert informe[modo].get('comprobaciones_fallidas') == informe[modo]['detectados']
