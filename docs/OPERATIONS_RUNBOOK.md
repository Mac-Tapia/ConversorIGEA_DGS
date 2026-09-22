# Runbook operativo

1. Ejecute `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1` y luego `scripts/verify.ps1`.
2. Copie a una carpeta nueva exactamente los TXT RED, CARGA y BD_Equipo del mismo export y estudio.
3. Ejecute `scripts/acceptance.ps1 -InputDir <carpeta> -OutputDir output\acceptance_<run_id>`.
4. Si G1–G4 aprueban, importe únicamente el DGS recién publicado mediante la API siguiendo `POWERFACTORY_ACCEPTANCE.md`. No se usa como entrada ningún DGS previo.
5. Compare G5 con objetos efectivos. Ejecute ComLdf en el caso original sin correcciones. Cualquier diagnóstico se hace en una copia con nombre trazable.
6. ComShc se ejecuta solo si existen impedancias y potencia de cortocircuito de fuente. Registre por separado falta de datos y falta de licencia.

Salida 0 significa aprobado; 2, bloqueado por datos/puerta; 3, API o etapa no disponible. Conserve manifiesto, hashes, diagnósticos y directorio de corrida. No reemplace valores faltantes por defaults.

Estado local 2026-09-22: `referencia` contiene solo `NA205.dgs`; por ello la aceptación TXT real está bloqueada en G1 (`INPUT_TXT_MISSING`) y PowerFactory no debe ejecutarse con ese DGS histórico.
