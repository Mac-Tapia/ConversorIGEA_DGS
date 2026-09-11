"""Interfaz gráfica para convertir TXT IGEA/CYMDIST → DGS PowerFactory."""

from __future__ import annotations

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
from . import __version__


CRS_PRESETS = (
    'EPSG:32718',  # UTM 18S (Ica / costa centro-sur Perú)
    'EPSG:32717',  # UTM 17S
    'EPSG:32719',  # UTM 19S
    'EPSG:4326',   # WGS84 (si CoordX/Y ya están en lon/lat)
)


class ConverterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f'Conversor IGEA/CYMDIST → DGS  v{__version__}')
        self.root.minsize(780, 640)
        self.root.geometry('900x700')

        self.red = StringVar()
        self.loads = StringVar()
        self.equipment = StringVar()
        self.out_dir = StringVar(value=str(Path.cwd() / 'output' / 'gui'))
        self.aliases = StringVar()
        self.source_crs = StringVar(value='EPSG:32718')
        self.target_crs = StringVar(value='EPSG:4326')
        self.include_geography = BooleanVar(value=True)
        self.strict = BooleanVar(value=True)
        self.convert_all = BooleanVar(value=False)
        self._dataset: CymdistDataset | None = None
        self._busy = False

        self._build()

    def _build(self) -> None:
        pad = {'padx': 10, 'pady': 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill=BOTH, expand=True)

        files = ttk.LabelFrame(frm, text='Archivos de entrada (TXT IGEA/CYMDIST)', padding=10)
        files.pack(fill=X, **pad)
        self._file_row(files, 'RED_*.txt', self.red, self._browse_red)
        self._file_row(files, 'CARGA_*.txt', self.loads, self._browse_loads)
        self._file_row(files, 'BD_Equipo_*.txt (catálogo de equipos)', self.equipment, self._browse_equipment)

        opts = ttk.LabelFrame(frm, text='Salida y opciones', padding=10)
        opts.pack(fill=X, **pad)
        self._file_row(opts, 'Carpeta de salida', self.out_dir, self._browse_out, directory=True)
        self._file_row(opts, 'Aliases de tipos (JSON, opcional)', self.aliases, self._browse_aliases)

        crs = ttk.Frame(opts)
        crs.pack(fill=X, pady=4)
        ttk.Label(crs, text='CRS origen (CoordX/Y):').pack(side=LEFT)
        ttk.Combobox(crs, textvariable=self.source_crs, values=CRS_PRESETS, width=16).pack(side=LEFT, padx=6)
        ttk.Label(crs, text='CRS destino GPS:').pack(side=LEFT, padx=(12, 0))
        ttk.Combobox(crs, textvariable=self.target_crs, values=('EPSG:4326',), width=16).pack(side=LEFT, padx=6)

        flags = ttk.Frame(opts)
        flags.pack(fill=X, pady=4)
        ttk.Checkbutton(flags, text='Georreferenciación (GPS + diagrama)', variable=self.include_geography).pack(side=LEFT)
        ttk.Checkbutton(flags, text='Modo estricto (recomendado)', variable=self.strict).pack(side=LEFT, padx=16)
        ttk.Checkbutton(flags, text='Convertir todos los alimentadores', variable=self.convert_all, command=self._toggle_all).pack(side=LEFT)

        feeders = ttk.LabelFrame(frm, text='Alimentadores', padding=10)
        feeders.pack(fill=BOTH, expand=True, **pad)
        btns = ttk.Frame(feeders)
        btns.pack(fill=X)
        ttk.Button(btns, text='Cargar / listar alimentadores', command=self._load_feeders).pack(side=LEFT)
        ttk.Button(btns, text='Seleccionar todos', command=self._select_all_feeders).pack(side=LEFT, padx=6)
        ttk.Button(btns, text='Limpiar selección', command=self._clear_feeders).pack(side=LEFT)

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

        actions = ttk.Frame(frm)
        actions.pack(fill=X, **pad)
        self.convert_btn = ttk.Button(actions, text='Convertir a DGS', command=self._start_convert)
        self.convert_btn.pack(side=LEFT)
        ttk.Button(actions, text='Abrir carpeta de salida', command=self._open_out).pack(side=LEFT, padx=8)
        self.status = StringVar(value='Seleccione los tres TXT y pulse «Cargar / listar alimentadores».')
        ttk.Label(actions, textvariable=self.status).pack(side=LEFT, padx=12)

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

    def _browse_red(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar RED_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.red.set(path)

    def _browse_loads(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar CARGA_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.loads.set(path)

    def _browse_equipment(self) -> None:
        path = filedialog.askopenfilename(
            title='Seleccionar BD_Equipo_*.txt',
            filetypes=[('TXT IGEA/CYMDIST', '*.txt'), ('Todos', '*.*')],
        )
        if path:
            self.equipment.set(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(title='Carpeta de salida DGS')
        if path:
            self.out_dir.set(path)

    def _browse_aliases(self) -> None:
        path = filedialog.askopenfilename(
            title='JSON de aliases de tipos de línea',
            filetypes=[('JSON', '*.json'), ('Todos', '*.*')],
        )
        if path:
            self.aliases.set(path)

    def _toggle_all(self) -> None:
        self.feeder_list.configure(selectmode='none' if self.convert_all.get() else 'extended')
        if self.convert_all.get():
            self.feeder_list.selection_remove(*self.feeder_list.selection())

    def _append_log(self, text: str) -> None:
        self.log.configure(state='normal')
        self.log.insert(END, text + '\n')
        self.log.see(END)
        self.log.configure(state='disabled')

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.convert_btn.configure(state='disabled' if busy else 'normal')

    def _require_inputs(self) -> bool:
        missing = []
        for label, var in (
            ('RED', self.red),
            ('CARGA', self.loads),
            ('BD_Equipo', self.equipment),
        ):
            p = Path(var.get().strip())
            if not var.get().strip() or not p.is_file():
                missing.append(label)
        if missing:
            messagebox.showerror('Archivos faltantes', f'Verifique que existan: {", ".join(missing)}')
            return False
        if not self.out_dir.get().strip():
            messagebox.showerror('Salida', 'Indique una carpeta de salida.')
            return False
        return True

    def _load_feeders(self) -> None:
        if self._busy:
            return
        if not self._require_inputs():
            return
        try:
            self._dataset = CymdistDataset.from_files(
                self.red.get().strip(),
                self.loads.get().strip(),
                self.equipment.get().strip(),
            )
        except Exception as exc:
            messagebox.showerror('Error al leer TXT', str(exc))
            self._append_log(f'ERROR lectura: {exc}')
            return

        for item in self.feeder_list.get_children():
            self.feeder_list.delete(item)

        feeders = sorted(self._dataset.feeder_ids(), key=lambda x: x.rsplit('_', 1)[-1])
        for network_id in feeders:
            name = network_id.rsplit('_', 1)[-1]
            source = self._dataset.sources.get(network_id, {})
            sections = len(self._dataset.feeders[network_id])
            self.feeder_list.insert(
                '',
                END,
                iid=network_id,
                values=(name, network_id, source.get('DesiredVoltage', ''), sections),
            )
        msg = f'Cargados {len(feeders)} alimentadores.'
        self.status.set(msg)
        self._append_log(msg)

    def _select_all_feeders(self) -> None:
        if self.convert_all.get():
            return
        self.feeder_list.selection_set(self.feeder_list.get_children())

    def _clear_feeders(self) -> None:
        self.feeder_list.selection_remove(*self.feeder_list.selection())

    def _open_out(self) -> None:
        path = Path(self.out_dir.get().strip())
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showinfo('Carpeta', f'{path}\n({exc})')

    def _start_convert(self) -> None:
        if self._busy:
            return
        if not self._require_inputs():
            return
        if self._dataset is None:
            self._load_feeders()
            if self._dataset is None:
                return

        all_feeders = self.convert_all.get()
        selected = list(self.feeder_list.selection())
        if not all_feeders and not selected:
            messagebox.showwarning('Selección', 'Seleccione al menos un alimentador o active «Convertir todos».')
            return

        aliases_path = self.aliases.get().strip() or None
        try:
            from .batch import convert_selection, load_aliases

            aliases = load_aliases(aliases_path)
        except Exception as exc:
            messagebox.showerror('Aliases / dependencias', str(exc))
            return

        if self.include_geography.get():
            try:
                import pyproj  # noqa: F401
            except ImportError:
                messagebox.showerror(
                    'Falta pyproj',
                    'Para georreferenciación instale pyproj:\n  pip install pyproj\n'
                    'O desactive «Georreferenciación» para convertir sin GPS.',
                )
                return

        out_dir = self.out_dir.get().strip()
        selectors = [self.feeder_list.item(i, 'values')[0] for i in selected] if not all_feeders else None
        kwargs = dict(
            all_feeders=all_feeders,
            aliases=aliases,
            strict=self.strict.get(),
            include_geography=self.include_geography.get(),
            source_crs=self.source_crs.get().strip() or 'EPSG:32718',
            target_crs=self.target_crs.get().strip() or 'EPSG:4326',
        )

        self._set_busy(True)
        self.status.set('Convirtiendo…')
        self._append_log('--- Inicio de conversión ---')

        def worker() -> None:
            try:
                manifest = convert_selection(self._dataset, selectors, out_dir, **kwargs)
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
                        lines.append(f"  OK {feeder}")
                    else:
                        err = item.get('error') or 'error'
                        lines.append(f"  FAIL {feeder}: {err}")
                self.root.after(0, lambda: self._on_convert_done(True, '\n'.join(lines), summary))
            except Exception:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._on_convert_done(False, tb, None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_convert_done(self, ok: bool, detail: str, summary: dict | None) -> None:
        self._set_busy(False)
        self._append_log(detail)
        if summary is not None:
            failed = summary.get('failed', 0)
            self.status.set(f"Listo — OK: {summary.get('ok', 0)}  Fallidos: {failed}")
            if failed:
                messagebox.showwarning('Conversión parcial', detail)
            else:
                messagebox.showinfo('Conversión OK', detail)
        else:
            self.status.set('Error en la conversión')
            messagebox.showerror('Error', detail)


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
