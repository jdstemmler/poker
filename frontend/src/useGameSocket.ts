/**
 * Custom hook for WebSocket connection with:
 * - Exponential backoff reconnection
 * - Heartbeat ping/pong
 * - Connection info tracking (who's online)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { EngineState, GameState, ConnectionInfo } from "./types";

interface UseGameSocketOptions {
  url: string | null;
  onLobbyUpdate?: (state: GameState) => void;
  onEngineUpdate?: (state: EngineState) => void;
  onConnectionInfo?: (info: ConnectionInfo) => void;
}

/** Backoff config */
const INITIAL_DELAY = 500;
const MAX_DELAY = 15_000;
const BACKOFF_FACTOR = 1.5;

export function useGameSocket({
  url,
  onLobbyUpdate,
  onEngineUpdate,
  onConnectionInfo,
}: UseGameSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const delayRef = useRef(INITIAL_DELAY);
  const mountedRef = useRef(true);

  // Keep callback refs stable
  const onLobbyRef = useRef(onLobbyUpdate);
  const onEngineRef = useRef(onEngineUpdate);
  const onConnInfoRef = useRef(onConnectionInfo);
  onLobbyRef.current = onLobbyUpdate;
  onEngineRef.current = onEngineUpdate;
  onConnInfoRef.current = onConnectionInfo;

  const connect = useCallback(() => {
    if (!url || !mountedRef.current) return;

    // Clean up any existing connection
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnected(true);
      delayRef.current = INITIAL_DELAY; // reset backoff on success
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const parsed = JSON.parse(event.data);
        const msgType = parsed.type;

        if (msgType === "ping") {
          // Respond with pong
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "pong" }));
          }
        } else if (msgType === "game_state" && parsed.data) {
          onEngineRef.current?.(parsed.data as EngineState);
        } else if (msgType === "connection_info") {
          onConnInfoRef.current?.(parsed as ConnectionInfo);
        } else if (parsed.code && parsed.status) {
          // Lobby state (has code + status fields at top level)
          onLobbyRef.current?.(parsed as GameState);
        }
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      setConnected(false);

      // Don't reconnect if server explicitly rejected us
      if (event.code >= 4000 && event.code < 4100) {
        return;
      }

      // Exponential backoff reconnect
      const delay = delayRef.current;
      delayRef.current = Math.min(delay * BACKOFF_FACTOR, MAX_DELAY);
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { connected };
}
