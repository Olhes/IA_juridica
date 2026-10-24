import { QualityPage } from '../../src/presentation/pages/QualityPage';

export const metadata = {
  title: 'Calidad — IA Jurídica',
  description: 'Métricas publicadas de calidad del asistente: qué se mide, cómo y qué falta por medir.',
};

export default function QualityRoute() {
  return <QualityPage />;
}
