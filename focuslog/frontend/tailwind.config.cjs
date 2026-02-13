/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          50: "#eef5ff",
          100: "#dae9ff",
          200: "#bdd8ff",
          300: "#93bdff",
          400: "#5f98ff",
          500: "#2f73f2",
          600: "#245cd0",
          700: "#1f49a8",
          800: "#1f3f84",
          900: "#1f376d"
        }
      },
      boxShadow: {
        card: "0 8px 28px rgba(15, 23, 42, 0.08)"
      },
      borderRadius: {
        panel: "12px"
      }
    }
  },
  plugins: []
};
