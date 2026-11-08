/** 047:RF-16 y RF-17: propuestas del maestro y datos observados son distintos. */
export interface EstadoAceptacionAgente {
  schema_version: number;
  propuestas: {
    definidas: number; materializadas: number; unicas: number; huella: string | null;
    filas: { texto: string; tarea: string }[];
  };
  humanas: { eventos: number; unicas: number };
  evaluacion: null | {
    modelo: string; ejemplos: number; acierto_tarea: number; f1_datos: number;
    aceptacion: { asistida: { aprobada: boolean; confirmacion_obligatoria: boolean; fallos: string[] } };
  };
  bloqueos: string[];
  integral: boolean;
}
