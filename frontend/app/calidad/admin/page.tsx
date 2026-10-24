import { QualityAdminPage } from '../../../src/presentation/pages/QualityAdminPage';

export const metadata = {
  title: 'Calidad (administración) — IA Jurídica',
  description: 'Regresiones entre versiones y colas de revisión humana (solo administradores).',
  robots: { index: false, follow: false },
};

export default function QualityAdminRoute() {
  return <QualityAdminPage />;
}
