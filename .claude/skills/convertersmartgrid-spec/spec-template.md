# Spec NNN — <Nombre de la funcionalidad>

Estado: borrador | aprobada | cumplida · Fecha: AAAA-MM-DD

## Contexto y objetivo
<Qué problema resuelve y por qué merece la pena, con el caso real que lo motivó. Un párrafo.>

## Usuarios / actores
<Quién lo usa: ingeniero de planificación desde la web, CLI en lote, PowerFactory…>

## Historias de usuario
- H1: Como <rol> quiero <acción> para <beneficio>.

## Requisitos funcionales (EARS)
- RF-1: CUANDO <evento>, EL SISTEMA <respuesta>.
- RF-2: SI <condición no deseada>, ENTONCES EL SISTEMA <respuesta>.
- RF-3: MIENTRAS <estado>, EL SISTEMA <respuesta>.
- RF-4: EL SISTEMA <comportamiento permanente>.

## Requisitos no funcionales
<Solo los que apliquen, con umbral: determinismo, escala (sin número fijo), tiempo, idioma…>

## Casos límite
<Disposición reducida y completa, alimentador vacío, cancelación a mitad, entrada corrupta…>

## Fuera de alcance
<Lo que explícitamente NO se hace en esta iteración.>

## Criterios de finalización
<Ej.: cada RF citado por al menos una prueba (`grep "NNN:RF-"`), suite en verde con los
datos reales, y DGS idéntico con workers=1 y workers>1.>

## Dudas abiertas
- [NECESITA ACLARACIÓN] <duda>
