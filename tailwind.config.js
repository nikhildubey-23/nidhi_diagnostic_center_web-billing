/** Tailwind build config — scans Flask templates & JS. */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fdf8f3",
          100: "#faebd7",
          200: "#f5d7b5",
          300: "#eebd8c",
          400: "#e69d5e",
          500: "#dd8138",
          600: "#c9672d",
          700: "#a84f25",
          800: "#874122",
          900: "#6d371f",
          950: "#3a1c10",
        },
        slate: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
      },
      fontFamily: {
        sans: [
          "Inter", "ui-sans-serif", "system-ui", "-apple-system",
          "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};