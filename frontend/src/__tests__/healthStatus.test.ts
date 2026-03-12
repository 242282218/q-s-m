import { describe, expect, it } from 'vitest';
import { getHealthIssues, getHealthStatusLabel, getHealthTone } from '../utils/healthStatus';

describe('health status helpers', () => {
  it('returns non-ok checks with readable labels and original messages', () => {
    const issues = getHealthIssues({
      database: { status: 'ok', message: 'Database connection successful' },
      cache: { status: 'error', message: "Cache error: 'valid'" },
      tmdb: { status: 'warning', message: 'TMDB client not initialized' },
    });

    expect(issues).toEqual([
      { key: 'cache', label: '缓存', status: 'error', message: "Cache error: 'valid'" },
      { key: 'tmdb', label: 'TMDB', status: 'warning', message: 'TMDB client not initialized' },
    ]);
  });

  it('maps degraded service to warning tone instead of generic error', () => {
    expect(getHealthStatusLabel('degraded')).toBe('服务降级');
    expect(getHealthTone('degraded')).toBe('warning');
  });
});
