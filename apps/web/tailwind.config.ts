import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#080a0f",
          900: "#0d1017",
          850: "#12151d",
          800: "#171b25",
          700: "#212734",
          600: "#2e3646",
          500: "#485466",
          400: "#6b7789",
          300: "#95a0b1",
          200: "#c2cad6",
          100: "#e6eaf0",
        },
        arena: {
          keyword: "#f5a524",
          semantic: "#22b8cf",
          graph: "#a78bfa",
          hybrid: "#4ade80",
          ontology: "#f472b6",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 260ms ease-out both",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
