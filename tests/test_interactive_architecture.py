"""Pruebas de la arquitectura C4 (AS-IS y TO-BE) y de sus ADR.

Spec 034: 034:RF-31 (C4 AS-IS interactivo) y 034:RF-34 a RF-41 (C4 TO-BE, ADR coherentes con el código y deuda de
excepciones mudas). Las comprobaciones de la TO-BE y de los ADR se prueban también contra repositorios sintéticos con
cada defecto, para que una prueba en verde no sea un detector ciego.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from apoyo import cargar_herramienta


ROOT = Path(__file__).resolve().parents[1]
DSL = ROOT / "docs" / "architecture" / "workspace.dsl"
HTML = ROOT / "docs" / "architecture" / "arquitectura-interactiva-c4.html"
BUILDER = ROOT / "tools" / "build_interactive_architecture.py"


def test_structurizr_model_exposes_required_views_and_real_access_points():
    text = DSL.read_text(encoding="utf-8")

    for key in (
        "SystemContext",
        "Containers",
        "Conversion",
        "PowerFactory",
        "Inteligencia",
        "Deployment",
    ):
        assert f'"{key}"' in text

    for access_point in (
        "http://127.0.0.1:8765/",
        "src/convertersmartgrid/presentacion/web/app.py",
        "src/convertersmartgrid/presentacion/web/services.py",
        "src/convertersmartgrid/adaptadores/digital_twin",
        "src/convertersmartgrid/aplicacion/asistente",
        "output/web",
    ):
        assert access_point in text
    assert 'nativeRunner -> oracle "Solicita preflight informativo"' in text
    assert 'oracle -> nativeRunner "Devuelve avisos; la importacion continua"' in text
    assert "engine -> oracle" not in text
    assert "oracle -> dgs" not in text
    assert "/tree/main/" not in text
    assert "/blob/main/" not in text
    # 034:RF-31: los puntos de acceso se enlazan fijados a una revisión, nunca a una ruta de la máquina del desarrollo
    # (antes se exigía un «file:///D:/…»: no vale en otro equipo y la lista de términos de la entrega lo rechaza).
    assert "file:///" not in text
    assert re.search(r"https://github\.com/[^\s\"]+/tree/[0-9a-f]{40}/src/convertersmartgrid/adaptadores/digital_twin", text)


def test_interactive_visualization_has_finite_flow_controls_and_accessible_nodes():
    text = HTML.read_text(encoding="utf-8")

    assert '<div id="csg-c4-flow"' in text
    assert "prefers-reduced-motion" in text
    assert 'id="flow-play"' in text
    assert 'id="flow-next"' in text
    assert 'id="flow-reset"' in text
    assert 'id="flow-speed"' in text
    assert 'aria-live="polite"' in text
    assert 'role="img"' in text
    assert 'role="tabpanel"' in text
    assert 'aria-controls="c4-stage"' in text
    assert "ArrowRight" in text
    assert "playFlow" in text
    assert "advanceFlow" in text
    assert "setView" in text
    assert "animationiteration" not in text.lower()
    assert "infinite" not in text.lower()
    assert "progress < 1 && playing" not in text
    assert "progress < 1 && activePath === path" in text
    assert "svgEl('textPath'" not in text
    assert "[hidden]" in text
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in text
    assert "${common[edge.from].label} -> ${common[edge.to].label}" in text
    assert "tools/verificar_pf.py" not in text
    assert "new URL(`../../${access}`" in text

    node_ids = set(re.findall(r'data-node-id="([^"]+)"', text))
    assert {"sources", "frontend", "api", "engine", "powerfactory", "twin", "assistant", "deliverables"} <= node_ids


def test_visualization_contains_every_required_flow_and_direct_destination():
    text = HTML.read_text(encoding="utf-8")

    for view in ("context", "containers", "conversion", "powerfactory", "intelligence", "deployment"):
        assert f'data-view="{view}"' in text

    for destination in (
        "src/convertersmartgrid/adaptadores/sources",
        "src/convertersmartgrid/adaptadores/dgs.py",
        "src/convertersmartgrid/presentacion/web/app.py",
        "tools/powerfactory_acceptance.py",
        "src/convertersmartgrid/adaptadores/digital_twin/oraculo.py",
        "src/convertersmartgrid/aplicacion/asistente/interprete.py",
        "docs/architecture/plano_flujo_arquitectura_converter_smart_grid.pdf",
    ):
        assert destination in text


def test_visualization_exposes_scientific_basis_and_standalone_delivery():
    text = HTML.read_text(encoding="utf-8")

    for source in (
        "https://doi.org/10.1016/j.jss.2014.03.071",
        "https://doi.org/10.1109/TPWRS.2018.2829021",
        "https://doi.org/10.1016/j.epsr.2020.106664",
        "https://redi.cedia.edu.ec/document/42803",
        "https://etheses.whiterose.ac.uk/id/eprint/30114/",
    ):
        assert source in text

def test_tracked_source_builds_standalone_delivery_in_clean_directory(tmp_path):
    assert (ROOT / "docs" / "architecture" / "plano_flujo_arquitectura_converter_smart_grid.pdf").is_file()
    subprocess.run(
        [sys.executable, str(BUILDER), "--output-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    standalone = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in standalone.lower()
    assert 'id="csg-c4-flow"' in standalone
    assert "<iframe" not in standalone
    assert "tools/powerfactory_acceptance.py" in standalone


# ====================================================================== C4 TO-BE y ADR (034:RF-34 a RF-41)
ES = cargar_herramienta('estado_specs.py')
TOBE = ROOT / "docs" / "architecture" / "workspace_to_be.dsl"
ADR_DIR = ROOT / "docs" / "architecture" / "adr"
DEUDA_MUDAS = ADR_DIR / "deuda_excepciones_mudas.json"

_ELEMENTO = re.compile(
    r'^[ \t]*(\w+)[ \t]*=[ \t]*(person|softwareSystem|container|component|deploymentEnvironment|deploymentNode'
    r'|infrastructureNode)\b', re.M)
_RELACION = re.compile(r'^[ \t]*(\w+)[ \t]*->[ \t]*(\w+)\b', re.M)
_AMPLIA = re.compile(r'^[ \t]*!element[ \t]+(\w+)', re.M)
#: La clave de una vista: la primera cadena tras su alcance; en las de despliegue, la segunda (tras el entorno).
_VISTA = re.compile(r'^[ \t]*(?:(?:systemContext|container|component|dynamic)[ \t]+\w+[ \t]+"([^"]+)"'
                    r'|deployment[ \t]+\w+[ \t]+"[^"]*"[ \t]+"([^"]+)")', re.M)
_URL = re.compile(r'url "https://github\.com/[^/"]+/[^/"]+/(?:blob|tree)/([^/"]+)/([^"]+)"')
_PROPIEDAD_ADR = re.compile(r'"ADR"[ \t]+"(ADR-\d{3})"')
_CABECERA_ADR = re.compile(r'^# (ADR-\d{3}) · (.+)$', re.M)
_CAMPO = re.compile(r'^- ([^:\n]+): *(.*)$', re.M)
_SECCION = re.compile(r'^## (.+)$', re.M)
_ITEM = re.compile(r'`([^`]+)`')
_CITA_RF = re.compile(r'\b(\d{3}):RF-(\d+[a-z]?)\b')
_CITA_SPEC = re.compile(r'\bspec (\d{3})\b')
_CITA_TAREA = re.compile(r'\b(\d{3}) (T\d+[a-z]?)\b')

CAMPOS_ADR = ("Estado", "Fecha", "Specs", "Elementos C4")
SECCIONES_ADR = ("Contexto", "Decisión", "Alternativa descartada", "Consecuencias", "Contratos afectados",
                 "Vuelta atrás")
ESTADOS_ADR = ("vigente", "pendiente", "sustituida", "retirada")


def _sin_comentarios(texto: str) -> str:
    return "\n".join(linea for linea in texto.splitlines() if not linea.lstrip().startswith("//"))


def _cierre(texto: str, abre: int) -> int:
    """Posición de la llave que cierra la que está en ``abre``; ignora las llaves dentro de comillas."""
    nivel, en_cadena = 0, False
    for i in range(abre, len(texto)):
        c = texto[i]
        if c == '"':
            en_cadena = not en_cadena
        elif not en_cadena and c == "{":
            nivel += 1
        elif not en_cadena and c == "}":
            nivel -= 1
            if nivel == 0:
                return i
    raise ValueError(f"llave sin cerrar en la posición {abre}")


def elementos_dsl(texto: str) -> dict[str, str]:
    """Identificador → texto propio de su bloque, sin los bloques de sus hijos; '' si no tiene bloque."""
    texto = _sin_comentarios(texto)
    tramos: list[tuple[str, int, int, int]] = []
    for m in _ELEMENTO.finditer(texto):
        fin_linea = texto.find("\n", m.start())
        linea = texto[m.start():fin_linea if fin_linea >= 0 else len(texto)]
        if "{" in linea:
            abre = texto.index("{", m.start())
            tramos.append((m.group(1), m.start(), abre, _cierre(texto, abre)))
        else:
            tramos.append((m.group(1), m.start(), -1, -1))
    salida: dict[str, str] = {}
    for nombre, _inicio, abre, cierra in tramos:
        if abre < 0:
            salida[nombre] = ""
            continue
        trozos, desde = [], abre + 1
        for _otro, o_inicio, o_abre, o_cierra in tramos:
            if desde <= o_inicio < cierra:
                trozos.append(texto[desde:o_inicio])
                desde = (o_cierra if o_abre >= 0 else texto.find("\n", o_inicio)) + 1
        trozos.append(texto[desde:cierra])
        salida[nombre] = "".join(trozos)
    return salida


def problemas_to_be(as_is: str, to_be: str, raiz: Path) -> list[str]:
    """034:RF-34 y 034:RF-35: la TO-BE extiende el AS-IS, no redefine nada y solo relaciona lo que existe."""
    problemas: list[str] = []
    limpio = _sin_comentarios(to_be).strip()
    if not limpio:
        return ["la TO-BE está vacía"]
    if not re.match(r'workspace\s+extends\s+workspace\.dsl\b', limpio):
        problemas.append("la TO-BE no empieza con «workspace extends workspace.dsl»: no extiende el mismo modelo")
    ids_as_is, propios = set(elementos_dsl(as_is)), elementos_dsl(to_be)
    for nombre in sorted(set(propios) & ids_as_is):
        problemas.append(f"la TO-BE redefine «{nombre}», que ya es del AS-IS")
    if not propios:
        problemas.append("la TO-BE no declara ningún elemento nuevo")
    todos = ids_as_is | set(propios)
    for nombre in _AMPLIA.findall(_sin_comentarios(to_be)):
        if nombre not in ids_as_is:
            problemas.append(f"la TO-BE amplía «{nombre}», que no está en el AS-IS")
    for origen, destino in _RELACION.findall(_sin_comentarios(to_be)):
        for nombre in (origen, destino):
            if nombre not in todos:
                problemas.append(f"la relación {origen} -> {destino} usa «{nombre}», que no está en ningún modelo")
    vistas_as_is = {a or b for a, b in _VISTA.findall(as_is)}
    vistas = [a or b for a, b in _VISTA.findall(_sin_comentarios(to_be))]
    if not vistas:
        problemas.append("la TO-BE no tiene vistas propias")
    for clave in vistas:
        if clave in vistas_as_is:
            problemas.append(f"la vista «{clave}» de la TO-BE ya es del AS-IS")
    for revision, ruta in _URL.findall(to_be):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            problemas.append(f"el enlace a {ruta} no está fijado a una revisión de 40 caracteres ({revision})")
        if not (raiz / ruta).exists():
            problemas.append(f"el enlace apunta a «{ruta}», que no existe en el repositorio")
    return problemas


def leer_adr(ruta: Path) -> dict:
    texto = ruta.read_text(encoding="utf-8")
    cabecera = _CABECERA_ADR.search(texto)
    primera = _SECCION.search(texto)
    prologo = texto[:primera.start()] if primera else texto
    campos = {m.group(1).strip(): m.group(2).strip() for m in _CAMPO.finditer(prologo)}
    secciones: dict[str, str] = {}
    marcas = list(_SECCION.finditer(texto))
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        secciones[m.group(1).strip()] = texto[m.end():fin].strip()
    return {"ruta": ruta, "id": cabecera.group(1) if cabecera else None,
            "titulo": cabecera.group(2).strip() if cabecera else "", "campos": campos, "secciones": secciones}


def leer_adrs(carpeta: Path) -> list[dict]:
    return [leer_adr(r) for r in sorted(carpeta.glob("ADR-*.md"))]


def _spec(raiz: Path, numero: str):
    carpetas = sorted((raiz / "specs").glob(f"{numero}-*"))
    return ES.leer_spec(carpetas[0]) if carpetas and (carpetas[0] / "spec.md").is_file() else None


def _ruta_segura(raiz: Path, ruta: str) -> Path | None:
    if not ruta or Path(ruta).is_absolute() or ".." in Path(ruta).parts or re.match(r"[A-Za-z]:", ruta):
        return None
    return raiz / ruta


def _definidos_py(ruta: Path) -> set[str]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8-sig"))
    nombres: set[str] = set()
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres.update(t.id for t in nodo.targets if isinstance(t, ast.Name))
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombres.add(nodo.target.id)
    return nombres


def _usados_py(ruta: Path) -> set[str]:
    nombres: set[str] = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8-sig"))):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, ast.ImportFrom):
            nombres.update(a.name for a in nodo.names)
    return nombres


def _norm_paquete(nombre: str) -> str:
    return re.sub(r"[-_.]+", "-", nombre).lower()


def comprobar_evidencia(raiz: Path, item: str, *, uso: bool = False) -> str | None:
    """None si el código declara ``item``; si no, el motivo.

    Formas: ``ruta.py::nombre`` (definido en el módulo, o usado si ``uso``), ``pyproject.toml::dep:paquete``
    (dependencia obligatoria), ``ruta::palabra`` (la palabra está en un fichero que no es Python) y ``ruta~texto``
    (el texto literal está en el fichero).
    """
    if "::" in item:
        ruta, nombre = item.split("::", 1)
        literal = False
    elif "~" in item:
        ruta, nombre = item.split("~", 1)
        literal = True
    else:
        return f"«{item}» no tiene la forma ruta::nombre ni ruta~texto"
    destino = _ruta_segura(raiz, ruta)
    if destino is None:
        return f"«{item}»: la ruta debe ser relativa al repositorio"
    if not nombre:
        return f"«{item}»: falta el nombre o el texto"
    if not destino.is_file():
        return f"«{item}»: no existe {ruta}"
    if literal:
        return None if nombre in destino.read_text(encoding="utf-8-sig") else f"«{item}»: el texto no está en {ruta}"
    if nombre.startswith("dep:"):
        if destino.name != "pyproject.toml":
            return f"«{item}»: «dep:» solo vale en pyproject.toml"
        try:
            deps = tomllib.loads(destino.read_text(encoding="utf-8")).get("project", {}).get("dependencies", [])
        except tomllib.TOMLDecodeError as exc:
            return f"«{item}»: pyproject.toml no se puede leer ({exc})"
        buscado = _norm_paquete(nombre[4:])
        nombres = {_norm_paquete(re.split(r"[\s\[<>=!~;]", d, maxsplit=1)[0]) for d in deps}
        return None if buscado in nombres else f"«{item}»: {nombre[4:]} no es dependencia obligatoria"
    if destino.suffix == ".py":
        try:
            nombres = _usados_py(destino) if uso else _definidos_py(destino)
        except SyntaxError as exc:
            return f"«{item}»: {ruta} no se puede analizar ({exc.msg}, línea {exc.lineno})"
        verbo = "no usa" if uso else "no define"
        return None if nombre in nombres else f"«{item}»: {ruta} {verbo} {nombre}"
    texto = destino.read_text(encoding="utf-8-sig")
    return None if re.search(r"(?<!\w)" + re.escape(nombre) + r"(?!\w)", texto) else f"«{item}»: no está en {ruta}"


def problemas_adr(adr: dict, raiz: Path, elementos_c4: set[str], ids_adr: set[str]) -> list[str]:
    """034:RF-36, 034:RF-38, 034:RF-39 y 034:RF-41: formato, citas, elementos C4 y estado frente al código."""
    nombre = adr["ruta"].name
    if adr["id"] is None:
        return [f"{nombre}: falta la cabecera «# ADR-NNN · título»"]
    p = [f"{adr['id']}: {x}" for x in _problemas_adr(adr, raiz, elementos_c4, ids_adr)]
    if not nombre.startswith(adr["id"] + "-"):
        p.append(f"{adr['id']}: el fichero {nombre} no empieza por su identificador")
    return p


def _problemas_adr(adr: dict, raiz: Path, elementos_c4: set[str], ids_adr: set[str]) -> list[str]:
    p: list[str] = []
    campos, secciones = adr["campos"], adr["secciones"]
    for campo in CAMPOS_ADR:
        if not campos.get(campo):
            p.append(f"falta el campo «{campo}»")
    for seccion in SECCIONES_ADR:
        if not secciones.get(seccion):
            p.append(f"falta la sección «{seccion}» o está vacía")
    estado = (campos.get("Estado") or "").split(" ")[0].strip(".,;")
    if estado and estado not in ESTADOS_ADR:
        p.append(f"estado «{estado}» desconocido; vale {', '.join(ESTADOS_ADR)}")
    if campos.get("Fecha") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", campos["Fecha"]):
        p.append(f"la fecha «{campos['Fecha']}» no es AAAA-MM-DD")
    specs = campos.get("Specs", "")
    if specs and not (_CITA_RF.search(specs) or _CITA_SPEC.search(specs)):
        p.append("«Specs» no cita ningún NNN:RF-n ni «spec NNN»")
    for numero, rf in _CITA_RF.findall(specs):
        s = _spec(raiz, numero)
        if s is None:
            p.append(f"cita {numero}:RF-{rf}, y la spec {numero} no existe")
        elif rf not in s.definiciones:
            p.append(f"cita {numero}:RF-{rf}, que la spec {numero} no define")
    for numero in _CITA_SPEC.findall(specs):
        if _spec(raiz, numero) is None:
            p.append(f"cita la spec {numero}, que no existe")
    for elemento in (e.strip() for e in campos.get("Elementos C4", "").split(",")):
        if elemento and elemento not in elementos_c4:
            p.append(f"nombra el elemento C4 «{elemento}», que no está en el AS-IS ni en la TO-BE")
    tareas, abiertas = [], []
    for numero, tarea in _CITA_TAREA.findall(campos.get("Tareas", "")):
        s = _spec(raiz, numero)
        encontrada = next((t for t in s.tareas if t.id == tarea), None) if s else None
        if encontrada is None:
            p.append(f"cita la tarea {numero} {tarea}, que no existe")
            continue
        tareas.append(f"{numero} {tarea}")
        if not encontrada.hecha:
            abiertas.append(f"{numero} {tarea}")
    evidencias = [(i, False) for i in _ITEM.findall(campos.get("Evidencia", ""))]
    evidencias += [(i, True) for i in _ITEM.findall(campos.get("Consumidores", ""))]
    faltan = [m for m in (comprobar_evidencia(raiz, i, uso=u) for i, u in evidencias) if m]
    mal_formadas = [m for m in faltan if "no tiene la forma" in m or "relativa" in m or "falta el nombre" in m
                    or "solo vale en" in m or "no se puede" in m]
    p.extend(mal_formadas)
    if estado == "vigente":
        p.extend(f"vigente, pero {m}" for m in faltan if m not in mal_formadas)
        p.extend(f"vigente, pero la tarea {t} está abierta" for t in abiertas)
        if not evidencias and not tareas:
            p.append("vigente sin «Evidencia» ni «Tareas»: nada lo ata al código")
    elif estado == "pendiente":
        if not campos.get("Pendiente en"):
            p.append("pendiente sin «Pendiente en» (qué tarea o qué trabajo lo cierra)")
        if not evidencias and not tareas:
            p.append("pendiente sin «Evidencia» esperada ni «Tareas»: no se sabría cuándo está hecho")
        elif not faltan and not abiertas:
            p.append("desfasado: el código ya declara toda su evidencia y sus tareas están cerradas; pase a vigente")
    elif estado == "sustituida":
        otro = re.search(r"ADR-\d{3}", campos.get("Sustituida por", ""))
        if not otro or otro.group(0) not in ids_adr:
            p.append("sustituida sin «Sustituida por» con un ADR que exista")
    elif estado == "retirada" and not campos.get("Motivo"):
        p.append("retirada sin «Motivo»")
    return p


def problemas_adr_y_to_be(to_be: str, adrs: list[dict]) -> list[str]:
    """034:RF-37: cada elemento nuevo de la TO-BE cita un ADR, y ese ADR lo nombra; ningún ADR se repite."""
    p: list[str] = []
    por_id = {a["id"]: a for a in adrs if a["id"]}
    for nombre, propio in elementos_dsl(to_be).items():
        citas = _PROPIEDAD_ADR.findall(propio)
        if not citas:
            p.append(f"el elemento «{nombre}» de la TO-BE no cita ningún ADR")
        for cita in citas:
            adr = por_id.get(cita)
            if adr is None:
                p.append(f"el elemento «{nombre}» cita {cita}, que no existe")
            elif nombre not in {e.strip() for e in adr["campos"].get("Elementos C4", "").split(",")}:
                p.append(f"el elemento «{nombre}» cita {cita}, que no lo nombra en «Elementos C4»")
    vistos: dict[str, Path] = {}
    for a in adrs:
        if a["id"] is None:
            continue
        if a["id"] in vistos:
            p.append(f"{a['id']} está repetido: {vistos[a['id']].name} y {a['ruta'].name}")
        vistos[a["id"]] = a["ruta"]
    return p


def _todos_los_problemas(raiz: Path, as_is: str, to_be: str, carpeta_adr: Path) -> list[str]:
    adrs = leer_adrs(carpeta_adr) if carpeta_adr.is_dir() else []
    if not adrs:
        return [f"no hay ningún ADR en {carpeta_adr}"]
    elementos = set(elementos_dsl(as_is)) | set(elementos_dsl(to_be))
    ids = {a["id"] for a in adrs if a["id"]}
    salida = problemas_to_be(as_is, to_be, raiz) + problemas_adr_y_to_be(to_be, adrs)
    for a in adrs:
        salida += problemas_adr(a, raiz, elementos, ids)
    return salida


def test_to_be_extends_as_is_model_without_redefining_it():
    """034:RF-34 y 034:RF-35 — la TO-BE extiende el mismo modelo, no redefine nada y solo relaciona lo que existe."""
    assert TOBE.is_file(), f"034:RF-34: falta el C4 TO-BE {TOBE.relative_to(ROOT)}"
    problemas = problemas_to_be(DSL.read_text(encoding="utf-8"), TOBE.read_text(encoding="utf-8"), ROOT)
    assert problemas == []


def test_every_new_to_be_element_cites_an_adr_that_names_it():
    """034:RF-37 — elemento nuevo de la TO-BE → ADR que lo nombra; ningún ADR repetido."""
    assert TOBE.is_file() and ADR_DIR.is_dir(), "034:RF-37: faltan la TO-BE o la carpeta de ADR"
    adrs = leer_adrs(ADR_DIR)
    assert adrs, "034:RF-36: no hay ningún ADR"
    assert problemas_adr_y_to_be(TOBE.read_text(encoding="utf-8"), adrs) == []


def test_adrs_are_complete_and_coherent_with_the_code():
    """034:RF-36, 034:RF-38, 034:RF-39 y 034:RF-41 — formato, citas y estado de cada ADR frente al código."""
    assert ADR_DIR.is_dir(), "034:RF-36: falta docs/architecture/adr"
    to_be = TOBE.read_text(encoding="utf-8") if TOBE.is_file() else ""
    assert _todos_los_problemas(ROOT, DSL.read_text(encoding="utf-8"), to_be, ADR_DIR) == []


def test_adrs_record_todays_boundary_decisions():
    """034:RF-36 — las decisiones de frontera del 2026-11-14 tienen su ADR, reconocido por la evidencia que cita.

    La evidencia se comprueba contra el código en ``test_adrs_are_complete_and_coherent_with_the_code``.
    """
    assert ADR_DIR.is_dir(), "034:RF-36: falta docs/architecture/adr"
    evidencias = [a["campos"].get("Evidencia", "") + a["campos"].get("Consumidores", "") for a in leer_adrs(ADR_DIR)]
    decisiones = {
        "escritura duradera del estado": "src/convertersmartgrid/dominio/util.py::publicar_duradero",
        "DXF garantizado y .dwg opcional": "pyproject.toml::dep:ezdxf",
        "avisos en lugar de excepciones mudas": "docs/architecture/adr/deuda_excepciones_mudas.json",
    }
    assert [d for d, e in decisiones.items() if not any(e in texto for texto in evidencias)] == []


# ---------------------------------------------------------------- los detectores, contra defectos sembrados
def _repo_sintetico(raiz: Path) -> None:
    (raiz / "specs" / "900-x").mkdir(parents=True)
    (raiz / "specs" / "900-x" / "spec.md").write_text(
        "# Spec 900\n\nEstado: aprobada\n\n- RF-1: EL SISTEMA hará algo.\n", encoding="utf-8")
    (raiz / "specs" / "900-x" / "tasks.md").write_text(
        "- [x] T1. Hecha. (RF-1)\n- [ ] T2. Abierta. (RF-1)\n", encoding="utf-8")
    (raiz / "src").mkdir()
    (raiz / "src" / "m.py").write_text(
        "from os import replace\n\nLIMITE = 3\n\n\ndef publicar():\n    replace\n", encoding="utf-8")
    (raiz / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["ezdxf>=1.3"]\n', encoding="utf-8")


_AS_IS_MIN = ('workspace "x" {\n  model {\n    s = softwareSystem "S" {\n      api = container "API" {\n      }\n'
              '    }\n  }\n  views {\n    container s "Containers" {\n      include *\n    }\n  }\n}\n')
_TO_BE_MIN = ('workspace extends workspace.dsl {\n  model {\n    !element s {\n      cad = container "CAD" {\n'
              '        properties {\n          "ADR" "ADR-001"\n        }\n      }\n    }\n    cad -> api "Usa"\n  }\n'
              '  views {\n    container s "ToBe" {\n      include *\n    }\n  }\n}\n')


def _adr(carpeta: Path, nombre: str, estado: str, *, extra: str = "", quitar: str = "") -> None:
    texto = (f"# {nombre[:7]} · Prueba\n\n- Estado: {estado}\n- Fecha: 2026-11-14\n- Specs: 900:RF-1\n"
             f"- Elementos C4: api, cad\n{extra}\n")
    for seccion in SECCIONES_ADR:
        if seccion != quitar:
            texto += f"## {seccion}\n\nTexto.\n\n"
    carpeta.mkdir(exist_ok=True)
    (carpeta / nombre).write_text(texto, encoding="utf-8")


@pytest.mark.parametrize("estado, extra, quitar, esperado", [
    ("vigente", "- Evidencia: `src/m.py::publicar`, `src/m.py::LIMITE`\n- Tareas: 900 T1", "", None),
    ("vigente", "- Evidencia: `src/m.py::borrar`", "", "src/m.py no define borrar"),
    ("vigente", "- Evidencia: `src/falta.py::f`", "", "no existe src/falta.py"),
    ("vigente", "- Evidencia: `src/m.py~LIMITE = 3`", "", None),
    ("vigente", "- Evidencia: `src/m.py~LIMITE = 4`", "", "el texto no está en src/m.py"),
    ("vigente", "- Consumidores: `src/m.py::replace`", "", None),
    ("vigente", "- Consumidores: `src/m.py::rename`", "", "src/m.py no usa rename"),
    ("vigente", "- Tareas: 900 T2", "", "la tarea 900 T2 está abierta"),
    ("vigente", "- Tareas: 900 T9", "", "la tarea 900 T9, que no existe"),
    ("vigente", "", "", "nada lo ata al código"),
    ("vigente", "- Evidencia: `D:/repo/src/m.py::f`", "", "relativa al repositorio"),
    ("vigente", "- Evidencia: `../fuera.py::f`", "", "relativa al repositorio"),
    ("vigente", "- Evidencia: `src/m.py`", "", "no tiene la forma"),
    ("vigente", "- Evidencia: `src/m.py::dep:ezdxf`", "", "«dep:» solo vale en pyproject.toml"),
    ("vigente", "- Evidencia: `src/m.py::publicar`", "Vuelta atrás", "falta la sección «Vuelta atrás»"),
    ("pendiente", "- Evidencia: `pyproject.toml::dep:ezdxf`\n- Tareas: 900 T1\n- Pendiente en: 900 T1", "",
     "desfasado"),
    ("pendiente", "- Evidencia: `pyproject.toml::dep:noexiste`\n- Pendiente en: 900 T2", "", None),
    ("pendiente", "- Tareas: 900 T2\n- Pendiente en: 900 T2", "", None),
    ("pendiente", "- Tareas: 900 T2", "", "sin «Pendiente en»"),
    ("pendiente", "- Pendiente en: algo", "", "no se sabría cuándo está hecho"),
    ("sustituida", "- Sustituida por: ADR-777\n- Evidencia: `src/m.py::LIMITE`", "", "sin «Sustituida por»"),
    ("retirada", "- Evidencia: `src/m.py::LIMITE`", "", "retirada sin «Motivo»"),
    ("propuesta", "- Evidencia: `src/m.py::LIMITE`", "", "estado «propuesta» desconocido"),
])
def test_adr_checker_detects_each_seeded_defect(tmp_path, estado, extra, quitar, esperado):
    """034:RF-38, 034:RF-39 y 034:RF-41 — cada defecto sembrado sale nombrado; el ADR sano, sin ninguno."""
    _repo_sintetico(tmp_path)
    _adr(tmp_path / "adr", "ADR-001-prueba.md", estado, extra=extra, quitar=quitar)
    problemas = _todos_los_problemas(tmp_path, _AS_IS_MIN, _TO_BE_MIN, tmp_path / "adr")
    if esperado is None:
        assert problemas == []
    else:
        assert any(esperado in x for x in problemas), problemas


def test_adr_checker_flags_bad_citations_and_unknown_elements(tmp_path):
    """034:RF-41 y 034:RF-37 — RF o spec inexistentes, elemento desconocido, sin cabecera, repetido y sin ADR."""
    _repo_sintetico(tmp_path)
    carpeta = tmp_path / "adr"
    _adr(carpeta, "ADR-001-prueba.md", "vigente", extra="- Evidencia: `src/m.py::LIMITE`")
    texto = (carpeta / "ADR-001-prueba.md").read_text(encoding="utf-8")
    texto = texto.replace("900:RF-1", "900:RF-7, spec 901").replace("Elementos C4: api", "Elementos C4: api, fantasma")
    (carpeta / "ADR-001-prueba.md").write_text(texto, encoding="utf-8")
    (carpeta / "ADR-001-copia.md").write_text(texto, encoding="utf-8")
    (carpeta / "ADR-002-sin-cabecera.md").write_text("Sin cabecera.\n", encoding="utf-8")
    problemas = "\n".join(_todos_los_problemas(tmp_path, _AS_IS_MIN, _TO_BE_MIN, carpeta))
    for esperado in ("900:RF-7, que la spec 900 no define", "la spec 901, que no existe", "«fantasma»",
                     "ADR-001 está repetido", "ADR-002-sin-cabecera.md: falta la cabecera"):
        assert esperado in problemas
    assert _todos_los_problemas(tmp_path, _AS_IS_MIN, _TO_BE_MIN, tmp_path / "vacia") == [
        f"no hay ningún ADR en {tmp_path / 'vacia'}"]


@pytest.mark.parametrize("to_be, esperado", [
    (_TO_BE_MIN, None),
    ("", "la TO-BE está vacía"),
    ("// solo un comentario\n", "la TO-BE está vacía"),
    (_TO_BE_MIN.replace("workspace extends workspace.dsl", 'workspace "otro"'), "no extiende el mismo modelo"),
    (_TO_BE_MIN.replace('cad = container "CAD"', 'api = container "API"'), "redefine «api»"),
    (_TO_BE_MIN.replace("!element s", "!element t"), "amplía «t»"),
    (_TO_BE_MIN.replace('cad -> api "Usa"', 'cad -> nadie "Usa"'), "usa «nadie»"),
    (_TO_BE_MIN.replace('"ToBe"', '"Containers"'), "la vista «Containers» de la TO-BE ya es del AS-IS"),
    (_TO_BE_MIN.replace('container s "ToBe" {\n      include *\n    }\n', ''), "no tiene vistas propias"),
    (_TO_BE_MIN.replace('cad = container "CAD" {',
                        'cad = container "CAD" {\n url "https://github.com/a/b/blob/main/x.md"'),
     "no está fijado a una revisión"),
    (_TO_BE_MIN.replace('cad = container "CAD" {',
                        'cad = container "CAD" {\n url "https://github.com/a/b/blob/' + "0" * 40 + '/no/existe.md"'),
     "«no/existe.md», que no existe"),
])
def test_to_be_checker_detects_each_seeded_defect(tmp_path, to_be, esperado):
    """034:RF-34 y 034:RF-35 — cada defecto sembrado en la TO-BE sale nombrado; la TO-BE sana no da ninguno."""
    problemas = problemas_to_be(_AS_IS_MIN, to_be, tmp_path)
    if esperado is None:
        assert problemas == []
    else:
        assert any(esperado in x for x in problemas), problemas


def test_to_be_element_without_adr_or_with_foreign_adr_is_flagged(tmp_path):
    """034:RF-37 — un elemento nuevo sin ADR, con un ADR que no existe o con uno que no lo nombra."""
    _repo_sintetico(tmp_path)
    _adr(tmp_path / "adr", "ADR-001-prueba.md", "vigente", extra="- Evidencia: `src/m.py::LIMITE`")
    adrs = leer_adrs(tmp_path / "adr")
    assert problemas_adr_y_to_be(_TO_BE_MIN, adrs) == []
    sin = _TO_BE_MIN.replace('"ADR" "ADR-001"', '"Spec" "900"')
    assert "el elemento «cad» de la TO-BE no cita ningún ADR" in problemas_adr_y_to_be(sin, adrs)
    otro = _TO_BE_MIN.replace("ADR-001", "ADR-009")
    assert "el elemento «cad» cita ADR-009, que no existe" in problemas_adr_y_to_be(otro, adrs)
    adrs[0]["campos"]["Elementos C4"] = "api"
    assert any("que no lo nombra" in x for x in problemas_adr_y_to_be(_TO_BE_MIN, adrs))


def test_dsl_element_reader_keeps_only_each_element_own_block():
    """034:RF-37 — la propiedad ADR de un hijo no cuenta para su padre, ni la del padre para el hijo."""
    texto = ('a = container "A" {\n  properties {\n    "ADR" "ADR-001"\n  }\n'
             '  b = component "B" {\n    properties {\n      "ADR" "ADR-002"\n    }\n  }\n'
             '  c = component "C" "sin bloque"\n}\n')
    propios = elementos_dsl(texto)
    assert set(propios) == {"a", "b", "c"}
    assert _PROPIEDAD_ADR.findall(propios["a"]) == ["ADR-001"]
    assert _PROPIEDAD_ADR.findall(propios["b"]) == ["ADR-002"]
    assert propios["c"] == ""
    with pytest.raises(ValueError, match="llave sin cerrar"):
        elementos_dsl('a = container "A" {\n')


# ---------------------------------------------------------------- 034:RF-40: avisos, no excepciones mudas
def _es_amplia(tipo: ast.expr | None) -> bool:
    if tipo is None:
        return True
    if isinstance(tipo, ast.Name):
        return tipo.id in ("Exception", "BaseException")
    if isinstance(tipo, ast.Tuple):
        return any(_es_amplia(e) for e in tipo.elts)
    return False


def _calla(sentencia: ast.stmt) -> bool:
    if isinstance(sentencia, (ast.Pass, ast.Continue)):
        return True
    if isinstance(sentencia, ast.Expr) and isinstance(sentencia.value, ast.Constant):
        return sentencia.value.value is Ellipsis
    if isinstance(sentencia, ast.Return):
        return sentencia.value is None or (isinstance(sentencia.value, ast.Constant)
                                           and sentencia.value.value in (True, None))
    return False


def excepciones_mudas(texto: str) -> list[int]:
    """Líneas de los ``except`` amplios cuyo único cuerpo calla o da paso, sin «# justificado:» (ADR-005)."""
    lineas = texto.splitlines()
    salida = []
    for nodo in ast.walk(ast.parse(texto)):
        if isinstance(nodo, ast.ExceptHandler) and _es_amplia(nodo.type) and len(nodo.body) == 1 \
                and _calla(nodo.body[0]):
            tramo = "\n".join(lineas[nodo.lineno - 1:nodo.body[0].end_lineno])
            if "# justificado:" not in tramo:
                salida.append(nodo.lineno)
    return sorted(salida)


def recuento_mudas(raiz: Path) -> dict[str, list[int]]:
    salida: dict[str, list[int]] = {}
    for base in ("src", "tools"):
        for ruta in sorted((raiz / base).rglob("*.py")):
            if "__pycache__" in ruta.parts:
                continue
            lineas = excepciones_mudas(ruta.read_text(encoding="utf-8-sig"))
            if lineas:
                salida[ruta.relative_to(raiz).as_posix()] = lineas
    return salida


def excesos_mudas(recuento: dict[str, list[int]], deuda: dict[str, int]) -> list[str]:
    return [f"{f}: {len(ls)} excepciones mudas y la deuda admite {deuda.get(f, 0)} (líneas {', '.join(map(str, ls))})"
            for f, ls in sorted(recuento.items()) if len(ls) > deuda.get(f, 0)]


def test_silent_broad_excepts_do_not_grow_beyond_registered_debt():
    """034:RF-40 — ningún fichero de src/ o tools/ tiene más excepciones mudas que su deuda registrada (ADR-005)."""
    assert DEUDA_MUDAS.is_file(), "034:RF-40: falta la deuda de excepciones mudas del ADR-005"
    deuda = json.loads(DEUDA_MUDAS.read_text(encoding="utf-8"))
    assert deuda.get("version") == 1 and isinstance(deuda.get("ficheros"), dict)
    assert all(isinstance(n, int) and n > 0 for n in deuda["ficheros"].values())
    assert excesos_mudas(recuento_mudas(ROOT), deuda["ficheros"]) == []


@pytest.mark.parametrize("codigo, mudas", [
    ("try:\n    x()\nexcept Exception:\n    pass\n", [3]),
    ("try:\n    x()\nexcept:\n    ...\n", [3]),
    ("for i in r:\n    try:\n        x()\n    except (ValueError, Exception):\n        continue\n", [4]),
    ("def f():\n    try:\n        x()\n    except BaseException:\n        return True\n", [4]),
    ("def f():\n    try:\n        x()\n    except Exception:\n        return None\n", [4]),
    ("def f():\n    try:\n        x()\n    except Exception:\n        return\n", [4]),
    ("try:\n    x()\nexcept Exception:  # justificado: limpieza al salir\n    pass\n", []),
    ("try:\n    x()\nexcept Exception:\n    pass  # justificado: limpieza al salir\n", []),
    ("try:\n    x()\nexcept OSError:\n    pass\n", []),
    ("def f():\n    try:\n        x()\n    except Exception:\n        return False\n", []),
    ("try:\n    x()\nexcept Exception as exc:\n    avisos.append(str(exc))\n", []),
    ("try:\n    x()\nexcept Exception:\n    log()\n    pass\n", []),
    ("try:\n    x()\nexcept Exception:  # noqa: BLE001\n    pass\n", [3]),
    ("", []),
])
def test_silent_except_detector_on_seeded_code(codigo, mudas):
    """034:RF-40 — el detector cuenta lo que calla y deja pasar lo que avisa, lo estrecho y lo justificado."""
    assert excepciones_mudas(codigo) == mudas


def test_silent_except_excess_names_file_and_lines(tmp_path):
    """034:RF-40 — un fichero nuevo con una muda, o uno que pasa de su deuda, sale con su ruta y su línea."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "src" / "a.py").write_text("try:\n    x()\nexcept Exception:\n    pass\n", encoding="utf-8")
    (tmp_path / "tools" / "b.py").write_text("x = 1\n", encoding="utf-8")
    recuento = recuento_mudas(tmp_path)
    assert recuento == {"src/a.py": [3]}
    assert excesos_mudas(recuento, {}) == ["src/a.py: 1 excepciones mudas y la deuda admite 0 (líneas 3)"]
    assert excesos_mudas(recuento, {"src/a.py": 1}) == []
