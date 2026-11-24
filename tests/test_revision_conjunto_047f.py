"""047:RF-43 / RF-75 a RF-78 — la medida de la T13, tras las cuentas, la conversión a total y la comprobación del coste
(MEJ24d), es con el conjunto 047f.

El 047e ya orientó el diagnóstico (cuentas descartadas, precios por km frente al total, bases declaradas al azar),
así que no vale para la aceptación: la medida usa `docs/REVISION_ROLES_CASOS_047f.json`, declarado antes de medir
con las mismas reglas que los anteriores. Aquí no hay Ollama: el cliente es falso y prueba el camino de la herramienta.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from test_revision_conjunto_047b import (  # noqa: F401  (``ollama_falso`` es un fixture)
    HUELLAS_EMPRESAS, RAZON_SOCIAL, _herramienta, _huella_sin_declaracion, _leer, _main, ollama_falso)
from apoyo import bloque_de_tarea

RAIZ = Path(__file__).resolve().parents[1]
F047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047f.json'
PREVIOS = [RAIZ / 'docs' / f'REVISION_ROLES_CASOS_047{s}.json' for s in ('b', 'c', 'd', 'e')]
#: Declarada el 2026-11-21 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047F = '05c423913e4e49d4ebb370fd8d760f89e4cfb3319ce9001395dde08da33afea6'


def _t13() -> str:
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    texto = tareas.read_text(encoding='utf-8')
    assert bloque_de_tarea(texto, 'T13') is not None, 'la spec 047 no tiene la tarea de la medida con el 047f'
    return bloque_de_tarea(texto, 'T13')


def test_conjunto_047f_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T13, con la fecha y la orden de la medida."""
    herramienta = _herramienta()
    assert F047.is_file(), 'no está el conjunto 047f'
    contenido = json.loads(F047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(F047.name) == HUELLA_047F
    assert _huella_sin_declaracion(contenido) == HUELLA_047F, 'el conjunto 047f cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047F and declaracion['fecha'] == '2026-11-21'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(F047) == HUELLA_047F
    t13 = _t13()
    assert HUELLA_047F in t13 and '2026-11-21' in t13
    assert '--conjunto docs/REVISION_ROLES_CASOS_047f.json' in t13, 'la T13 no deja la orden de la medida con el 047f'
    assert '047e' in t13 and 'no vale para la aceptación' in t13


def test_conjunto_047f_nuevo_seis_y_seis_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 6 sanos y 6 con un error, nada del 047 al 047e, nombres opacos y sin empresas."""
    herramienta = _herramienta()
    casos = _leer(herramienta, F047)
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


def test_medida_047f_con_partidas_precios_y_totales(tmp_path, ollama_falso):
    """047:RF-76 / RF-77 — el 047f trae costes por partidas, por unidad, por km y totales en sanos y con error; con un
    revisor que lo aprueba todo, la comprobación del coste no da ninguna falsa alarma en los sanos."""
    herramienta = _herramienta()
    casos = _leer(herramienta, F047)
    marcas = re.compile(r'c/u|cada uno|por unidad|/km|por km|en total|[Pp]artidas')
    for defecto in (None, 'coste'):
        assert any(marcas.search(t) for c in casos if c['defecto'] == defecto for t in c['evidencia'].values())
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(F047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == F047.name and informe['conjunto_sha256'] == HUELLA_047F
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['falsas_alarmas'] == 0 and informe[modo]['sin_respuesta'] == 0
        assert informe[modo].get('comprobaciones_fallidas') == informe[modo]['detectados']
