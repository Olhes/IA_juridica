import { FileText, Globe, Shield } from 'lucide-react';

interface FeatureCardsProps {
  features: {
    accessibility: string;
    accessibilityDescription: string;
    democratization: string;
    democratizationDescription: string;
    practical: string;
    practicalDescription: string;
  };
}

export function FeatureCards({ features }: FeatureCardsProps) {
  return (
    <div className="grid md:grid-cols-3 gap-8 mb-12">
      <div className="bg-white rounded-lg shadow-lg p-6 transform hover:-translate-y-1 transition-transform">
        <div className="flex justify-center mb-4">
          <Globe className="w-12 h-12 text-blue-700" />
        </div>
        <h3 className="text-xl font-semibold text-center mb-3">{features.accessibility}</h3>
        <p className="text-gray-600 text-center">{features.accessibilityDescription}</p>
      </div>

      <div className="bg-white rounded-lg shadow-lg p-6 transform hover:-translate-y-1 transition-transform">
        <div className="flex justify-center mb-4">
          <Shield className="w-12 h-12 text-emerald-700" />
        </div>
        <h3 className="text-xl font-semibold text-center mb-3">{features.democratization}</h3>
        <p className="text-gray-600 text-center">{features.democratizationDescription}</p>
      </div>

      <div className="bg-white rounded-lg shadow-lg p-6 transform hover:-translate-y-1 transition-transform">
        <div className="flex justify-center mb-4">
          <FileText className="w-12 h-12 text-amber-700" />
        </div>
        <h3 className="text-xl font-semibold text-center mb-3">{features.practical}</h3>
        <p className="text-gray-600 text-center">{features.practicalDescription}</p>
      </div>
    </div>
  );
}
