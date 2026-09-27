"""Creación y acceso a la Data Extension ``Alimentador`` en PowerFactory."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .feeder_metadata import TARGET_CLASSES


CONFIGURATION_NAME = 'Trazabilidad IGEA'
_ATTRIBUTE_NAME = 'alimentador'
_ATTRIBUTE_DESCRIPTION = 'Alimentador'


def data_extension_attribute_name() -> str:
    """Devuelve el nombre calificado que exponen los objetos de PowerFactory."""

    return f'p:{_ATTRIBUTE_NAME}'


def ensure_alimentador_data_extensions(
    project: Any,
    classes: Iterable[str] = TARGET_CLASSES,
) -> dict[str, list[Any]]:
    """Crea una sola columna ``Alimentador`` para cada clase objetivo.

    PowerFactory exige encerrar los cambios de Data Extensions entre
    ``BeginDataExtensionModification`` y ``EndDataExtensionModification``.
    Un fallo en una clase se registra sin impedir que se intenten las demás.
    """

    begin = getattr(project, 'BeginDataExtensionModification', None)
    end = getattr(project, 'EndDataExtensionModification', None)
    if project is None or not callable(begin) or not callable(end):
        raise RuntimeError(
            'No hay un proyecto activo o la API de Data Extensions no está disponible'
        )

    settings = begin()
    try:
        get_configuration = getattr(settings, 'GetConfiguration', None)
        add_configuration = getattr(settings, 'AddConfiguration', None)
        if settings is None or not callable(get_configuration) or not callable(add_configuration):
            raise RuntimeError('La API de Data Extensions no devolvió una configuración válida')

        report: dict[str, list[Any]] = {
            'created': [],
            'existing': [],
            'errors': [],
        }
        for class_name in classes:
            try:
                configuration = get_configuration(class_name, CONFIGURATION_NAME)
                if configuration is not None:
                    report['existing'].append(class_name)
                    continue

                configuration = add_configuration(class_name, CONFIGURATION_NAME)
                if configuration is None:
                    raise RuntimeError('AddConfiguration no devolvió una configuración')
                add_string = getattr(configuration, 'AddString', None)
                if not callable(add_string):
                    raise RuntimeError('La configuración no ofrece AddString')
                result = add_string(
                    _ATTRIBUTE_NAME,
                    _ATTRIBUTE_DESCRIPTION,
                    '',
                    '',
                )
                if result not in (None, 0):
                    raise RuntimeError(f'AddString devolvió {result!r}')
                report['created'].append(class_name)
            except Exception as exc:  # PowerFactory expone errores de tipos variables.
                report['errors'].append(
                    {'class_name': class_name, 'error': str(exc)}
                )
        return report
    finally:
        end()
