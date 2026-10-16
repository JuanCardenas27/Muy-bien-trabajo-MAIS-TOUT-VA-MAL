// Errores de la capa de datos (Task WEB-03).
//
// Los mensajes están en español y son los que ve el usuario cuando el
// bundle no se puede cargar: versión futura, archivo corrupto o fallo
// de red. Las claves `data.*` corresponden a las cadenas del plan.

export const DATA_MESSAGES = {
  'data.unsupported': 'Versión de datos no soportada: recarga la página',
  'data.corrupt': 'Archivo dañado o incompleto: recarga la página',
  'data.network': 'No se pudieron descargar los datos: revisa tu conexión',
} as const;

export type DataMessageKey = keyof typeof DATA_MESSAGES;

export class DataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DataError';
  }
}
