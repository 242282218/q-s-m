import { reactive } from 'vue';

export type ToastType = 'success' | 'error' | 'info';

export interface ToastItem {
  id: number;
  type: ToastType;
  text: string;
}

const toasts = reactive<ToastItem[]>([]);
let seed = 1;

export function useToast() {
  const push = (text: string, type: ToastType = 'info', duration = 2800) => {
    const item: ToastItem = { id: seed++, type, text };
    toasts.push(item);
    window.setTimeout(() => {
      const idx = toasts.findIndex((t) => t.id === item.id);
      if (idx >= 0) {
        toasts.splice(idx, 1);
      }
    }, duration);
  };

  return {
    toasts,
    push,
  };
}
