"""Interfaz gráfica para convertir TXT IGEA/CYMDIST → DGS PowerFactory."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import (
    BooleanVar,
    Canvas,
    END,
    LEFT,
    RIGHT,
    StringVar,
    Tk,
    Toplevel,
    W,
    X,
    Y,
    BOTH,
    filedialog,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

from .batch import STAGE_PREFIX
from .dataset import CymdistDataset
# Los tres papeles que puede tener un TXT del export. Se reconocen por el contenido del
# fichero, no por su nombre (ver igea_dgs.identify).
from .identify import CARGA, EQUIPOS, RED
from .inventory import build_dataset_inventory, format_inventory_report, write_inventory
from .naming import feeder_short_name, sort_key_feeder
from .powerfactory_env import (
    DEFAULT_PF_PYTHON, pf_api_version, pf_python_dir, python_for_pf, version_key,
)
from . import __version__


# CRS de ORIGEN: solo sistemas proyectados con unidades en metros.
#
# Las longitudes eléctricas se miden con distancia euclidiana sobre CoordX/CoordY
# y se interpretan como metros. Un CRS geográfico (grados) como EPSG:4326 produce
# longitudes ~1e5 veces menores sin que ninguna validación lo detecte, porque el
# validador compara el DGS contra el mismo modelo que lo generó. El motor lo
# rechaza en geography.assert_metre_source_crs; esta lista no debe reintroducirlo.
# Ver docs/DIAGNOSTICO_BACKEND_FRONTEND_2026-09-22.md (C-01).
CRS_PRESETS = (
    'EPSG:32718',  # UTM 18S (Ica / costa Perú — default NA205)
    'EPSG:32717',  # UTM 17S
    'EPSG:32719',  # UTM 19S
    'EPSG:32716',  # UTM 16S
    'EPSG:32618',  # UTM 18N
    'EPSG:31983',  # SIRGAS 2000 / UTM 23S (ejemplo Brasil)
    'EPSG:5343',   # POSGAR 2007 / Argentina 3
)

STEPS_HINT = (
    'Flujo: 1) Elija la entrada (tres TXT o base .mdb)  ·  2) Cargar / listar  ·  '
    '3) Seleccione uno, varios o todos  ·  4) Convertir a DGS  ·  '
    '5) Cargar DGS en DigSILENT + flujo (+ estudios).'
)

DEFAULT_STATUS = 'Elija la entrada y pulse «Cargar / listar alimentadores».'

# Detección de PowerFactory: compartida con la interfaz web (powerfactory_env).
_DEFAULT_PF_PYTHON = DEFAULT_PF_PYTHON
_version_key = version_key
_pf_python_dir = pf_python_dir
_pf_api_version = pf_api_version
_python_for_pf = python_for_pf


def _powerfactory_acceptance_script() -> Path:
    return _project_root() / 'tools' / 'powerfactory_acceptance.py'


def _default_aliases_path() -> str:
    path = Path(__file__).resolve().parents[2] / 'config' / 'line_type_aliases.json'
    return str(path) if path.is_file() else ''


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _referencia_dir() -> Path:
    return _project_root() / 'referencia'


def _first_existing(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    if not directory.is_dir():
        return None
    for pattern in patterns:
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def _default_referencia_inputs() -> tuple[str, str, str]:
    """Prefill GUI with model TXT from referencia/ when present."""
    ref = _referencia_dir()
    red = _first_existing(ref, ('RED_*.txt', 'RED*.txt'))
    loads = _first_existing(ref, ('CARGA_*.txt', 'CARGA*.txt'))
    equip = _first_existing(ref, ('BD_Equipo*.txt',))
    return (
        str(red) if red else '',
        str(loads) if loads else '',
        str(equip) if equip else '',
    )


def _default_out_dir() -> str:
    return str(Path.cwd() / 'output' / 'gui')


def _legacy_state_path() -> Path:
    """Ruta del antiguo gui_state.json (se elimina para no arrastrar sesiones)."""
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        return Path(base) / 'igea-dgs' / 'gui_state.json'
    return Path.home() / '.igea-dgs' / 'gui_state.json'


class _NewSedDialog:
    """Formulario modal para una sola SED nueva.

    Solo recoge y convierte texto. **No valida nada**: las reglas viven en
    ``loads_create.single_new_load``, que es el mismo camino que recorre la plantilla.
    Si este formulario comprobase por su cuenta, acabaría divergiendo del fichero y
    habría dos definiciones de «fila válida», que es como aparecen los datos que pasan
    por un lado y no por el otro.
    """

    CAMPOS = (
        ('sed_code', 'Código de la SED *', '', 'Por ejemplo SE31045.'),
        ('installed_kva', 'Potencia del transformador (kVA) *', '',
         'La de placa, no la carga.'),
        ('coord_x', 'Coordenada Este (X)', '',
         'En el mismo sistema que el export. Se conecta al nodo más cercano.'),
        ('coord_y', 'Coordenada Norte (Y)', '', ''),
        ('node_id', 'Nodo de conexión', '',
         'Solo si quiere imponerlo; en blanco se deduce del punto.'),
        ('kw', 'Carga activa (kW)', '', 'Deje en blanco si da kVA y FP.'),
        ('kvar', 'Carga reactiva (kvar)', '', ''),
        ('kva', 'Carga aparente (kVA)', '', ''),
        ('fp', 'Factor de potencia', '0.95', ''),
        ('conductor', 'Conductor impuesto', '',
         'En blanco se elige por ampacidad y caída de tensión.'),
    )

    NUMERICOS = ('installed_kva', 'coord_x', 'coord_y', 'kw', 'kvar', 'kva', 'fp')

    def __init__(self, parent: Tk, feeder: str) -> None:
        self.result: dict | None = None
        self.win = Toplevel(parent)
        self.win.title(f'Crear una SED en {feeder}')
        self.win.transient(parent)
        self.win.resizable(False, False)

        marco = ttk.Frame(self.win, padding=12)
        marco.pack(fill=BOTH, expand=True)
        ttk.Label(
            marco,
            text=('Los campos con * son obligatorios. Indique las coordenadas del punto '
                  'o bien el nodo de conexión.'),
            wraplength=520, foreground='#444',
        ).grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 8))

        self.vars: dict[str, StringVar] = {}
        for fila, (clave, etiqueta, inicial, ayuda) in enumerate(self.CAMPOS, start=1):
            ttk.Label(marco, text=etiqueta).grid(row=fila, column=0, sticky=W, pady=2)
            var = StringVar(value=inicial)
            self.vars[clave] = var
            ttk.Entry(marco, textvariable=var, width=26).grid(
                row=fila, column=1, sticky=W, padx=(8, 0), pady=2)
            if ayuda:
                ttk.Label(marco, text=ayuda, foreground='#666', wraplength=300).grid(
                    row=fila, column=2, sticky=W, padx=(8, 0))

        botones = ttk.Frame(marco)
        botones.grid(row=len(self.CAMPOS) + 1, column=0, columnspan=3,
                     sticky='e', pady=(12, 0))
        ttk.Button(botones, text='Cancelar', command=self.win.destroy).pack(side=RIGHT)
        ttk.Button(botones, text='Crear', command=self._aceptar).pack(
            side=RIGHT, padx=(0, 8))

        self.win.bind('<Return>', lambda _e: self._aceptar())
        self.win.bind('<Escape>', lambda _e: self.win.destroy())
        self.win.grab_set()
        parent.wait_window(self.win)

    def _aceptar(self) -> None:
        datos: dict = {}
        malos: list[str] = []
        for clave, etiqueta, _inicial, _ayuda in self.CAMPOS:
            crudo = self.vars[clave].get().strip()
            if clave not in self.NUMERICOS:
                datos[clave] = crudo
                continue
            if not crudo:
                datos[clave] = None if clave in ('coord_x', 'coord_y', 'kw', 'kvar',
                                                 'kva', 'fp') else 0.0
                continue
            try:
                datos[clave] = float(crudo.replace(',', '.'))
            except ValueError:
                malos.append(f'«{etiqueta.rstrip(" *")}»: {crudo!r} no es un número.')
        if malos:
            messagebox.showerror('Dato no numérico', '\n'.join(malos), parent=self.win)
            return
        if datos.get('installed_kva') is None:
            datos['installed_kva'] = 0.0
        self.result = datos
        self.win.destroy()


class ConverterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f'Conversor IGEA/CYMDIST → DGS  v{__version__}')
        # La ventana ya no tiene que caber entera: hay barra de desplazamiento. El
        # mínimo baja para que funcione en un portátil de 768 px de alto, y el tamaño
        # inicial se ajusta a la pantalla en lugar de fijar uno que puede no caber.
        self.root.minsize(780, 480)
        alto = min(900, max(560, self.root.winfo_screenheight() - 120))
        self.root.geometry(f'960x{alto}')

        # Dos alternativas de entrada: 'txt' (tres ficheros) o 'mdb' (base Access).
        self.input_mode = StringVar(value='txt')
        self.red = StringVar()
        self.loads = StringVar()
        self.equipment = StringVar()
        self.equipment_extra = StringVar()
        self.mdb = StringVar()
        self.equipment_mdb = StringVar()
        self.study = StringVar()
        self.out_dir = StringVar(value=_default_out_dir())
        self.aliases = StringVar(value=_default_aliases_path())
        self.source_crs = StringVar(value='EPSG:32718')  # UTM 18S — costa Perú / Ica
        self.target_crs = StringVar(value='EPSG:4326')
        self.include_geography = BooleanVar(value=True)
        self.strict = BooleanVar(value=True)
        self.export_xlsx = BooleanVar(value=False)
        self.export_tsv = BooleanVar(value=False)
        self.write_preview = BooleanVar(value=False)
        self.convert_all = BooleanVar(value=False)
        self._dataset: CymdistDataset | None = None
        self._inventory: dict | None = None
        self._busy = False
        self._action_buttons: list[ttk.Button] = []
        self._cancel: threading.Event | None = None
        self._worker: threading.Thread | None = None

        self._build()
        self._discard_legacy_state()
        self._reset_session(full=True, announce=False)
        if not self._restaurar_ajustes():
            # Solo se recurre a los TXT de ejemplo cuando no hay nada recordado: si el
            # operador ya trabajó con una entrega, esa manda sobre los de referencia/.
            red0, loads0, equip0 = _default_referencia_inputs()
            if red0:
                self.red.set(red0)
            if loads0:
                self.loads.set(loads0)
            if equip0:
                self.equipment.set(equip0)
            if red0 or loads0 or equip0:
                self._refresh_input_status()
                self._append_log('TXT modelo precargados desde carpeta referencia/.')
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ------------------------------------------------------------------
    # Memoria entre sesiones
    # ------------------------------------------------------------------

    def _campos_persistentes(self) -> dict:
        """Lo que se recuerda entre sesiones. Ver igea_dgs.settings."""
        from . import settings

        valores: dict = {}
        for campo in settings.CAMPOS_RUTA + settings.CAMPOS_CARPETA + settings.CAMPOS_TEXTO:
            var = getattr(self, campo, None)
            if var is not None:
                valores[campo] = var.get()
        for campo in settings.CAMPOS_BOOL:
            var = getattr(self, campo, None)
            if var is not None:
                valores[campo] = bool(var.get())
        return valores

    def _guardar_ajustes(self) -> None:
        """Guarda la selección actual. Silencioso: no debe estorbar el trabajo."""
        from . import settings

        try:
            settings.guardar(self._campos_persistentes())
        except Exception:  # noqa: BLE001 - recordar es una comodidad, no el trabajo
            pass

    def _restaurar_ajustes(self) -> bool:
        """Recupera lo de la última sesión. Devuelve si había algo que recuperar.

        Una ruta que ya no existe no se restaura —lo filtra ``settings.cargar``— pero
        sí se dice, porque que desaparezca un fichero es normal cuando se mueve la
        carpeta de la entrega, y el operador debe enterarse por un mensaje y no porque
        el campo aparezca vacío sin explicación.
        """
        from . import settings

        guardado = settings.cargar()
        perdidas = settings.olvidadas(settings.leer_crudo())
        if not guardado and not perdidas:
            return False

        for campo, valor in guardado.items():
            var = getattr(self, campo, None)
            if var is None:
                continue
            try:
                var.set(valor)
            except Exception:  # noqa: BLE001
                continue

        if perdidas:
            self._append_log(
                'Estos ficheros de la sesión anterior ya no están y se dejan vacíos:\n'
                + '\n'.join(f'  · {p}' for p in perdidas)
            )
        recuperados = [c for c in settings.CAMPOS_RUTA if c in guardado]
        if recuperados:
            self._append_log(
                f'Recuperada la selección de la última sesión ({len(recuperados)} '
                f'fichero(s)). Elija otros con «Examinar…» y se recordarán esos.'
            )
        self._refresh_input_status()
        return bool(guardado)

    def _contenedor_desplazable(self) -> 'ttk.Frame':
        """Marco con barra de desplazamiento vertical, para que la ventana quepa.

        La ventana creció hasta pasar de 1.300 píxeles de alto: con la lista de
        alimentadores, los cuatro módulos de cargas, el catálogo y el sistema, en un
        portátil normal quedaban fuera de la pantalla la lista de alimentadores y el
        botón «Cancelar». Y lo que no se ve no existe: el operador no puede saber que
        hay más abajo.

        Se envuelve todo en un ``Canvas`` porque Tk no desplaza un ``Frame`` por sí
        solo. El marco interior se ensancha con la ventana —si no, el contenido
        quedaría encajado a la izquierda— y la rueda del ratón se atiende solo mientras
        el puntero está encima, para no robarle el desplazamiento a la lista de
        alimentadores ni al Registro, que tienen el suyo.
        """
        # Panel divisible: el formulario arriba y el Registro abajo, con el separador
        # arrastrable. El Registro NO puede ir dentro del área desplazable: dentro de un
        # Canvas, `expand=True` no hace nada —el marco interior se ajusta a su
        # contenido—, así que la caja de texto se quedaba con su altura mínima y no
        # había forma de agrandarla. Fuera del lienzo recupera su comportamiento y
        # además se puede repartir el espacio a gusto.
        self._panel = ttk.PanedWindow(self.root, orient='vertical')
        self._panel.pack(fill=BOTH, expand=True)

        contenedor = ttk.Frame(self._panel)
        self._panel.add(contenedor, weight=4)

        lienzo = Canvas(contenedor, highlightthickness=0)
        barra = ttk.Scrollbar(contenedor, orient='vertical', command=lienzo.yview)
        interior = ttk.Frame(lienzo, padding=12)

        ventana = lienzo.create_window((0, 0), window=interior, anchor='nw')
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side=LEFT, fill=BOTH, expand=True)
        barra.pack(side=RIGHT, fill=Y)

        def _al_cambiar_contenido(_evento=None) -> None:
            lienzo.configure(scrollregion=lienzo.bbox('all'))

        def _al_cambiar_ventana(evento) -> None:
            lienzo.itemconfigure(ventana, width=evento.width)

        interior.bind('<Configure>', _al_cambiar_contenido)
        lienzo.bind('<Configure>', _al_cambiar_ventana)

        def _rueda(evento) -> None:
            # Si todo cabe, no hay nada que desplazar y moverlo despistaría.
            region = lienzo.bbox('all')
            if not region or region[3] - region[1] <= lienzo.winfo_height():
                return
            lienzo.yview_scroll(-1 if evento.delta > 0 else 1, 'units')

        def _entrar(_e=None) -> None:
            lienzo.bind_all('<MouseWheel>', _rueda)

        def _salir(_e=None) -> None:
            lienzo.unbind_all('<MouseWheel>')

        lienzo.bind('<Enter>', _entrar)
        lienzo.bind('<Leave>', _salir)
        self._lienzo = lienzo
        return interior

    def _build(self) -> None:
        pad = {'padx': 10, 'pady': 4}
        frm = self._contenedor_desplazable()

        ttk.Label(frm, text=STEPS_HINT, wraplength=860).pack(anchor=W, padx=10, pady=(0, 6))

        files = ttk.LabelFrame(frm, text='Paso 1 — Entrada de datos (elija una alternativa)', padding=10)
        files.pack(fill=X, **pad)

        mode = ttk.Frame(files)
        mode.pack(fill=X, pady=(0, 6))
        ttk.Radiobutton(
            mode, text='Alternativa 1 — Tres ficheros TXT exportados de IGEA/CYMDIST',
            variable=self.input_mode, value='txt', command=self._on_input_mode_change,
        ).pack(anchor=W)
        ttk.Radiobutton(
            mode, text='Alternativa 2 — Base de datos Access de CYMDIST (.mdb)',
            variable=self.input_mode, value='mdb', command=self._on_input_mode_change,
        ).pack(anchor=W)

        self.txt_frame = ttk.Frame(files)
        self.txt_frame.pack(fill=X)
        # Se describe el CONTENIDO, no un nombre: los TXT de la distribuidora no
        # siguen ninguna convención y el nombre cambia de una entrega a otra. Lo
        # que se comprueba al elegirlos son las tablas que traen dentro.
        self._file_row(self.txt_frame, 'RED — topología (nodos, tramos, fuentes)',
                       self.red, self._browse_red)
        self._file_row(self.txt_frame, 'CARGA — demanda por cliente',
                       self.loads, self._browse_loads)
        self._file_row(self.txt_frame, 'EQUIPOS — catálogo de conductores y cables',
                       self.equipment, self._browse_equipment)
        # Cuando la entrega trae un catálogo incompleto —pasó: 9 tipos frente a los
        # 43 que usaba la red— sin esto el 100 % de los tramos toma la impedancia
        # de DEFAULT y el modelo converge igual, sin que nada lo delate.
        self._file_row(self.txt_frame,
                       'EQUIPOS complementario (opcional, si el anterior no cubre)',
                       self.equipment_extra, self._browse_equipment_extra)

        self.mdb_frame = ttk.Frame(files)
        self._file_row(self.mdb_frame, 'Base de red (.mdb)', self.mdb, self._browse_mdb)
        self._file_row(self.mdb_frame, 'Base de equipos (.mdb, si está aparte)', self.equipment_mdb, self._browse_equipment_mdb)
        self._file_row(self.mdb_frame, 'Estudio o proyecto (.zxst, opcional)', self.study, self._browse_study)
        ttk.Label(
            self.mdb_frame,
            text=(
                'Requiere Windows con el driver «Microsoft Access Driver» y pyodbc '
                '(pip install "igea-dgs[access]"). El estudio, si se indica, limita la '
                'conversión a sus alimentadores.'
            ),
            foreground='#555', wraplength=840,
        ).pack(anchor=W, pady=(2, 0))

        self.files_ready = StringVar(value='Faltan archivos por seleccionar.')
        ttk.Label(files, textvariable=self.files_ready, foreground='#335').pack(anchor=W, pady=(6, 0))

        opts = ttk.LabelFrame(frm, text='Salida y opciones', padding=10)
        opts.pack(fill=X, **pad)
        self._file_row(opts, 'Carpeta de salida', self.out_dir, self._browse_out, directory=True)
        self._file_row(opts, 'Aliases de tipos (JSON, opcional)', self.aliases, self._browse_aliases)

        crs = ttk.Frame(opts)
        crs.pack(fill=X, pady=4)
        ttk.Label(crs, text='CRS origen (el de su empresa/región):').pack(side=LEFT)
        # Editable a propósito: cualquier EPSG proyectado en metros vale, no solo los
        # presets. Las unidades las verifica el motor antes de convertir
        # (geography.assert_metre_source_crs), no este widget.
        ttk.Combobox(crs, textvariable=self.source_crs, values=CRS_PRESETS, width=16).pack(side=LEFT, padx=6)
        ttk.Label(crs, text='CRS destino GPS:').pack(side=LEFT, padx=(12, 0))
        ttk.Combobox(crs, textvariable=self.target_crs, values=('EPSG:4326',), width=16).pack(side=LEFT, padx=6)
        ttk.Label(
            opts,
            text=(
                'Escriba cualquier código EPSG si no está en la lista. No está limitado a una '
                'empresa o zona. Debe ser un CRS proyectado en metros: uno en grados '
                '(p. ej. EPSG:4326) falsearía las longitudes y se rechaza al convertir.'
            ),
            foreground='#555',
        ).pack(anchor=W, pady=(2, 0))

        flags = ttk.Frame(opts)
        flags.pack(fill=X, pady=4)
        ttk.Checkbutton(flags, text='Georreferenciación (GPS + diagrama)', variable=self.include_geography).pack(side=LEFT)
        ttk.Checkbutton(flags, text='Modo estricto (topología; tipos se auto-resuelven)', variable=self.strict).pack(side=LEFT, padx=16)
        ttk.Checkbutton(
            flags,
            text='Convertir TODOS los alimentadores cargados',
            variable=self.convert_all,
            command=self._toggle_all,
        ).pack(side=LEFT)

        extras = ttk.Frame(opts)
        extras.pack(fill=X, pady=2)
        ttk.Checkbutton(
            extras,
            text='Vista previa mapa HTML (leafmap/Leaflet)',
            variable=self.write_preview,
        ).pack(side=LEFT)
        ttk.Checkbutton(extras, text='Exportar Excel (.xlsx)', variable=self.export_xlsx).pack(side=LEFT, padx=16)
        ttk.Checkbutton(extras, text='Exportar TSV por tabla', variable=self.export_tsv).pack(side=LEFT)

        feeders = ttk.LabelFrame(frm, text='Paso 2–4 — Alimentadores y conversión a DGS', padding=10)
        feeders.pack(fill=BOTH, expand=True, **pad)
        btns = ttk.Frame(feeders)
        btns.pack(fill=X)
        self.load_btn = ttk.Button(btns, text='Cargar / listar alimentadores', command=self._load_feeders)
        self.load_btn.pack(side=LEFT)
        self.select_all_btn = ttk.Button(btns, text='Seleccionar todos', command=self._select_all_feeders)
        self.select_all_btn.pack(side=LEFT, padx=6)
        self.clear_btn = ttk.Button(btns, text='Limpiar selección', command=self._clear_feeders)
        self.clear_btn.pack(side=LEFT)
        self._action_buttons.extend([self.load_btn, self.select_all_btn, self.clear_btn])

        # Paso 4 — botones de conversión siempre visibles (arriba de la lista)
        convert_btns = ttk.Frame(feeders)
        convert_btns.pack(fill=X, pady=(8, 0))
        self.convert_one_btn = ttk.Button(
            convert_btns,
            text='Convertir 1 (individual)',
            command=self._start_convert_one,
        )
        self.convert_one_btn.pack(side=LEFT, padx=(0, 6), ipady=3)
        self.convert_selected_btn = ttk.Button(
            convert_btns,
            text='Convertir seleccionados → DGS',
            command=self._start_convert_selected,
        )
        self.convert_selected_btn.pack(side=LEFT, padx=(0, 6), ipady=3)
        self.convert_all_btn = ttk.Button(
            convert_btns,
            text='Convertir TODOS → DGS',
            command=self._start_convert_all,
        )
        self.convert_all_btn.pack(side=LEFT, padx=(0, 6), ipady=3)
        self.open_out_btn = ttk.Button(convert_btns, text='Abrir carpeta de salida', command=self._open_out)
        self.open_out_btn.pack(side=LEFT)
        self.pf_flow_btn = ttk.Button(
            convert_btns,
            text='Cargar DGS en DigSILENT + flujo',
            command=self._start_powerfactory_flow,
        )
        self.pf_flow_btn.pack(side=LEFT, padx=(12, 0), ipady=3)
        # Cancelar es el único botón que se habilita *durante* el trabajo: por eso no
        # entra en _action_buttons, que se deshabilitan al ocupar la interfaz.
        self.cancel_btn = ttk.Button(
            convert_btns, text='Cancelar', command=self._request_cancel, state='disabled',
        )
        self.cancel_btn.pack(side=LEFT, padx=(12, 0), ipady=3)
        self._action_buttons.extend([
            self.convert_one_btn,
            self.convert_selected_btn,
            self.convert_all_btn,
            self.open_out_btn,
            self.pf_flow_btn,
        ])

        # Actualización masiva de cargas de SED por plantilla Excel/CSV.
        loads_row = ttk.Frame(feeders)
        loads_row.pack(fill=X, pady=(8, 0))
        ttk.Label(loads_row, text='Cargas de SED:').pack(side=LEFT)
        self.template_btn = ttk.Button(
            loads_row, text='1) Descargar plantilla', command=self._download_load_template,
        )
        self.template_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.apply_loads_btn = ttk.Button(
            loads_row, text='2) Cargar fichero y actualizar', command=self._apply_load_template,
        )
        self.apply_loads_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        ttk.Label(
            loads_row,
            text='(seleccione UN alimentador ya convertido)',
            foreground='#555',
        ).pack(side=LEFT, padx=(8, 0))
        self._action_buttons.extend([self.template_btn, self.apply_loads_btn])

        # Creación de SED nuevas. Es el mismo problema con una fila o con N, así que
        # el formulario y la plantilla van juntos y comparten validación.
        create_row = ttk.Frame(feeders)
        create_row.pack(fill=X, pady=(4, 0))
        ttk.Label(create_row, text='SED nuevas:  ').pack(side=LEFT)
        self.create_template_btn = ttk.Button(
            create_row, text='3) Descargar plantilla de creación',
            command=self._download_create_template,
        )
        self.create_template_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.create_apply_btn = ttk.Button(
            create_row, text='4) Cargar fichero y crear',
            command=self._apply_create_template,
        )
        self.create_apply_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.create_one_btn = ttk.Button(
            create_row, text='5) Crear una SED…', command=self._create_single_load,
        )
        self.create_one_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self._action_buttons.extend([
            self.create_template_btn, self.create_apply_btn, self.create_one_btn,
        ])
        ttk.Label(
            feeders,
            text=(
                'Las SED nuevas se sitúan por coordenadas: el punto se conecta al nodo '
                'más cercano con una derivación aérea, y la sección se elige por '
                'ampacidad y caída de tensión.'
            ),
            foreground='#555', wraplength=860,
        ).pack(anchor=W, pady=(2, 0))

        # Catálogo de parámetros eléctricos (carpeta input/).
        cat_row = ttk.Frame(feeders)
        cat_row.pack(fill=X, pady=(6, 0))
        ttk.Label(cat_row, text='Parámetros:  ').pack(side=LEFT)
        self.catalog_build_btn = ttk.Button(
            cat_row, text='Generar catálogo y auditar',
            command=self._build_catalog,
        )
        self.catalog_build_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.catalog_apply_btn = ttk.Button(
            cat_row, text='Aplicar catálogo corregido',
            command=self._apply_catalog,
        )
        self.catalog_apply_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        ttk.Label(
            cat_row, text='(compara el modelo con las fichas de fabricante)',
            foreground='#555',
        ).pack(side=LEFT, padx=(8, 0))
        self._action_buttons.extend([self.catalog_build_btn, self.catalog_apply_btn])

        # Sistema completo: los 96 alimentadores en UNA sola red. Es lo que hace
        # posible preguntar si un alimentador puede respaldar a otro o dónde conviene
        # abrir, porque el respaldo y la reconfiguración ocurren ENTRE alimentadores.
        sistema_row = ttk.Frame(feeders)
        sistema_row.pack(fill=X, pady=(6, 0))
        ttk.Label(sistema_row, text='Sistema:     ').pack(side=LEFT)
        self.grid_btn = ttk.Button(
            sistema_row, text='Convertir TODO a una sola grid',
            command=self._build_system_grid,
        )
        self.grid_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.anio0_btn = ttk.Button(
            sistema_row, text='Escenario base año 0 + diagnóstico',
            command=self._run_base_scenario,
        )
        self.anio0_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self.datos_btn = ttk.Button(
            sistema_row, text='¿Qué datos faltan?', command=self._missing_data,
        )
        self.datos_btn.pack(side=LEFT, padx=(8, 0), ipady=2)
        self._action_buttons.extend([self.grid_btn, self.anio0_btn, self.datos_btn])
        ttk.Label(
            feeders,
            text=(
                'La red unida conserva la tensión y la fuente de cada alimentador, y '
                'pone los enlaces entre ellos como interruptores normalmente abiertos. '
                '«¿Qué datos faltan?» no toca DigSILENT y tarda segundos.'
            ),
            foreground='#555', wraplength=860,
        ).pack(anchor=W, pady=(2, 0))

        self.status = StringVar(value=DEFAULT_STATUS)
        ttk.Label(feeders, textvariable=self.status, foreground='#335').pack(anchor=W, pady=(6, 0))
        ttk.Label(
            feeders,
            text=(
                'Selección: clic = uno · Ctrl+clic = varios · Mayús+clic = rango · '
                '«Seleccionar todos» = marcar filas. Luego use los botones de conversión.'
            ),
            foreground='#444',
            wraplength=860,
        ).pack(anchor=W, pady=(2, 0))

        list_frm = ttk.Frame(feeders)
        list_frm.pack(fill=BOTH, expand=True, pady=6)
        scroll = ttk.Scrollbar(list_frm)
        scroll.pack(side=RIGHT, fill=Y)
        self.feeder_list = ttk.Treeview(
            list_frm,
            columns=('name', 'network', 'kv', 'sections', 'loads', 'switches', 'status'),
            show='headings',
            selectmode='extended',
            yscrollcommand=scroll.set,
            height=8,
        )
        scroll.config(command=self.feeder_list.yview)
        self.feeder_list.heading('name', text='Alimentador')
        self.feeder_list.heading('network', text='NetworkID')
        self.feeder_list.heading('kv', text='kV')
        self.feeder_list.heading('sections', text='Tramos')
        self.feeder_list.heading('loads', text='Cargas')
        self.feeder_list.heading('switches', text='SW')
        self.feeder_list.heading('status', text='Estado')
        self.feeder_list.column('name', width=80, anchor=W)
        self.feeder_list.column('network', width=210, anchor=W)
        self.feeder_list.column('kv', width=55, anchor=W)
        self.feeder_list.column('sections', width=65, anchor=W)
        self.feeder_list.column('loads', width=65, anchor=W)
        self.feeder_list.column('switches', width=50, anchor=W)
        self.feeder_list.column('status', width=90, anchor=W)
        self.feeder_list.pack(side=LEFT, fill=BOTH, expand=True)
        self.feeder_list.bind('<<TreeviewSelect>>', self._on_feeder_select)
        self.feeder_list.bind('<Double-1>', self._on_feeder_double_click)
        self._refresh_convert_buttons()

        progress_frm = ttk.Frame(frm)
        progress_frm.pack(fill=X, **pad)
        self.progress = ttk.Progressbar(progress_frm, mode='determinate')
        self.progress.pack(fill=X)

        # El Registro va en el panel inferior, fuera del área desplazable, para que
        # pueda crecer y para poder repartir el espacio arrastrando el separador.
        abajo = ttk.Frame(self._panel)
        self._panel.add(abajo, weight=1)
        log_frm = ttk.LabelFrame(
            abajo, text='Registro  (arrastre el separador de arriba para agrandarlo)',
            padding=6)
        log_frm.pack(fill=BOTH, expand=True, padx=10, pady=(4, 2))
        self.log = ScrolledText(log_frm, height=8, wrap='none', state='disabled')
        self.log.pack(fill=BOTH, expand=True)

        note = (
            'Nota: BD_Equipo es el catálogo TXT de equipos CYMDIST (no una base SQL). '
            'Los tres archivos deben ser la exportación IGEA/CYMDIST del mismo lote.'
        )
        ttk.Label(abajo, text=note, foreground='#444').pack(anchor=W, padx=10, pady=(0, 4))

    def _file_row(self, parent, label, var, command, directory: bool = False) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=2)
        ttk.Label(row, text=label, width=36).pack(side=LEFT)
        ttk.Entry(row, textvariable=var).pack(side=LEFT, fill=X, expand=True, padx=6)
        ttk.Button(row, text='Examinar…', command=command).pack(side=LEFT)

    def _on_input_mode_change(self) -> None:
        """Muestra solo el panel de la alternativa elegida."""
        if self.input_mode.get() == 'mdb':
            self.txt_frame.pack_forget()
            self.mdb_frame.pack(fill=X)
        else:
            self.mdb_frame.pack_forget()
            self.txt_frame.pack(fill=X)
        self._invalidate_loaded_data()
        self._refresh_input_status(announce=False)

    def _input_paths_ready(self) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if self.input_mode.get() == 'mdb':
            # El estudio y la base de equipos son opcionales; la base de red no.
            for label, var in (('Base de red (.mdb)', self.mdb),):
                if not var.get().strip() or not Path(var.get().strip()).is_file():
                    missing.append(label)
            for label, var in (
                ('Base de equipos', self.equipment_mdb),
                ('Estudio', self.study),
            ):
                value = var.get().strip()
                if value and not Path(value).is_file():
                    missing.append(f'{label} (ruta no válida)')
            return (not missing, missing)
        for label, var in (
            ('RED', self.red),
            ('CARGA', self.loads),
            ('BD_Equipo', self.equipment),
        ):
            p = Path(var.get().strip())
            if not var.get().strip() or not p.is_file():
                missing.append(label)
        return (not missing, missing)

    def _load_input_dataset(self) -> CymdistDataset:
        """Lee la entrada elegida. Ambas vías devuelven el mismo tipo de dataset."""
        if self.input_mode.get() == 'mdb':
            from .access import read_access_dataset

            networks = None
            study = self.study.get().strip()
            if study:
                from .study import study_networks

                networks = study_networks(study)
            return read_access_dataset(
                self.mdb.get().strip(),
                equipment_db=self.equipment_mdb.get().strip() or None,
                networks=networks,
            )
        dataset = CymdistDataset.from_files(
            self.red.get().strip(), self.loads.get().strip(), self.equipment.get().strip(),
        )
        # Catálogo incompleto: se completa si se indicó otro, y en todo caso se dice
        # cuánta red quedaría con la impedancia de DEFAULT. Un catálogo que no
        # corresponde con la red produce un modelo que converge igual, así que si no se
        # avisa aquí no se avisa en ninguna parte.
        from .catalog_merge import completar, diagnosticar

        extra = self.equipment_extra.get().strip()
        informe = (completar(dataset, [extra]) if extra else diagnosticar(dataset))
        if extra or informe.cobertura_final < 1.0:
            self._append_log('--- Catálogo de conductores ---')
            self._append_log(informe.texto())
        if informe.cobertura_final < 0.5:
            messagebox.showwarning(
                'El catálogo no cubre esta red',
                f'Solo el {informe.cobertura_final * 100:.0f} % de los tipos de línea '
                f'que usa la red está en el catálogo cargado.\n\n'
                'El resto tomará la impedancia de DEFAULT: el modelo convertirá y '
                'convergerá igual, pero las pérdidas y las caídas de tensión no '
                'significarán nada, y nada en el resultado lo delatará.\n\n'
                'Indique en «EQUIPOS complementario» el BD_Equipo de otra entrega.',
            )
        return dataset

    def _refresh_input_status(self, *, announce: bool = True, just_set: str | None = None) -> None:
        ready, missing = self._input_paths_ready()
        if just_set:
            name = Path(just_set).name
            self._append_log(f'Archivo asignado: {name}')
        if ready:
            self.files_ready.set(
                'Base de datos lista. Pulse «Cargar / listar alimentadores».'
                if self.input_mode.get() == 'mdb'
                else 'Los tres TXT están listos. Pulse «Cargar / listar alimentadores».'
            )
            if announce:
                self.status.set('TXT listos — pulse «Cargar / listar alimentadores».')
        else:
            self.files_ready.set(f'Pendientes: {", ".join(missing)}.')
            if announce and just_set:
                self.status.set(f'Archivo cargado. Aún faltan: {", ".join(missing)}.')

    def _confirmar_tipo(self, path: str, esperado: str) -> bool:
        """Avisa si el fichero elegido no es lo que esa casilla espera.

        El nombre del fichero no dice nada: los TXT de la distribuidora no siguen
        ninguna convención y cambian de una entrega a otra. Lo único que distingue un
        RED de un CARGA o de un catálogo son las tablas que declara dentro, así que se
        miran al elegirlo y no al convertir, cuando ya se perdió tiempo.

        Se avisa pero se deja continuar: si mañana el export trae una tabla nueva, más
        vale que el operador pueda seguir que bloquearle el trabajo por una heurística.
        """
        from .identify import comprobar_ranura

        problema = comprobar_ranura(path, esperado)
        if not problema:
            return True
        return messagebox.askyesno(
            'El fichero no encaja con la casilla',
            problema + '\n\n¿Usarlo de todos modos?',
            icon='warning',
        )

    def _browse_red(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar el TXT de RED — topología',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            if not self._confirmar_tipo(path, RED):
                return
            self.red.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_loads(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar el TXT de CARGA — demanda',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            if not self._confirmar_tipo(path, CARGA):
                return
            self.loads.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_equipment_extra(self) -> None:
        """Catálogo de otra entrega, para rellenar los códigos que falten.

        No se comprueba con _confirmar_tipo por la misma razón que el principal, pero
        sí se avisa si no parece un catálogo: es el error fácil de cometer aquí.
        """
        path = filedialog.askopenfilename(
            title='BD_Equipo de otra entrega, para completar el catálogo',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            if not self._confirmar_tipo(path, EQUIPOS):
                return
            self.equipment_extra.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_equipment(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar el TXT de EQUIPOS — catálogo',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            if not self._confirmar_tipo(path, EQUIPOS):
                return
            self.equipment.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_mdb(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar base de red CYMDIST (.mdb)',
            filetypes=[('Base de datos Access', '*.mdb;*.accdb'), ('Todos', '*.*')],
        )
        if path:
            self.mdb.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_equipment_mdb(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar base de equipos CYMDIST (.mdb)',
            filetypes=[('Base de datos Access', '*.mdb;*.accdb'), ('Todos', '*.*')],
        )
        if path:
            self.equipment_mdb.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_study(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar estudio o proyecto CYMDIST (opcional)',
            filetypes=[('Estudio CYMDIST', '*.zxst;*.xst'), ('Todos', '*.*')],
        )
        if path:
            self.study.set(path)
            self._guardar_ajustes()
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title='Carpeta de salida DGS')
        if path:
            self.out_dir.set(path)
            self._guardar_ajustes()
            self._append_log(f'Carpeta de salida: {path}')
            self.status.set(f'Salida: {path}')

    def _browse_aliases(self) -> None:
        path = filedialog.askopenfilename(
            title='JSON de aliases de tipos de línea',
            filetypes=[('JSON', '*.json'), ('Todos', '*.*')],
        )
        if path:
            self.aliases.set(path)
            self._guardar_ajustes()
            self._append_log(f'Aliases: {Path(path).name}')

    def _toggle_all(self) -> None:
        all_mode = self.convert_all.get()
        self.feeder_list.configure(selectmode='none' if all_mode else 'extended')
        if all_mode:
            self.feeder_list.selection_remove(*self.feeder_list.selection())
            n = len(self.feeder_list.get_children())
            msg = (
                f'Modo TODOS activo: pulse «Convertir TODOS → DGS» ({n} alimentadores).'
                if n
                else 'Modo TODOS activo: cargue alimentadores y luego convierta.'
            )
            self.status.set(msg)
            self._append_log(msg)
        else:
            self.status.set('Modo selección: elija uno o varios alimentadores en la lista.')
            self._append_log('Modo selección manual (uno o varios).')
        self._refresh_convert_buttons()

    def _refresh_convert_buttons(self) -> None:
        """Actualiza etiquetas/estado de los botones de conversión según la selección."""
        n = len(self.feeder_list.selection())
        total = len(self.feeder_list.get_children())
        if hasattr(self, 'convert_one_btn'):
            if n == 1:
                name = self.feeder_list.item(self.feeder_list.selection()[0], 'values')[0]
                self.convert_one_btn.configure(text=f'Convertir 1 → DGS ({name})')
            else:
                self.convert_one_btn.configure(text='Convertir 1 (individual)')
        if hasattr(self, 'convert_selected_btn'):
            if n >= 2:
                self.convert_selected_btn.configure(text=f'Convertir {n} seleccionados → DGS')
            elif n == 1:
                self.convert_selected_btn.configure(text='Convertir seleccionados → DGS (1)')
            else:
                self.convert_selected_btn.configure(text='Convertir seleccionados → DGS')
        if hasattr(self, 'convert_all_btn'):
            if total:
                self.convert_all_btn.configure(text=f'Convertir TODOS → DGS ({total})')
            else:
                self.convert_all_btn.configure(text='Convertir TODOS → DGS')

    def _on_feeder_select(self, _event=None) -> None:
        if self.convert_all.get() or self._busy:
            return
        n = len(self.feeder_list.selection())
        if n == 0:
            self.status.set('Sin selección — elija 1 o varios, o pulse «Convertir TODOS».')
        elif n == 1:
            name = self.feeder_list.item(self.feeder_list.selection()[0], 'values')[0]
            self.status.set(f'Seleccionado 1: {name} — pulse «Convertir 1» o «Convertir seleccionados».')
        else:
            self.status.set(f'Seleccionados {n} — pulse «Convertir {n} seleccionados → DGS».')
        self._refresh_convert_buttons()

    def _on_feeder_double_click(self, _event=None) -> None:
        """Doble clic en una fila: convierte ese alimentador (individual)."""
        if self._busy or self.convert_all.get():
            return
        if not self.feeder_list.selection():
            return
        self._start_convert_one()

    def _start_convert_one(self) -> None:
        """Convierte exactamente el alimentador seleccionado (debe ser 1)."""
        selected = list(self.feeder_list.selection())
        if len(selected) != 1:
            messagebox.showwarning(
                'Selección individual',
                'Seleccione exactamente UN alimentador en la lista\n'
                '(clic simple) y pulse «Convertir 1».\n\n'
                'Para varios use «Convertir seleccionados».',
            )
            return
        self.convert_all.set(False)
        self.feeder_list.configure(selectmode='extended')
        self._start_convert(force_all=False)

    def _start_convert_selected(self) -> None:
        """Convierte todos los alimentadores actualmente seleccionados (1, 2, 3, 4…)."""
        selected = list(self.feeder_list.selection())
        if not selected:
            messagebox.showwarning(
                'Sin selección',
                'Seleccione uno o varios alimentadores (Ctrl+clic / Mayús+clic)\n'
                'o use «Seleccionar todos», luego pulse este botón.',
            )
            return
        self.convert_all.set(False)
        self.feeder_list.configure(selectmode='extended')
        self._start_convert(force_all=False)

    def _start_convert_all(self) -> None:
        """Convierte todos los alimentadores cargados en la lista."""
        if not self.feeder_list.get_children():
            messagebox.showwarning('Sin datos', 'Primero pulse «Cargar / listar alimentadores».')
            return
        self.convert_all.set(True)
        self.feeder_list.configure(selectmode='none')
        self.feeder_list.selection_remove(*self.feeder_list.selection())
        self._start_convert(force_all=True)

    def _clear_log(self) -> None:
        self.log.configure(state='normal')
        self.log.delete('1.0', END)
        self.log.configure(state='disabled')

    def _clear_feeder_list(self) -> None:
        for item in self.feeder_list.get_children():
            self.feeder_list.delete(item)

    def _invalidate_loaded_data(self) -> None:
        """Si cambian los TXT, la lista/carga anterior ya no vale."""
        self._dataset = None
        self._clear_feeder_list()
        self.convert_all.set(False)
        self.feeder_list.configure(selectmode='extended')
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0)

    def _discard_legacy_state(self) -> None:
        """Elimina el estado guardado de versiones anteriores (sin reutilizar rutas)."""
        path = _legacy_state_path()
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def _reset_session(self, *, full: bool, announce: bool = True) -> None:
        """Deja la UI en cero para una ejecución nueva.

        full=True: también limpia rutas TXT, salida, CRS y flags (cierre / arranque).
        full=False: limpia solo runtime (lista, log, progreso) al volver a cargar.
        """
        self._dataset = None
        self._inventory = None
        self._busy = False
        self._clear_feeder_list()
        self._clear_log()
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0, maximum=100)
        self.convert_all.set(False)
        self.feeder_list.configure(selectmode='extended')

        if full:
            self.red.set('')
            self.loads.set('')
            self.equipment.set('')
            self.out_dir.set(_default_out_dir())
            self.aliases.set(_default_aliases_path())
            self.source_crs.set('EPSG:32718')
            self.target_crs.set('EPSG:4326')
            self.include_geography.set(True)
            self.strict.set(True)
            self.export_xlsx.set(False)
            self.export_tsv.set(False)
            self.write_preview.set(False)
            self._discard_legacy_state()

        for btn in self._action_buttons:
            btn.configure(state='normal')
        self.status.set(DEFAULT_STATUS)
        self._refresh_input_status(announce=False)
        if announce:
            self._append_log('Sesión restablecida — lista para una nueva ejecución.')

    def _append_log(self, text: str) -> None:
        self.log.configure(state='normal')
        self.log.insert(END, text + '\n')
        self.log.see(END)
        self.log.configure(state='disabled')

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        for btn in self._action_buttons:
            btn.configure(state=state)
        # Cancelar va al revés: solo tiene sentido mientras algo está corriendo.
        self.cancel_btn.configure(state='normal' if busy else 'disabled')
        if not busy:
            self.progress.configure(value=0)

    def _request_cancel(self) -> None:
        """Señala la cancelación; el motor termina el alimentador en curso y para."""
        if not self._busy or self._cancel is None:
            return
        self._cancel.set()
        self.cancel_btn.configure(state='disabled')
        self.status.set('Cancelando… se conserva lo ya convertido.')
        self._append_log(
            'Cancelación solicitada: el alimentador en curso termina y se conserva, '
            'no se empieza ninguno más, y los ya convertidos se conservan.'
        )

    def _require_inputs(self) -> bool:
        ready, missing = self._input_paths_ready()
        if not ready:
            messagebox.showerror('Archivos faltantes', f'Verifique que existan: {", ".join(missing)}')
            return False
        if not self.out_dir.get().strip():
            messagebox.showerror('Salida', 'Indique una carpeta de salida.')
            return False
        aliases = self.aliases.get().strip()
        if aliases and not Path(aliases).is_file():
            messagebox.showerror('Aliases', f'No se encuentra el JSON de aliases:\n{aliases}')
            return False
        return True

    def _load_feeders(self) -> None:
        if self._busy:
            return
        if not self._require_inputs():
            return

        out_dir = Path(self.out_dir.get().strip() or _default_out_dir())
        from_mdb = self.input_mode.get() == 'mdb'

        # Nueva carga = ejecución limpia (sin restos de la anterior)
        self._reset_session(full=False, announce=False)

        self._set_busy(True)
        self.status.set(
            'Leyendo base de datos CYMDIST… espere.' if from_mdb
            else 'Analizando TXT en profundidad… espere.'
        )
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        self._append_log('--- Carga e inventario de alimentadores ---')
        if from_mdb:
            self._append_log(f'Base de red: {Path(self.mdb.get().strip()).name}')
            if self.equipment_mdb.get().strip():
                self._append_log(f'Base de equipos: {Path(self.equipment_mdb.get().strip()).name}')
            if self.study.get().strip():
                self._append_log(f'Estudio: {Path(self.study.get().strip()).name}')
        else:
            self._append_log(f'RED: {Path(self.red.get().strip()).name}')
            self._append_log(f'CARGA: {Path(self.loads.get().strip()).name}')
            self._append_log(f'BD_Equipo: {Path(self.equipment.get().strip()).name}')

        def worker() -> None:
            try:
                dataset = self._load_input_dataset()
                inventory = build_dataset_inventory(dataset)
                inv_path = write_inventory(inventory, out_dir / 'dataset_inventory.json')
                report = format_inventory_report(inventory)
                self.root.after(
                    0,
                    lambda: self._on_load_done(True, dataset, inventory, report, str(inv_path), None),
                )
            except Exception as exc:
                err = str(exc)
                self.root.after(
                    0,
                    lambda: self._on_load_done(False, None, None, None, None, err),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_load_done(
        self,
        ok: bool,
        dataset: CymdistDataset | None,
        inventory: dict | None,
        report: str | None,
        inv_path: str | None,
        error: str | None,
    ) -> None:
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0)
        self._set_busy(False)
        if not ok or dataset is None or inventory is None:
            messagebox.showerror('Error al leer TXT', error or 'Error desconocido')
            self._append_log(f'ERROR lectura: {error}')
            self.status.set('Error al cargar TXT')
            return

        self._dataset = dataset
        self._inventory = inventory
        self._clear_feeder_list()

        for row in inventory['feeders']:
            status = 'Convertible' if row['convertible'] else 'Stub (0 tramos)'
            self.feeder_list.insert(
                '',
                END,
                iid=row['network_id'],
                values=(
                    row['feeder'],
                    row['network_id'],
                    row['nominal_kv'],
                    row['sections'],
                    row['loads'],
                    row['switches'],
                    status,
                ),
            )

        totals = inventory['totals']
        conv = inventory['conversion']
        integ = inventory['integrity']
        msg = (
            f"Inventario: {totals['feeders']} alimentadores · "
            f"{conv['expected_dgs_files']} DGS esperados · "
            f"{totals['sections']} tramos · {totals['customer_loads']} cargas"
        )
        self.status.set(msg)
        if report:
            self._append_log(report)
        if inv_path:
            self._append_log(f'Inventario JSON: {inv_path}')

        short = (
            f"Análisis completo de los 3 TXT.\n\n"
            f"Alimentadores leídos: {totals['feeders']}\n"
            f"Convertibles (con tramos): {totals['convertible_feeders']}\n"
            f"Stub sin SECTION: {totals['stub_feeders']}\n"
            f"Tramos / cargas / SW: {totals['sections']} / "
            f"{totals['customer_loads']} / {totals['switches']}\n\n"
            f"Conversión de este proyecto:\n"
            f"→ {conv['expected_dgs_files']} archivos .dgs independientes\n"
            f"(uno por alimentador convertible).\n\n"
            f"Integridad: {integ['errors']} errores, {integ['warnings']} avisos\n"
            f"Detalle en el Registro y en dataset_inventory.json"
        )
        if integ['errors']:
            messagebox.showwarning('Inventario con errores de integridad', short)
        else:
            messagebox.showinfo('Inventario TXT listo', short)
        self._refresh_convert_buttons()

    def _select_all_feeders(self) -> None:
        if self.convert_all.get():
            self.convert_all.set(False)
            self.feeder_list.configure(selectmode='extended')
        children = self.feeder_list.get_children()
        if not children:
            messagebox.showwarning('Sin datos', 'Primero pulse «Cargar / listar alimentadores».')
            return
        self.feeder_list.selection_set(children)
        self.status.set(
            f'Seleccionados {len(children)} — pulse «Convertir {len(children)} seleccionados → DGS».'
        )
        self._append_log(f'Selección manual de todos: {len(children)}.')
        self._refresh_convert_buttons()

    def _clear_feeders(self) -> None:
        self.feeder_list.selection_remove(*self.feeder_list.selection())
        if self.convert_all.get():
            self.convert_all.set(False)
            self.feeder_list.configure(selectmode='extended')
        self.status.set('Selección limpiada.')
        self._refresh_convert_buttons()

    def _open_out(self) -> None:
        path = Path(self.out_dir.get().strip())
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showinfo('Carpeta', f'{path}\n({exc})')

    def _selected_feeder_names(self) -> list[str]:
        return [self.feeder_list.item(i, 'values')[0] for i in self.feeder_list.selection()]

    def _start_powerfactory_flow(self) -> None:
        """Import selected feeder DGS into DigSilent, ensure scenario, run LDF with corrections."""
        if self._busy:
            return
        selected = self._selected_feeder_names()
        if not selected:
            messagebox.showwarning(
                'Selección',
                'Seleccione al menos un alimentador convertido (clic / Ctrl+clic)\n'
                'y pulse «Cargar DGS en DigSILENT + flujo».',
            )
            return

        out_dir = Path(self.out_dir.get().strip())
        jobs: list[tuple[str, Path, Path | None]] = []
        missing: list[str] = []
        for feeder in selected:
            dgs = out_dir / f'{feeder}.dgs'
            if not dgs.is_file():
                missing.append(feeder)
                continue
            geo = out_dir / f'{feeder}_geography.json'
            jobs.append((feeder, dgs, geo if geo.is_file() else None))

        if missing:
            messagebox.showwarning(
                'DGS no encontrado',
                'Primero convierta a DGS. Faltan archivos:\n'
                + '\n'.join(f'  • {f}.dgs' for f in missing[:12])
                + ('\n  …' if len(missing) > 12 else ''),
            )
            if not jobs:
                return

        script = _powerfactory_acceptance_script()
        if not script.is_file():
            messagebox.showerror(
                'Script no encontrado',
                f'No está tools/powerfactory_acceptance.py:\n{script}',
            )
            return

        pf_dir = _pf_python_dir()
        pf_python, pf_python_why = _python_for_pf(pf_dir)
        if pf_python is None:
            wanted = _pf_api_version(pf_dir)
            running = f'{sys.version_info.major}.{sys.version_info.minor}'
            messagebox.showerror(
                'Python incompatible con la API de PowerFactory',
                f'La API de PowerFactory es para Python {wanted}, pero el conversor corre '
                f'sobre Python {running}. powerfactory.pyd es una extensión binaria: solo '
                f'carga en su versión exacta.'
                '\n\n'
                f'Instale Python {wanted}, o indique el intérprete en la variable de '
                'entorno IGEA_PF_INTERPRETER.',
            )
            self._append_log(f'DigSILENT no disponible: {pf_python_why}')
            return
        if not messagebox.askyesno(
            'DigSILENT PowerFactory',
            f'Se importarán {len(jobs)} DGS en PowerFactory,\n'
            'se activará el proyecto, se creará/activará un escenario de operación,\n'
            'se ejecutará el flujo de potencia (ComLdf, con correcciones si no converge)\n'
            'y la suite de estudios (corto circuito ComShc si la licencia lo permite).\n\n'
            'Requisitos: PowerFactory instalado y preferiblemente abierto.\n'
            f'API Python: {pf_dir or "(no detectada — use PF_PYTHON)"}\n'
            f'Intérprete: {pf_python}  [{pf_python_why}]\n\n'
            '¿Continuar?',
        ):
            return

        self._set_busy(True)
        self.status.set('DigSILENT: importando / estudios… no cierre la ventana.')
        self.progress.configure(mode='determinate', value=0, maximum=max(len(jobs), 1))
        self._append_log('--- Inicio DigSILENT: import + escenario + flujo + estudios ---')
        if pf_dir:
            self._append_log(f'PF_PYTHON={pf_dir}')
            self._append_log(f'Intérprete para la API: {pf_python}  [{pf_python_why}]')
        else:
            self._append_log(
                'AVISO: no se encontró carpeta PowerFactory/Python. '
                'Defina PF_PYTHON o añada el API a PYTHONPATH.'
            )

        def worker() -> None:
            results: list[str] = []
            ok_n = 0
            fail_n = 0
            env = os.environ.copy()
            if pf_dir is not None:
                env['PYTHONPATH'] = str(pf_dir) + os.pathsep + env.get('PYTHONPATH', '')
                env['PF_PYTHON'] = str(pf_dir)

            for index, (feeder, dgs, geo) in enumerate(jobs, start=1):

                def update_status(i=index, name=feeder, total=len(jobs)) -> None:
                    self.progress.configure(maximum=total, value=i - 1)
                    self.status.set(f'DigSILENT {i}/{total}: {name}')
                    self._append_log(f'[{i}/{total}] Import + flujo + estudios {name}…')

                self.root.after(0, update_status)

                cmd = [
                    # No sys.executable: el venv puede correr un Python que la API
                    # binaria de PowerFactory no soporta (ver _python_for_pf).
                    str(pf_python),
                    str(script),
                    '--import-dgs',
                    str(dgs),
                    '--ensure-scenario',
                    '--run-load-flow',
                    '--fix-until-converge',
                    '--run-studies',
                ]
                if geo is not None:
                    cmd.extend(['--manifest', str(geo)])
                out_json = out_dir / f'{feeder}_powerfactory_acceptance.json'
                out_txt = out_dir / f'{feeder}_powerfactory_acceptance.txt'
                cmd.extend(['--output-json', str(out_json), '--output-txt', str(out_txt)])

                try:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        env=env,
                        cwd=str(_project_root()),
                        check=False,
                    )
                    stdout = (proc.stdout or '').strip()
                    stderr = (proc.stderr or '').strip()
                    if stdout:
                        self.root.after(0, lambda t=stdout: self._append_log(t))
                    if stderr:
                        self.root.after(0, lambda t=stderr: self._append_log(t))
                    if proc.returncode == 0:
                        ok_n += 1
                        results.append(f'OK {feeder} → convergencia / aceptación')
                    elif proc.returncode == 3:
                        fail_n += 1
                        results.append(
                            f'FAIL {feeder}: API PowerFactory no disponible '
                            '(abra PF o configure PF_PYTHON / PYTHONPATH)'
                        )
                    else:
                        fail_n += 1
                        # Prefer last meaningful line from stderr/stdout.
                        detail = ''
                        for block in (stderr, stdout):
                            for line in reversed(block.splitlines()):
                                if line.strip():
                                    detail = line.strip()
                                    break
                            if detail:
                                break
                        results.append(f'FAIL {feeder}: {detail or f"exit {proc.returncode}"}')
                except Exception as exc:
                    fail_n += 1
                    results.append(f'FAIL {feeder}: {exc}')

            summary = {
                'ok': ok_n,
                'failed': fail_n,
                'requested': len(jobs),
                'lines': results,
                'out_dir': str(out_dir),
            }
            self.root.after(0, lambda: self._on_powerfactory_done(summary))

        threading.Thread(target=worker, daemon=True).start()

    def _on_powerfactory_done(self, summary: dict) -> None:
        self._set_busy(False)
        ok_n = summary.get('ok', 0)
        fail_n = summary.get('failed', 0)
        requested = summary.get('requested', 0)
        for line in summary.get('lines') or []:
            self._append_log(f'  {line}')
        self._append_log('--- Fin DigSILENT ---')
        self.progress.configure(value=self.progress['maximum'] or 1)
        self.status.set(f'DigSILENT terminado — OK: {ok_n}  Fallidos: {fail_n}')
        short = (
            f'DigSILENT: import + escenario + flujo + estudios.\n\n'
            f'Solicitados: {requested}\n'
            f'OK: {ok_n}\n'
            f'Fallidos: {fail_n}\n\n'
            f'Los .dgs del convertidor quedan en la carpeta de salida:\n'
            f'{summary.get("out_dir")}\n'
            f'(si ComExport funciona: *_pf_converged.dgs)\n\n'
            f'Reportes: *_powerfactory_acceptance.json/.txt\n'
            f'en {summary.get("out_dir")}\n\n'
            'Detalle (diagnóstico / correcciones / ComShc / persistencia) en el Registro.'
        )
        if fail_n:
            messagebox.showwarning('DigSILENT terminado (con fallos)', short)
        else:
            messagebox.showinfo('DigSILENT terminado', short)

    def _start_convert(self, *, force_all: bool | None = None) -> None:
        if self._busy:
            return
        if not self._require_inputs():
            return
        if self._dataset is None:
            messagebox.showinfo('Carga pendiente', 'Primero pulse «Cargar / listar alimentadores».')
            return

        all_feeders = self.convert_all.get() if force_all is None else force_all
        selected = list(self.feeder_list.selection())
        if not all_feeders and not selected:
            messagebox.showwarning(
                'Selección',
                'Seleccione al menos un alimentador (clic / Ctrl+clic),\n'
                'use «Seleccionar todos», o pulse «Convertir TODOS → DGS».',
            )
            return

        aliases_path = self.aliases.get().strip() or None
        try:
            from .batch import convert_selection, load_aliases

            aliases = load_aliases(aliases_path)
        except Exception as exc:
            messagebox.showerror('Aliases', str(exc))
            return

        if self.include_geography.get():
            try:
                import pyproj  # noqa: F401
            except ImportError:
                messagebox.showerror(
                    'Falta pyproj',
                    'Para georreferenciación instale:\n  pip install -r requirements.txt\n'
                    'O desactive «Georreferenciación» para convertir sin GPS.',
                )
                return

        if self.write_preview.get() and not self.include_geography.get():
            messagebox.showerror(
                'Vista previa',
                'La vista previa del mapa requiere georreferenciación activa.',
            )
            return

        if self.export_xlsx.get():
            try:
                import pandas  # noqa: F401
                import openpyxl  # noqa: F401
            except ImportError:
                messagebox.showerror(
                    'Falta pandas/openpyxl',
                    'Para Excel instale:\n  pip install "igea-dgs[xlsx]"\n'
                    'O desactive «Exportar Excel».',
                )
                return

        out_dir = self.out_dir.get().strip()
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror('Salida', f'No se puede crear la carpeta de salida:\n{exc}')
            return

        selectors = [self.feeder_list.item(i, 'values')[0] for i in selected] if not all_feeders else None
        if all_feeders:
            scope = f'todos ({len(self.feeder_list.get_children())})'
        else:
            scope = f'{len(selectors)} seleccionado(s): {", ".join(selectors[:8])}' + (
                '…' if len(selectors) > 8 else ''
            )
        self._append_log(f'Alcance de conversión: {scope}')

        kwargs = dict(
            all_feeders=all_feeders,
            aliases=aliases,
            strict=self.strict.get(),
            include_geography=self.include_geography.get(),
            source_crs=self.source_crs.get().strip() or 'EPSG:32718',
            target_crs=self.target_crs.get().strip() or 'EPSG:4326',
            export_xlsx=self.export_xlsx.get(),
            export_tsv=self.export_tsv.get(),
            write_preview=self.write_preview.get(),
            preview_backend='auto',
        )
        # Reglas del proyecto (igea_dgs.reglas) con su catálogo: las mismas que la web.
        from .reglas import catalogo_del_proyecto

        kwargs['catalogo'] = catalogo_del_proyecto()
        dataset = self._dataset

        self._cancel = threading.Event()
        self._set_busy(True)
        self.status.set('Convirtiendo… puede cancelar en cualquier momento.')
        self.progress.configure(mode='determinate', value=0, maximum=100)
        self._append_log('--- Inicio de conversión ---')

        def on_progress(network_id: str, index: int, total: int) -> None:
            feeder = feeder_short_name(network_id)

            def update() -> None:
                self.progress.configure(maximum=max(total, 1), value=index)
                self.status.set(f'Convirtiendo {index}/{total}: {feeder}')
                self._append_log(f'[{index}/{total}] {feeder}…')

            self.root.after(0, update)

        def worker() -> None:
            try:
                manifest = convert_selection(
                    dataset, selectors, out_dir,
                    on_progress=on_progress, cancel=self._cancel, **kwargs,
                )
                summary = manifest['summary']
                lines = [
                    f"Solicitados: {summary['requested']}",
                    f"OK: {summary['ok']}",
                    f"Omitidos: {summary.get('skipped', 0)}",
                    f"Fallidos: {summary['failed']}",
                    f"Manifiesto: {Path(out_dir) / 'batch_manifest.json'}",
                ]
                for item in manifest.get('feeders', []):
                    feeder = item.get('feeder') or item.get('network_id', '?')
                    status = item.get('status')
                    if status == 'ok':
                        counts = item.get('counts') or {}
                        extra = []
                        if item.get('preview_html'):
                            extra.append('preview')
                        if item.get('xlsx'):
                            extra.append('xlsx')
                        if item.get('tsv_dir'):
                            extra.append('tsv')
                        suffix = f" [{', '.join(extra)}]" if extra else ''
                        lines.append(
                            f"  OK {feeder} → líneas={counts.get('source_lines', '?')} "
                            f"cargas={counts.get('source_loads', '?')} "
                            f"SED={counts.get('source_seds', counts.get('dgs_seds', '?'))}{suffix}"
                        )
                    elif status == 'skipped':
                        lines.append(f"  OMITIDO {feeder}: {item.get('error') or 'sin topología'}")
                    else:
                        err = item.get('error') or 'error'
                        lines.append(f"  FAIL {feeder}: {err}")
                self.root.after(0, lambda: self._on_convert_done(True, '\n'.join(lines), summary, out_dir))
            except Exception:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._on_convert_done(False, tb, None, out_dir))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _on_convert_done(self, ok: bool, detail: str, summary: dict | None, out_dir: str) -> None:
        self._set_busy(False)
        self._append_log(detail)
        self._append_log('--- Fin de conversión ---')
        if summary is not None:
            failed = summary.get('failed', 0)
            skipped = summary.get('skipped', 0)
            ok_n = summary.get('ok', 0)
            requested = summary.get('requested', 0)
            self.status.set(
                f'Conversión terminada — OK: {ok_n}  Omitidos: {skipped}  Fallidos: {failed}'
            )
            self.progress.configure(value=self.progress['maximum'] or 1)
            short = (
                f'Conversión finalizada.\n\n'
                f'Solicitados: {requested}\n'
                f'OK: {ok_n}\n'
                f'Omitidos: {skipped}\n'
                f'Fallidos: {failed}\n\n'
                f'Salida: {out_dir}\n'
                f'Manifiesto: batch_manifest.json\n\n'
                'Detalle completo en el Registro.'
            )
            if failed:
                messagebox.showwarning('Conversión terminada (con fallos)', short)
            else:
                messagebox.showinfo('Conversión terminada', short)
            if ok_n and messagebox.askyesno('Carpeta de salida', '¿Abrir la carpeta de salida ahora?'):
                self._open_out()
        else:
            self.status.set('Error en la conversión')
            first_line = detail.strip().splitlines()[-1] if detail.strip() else 'Error desconocido'
            messagebox.showerror('Error', f'{first_line}\n\nDetalle en el Registro.')

    # ---------------------------------------------- cargas de SED por plantilla

    def _single_selected_model(self):
        """Modelo del único alimentador seleccionado, o None con aviso al operador."""
        if self._dataset is None:
            messagebox.showinfo('Carga pendiente', 'Primero pulse «Cargar / listar alimentadores».')
            return None
        names = self._selected_feeder_names()
        if len(names) != 1:
            messagebox.showwarning(
                'Seleccione un alimentador',
                'Las cargas se actualizan por alimentador.\n\n'
                'Seleccione exactamente UNO en la lista.',
            )
            return None
        from .model import build_feeder_model
        from .reglas import REGLAS_PROYECTO, aplicar_reglas, catalogo_del_proyecto, preparar_dataset

        try:
            catalogo = catalogo_del_proyecto()
            preparar_dataset(self._dataset, catalogo=catalogo)
            modelo = build_feeder_model(
                self._dataset, names[0], strict=False,
                include_geography=self.include_geography.get(),
            )
            correcciones = None
            if catalogo is not None:
                from .catalog import leer_catalogo

                correcciones = leer_catalogo(catalogo)
            # El mismo modelo que el DGS: sin trafomix, puentes fundidos, SED ajustadas.
            aplicar_reglas(modelo, REGLAS_PROYECTO, correcciones=correcciones)
            return modelo
        except Exception as exc:
            self._append_log(traceback.format_exc())
            messagebox.showerror('Modelo', f'No se pudo construir {names[0]}:\n{exc}')
            return None

    def _download_load_template(self) -> None:
        model = self._single_selected_model()
        if model is None:
            return
        if not model.seds:
            messagebox.showinfo(
                'Sin SED',
                f'{model.name} no tiene SED en el export, así que no hay cargas que '
                'actualizar por plantilla.',
            )
            return
        path = filedialog.asksaveasfilename(
            title='Guardar plantilla de cargas',
            initialfile=f'{model.name}_cargas.xlsx',
            defaultextension='.xlsx',
            filetypes=[('Excel', '*.xlsx'), ('CSV', '*.csv')],
        )
        if not path:
            return
        from .loads import LoadTemplateError, model_sed_loads, write_template

        try:
            out = write_template(model_sed_loads(model), path)
        except LoadTemplateError as exc:
            messagebox.showerror('Plantilla', str(exc))
            return
        self._append_log(f'Plantilla de cargas: {out}  ({len(model.seds)} SED)')
        messagebox.showinfo(
            'Plantilla generada',
            f'{out.name}\n\n{len(model.seds)} SED de {model.name}.\n\n'
            'Escriba los valores nuevos en «Kw» y «Kvar» (o en «(kVA)» y «FP»); «accion» = omitir salta la fila. Vuelva a cargar el fichero '
            'con el botón 2.',
        )

    def _apply_load_template(self) -> None:
        model = self._single_selected_model()
        if model is None:
            return
        path = filedialog.askopenfilename(
            title='Plantilla de cargas rellenada',
            filetypes=[('Excel o CSV', '*.xlsx;*.csv'), ('Todos', '*.*')],
        )
        if not path:
            return
        from .loads import LoadTemplateError, build_plan, plan_to_payload, read_workbook

        try:
            # read_template no existía: el botón fallaba siempre. El libro trae una hoja
            # por alimentador; si solo trae una (o es un CSV), vale esa.
            hojas = read_workbook(path)
            hoja = hojas.get(model.name)
            if hoja is None and len(hojas) == 1:
                hoja = next(iter(hojas.values()))
            if hoja is None:
                raise LoadTemplateError(
                    f'El fichero no trae una hoja para {model.name}. '
                    f'Hojas: {", ".join(hojas) or "ninguna"}.')
            plan = build_plan(model, hoja)
        except LoadTemplateError as exc:
            messagebox.showerror('Plantilla', str(exc))
            return

        self._append_log('--- Plan de actualización de cargas ---')
        self._append_log(plan.report())

        if plan.row_errors:
            messagebox.showerror(
                'Plantilla con errores',
                f'{len(plan.row_errors)} fila(s) con error. No se aplica ningún cambio.\n\n'
                f'{plan.row_errors[0]}\n\nDetalle completo en el Registro.',
            )
            return
        if not plan.has_changes:
            messagebox.showinfo('Sin cambios', 'La plantilla no contiene SED del modelo que actualizar.')
            return

        if plan.unknown:
            # SED del fichero que no existen en el modelo: no se inventan aquí.
            faltan = ', '.join(r.sed_code for r in plan.unknown[:10])
            more = '' if len(plan.unknown) <= 10 else f' (+{len(plan.unknown) - 10} más)'
            if not messagebox.askyesno(
                'SED que no están en el modelo',
                f'{len(plan.unknown)} SED del fichero no existen en {model.name}:\n\n'
                f'{faltan}{more}\n\n'
                'Crear una SED nueva necesita datos que la plantilla no trae (nodo de '
                'conexión, tramo, kVA del transformador). Eso corresponde al módulo de '
                'creación de cargas.\n\n'
                f'¿Continuar actualizando solo las {len(plan.updates)} SED existentes?',
            ):
                return

        resumen = (
            f'Alimentador: {model.name}\n'
            f'SED a actualizar: {len(plan.updates)}\n'
            f'SED omitidas: {len(plan.skipped)}\n'
            f'SED sin mencionar (quedan igual): {len(plan.untouched)}\n'
            f'SED no existentes en el modelo: {len(plan.unknown)}\n\n'
            'Se escribirá el plan y se aplicará sobre el proyecto de PowerFactory.\n'
            '¿Continuar?'
        )
        if not messagebox.askyesno('Actualizar cargas en DigSILENT', resumen):
            return

        out_dir = Path(self.out_dir.get().strip() or _default_out_dir())
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / f'{model.name}_plan_cargas.json'
        plan_path.write_text(
            json.dumps(plan_to_payload(plan), indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        self._append_log(f'Plan escrito: {plan_path}')
        self._run_load_update(model.name, plan_path, out_dir)

    def _run_load_update(
        self, feeder: str, plan_path: Path, out_dir: Path, *,
        script_name: str = 'apply_sed_loads.py',
        report_suffix: str = 'cargas_aplicadas',
        busy_text: str = 'Actualizando cargas en DigSILENT…',
        ok_text: str = 'Cargas actualizadas',
    ) -> None:
        """Aplica el plan en PowerFactory, en proceso aparte y con su intérprete.

        Lo comparten la actualización masiva y la creación de SED: cambia el script y
        el nombre del informe, pero el problema es el mismo —la API de PowerFactory se
        enlaza a una versión concreta de CPython, así que hay que salir a otro
        intérprete— y no conviene tener dos copias de esa lógica.
        """
        pf_dir = _pf_python_dir()
        pf_python, why = _python_for_pf(pf_dir)
        if pf_python is None:
            messagebox.showerror(
                'Python incompatible con la API de PowerFactory',
                f'La API es para Python {_pf_api_version(pf_dir)} y el conversor corre '
                f'sobre {sys.version_info.major}.{sys.version_info.minor}. '
                'Instale esa versión o defina IGEA_PF_INTERPRETER.',
            )
            return
        script = _project_root() / 'tools' / script_name
        if not script.is_file():
            messagebox.showerror('Script ausente', f'No se encuentra {script}')
            return

        self._cancel = threading.Event()
        self._set_busy(True)
        self.status.set(busy_text)
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        self._append_log(f'Intérprete PowerFactory: {pf_python}  [{why}]')

        report_json = out_dir / f'{feeder}_{report_suffix}.json'
        env = os.environ.copy()
        if pf_dir is not None:
            env['PYTHONPATH'] = str(pf_dir) + os.pathsep + env.get('PYTHONPATH', '')
            env['PF_PYTHON'] = str(pf_dir)
        cmd = [
            str(pf_python), str(script),
            '--plan', str(plan_path),
            '--project', feeder,
            '--run-load-flow',
            '--output-json', str(report_json),
        ]

        def worker() -> None:
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, env=env,
                    cwd=str(_project_root()), check=False,
                )
                salida = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
                self.root.after(0, lambda t=salida: self._append_log(t))
                self.root.after(0, lambda rc=proc.returncode:
                                self._on_loads_done(rc, report_json, ok_text))
            except Exception:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._append_log(tb))
                self.root.after(0, lambda: self._on_loads_done(-1, report_json, ok_text))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _on_loads_done(self, returncode: int, report_json: Path,
                       ok_text: str = 'Cargas actualizadas') -> None:
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0)
        self._set_busy(False)
        if returncode == 0:
            self.status.set(f'{ok_text} en DigSILENT.')
            messagebox.showinfo(
                ok_text,
                f'Aplicado sobre el proyecto.\n\nInforme: {report_json.name}\n'
                'Detalle en el Registro.',
            )
            return
        if returncode == 3:
            self.status.set('DigSILENT no disponible.')
            messagebox.showerror(
                'DigSILENT no disponible',
                'No se pudo conectar con PowerFactory. Ábralo y reintente.',
            )
            return
        self.status.set('La actualización terminó con avisos o fallos.')
        messagebox.showwarning(
            'Actualización incompleta',
            f'El proceso devolvió el código {returncode}. Puede haber SED no encontradas '
            'o ambiguas en el proyecto.\n\nRevise el Registro y el informe.',
        )

    # ------------------------------------------------------------------
    # Creación de SED nuevas
    # ------------------------------------------------------------------

    def _download_create_template(self) -> None:
        model = self._single_selected_model()
        if model is None:
            return
        path = filedialog.asksaveasfilename(
            title='Guardar plantilla de creación de SED',
            initialfile=f'{model.name}_sed_nuevas.xlsx',
            defaultextension='.xlsx',
            filetypes=[('Excel', '*.xlsx'), ('CSV', '*.csv')],
        )
        if not path:
            return
        from .loads import LoadTemplateError
        from .loads_create import write_create_template

        try:
            out = write_create_template(
                [], path, feeder=model.name, node_choices=sorted(model.nodes),
            )
        except LoadTemplateError as exc:
            messagebox.showerror('Plantilla', str(exc))
            return
        self._append_log(f'Plantilla de creación: {out}  ({len(model.nodes)} nodos)')
        messagebox.showinfo(
            'Plantilla generada',
            f'{out.name}\n\nRellene una fila por SED nueva.\n\n'
            'Basta con SED, CoordX, CoordY y kVA_instalado: el nodo de conexión y el '
            'conductor se deducen del punto. Si prefiere fijarlos, use las columnas '
            '«nodo_conexion» y «conductor».\n\n'
            'La hoja «nodos_validos» lista los nodos del alimentador.',
        )

    def _apply_create_template(self) -> None:
        model = self._single_selected_model()
        if model is None:
            return
        path = filedialog.askopenfilename(
            title='Plantilla de creación rellenada',
            filetypes=[('Excel o CSV', '*.xlsx;*.csv'), ('Todos', '*.*')],
        )
        if not path:
            return
        from .loads import LoadTemplateError
        from .loads_create import build_create_plan, read_create_workbook

        try:
            hojas = read_create_workbook(path)
        except LoadTemplateError as exc:
            messagebox.showerror('Plantilla', str(exc))
            return
        filas = [r for rows, _ in hojas.values() for r in rows]
        errores = [e for _, errs in hojas.values() for e in errs]
        plan = build_create_plan(model, filas, errores)
        self._finish_create(model, plan)

    def _create_single_load(self) -> None:
        """Formulario para una sola SED. Comparte validación con la plantilla."""
        model = self._single_selected_model()
        if model is None:
            return
        datos = _NewSedDialog(self.root, model.name).result
        if datos is None:
            return
        from .loads_create import build_create_plan, single_new_load

        filas, errores = single_new_load(feeder=model.name, **datos)
        plan = build_create_plan(model, filas, errores)
        self._finish_create(model, plan)

    def _finish_create(self, model, plan) -> None:
        """Enseña el plan de creación, pide confirmación y lo aplica."""
        self._append_log('--- Plan de creación de SED ---')
        self._append_log(plan.report())

        if plan.row_errors:
            messagebox.showerror(
                'Datos con errores',
                f'{len(plan.row_errors)} fila(s) con error. No se crea nada.\n\n'
                f'{plan.row_errors[0]}\n\nDetalle completo en el Registro.',
            )
            return
        if not plan.create:
            texto = 'No hay ninguna SED nueva que crear.'
            if plan.already_exists:
                texto += (f'\n\n{len(plan.already_exists)} ya existen en {model.name}; '
                          'esas se actualizan con los botones 1 y 2.')
            messagebox.showinfo('Sin SED que crear', texto)
            return

        detalle = '\n'.join(
            f'  · {i.load.sed_code}: {i.load.installed_kva:g} kVA → nodo {i.node_id} '
            f'a {i.distance_m:,.0f} m, conductor {i.conductor.code} '
            f'(ΔV {i.conductor.voltage_drop_pct:.2f} %)'
            for i in plan.create[:12]
        )
        mas = '' if len(plan.create) <= 12 else f'\n  … y {len(plan.create) - 12} más'
        if not messagebox.askyesno(
            'Crear SED en DigSILENT',
            f'Alimentador: {model.name}\nSED nuevas: {len(plan.create)}\n\n'
            f'{detalle}{mas}\n\n'
            'Se creará en PowerFactory el nodo, la derivación aérea, la subestación, '
            'el transformador y la carga.\n¿Continuar?',
        ):
            return

        from .loads_create import create_plan_to_payload

        out_dir = Path(self.out_dir.get().strip() or _default_out_dir())
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / f'{model.name}_plan_sed_nuevas.json'
        plan_path.write_text(
            json.dumps(
                create_plan_to_payload(
                    plan, nominal_kv=model.nominal_kv,
                    source_crs=self.source_crs.get().strip(),
                ),
                indent=2, ensure_ascii=False,
            ) + '\n',
            encoding='utf-8',
        )
        self._append_log(f'Plan escrito: {plan_path}')
        self._run_load_update(
            model.name, plan_path, out_dir,
            script_name='create_sed_loads.py',
            report_suffix='sed_creadas',
            busy_text='Creando SED en DigSILENT…',
            ok_text='SED creadas',
        )

    # ------------------------------------------------------------------
    # Sistema completo: los 96 alimentadores en una sola red
    # ------------------------------------------------------------------

    def _entradas_para_guion(self) -> list[str] | None:
        """Los argumentos de entrada que espera cualquiera de los guiones.

        Se leen de los mismos campos que usa la conversión, así que la interfaz no
        tiene una segunda idea de dónde están los ficheros.
        """
        if self.input_mode.get() == 'mdb':
            mdb = self.mdb.get().strip()
            if not mdb or not Path(mdb).is_file():
                messagebox.showwarning(
                    'Falta la base de datos',
                    'Elija el fichero .mdb de CYMDIST en el Paso 1.')
                return None
            argumentos = ['--mdb', mdb]
            equipo = self.equipment_mdb.get().strip()
            if equipo:
                argumentos += ['--equipment-mdb', equipo]
            return argumentos

        rutas = {'--red': self.red.get().strip(),
                 '--cargas': self.loads.get().strip(),
                 '--equipos': self.equipment.get().strip()}
        faltan = [k for k, v in rutas.items() if not v or not Path(v).is_file()]
        if faltan:
            messagebox.showwarning(
                'Faltan ficheros de entrada',
                'Elija los tres TXT en el Paso 1 antes de convertir el sistema.\n\n'
                f'Sin indicar: {", ".join(faltan)}')
            return None
        argumentos = []
        for clave, valor in rutas.items():
            argumentos += [clave, valor]
        return argumentos

    def _lanzar_guion(
        self, guion: str, argumentos: list[str], *, titulo: str, al_terminar=None,
    ) -> None:
        """Ejecuta un guion de tools/ en segundo plano, volcando su salida al Registro.

        Va por subproceso, no en el propio hilo, por dos razones que ya costaron
        tiempo: PowerFactory solo admite un proceso con el motor a la vez, y la
        interfaz tiene que seguir respondiendo mientras una red de 53.000 barras se
        importa.
        """
        script = _project_root() / 'tools' / guion
        if not script.is_file():
            messagebox.showerror('Guion ausente', f'No se encuentra {script}')
            return

        self._cancel = threading.Event()
        self._set_busy(True)
        self.status.set(f'{titulo}…')
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        self._append_log(f'--- {titulo} ---')

        orden = [sys.executable, str(script)] + argumentos
        self._append_log(' '.join(orden))

        def worker() -> None:
            try:
                proc = subprocess.run(
                    orden, capture_output=True, text=True, check=False,
                    cwd=str(_project_root()), encoding='utf-8', errors='replace',
                )
                salida = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
                self.root.after(0, lambda t=salida: self._append_log(t))
                self.root.after(
                    0, lambda rc=proc.returncode: self._guion_terminado(rc, titulo, al_terminar))
            except Exception:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._append_log(tb))
                self.root.after(0, lambda: self._guion_terminado(-1, titulo, al_terminar))

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _guion_terminado(self, returncode: int, titulo: str, al_terminar) -> None:
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0)
        self._set_busy(False)
        if returncode == 0:
            self.status.set(f'{titulo}: terminado.')
            if al_terminar:
                al_terminar()
            else:
                messagebox.showinfo(titulo, 'Terminado. El detalle está en el Registro.')
            return
        self.status.set(f'{titulo}: terminó con código {returncode}.')
        messagebox.showwarning(
            titulo,
            f'El proceso devolvió el código {returncode}.\n\n'
            'Las causas más frecuentes son que PowerFactory no esté abierto, o que '
            'otro proceso tenga tomado su motor: solo admite uno a la vez.\n\n'
            'El detalle está en el Registro.')

    def _build_system_grid(self) -> None:
        argumentos = self._entradas_para_guion()
        if argumentos is None:
            return
        if not messagebox.askyesno(
            'Convertir todo a una sola grid',
            'Se unirán TODOS los alimentadores en una sola red y se importará en '
            'DigSILENT.\n\n'
            'Cada alimentador conserva su tensión y su fuente, y los enlaces entre '
            'ellos quedan como interruptores normalmente abiertos.\n\n'
            'Sobre el export completo son unos 30 MB y varios minutos. ¿Continuar?',
        ):
            return
        salida = Path(self.out_dir.get().strip() or _default_out_dir()) / 'sistema'
        self._lanzar_guion(
            'build_system_grid.py',
            argumentos + ['--nombre', 'SISTEMA',
                          '--out', str(salida / 'SISTEMA.dgs'),
                          '--source-crs', self.source_crs.get().strip() or 'EPSG:32718',
                          '--importar', '--run-load-flow'],
            titulo='Red unida en una sola grid',
        )

    def _run_base_scenario(self) -> None:
        argumentos = self._entradas_para_guion()
        if argumentos is None:
            return
        if not messagebox.askyesno(
            'Escenario base del año 0',
            'Se construirá la red unida, se importará en DigSILENT creando el caso '
            'ANIO_0_BASE con su escenario de operación, se hará converger el flujo y '
            'se ejecutarán los estudios.\n\n'
            'Los estudios que resuelven la red muchas veces —contingencias N-1, '
            'fiabilidad, optimizaciones— quedan fuera: sobre 53.000 barras pueden '
            'tardar horas.\n\n'
            'Es la operación más larga de la interfaz. ¿Continuar?',
        ):
            return
        salida = Path(self.out_dir.get().strip() or _default_out_dir()) / 'anio0'
        self._lanzar_guion(
            'base_scenario.py',
            argumentos + ['--nombre', 'PIDE_ANIO_0', '--out-dir', str(salida),
                          '--source-crs', self.source_crs.get().strip() or 'EPSG:32718'],
            titulo='Escenario base año 0',
        )

    def _missing_data(self) -> None:
        """Qué estudios se pueden sustentar hoy y qué dato falta para los demás."""
        argumentos = self._entradas_para_guion()
        if argumentos is None:
            return
        salida = Path(self.out_dir.get().strip() or _default_out_dir()) / 'anio0'
        self._lanzar_guion(
            'base_scenario.py',
            argumentos + ['--solo-datos', '--out-dir', str(salida)],
            titulo='Datos que faltan para el año 0',
            al_terminar=lambda: messagebox.showinfo(
                'Datos que faltan',
                'El informe está en el Registro y en anio0/datos_faltantes.json.\n\n'
                'Los estudios marcados «SIN DATOS» se ejecutan igual pero su resultado '
                'no significa nada: es el caso de la fiabilidad con las tasas de falla '
                'a cero, que devuelve SAIDI = 0 sin fallar.'),
        )

    # ------------------------------------------------------------------
    # Catálogo de parámetros eléctricos
    # ------------------------------------------------------------------

    def _catalog_models(self) -> list:
        """Modelos de los alimentadores marcados, o de todos si no hay selección."""
        if self._dataset is None:
            messagebox.showinfo('Carga pendiente',
                                'Primero pulse «Cargar / listar alimentadores».')
            return []
        from .model import build_feeder_model

        elegidos = set(self._selected_feeder_names())
        modelos = []
        fallidos = 0
        for net in self._dataset.feeder_ids():
            try:
                m = build_feeder_model(self._dataset, net, strict=False,
                                       include_geography=False)
            except Exception:
                fallidos += 1
                continue
            if not elegidos or m.name in elegidos:
                modelos.append(m)
        if fallidos:
            self._append_log(
                f'{fallidos} alimentador(es) no se pudieron construir y quedan fuera '
                'del catálogo.'
            )
        if not modelos:
            messagebox.showwarning('Sin alimentadores',
                                   'No se pudo construir ningún alimentador.')
        return modelos

    def _build_catalog(self) -> None:
        modelos = self._catalog_models()
        if not modelos:
            return
        from .catalog import CatalogError, auditar, escribir_catalogo, input_dir

        self.status.set('Auditando parámetros contra las fichas…')
        self.root.update_idletasks()
        try:
            aud = auditar(modelos)
            destino = escribir_catalogo(
                aud, base=_project_root(), nominal_kv=modelos[0].nominal_kv,
            )
        except CatalogError as exc:
            self.status.set(DEFAULT_STATUS)
            messagebox.showerror('Catálogo', str(exc))
            return

        self._append_log('--- Auditoría de parámetros eléctricos ---')
        self._append_log(aud.resumen())
        for h in aud.hallazgos:
            self._append_log('  ' + h.linea())
        self._append_log(f'Catálogo: {destino}')
        self.status.set(f'Catálogo generado: {len(aud.graves)} hallazgos graves.')

        messagebox.showinfo(
            'Catálogo de parámetros',
            f'{destino}\n\n{aud.resumen()}\n\n'
            'La hoja «hallazgos» lista las diferencias entre el modelo y la ficha, y '
            '«parametros_por_elemento» dice qué ficha hace falta para cada dato.\n\n'
            'Complete las columnas en blanco, marque la fila como «ficha» y vuelva a '
            'cargarla con «Aplicar catálogo corregido».',
        )
        try:
            os.startfile(input_dir(_project_root()))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - abrir la carpeta es una comodidad, no el trabajo
            pass

    def _apply_catalog(self) -> None:
        model = self._single_selected_model()
        if model is None:
            return
        from .catalog import (
            CATALOG_FILENAME, CatalogError, aplicar_correcciones, input_dir,
            leer_catalogo,
        )

        por_defecto = input_dir(_project_root()) / CATALOG_FILENAME
        path = filedialog.askopenfilename(
            title='Catálogo de parámetros corregido',
            initialdir=str(por_defecto.parent),
            initialfile=por_defecto.name if por_defecto.exists() else '',
            filetypes=[('Excel', '*.xlsx'), ('Todos', '*.*')],
        )
        if not path:
            return
        try:
            correcciones = leer_catalogo(path)
        except CatalogError as exc:
            messagebox.showerror('Catálogo', str(exc))
            return
        if not correcciones:
            messagebox.showinfo(
                'Sin correcciones',
                'El catálogo no trae ninguna fila marcada como «ficha» o «derivado» '
                'con un valor que aplicar.\n\n'
                'Escriba el valor de la ficha en «R1_ficha_ohm_km» o '
                '«ampacidad_ficha_A» y ponga «ficha» en la columna «estado».',
            )
            return

        cambios = aplicar_correcciones(model, correcciones)
        if not cambios:
            messagebox.showinfo(
                'Sin cambios',
                f'Las {len(correcciones)} filas del catálogo ya coinciden con '
                f'{model.name}. No hay nada que corregir.',
            )
            return
        self._append_log(f'--- Catálogo aplicado a {model.name} ---')
        self._append_log(
            '  La identidad de cada elemento se conserva: el código, el material y la '
            'sección salen del export. Solo cambian sus características.'
        )
        for c in cambios:
            self._append_log('  ' + c.linea())
        # Un cambio grande no es cosmético: las pérdidas y la caída de tensión de esos
        # tramos se mueven en la misma proporción, y quien lo aplica debe saberlo antes
        # de que el estudio dé otro resultado.
        fuertes = [c for c in cambios
                   if c.variacion_pct is not None and abs(c.variacion_pct) >= 25.0]
        aviso = ''
        if fuertes:
            aviso = (f'\n\n{len(fuertes)} cambio(s) de más del 25 %. Las pérdidas y la '
                     'caída de tensión de esos tramos cambian en la misma proporción.')
        messagebox.showinfo(
            'Catálogo aplicado',
            f'{len(cambios)} característica(s) corregidas en {model.name}:\n\n'
            + '\n'.join(c.linea() for c in cambios[:12])
            + ('' if len(cambios) <= 12 else f'\n… y {len(cambios) - 12} más')
            + aviso
            + '\n\nVuelva a convertir el alimentador para que el DGS salga con estos '
              'valores. El TXT de origen no se toca.',
        )
        self.status.set(f'{len(cambios)} características corregidas desde el catálogo.'
                        ' Reconvierta para aplicarlas al DGS.')

    def _on_close(self) -> None:
        # Lo que se cambió sin pasar por un selector —el CRS, las casillas— se
        # guarda aquí. Los ficheros ya se guardaron al elegirlos.
        self._guardar_ajustes()
        # Cerrar durante un lote mataba el hilo daemon a mitad de escritura y dejaba
        # ficheros truncados indistinguibles de válidos. Ahora se cancela, se espera a
        # que el motor cierre el alimentador en curso y solo entonces se destruye.
        if self._busy:
            if not messagebox.askyesno(
                'Conversión en curso',
                '¿Cancelar la conversión en curso y salir? Se conservará todo lo ya '
                'convertido; el alimentador en curso termina o, si no da tiempo, se '
                'descarta entero. Nunca queda a medias.',
            ):
                return
            if self._cancel is not None:
                self._cancel.set()
            self.status.set('Cancelando antes de salir…')
            self.root.update_idletasks()
            self._wait_for_worker()
        self._reset_session(full=True, announce=False)
        self.root.destroy()

    def _wait_for_worker(self, timeout_s: float = 30.0) -> bool:
        """Espera a que el hilo termine el alimentador en curso y lo publique."""
        worker = self._worker
        if worker is None or not worker.is_alive():
            return True
        worker.join(timeout=timeout_s)
        if worker.is_alive():
            messagebox.showwarning(
                'Cierre forzado',
                f'La conversión no respondió en {timeout_s:.0f} s. Al salir ahora, el '
                'alimentador en curso puede quedar incompleto en su carpeta temporal '
                f'«{STAGE_PREFIX}…», que puede borrar a mano. Los ya convertidos están '
                'completos.',
            )
            return False
        return True


def main() -> int:
    root = Tk()
    try:
        style = ttk.Style()
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        elif 'clam' in style.theme_names():
            style.theme_use('clam')
    except Exception:
        pass
    ConverterApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
