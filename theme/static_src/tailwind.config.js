import forms from '@tailwindcss/forms';

export const btnVariants = {
  primary: 'bg-primary text-text hover:bg-primary-dark',
  secondary: 'bg-background text-text hover:bg-background-dark',
  success: 'bg-success text-text hover:bg-success-dark',
  danger: 'bg-error text-text hover:bg-error-dark',
  'danger-light': 'bg-error-light hover:bg-error-lighter text-error-dark',
  purple: 'bg-accent text-text hover:bg-accent-dark',
  muted: 'bg-background hover:bg-background-dark text-text',
  disabled: 'bg-background text-text cursor-not-allowed',
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
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#4f46e5',
          light: '#6366f1',
          dark: '#4338ca',
        },
        header: '#0d1b2a',
        background: {
          DEFAULT: '#ffffff',
          dark: '#1e293b',
        },
        text: {
          DEFAULT: '#0f172a',
          light: '#f8fafc',
        },
        accent: {
          DEFAULT: '#2563eb',
          light: '#3b82f6',
          dark: '#1e40af',
        },
        success: {
          DEFAULT: '#059669',
          dark: '#047857',
        },
        error: {
          DEFAULT: '#e11d48',
          light: '#ffe4e6',
          lighter: '#fecdd3',
          dark: '#be123c',
        },
        warning: {
          DEFAULT: '#facc15',
          dark: '#eab308',
        },
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

