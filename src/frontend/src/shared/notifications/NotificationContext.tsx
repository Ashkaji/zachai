import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type NotificationTier = "critical" | "informational" | "audit";

export interface Notification {
  id: string;
  tier: NotificationTier;
  title: string;
  body: string;
  timestamp: string;
}

// Minimal Event Bus implementation
type Listener = (notification: Notification) => void;

class NotificationEventBus {
  private listeners: Listener[] = [];

  subscribe(listener: Listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  emit(notification: Omit<Notification, "id" | "timestamp">) {
    const fullNotification: Notification = {
      ...notification,
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
    };
    this.listeners.forEach((listener) => listener(fullNotification));
  }
}

export const eventBus = new NotificationEventBus();

interface NotificationContextType {
  notifications: Notification[];
  activeNotifications: Notification[]; // Only Critical and Informational
  dismissNotification: (id: string) => void;
  clearAll: () => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    const unsubscribe = eventBus.subscribe((newNotification) => {
      setNotifications((prev) => [newNotification, ...prev]);
    });
    return unsubscribe;
  }, []);

  const dismissNotification = (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  const activeNotifications = notifications.filter(
    (n) => n.tier === "critical" || n.tier === "informational"
  );

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        activeNotifications,
        dismissNotification,
        clearAll,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error("useNotifications must be used within a NotificationProvider");
  }
  return context;
}
