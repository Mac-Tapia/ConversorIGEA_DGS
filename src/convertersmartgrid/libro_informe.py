"""El libro Excel de cada informe, relleno a partir del modelo de la empresa (spec 066).

El modelo tiene imágenes, un gráfico, vínculos externos y comentarios: openpyxl los pierde al guardar, así que el libro
lo escribe Excel con un plan de celdas. Las hojas y las celdas vienen del perfil de la empresa; sin esa sección no
hay libro (066:RF-2), porque el libro de una empresa no vale para otra.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .informes import _fecha_larga

#: Tolerancia entre el importe del libro y el del informe, en soles (066:RF-10).
TOLERANCIA_SOLES = 1.0
ERRORES_DE_FORMULA = ('#REF!', '#DIV/0!', '#VALUE!', '#NAME?', '#N/A', '#NUM!', '#NULL!')


@dataclass(frozen=True)
class ConfigLibro:
    """El plano del libro, tal como lo declara el perfil de la empresa (066:RF-4)."""

    modelo: Path | None
    celdas: Mapping[str, Any]
    textos: Mapping[str, str] = field(default_factory=dict)
    formulas: Mapping[str, str] = field(default_factory=dict)
    bloque_hoja: str = ''
    bloque: Mapping[str, str] = field(default_factory=dict)
    desplazamiento: int = 0
    imagenes: Mapping[str, str] = field(default_factory=dict)
    ancho_imagen: float = 420.0
    vaciar: Sequence[str] = ()
    sin_dato: Mapping[str, Sequence[str]] = field(default_factory=dict)
    borrar_hojas: Sequence[str] = ()
    sin_imagenes: Sequence[str] = ()
    catalogo: Sequence[str] = ()
    prohibidos: Sequence[str] = ()
    control: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def de_perfil(cls, datos: Mapping[str, Any], raiz: Path) -> 'ConfigLibro | None':
        """El plano del perfil, o ``None`` si la empresa no tiene libro (066:RF-2)."""
        informes = datos.get('informes') or {}
        d = informes.get('libro_informe')
        if not isinstance(d, Mapping):
            return None
        modelo = informes.get('modelo_libro')
        return cls(modelo=Path(raiz) / modelo if modelo else None, celdas=d.get('celdas') or {},
                   textos=d.get('textos') or {}, formulas=d.get('formulas') or {},
                   bloque_hoja=d.get('bloque_hoja') or '', bloque=d.get('bloque') or {},
                   desplazamiento=int(d.get('desplazamiento') or 0), imagenes=d.get('imagenes') or {},
                   ancho_imagen=float(d.get('ancho_imagen') or 420.0), vaciar=tuple(d.get('vaciar') or ()),
                   sin_dato=d.get('sin_dato') or {}, borrar_hojas=tuple(d.get('borrar_hojas') or ()),
                   sin_imagenes=tuple(d.get('sin_imagenes') or ()), catalogo=tuple(d.get('catalogo') or ()),
                   prohibidos=tuple(d.get('prohibidos') or ()), control=d.get('control') or {})


@dataclass(frozen=True)
class ResultadoLibro:
    """El libro generado o el motivo, con lo que quedó vacío y lo que no cuadra."""

    ruta: Path | None
    motivo: str = ''
    huecos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()


def _bajar(celda: str, filas: int) -> str:
    """La misma celda ``filas`` más abajo: el modelo repite el bloque del estado proyectado."""
    return re.sub(r'(\d+)', lambda m: str(int(m.group(1)) + filas), celda)


def _del_bloque(caso: Mapping[str, Any] | None, perdidas: Mapping[str, Any] | None) -> dict[str, Any]:
    """Los valores de un estado para el bloque de resultados del libro."""
    if not caso or not caso.get('converge'):
        return {}
    fuente, perd = caso.get('fuente') or {}, caso.get('perdidas') or {}
    kw, kvar = fuente.get('kw'), fuente.get('kvar')
    out: dict[str, Any] = {'kw': kw, 'kvar': kvar, 'perdidas_kw': perd.get('kw'), 'perdidas_kvar': perd.get('kvar')}
    if kw is not None and kvar is not None:
        kva = math.hypot(kw, kvar)
        out.update(kva=kva, fp_pct=abs(kw) / kva * 100 if kva else None)
    if kw is not None and perd.get('kw') is not None:
        out['carga_kw'] = kw - perd['kw']
    if perd.get('kw') is not None and perd.get('kvar') is not None:
        s = math.hypot(perd['kw'], perd['kvar'])
        out.update(perdidas_kva=s, perdidas_fp=abs(perd['kw']) / s * 100 if s else None)
    minima = caso.get('tension_min') or {}
    sobre = caso.get('cargabilidad_max') or {}
    alta = caso.get('tension_max') or {}
    for fase in 'ABC':
        e = minima.get(fase) or minima.get('trifásica') or {}
        f = fase.lower()
        out.update({f'sub_{f}': e.get('valor'), f'sub_donde_{f}': e.get('donde'),
                    f'sobrecarga_{f}': sobre['valor'] / 100 if sobre.get('valor') is not None else None,
                    f'sobrecarga_donde_{f}': sobre.get('donde'),
                    f'sobretension_{f}': alta.get('valor'), f'sobretension_donde_{f}': alta.get('donde')})
    out.update(sub_conteo=caso.get('nodos_fuera'), sobrecarga_conteo=caso.get('tramos_sobre'),
               kw_fuente=kw, kvar_fuente=kvar, kva_fuente=out.get('kva'), fp_fuente=out.get('fp_pct'),
               kw_produccion=kw, kvar_produccion=kvar, kva_produccion=out.get('kva'), fp_produccion=out.get('fp_pct'),
               perdidas_total_kw=perd.get('kw'))
    if perdidas:
        out['perdidas_mwh'] = perdidas['perdidas_kwh'] / 1000 if perdidas.get('perdidas_kwh') is not None else None
        if perdidas.get('energia_kwh') and perdidas.get('maxima_kw'):
            out['fc'] = perdidas['energia_kwh'] / (perdidas['maxima_kw'] * 8760)
    return out


def _proyectado(r: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """El estado con obras: en el de factibilidad, su caso; en el de estudio, la última etapa."""
    if r.get('proyectado'):
        return r['proyectado']
    etapas = r.get('etapas') or []
    return (etapas[-1].get('caso') if etapas else None)


def _tension_de_despacho(bloque: dict[str, Any], kv: float | None) -> None:
    """Tensión y corriente en la fuente. La máxima de la red radial es la de su cabecera."""
    u, kva = bloque.get('sobretension_a'), bloque.get('kva')
    if u is None or not kv:
        return
    kvll = u * kv
    bloque.update(vpu=u, kvll=kvll, kvln=kvll / math.sqrt(3))
    if kva is not None:
        bloque['i_a'] = kva / (math.sqrt(3) * kvll)


def valores_del_informe(r: Mapping[str, Any], conclusion: str = '') -> dict[str, Any]:
    """Del JSON del informe a los valores que el perfil coloca en celdas (066:RF-1, 066:RF-12)."""
    s = r.get('solicitud') or {}
    libro = r.get('libro') or {}
    alimentador = s.get('alimentador') or next(iter(r.get('alimentadores') or ()), None)
    potencia, actual = s.get('potencia_kw'), s.get('potencia_actual_kw')
    incremento = potencia - actual if potencia is not None and actual is not None else potencia
    kv = s.get('tension_kv') or (r.get('punto_diseno') or {}).get('kv_ll')
    return {'cliente': s.get('cliente'), 'ubicacion': s.get('ubicacion'), 'tipo_solicitud': s.get('tipo_solicitud'),
            'potencia_kw': potencia, 'incremento': f'{incremento:g} kW' if incremento is not None else None,
            # En letras: la hoja la encadena en un texto, y como fecha de Excel saldría «El 45965».
            'fecha_solicitud': _fecha_larga(date.fromisoformat(str(s['fecha_solicitud']))) if s.get('fecha_solicitud') else None,
            'alimentador': alimentador,
            'set_nombre': s.get('set_nombre'), 'tension_kv': s.get('tension_kv'),
            'transformador': s.get('transformador'), 'expediente': s.get('expediente'),
            'precio_compra': libro.get('precio_compra'), 'conclusion': conclusion or None, '_kv': kv}


def plan_del_libro(config: ConfigLibro, r: Mapping[str, Any], *, destino: Path, conclusion: str = '',
                   imagenes: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Lo que Excel debe hacer con el modelo, sin tocar Excel (066:RF-4, 066:RF-5, 066:RF-6, 066:RF-8)."""
    valores = valores_del_informe(r, conclusion)
    escribir: list[dict[str, Any]] = []
    vaciar: list[str] = list(config.vaciar)
    huecos: list[str] = []

    def colocar(destinos: Any, valor: Any, nombre: str) -> None:
        for d in ([destinos] if isinstance(destinos, str) else destinos):
            if valor in (None, ''):
                vaciar.append(d)
            else:
                escribir.append({'celda': d, 'valor': valor})
        if valor in (None, ''):
            huecos.append(nombre)

    for nombre, destinos in config.celdas.items():
        colocar(destinos, valores.get(nombre), nombre)
    for celda, texto in config.textos.items():
        colocar(celda, texto.format(alimentador=valores['alimentador'] or ''), celda)

    perdidas = r.get('perdidas') or {}
    for estado, caso, filas in (('actual', r.get('actual'), 0), ('proyectado', _proyectado(r), config.desplazamiento)):
        bloque = _del_bloque(caso, perdidas.get(estado))
        _tension_de_despacho(bloque, valores['_kv'])
        for nombre, celda in config.bloque.items():
            colocar(f'{config.bloque_hoja}!{_bajar(celda, filas)}', bloque.get(nombre), f'{nombre} del estado {estado}')

    datos_de_equipos = r.get('datos_sin_dato') or {}
    for nombre, destinos in config.sin_dato.items():
        if datos_de_equipos.get(nombre):                                              # 066:RF-13
            escribir += [{'celda': celda, 'valor': valor} for celda, valor in datos_de_equipos[nombre].items()]
            continue
        vaciar.extend(destinos)
        huecos.append(nombre)

    fotos = []
    for clave, celda in config.imagenes.items():
        estado, modo = clave.split('.')
        ruta = ((imagenes or {}).get(estado) or {}).get(modo)
        if ruta:
            fotos.append({'celda': celda, 'ruta': str(Path(ruta).resolve())})
        else:
            huecos.append(f'imagen de {modo} del estado {estado}')
    return {'modelo': str(Path(config.modelo).resolve()) if config.modelo else '', 'destino': str(Path(destino).resolve()),
            'borrar_hojas': list(config.borrar_hojas), 'sin_imagenes': list(config.sin_imagenes),
            'vaciar': list(dict.fromkeys(vaciar)), 'escribir': escribir,
            'formulas': [{'celda': c, 'formula': f} for c, f in config.formulas.items()], 'imagenes': fotos,
            'ancho_imagen': config.ancho_imagen, 'huecos': list(dict.fromkeys(huecos))}


#: Aplica el plan con Excel. ``Value2`` escribe sin formato; ``MergeArea`` porque el modelo combina celdas.
_GUION_EXCEL = r"""
$ErrorActionPreference = 'Stop'
$p = Get-Content -Raw -Encoding UTF8 -LiteralPath '{plan}' | ConvertFrom-Json
$x = New-Object -ComObject Excel.Application
$x.Visible = $false; $x.DisplayAlerts = $false; $x.AskToUpdateLinks = $false
function Celda($w, $ref) {{ $i = $ref.LastIndexOf('!'); $w.Worksheets.Item($ref.Substring(0, $i)).Range($ref.Substring($i + 1)) }}
try {{
  $w = $x.Workbooks.Open($p.modelo, 0, $false)
  foreach ($h in $p.borrar_hojas) {{ $w.Worksheets.Item($h).Delete() | Out-Null }}
  $l = $w.LinkSources(1)
  if ($l) {{ foreach ($k in $l) {{ $w.BreakLink($k, 1) | Out-Null }} }}
  foreach ($n in @($w.Names)) {{ if ($n.RefersTo -match '#REF|\[') {{ $n.Delete() | Out-Null }} }}
  foreach ($s in @($w.Worksheets)) {{ $s.Cells.ClearComments() | Out-Null }}
  foreach ($h in $p.sin_imagenes) {{
    $s = $w.Worksheets.Item($h)
    foreach ($f in @($s.Shapes)) {{ if ($f.Type -eq 13) {{ $f.Delete() | Out-Null }} }}
  }}
  foreach ($ref in $p.vaciar) {{ foreach ($c in @(Celda $w $ref)) {{ foreach ($u in @($c.Cells)) {{ $u.MergeArea.ClearContents() | Out-Null }} }} }}
  # ConvertFrom-Json da Decimal y Excel no lo acepta: un número va como double.
  foreach ($e in $p.escribir) {{
    $v = $e.valor; if ($v -isnot [string]) {{ $v = [double]$v }}
    # Sin pasar por el adaptador de PowerShell: con WPS (responde a Excel.Application) tipa Value2 como texto.
    $u = (Celda $w $e.celda).MergeArea.Cells.Item(1, 1)
    [void][System.__ComObject].InvokeMember('Value2', [Reflection.BindingFlags]::SetProperty, $null, $u, [object[]]@($v))
  }}
  foreach ($e in $p.formulas) {{ (Celda $w $e.celda).Formula = $e.formula }}
  foreach ($e in $p.imagenes) {{
    $c = Celda $w $e.celda
    $f = $c.Worksheet.Shapes.AddPicture($e.ruta, 0, -1, $c.Left, $c.Top, -1, -1)
    $f.LockAspectRatio = -1; $f.Width = $p.ancho_imagen
  }}
  $x.CalculateFull()
  $w.SaveAs($p.destino, 51)
  $w.Close($false)
}} finally {{ $x.Quit() }}
"""


def rellenar_con_excel(plan: Mapping[str, Any], *, ejecutar: Callable[[str], Any] | None = None) -> tuple[Path | None, str]:
    """Genera el libro con Excel. Sin Excel se dice el motivo y el Word sigue (066:RF-9)."""
    destino = Path(plan['destino'])
    inicio = time.time() - 2
    with tempfile.TemporaryDirectory() as carpeta:
        fichero = Path(carpeta) / 'plan.json'
        fichero.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        orden = _GUION_EXCEL.format(plan=fichero)
        correr = ejecutar or (lambda c: subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', c], capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=300, check=False))
        try:
            hecho = correr(orden)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f'no se pudo abrir Excel: {exc}'
    # Como en el PDF (063:RF-50): lo que vale es el fichero de esta vez, aunque Excel caiga al cerrarse.
    if destino.is_file() and destino.stat().st_mtime >= inicio and destino.stat().st_size > 0:
        return destino, ''
    return None, str(getattr(hecho, 'stderr', '') or 'Excel no generó el libro').strip()[:300]


def comprobar_libro(config: ConfigLibro, ruta: Path, r: Mapping[str, Any]) -> list[str]:
    """Lo que no debe quedar en el libro y los importes que deben cuadrar (066:RF-7, 066:RF-10)."""
    import openpyxl

    avisos: list[str] = []
    libro = openpyxl.load_workbook(ruta, data_only=True)
    prohibidos = [p.casefold() for p in config.prohibidos]
    for hoja in libro.worksheets:
        if hoja.title in config.catalogo:
            continue
        for fila in hoja.iter_rows():
            for c in fila:
                if not isinstance(c.value, str):
                    continue
                texto = c.value.casefold()
                if any(p in texto for p in prohibidos):
                    avisos.append(f'{hoja.title}!{c.coordinate} conserva datos del modelo: {c.value[:60]}')
                elif c.value in ERRORES_DE_FORMULA:
                    avisos.append(f'{hoja.title}!{c.coordinate} da {c.value}')
    perdidas = r.get('perdidas') or {}
    for estado, ref in config.control.items():
        esperado = (perdidas.get(estado) or {}).get('no_reconocida_soles')
        hoja, celda = ref.rsplit('!', 1)
        valor = libro[hoja][celda].value if hoja in libro.sheetnames else None
        if esperado is not None and (not isinstance(valor, (int, float)) or abs(valor - esperado) > TOLERANCIA_SOLES):
            avisos.append(f'{ref} da {valor} y el informe {esperado:.2f} S/. en el estado {estado}')
    return avisos


def conclusiones_del_word(docx: Path) -> str:
    """El texto de las conclusiones del informe: el libro dice lo mismo que el Word."""
    import docx as python_docx

    parrafos = [p.text.strip() for p in python_docx.Document(str(docx)).paragraphs if p.text.strip()]
    inicio = next((i for i, t in enumerate(parrafos) if t.upper().startswith('3. CONCLUSIONES')), None)
    return ' '.join(parrafos[inicio + 1:]) if inicio is not None else ''


def generar_libro(config: ConfigLibro, docx: Path, r: Mapping[str, Any],
                  imagenes: Mapping[str, Mapping[str, Any]] | None = None, *,
                  ejecutar: Callable[[str], Any] | None = None) -> ResultadoLibro:
    """El libro junto al Word, comprobado (066:RF-1)."""
    if config.modelo is None or not Path(config.modelo).is_file():
        return ResultadoLibro(None, f'no está el libro modelo del perfil: {config.modelo or "falta informes.modelo_libro"}')
    plan = plan_del_libro(config, r, destino=Path(docx).with_suffix('.xlsx'),
                          conclusion=conclusiones_del_word(docx), imagenes=imagenes)
    ruta, motivo = rellenar_con_excel(plan, ejecutar=ejecutar)
    if ruta is None:
        return ResultadoLibro(None, motivo, tuple(plan['huecos']))
    return ResultadoLibro(ruta, '', tuple(plan['huecos']), tuple(comprobar_libro(config, ruta, r)))
