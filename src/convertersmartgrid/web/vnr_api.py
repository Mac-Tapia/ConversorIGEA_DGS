"""108 T28: el estudio VNR desde la web (Guía del VNR, RCD 232-2017-OS/CD; 108:RF-21 a RF-25).

El operador suelta el ``canonical.json`` del inventario VNR-GIS (el que deja el conversor del módulo ``vnr``) y el libro
o el zip del SICODI de la última fijación, elige el sector típico de la Guía y el del SICODI, y el estudio corre como
trabajo del motor: zonifica, adapta, codifica y valoriza, y deja en ``<salidas>/vnr/`` el resultado y el libro de los
formatos A1 y C1 del Anexo 5. Lo que falta para una regla queda como hueco nombrado en el resultado; nada se inventa.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..util import publicar_duradero
from .api_contract import JobRespuesta

CARPETA = 'vnr'
RESULTADO = 'resultado_vnr.json'
LIBRO = 'formatos_vnr.xlsx'
SECTORES_GUIA = ('urbano_alta', 'urbano_media_baja', 'urbano_rural', 'rural_ser')
EXT_SICODI = ('.xlsx', '.xlsm', '.xls', '.xlsb', '.zip')


class SedVnrRespuesta(BaseModel):
    sed: str
    md_kw: float
    kva_adaptado: float
    zona: str
    tipo: str
    codigo: str
    kva_catalogo: float
    regla: str


class VnrEstudioRespuesta(BaseModel):
    """108 T28: el último estudio VNR del espacio; vacío si aún no hay ninguno."""
    sector: str | None = None
    sector_sicodi: str | None = None
    moneda: str | None = None
    sicodi: str | None = None
    huella_sicodi: str | None = None
    formula: str | None = None
    vnr_ie: float | None = None
    vnr_ine: float | None = None
    vnr_total: float | None = None
    completo: bool | None = None
    zonas_mt: dict[str, int] | None = None
    zonas_bt: dict[str, int] | None = None
    tramos_mt: int | None = None
    tramos_bt: int | None = None
    seds: list[SedVnrRespuesta] | None = None
    partidas_sin_costo: list[str] | None = None
    huecos: list[str] | None = None
    anualidad_vnr_real: dict[str, float | int | str | None] | None = None
    libro: str | None = None


def calcular(ws, ctx, canonical: Path, sicodi: Path, *, nombre_sicodi: str, sector: str, sector_sicodi: str,
             resolucion: str, anio: int, moneda: str) -> dict:
    """El trabajo del motor: lee, estudia, escribe el resultado y el libro de formatos."""
    from ..adaptadores.entrada.vnr.models.canonical import CanonicalModel
    from ..costos_fuentes import leer_sicodi
    from ..registro_normativo import cargar_registro
    from ..vad.costos import anualidad_vnr_real
    from ..vad.vnr_estudio import estudio_vnr
    from ..vad.vnr_formatos import escribir_formatos
    from ..vad.vnr_guia import ANEXO2_DEFECTO, cargar_anexo2, cargar_anexo5, cargar_anexo6, formato_resumen

    config = ANEXO2_DEFECTO.parents[1]
    ctx.log('Leyendo el inventario VNR-GIS…')
    modelo = CanonicalModel.from_dict(json.loads(canonical.read_text(encoding='utf-8')))
    ctx.log('Leyendo el SICODI…')
    tabla = leer_sicodi(sicodi, resolucion=resolucion, anio=anio, moneda=moneda, url=nombre_sicodi,
                        fecha_descarga='subido desde la web')
    registro = cargar_registro(config / 'normativa' / 'rcd_232_2017.json')
    a2, a5, a6 = cargar_anexo2(), cargar_anexo5(), cargar_anexo6()
    ctx.log('Zonificando, adaptando y valorizando con la Guía del VNR…')
    e = estudio_vnr(modelo, sector=sector, sector_sicodi=sector_sicodi, tabla_costos=tabla, registro=registro,
                    anexo2=a2, anexo6=a6)
    salida = ws.out_dir / CARPETA
    salida.mkdir(parents=True, exist_ok=True)
    formatos = [formato_resumen(e.resultado, a2, a5, codigo='A1', moneda=moneda),
                formato_resumen(e.resultado, a2, a5, codigo='C1', ambito='inventario cargado', moneda=moneda)]
    escribir_formatos(formatos, salida / LIBRO, notas=a5['notas'])
    try:
        anual = anualidad_vnr_real(e.resultado, registro=cargar_registro(config / 'vad', config / 'normativa'))
        anualidad = {'factor': anual.factor_anualidad, 'anualidad': anual.anualidad, 'vida_util_anios':
                     anual.vida_util_anios}
    except Exception as exc:  # noqa: BLE001 - la anualidad es un contraste: su fallo se dice, no tumba el estudio
        anualidad = {'error': f'{exc.__class__.__name__}: {exc}'}
    datos = {
        'sector': sector, 'sector_sicodi': sector_sicodi, 'moneda': moneda, 'sicodi': nombre_sicodi,
        'huella_sicodi': e.resultado.huella_costos, 'formula': e.resultado.formula,
        'vnr_ie': e.resultado.vnr_ie, 'vnr_ine': e.resultado.vnr_ine, 'vnr_total': e.resultado.total,
        'completo': e.resultado.completo, 'zonas_mt': e.zonas_mt, 'zonas_bt': e.zonas_bt,
        'tramos_mt': len(e.adaptados_mt), 'tramos_bt': len(e.adaptados_bt), 'seds': e.seds,
        'partidas_sin_costo': [f'{h.item.codigo}: {h.motivo}' for h in e.resultado.huecos],
        'huecos': e.huecos, 'anualidad_vnr_real': anualidad, 'libro': f'{CARPETA}/{LIBRO}',
    }
    publicar_duradero(salida / RESULTADO, json.dumps(datos, ensure_ascii=False, indent=1))
    ctx.log(f'VNR {"completo" if e.resultado.completo else "con huecos"}: {e.resultado.vnr_ie:,.2f} {moneda}')
    return datos


def ultimo(ws) -> dict:
    ruta = ws.out_dir / CARPETA / RESULTADO
    return json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else {}


def registrar_rutas_vnr(app: FastAPI, *, ws_or_404, submit, guardar_subida: Callable[[Path, UploadFile], None]) -> None:
    ruta = '/api/workspaces/{wid}/vnr/estudio'

    @app.get(ruta, response_model=VnrEstudioRespuesta, response_model_exclude_unset=True)
    def vnr_estado(wid: str) -> dict:
        """108 T28: el último estudio VNR del espacio (vacío si no hay)."""
        return ultimo(ws_or_404(wid))

    @app.post(ruta, status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def vnr_lanzar(wid: str, sector: str = Form(...), sector_sicodi: str = Form(...), resolucion: str = Form(...),
                   anio: int = Form(...), moneda: str = Form(...), canonical: UploadFile | None = File(None),
                   sicodi: UploadFile | None = File(None), fuente_sicodi: str | None = Form(None)) -> dict:
        """108 T28 y 109:RF-25/25: lanza el estudio VNR en un trabajo del motor. El inventario es, por defecto, la red
        que dejó la carga del espacio (la misma del conversor); el SICODI, el libro de la empresa elegido o el vigente.
        Un fichero subido manda y, si es el SICODI, se registra para todos los módulos."""
        ws = ws_or_404(wid)
        if sector not in SECTORES_GUIA:
            raise HTTPException(400, f'Sector típico de la Guía no válido: elija uno de {", ".join(SECTORES_GUIA)}.')
        if not sector_sicodi.strip() or not resolucion.strip() or not moneda.strip():
            raise HTTPException(400, 'Indique el sector típico del SICODI, su resolución y su moneda.')
        if canonical is not None and canonical.filename and Path(canonical.filename).suffix.lower() != '.json':
            raise HTTPException(400, 'El inventario es el canonical.json que deja el conversor VNR-GIS.')
        if sicodi is not None and sicodi.filename and Path(sicodi.filename).suffix.lower() not in EXT_SICODI:
            raise HTTPException(400, 'El SICODI es un libro de cálculo (.xlsx, .xlsm, .xls, .xlsb) o su zip.')
        from .. import fuentes_empresa
        from .fuentes_api import fuente_o_subida
        temporal = Path(tempfile.mkdtemp(prefix='csg-vnr-'))
        try:
            if canonical is not None and canonical.filename:
                ruta_canonical = temporal / 'canonical.json'
                guardar_subida(ruta_canonical, canonical)
            else:
                red = fuentes_empresa.red_del_espacio(Path(ws.root))
                if not red or not red.get('canonical'):
                    raise HTTPException(400, 'El espacio no tiene una red VNR-GIS cargada: cárguela en «Entrada de '
                                             'datos» (o suba su canonical.json).')
                ruta_canonical = Path(ws.root) / red['canonical']
            ruta_sicodi = fuente_o_subida(ws, 'sicodi', fuente_sicodi, sicodi, guardar_subida, periodo=resolucion.strip())
        except BaseException:
            shutil.rmtree(temporal, ignore_errors=True)
            raise
        nombre_sicodi = ruta_sicodi.name

        def trabajo(ctx) -> dict:
            try:
                return calcular(ws, ctx, ruta_canonical, ruta_sicodi, nombre_sicodi=nombre_sicodi, sector=sector,
                                sector_sicodi=sector_sicodi.strip(), resolucion=resolucion.strip(), anio=anio,
                                moneda=moneda.strip())
            finally:
                shutil.rmtree(temporal, ignore_errors=True)

        return submit(ws, 'vnr_estudio', f'Estudio VNR (Guía 232-2017), sector {sector}, {sector_sicodi}', trabajo,
                      lane='engine')
