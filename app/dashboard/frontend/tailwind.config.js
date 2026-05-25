export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Geist", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        night: "#07080d",
        panel: "#10131d",
        cyanx: "#22d3ee",
        violetx: "#a78bfa",
      },
      boxShadow: {
        glow: "0 0 50px rgba(34, 211, 238, 0.16)",
      },
    },
  },
  plugins: [],
};

