# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS tools
WORKDIR /app/web
COPY deploy/node/package.json deploy/node/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY web ./
COPY deploy/toolbox.sh /usr/local/bin/toolbox
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app \
    && chown -R app:app /app
USER app
ENTRYPOINT ["/bin/sh", "/usr/local/bin/toolbox", "node"]
CMD ["npm", "run", "lint"]

FROM tools AS build
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS runtime
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 8080
