"""Informes en Word del estudio VAD: Resultados Relevantes (108:RF-14) e Informe del Estudio (108:RF-15).

La forma de cada informe sale del registro, no del código:

* ``vad.anexo3.apartados``: los apartados del Informe de Resultados Relevantes (anexo 3 del TdR);
* ``vad.informe_estudio.estructura``: los apartados y subapartados del Informe del Estudio (numeral 9).

El contenido lo da el estudio, apartado por apartado (clave ``"<n>"`` para un apartado y ``"<n>.<letra>"`` para un
subapartado, con las letras en el orden del registro), como párrafos y :class:`Cifra`. **Cada cifra sale del estudio
con su origen o queda como hueco nombrado**: una cifra con valor y sin origen se rechaza, y una sin valor se escribe
resaltada como hueco. Un apartado sin contenido también es un hueco nombrado. Contenido para un apartado que el
registro no tiene se rechaza.

El PDF integrado del numeral 9 se pide al exportador del proyecto (``informe_docx.exportar_pdf``, con Word). Si no
sale, el Word queda hecho y se dice el motivo: nunca se oculta (063:RF-42).
"""
from __future__ import annotations

import math
import os
import string
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, Union

from ..registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from . import VadError

ExportarPdf = Callable[[Path], 'tuple[Path | None, str]']


@dataclass(frozen=True)
class Cifra:
    nombre: str
    valor: float | str | None
    unidad: str = ''
    #: De qué cálculo o tabla del estudio sale (obligatorio si hay valor).
    origen: str = ''

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise VadError('una cifra del informe necesita su nombre')
        if self.valor is None:
            return
        if isinstance(self.valor, bool) or not isinstance(self.valor, (int, float, str)) \
                or (isinstance(self.valor, float) and not math.isfinite(self.valor)):
            raise VadError(f'la cifra «{self.nombre}» tiene un valor no admitido: {self.valor!r}')
        if not self.origen.strip():
            raise VadError(f'la cifra «{self.nombre}» no dice de qué cálculo o tabla del estudio sale (origen)')


Bloque = Union[str, Cifra]


@dataclass(frozen=True)
class Apartado:
    clave: str
    titulo: str
    nivel: int


@dataclass(frozen=True)
class InformeVad:
    docx: Path
    apartados: tuple[Apartado, ...]
    huecos: tuple[str, ...]
    pdf: Path | None = None
    motivo_pdf: str = ''
    regla: str = ''
    acto: str = ''


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None) -> ReglaVigente:
    try:
        return registro.regla(clave, fecha)
    except RegistroError as exc:
        raise VadError(f'el registro no trae {clave}: {exc}') from exc


def _texto(d: Any, campo: str, clave: str) -> str:
    v = d.get(campo) if isinstance(d, Mapping) else None
    if not isinstance(v, str) or not v.strip():
        raise VadError(f'{clave}: un apartado del registro no trae «{campo}»: {d!r}')
    return v.strip()


def apartados(registro: RegistroNormativo, clave: str, fecha: str | None = None) -> tuple[list[Apartado], ReglaVigente]:
    """Los apartados (y subapartados) de la regla ``clave``, en el orden del registro."""
    rv = _regla(registro, clave, fecha)
    lista = rv.regla.valor
    if not isinstance(lista, list) or not lista:
        raise VadError(f'{clave} tiene que ser una lista no vacía de apartados')
    out: list[Apartado] = []
    for d in lista:
        numero, titulo = _texto(d, 'numero', clave), _texto(d, 'titulo', clave)
        out.append(Apartado(numero, f'{numero}. {titulo}', 1))
        subs = d.get('subapartados') or []
        if not isinstance(subs, list) or len(subs) > len(string.ascii_lowercase):
            raise VadError(f'{clave}: los subapartados de {numero} tienen que ser una lista de hasta 26 títulos')
        for letra, sub in zip(string.ascii_lowercase, subs):
            if not isinstance(sub, str) or not sub.strip():
                raise VadError(f'{clave}: un subapartado de {numero} no tiene título')
            out.append(Apartado(f'{numero}.{letra}', f'{letra}. {sub.strip()}', 2))
    claves = [a.clave for a in out]
    if len(set(claves)) != len(claves):
        raise VadError(f'{clave}: apartados repetidos en el registro')
    return out, rv


def _guardar(documento: Any, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.csg-', suffix='.docx', dir=destino.parent)
    os.close(fd)
    try:
        documento.save(tmp)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _escribir(registro: RegistroNormativo, clave: str, titulo: str, contenido: Mapping[str, Sequence[Bloque]],
              destino: Path | str, empresa: str, fecha: str | None) -> InformeVad:
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    if not str(empresa or '').strip():
        raise VadError('el informe necesita la empresa del estudio (del perfil); no se supone ninguna')
    lista, rv = apartados(registro, clave, fecha)
    conocidas = {a.clave for a in lista}
    extra = sorted(set(contenido) - conocidas)
    if extra:
        raise VadError(f'contenido para apartados que el registro no tiene ({clave}): {", ".join(extra)}')
    for k, bloques in contenido.items():
        if isinstance(bloques, (str, Cifra)) or not all(isinstance(b, (str, Cifra)) for b in bloques):
            raise VadError(f'el contenido del apartado {k} tiene que ser una lista de párrafos y cifras')
    con_hijos = {a.clave.split('.')[0] for a in lista if a.nivel == 2}
    doc = Document()
    doc.add_heading(titulo, level=0)
    doc.add_paragraph(f'{empresa.strip()}. Estructura según {rv.norma.acto} ({rv.regla.articulo_o_anexo}, líneas '
                      f'{rv.regla.lineas}).')
    huecos: list[str] = []

    def hueco(parrafo: Any, texto: str) -> None:
        run = parrafo.add_run(f'[{texto}]')
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW

    for a in lista:
        doc.add_heading(a.titulo, level=a.nivel)
        bloques = list(contenido.get(a.clave) or ())
        if not bloques:
            if a.nivel == 1 and a.clave in con_hijos:
                continue  # el contenido va en sus subapartados, que se comprueban uno a uno
            hueco(doc.add_paragraph(), f'Hueco: «{a.titulo}» sin contenido del estudio')
            huecos.append(f'{a.clave} {a.titulo}: sin contenido')
            continue
        for b in bloques:
            p = doc.add_paragraph()
            if isinstance(b, str):
                p.add_run(b)
            elif b.valor is None:
                p.add_run(f'{b.nombre}: ')
                hueco(p, f'Hueco: {b.nombre}{f" ({b.unidad})" if b.unidad else ""}')
                huecos.append(f'{a.clave} {a.titulo}: la cifra «{b.nombre}» no sale del estudio')
            else:
                p.add_run(f'{b.nombre}: {b.valor}{f" {b.unidad}" if b.unidad else ""} (origen: {b.origen})')
    destino = Path(destino)
    _guardar(doc, destino)
    return InformeVad(destino, tuple(lista), tuple(huecos), regla=rv.regla.clave, acto=rv.norma.acto)


def escribir_resultados_relevantes(registro: RegistroNormativo, contenido: Mapping[str, Sequence[Bloque]],
                                   destino: Path | str, *, empresa: str, fecha: str | None = None) -> InformeVad:
    """El Informe de Resultados Relevantes con los apartados del anexo 3 registrado (108:RF-14)."""
    return _escribir(registro, 'vad.anexo3.apartados', 'Informe de los Resultados Relevantes del Estudio de Costos '
                     'del VAD', contenido, destino, empresa, fecha)


def escribir_informe_estudio(registro: RegistroNormativo, contenido: Mapping[str, Sequence[Bloque]],
                             destino: Path | str, *, empresa: str, exportar_pdf: ExportarPdf | None = None,
                             fecha: str | None = None) -> InformeVad:
    """El Informe del Estudio con la estructura del numeral 9 registrada, en Word y en PDF integrado (108:RF-15)."""
    informe = _escribir(registro, 'vad.informe_estudio.estructura', 'Informe del Estudio de Costos del VAD',
                        contenido, destino, empresa, fecha)
    if exportar_pdf is None:
        from ..informe_docx import exportar_pdf as exportar_pdf_word
        exportar_pdf = exportar_pdf_word
    pdf, motivo = exportar_pdf(informe.docx)
    if pdf is None and not motivo:
        motivo = 'el exportador no generó el PDF y no dijo por qué'
    return InformeVad(informe.docx, informe.apartados, informe.huecos, pdf, '' if pdf else motivo, informe.regla,
                      informe.acto)
