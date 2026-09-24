"""La GUI se construye y cada campo llega a un parámetro real del motor.

`gui.py` no tenía ninguna prueba (F-08 del diagnóstico 2026-09-22). Estas cubren
lo mínimo que se rompe en silencio: un campo que deja de pasarse al motor, un
parámetro renombrado en `convert_selection`, o un preset de CRS que reintroduce
el defecto C-01.

Las dos primeras no necesitan pantalla; solo la de construcción requiere Tk.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from igea_dgs.batch import convert_selection

GUI_SOURCE = Path(__file__).resolve().parents[1] / 'src' / 'igea_dgs' / 'gui.py'

# Campos que no son parámetros directos de convert_selection: rutas de entrada que
# construyen el dataset, destino posicional, o estado puramente visual.
INDIRECT_FIELDS = {
    # Alternativa 1 de entrada → CymdistDataset.from_files, vía _load_input_dataset
    'red', 'loads', 'equipment',
    # Alternativa 2 de entrada → access.read_access_dataset, vía _load_input_dataset
    'input_mode', 'mdb', 'equipment_mdb',
    'study',                      # → study.study_networks, vía _load_input_dataset
    'out_dir',                    # → out_dir posicional
    'aliases',                    # → aliases, vía load_aliases
    'convert_all',                # → all_feeders, vía _start_convert
    'files_ready', 'status',      # solo UI
}


def _gui_source() -> str:
    return GUI_SOURCE.read_text(encoding='utf-8')


def _declared_fields(source: str) -> set[str]:
    return set(re.findall(r'self\.(\w+) = (?:StringVar|BooleanVar)', source))


def _engine_kwargs(source: str) -> dict[str, str]:
    """{parámetro del motor: campo de la GUI} leídos del bloque kwargs = dict(...)."""
    block = source.split('kwargs = dict(')[1].split(')\n')[0]
    return dict(re.findall(r'(\w+)=self\.(\w+)\.get\(\)', block))


def test_every_gui_field_is_wired_to_the_engine():
    source = _gui_source()
    fields = _declared_fields(source)
    wired = set(_engine_kwargs(source).values())
    orphans = fields - wired - INDIRECT_FIELDS
    assert not orphans, f'Campos de la GUI que no llegan al motor: {sorted(orphans)}'


def test_both_input_alternatives_are_reachable_from_the_gui():
    """Las dos vías de entrada deben estar cableadas, no solo declaradas."""
    source = _gui_source()
    fields = _declared_fields(source)
    assert {'red', 'loads', 'equipment'} <= fields, 'falta la alternativa TXT'
    assert {'mdb', 'equipment_mdb', 'study'} <= fields, 'falta la alternativa Access'
    assert 'input_mode' in fields, 'falta el selector de alternativa'
    # _load_input_dataset es el punto único donde se resuelve la entrada.
    assert 'def _load_input_dataset' in source
    assert 'read_access_dataset' in source
    assert 'study_networks' in source
    assert 'CymdistDataset.from_files' in source


def test_load_update_module_is_wired():
    """Módulo de cargas: plantilla → fichero → plan → PowerFactory."""
    source = _gui_source()
    for handler in (
        '_download_load_template', '_apply_load_template',
        '_run_load_update', '_on_loads_done', '_single_selected_model',
    ):
        assert f'def {handler}' in source, handler
    # La plantilla y la lectura vienen del motor, no de la vista.
    assert 'write_template' in source and 'read_template' in source
    assert 'build_plan' in source and 'plan_to_payload' in source
    # El plan se aplica en proceso aparte con el intérprete de la API.
    assert 'apply_sed_loads.py' in source
    assert '_python_for_pf' in source


def test_gui_kwargs_match_convert_selection_signature():
    """Renombrar un parámetro del motor debe romper aquí, no en producción."""
    engine_params = set(inspect.signature(convert_selection).parameters)
    passed = set(_engine_kwargs(_gui_source()))
    unknown = passed - engine_params
    assert not unknown, f'La GUI pasa parámetros inexistentes en convert_selection: {sorted(unknown)}'


def test_source_crs_presets_are_all_projected_in_metres():
    """Ningún preset puede reintroducir el CRS en grados del defecto C-01."""
    pytest.importorskip('pyproj')
    from igea_dgs.geography import assert_metre_source_crs
    from igea_dgs.gui import CRS_PRESETS

    assert CRS_PRESETS, 'la lista de presets no puede quedar vacía'
    for crs in CRS_PRESETS:
        assert_metre_source_crs(crs)  # lanza ValueError si no está en metros


def test_gui_builds_with_expected_controls():
    tkinter = pytest.importorskip('tkinter')
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:  # sin display (CI headless)
        pytest.skip(f'Tk no disponible: {exc}')

    from igea_dgs.gui import ConverterApp

    try:
        root.withdraw()
        app = ConverterApp(root)
        root.update_idletasks()

        assert app.include_geography.get() is True, 'georreferenciación ON por defecto'
        assert app.strict.get() is True, 'modo estricto ON por defecto'
        assert app.source_crs.get(), 'debe haber un CRS de origen por defecto'
        assert app._action_buttons, 'debe registrar botones para deshabilitar durante _busy'

        # _set_busy no debe lanzar y debe alternar el estado de los botones.
        app._set_busy(True)
        assert all(str(b.cget('state')) == 'disabled' for b in app._action_buttons)
        app._set_busy(False)
        assert all(str(b.cget('state')) == 'normal' for b in app._action_buttons)

        # El CRS de origen sigue siendo editable: cualquier EPSG métrico es válido,
        # no solo los presets. Las unidades las verifica el motor.
        from tkinter import ttk

        def walk(widget, acc):
            for child in widget.winfo_children():
                acc.append(child)
                walk(child, acc)
            return acc

        combos = [w for w in walk(root, []) if isinstance(w, ttk.Combobox)]
        assert combos, 'debe existir el desplegable de CRS'
        assert str(combos[0].cget('state')) != 'readonly', (
            'el CRS de origen debe poder escribirse a mano (universalidad)'
        )
    finally:
        root.destroy()
