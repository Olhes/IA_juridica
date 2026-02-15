import { NextResponse } from 'next/server';
import {
  parseUpstreamPayload,
  postLegalQuery,
  postLegalQueryStream
} from '../../../../src/infrastructure/backend/fastapi-client';

export const runtime = 'nodejs';

interface ConsultRequestBody {
  query?: string;
  language?: string;
  context?: unknown;
  stream?: boolean;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as ConsultRequestBody;
    const query = typeof body.query === 'string' ? body.query.trim() : '';
    const language = typeof body.language === 'string' ? body.language : 'spanish';
    const shouldStream = body.stream === true;

    if (!query) {
      return NextResponse.json(
        { success: false, error: 'La consulta es obligatoria.' },
        { status: 400 }
      );
    }

    if (shouldStream) {
      const upstreamStreamResponse = await postLegalQueryStream({
        query,
        language,
        context: body.context
      });

      if (!upstreamStreamResponse.ok) {
        const upstreamErrorPayload = await parseUpstreamPayload(upstreamStreamResponse);
        return NextResponse.json(
          {
            success: false,
            error:
              (typeof upstreamErrorPayload.detail === 'string' && upstreamErrorPayload.detail) ||
              'No se pudo procesar la consulta legal en streaming.'
          },
          { status: upstreamStreamResponse.status }
        );
      }

      if (!upstreamStreamResponse.body) {
        return NextResponse.json(
          {
            success: false,
            error: 'El backend no devolvio un stream valido.'
          },
          { status: 500 }
        );
      }

      return new Response(upstreamStreamResponse.body, {
        status: 200,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-cache, no-transform',
          Connection: 'keep-alive'
        }
      });
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
