/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        raw: {
          bg: "#0d0f12",
          card: "#14171d",
          border: "#262b34",
          accent: "#ff1e1e",
          green: "#00e676",
          yellow: "#ffd600",
          text: "#e1e4ea",
          dim: "#88909e"
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace']
      }
    },
  },
  plugins: [],
}
