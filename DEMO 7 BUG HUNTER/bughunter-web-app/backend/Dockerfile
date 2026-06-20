FROM node:18-slim

# Install git and clean up caches
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install bug-hunter CLI globally
RUN npm install -g @codexstar/bug-hunter

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000
# Defaults to running the API layer. Can be overridden in compose for worker profiles.
CMD ["node", "api.js"]
