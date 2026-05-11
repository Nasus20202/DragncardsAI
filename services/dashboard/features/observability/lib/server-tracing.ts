import { trace } from "@opentelemetry/api";

const tracer = trace.getTracer("dashboard.server");

export async function withServerSpan<T>(
  name: string,
  attributes: Record<string, string | number | boolean | undefined>,
  fn: () => Promise<T>
): Promise<T> {
  return tracer.startActiveSpan(name, async (span) => {
    try {
      for (const [key, value] of Object.entries(attributes)) {
        if (value !== undefined) {
          span.setAttribute(key, value);
        }
      }
      return await fn();
    } finally {
      span.end();
    }
  });
}
