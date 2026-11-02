"""Fija el cierre instalado del requirements principal para CPython 3.12/Windows.

065:RF-15 y RF-24. Produce constraints de versiones, no hashes de wheels ni una
auditoría CVE. El inventario completo del entorno no se exporta: puede incluir ML
optativo, instalaciones privadas o herramientas ajenas al producto.
"""

from __future__ import annotations

import argparse
from collections import deque
from importlib import metadata
import platform
from pathlib import Path
import re
import sys
import tomllib

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def comprobar_destino(version: str, plataforma: str, maquina: str) -> None:
    """Evita que un resultado de otro ABI se publique con el nombre Windows 3.12."""
    if Version(version).release[:2] != (3, 12) or plataforma != "win32" or maquina.upper() != "AMD64":
        raise ValueError("Este cierre requiere CPython 3.12 Windows AMD64")


def leer_requisitos(ruta: Path, visitados: frozenset[Path] = frozenset()) -> list[str]:
    """Lee el único manifiesto y el editable local sin congelar paquetes ajenos."""
    ruta = ruta.resolve()
    if ruta in visitados:
        raise ValueError("Inclusión circular de requirements")
    requisitos = []
    for original in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = original.split(" #", 1)[0].strip()
        if not linea or linea.startswith("#"):
            continue
        if linea.startswith(("-c ", "--constraint ")):
            # Los constraints son salida de esta herramienta, no una segunda lista
            # de paquetes que pueda introducir dependencias ausentes del producto.
            continue
        if linea.startswith(("-r ", "--requirement ")):
            requisitos.extend(leer_requisitos(ruta.parent / linea.split(maxsplit=1)[1], visitados | {ruta}))
            continue
        if linea.startswith(("-e ", "--editable ")):
            editable = linea.split(maxsplit=1)[1]
            coincidencia = re.fullmatch(r"\.(?:\[([a-zA-Z0-9_,.-]+)\])?", editable)
            if not coincidencia:
                raise ValueError("Solo se permite el editable del proyecto actual")
            proyecto = tomllib.loads((ruta.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            requisitos.extend(proyecto.get("dependencies", []))
            for extra in (coincidencia[1] or "").split(","):
                if extra:
                    try:
                        requisitos.extend(proyecto["optional-dependencies"][extra])
                    except KeyError as exc:
                        raise ValueError(f"Extra del proyecto desconocido: {extra}") from exc
            continue
        if linea.startswith("-"):
            raise ValueError("Opción no reproducible en requirements")
        try:
            requisito = Requirement(linea)
        except InvalidRequirement as exc:
            raise ValueError("Requisito no admitido; use nombres de distribución") from exc
        if requisito.url:
            raise ValueError(f"Referencia directa no admitida para {requisito.name}")
        requisitos.append(linea)
    return requisitos


def resolver_cierre(requisitos: list[str], inventario: dict | None = None) -> dict[str, str]:
    """Recorre Requires-Dist hasta un punto fijo, incluidos extras transitivos."""
    instalado = inventario is None
    inventario = {} if instalado else {canonicalize_name(n): d for n, d in inventario.items()}
    entorno = default_environment()
    pendientes = deque((r, frozenset({""})) for r in requisitos)
    activados: dict[str, set[str]] = {}
    cierre = {}
    while pendientes:
        texto, contexto = pendientes.popleft()
        requisito = Requirement(texto)
        nombre = canonicalize_name(requisito.name)
        if requisito.marker and not any(requisito.marker.evaluate({**entorno, "extra": e}) for e in contexto):
            continue
        if requisito.url:
            raise ValueError(f"Referencia directa no admitida para {nombre}")
        distribucion = inventario.get(nombre)
        if distribucion is None and instalado:
            try:
                distribucion = metadata.distribution(nombre)
                inventario[nombre] = distribucion
            except metadata.PackageNotFoundError:
                pass
        if distribucion is None:
            raise ValueError(f"Dependencia ausente en el entorno fuente: {nombre}")
        try:
            version = Version(distribucion.version or "")
        except InvalidVersion as exc:
            raise ValueError(f"Falta una versión válida para {nombre}") from exc
        if version.local:
            raise ValueError(f"Versión local no reproducible desde el índice público: {nombre}")
        if distribucion.read_text("direct_url.json"):
            # Un pin por nombre borraría la procedencia de un wheel local o VCS.
            # Se exige tratar esos artefactos mediante un lock de fuentes separado.
            raise ValueError(f"El origen directo de {nombre} no se conserva en constraints")
        if requisito.specifier and not requisito.specifier.contains(version, prereleases=True):
            raise ValueError(f"Versión incompatible: {nombre}=={version}, requerido {requisito.specifier}")
        nuevos = {"", *(canonicalize_name(e) for e in requisito.extras)}
        anteriores = activados.get(nombre)
        if anteriores is not None and nuevos <= anteriores:
            continue
        activados.setdefault(nombre, set()).update(nuevos)
        cierre[nombre] = str(version)
        pendientes.extend((dep, frozenset(activados[nombre])) for dep in distribucion.requires or [])
    return dict(sorted(cierre.items()))


def texto_constraints(cierre: dict[str, str], version_python: str) -> str:
    """Serializa sin timestamps, rutas privadas ni diferencias por orden de lectura."""
    cabecera = (
        "# Generado por tools/fijar_entorno.py desde el cierre de requirements.txt.\n"
        f"# Fuente: CPython {version_python}, Windows AMD64. Otro destino no está verificado.\n"
        "# Lock de versiones de metadatos; no contiene hashes de wheels ni escaneo CVE.\n"
        "# No incluye extras ML/drivers opcionales ni fija el backend de build aislado.\n"
        "# Regenerar con el entorno fuente verificado y revisar el diff antes de adoptar.\n"
    )
    marcador = 'python_version == "3.12" and sys_platform == "win32" and platform_machine == "AMD64"'
    return cabecera + "".join(f"{n}=={v} ; {marcador}\n" for n, v in sorted(cierre.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"), help="Manifiesto principal del candidato")
    parser.add_argument("--salida", type=Path, help="Constraints de salida; por defecto se imprimen")
    args = parser.parse_args()
    try:
        comprobar_destino(platform.python_version(), sys.platform, platform.machine())
        if platform.python_implementation() != "CPython":
            raise ValueError("Este cierre requiere CPython")
        texto = texto_constraints(resolver_cierre(leer_requisitos(args.requirements)), platform.python_version())
        if args.salida:
            args.salida.write_text(texto, encoding="utf-8", newline="\n")
        else:
            print(texto, end="")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"No se pudo fijar el entorno: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
