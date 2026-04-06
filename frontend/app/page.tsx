import { ChatPage } from '../src/presentation/pages/ChatPage';

export const metadata = {
  title: 'IA Jurídica — Asistente Legal Bilingüe',
  description:
    'Asistente legal bilingüe (Español / Quechua) para comunidades andinas. Consultas sobre violencia familiar, pensión de alimentos, medidas de protección y más.',
};

export default function HomePage() {
  return <ChatPage />;
}
