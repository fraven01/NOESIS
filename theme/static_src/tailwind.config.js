import forms from '@tailwindcss/forms';

export const btnVariants = {
  primary: 'bg-primary text-white hover:bg-primary-dark',
  secondary: 'bg-gray-300 text-black hover:bg-gray-400',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700',
  danger: 'bg-rose-600 text-white hover:bg-rose-700',
  'danger-light': 'bg-rose-100 hover:bg-rose-200 text-rose-700',
  purple: 'bg-purple-600 text-white hover:bg-purple-700',
  muted: 'bg-gray-200 hover:bg-gray-300 text-gray-800',
  disabled: 'bg-gray-300 text-gray-500 cursor-not-allowed',
};

export default {
  btnVariants,
  content: [
    '../templates/**/*.html',
    '../../templates/**/*.html',
    '../../core/templates/**/*.html',
    '../../**/templates/**/*.html',
    '../../**/*.py',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#4f46e5',
          light: '#6366f1',
          dark: '#4338ca',
        },
        header: '#0d1b2a',
        gray: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
      },
    },
  },
  plugins: [forms],
};

