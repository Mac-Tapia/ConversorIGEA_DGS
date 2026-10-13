# Diseño del contrato universal de carga y validación nativa

**Fecha:** 2026-10-13

**Estado:** aprobado en conversación el 2026-10-13

**Alcance:** TXT, MDB y VNR-GIS; modelo canónico; DGS y sidecar; importación,
calibración y estudios nativos en DIgSILENT PowerFactory 2024.

## 1. Objetivo

Aplicar una sola vez, en el núcleo común, las correcciones comprobadas durante el
caso CA101. Cada carga de una fuente TXT, MDB o VNR-GIS debe evaluar el mismo
contrato y producir las mismas garantías. Ninguna regla de bancos, clientes,
escalado, cuadre o aceptación puede tener una implementación por modalidad.

El resultado debe probar cuatro estados distintos:

1. la fuente fue custodiada y normalizada;
2. el DGS conserva el modelo canónico y su procedencia;
3. PowerFactory persistió y releyó los objetos esperados;
4. el flujo nativo produjo resultados eléctricos observables.

Un comando que termina sin excepción no demuestra por sí solo ninguno de los tres
estados posteriores.

## 2. Decisión arquitectónica

Se conserva la arquitectura existente de adaptadores, pero sus salidas se someten
a un contrato canónico único:

```text
TXT ─┐
MDB ─┼─> SourceAdapter ─> CymdistDataset ─> contrato universal
VNR ─┘                                      │
                                             ├─> DGS + sidecar + hashes
                                             └─> inventario y dictamen por feeder
                                                        │
                                                        v
                                             PowerFactory nativo
                                             importación + relectura
                                                        │
                                                        v
                                             ajuste + ComLdf + estudios
```

Las diferencias de formato terminan al salir del adaptador. A partir de
`CymdistDataset`, todas las fuentes usan las mismas funciones, estados, informes y
pruebas.

## 3. Invariantes universales

- No se codifican `CA101`, nombres de empresa, rutas locales ni cantidades de
  equipos de una red concreta.
- Cada artefacto pertenece a un único `source_run_id`, `source_mode` y
  `source_fingerprint`.
- Cada objeto eléctrico pertenece a un alimentador exacto o queda declarado como
  ambiguo; no se elige por proximidad de nombre.
- La fuente original nunca se modifica.
- Las correcciones se escriben sobre una variación o escenario controlado, salvo
  los metadatos de custodia creados durante la importación.
- Toda mutación PowerFactory tiene preflight, plan identificable, escritura,
  relectura y rollback informado.
- Una diferencia de kVAR no bloquea el cuadre de demanda; una discrepancia de
  identidad, mes o persistencia sí lo bloquea.
- Una subtensión, sobrecarga o no convergencia nunca se convierte en éxito por un
  cambio de etiqueta.

## 4. Evaluación obligatoria al cargar una fuente

`load_dataset` ejecutará el contrato después de que el adaptador produzca el
`CymdistDataset` y antes de publicar el inventario. El contrato devuelve un
`UniversalSourceAudit` con:

- identidad y huella de la ejecución fuente;
- alimentadores descubiertos y sus `NetworkID`;
- propiedad de tramos, cargas, SED, fuentes y bancos;
- cargas sin ubicación, duplicadas o con alimentador ambiguo;
- fases, P, Q, FP, kVA y origen de cada valor disponible;
- bancos sin nodo, alimentador, fases o potencia válida;
- conteos por clase y por alimentador;
- bloqueos de datos y avisos no bloqueantes.

Este dictamen se estampa en el inventario, el manifiesto de conversión y el sidecar.
La reconstrucción puede completar datos según la política vigente, pero cada valor
derivado conserva su procedencia y no reemplaza silenciosamente el original.

## 5. Bancos de condensadores

### 5.1 Modelo común

El modelo del conversor incorporará `CapacitorBank` con, como mínimo:

- identificador y nombre;
- nodo de conexión;
- alimentador y `NetworkID`;
- fases o tecnología de conexión;
- potencia nominal por escalón en kVAR;
- número máximo y número activo de escalones;
- tensión nominal y estado de servicio;
- procedencia del valor y regla que lo normalizó.

TXT, MDB y VNR-GIS mapearán sus campos a esa estructura. El puente VNR no podrá
descartar los objetos `CanonicalModel.capacitors`.

### 5.2 Potencia exclusivamente de origen

No existe potencia nominal predeterminada, normalizada ni inferida para un banco.
El sistema conserva exactamente la capacidad que declare la fuente original, junto
con sus fases, tecnología de conexión y escalones. La potencia instalada total solo
se calcula como `qcapn × ncapa` cuando ambos valores proceden de la fuente.

Si la fuente identifica un banco pero no declara una capacidad válida, el objeto se
conserva en el inventario como incompleto, no se crea un `ElmShnt` con una potencia
inventada y el dictamen registra `MISSING_CAPACITOR_CAPACITY`. La conversión puede
conservar el resto de la red, pero no se declara completa la aceptación nativa del
banco ni los estudios que dependan de su compensación reactiva.

### 5.3 DGS, metadata y relectura

El escritor común generará `ElmShnt`, su cubículo y su FID. El sidecar incluirá
`ElmShnt` entre las clases con `p:alimentador`. La aceptación nativa releerá:

- `ctech`, `shtype`, `qcapn`, `ncapx`, `ncapa`, `ushnm` y `outserv`;
- barra/cubículo y alimentador;
- potencia nominal por escalón y total activa.

Una diferencia entre plan y relectura es un bloqueo de persistencia, no un aviso.

## 6. Custodia del proyecto PowerFactory

Al terminar la importación se guardará un `PowerFactoryProjectBinding` con:

- proyecto y carpeta nativos;
- target DGS y SHA-256;
- sidecar y SHA-256;
- ejecución, modo y fingerprint de fuente;
- alimentadores incluidos;
- hash del inventario nativo de identidades y conexiones;
- evidencia de guardado, reapertura, relectura y `ComLdf`.

Antes de cargas, ajuste de cabecera, verificación, obras, estudios o transferencia,
el servicio exigirá que el proyecto elegido coincida con ese binding y con el run
activo. El guion nativo recalculará el inventario por identidad PowerFactory y
rechazará un proyecto distinto aunque tenga el mismo nombre visible.

La identidad nativa será `GetFullName()` más clase; no se usará `id(wrapper)` cuando
PowerFactory entregue wrappers diferentes para el mismo objeto.

## 7. Mes de la máxima y clientes importantes

Cada máximo de cabecera conserva su timestamp y periodo `AAAA-MM`. El catálogo de
clientes conserva también el periodo del libro activo. Al construir un plan:

- si existe libro de clientes, su periodo debe coincidir con el periodo del máximo;
- si no se puede demostrar el periodo, el ajuste con clientes fijos se bloquea;
- si no se proporcionó libro de clientes, se permite repartir todas las SED por kVA
  y se deja el aviso existente;
- el informe guarda libro, hoja, periodo, fingerprint y criterio de selección.

Con ello, una coincidencia por NIS o SED no se presenta como prueba de coincidencia
temporal.

## 8. Potencia de clientes importantes

Para cada cliente importante del mes seleccionado:

```text
P_kW = Pot
tan(phi) = ERI / EA
Q_kvar = P_kW * tan(phi)
FP = P_kW / hypot(P_kW, Q_kvar)
```

Si EA o ERI no existe o EA es cero, se usa el FP de la cabecera y se identifica el
cliente afectado. Las sumas se realizan por SED.

En PowerFactory:

- las SED con clientes importantes reciben P y Q calculados y quedan fijas;
- las demás SED se distribuyen por kVA instalado;
- el kVA se obtiene primero del transformador nativo y después del modelo canónico
  del mismo run, sea TXT, MDB o VNR-GIS;
- las escrituras de P, Q, FP, estado y bandera de escalado se releen antes del flujo.

## 9. Población universal de cargas

La población de una red será la unión de:

```text
ElmFeeder.GetObjs("ElmLod")
∪
GetCalcRelevantObjects("*.ElmLod") filtrado por p:alimentador
```

Las etiquetas nativas escalares o devueltas como lista se normalizan de la misma
forma. Los objetos se deduplican por identidad nativa. Una etiqueta no vacía y
contradictoria excluye la carga y genera evidencia; una carga sin etiqueta puede
entrar por topología para mantener compatibilidad con modelos anteriores.

El informe muestra conteos `topología`, `etiqueta`, `unión`, `contradicciones` y
`ambiguos`.

## 10. Algoritmo de cuadre

El criterio universal de aceptación es la potencia activa de cabecera:

```text
abs(P_nativa - P_objetivo) / P_objetivo <= tolerancia
```

La asignación inicial sigue usando la Q conocida:

- Q fija de clientes: relación ERI/EA;
- Q repartida: remanente distribuido por kVA cuando es físicamente viable;
- remanente Q negativo: FP objetivo para las cargas escalables.

Las iteraciones posteriores corrigen el factor de P para absorber pérdidas. La Q
resultante del flujo nativo no impide aceptar el cuadre de kW. Todo resultado incluye:

```json
{
  "kvar_no_bloqueante": {
    "objetivo_kvar": 302.0,
    "nativo_kvar": 1556.386,
    "diferencia_kvar": 1254.386,
    "bloquea": false
  }
}
```

El aviso se muestra siempre que la diferencia supere la tolerancia informativa,
independientemente de su signo.

## 11. Estudios exclusivamente nativos

Después del ajuste, todos los estudios usan comandos nativos PowerFactory y el
proyecto ligado al run:

- `ComLdf` balanceado y desbalanceado;
- balance de fases;
- pérdidas, tensiones y cargabilidad;
- troncal, contingencias y transferencia cuando sean aplicables;
- bancos, obras y escenarios mediante objetos nativos.

Un resultado simulado, fake, pandapower o validación de DGS sirve como prueba previa,
no como aceptación del estudio. La aceptación requiere relectura nativa del comando,
código de ejecución, validez de resultados y magnitudes relevantes.

## 12. Estados del dictamen

- `OK`: identidad, persistencia, relectura, convergencia y cuadre de kW válidos.
- `AVISO_KVAR`: kW cuadrado; diferencia reactiva nativa informativa.
- `BLOQUEADO_DATOS`: fuente, alimentador, periodo o dato imprescindible ambiguo.
- `BLOQUEADO_PERSISTENCIA`: PowerFactory no conservó lo escrito al releer.
- `NO_CONVERGE`: el flujo nativo no entrega solución válida.
- `VIOLACION_FISICA`: tensión, cargabilidad u otra restricción fuera de límite.
- `NO_APLICA`: estudio imposible por topología o equipo inexistente, con explicación.

La interfaz no mostrará un `FAIL` genérico. Los últimos cinco estados no se maquillan
como `OK`; mantienen su significado técnico y su evidencia.

## 13. API, interfaz e informes

La interfaz mostrará permanentemente:

- modalidad y run activo;
- proyecto PowerFactory ligado y fecha de relectura;
- periodo de la máxima y periodo del libro de clientes;
- bancos por alimentador y potencia releída;
- clientes fijos, SED escaladas y conteos de población;
- P objetivo/nativa, Q objetivo/nativa y diferencia no bloqueante;
- convergencia, tensión mínima y máxima cargabilidad.

El JSON será la fuente del Excel/PDF y de la interfaz; no se recalcularán valores en
el frontend.

## 14. Estrategia de pruebas

### Automatizadas

- Una prueba parametrizada `txt/mdb/vnr` verifica el mismo dictamen canónico.
- Bancos monofásicos y trifásicos con distintas capacidades de origen conservadas
  exactamente, y banco sin capacidad que nunca recibe un valor sintético.
- Conservación VNR → modelo común → DGS → sidecar.
- Carga sin alimentador, banco ambiguo y FID duplicado.
- Mes coincidente, distinto y desconocido.
- Cálculo P/Q/FP con EA/ERI y fallback de FP.
- Unión topología/etiqueta, atributo lista y wrappers duplicados.
- Proyecto histórico con el mismo nombre y run diferente.
- kW dentro de tolerancia con Q positiva o negativa fuera de tolerancia.
- Relectura fallida y rollback.

### Integración

`tools/accept_three_sources.py` se ampliará para exigir, por modalidad:

- auditoría universal de fuente;
- DGS y sidecar con bancos/cargas;
- importación y binding de proyecto;
- relectura de `p:alimentador` y bancos;
- ajuste de una cabecera disponible;
- informe de kW y diferencia de kVAR;
- `ComLdf` nativo.

Las fuentes ausentes se declaran como tales y nunca se sustituyen entre sí.

### Aceptación real

Para cada fuente oficial disponible se conservarán los artefactos y hashes. Una
aceptación real requiere PowerFactory 2024, proyecto reabierto y `ComLdf` válido.
Los fakes prueban contratos, no sustituyen esta aceptación.

## 15. Criterios de finalización

- No existe una rama de algoritmo de calibración por `txt`, `mdb` o `vnr`.
- Los tres adaptadores producen el mismo contrato y las mismas clases canónicas.
- Los bancos sobreviven de la fuente hasta la relectura `ElmShnt`.
- El periodo de clientes queda probado contra el periodo de la máxima.
- Las cargas fijas usan `Pot`, EA y ERI; las demás se escalan por kVA.
- El kW puede quedar `OK` con diferencia kVAR explícita y no bloqueante.
- Todo estudio declarado aceptado proviene de PowerFactory nativo.
- Suite completa y build frontend sin errores.
- La evidencia real distingue comando, guardado, reapertura, relectura y aceptación
  física.

## 16. Fundamento científico

La separación entre adaptadores y un modelo eléctrico común sigue el principio de
representación interoperable desarrollado en la tesis doctoral de McMorran sobre el
Common Information Model: <https://stax.strath.ac.uk/concern/theses/cc08hf706>.

La construcción de modelos de distribución a partir de GIS y datos operativos reales,
seguida de flujo de potencia, está documentada en la tesis doctoral de Junyi Lu:
<https://pureportal.strath.ac.uk/en/studentTheses/predicting-power-distribution-network-characteristics-and-load-pr/>
y en la tesis de maestría de Derbe Tefera:
<https://etd.aau.edu.et/items/56fa0725-26f3-4436-b102-7f00fd4ffa6b>.

El uso conjunto de medición de cabecera y datos de consumo para asignar cargas se
fundamenta en Carmona-Delgado, Romero-Ramos y Riquelme-Santos, *Electric Power
Systems Research*, DOI 10.1016/j.epsr.2013.03.004:
<https://www.sciencedirect.com/science/article/pii/S0378779613000758>.

La necesidad de verificar topología y parámetros antes de usar un modelo en
monitoreo, análisis o control está sustentada en *IEEE Transactions on
Instrumentation and Measurement*, DOI 10.1109/TIM.2022.3175043:
<https://ieeexplore.ieee.org/document/9781319/>.

La asignación temporal de perfiles a cargas de un alimentador está respaldada por el
test feeder cuasiestático publicado en IEEE PES General Meeting, DOI
10.1109/PESGM.2012.6345414:
<https://ieeexplore.ieee.org/document/6345414/>.
