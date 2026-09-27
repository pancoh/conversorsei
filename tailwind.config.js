/** Configuração do Tailwind para a interface web em docs/. */
module.exports = {
  content: ["./docs/index.html", "./docs/app.js"],
  theme: {
    extend: {
      colors: {
        blue: {
          50: '#EFF9FD',
          200: '#B8E4F6',
          500: '#0694DD',
          600: '#007EB9',
          700: '#2D5E98',
          800: '#244D7D',
          900: '#123B53',
        },
        emerald: {
          400: '#91BB25',
          700: '#4F6E08',
        },
      },
    },
  },
  plugins: [],
};
