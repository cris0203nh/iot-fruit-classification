"""Cabeceras defensivas para HTTP sin alterar el contrato JSON de FastAPI.

Middleware ASGI puro: incluye preflight CORS, respuestas 401/403/404 y FileResponse.
COEP no se impone aquí: Swagger UI depende de recursos externos; antes de
activarlo es necesario comprobar la aplicación real en el navegador.
"""

from starlette.datastructures import MutableHeaders


class HttpSecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                # Protege respuestas de API contra carga cross-origin 'no-cors'.
                # Fetch con CORS explícito desde React sigue siendo compatible.
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["Referrer-Policy"] = "no-referrer"

                # La API publica información dinámica, de autenticación y
                # evidencias. Evita persistirlas en cachés del navegador/proxy.
                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"

                # COOP es una política de documentos, no una defensa necesaria
                # sobre payloads JSON. No configurar COEP globalmente.
                if path in ("/docs", "/redoc"):
                    headers["Cross-Origin-Opener-Policy"] = "same-origin"

            await send(message)

        await self.app(scope, receive, send_with_security_headers)
