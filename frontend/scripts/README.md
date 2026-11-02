# Compilación preservada — spec 065

Instalar con `npm ci` y ejecutar `npm test`, `npm run typecheck`, `npm run build`.
`package-lock.json` fija la instalación; `engines` y `.npmrc` rechazan Node/npm
incompatibles. `packageManager` identifica la versión con que se verificó el lock.

`runtime-paths.mjs` mantiene el contrato de `convertersmartgrid.runtime_paths`:
SHA256 de la ruta real del checkout (Windows: `/` y minúsculas), primeros 16 caracteres.
`CSG_RUNTIME_HOME` y `CSG_CACHE_HOME` son raíces externas explícitas. Sin variables,
runtime usa `primary_repo.parent/.convertersmartgrid-runtime/<hash>` y caché usa
`LOCALAPPDATA/ConverterSmartGrid/<hash>/cache` (XDG o `~/.cache` fuera de Windows).
El checkout primario se obtiene de `git-common-dir`: un worktree anidado no puede
colocar staging dentro del repositorio primario. Sin Git se requiere runtime explícito.
Se resuelven enlaces antes de rechazar raíces interiores; runtime debe compartir
volumen con `dist`. El caché puede vivir en otro volumen.

`build.mjs` ejecuta TypeScript sin emisión ni incremental y Vite con config loader
`runner`, sin `.vite-temp`. El staging se crea bajo runtime por checkout y ejecución;
solo `dist` es durable dentro del proyecto. No modifica `node_modules` ni borra fuentes.
Antes de publicar ejecuta el validador canónico `web/runtime.py --validate-dist` con
Python aislado (`-I -B`, solo stdlib): `CSG_PYTHON`, `.venv` del checkout primario o
`python` de PATH. Rechaza referencias locales faltantes usando la misma regla del
lanzador; un paquete Python instalado de otro worktree no interviene.
Un bloqueo serializa builds del mismo checkout. Tras compilar se mueve `dist` completo
a respaldo, luego se renombra la salida completa a `dist`; si falla, se restituye el
respaldo. Windows no sustituye directorios no vacíos con un solo rename: existe una
ventana breve sin `dist`, nunca un árbol parcialmente copiado. Una interrupción en esa
ventana conserva el respaldo externo y el diario para restaurarlo en el siguiente build.
Si no puede restaurarlo se informa su ruta y se conserva para revisión. No se borra una
publicación desconocida, ni se pretende aceptación eléctrica por estas comprobaciones.

Las pruebas crean fixtures propios externos y eliminan solo su carpeta. Para conservar
logs o elegir una raíz sin espacios: `CSG_TEST_HOME=<directorio externo existente>`.
La suite prueba rutas con/sin espacios, fallo TypeScript, fallo real Vite `writeBundle`,
rollback por error real del sistema de archivos, recuperación y raíces de worktrees.

El fundamento combina conformidad observable y control de dependencias: la tesis de
maestría de [Jan Thomas (RWTH, 2017)](https://swc-rwth.de/theses/software-architecture-conformance-analysis-large-scale-industrial-case-study/)
compara verificaciones estáticas y de comportamiento; la tesis doctoral de
[Lakshitha de Silva (St Andrews, 2014)](https://research-repository.st-andrews.ac.uk/handle/10023/5220)
estudia conformidad durante la ejecución; y
[Zimmermann et al. (USENIX Security, 2019)](https://arxiv.org/abs/1902.09217),
[indexado en DBLP](https://dblp.org/rec/conf/uss/ZimmermannSTP19.html), analiza
riesgos de dependencias npm. Motivan verificar comportamiento y versiones; no
certifican este producto. Consulta web: 2026-11-02. Las versiones concretas se
contrastaron con [Vite 6.4.5](https://github.com/vitejs/vite/blob/v6.4.5/packages/vite/CHANGELOG.md)
y [source-map-js 1.2.2](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2),
y la auditoría reproducible del lock se conserva como evidencia externa.
