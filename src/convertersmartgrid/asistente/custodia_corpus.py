"""Resolución explícita de custodias relativas, sin estado compartido entre corpus (047/065)."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PureWindowsPath

from ..evaluacion_modelos import huella


def sin_enlaces(ruta: Path) -> Path:
    """No seguir enlaces o junctions ni en la entrada ni en sus ancestros."""
    ruta = ruta.expanduser().absolute()
    for componente in (ruta, *ruta.parents):
        if componente.is_symlink() or componente.is_junction():
            raise ValueError('fuente o destino con enlace no admitido: ' + str(componente))
    return ruta.resolve()


def relativa_segura(raiz: Path, texto: str) -> Path:
    """El mapeo portable no puede salir de la nueva custodia."""
    ruta = Path(texto)
    windows = PureWindowsPath(texto)
    if (not texto or ruta.is_absolute() or windows.drive or windows.root or
            '..' in ruta.parts or '..' in windows.parts or '\\' in texto):
        raise ValueError('ruta relativa de custodia invalida o con escape')
    destino = sin_enlaces(raiz / ruta)
    if not destino.is_relative_to(raiz):
        raise ValueError('escape de la custodia del corpus')
    return destino


@dataclass(frozen=True)
class CustodiaCorpus:
    """Cada lector recibe su resolución; nunca cambia el significado de otro corpus."""
    raiz: Path
    resoluciones: dict[str, tuple[Path, str, int]]

    def ruta(self, evidencia: dict) -> Path:
        texto = evidencia['ruta']
        if not Path(texto).is_absolute():
            return relativa_segura(self.raiz, texto)
        entrada = self.resoluciones.get(texto)
        if entrada is None:
            raise ValueError('fuente absoluta sin mapeo de custodia')
        ruta, sha, cantidad = entrada
        if (sha, cantidad) != (evidencia['sha256'], evidencia['bytes']):
            raise ValueError('huella de resolución distinta de la fuente sellada')
        return sin_enlaces(ruta)


def leer_custodia(dataset: Path, meta: dict) -> CustodiaCorpus | None:
    """Los corpus anteriores mantienen su validador; la nueva custodia es opt-in."""
    traslado = meta.get('reubicacion_fuentes')
    if traslado is None:
        return None
    if (traslado.get('schema_version') != 1 or
            huella({k: v for k, v in traslado.items() if k != 'huella'}) != traslado.get('huella')):
        raise ValueError('huella del manifiesto de reubicación invalida')
    raiz = sin_enlaces(dataset)
    for nombre, evidencia in traslado['archivos_originales'].items():
        relativa = 'origen/dataset_manifest.json' if nombre == 'dataset_manifest.json' else nombre
        archivo = relativa_segura(raiz, relativa)
        with archivo.open('rb') as entrada:
            sha = hashlib.file_digest(entrada, 'sha256').hexdigest()
        if (sha, archivo.stat().st_size) != (evidencia['sha256'], evidencia['bytes']):
            raise ValueError('huella de archivo original custodiado modificada: ' + nombre)
    original = json.loads((raiz / 'origen/dataset_manifest.json').read_text(encoding='utf-8'))
    esperado = {**original, 'reubicacion_fuentes': traslado}
    esperado['archivos_particion'] = {p: {**e, 'ruta': p + '.jsonl'}
                                      for p, e in original['archivos_particion'].items()}
    for clave, nombre in (('contextos_fuente', 'contextos_fuente.json'),
                          ('humanas_reservadas_archivo', 'humanas_reservadas.json')):
        esperado[clave] = {**original[clave], 'ruta': nombre}
    if (huella(esperado) != huella(meta) or
            original['dataset_hash'] != traslado['dataset_hash_preservado']):
        raise ValueError('manifiesto distinto del sellado original custodiado')
    resoluciones = {}
    for entrada in traslado['resoluciones']:
        original = entrada['origen']
        if original in resoluciones:
            raise ValueError('resolución ambigua de fuente')
        resoluciones[original] = (relativa_segura(raiz, entrada['destino']),
                                  entrada['sha256'], entrada['bytes'])
    return CustodiaCorpus(raiz, resoluciones)


def ruta_fuente(evidencia: dict, custodia: CustodiaCorpus | None = None) -> Path:
    """Resolver solo cuando el lector dispone de un manifiesto explícito."""
    return custodia.ruta(evidencia) if custodia else Path(evidencia['ruta'])
