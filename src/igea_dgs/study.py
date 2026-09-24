"""Estudio o proyecto de CYMDIST (``.zxst`` / ``.xst``) — entrada **opcional**.

Un estudio no contiene la red: la topología vive en la base ``.mdb`` o en el TXT. Lo
que aporta es **qué alimentadores forman parte del estudio**, de modo que se puede
convertir exactamente ese conjunto en lugar de elegirlos a mano.

Formato observado (CYME International T&D, 2026): el ``.zxst`` es un ZIP con un único
``.xst`` dentro, que es XML con raíz ``<Cyme>``. La lista de redes está en
``<Networks>``, con un ``<NetworkID>`` por alimentador.

Es opcional por diseño: sin estudio se convierte todo, o lo que el operador seleccione.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

STUDY_SUFFIXES = ('.zxst', '.xst')


class StudyReadError(RuntimeError):
    """El fichero no es un estudio CYMDIST legible."""


def _study_xml(path: Path) -> bytes:
    if not path.is_file():
        raise StudyReadError(f'No se encuentra el estudio: {path}')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.xst')]
            if not names:
                raise StudyReadError(
                    f'{path.name}: el ZIP no contiene ningún .xst. '
                    'No parece un estudio CYMDIST.'
                )
            return archive.read(names[0])
    return path.read_bytes()


def study_networks(path: Path | str) -> list[str]:
    """``NetworkId`` que el estudio incluye, en orden alfabético y sin repetidos.

    Devuelve los identificadores completos, tal como los usa la base; se pasan a
    :func:`igea_dgs.access.read_access_dataset` como ``networks``.
    """
    study_path = Path(path)
    raw = _study_xml(study_path)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise StudyReadError(f'{study_path.name}: XML ilegible ({exc}).') from exc

    networks: set[str] = set()
    # <Networks><NetworkID>…</NetworkID>…</Networks> es la lista del estudio. Otros
    # elementos (factores de escala, arc flash) también llevan NetworkID pero se
    # refieren a ajustes puntuales, no al alcance: no se toman.
    for container in root.iter('Networks'):
        for child in container:
            if child.tag.endswith('NetworkID') and (child.text or '').strip():
                networks.add(child.text.strip())

    if not networks:
        raise StudyReadError(
            f'{study_path.name}: no se encontró ninguna red en <Networks>. '
            'El estudio puede ser de otra versión de CYMDIST; convierta sin --study.'
        )
    return sorted(networks)


def describe(path: Path | str) -> dict:
    """Resumen del estudio para el manifiesto y para el registro de la interfaz."""
    study_path = Path(path)
    networks = study_networks(study_path)
    return {
        'study': str(study_path),
        'study_name': study_path.stem,
        'networks': networks,
        'network_count': len(networks),
    }
