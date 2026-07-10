import { useCallback, useEffect, useRef } from "react";
import { Window } from "@tauri-apps/api/window";
import { isTauriRuntime } from "../views/windowActions";

export type WindowCloseReason = "manual" | "escape" | "blur";

interface WindowLifecycleOptions {
  onClose: () => void | Promise<void>;
  onOpen?: () => void;
  closeOnBlur?: boolean;
  closeOnEscape?: boolean;
  replayOnFocus?: boolean;
  shouldIgnoreClose?: (reason: WindowCloseReason) => boolean;
}

export function useWindowLifecycle({
  onClose,
  onOpen,
  closeOnBlur = false,
  closeOnEscape = true,
  replayOnFocus = true,
  shouldIgnoreClose
}: WindowLifecycleOptions) {
  const closingRef = useRef(false);

  const resetClosing = useCallback(() => {
    closingRef.current = false;
  }, []);

  const closeWindow = useCallback(async (reason: WindowCloseReason = "manual") => {
    if (closingRef.current || shouldIgnoreClose?.(reason)) {
      return;
    }
    closingRef.current = true;
    try {
      await onClose();
    } finally {
      closingRef.current = false;
    }
  }, [onClose, shouldIgnoreClose]);

  useEffect(() => {
    if (!closeOnEscape) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        void closeWindow("escape");
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeOnEscape, closeWindow]);

  useEffect(() => {
    if (!isTauriRuntime() || (!closeOnBlur && !replayOnFocus)) {
      return;
    }

    let unlisten: (() => void) | undefined;
    let didCleanup = false;
    Window.getCurrent()
      .onFocusChanged(({ payload: focused }) => {
        if (!focused && closeOnBlur) {
          void closeWindow("blur");
          return;
        }
        if (focused && replayOnFocus) {
          onOpen?.();
        }
      })
      .then((nextUnlisten) => {
        if (didCleanup) {
          nextUnlisten();
          return;
        }
        unlisten = nextUnlisten;
      })
      .catch((error) => {
        console.warn("Failed to listen window focus changes", error);
      });

    return () => {
      didCleanup = true;
      unlisten?.();
    };
  }, [closeOnBlur, closeWindow, onOpen, replayOnFocus]);

  return { closingRef, closeWindow, resetClosing };
}
