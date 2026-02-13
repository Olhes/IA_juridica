import clsx from 'clsx';
import type { SupportedLanguage } from '../../domain/legal/types';

interface LanguageToggleProps {
  currentLanguage: SupportedLanguage;
  onLanguageChange: (language: SupportedLanguage) => void;
}

export function LanguageToggle({ currentLanguage, onLanguageChange }: LanguageToggleProps) {
  return (
    <div className="flex justify-center mb-8">
      <div className="bg-white rounded-lg shadow-md p-1 flex gap-1">
        <button
          type="button"
          onClick={() => onLanguageChange('spanish')}
          className={clsx(
            'px-6 py-2 rounded-md font-medium transition-all duration-200',
            currentLanguage === 'spanish'
              ? 'bg-blue-700 text-white shadow-sm'
              : 'text-gray-600 hover:text-gray-800'
          )}
        >
          Espanol
        </button>
        <button
          type="button"
          onClick={() => onLanguageChange('quechua')}
          className={clsx(
            'px-6 py-2 rounded-md font-medium transition-all duration-200',
            currentLanguage === 'quechua'
              ? 'bg-blue-700 text-white shadow-sm'
              : 'text-gray-600 hover:text-gray-800'
          )}
        >
          Quechua
        </button>
      </div>
    </div>
  );
}
