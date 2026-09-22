# Diccionario de datos estricto

| Concepto | Fuente obligatoria | Regla |
|---|---|---|
| Alimentador/fuente | RED | ID, nodo y kV explícitos |
| Tramo aéreo/subterráneo | RED + BD_Equipo | Conservar clase, extremos y estado |
| Fases | RED | A/B/C exactas; sin completar fases |
| Circuitos/ternas | RED | Entero positivo; se conserva multiplicidad |
| Conductores por fase | RED/BD_Equipo | Entero explícito |
| Sección | TXT y ficha exacta | Decimal en mm²; nunca default |
| Longitud | RED | km autoritativos salvo política explícita y compatible |
| Impedancias/admitancias/ampacidad | ficha fabricante aprobada | unidades explícitas y trazabilidad |
| Carga | CARGA | P/Q derivados solo de tipo soportado y factor de potencia válido |
| Solar/térmica | TXT + ficha | entidades diferenciadas; potencia y tecnología explícitas |
| TRAFOMIX | relación tipada | excluir equipo y su carga asociada; no excluir SED/carga válida por nombre |

Todo campo ausente o ambiguo produce diagnóstico bloqueante con archivo, sección, fila y campo cuando estén disponibles.
