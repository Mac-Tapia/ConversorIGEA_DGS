"""La biblioteca normativa en el asistente: el índice y la consulta la leen por su API, no por una copia fija.

Cada regla de la biblioteca es un fragmento del corpus ampliado, con la fuente ``normativa:<acto>#<clave>`` y el texto
«<acto> · <artículo o anexo> · <clave> = <valor> · <estado> · vigente desde … · cita literal». Una norma o una
modificatoria que se añada a la biblioteca entra en la siguiente indexación, porque la huella del corpus incluye la de
la biblioteca. Las normas de solo referencia (técnicas con derechos y bibliografía) van sin texto: título, edición y
cláusula usada. Una cita normativa se comprueba contra la API: la regla tiene que seguir en la biblioteca con el mismo
texto. La biblioteca es universal: nada de una empresa entra en ella.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from ...dominio.registro_normativo import Norma, Regla, RegistroError, RegistroNormativo, cargar_registro

#: Prefijo de la fuente de un fragmento normativo; lo que sigue es ``<acto>#<clave>``.
PREFIJO = 'normativa:'
#: Lo que se reparte en el texto de una cita literal larga, para que el fragmento quepa en el índice.
TOPE_CITA = 600
CARPETAS = ('config/normativa', 'config/vad')


def biblioteca(repo: Path | str, fecha: str | None = None) -> RegistroNormativo:
    """La biblioteca normativa, por su API (``biblioteca_normativa.cargar_biblioteca``) cuando existe; sin ella, el
    registro de la entrega (``config/normativa`` y ``config/vad``). Es el único punto por el que el asistente la lee."""
    try:
        from ..biblioteca_normativa import cargar_biblioteca
    except ImportError:
        raiz = Path(repo)
        return cargar_registro(*(raiz / c for c in CARPETAS if (raiz / c).is_dir()))
    return cargar_biblioteca(fecha, raiz=Path(repo))


def huella(repo: Path | str) -> str:
    """La huella de la biblioteca: cambia cuando se añade, modifica o retira una norma."""
    try:
        from ..biblioteca_normativa import huella_biblioteca
    except ImportError:
        raiz = Path(repo)
        h = hashlib.sha256()
        for c in CARPETAS:
            for p in sorted((raiz / c).glob('*.json')):
                h.update(f'{c}/{p.name}\n'.encode())
                h.update(p.read_bytes())
        return h.hexdigest()
    return huella_biblioteca(raiz=Path(repo))


def _hoy() -> str:
    return date.today().isoformat()


def _estado(norma: Norma, hoy: str) -> str:
    if norma.solo_referencia:
        return 'solo_referencia'
    if not norma.vigente_en(hoy):
        return 'no_vigente'
    return norma.estado_juridico


def _valor(valor: Any) -> str:
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, sort_keys=True)


def texto_de(norma: Norma, regla: Regla, hoy: str | None = None) -> str:
    """El texto del fragmento de una regla. Una norma de solo referencia no lleva cita: título, edición y cláusula."""
    hoy = hoy or _hoy()
    partes = [norma.acto, regla.articulo_o_anexo or 'sin artículo', f'{regla.clave} = {_valor(regla.valor)}'
              + (f' {regla.unidad}' if regla.unidad else ''), _estado(norma, hoy)]
    if norma.vigencia_desde:
        partes.append(f'vigente desde {norma.vigencia_desde}'
                      + (f' hasta {norma.vigencia_hasta}' if norma.vigencia_hasta else ''))
    partes.append(norma.titulo)
    if norma.solo_referencia:
        partes.append(f'solo referencia: {norma.solo_referencia}' + (f', edición {norma.version}' if norma.version else ''))
    elif regla.cita_literal:
        partes.append(f'cita: {regla.cita_literal[:TOPE_CITA]}')
    if regla.interpretacion:
        partes.append(f'interpretación: {regla.interpretacion[:TOPE_CITA]}')
    return ' · '.join(partes)


def fuente_de(norma: Norma, regla: Regla) -> str:
    return f'{PREFIJO}{norma.acto}#{regla.clave}'


def vigencia_de(norma: Norma, hoy: str | None = None) -> str:
    """``vigente`` o ``historico``, como los ficheros del corpus: una norma derogada o aún no vigente es histórica."""
    return 'vigente' if norma.vigente_en(hoy or _hoy()) else 'historico'


def trozos(registro: RegistroNormativo, hoy: str | None = None) -> list[tuple[str, str, str]]:
    """``(fuente, texto, vigencia)`` de cada regla de la biblioteca, en orden de acto y clave."""
    hoy = hoy or _hoy()
    out = []
    for acto in sorted(registro.normas):
        norma = registro.normas[acto]
        for regla in sorted(norma.reglas, key=lambda r: r.clave):
            out.append((fuente_de(norma, regla), texto_de(norma, regla, hoy), vigencia_de(norma, hoy)))
    return out


def es_normativa(fuente: str) -> bool:
    return str(fuente).startswith(PREFIJO)


def _partes(fuente: str) -> tuple[str, str]:
    acto, _, clave = str(fuente)[len(PREFIJO):].partition('#')
    return acto, clave


def verificar(registro: RegistroNormativo, fuente: str, texto: str, hoy: str | None = None) -> bool:
    """Si la cita sigue en la biblioteca con el mismo texto (047:RF-29, para la norma)."""
    if not es_normativa(fuente):
        return False
    acto, clave = _partes(fuente)
    norma = registro.normas.get(acto)
    regla = next((r for r in (norma.reglas if norma else ()) if r.clave == clave), None)
    return regla is not None and texto_de(norma, regla, hoy) == texto


def _coincide(norma: Norma, regla: Regla, palabras: Iterable[str]) -> bool:
    plano = ' '.join((norma.acto, norma.titulo, regla.clave, regla.articulo_o_anexo, regla.cita_literal,
                      regla.interpretacion, regla.aplicacion)).casefold()
    return all(p in plano for p in palabras)


def consultar_norma(repo: Path | str, clave: str | None = None, texto: str | None = None, fecha: str | None = None,
                    *, politica: Any = None, tope: int = 10) -> dict[str, Any]:
    """La herramienta de lectura del asistente sobre la biblioteca: la regla vigente de ``clave`` en ``fecha`` (con su
    norma, artículo, estado y cita), o las reglas cuyo texto contiene todas las palabras de ``texto``. Solo lectura."""
    del politica  # la biblioteca es pública y universal: no hay datos locales que proteger
    registro = biblioteca(repo, fecha)
    hoy = fecha or _hoy()
    if clave:
        try:
            vigente = registro.regla(clave, fecha)
        except RegistroError as exc:
            return {'herramienta': 'consultar_norma', 'clave': clave, 'existe': False, 'motivo': str(exc),
                    'fuente': f'{PREFIJO}#{clave}', 'vigencia': 'vigente', 'estado_spec': None}
        reglas = [(vigente.norma, vigente.regla)]
    else:
        palabras = [p for p in str(texto or '').casefold().split() if len(p) > 2]
        if not palabras:
            return {'herramienta': 'consultar_norma', 'existe': False, 'motivo': 'falta la clave o el texto',
                    'fuente': PREFIJO, 'vigencia': 'vigente', 'estado_spec': None}
        reglas = [(n, r) for a in sorted(registro.normas) for n in (registro.normas[a],)
                  for r in sorted(n.reglas, key=lambda r: r.clave) if _coincide(n, r, palabras)][:tope]
    if not reglas:
        return {'herramienta': 'consultar_norma', 'texto': texto, 'existe': False, 'motivo': 'ninguna regla coincide',
                'fuente': PREFIJO, 'vigencia': 'vigente', 'estado_spec': None}
    hallados = [{'fuente': fuente_de(n, r), 'texto': texto_de(n, r, hoy), 'clave': r.clave, 'norma': n.acto,
                 'articulo_o_anexo': r.articulo_o_anexo, 'valor': r.valor, 'estado': _estado(n, hoy),
                 'vigencia': vigencia_de(n, hoy)} for n, r in reglas]
    primero = hallados[0]
    return {'herramienta': 'consultar_norma', 'clave': clave, 'texto': texto, 'existe': True, 'reglas': hallados,
            'fuente': primero['fuente'], 'vigencia': primero['vigencia'], 'estado_spec': None,
            'sha256': hashlib.sha256(json.dumps(hallados, ensure_ascii=False, sort_keys=True,
                                                default=str).encode('utf-8')).hexdigest()}
