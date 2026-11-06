"""Lo que los entregables de otra empresa enseñan al asistente: redactar y dar formato (spec 072, RF-19).

El usuario autorizó el 2026-11-02 usar los entregables PIDE de Electro Oriente para entrenar, «con revisión
humana», y la spec lo limita a redactar y dar formato, nunca como verdad eléctrica: las cifras de esos
informes son de otra red y tienen incoherencias propias (103 proyectos en ALT1 frente a 81 hojas de
evaluación). Por eso aquí:

* solo entra un fragmento que una persona revisó y aprobó, con su nombre y su fecha; el maestro destila
  órdenes (memoria «maestro hace de humano»), pero esta autorización pide revisión humana y no la sustituye;
* el uso declarado es ``redaccion`` o ``formato``; cualquier otro se rechaza al registrar;
* el texto entra con las cifras y los códigos de elementos ocultos: el modelo aprende cómo se escribe una
  sección, no los kW ni las barras de otra empresa;
* el registro es solo de añadir (JSONL), la última decisión de cada fragmento manda, y una revisión vale
  para el texto que se revisó: si el corpus se reconstruye y el texto cambia, vuelve a estar pendiente.

Los fragmentos son los de ``pide_dataset`` (``fragments.jsonl``). Las hojas de cálculo no son redacción: los
formatos se aprenden por sus columnas en ``ejemplos_pide`` (027:RF-48), no por sus cifras.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

#: Usos que autoriza 072:RF-19; «verdad eléctrica» no es uno de ellos.
USOS = ('redaccion', 'formato')
SCHEMA = 'csg-corpus-redaccion-revision-v1'

_CODIGO = re.compile(r'\b(?=[A-Za-zÁÉÍÓÚÑáéíóúñ]*\d)(?=\d*[A-Za-zÁÉÍÓÚÑáéíóúñ])[A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]*\d'
                     r'[A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]*\b')
_NUMERO = re.compile(r'\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*')


class CorpusRedaccionError(ValueError):
    """Una revisión que no cumple lo que autoriza 072:RF-19."""


def sin_cifras(texto: str) -> str:
    """El texto con los códigos de elementos y las cifras ocultos: la forma queda, los valores no."""
    return _NUMERO.sub('‹n›', _CODIGO.sub('‹código›', texto))


def huella_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _es_redaccion(fragmento: Mapping[str, Any]) -> bool:
    return not str(fragmento.get('location') or '').startswith('sheet:') and bool(str(fragmento.get('text') or '').strip())


def _leer(registro: Path) -> list[dict]:
    if not registro.is_file():
        return []
    return [json.loads(x) for x in registro.read_text(encoding='utf-8').splitlines() if x.strip()]


def _vigentes(registro: Path) -> dict[str, dict]:
    """La última decisión de cada fragmento: el registro solo se añade, nunca se reescribe."""
    ultimas: dict[str, dict] = {}
    for fila in _leer(registro):
        ultimas[fila['record_id']] = fila
    return ultimas


def registrar_revision(registro: Path | str, fragmento: Mapping[str, Any], *, revisor: str, origen: str,
                       aprobado: bool, uso: str, fecha: str | None = None, nota: str = '') -> dict:
    """Anota la decisión de una persona sobre un fragmento (072:RF-19) y la devuelve."""
    if origen != 'humano':
        raise CorpusRedaccionError(f'072:RF-19 pide revisión humana; «{origen}» no lo es')
    if not str(revisor or '').strip():
        raise CorpusRedaccionError('la revisión no dice quién es el revisor')
    if uso not in USOS:
        raise CorpusRedaccionError(f'uso «{uso}» no autorizado: solo {", ".join(USOS)}, nunca como verdad eléctrica')
    if not fragmento.get('record_id') or not _es_redaccion(fragmento):
        raise CorpusRedaccionError('el fragmento no es texto de un informe con su record_id')
    fila = {'schema': SCHEMA, 'record_id': str(fragmento['record_id']),
            'huella_texto': huella_texto(str(fragmento['text'])), 'fuente': fragmento.get('relative_path') or '',
            'empresa': fragmento.get('empresa') or '', 'periodo': fragmento.get('periodo') or '',
            'uso': uso, 'aprobado': bool(aprobado), 'verdad_electrica': False,
            'revisor': str(revisor).strip(), 'origen': origen, 'fecha': fecha or date.today().isoformat(),
            'nota': nota}
    registro = Path(registro)
    registro.parent.mkdir(parents=True, exist_ok=True)
    with registro.open('a', encoding='utf-8') as f:
        f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + '\n')
    return fila


def ejemplos_para_entrenar(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Los fragmentos aprobados por una persona, con su texto sin cifras y su procedencia (072:RF-19)."""
    vigentes = _vigentes(Path(registro))
    out = []
    for f in fragmentos:
        r = vigentes.get(str(f.get('record_id')))
        if (r is None or not r['aprobado'] or r.get('origen') != 'humano' or r.get('uso') not in USOS
                or not _es_redaccion(f) or r['huella_texto'] != huella_texto(str(f['text']))):
            continue
        out.append({'record_id': r['record_id'], 'uso': r['uso'], 'texto': sin_cifras(str(f['text'])),
                    'fuente': r['fuente'], 'empresa': r['empresa'], 'periodo': r['periodo'],
                    'revisor': r['revisor'], 'fecha': r['fecha'], 'verdad_electrica': False})
    return out


def pendientes(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Los fragmentos de redacción sin una revisión del texto que tienen hoy."""
    vigentes = _vigentes(Path(registro))
    return [f for f in fragmentos if _es_redaccion(f)
            and (vigentes.get(str(f.get('record_id'))) or {}).get('huella_texto') != huella_texto(str(f['text']))]


def resumen(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]]) -> dict:
    """Cuánto del corpus está revisado, aprobado y pendiente: el registro del corpus revisado (T9)."""
    fragmentos = [f for f in fragmentos if _es_redaccion(f)]
    vigentes = _vigentes(Path(registro))
    revisadas = [vigentes[str(f['record_id'])] for f in fragmentos
                 if (vigentes.get(str(f.get('record_id'))) or {}).get('huella_texto') == huella_texto(str(f['text']))]
    aprobadas = [r for r in revisadas if r['aprobado']]
    return {'fragmentos': len(fragmentos), 'revisados': len(revisadas), 'aprobados': len(aprobadas),
            'rechazados': len(revisadas) - len(aprobadas), 'pendientes': len(fragmentos) - len(revisadas),
            'por_uso': dict(Counter(r['uso'] for r in aprobadas)),
            'revisores': sorted({r['revisor'] for r in revisadas})}
