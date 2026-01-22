import React from 'react';

const LanguageToggle = ({ currentLanguage, onLanguageChange }) => {
  return (
    <div className="flex justify-center mb-8">
      <div className="bg-white rounded-lg shadow-md p-1 flex">
        <button
          onClick={() => onLanguageChange('spanish')}
          className={`px-6 py-2 rounded-md font-medium transition-all duration-200 ${
            currentLanguage === 'spanish'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          Español
        </button>
        <button
          onClick={() => onLanguageChange('quechua')}
          className={`px-6 py-2 rounded-md font-medium transition-all duration-200 ${
            currentLanguage === 'quechua'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          Quechua
        </button>
      </div>
    </div>
  );
};

export default LanguageToggle;
