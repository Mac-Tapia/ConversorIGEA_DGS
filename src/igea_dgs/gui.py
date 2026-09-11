"""Interfaz gráfica para convertir TXT IGEA/CYMDIST → DGS PowerFactory."""

from __future__ import annotations

import os
import threading
import traceback
from pathlib import Path
from tkinter import (
    BooleanVar,
    END,
    LEFT,
    RIGHT,
    StringVar,
    Tk,
    W,
    X,
    Y,
    BOTH,
    filedialog,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

from .dataset import CymdistDataset
from .naming import feeder_short_name, sort_key_feeder
from . import __version__


CRS_PRESETS = (
    'EPSG:32718',  # UTM 18S (ejemplo costa Perú)
    'EPSG:32717',  # UTM 17S
    'EPSG:32719',  # UTM 19S
    'EPSG:32716',  # UTM 16S
    'EPSG:32618',  # UTM 18N
    'EPSG:31983',  # SIRGAS 2000 / UTM 23S (ejemplo Brasil)
    'EPSG:5343',   # POSGAR 2007 / Argentina 3
    'EPSG:4326',   # WGS84 lon/lat (si CoordX/Y ya son geográficas)
)

STEPS_HINT = (
    'Flujo: 1) Elija los tres TXT  ·  2) Cargar / listar  ·  '
    '3) Seleccione uno, varios o todos  ·  4) Convertir a DGS.'
)

DEFAULT_STATUS = 'Seleccione los tres TXT y pulse «Cargar / listar alimentadores».'


def _default_aliases_path() -> str:
    path = Path(__file__).resolve().parents[2] / 'config' / 'line_type_aliases.json'
    return str(path) if path.is_file() else ''


def _default_out_dir() -> str:
    return str(Path.cwd() / 'output' / 'gui')


def _legacy_state_path() -> Path:
    """Ruta del antiguo gui_state.json (se elimina para no arrastrar sesiones)."""
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        return Path(base) / 'igea-dgs' / 'gui_state.json'
    return Path.home() / '.igea-dgs' / 'gui_state.json'


class ConverterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f'Conversor IGEA/CYMDIST → DGS  v{__version__}')
        self.root.minsize(780, 640)
        self.root.geometry('920x720')

        self.red = StringVar()
        self.loads = StringVar()
        self.equipment = StringVar()
        self.out_dir = StringVar(value=_default_out_dir())
        self.aliases = StringVar(value=_default_aliases_path())
        self.source_crs = StringVar(value='EPSG:32718')
        self.target_crs = StringVar(value='EPSG:4326')
        self.include_geography = BooleanVar(value=True)
        self.strict = BooleanVar(value=True)
        self.convert_all = BooleanVar(value=False)
        self._dataset: CymdistDataset | None = None
        self._busy = False
        self._action_buttons: list[ttk.Button] = []

        self._build()
        self._discard_legacy_state()
        self._reset_session(full=True, announce=False)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build(self) -> None:
        pad = {'padx': 10, 'pady': 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text=STEPS_HINT, wraplength=860).pack(anchor=W, padx=10, pady=(0, 6))

        files = ttk.LabelFrame(frm, text='Paso 1 — Archivos de entrada (TXT IGEA/CYMDIST)', padding=10)
        files.pack(fill=X, **pad)
        self._file_row(files, 'RED_*.txt', self.red, self._browse_red)
        self._file_row(files, 'CARGA_*.txt', self.loads, self._browse_loads)
        self._file_row(files, 'BD_Equipo_*.txt (catálogo de equipos)', self.equipment, self._browse_equipment)
        self.files_ready = StringVar(value='Faltan archivos por seleccionar.')
        ttk.Label(files, textvariable=self.files_ready, foreground='#335').pack(anchor=W, pady=(6, 0))

        opts = ttk.LabelFrame(frm, text='Salida y opciones', padding=10)
        opts.pack(fill=X, **pad)
        self._file_row(opts, 'Carpeta de salida', self.out_dir, self._browse_out, directory=True)
        self._file_row(opts, 'Aliases de tipos (JSON, opcional)', self.aliases, self._browse_aliases)

        crs = ttk.Frame(opts)
        crs.pack(fill=X, pady=4)
        ttk.Label(crs, text='CRS origen (el de su empresa/región):').pack(side=LEFT)
        ttk.Combobox(crs, textvariable=self.source_crs, values=CRS_PRESETS, width=16).pack(side=LEFT, padx=6)
        ttk.Label(crs, text='CRS destino GPS:').pack(side=LEFT, padx=(12, 0))
        ttk.Combobox(crs, textvariable=self.target_crs, values=('EPSG:4326',), width=16).pack(side=LEFT, padx=6)
        ttk.Label(
            opts,
            text='Escriba cualquier código EPSG si no está en la lista. No está limitado a una empresa o zona.',
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

        feeders = ttk.LabelFrame(frm, text='Paso 2–3 — Alimentadores (uno, varios o todos)', padding=10)
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

        ttk.Label(
            feeders,
            text=(
                'Selección: clic = uno · Ctrl+clic = varios · Mayús+clic = rango · '
                '«Seleccionar todos» = todos de la lista · o marque «Convertir TODOS».'
            ),
            foreground='#444',
            wraplength=860,
        ).pack(anchor=W, pady=(4, 0))

        list_frm = ttk.Frame(feeders)
        list_frm.pack(fill=BOTH, expand=True, pady=6)
        scroll = ttk.Scrollbar(list_frm)
        scroll.pack(side=RIGHT, fill=Y)
        self.feeder_list = ttk.Treeview(
            list_frm,
            columns=('name', 'network', 'kv', 'sections'),
            show='headings',
            selectmode='extended',
            yscrollcommand=scroll.set,
            height=10,
        )
        scroll.config(command=self.feeder_list.yview)
        self.feeder_list.heading('name', text='Alimentador')
        self.feeder_list.heading('network', text='NetworkID')
        self.feeder_list.heading('kv', text='kV')
        self.feeder_list.heading('sections', text='Secciones')
        self.feeder_list.column('name', width=100, anchor=W)
        self.feeder_list.column('network', width=280, anchor=W)
        self.feeder_list.column('kv', width=80, anchor=W)
        self.feeder_list.column('sections', width=90, anchor=W)
        self.feeder_list.pack(side=LEFT, fill=BOTH, expand=True)
        self.feeder_list.bind('<<TreeviewSelect>>', self._on_feeder_select)
        self.feeder_list.bind('<Double-1>', self._on_feeder_double_click)

        # Paso 4 — acción principal: convertir el/los alimentador(es) seleccionado(s)
        convert_frm = ttk.LabelFrame(frm, text='Paso 4 — Conversión a DGS', padding=10)
        convert_frm.pack(fill=X, **pad)
        actions = ttk.Frame(convert_frm)
        actions.pack(fill=X)
        self.convert_btn = ttk.Button(
            actions,
            text='Convertir a DGS (seleccionados)',
            command=self._start_convert,
        )
        self.convert_btn.pack(side=LEFT, padx=(0, 8), ipady=4)
        self.open_out_btn = ttk.Button(actions, text='Abrir carpeta de salida', command=self._open_out)
        self.open_out_btn.pack(side=LEFT)
        self._action_buttons.extend([self.convert_btn, self.open_out_btn])
        self.status = StringVar(value=DEFAULT_STATUS)
        ttk.Label(actions, textvariable=self.status).pack(side=LEFT, padx=12)
        ttk.Label(
            convert_frm,
            text=(
                'Convierte el alimentador seleccionado, varios a la vez, o todos '
                'si marcó «Convertir TODOS». Doble clic en una fila también inicia la conversión.'
            ),
            foreground='#444',
            wraplength=860,
        ).pack(anchor=W, pady=(6, 0))

        progress_frm = ttk.Frame(frm)
        progress_frm.pack(fill=X, **pad)
        self.progress = ttk.Progressbar(progress_frm, mode='determinate')
        self.progress.pack(fill=X)

        log_frm = ttk.LabelFrame(frm, text='Registro', padding=6)
        log_frm.pack(fill=BOTH, expand=True, **pad)
        self.log = ScrolledText(log_frm, height=10, wrap='word', state='disabled')
        self.log.pack(fill=BOTH, expand=True)

        note = (
            'Nota: BD_Equipo es el catálogo TXT de equipos CYMDIST (no una base SQL). '
            'Los tres archivos deben ser la exportación IGEA/CYMDIST del mismo lote.'
        )
        ttk.Label(frm, text=note, foreground='#444').pack(anchor=W, padx=10)

    def _file_row(self, parent, label, var, command, directory: bool = False) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=2)
        ttk.Label(row, text=label, width=36).pack(side=LEFT)
        ttk.Entry(row, textvariable=var).pack(side=LEFT, fill=X, expand=True, padx=6)
        ttk.Button(row, text='Examinar…', command=command).pack(side=LEFT)

    def _input_paths_ready(self) -> tuple[bool, list[str]]:
        missing: list[str] = []
        for label, var in (
            ('RED', self.red),
            ('CARGA', self.loads),
            ('BD_Equipo', self.equipment),
        ):
            p = Path(var.get().strip())
            if not var.get().strip() or not p.is_file():
                missing.append(label)
        return (not missing, missing)

    def _refresh_input_status(self, *, announce: bool = True, just_set: str | None = None) -> None:
        ready, missing = self._input_paths_ready()
        if just_set:
            name = Path(just_set).name
            self._append_log(f'Archivo asignado: {name}')
        if ready:
            self.files_ready.set('Los tres TXT están listos. Pulse «Cargar / listar alimentadores».')
            if announce:
                self.status.set('TXT listos — pulse «Cargar / listar alimentadores».')
        else:
            self.files_ready.set(f'Pendientes: {", ".join(missing)}.')
            if announce and just_set:
                self.status.set(f'Archivo cargado. Aún faltan: {", ".join(missing)}.')

    def _browse_red(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar RED_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.red.set(path)
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_loads(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar CARGA_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.loads.set(path)
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_equipment(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar BD_Equipo_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.equipment.set(path)
            self._invalidate_loaded_data()
            self._refresh_input_status(just_set=path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title='Carpeta de salida DGS')
        if path:
            self.out_dir.set(path)
            self._append_log(f'Carpeta de salida: {path}')
            self.status.set(f'Salida: {path}')

    def _browse_aliases(self) -> None:
        path = filedialog.askopenfilename(
            title='JSON de aliases de tipos de línea',
            filetypes=[('JSON', '*.json'), ('Todos', '*.*')],
        )
        if path:
            self.aliases.set(path)
            self._append_log(f'Aliases: {Path(path).name}')

    def _toggle_all(self) -> None:
        all_mode = self.convert_all.get()
        self.feeder_list.configure(selectmode='none' if all_mode else 'extended')
        if all_mode:
            self.feeder_list.selection_remove(*self.feeder_list.selection())
            n = len(self.feeder_list.get_children())
            msg = (
                f'Modo TODOS activo: se convertirán los {n} alimentadores cargados.'
                if n
                else 'Modo TODOS activo: cargue alimentadores y luego convierta.'
            )
            self.status.set(msg)
            self._append_log(msg)
        else:
            self.status.set('Modo selección: elija uno o varios alimentadores en la lista.')
            self._append_log('Modo selección manual (uno o varios).')

    def _on_feeder_select(self, _event=None) -> None:
        if self.convert_all.get() or self._busy:
            return
        n = len(self.feeder_list.selection())
        if n == 0:
            self.status.set('Sin selección — elija alimentadores o active «Convertir TODOS».')
        elif n == 1:
            name = self.feeder_list.item(self.feeder_list.selection()[0], 'values')[0]
            self.status.set(f'Seleccionado 1 alimentador: {name} — pulse Convertir a DGS')
        else:
            self.status.set(f'Seleccionados {n} alimentadores — pulse Convertir a DGS')

    def _on_feeder_double_click(self, _event=None) -> None:
        """Doble clic en una fila: convierte ese alimentador (o la selección actual)."""
        if self._busy or self.convert_all.get():
            return
        if not self.feeder_list.selection():
            return
        self._start_convert()

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
        if not busy:
            self.progress.configure(value=0)

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

        red = self.red.get().strip()
        loads = self.loads.get().strip()
        equipment = self.equipment.get().strip()

        # Nueva carga = ejecución limpia (sin restos de la anterior)
        self._reset_session(full=False, announce=False)

        self._set_busy(True)
        self.status.set('Leyendo TXT… espere, por favor.')
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        self._append_log('--- Carga de alimentadores (sesión limpia) ---')
        self._append_log(f'RED: {Path(red).name}')
        self._append_log(f'CARGA: {Path(loads).name}')
        self._append_log(f'BD_Equipo: {Path(equipment).name}')

        def worker() -> None:
            try:
                dataset = CymdistDataset.from_files(red, loads, equipment)
                self.root.after(0, lambda: self._on_load_done(True, dataset, None))
            except Exception as exc:
                self.root.after(0, lambda: self._on_load_done(False, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_load_done(self, ok: bool, dataset: CymdistDataset | None, error: str | None) -> None:
        self.progress.stop()
        self.progress.configure(mode='determinate', value=0)
        self._set_busy(False)
        if not ok or dataset is None:
            messagebox.showerror('Error al leer TXT', error or 'Error desconocido')
            self._append_log(f'ERROR lectura: {error}')
            self.status.set('Error al cargar TXT')
            return

        self._dataset = dataset
        self._clear_feeder_list()

        feeders = sorted(dataset.feeder_ids(), key=sort_key_feeder)
        for network_id in feeders:
            name = feeder_short_name(network_id)
            source = dataset.sources.get(network_id, {})
            sections = len(dataset.feeders[network_id])
            self.feeder_list.insert(
                '',
                END,
                iid=network_id,
                values=(name, network_id, source.get('DesiredVoltage', ''), sections),
            )
        msg = f'Carga terminada: {len(feeders)} alimentadores listos.'
        self.status.set(msg)
        self._append_log(msg)
        if self.convert_all.get():
            next_step = (
                f'Se leyeron {len(feeders)} alimentadores.\n\n'
                'Tiene activo «Convertir TODOS».\n'
                'Pulse «Convertir a DGS (seleccionados)» para generar todos.'
            )
        else:
            next_step = (
                f'Se leyeron {len(feeders)} alimentadores.\n\n'
                'Seleccione uno (clic), varios (Ctrl+clic) o todos,\n'
                'o marque «Convertir TODOS», y luego pulse\n'
                '«Convertir a DGS (seleccionados)».'
            )
        messagebox.showinfo('Archivos cargados', next_step)

    def _select_all_feeders(self) -> None:
        if self.convert_all.get():
            messagebox.showinfo(
                'Modo todos',
                'Ya está activo «Convertir TODOS». No hace falta seleccionar filas.',
            )
            return
        children = self.feeder_list.get_children()
        if not children:
            messagebox.showwarning('Sin datos', 'Primero pulse «Cargar / listar alimentadores».')
            return
        self.feeder_list.selection_set(children)
        self.status.set(f'Seleccionados todos: {len(children)} alimentadores.')
        self._append_log(f'Selección manual de todos: {len(children)}.')

    def _clear_feeders(self) -> None:
        self.feeder_list.selection_remove(*self.feeder_list.selection())
        if not self.convert_all.get():
            self.status.set('Selección limpiada.')

    def _open_out(self) -> None:
        path = Path(self.out_dir.get().strip())
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showinfo('Carpeta', f'{path}\n({exc})')

    def _start_convert(self) -> None:
        if self._busy:
            return
        if not self._require_inputs():
            return
        if self._dataset is None:
            messagebox.showinfo('Carga pendiente', 'Primero pulse «Cargar / listar alimentadores».')
            return

        all_feeders = self.convert_all.get()
        selected = list(self.feeder_list.selection())
        if not all_feeders and not selected:
            messagebox.showwarning(
                'Selección',
                'Seleccione al menos un alimentador (clic / Ctrl+clic),\n'
                'use «Seleccionar todos», o active «Convertir TODOS».',
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
        )
        dataset = self._dataset

        self._set_busy(True)
        self.status.set('Convirtiendo… no cierre la ventana.')
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
                manifest = convert_selection(dataset, selectors, out_dir, on_progress=on_progress, **kwargs)
                summary = manifest['summary']
                lines = [
                    f"Solicitados: {summary['requested']}",
                    f"OK: {summary['ok']}",
                    f"Fallidos: {summary['failed']}",
                    f"Manifiesto: {Path(out_dir) / 'batch_manifest.json'}",
                ]
                for item in manifest.get('feeders', []):
                    feeder = item.get('feeder') or item.get('network_id', '?')
                    if item.get('status') == 'ok':
                        lines.append(f"  OK {feeder} → {item.get('dgs', '')}")
                    else:
                        err = item.get('error') or 'error'
                        lines.append(f"  FAIL {feeder}: {err}")
                self.root.after(0, lambda: self._on_convert_done(True, '\n'.join(lines), summary, out_dir))
            except Exception:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._on_convert_done(False, tb, None, out_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _on_convert_done(self, ok: bool, detail: str, summary: dict | None, out_dir: str) -> None:
        self._set_busy(False)
        self._append_log(detail)
        self._append_log('--- Fin de conversión ---')
        if summary is not None:
            failed = summary.get('failed', 0)
            ok_n = summary.get('ok', 0)
            requested = summary.get('requested', 0)
            self.status.set(f'Conversión terminada — OK: {ok_n}  Fallidos: {failed}')
            self.progress.configure(value=self.progress['maximum'] or 1)
            short = (
                f'Conversión finalizada.\n\n'
                f'Solicitados: {requested}\n'
                f'OK: {ok_n}\n'
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

    def _on_close(self) -> None:
        # Al cerrar: sesión a cero; nada de la ejecución queda para la próxima apertura.
        self._reset_session(full=True, announce=False)
        self.root.destroy()


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
