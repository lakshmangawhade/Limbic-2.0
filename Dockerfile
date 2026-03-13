FROM node:20-alpine

WORKDIR /app

COPY index.html ./index.html
COPY server.js ./server.js
COPY .env.example ./.env.example

EXPOSE 3000

CMD ["node", "server.js"]
