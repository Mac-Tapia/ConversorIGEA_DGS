"""Los formatos del Anexo 5 de la Guía del VNR (RCD 232-2017-OS/CD) en un libro Excel: una hoja por formato con sus
filas, su cantidad, su costo (subtotal / cantidad) y su subtotal en miles, y las notas (1) y (2) del formato
(spec 108, RF-24). Los totales van como fórmulas; una fila con huecos lleva la lista de partidas sin costo."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...aplicacion.vad.vnr_guia import Formato


def escribir_formatos(formatos: Iterable[Formato], ruta: Path | str, *, notas: Iterable[str] = ()) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    ruta = Path(ruta)
    libro = Workbook()
    libro.remove(libro.active)
    for f in formatos:
        h = libro.create_sheet(f.codigo)
        h.append([f'Formato {f.codigo}', f.titulo])
        h.append(['Ámbito', f.ambito or '—', 'Moneda de los costos', f.moneda or 'la de la fuente de costos'])
        h.append([])
        h.append(['Grupo', 'Ítem', 'Descripción', 'Unidad', 'Cantidad (1)', 'Costo (2)', 'Subtotal (miles)',
                  'Partidas sin costo'])
        for c in h[4]:
            c.font = Font(bold=True)
        primera = h.max_row + 1
        for fila in f.filas:
            h.append([fila.grupo, fila.item, fila.descripcion, fila.unidad, fila.cantidad, fila.costo_unitario,
                      fila.subtotal_miles, '; '.join(fila.huecos)])
        ultima = h.max_row
        h.append(['', '', 'Total', '', '', '', f'=SUM(G{primera}:G{ultima})' if f.total_miles is not None else None,
                  'sin total: hay partidas sin costo' if f.total_miles is None else ''])
        if f.sin_fila:
            h.append(['', '', 'Códigos sin fila en el formato', '', '', '', '', ', '.join(f.sin_fila)])
        h.append([])
        for n in notas:
            h.append([n])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
    return ruta
