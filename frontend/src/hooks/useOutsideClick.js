import { useEffect } from "react";

/**
 * Calls `handler` when a mousedown/touchstart fires outside the referenced element.
 * Pass `enabled=false` to disable (e.g. when the element isn't open).
 *
 * Use mousedown (not click) so the handler fires before the document gets a focus shift
 * — this avoids race conditions when the user clicks on another interactive surface.
 */
export function useOutsideClick(ref, handler, enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined;

    function onPointerDown(event) {
      const el = ref.current;
      if (!el) return;
      if (el.contains(event.target)) return;
      handler(event);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
    };
  }, [ref, handler, enabled]);
}
