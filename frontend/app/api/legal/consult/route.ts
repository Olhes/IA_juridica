import { NextResponse } from 'next/server';
import {
  parseUpstreamPayload,
  postLegalQuery
} from '../../../../src/infrastructure/backend/fastapi-client';

export const runtime = 'nodejs';

interface ConsultRequestBody {
  query?: string;
  language?: string;
  context?: unknown;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as ConsultRequestBody;
    const query = typeof body.query === 'string' ? body.query.trim() : '';
    const language = typeof body.language === 'string' ? body.language : 'spanish';

    if (!query) {
      return NextResponse.json(
        { success: false, error: 'La consulta es obligatoria.' },
        { status: 400 }
      );
    }

    const upstreamResponse = await postLegalQuery({
      query,
      language,
      context: body.context
    });

    const upstreamPayload = await parseUpstreamPayload(upstreamResponse);

    if (!upstreamResponse.ok) {
      return NextResponse.json(
        {
          success: false,
          error:
            (typeof upstreamPayload.detail === 'string' && upstreamPayload.detail) ||
            'No se pudo procesar la consulta legal.'
        },
        { status: upstreamResponse.status }
      );
    }

    const responsePayload =
      typeof upstreamPayload.response === 'object' && upstreamPayload.response !== null
        ? (upstreamPayload.response as Record<string, unknown>)
        : {};

    const normalizedResponse = {
      ...responsePayload,
      spanish:
        (typeof responsePayload.spanish === 'string' && responsePayload.spanish) ||
        (typeof responsePayload.respuesta_espanol === 'string'
          ? responsePayload.respuesta_espanol
          : ''),
      quechua:
        (typeof responsePayload.quechua === 'string' && responsePayload.quechua) ||
        (typeof responsePayload.respuesta_quechua === 'string'
          ? responsePayload.respuesta_quechua
          : '')
    };

    return NextResponse.json({
      success: true,
      data: {
        ...upstreamPayload,
        response: normalizedResponse
      }
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : 'Error inesperado en frontend API route.'
      },
      { status: 500 }
    );
  }
}
