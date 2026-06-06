FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN rm -rf .next && npm run build && rm -rf .next/standalone/.next/static && cp -r .next/static .next/standalone/.next/static

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["node", ".next/standalone/server.js"]
