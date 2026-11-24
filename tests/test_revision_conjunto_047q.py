"""047:RF-43 / RF-96 a RF-101 — la aceptación de la T25, con el código que comprueba lo que no depende de
interpretar la red, es con el conjunto 047q, de 24 casos.

Del 047 al 047p orientaron las reglas, así que no valen para la aceptación: la medida usa
`docs/REVISION_ROLES_CASOS_047q.json`, declarado antes de medir
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
G047 = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047q.json'
PREVIOS = [RAIZ / 'docs' / f'REVISION_ROLES_CASOS_047{s}.json' for s in ('b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p')]
#: Declarada el 2026-11-24 antes de medir; si el conjunto cambia, esta prueba lo dice (047:RF-43).
HUELLA_047Q = 'eb04a0a39151cedf0e6ed31b449c91b860e23f2b5a32d62165795cc89ea23b0a'


def _t25() -> str:
    tareas = next((RAIZ / 'specs').glob('047-*')) / 'tasks.md'
    texto = tareas.read_text(encoding='utf-8')
    assert bloque_de_tarea(texto, 'T25') is not None, 'la spec 047 no tiene la tarea de la medida con el 047q'
    return bloque_de_tarea(texto, 'T25')


def test_conjunto_047q_declarado_antes_de_medir_y_fijo():
    """047:RF-43 — su huella está en la herramienta, en el fichero y en la T25, con la fecha y la orden de la medida."""
    herramienta = _herramienta()
    assert G047.is_file(), 'no está el conjunto 047q'
    contenido = json.loads(G047.read_text(encoding='utf-8'))
    assert herramienta.DECLARADOS.get(G047.name) == HUELLA_047Q
    assert _huella_sin_declaracion(contenido) == HUELLA_047Q, 'el conjunto 047q cambió después de declararse'
    declaracion = contenido['declaracion']
    assert declaracion['sha256'] == HUELLA_047Q and declaracion['fecha'] == '2026-11-24'
    assert declaracion['origen'] == 'maestro' and 'maestro' in contenido['descripcion']
    assert herramienta.huella(G047) == HUELLA_047Q
    t25 = _t25()
    assert HUELLA_047Q in t25 and '2026-11-24' in t25
    assert '--conjunto docs/REVISION_ROLES_CASOS_047q.json' in t25, 'la T25 no deja la orden de la medida con el 047q'
    assert '047p' in t25 and 'no vale para la aceptación' in t25


def test_conjunto_047q_nuevo_doce_y_doce_opaco_y_sintetico(tmp_path):
    """047:RF-39 / RF-43 — 12 sanos y 12 con un error, nada del 047 al 047p, nombres opacos y sin empresas."""
    herramienta = _herramienta()
    casos = _leer(herramienta, G047)
    assert len(casos) == 24
    assert sum(c['defecto'] is None for c in casos) == 12 and sum(c['defecto'] is not None for c in casos) == 12
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


def test_medida_047q_con_cifras_de_otras_formas(tmp_path, ollama_falso):
    """047:RF-76 / RF-77 — el 047q trae costes por partidas, por unidad, por km y totales en sanos y con error; con un
    revisor que lo aprueba todo, la comprobación del coste no da ninguna falsa alarma en los sanos."""
    herramienta = _herramienta()
    casos = _leer(herramienta, G047)
    # 047:RF-95: también «por <pieza>», «cada <pieza>» y «por kilómetro», que el 047m y el 047n escriben así.
    marcas = re.compile(r'c/u|cada uno|por unidad|/km|por km|por kil[oó]metro|el kil[oó]metro|en total|[Pp]artidas|'
                        r'por [a-z]{4,}|cada [a-z]{4,}')
    for defecto in (None, 'coste'):
        assert any(marcas.search(t) for c in casos if c['defecto'] == defecto for t in c['evidencia'].values())
    salida = tmp_path / 'informe.json'
    assert _main(herramienta, ['--modelo', 'falso:1', '--conjunto', str(G047), '--salida', str(salida)]) == 0
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert informe['conjunto'] == G047.name and informe['conjunto_sha256'] == HUELLA_047Q
    for modo in ('rol_unico', 'equipo'):
        assert informe[modo]['falsas_alarmas'] == 0 and informe[modo]['sin_respuesta'] == 0
        assert informe[modo].get('comprobaciones_fallidas') == informe[modo]['detectados']
