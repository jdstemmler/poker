/** Custom hook for WebSocket connection with auto-reconnect. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { GameState } from "./types";

interface UseGameSocketOptions {
  url: string | null;
  onStateUpdate: (state: GameState) => void;
}

export function useGameSocket({ url, onStateUpdate }: UseGameSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const onStateRef = useRef(onStateUpdate);
  onStateRef.current = onStateUpdate;

  const connect = useCallback(() => {
    if (!url) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      try {
        const state: GameState = JSON.parse(event.data);
        onStateRef.current(state);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 2 seconds
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
