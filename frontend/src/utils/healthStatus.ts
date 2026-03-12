import type { HealthCheck } from '@/types/api';

const HEALTH_CHECK_LABELS: Record<string, string> = {
  api: '接口',
  service: '服务',
  database: '数据库',
  tmdb: 'TMDB',
  cache: '缓存',
};

export interface HealthIssue extends HealthCheck {
  key: string;
  label: string;
}

function getSeverity(status: string): number {
  switch (status) {
    case 'error':
      return 3;
    case 'warning':
    case 'degraded':
      return 2;
    default:
      return 1;
  }
}

export function getHealthTone(status: string): 'ok' | 'warning' | 'error' {
  switch (status) {
    case 'ok':
      return 'ok';
    case 'degraded':
    case 'warning':
      return 'warning';
    default:
      return 'error';
  }
}

export function getHealthStatusLabel(status: string): string {
  switch (status) {
    case 'ok':
      return '运行正常';
    case 'degraded':
      return '服务降级';
    case 'warning':
      return '服务告警';
    case 'error':
      return '服务异常';
    default:
      return '状态未知';
  }
}

export function getHealthIssues(
  checks: Record<string, HealthCheck> | null | undefined
): HealthIssue[] {
  if (!checks) {
    return [];
  }

  return Object.entries(checks)
    .filter(([, check]) => check.status !== 'ok')
    .sort(([, left], [, right]) => getSeverity(right.status) - getSeverity(left.status))
    .map(([key, check]) => ({
      key,
      label: HEALTH_CHECK_LABELS[key] ?? key,
      status: check.status,
      message: check.message,
    }));
}
