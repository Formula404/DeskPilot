import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f7f7f4",
        foreground: "#1f2933",
        panel: "#ffffff",
        border: "#d8d9d2",
        accent: "#256f7b",
        muted: "#667085"
      }
    }
  },
  plugins: []
} satisfies Config;
