export const conversation = (id = 'a', title = 'Nueva consulta', count = 0) => ({
  id, title, language: 'spanish', created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T12:00:00Z', message_count: count,
});
export const payload = {
  query: 'Consulta sintética', sources: ['Documento sintético'],
  response: {
    tema: 'general', respuesta_espanol: 'Respuesta final en español',
    respuesta_quechua: 'Kutichiy final', pasos_recomendados: [], recursos: [],
    advertencias: [], fuentes: [], confianza: 0.8, fecha_respuesta: '2026-10-01',
  },
};
export function streamResponse(text: string, width = 1) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({
    start(controller) {
      for (let index = 0; index < bytes.length; index += width) {
        controller.enqueue(bytes.slice(index, index + width));
      }
      controller.close();
    },
  }));
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
