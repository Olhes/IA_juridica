// Generado por backend/scripts/export_stream_contract.py. No editar a mano.

export const STREAM_CONTRACT_VERSION = 1;

export interface ChunkEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "chunk";
  delta: string;
}

export interface DoneEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "done";
}

export interface ErrorEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "error";
  code: "RETRIEVAL_UNAVAILABLE" | "GENERATION_UNAVAILABLE" | "TRANSLATION_UNAVAILABLE" | "TIMEOUT" | "INTERNAL_ERROR";
  message: string;
  retryable: boolean;
}

export interface FinalEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "final";
  data: Record<string, unknown>;
}

export interface MetaEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "meta";
  data: Record<string, unknown>;
}

export interface StageEvent {
  v: 1;
  seq: number;
  request_id: string;
  type: "stage";
  stage: "translate_in" | "retrieval" | "generation" | "validation" | "translate_out";
  status: "start" | "end";
  elapsed_ms?: number | null;
}

export type StreamEvent = MetaEvent | StageEvent | ChunkEvent | FinalEvent | ErrorEvent | DoneEvent;
