"use client";

import { useCallback, useEffect, useRef, useState } from "react";

function buildWebSocketUrl(path: string): string {
    const wsProtocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = process.env.NEXT_PUBLIC_API_URL
        ?.replace(/^https?:\/\//, "")
        ?.replace(/\/api\/?$/, "") || "localhost:8000";
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    return `${wsProtocol}//${host}${normalizedPath}`;
}

export interface UseWebSocketOptions {
    path: string;
    autoConnect?: boolean;
    reconnectDelay?: number;
    onMessage?: (data: any) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (error: Event) => void;
}

export interface UseWebSocketReturn {
    isConnected: boolean;
    connect: () => void;
    disconnect: () => void;
    send: (data: any) => void;
}

export function useDynamicWebSocket({
    path,
    autoConnect = true,
    reconnectDelay = 5000,
    onMessage,
    onOpen,
    onClose,
    onError,
}: UseWebSocketOptions): UseWebSocketReturn {
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const isMountedRef = useRef(true);

    const onMessageRef = useRef(onMessage);
    const onOpenRef = useRef(onOpen);
    const onCloseRef = useRef(onClose);
    const onErrorRef = useRef(onError);

    useEffect(() => {
        onMessageRef.current = onMessage;
        onOpenRef.current = onOpen;
        onCloseRef.current = onClose;
        onErrorRef.current = onError;
    }, [onMessage, onOpen, onClose, onError]);

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
    }, []);

    const connect = useCallback(() => {
        // Don't connect if already connected or connecting
        if (wsRef.current?.readyState === WebSocket.OPEN ||
            wsRef.current?.readyState === WebSocket.CONNECTING) {
            return;
        }

        try {
            const wsUrl = buildWebSocketUrl(path);
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                if (!isMountedRef.current) return;
                setIsConnected(true);
                if (reconnectTimeoutRef.current) {
                    clearTimeout(reconnectTimeoutRef.current);
                    reconnectTimeoutRef.current = null;
                }
                onOpenRef.current?.();
            };

            ws.onmessage = (event) => {
                if (!isMountedRef.current) return;
                try {
                    const data = JSON.parse(event.data);
                    onMessageRef.current?.(data);
                } catch {
                    // If not JSON, pass raw data
                    onMessageRef.current?.(event.data);
                }
            };

            ws.onclose = () => {
                if (!isMountedRef.current) return;
                setIsConnected(false);
                wsRef.current = null;
                onCloseRef.current?.();

                // Auto-reconnect if enabled
                if (reconnectDelay > 0 && !reconnectTimeoutRef.current) {
                    reconnectTimeoutRef.current = setTimeout(() => {
                        if (isMountedRef.current) {
                            connect();
                        }
                    }, reconnectDelay);
                }
            };

            ws.onerror = (error) => {
                if (!isMountedRef.current) return;
                onErrorRef.current?.(error);
            };
        } catch (err) {
            console.error("WebSocket connection error:", err);
        }
    }, [path, reconnectDelay]);

    const send = useCallback((data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            const message = typeof data === "string" ? data : JSON.stringify(data);
            wsRef.current.send(message);
        } else {
            console.warn("WebSocket is not connected. Message not sent.");
        }
    }, []);

    // Auto-connect on mount
    useEffect(() => {
        isMountedRef.current = true;
        if (autoConnect) {
            connect();
        }
        return () => {
            isMountedRef.current = false;
            disconnect();
        };
    }, [autoConnect, connect, disconnect]);

    return {
        isConnected,
        connect,
        disconnect,
        send,
    };
}
