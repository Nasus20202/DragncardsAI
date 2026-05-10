declare module "swagger-ui-react" {
  import type { ComponentType } from "react";

  const SwaggerUI: ComponentType<{ spec: unknown }>;

  export default SwaggerUI;
}
