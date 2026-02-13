import { NextResponse } from 'next/server';
import {
  parseUpstreamPayload,
  postPdfReport
} from '../../../../src/infrastructure/backend/fastapi-client';

export const runtime = 'nodejs';

interface PdfRequestBody {
  query?: string;
  response?: Record<string, unknown>;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as PdfRequestBody;
    const query = typeof body.query === 'string' ? body.query.trim() : '';

    if (!query || !body.response) {
      return NextResponse.json(
        { success: false, error: 'query y response son obligatorios.' },
        { status: 400 }
      );
    }

    const upstreamResponse = await postPdfReport({
      query,
      response: body.response
    });

    const contentType = upstreamResponse.headers.get('content-type') || '';
    if (upstreamResponse.ok && contentType.includes('application/pdf')) {
      const data = await upstreamResponse.arrayBuffer();
      return new Response(data, {
        status: 200,
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': `attachment; filename="informe-legal-${Date.now()}.pdf"`
        }
      });
    }

    const payload = await parseUpstreamPayload(upstreamResponse);
    const rawMessage =
      (typeof payload.message === 'string' && payload.message) ||
      (typeof payload.detail === 'string' && payload.detail) ||
      'No se pudo generar el PDF.';

    if (rawMessage.toLowerCase().includes('not implemented')) {
      return NextResponse.json(
        {
          success: false,
          error: 'La generacion de PDF aun no esta implementada en FastAPI.'
        },
        { status: 501 }
      );
    }

    if (!upstreamResponse.ok) {
      return NextResponse.json(
        {
          success: false,
          error: rawMessage
        },
        { status: upstreamResponse.status }
      );
    }

    return NextResponse.json(payload);
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
