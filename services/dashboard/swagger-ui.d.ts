declare module "swagger-ui" {
  interface SwaggerUiInstance {
    destroy?: () => void;
  }

  interface SwaggerUiOptions {
    domNode?: Element | null;
    url?: string;
    deepLinking?: boolean;
    displayOperationId?: boolean;
    tryItOutEnabled?: boolean;
  }

  export default function SwaggerUI(options: SwaggerUiOptions): SwaggerUiInstance;
}
