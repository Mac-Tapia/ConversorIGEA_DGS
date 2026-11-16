"""111:RF-16 — web de prueba para los recorridos en navegador real, aislada y con la seguridad real.

La lanza ``preparar.mjs``; no forma parte del producto ni de la suite de Python.
- Carpeta temporal propia (runtime, caché, temporales, asistente y sesiones): no toca el perfil del usuario.
- Un espacio con un export SINTÉTICO sorteado (``tests/synthetic_export.py``, ``ExportSpec(seed=…)``), con un número de
  alimentadores dado y la disposición sorteada con la misma semilla; cargado con su georreferenciación y convertido con
  la vista previa, como lo haría el operador.
- Sin GPU. Las teselas de fondo siguen ``CSG_SALIDA_TESELAS`` del entorno; el navegador las sirve en local.
Uso: python -I web_de_prueba.py <raíz del repositorio> <carpeta temporal> <puerto> <semilla> <alimentadores>
  → una línea «LISTA {json}» con la base, la url de entrada (con la sesión), el espacio y los alimentadores.
"""
import json
import os
import random
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

RAIZ, TMP = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
PUERTO, SEMILLA, N_ALIM = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
TMP.mkdir(parents=True, exist_ok=True)
for var, sub in (("CSG_RUNTIME_HOME", "runtime"), ("CSG_CACHE_HOME", "cache"), ("CSG_TEMP_HOME", "temp"),
                 ("CSG_ASISTENTE_DATA", "asistente"), ("CSG_WEB_SESIONES", "sesiones")):
    os.environ[var] = str(TMP / sub)
    (TMP / sub).mkdir(parents=True, exist_ok=True)
os.environ["CSG_WEB_FRONTEND"] = str(RAIZ / "frontend" / "dist")
os.environ["CSG_WEB_PUERTO"] = str(PUERTO)
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "tests")]
os.chdir(RAIZ)

import uvicorn  # noqa: E402

from synthetic_export import CRS_SINTETICO, ExportSpec, write_export  # noqa: E402
from convertersmartgrid import sesion_web  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402

assert sesion_web.EXIGIR_SEGURIDAD, "la web de prueba corre con la seguridad encendida"
sesion = sesion_web.crear_sesion(PUERTO)
app = create_app(TMP / "web")
BASE = f"http://127.0.0.1:{PUERTO}"
servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PUERTO, log_level="warning"))
threading.Thread(target=servidor.run, daemon=True).start()
for _ in range(240):
    if servidor.started:
        break
    time.sleep(0.25)


def pedir(metodo, ruta, *, datos=None, cuerpo=None, tipo=None):
    cab = sesion_web.cabeceras_locales(BASE)
    if tipo:
        cab["Content-Type"] = tipo
    elif datos is not None:
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + ruta, method=metodo, headers=cab,
                                 data=cuerpo if cuerpo is not None else (json.dumps(datos).encode() if datos is not None else None))
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read() or b"null")


def subir(wid, slot, ruta):
    limite = uuid.uuid4().hex
    cuerpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{ruta.name}\"\r\n"
              f"Content-Type: application/octet-stream\r\n\r\n").encode() + ruta.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    return pedir("POST", f"/api/workspaces/{wid}/inputs/{slot}", cuerpo=cuerpo, tipo=f"multipart/form-data; boundary={limite}")


def esperar(job):
    for _ in range(2400):
        j = pedir("GET", f"/api/jobs/{job['id']}")
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise TimeoutError(job)


disposicion = random.Random(SEMILLA).choice(("reducido", "completo"))
wid = pedir("POST", "/api/workspaces")["id"]
red, cargas, equipo = write_export(ExportSpec(feeders=N_ALIM, seed=SEMILLA, layout=disposicion), TMP / "export")
for slot, ruta in (("red", red), ("loads", cargas), ("equipment", equipo)):
    subir(wid, slot, ruta)
pedir("PUT", f"/api/workspaces/{wid}/options", datos={"include_geography": True, "source_crs": CRS_SINTETICO, "write_preview": True})
carga = esperar(pedir("POST", f"/api/workspaces/{wid}/load"))
assert carga["status"] == "done", carga
alimentadores = [f["feeder"] for f in pedir("GET", f"/api/workspaces/{wid}/feeders")["feeders"]]
conv = esperar(pedir("POST", f"/api/workspaces/{wid}/convert", datos={"feeders": alimentadores}))
assert conv["status"] in ("done", "parcial"), conv
print("LISTA " + json.dumps({"base": BASE, "entrada": sesion_web.url_de_entrada(f"{BASE}/?espacio={wid}"), "espacio": wid,
                             "alimentadores": alimentadores, "disposicion": disposicion, "conversion": conv["status"]},
                            ensure_ascii=False), flush=True)
while True:
    time.sleep(3600)
