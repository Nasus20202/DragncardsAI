const SWAGGER_VERSION = "5.32.5";

function buildSwaggerHtml() {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@${SWAGGER_VERSION}/swagger-ui.css" />
    <style>
      html, body {
        height: 100%;
        margin: 0;
        background: #fff;
      }

      #swagger-ui {
        min-height: 100vh;
      }

      #swagger-ui .topbar {
        display: none;
      }

      #swagger-ui .swagger-ui {
        font-family: Arial, Helvetica, sans-serif;
      }
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@${SWAGGER_VERSION}/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@${SWAGGER_VERSION}/swagger-ui-standalone-preset.js"></script>
    <script>
      const renderError = (message) => {
        const target = document.getElementById('swagger-ui');
        if (!target) return;
        target.innerHTML = '<div style="padding:24px;font-family:Arial,Helvetica,sans-serif;color:#b91c1c">' + message + '</div>';
      };

      const start = () => {
        if (!window.SwaggerUIBundle || !window.SwaggerUIStandalonePreset) {
          renderError('Swagger UI assets failed to load.');
          return;
        }

        window.ui = window.SwaggerUIBundle({
          url: '/api/openapi/document',
          dom_id: '#swagger-ui',
          presets: [
            window.SwaggerUIBundle.presets.apis,
            window.SwaggerUIStandalonePreset,
          ],
          layout: 'BaseLayout',
          deepLinking: true,
          displayOperationId: true,
          tryItOutEnabled: true,
        });
      };

      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
      } else {
        start();
      }
    </script>
  </body>
</html>`;
}

export const dynamic = "force-dynamic";

export function GET() {
  return new Response(buildSwaggerHtml(), {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
