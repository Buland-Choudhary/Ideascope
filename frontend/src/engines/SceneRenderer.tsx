import { useEffect, useMemo, useRef, useState } from "react";

import type { Beat, ParamValue } from "../types/lesson";
import { scanSceneCode } from "./denylist";
import { buildSceneDocument, ERROR, READY, UPDATE_PARAM } from "./sceneRuntime";

type Status = "loading" | "ready" | "error";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

interface SceneRendererProps {
  beat: Beat;
  params: Record<string, ParamValue>;
}

/**
 * Mounts one beat's scene in a sandboxed iframe and bridges `postMessage`.
 * The iframe is rebuilt only when the beat changes; manipulable changes flow
 * through as `updateParam` messages without a reload.
 */
export function SceneRenderer({ beat, params }: SceneRendererProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const scan = useMemo(() => scanSceneCode(beat.scene.code), [beat.scene.code]);

  // Capture the param values at the moment the beat mounts so they can be
  // embedded as the scene's initial state; later changes arrive via messages.
  const initialParamsRef = useRef(params);
  const [srcDoc, setSrcDoc] = useState("");

  // buildSceneDocument is async (p5 loads via a dynamic import, only for
  // canvas scenes — see sceneRuntime.ts); the "loading" status below already
  // covers this wait, same as it covers the iframe's own ready() signal.
  useEffect(() => {
    if (!scan.ok) {
      setSrcDoc("");
      return;
    }
    let cancelled = false;
    buildSceneDocument({
      engine: beat.engine,
      code: beat.scene.code,
      params: initialParamsRef.current,
      reducedMotion: prefersReducedMotion(),
    }).then((doc) => {
      if (!cancelled) setSrcDoc(doc);
    });
    return () => {
      cancelled = true;
    };
    // Rebuild only per beat; initialParamsRef (a ref) is read at build time.
  }, [beat.id, beat.engine, beat.scene.code, scan.ok]);

  // Reset status when the beat (and thus the iframe) changes.
  useEffect(() => {
    if (!scan.ok) {
      setStatus("error");
      setErrorMessage(`Scene rejected: ${scan.reason}`);
      return;
    }
    setStatus("loading");
    setErrorMessage(null);
  }, [beat.id, scan.ok, scan.reason]);

  // Listen for ready/error from this iframe only.
  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      if (ev.source !== iframeRef.current?.contentWindow) return;
      const msg = ev.data as { type?: string; message?: string };
      if (msg?.type === READY) setStatus("ready");
      else if (msg?.type === ERROR) {
        setStatus("error");
        setErrorMessage(msg.message ?? "Scene failed to render");
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [beat.id]);

  // Forward changed params to the running scene.
  const lastSentRef = useRef<Record<string, ParamValue>>(initialParamsRef.current);
  useEffect(() => {
    if (status !== "ready") return;
    const target = iframeRef.current?.contentWindow;
    if (!target) return;
    for (const [param, value] of Object.entries(params)) {
      if (lastSentRef.current[param] !== value) {
        target.postMessage({ type: UPDATE_PARAM, param, value }, "*");
      }
    }
    lastSentRef.current = params;
  }, [params, status]);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-gray-200 bg-white">
      {srcDoc && (
        <iframe
          ref={iframeRef}
          title={`Scene: ${beat.intent}`}
          srcDoc={srcDoc}
          sandbox="allow-scripts"
          className="h-full w-full"
        />
      )}
      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70 text-sm text-gray-500">
          Preparing scene…
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex items-center justify-center bg-red-50 p-4 text-center text-sm text-red-700">
          Couldn&apos;t render this scene.
          {errorMessage ? <span className="sr-only"> {errorMessage}</span> : null}
        </div>
      )}
    </div>
  );
}
