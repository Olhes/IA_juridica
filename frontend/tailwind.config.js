// Paleta "Tocapu" (diseño A): tejido andino sobre fondo crema.
// Se remapean las escalas que ya usan los componentes, así el rediseño no toca
// estructura ni lógica: neutros -> berenjena, acento -> magenta, ámbar -> dorado,
// verdes/azules -> turquesa. Rojos y rosas quedan para errores/alertas.
const berenjena = {
  50: '#FFF8F0', 100: '#F6ECF0', 200: '#F0DDE3', 300: '#D9C3D3', 400: '#A68DA1',
  500: '#7E6580', 600: '#6A5470', 700: '#4A2D5E', 800: '#3D2550', 900: '#2B1838',
  950: '#1C0F26',
};
const magenta = {
  50: '#FCE6EE', 100: '#F9D3E1', 200: '#F2AFC8', 300: '#E98AAE', 400: '#D85A8A',
  500: '#C43A70', 600: '#B8285F', 700: '#A3204F', 800: '#7A1239', 900: '#5E0E2C',
  950: '#3F0A1E',
};
const dorado = {
  50: '#FDF0D9', 100: '#FBE3B5', 200: '#F8D08A', 300: '#F5BD60', 400: '#F2A93B',
  500: '#E0931F', 600: '#B87412', 700: '#7A4B00', 800: '#5C3900', 900: '#4A2D10',
  950: '#2E1B05',
};
const turquesa = {
  50: '#DDF3F1', 100: '#BCE8E4', 200: '#8DD6D0', 300: '#5CC1BA', 400: '#33ADA7',
  500: '#1E9C97', 600: '#11706F', 700: '#0D5C59', 800: '#0B4A48', 900: '#083B39',
  950: '#042523',
};

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,jsx,ts,tsx,mdx}',
    './src/**/*.{js,jsx,ts,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        'inter': ['Inter', 'sans-serif'],
        'sans': ['var(--font-nunito)', 'system-ui', 'sans-serif'],
        'display': ['var(--font-bricolage)', 'var(--font-nunito)', 'sans-serif'],
      },
      // Botones y tarjetas del diseño A: esquinas de 10–22 px.
      borderRadius: {
        'md': '10px',
        'lg': '12px',
        'xl': '14px',
        '2xl': '18px',
        '3xl': '22px',
      },
      colors: {
        slate: berenjena,
        gray: berenjena,
        zinc: berenjena,
        neutral: berenjena,
        stone: berenjena,
        indigo: magenta,
        violet: magenta,
        purple: magenta,
        fuchsia: magenta,
        amber: dorado,
        yellow: dorado,
        orange: dorado,
        emerald: turquesa,
        teal: turquesa,
        green: turquesa,
        cyan: turquesa,
        sky: turquesa,
        blue: turquesa,
        'primary': {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        'secondary': {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
        }
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
}
