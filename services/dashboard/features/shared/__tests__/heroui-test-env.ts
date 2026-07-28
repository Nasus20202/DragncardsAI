/**
 * Test-environment shims for rendering real Hero UI overlay components under
 * jsdom. Hero UI's popovers measure their trigger with a `ResizeObserver`, which
 * jsdom does not implement; without a stand-in, any `ComboBox`/`Select` popover
 * throws on render.
 */
export function installResizeObserver() {
  if ("ResizeObserver" in globalThis) return;
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true,
    value: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
}
