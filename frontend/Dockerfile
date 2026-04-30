FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json ./
RUN npm install --legacy-peer-deps

# Copy source and build
COPY . .
RUN npm run build


# ── Production: serve with a lightweight static server ───────────────────────
FROM node:20-alpine AS production

WORKDIR /app

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
