/** Custom hook for WebSocket connection with auto-reconnect. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { EngineState, GameState } from "./types";

interface UseGameSocketOptions {
  url: string | null;
  onLobbyUpdate?: (state: GameState) => void;
  onEngineUpdate?: (state: EngineState) => void;
}

export function useGameSocket({
  url,
  onLobbyUpdate,
  onEngineUpdate,
}: UseGameSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const onLobbyRef = useRef(onLobbyUpdate);
  const onEngineRef = useRef(onEngineUpdate);
  onLobbyRef.current = onLobbyUpdate;
  onEngineRef.current = onEngineUpdate;

  const connect = useCallback(() => {
    if (!url) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);

        // Check if this is a typed message (Phase 2+)
        if (parsed.type === "game_state" && parsed.data) {
          onEngineRef.current?.(parsed.data as EngineState);
        } else if (parsed.code && parsed.status) {
          // Legacy lobby state (has code + status fields)
          onLobbyRef.current?.(parsed as GameState);
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
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
