"use client";

import React, {
    createContext,
    useContext,
    useEffect,
    useRef,
    useState,
    useCallback,
} from "react";

type WebSocketMessage = {
    type: string;
    payload: any;
};

type WebSocketContextType = {
    isConnected: boolean;
    subscribe: (eventType: string, callback: (payload: any) => void) => () => void;
    sendMessage: (type: string, payload: any) => void;
};

const WebSocketContext = createContext<WebSocketContextType | undefined>(
    undefined
);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const subscribersRef = useRef<
        Record<string, Set<(payload: any) => void>>
    >({});
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/ws/events";
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket connected");
            setIsConnected(true);
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
        };

        ws.onclose = () => {
            console.log("WebSocket disconnected");
            setIsConnected(false);
            wsRef.current = null;
            // Attempt reconnect
            if (!reconnectTimeoutRef.current) {
                reconnectTimeoutRef.current = setTimeout(() => {
                    console.log("Attempting to reconnect...");
                    connect();
                }, 3000);
            }
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            ws.close();
        };

        ws.onmessage = (event) => {
            try {
                const message: WebSocketMessage = JSON.parse(event.data);
                const { type, payload } = message;

                if (subscribersRef.current[type]) {
                    subscribersRef.current[type].forEach((callback) => {
                        try {
                            callback(payload);
                        } catch (err) {
                            console.error(`Error in WebSocket subscriber for ${type}:`, err);
                        }
                    });
                }
            } catch (e) {
                console.error("Failed to parse WebSocket message:", e);
            }
        };

        wsRef.current = ws;
    }, []);

    useEffect(() => {
        connect();
        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
    }, [connect]);

    const subscribe = useCallback(
        (eventType: string, callback: (payload: any) => void) => {
            if (!subscribersRef.current[eventType]) {
                subscribersRef.current[eventType] = new Set();
            }
            subscribersRef.current[eventType].add(callback);

            return () => {
                if (subscribersRef.current[eventType]) {
                    subscribersRef.current[eventType].delete(callback);
                    if (subscribersRef.current[eventType].size === 0) {
                        delete subscribersRef.current[eventType];
                    }
                }
            };
        },
        []
    );

    const sendMessage = useCallback((type: string, payload: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type, payload }));
        } else {
            console.warn("WebSocket is not connected. Message not sent.");
        }
    }, []);

    return (
        <WebSocketContext.Provider value={{ isConnected, subscribe, sendMessage }}>
            {children}
        </WebSocketContext.Provider>
    );
}

export function useWebSocket() {
    const context = useContext(WebSocketContext);
    if (context === undefined) {
        throw new Error("useWebSocket must be used within a WebSocketProvider");
    }
    return context;
}
