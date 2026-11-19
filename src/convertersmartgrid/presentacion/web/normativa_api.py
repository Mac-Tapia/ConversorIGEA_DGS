"""La biblioteca normativa general en la web (107:RF-21): las normas con su estado en una fecha, las reglas de cada una
con su cita, y la subida de una norma a la capa del usuario. Es la misma biblioteca para toda empresa, estudio y
módulo; no depende del espacio de trabajo.

107:RF-22 y 026:RF-46: la comprobación de las fuentes oficiales (solo lectura: huella y vigencia) y la regeneración de
un registro desde su fuente ya descargada, con su generador de ``tools/normativa``: primero una vista previa (corre el
generador en una carpeta temporal, que comprueba la huella de la fuente y la lee solo en copia, y dice qué reglas
entran, salen o cambian), y después ``aplicar`` con su ficha, que lo escribe en la capa del usuario si la biblioteca no
cambió entretanto. Sin la fuente dice cuál falta y dónde; nunca descarga nada.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

#: 107:RF-22: los generadores de los registros de la biblioteca (las sombreadas de la RCD 217 van dentro del de formatos).
GENERADORES = {'guia_vnr_232': 'generar_guia_vnr_232.py', 'formatos_217': 'generar_formatos_217.py',
               'coes': 'generar_coes.py', 'reconsideraciones': 'generar_reconsideraciones.py'}
#: Lo que el generador lee del repositorio como entrada (p. ej. la de las reconsideraciones) y donde escribe.
_COPIADAS = ('config/normativa', 'config/vnr')
_TOPE_S = 1800

from ...aplicacion import biblioteca_normativa as bn
from ...dominio.registro_normativo import RegistroError


class NormaResumen(BaseModel):
    acto: str
    titulo: str
    estado: str
    obliga: bool
    reglas: int
    url: str = ''
    vigencia_desde: str = ''
    vigencia_hasta: str = ''
    solo_referencia: str = ''
    sustituida_por_el_usuario: bool = False


class BibliotecaRespuesta(BaseModel):
    fecha: str
    huella: str
    capa_usuario: str
    normas: list[NormaResumen] = Field(default_factory=list)


class ReglaRespuesta(BaseModel):
    clave: str
    valor: str
    unidad: str = ''
    articulo_o_anexo: str = ''
    pagina: str = ''
    lineas: str = ''
    cita_literal: str = ''
    interpretacion: str = ''
    citada: bool = False


class ReglasRespuesta(BaseModel):
    acto: str
    reglas: list[ReglaRespuesta] = Field(default_factory=list)


class AgregadaRespuesta(BaseModel):
    actos: list[str]
    huella: str


class FuenteNorma(BaseModel):
    acto: str
    fichero: str = ''
    fuente: str
    motivo: str = ''
    estado_juridico: str
    obliga: bool
    vigencia_desde: str = ''
    vigencia_hasta: str = ''


class FuentesNormativaRespuesta(BaseModel):
    fecha: str
    carpeta: bool
    cuenta: dict[str, int] = Field(default_factory=dict)
    normas: list[FuenteNorma] = Field(default_factory=list)


class RegenerarPedido(BaseModel):
    generador: str


class CambioNorma(BaseModel):
    acto: str
    nueva: bool = False
    entran: list[str] = Field(default_factory=list)
    salen: list[str] = Field(default_factory=list)
    cambian: list[str] = Field(default_factory=list)
    vigencia: dict[str, list[str]] = Field(default_factory=dict)


class RegenerarRespuesta(BaseModel):
    generador: str
    token: str
    sin_cambios: bool
    cambios: list[CambioNorma] = Field(default_factory=list)
    #: Otros ficheros que el generador rehízo (p. ej. las tablas de config/vnr): viajan con el programa y no se
    #: escriben desde aquí; se dicen para que el integrador los lleve.
    otros: list[str] = Field(default_factory=list)


class AplicadaRespuesta(BaseModel):
    actos: list[str]
    huella: str
    sin_cambios: bool
    cambios: list[CambioNorma] = Field(default_factory=list)
    otros: list[str] = Field(default_factory=list)


def _limpio(texto: str, *rutas: Path | None) -> str:
    """El mensaje del generador sin las rutas de la máquina."""
    for r, nombre in zip(rutas, ('<fuentes>', '<temporal>', '<programa>')):
        if r is not None:
            for forma in {str(r), r.as_posix(), str(r.resolve()), r.resolve().as_posix()}:
                texto = texto.replace(forma, nombre)
    return texto


def _huellas(carpeta: Path) -> dict[str, str]:
    return {f.relative_to(carpeta).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(carpeta.rglob('*')) if f.is_file()}


def registrar_rutas_normativa(app: FastAPI, *, guardar_subida: Callable[[Path, UploadFile], None],
                              hoy: Callable[[], str], carpeta_fuentes: Callable[[], Path | None] | None = None,
                              programa: Callable[[], Path] | None = None) -> None:
    base = '/api/normativa'

    def _carpeta() -> Path | None:
        if carpeta_fuentes is not None:
            return carpeta_fuentes()
        from ...adaptadores.pit.armado import carpeta_de_fuentes
        return carpeta_de_fuentes()

    def _programa() -> Path:
        if programa is not None:
            return programa()
        from ...adaptadores.powerfactory_env import project_root
        return project_root()

    def _preparadas() -> Path:
        return bn.ruta_capa_usuario().parent / 'normativa_regenerada'

    @app.get(base, response_model=BibliotecaRespuesta)
    def normativa_listar(fecha: str | None = None) -> dict:
        """107:RF-21: cada norma de la biblioteca, su estado y si obliga en ``fecha`` (hoy, si no se da)."""
        dia = fecha or hoy()
        try:
            r = bn.cargar_biblioteca(dia)
        except RegistroError as exc:
            raise HTTPException(500, f'La biblioteca normativa no carga: {exc}') from exc
        sustituidas = getattr(r, 'sustituidas', {})
        normas = [{'acto': n.acto, 'titulo': n.titulo, 'estado': n.estado_juridico, 'obliga': n.obligatoria_en(dia),
                   'reglas': len(n.reglas), 'url': n.url, 'vigencia_desde': n.vigencia_desde,
                   'vigencia_hasta': n.vigencia_hasta, 'solo_referencia': n.solo_referencia,
                   'sustituida_por_el_usuario': n.acto in sustituidas} for n in (r.normas[a] for a in sorted(r.normas))]
        return {'fecha': dia, 'huella': bn.huella_biblioteca(), 'capa_usuario': str(bn.ruta_capa_usuario()),
                'normas': normas}

    @app.get(f'{base}/reglas', response_model=ReglasRespuesta)
    def normativa_reglas(acto: str) -> dict:
        """107:RF-21: las reglas de una norma, cada una con su artículo, página, líneas y cita literal."""
        r = bn.cargar_biblioteca()
        if acto not in r.normas:
            raise HTTPException(404, f'La biblioteca no tiene la norma {acto}.')
        reglas = [{'clave': x.clave, 'valor': str(x.valor), 'unidad': str(x.unidad),
                   'articulo_o_anexo': str(x.articulo_o_anexo), 'pagina': str(x.pagina), 'lineas': str(x.lineas),
                   'cita_literal': str(x.cita_literal), 'interpretacion': str(x.interpretacion), 'citada': x.citada}
                  for x in r.normas[acto].reglas]
        return {'acto': acto, 'reglas': reglas}

    @app.post(base, response_model=AgregadaRespuesta)
    def normativa_agregar(file: UploadFile = File(...)) -> dict:
        """107:RF-21: añade o actualiza una norma en la capa del usuario; lo que no cumple el esquema no entra."""
        nombre = Path(file.filename or '').name
        if not nombre.lower().endswith('.json'):
            raise HTTPException(422, 'La norma se sube como un fichero .json del esquema registro_normativo_v1.')
        with tempfile.TemporaryDirectory() as tmp:
            temporal = Path(tmp) / nombre
            guardar_subida(temporal, file)
            try:
                actos = bn.agregar_norma(temporal)
            except RegistroError as exc:
                raise HTTPException(422, str(exc)) from exc
        return {'actos': actos, 'huella': bn.huella_biblioteca()}

    @app.get(f'{base}/fuentes', response_model=FuentesNormativaRespuesta)
    def normativa_fuentes(fecha: str | None = None) -> dict:
        """107:RF-22, 026:RF-46: la huella de la fuente oficial de cada norma y su vigencia en ``fecha``; solo lee."""
        try:
            return bn.comprobar_fuentes(_carpeta(), fecha or hoy())
        except RegistroError as exc:
            raise HTTPException(500, f'La biblioteca normativa no carga: {exc}') from exc

    @app.post(f'{base}/regenerar', response_model=RegenerarRespuesta)
    def normativa_regenerar(pedido: RegenerarPedido) -> dict:
        """107:RF-22: corre el generador en una carpeta temporal y dice qué reglas entran, salen o cambian; no escribe
        en la biblioteca. Devuelve la ficha (``token``) para aplicarlo."""
        guion = GENERADORES.get(pedido.generador)
        if guion is None:
            raise HTTPException(422, f'Generador desconocido «{pedido.generador}»; los hay: {", ".join(GENERADORES)}.')
        fuentes = _carpeta()
        if fuentes is None or not fuentes.is_dir():
            raise HTTPException(409, 'Falta la carpeta de fuentes normativas: ponga en CSG_FUENTES_NORMATIVAS la '
                                     'carpeta con las fuentes oficiales descargadas y su SHA256SUMS.txt. No se '
                                     'descarga nada.')
        raiz = _programa()
        script = raiz / 'tools' / 'normativa' / guion
        if not script.is_file():
            raise HTTPException(404, f'Esta instalación no trae el generador tools/normativa/{guion}.')
        token = secrets.token_hex(12)
        destino = _preparadas() / token
        try:
            for rel in _COPIADAS:
                if (raiz / rel).is_dir():
                    shutil.copytree(raiz / rel, destino / rel)
                else:
                    (destino / rel).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # 026:RF-46: una copia a medias no queda como regeneración preparada.
            shutil.rmtree(destino, ignore_errors=True)
            raise HTTPException(500, f'No se pudo preparar la regeneración: {exc}') from exc
        antes = _huellas(destino)
        try:
            corrida = subprocess.run([sys.executable, str(script), '--fuentes', str(fuentes), '--destino',
                                      str(destino)], cwd=str(raiz), capture_output=True, text=True,
                                     encoding='utf-8', errors='replace', timeout=_TOPE_S, check=False)
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(destino, ignore_errors=True)
            raise HTTPException(504, f'El generador {guion} no terminó en {_TOPE_S} s.') from exc
        if corrida.returncode != 0:
            shutil.rmtree(destino, ignore_errors=True)
            ultimo = [x for x in (corrida.stderr or corrida.stdout or '').splitlines() if x.strip()]
            motivo = _limpio(ultimo[-1] if ultimo else f'rc={corrida.returncode}', fuentes, destino, raiz)
            raise HTTPException(422, f'No se regenera: {motivo}')
        despues = _huellas(destino)
        rehechos = sorted(k for k, v in despues.items() if antes.get(k) != v)
        registros = [k for k in rehechos if k.startswith('config/normativa/') and k.count('/') == 2
                     and k.endswith('.json')]
        try:
            cambios = [c for k in registros for c in bn.comparar_con_vigente(destino / k)]
        except RegistroError as exc:
            shutil.rmtree(destino, ignore_errors=True)
            raise HTTPException(422, 'El registro regenerado no valida: '
                                     f'{_limpio(str(exc), fuentes, destino, raiz)}') from exc
        sin_cambios = not any(c['nueva'] or c['entran'] or c['salen'] or c['cambian'] or c['vigencia']
                              for c in cambios)
        otros = [k for k in rehechos if k not in registros]
        from ...dominio.util import write_json_atomic

        ficha = {'generador': pedido.generador, 'huella': bn.huella_biblioteca(), 'registros': registros,
                 'sin_cambios': sin_cambios, 'cambios': cambios, 'otros': otros}
        write_json_atomic(destino / 'ficha.json', json.loads(json.dumps(ficha, default=str)))   # 001:RF-5
        return {'generador': pedido.generador, 'token': token, 'sin_cambios': sin_cambios, 'cambios': cambios,
                'otros': otros}

    @app.post(f'{base}/regenerar/{{token}}/aplicar', response_model=AplicadaRespuesta)
    def normativa_regenerar_aplicar(token: str) -> dict:
        """107:RF-22: escribe en la capa del usuario lo regenerado en la vista previa ``token``, si la biblioteca no
        cambió desde entonces; sin cambios, no escribe nada."""
        if not token.isalnum():
            raise HTTPException(422, 'Ficha no válida.')
        destino = _preparadas() / token
        try:
            ficha = json.loads((destino / 'ficha.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise HTTPException(404, 'No hay una vista previa con esa ficha: regenere de nuevo.') from exc
        if ficha['huella'] != bn.huella_biblioteca():
            raise HTTPException(409, 'La biblioteca cambió desde la vista previa: regenere de nuevo para ver los '
                                     'cambios sobre la vigente.')
        actos: list[str] = []
        if not ficha['sin_cambios']:
            try:
                for rel in ficha['registros']:
                    actos += bn.agregar_norma(destino / rel)
            except RegistroError as exc:
                raise HTTPException(422, str(exc)) from exc
        shutil.rmtree(destino, ignore_errors=True)
        return {'actos': actos, 'huella': bn.huella_biblioteca(), 'sin_cambios': ficha['sin_cambios'],
                'cambios': ficha.get('cambios') or [], 'otros': ficha.get('otros') or []}
