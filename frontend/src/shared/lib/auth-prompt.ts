import { hasStoredApiKey } from '@/shared/lib/api-key';

export interface AuthRequiredDetail {
  message: string;
  hasStoredKey: boolean;
}

export const AUTH_REQUIRED_EVENT = 'qsm:auth-required';

const DEFAULT_AUTH_REQUIRED_MESSAGE = '该实例已启用 API 访问 Key，请输入有效密钥后重试。';

function normalizeAuthRequiredMessage(message?: string | null): string {
  const normalized = message?.trim();
  return normalized || DEFAULT_AUTH_REQUIRED_MESSAGE;
}

export function emitAuthRequired(message?: string | null): void {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') {
    return;
  }

  window.dispatchEvent(
    new CustomEvent<AuthRequiredDetail>(AUTH_REQUIRED_EVENT, {
      detail: {
        message: normalizeAuthRequiredMessage(message),
        hasStoredKey: hasStoredApiKey(),
      },
    })
  );
}

export function subscribeAuthRequired(
  listener: (detail: AuthRequiredDetail) => void
): () => void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => undefined;
  }

  const handler = (event: Event) => {
    const detail = (event as CustomEvent<AuthRequiredDetail>).detail;
    listener({
      message: normalizeAuthRequiredMessage(detail?.message),
      hasStoredKey: Boolean(detail?.hasStoredKey),
    });
  };

  window.addEventListener(AUTH_REQUIRED_EVENT, handler as EventListener);
  return () => window.removeEventListener(AUTH_REQUIRED_EVENT, handler as EventListener);
}
