import forms from '@tailwindcss/forms';

export const btnVariants = {
  primary: 'bg-primary text-white hover:bg-primary-dark',
  secondary: 'bg-gray-300 text-black hover:bg-gray-400',
  success: 'bg-green-600 text-white hover:bg-green-700',
  danger: 'bg-red-600 text-white hover:bg-red-700',
  'danger-light': 'bg-red-100 hover:bg-red-200 text-red-700',
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
          DEFAULT: '#2563eb',
          light: '#3b82f6',
          dark: '#1e40af',
        },
        gray: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
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

