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


@pytest.fixture(scope='module')
def app_tk():
    """Una sola ventana para todo el módulo.

    Tk no lleva bien crear y destruir muchas raíces en un mismo proceso: a partir de
    la tercera o cuarta falla con «tk wasn't installed properly» y la prueba se omite.
    Una prueba que a veces no corre no protege de nada, así que se construye la ventana
    una vez. Cada prueba que toque un campo lo fija antes de mirarlo, de modo que
    compartir la instancia no las hace depender del orden.
    """
    tkinter = pytest.importorskip('tkinter')
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:
        pytest.skip(f'Tk no disponible: {exc}')
    from igea_dgs.gui import ConverterApp

    root.withdraw()
    app = ConverterApp(root)
    root.update_idletasks()
    yield app
    root.destroy()


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


def test_gui_builds_with_expected_controls(app_tk):
    """Usa la ventana compartida a propósito.

    Antes creaba su propia raíz de Tk y la destruía. Tk no admite crear otra después en
    el mismo proceso —falla con «tk wasn't installed properly»—, así que todas las
    pruebas que vinieran detrás se omitían. Once de golpe, en silencio.
    """
    from tkinter import ttk

    app = app_tk
    assert app.include_geography.get() is True, 'georreferenciación ON por defecto'
    assert app.strict.get() is True, 'modo estricto ON por defecto'
    assert app.source_crs.get(), 'debe haber un CRS de origen por defecto'
    assert app._action_buttons, 'debe registrar botones para deshabilitar durante _busy'

    # _set_busy no debe lanzar y debe alternar el estado de los botones.
    app._set_busy(True)
    assert all(str(b.cget('state')) == 'disabled' for b in app._action_buttons)
    app._set_busy(False)
    assert all(str(b.cget('state')) == 'normal' for b in app._action_buttons)

    # El CRS de origen sigue siendo editable: cualquier EPSG métrico es válido, no solo
    # los presets. Las unidades las verifica el motor.
    def walk(widget, acc):
        for child in widget.winfo_children():
            acc.append(child)
            walk(child, acc)
        return acc

    combos = [w for w in walk(app.root, []) if isinstance(w, ttk.Combobox)]
    assert combos, 'debe existir el desplegable de CRS'
    assert str(combos[0].cget('state')) != 'readonly', (
        'el CRS de origen debe poder escribirse a mano (universalidad)'
    )


# ---------------------------------------------------------------------------
# Módulos de cargas: los cuatro que pidió el usuario deben tener botón y destino
# ---------------------------------------------------------------------------

#: (botón, manejador) de cada módulo. Un botón sin manejador es una interfaz que
#: promete algo que no hace, y es exactamente lo que pasó con la creación de SED:
#: el motor estaba escrito y solo se llegaba a él por línea de órdenes.
MODULOS_DE_CARGAS = (
    ('template_btn', '_download_load_template'),
    ('apply_loads_btn', '_apply_load_template'),
    ('create_template_btn', '_download_create_template'),
    ('create_apply_btn', '_apply_create_template'),
    ('create_one_btn', '_create_single_load'),
    ('catalog_build_btn', '_build_catalog'),
    ('catalog_apply_btn', '_apply_catalog'),
    ('grid_btn', '_build_system_grid'),
    ('anio0_btn', '_run_base_scenario'),
    ('datos_btn', '_missing_data'),
)


@pytest.mark.parametrize('_boton,manejador', MODULOS_DE_CARGAS)
def test_cada_boton_tiene_su_manejador(_boton, manejador):
    from igea_dgs.gui import ConverterApp

    assert callable(getattr(ConverterApp, manejador, None)), (
        f'{manejador} no existe: el botón no lleva a ninguna parte'
    )


def test_los_manejadores_llegan_al_motor_de_creacion():
    """Los botones de creación deben usar loads_create, no reimplementar sus reglas."""
    source = _gui_source()
    cuerpo = source.split('def _download_create_template')[1]
    for simbolo in ('write_create_template', 'read_create_workbook',
                    'build_create_plan', 'single_new_load', 'create_plan_to_payload'):
        assert simbolo in cuerpo, f'la GUI no usa {simbolo}'


def test_la_creacion_lanza_el_script_de_creacion_y_no_el_de_actualizacion():
    source = _gui_source()
    cuerpo = source.split('def _finish_create')[1].split('def ')[0]
    assert "script_name='create_sed_loads.py'" in cuerpo


def test_el_formulario_de_una_sed_no_valida_por_su_cuenta():
    """Si el formulario validase aparte, divergiría de la plantilla."""
    source = _gui_source()
    clase = source.split('class _NewSedDialog')[1].split('\nclass ')[0]
    # Se mira el código, no la explicación: el docstring sí nombra a quien valida.
    codigo = clase.split('"""', 2)[-1]
    # Solo convierte texto a número; las reglas de negocio no viven aquí.
    for prohibido in ('single_new_load', 'find_nearest_node', 'select_conductor',
                      'build_create_plan'):
        assert prohibido not in codigo, f'el diálogo no debe decidir {prohibido}'


def test_el_catalogo_se_aplica_al_modelo_y_no_al_txt():
    source = _gui_source()
    cuerpo = source.split('def _apply_catalog')[1].split('\n    def ')[0]
    assert 'aplicar_correcciones' in cuerpo
    assert 'El TXT de origen no se toca' in cuerpo


@pytest.mark.parametrize('_boton,_manejador', MODULOS_DE_CARGAS)
def test_los_botones_se_deshabilitan_mientras_trabaja(_boton, _manejador):
    """Todo botón de acción debe registrarse en _action_buttons."""
    source = _gui_source()
    bloque = source.split('_action_buttons.extend')
    registrados = ' '.join(bloque[1:])
    assert f'self.{_boton}' in registrados, (
        f'{_boton} no se deshabilita durante una operación larga'
    )


def test_la_gui_trata_los_cambios_como_objetos_y_no_como_texto():
    """`aplicar_correcciones` devuelve objetos Cambio, no cadenas.

    Esta prueba existe porque el cambio de tipo de retorno pasó desapercibido: la GUI
    siguió haciendo `'\\n'.join(cambios)`, que revienta con objetos, y ninguna prueba
    lo tocaba porque la rama solo se recorre con una pantalla delante.
    """
    source = _gui_source()
    cuerpo = source.split('def _apply_catalog')[1].split('\n    def ')[0]
    assert 'c.linea() for c in cambios' in cuerpo, (
        'la GUI debe formatear cada Cambio con .linea()'
    )
    assert "'\\n'.join(cambios" not in cuerpo, (
        'unir objetos Cambio como si fueran cadenas lanza TypeError'
    )


def test_la_gui_avisa_de_los_cambios_grandes():
    """Un cambio de más del 25 % mueve el resultado del estudio: hay que decirlo."""
    source = _gui_source()
    cuerpo = source.split('def _apply_catalog')[1].split('\n    def ')[0]
    assert 'variacion_pct' in cuerpo
    assert '25.0' in cuerpo


def test_el_apply_catalog_no_reimplementa_la_correccion():
    source = _gui_source()
    cuerpo = source.split('def _apply_catalog')[1].split('\n    def ')[0]
    assert 'aplicar_correcciones' in cuerpo
    for prohibido in ('aaac_r20_ohm_km', 'replace(', 'r1_ohm_km ='):
        assert prohibido not in cuerpo, f'la GUI no debe calcular {prohibido}'


# ---------------------------------------------------------------------------
# Sistema completo: los 96 alimentadores en una sola red
# ---------------------------------------------------------------------------

def test_los_botones_de_sistema_llaman_a_los_guiones_correctos():
    """Cada botón debe lanzar SU guion; cruzarlos daría un resultado plausible y falso."""
    source = _gui_source()
    grid = source.split('def _build_system_grid')[1].split('\n    def ')[0]
    assert "'build_system_grid.py'" in grid

    anio0 = source.split('def _run_base_scenario')[1].split('\n    def ')[0]
    assert "'base_scenario.py'" in anio0
    assert "'--solo-datos'" not in anio0, 'el año 0 completo NO es solo el informe de datos'

    datos = source.split('def _missing_data')[1].split('\n    def ')[0]
    assert "'--solo-datos'" in datos, 'este botón no debe tocar DigSILENT'


def test_los_guiones_que_lanza_la_interfaz_existen():
    raiz = GUI_SOURCE.resolve().parents[2]
    for guion in ('build_system_grid.py', 'base_scenario.py', 'apply_sed_loads.py',
                  'create_sed_loads.py', 'run_one_study.py'):
        assert (raiz / 'tools' / guion).is_file(), guion


def test_la_entrada_se_lee_de_los_mismos_campos_que_la_conversion():
    """Si la interfaz tuviera una segunda idea de dónde están los ficheros, divergirían."""
    source = _gui_source()
    cuerpo = source.split('def _entradas_para_guion')[1].split('\n    def ')[0]
    for campo in ('self.input_mode', 'self.mdb', 'self.red', 'self.loads',
                  'self.equipment'):
        assert campo in cuerpo, campo


def test_las_operaciones_largas_van_en_subproceso_y_no_bloquean_la_ventana():
    source = _gui_source()
    cuerpo = source.split('def _lanzar_guion')[1].split('\n    def ')[0]
    assert 'threading.Thread' in cuerpo
    assert 'subprocess.run' in cuerpo
    assert 'self._set_busy(True)' in cuerpo


# ---------------------------------------------------------------------------
# Los selectores de fichero, EJECUTADOS
# ---------------------------------------------------------------------------
#
# Las pruebas de arriba leen el código fuente y comprueban que las piezas están
# conectadas. No pueden cazar un NameError, porque el nombre está escrito y parece
# correcto: solo falla al ejecutarse. Pasó exactamente eso — los selectores usaban RED,
# CARGA y EQUIPOS sin que estuvieran importados en gui.py, Tk se tragaba la excepción
# del callback y el campo simplemente no se rellenaba. Desde fuera parecía que la
# ventana ignoraba el fichero elegido.
#
# Por eso estas llaman a los manejadores de verdad, con el diálogo de fichero
# sustituido.


def _escribir_txt(tmp_path, nombre, tablas):
    contenido = ['[GENERAL]', 'DATE=01/01/2026', '']
    for t in tablas:
        contenido += [f'[{t}]', f'FORMAT_{t.replace(" ", "")}=ID,A,B', 'X,1,2', '']
    ruta = tmp_path / nombre
    ruta.write_text('\n'.join(contenido), encoding='utf-8')
    return ruta


@pytest.mark.parametrize('metodo,campo,tablas', [
    ('_browse_red', 'red', ['NODE', 'SECTION', 'SOURCE']),
    ('_browse_loads', 'loads', ['CUSTOMER LOADS']),
    ('_browse_equipment', 'equipment', ['CONDUCTOR', 'LINE']),
])
def test_elegir_un_fichero_correcto_rellena_su_campo(
    app_tk, tmp_path, monkeypatch, metodo, campo, tablas,
):
    """Con el fichero que toca, el campo se rellena sin preguntar nada."""
    from igea_dgs import gui as gui_mod

    ruta = _escribir_txt(tmp_path, 'nombre_cualquiera.txt', tablas)
    monkeypatch.setattr(gui_mod.filedialog, 'askopenfilename', lambda **k: str(ruta))
    getattr(app_tk, metodo)()
    assert getattr(app_tk, campo).get() == str(ruta)


def test_un_fichero_de_otro_tipo_pregunta_antes_de_aceptarlo(
    app_tk, tmp_path, monkeypatch,
):
    """Si se acepta el aviso, el fichero entra igual: el operador manda."""
    from igea_dgs import gui as gui_mod

    catalogo = _escribir_txt(tmp_path, 'equipos.txt', ['CONDUCTOR', 'LINE'])
    monkeypatch.setattr(gui_mod.filedialog, 'askopenfilename', lambda **k: str(catalogo))
    preguntas = []
    monkeypatch.setattr(
        gui_mod.messagebox, 'askyesno',
        lambda titulo, mensaje, **k: preguntas.append(mensaje) or True)
    app_tk._browse_loads()
    assert preguntas, 'debe avisar de que el fichero no encaja con la casilla'
    assert 'BD_Equipo' in preguntas[0]
    assert app_tk.loads.get() == str(catalogo)


def test_si_se_rechaza_el_aviso_el_campo_no_cambia(app_tk, tmp_path, monkeypatch):
    from igea_dgs import gui as gui_mod

    app_tk.loads.set('valor previo')
    catalogo = _escribir_txt(tmp_path, 'equipos.txt', ['CONDUCTOR'])
    monkeypatch.setattr(gui_mod.filedialog, 'askopenfilename', lambda **k: str(catalogo))
    monkeypatch.setattr(gui_mod.messagebox, 'askyesno', lambda *a, **k: False)
    app_tk._browse_loads()
    assert app_tk.loads.get() == 'valor previo'


def test_cancelar_el_dialogo_no_toca_el_campo(app_tk, monkeypatch):
    from igea_dgs import gui as gui_mod

    app_tk.red.set('lo de antes')
    monkeypatch.setattr(gui_mod.filedialog, 'askopenfilename', lambda **k: '')
    app_tk._browse_red()
    assert app_tk.red.get() == 'lo de antes'


def test_las_constantes_de_tipo_estan_importadas_en_la_interfaz():
    """El fallo concreto: se usaban sin importar y saltaba NameError al examinar."""
    from igea_dgs import gui as gui_mod

    for nombre in ('RED', 'CARGA', 'EQUIPOS'):
        assert hasattr(gui_mod, nombre), (
            f'gui.py usa {nombre} en los selectores de fichero pero no lo importa'
        )


# ---------------------------------------------------------------------------
# La ventana tiene que caber en la pantalla
# ---------------------------------------------------------------------------
#
# El formulario creció hasta pasar de 1.200 píxeles de alto: entrada, salida, lista de
# alimentadores, cuatro módulos de cargas, catálogo y sistema. En un portátil normal la
# lista de alimentadores y el botón «Cancelar» quedaban fuera de la pantalla, y lo que
# no se ve no existe: el operador no puede saber que hay más abajo.


def test_el_contenido_es_mas_alto_que_una_pantalla_de_portatil(app_tk):
    """Si algún día deja de serlo, la barra sobra; mientras tanto, hace falta."""
    lienzo = app_tk._lienzo
    lienzo.master.update_idletasks()
    region = lienzo.bbox('all')
    assert region is not None
    alto = region[3] - region[1]
    assert alto > 768, (
        f'el formulario mide {alto} px; si cabe en una pantalla de portátil, '
        'revise si la barra de desplazamiento sigue teniendo sentido'
    )


def test_hay_barra_de_desplazamiento_vertical(app_tk):
    from tkinter import ttk

    lienzo = app_tk._lienzo
    barras = [w for w in lienzo.master.winfo_children()
              if isinstance(w, ttk.Scrollbar) and str(w.cget('orient')) == 'vertical']
    assert barras, 'sin barra vertical, lo que no cabe queda inalcanzable'


def test_todo_el_contenido_queda_alcanzable(app_tk):
    """La región de desplazamiento debe cubrir el formulario entero, no una parte."""
    lienzo = app_tk._lienzo
    lienzo.master.update_idletasks()
    region = lienzo.bbox('all')
    declarada = [float(x) for x in str(lienzo.cget('scrollregion')).split()]
    assert declarada, 'el lienzo no declara región de desplazamiento'
    assert declarada[3] >= region[3] - 1, (
        'la región declarada se queda corta: parte del formulario no se alcanza'
    )


def test_el_minimo_de_ventana_cabe_en_un_portatil(app_tk):
    ancho, alto = app_tk.root.minsize()
    assert alto <= 600, f'un mínimo de {alto} px no cabe en una pantalla de 768'
    assert ancho <= 800


def test_la_ventana_no_arranca_mas_alta_que_la_pantalla(app_tk):
    raiz = app_tk.root
    raiz.update_idletasks()
    alto_ventana = int(raiz.geometry().split('x')[1].split('+')[0])
    assert alto_ventana <= raiz.winfo_screenheight(), (
        'la ventana arranca más alta que la pantalla: parte queda fuera desde el inicio'
    )


def test_el_marco_interior_se_ensancha_con_la_ventana():
    """Sin esto el contenido queda encajado a la izquierda con la ventana ancha."""
    source = _gui_source()
    cuerpo = source.split('def _contenedor_desplazable')[1].split('\n    def ')[0]
    assert 'itemconfigure' in cuerpo
    assert "width=evento.width" in cuerpo


def test_la_rueda_no_se_apropia_del_desplazamiento_de_las_listas():
    """La lista de alimentadores y el Registro tienen su propia barra."""
    source = _gui_source()
    cuerpo = source.split('def _contenedor_desplazable')[1].split('\n    def ')[0]
    assert "bind('<Enter>'" in cuerpo and "bind('<Leave>'" in cuerpo
    assert 'unbind_all' in cuerpo


# ---------------------------------------------------------------------------
# El Registro tiene que poder crecer
# ---------------------------------------------------------------------------
#
# Al meter todo el formulario en un Canvas desplazable, el Registro se quedó con su
# altura mínima y no había forma de agrandarlo: dentro de un Canvas, «expand=True» no
# hace nada, porque el marco interior se ajusta a su contenido en lugar de a la ventana.
# El Registro es donde sale TODO —el inventario, los avisos del catálogo, la salida de
# los guiones de sistema—, así que dejarlo en ocho líneas fijas lo vuelve inservible.
#
# Va en el panel inferior, fuera del lienzo, con el separador arrastrable.


def test_el_registro_esta_fuera_del_area_desplazable(app_tk):
    """Si vuelve a caer dentro del lienzo, deja de poder crecer."""
    from tkinter import Canvas

    padres = []
    w = app_tk.log
    while w is not None and w is not app_tk.root:
        padres.append(w)
        w = w.master
    assert not any(isinstance(x, Canvas) for x in padres), (
        'el Registro está dentro del Canvas: no podrá agrandarse'
    )


def test_hay_un_panel_divisible_con_dos_zonas(app_tk):
    from tkinter import ttk

    assert isinstance(app_tk._panel, ttk.PanedWindow)
    assert len(app_tk._panel.panes()) == 2, 'formulario arriba, Registro abajo'


def _con_ventana_visible(app, ancho=960, alto=800):
    """Muestra la ventana para poder medirla, y la vuelve a ocultar.

    Tk no calcula geometría de una ventana retirada: todo mide 1 px. Y el tamaño del
    Registro es justo lo que hay que comprobar aquí, así que no vale sustituirlo por
    una propiedad estructural.
    """
    raiz = app.root
    raiz.deiconify()
    raiz.geometry(f'{ancho}x{alto}')
    raiz.update()
    raiz.update_idletasks()
    return raiz


def test_el_registro_crece_al_mover_el_separador(app_tk):
    """La prueba que de verdad importa: que se pueda desplegar."""
    raiz = _con_ventana_visible(app_tk)
    try:
        app_tk._panel.sashpos(0, 650)
        raiz.update_idletasks()
        pequeno = app_tk.log.winfo_height()

        app_tk._panel.sashpos(0, 350)
        raiz.update_idletasks()
        grande = app_tk.log.winfo_height()

        assert grande > pequeno * 1.5, (
            f'el Registro pasa de {pequeno} a {grande} px: no está creciendo'
        )
    finally:
        raiz.withdraw()


def test_el_registro_arranca_con_altura_util(app_tk):
    raiz = _con_ventana_visible(app_tk)
    try:
        alto = app_tk.log.winfo_height()
        assert alto > 120, f'{alto} px: con ocho líneas escasas el inventario no se lee'
    finally:
        raiz.withdraw()


def test_el_titulo_dice_como_agrandarlo(app_tk):
    """Un separador arrastrable no se ve; hay que decirlo.

    Se busca el LabelFrame subiendo por los padres: ScrolledText se envuelve a sí
    mismo, así que su `master` directo es un Frame interno suyo, no el marco con título.
    """
    from tkinter import ttk

    w = app_tk.log
    titulo = ''
    while w is not None:
        if isinstance(w, ttk.LabelFrame):
            titulo = str(w.cget('text'))
            break
        w = w.master
    assert titulo, 'el Registro debe estar dentro de un marco con título'
    assert 'separador' in titulo.lower()
