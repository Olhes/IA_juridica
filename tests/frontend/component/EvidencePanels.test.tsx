import { test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  AssistantEvidence,
  CitationChips,
  InsufficientEvidenceCard,
  TrustPanel,
} from '../../../frontend/src/presentation/components/chat/EvidencePanels';
import { TerminalModal } from '../../../frontend/src/presentation/components/TerminalModal';
import { payload } from '../fixtures/chat';

const citations = [
  { key: 'cc:art:475', text: 'Art. 475 CC', status: 'verified', source: 'Guía de pensión', excerpt: 'Prelación de obligados (Art. 475 CC)' },
  { key: 'ley:99999', text: 'Ley 99999', status: 'unverified', source: null, excerpt: null },
];
const evidence = [{ source: 'Guía de pensión', relevance: 0.8, excerpt: 'Prelación de obligados' }];
const withMetadata = (metadata: object, validation: object = {}) =>
  ({ ...payload, validation: { is_grounded: true, hallucination_risk: 0.12, is_reliable: true, ...validation }, metadata } as any);

test('evidencia insuficiente muestra la tarjeta con recursos de ayuda y teléfonos', () => {
  render(<InsufficientEvidenceCard language="spanish" />);
  expect(screen.getByRole('region', { name: /no hay evidencia suficiente/i })).toBeVisible();
  for (const name of ['Línea 100', 'Centros Emergencia Mujer (CEM)', 'Defensoría del Pueblo']) {
    expect(screen.getByText(name)).toBeVisible();
  }
  expect(screen.getByRole('link', { name: '0800-15170' })).toHaveAttribute('href', 'tel:0800-15170');
});

test('tarjeta de evidencia insuficiente existe en quechua y reemplaza chips y panel', () => {
  const { rerender } = render(<InsufficientEvidenceCard language="quechua" />);
  expect(screen.getByText('Corpuspi mana haypachu willakuy')).toBeVisible();
  rerender(<AssistantEvidence language="spanish" apiResponse={withMetadata({ evidence_status: 'insufficient_evidence', citations })} />);
  expect(screen.getByRole('region', { name: /no hay evidencia suficiente/i })).toBeVisible();
  expect(screen.queryByText('Art. 475 CC')).toBeNull();
  expect(screen.queryByText('¿Por qué confiar en esta respuesta?')).toBeNull();
});

test('chips de citas distinguen verificadas y no verificadas y muestran el extracto del corpus', async () => {
  const user = userEvent.setup();
  render(<CitationChips language="spanish" apiResponse={withMetadata({ citations })} />);
  await user.click(screen.getByText('Art. 475 CC'));
  expect(screen.getByText(/Extracto de Guía de pensión/)).toBeVisible();
  expect(screen.getByText(/Prelación de obligados \(Art\. 475 CC\)/)).toBeVisible();
  expect(screen.getByLabelText('Art. 475 CC: Verificada en las fuentes')).toBeInTheDocument();
  expect(screen.getByLabelText('Ley 99999: No se encontró en las fuentes recuperadas')).toBeInTheDocument();
});

test('sin citas no se dibuja el bloque de citas', () => {
  const { container } = render(<CitationChips language="spanish" apiResponse={withMetadata({ citations: [] })} />);
  expect(container).toBeEmptyDOMElement();
});

test('panel de confianza resume solo lo medido: fuentes, validador, riesgo, citas y aviso', async () => {
  const user = userEvent.setup();
  render(<TrustPanel language="spanish" apiResponse={withMetadata({ citations, evidence })} />);
  await user.click(screen.getByText('¿Por qué confiar en esta respuesta?'));
  expect(screen.getByText('Se apoya en 1 fuente recuperada del corpus.')).toBeVisible();
  expect(screen.getByText('El validador encontró respaldo en las fuentes.')).toBeVisible();
  expect(screen.getByText('Riesgo estimado de alucinación: 12 %.')).toBeVisible();
  expect(screen.getByText('1 de 2 citas legales verificadas en las fuentes.')).toBeVisible();
  expect(screen.getByText('El sistema la considera fiable.')).toBeVisible();
  expect(screen.getByText(/no certifica verdad jurídica/)).toBeVisible();
});

test('panel de confianza advierte cuando no es fiable y no inventa datos ausentes', async () => {
  const user = userEvent.setup();
  render(<TrustPanel language="spanish" apiResponse={withMetadata({}, { is_reliable: false, is_grounded: false })} />);
  await user.click(screen.getByText('¿Por qué confiar en esta respuesta?'));
  expect(screen.getByText('No se recuperaron fuentes del corpus.')).toBeVisible();
  expect(screen.getByText('El validador no encontró respaldo suficiente en las fuentes.')).toBeVisible();
  expect(screen.getByText(/no la considera fiable/)).toBeVisible();
  expect(screen.getByText('La respuesta no cita normas concretas.')).toBeVisible();
});

test('la terminal muestra tarjeta, chips y panel solo en respuestas finales del asistente', () => {
  const messages = [
    { id: 'a', content: 'Respuesta', isUser: false, apiResponse: withMetadata({ citations, evidence }) },
    { id: 'b', content: 'Sin evidencia', isUser: false, apiResponse: withMetadata({ evidence_status: 'insufficient_evidence' }) },
    { id: 'c', content: 'En curso', isUser: false, isStreaming: true, apiResponse: withMetadata({ citations }) },
  ];
  render(<TerminalModal isOpen onSend={() => {}} onClose={() => {}} messages={messages} />);
  expect(screen.getAllByText('Art. 475 CC')).toHaveLength(1);
  expect(screen.getAllByText('¿Por qué confiar en esta respuesta?')).toHaveLength(1);
  expect(screen.getAllByRole('region', { name: /no hay evidencia suficiente/i })).toHaveLength(1);
});
