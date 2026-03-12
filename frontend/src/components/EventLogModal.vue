<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';

interface LogLine {
  level: string;
  text: string;
  timestamp?: string;
}

const props = defineProps<{
  visible: boolean;
  title: string;
  progress: number;
  counter: string;
  summary: string;
  lines: LogLine[];
  busy: boolean;
}>();

const emit = defineEmits<{ close: [] }>();
const logRef = ref<HTMLElement | null>(null);

// 日志过滤状态
const filters = ref({
  info: true,
  warning: true,
  error: true
});

// 自动滚动开关
const autoScroll = ref(true);

// 复制按钮状态
const copying = ref(false);

// 智能判断是否有错误：只有当失败数量 > 0 时才认为有错误
const hasError = computed(() => {
  const summary = props.summary || '';
  // 检查汇总信息中的失败数量
  const failMatch = summary.match(/失败\s*(\d+)/);
  if (failMatch && failMatch[1]) {
    const failCount = parseInt(failMatch[1]);
    return failCount > 0;
  }
  // 如果没有匹配到数字，检查是否有其他错误关键词（排除统计数字的情况）
  return summary.includes('任务失败') || summary.includes('发生错误');
});

// 按阶段分组日志
const groupedLogs = computed(() => {
  const groups: Array<{
    title: string;
    icon: string;
    stage: string;
    logs: LogLine[];
  }> = [];

  let currentGroup: {
    title: string;
    icon: string;
    stage: string;
    logs: LogLine[];
  } | null = null;

  const stagePatterns = [
    { stage: 'init', pattern: /^开始 (独立 | 重命名)/, title: '初始化', icon: '🚀' },
    { stage: 'locate', pattern: /^定位目录/, title: '定位目录', icon: '📍' },
    { stage: 'reorganize', pattern: /^(重组 | 创建目录 | 移动文件 | 根目录改名)/, title: '重组结构', icon: '📁' },
    { stage: 'cleanup', pattern: /^(清理 | 删除)/, title: '清理优化', icon: '🧹' },
    { stage: 'complete', pattern: /^(完成汇总 | 重命名完成 | 完成)/, title: '完成', icon: '✅' }
  ];

  for (const line of props.lines) {
    // 检查是否是新阶段的开始
    const matchedStage = stagePatterns.find(s => s.pattern.test(line.text));
    
    if (matchedStage) {
      // 保存当前组
      if (currentGroup && currentGroup.logs.length > 0) {
        groups.push(currentGroup);
      }
      // 创建新组
      currentGroup = {
        title: matchedStage.title,
        icon: matchedStage.icon,
        stage: matchedStage.stage,
        logs: [line]
      };
    } else {
      // 添加到当前组
      if (!currentGroup) {
        currentGroup = {
          title: '其他',
          icon: '📄',
          stage: 'other',
          logs: []
        };
      }
      currentGroup.logs.push(line);
    }
  }

  // 添加最后一组
  if (currentGroup && currentGroup.logs.length > 0) {
    groups.push(currentGroup);
  }

  return groups;
});

// 过滤后的日志
const filteredLogs = computed(() => {
  return groupedLogs.value.map(group => ({
    ...group,
    logs: group.logs.filter(log => {
      if (log.level === 'info' && !filters.value.info) return false;
      if (log.level === 'warning' && !filters.value.warning) return false;
      if (log.level === 'error' && !filters.value.error) return false;
      return true;
    })
  }));
});

// 统计信息
const logStats = computed(() => {
  const stats = { info: 0, warning: 0, error: 0 };
  props.lines.forEach(line => {
    if (line.level === 'info') stats.info++;
    else if (line.level === 'warning') stats.warning++;
    else if (line.level === 'error') stats.error++;
  });
  return stats;
});

// 复制日志功能
const copyLogs = async () => {
  copying.value = true;
  try {
    const logText = props.lines
      .map(line => {
        const timestamp = line.timestamp || new Date().toLocaleTimeString('zh-CN', { hour12: false });
        return `[${timestamp}] [${line.level.toUpperCase()}] ${line.text}`;
      })
      .join('\n');
    
    await navigator.clipboard.writeText(logText);
    
    // 显示成功提示
    const toast = document.createElement('div');
    toast.textContent = '✅ 日志已复制到剪贴板';
    toast.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 24px;
      background: linear-gradient(135deg, #1f9d55, #3ecf8e);
      color: white;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 9999;
      animation: slideIn 0.3s ease-out;
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
  } catch (error) {
    console.error('复制失败:', error);
  } finally {
    copying.value = false;
  }
};

// 下载日志功能
const downloadLogs = () => {
  const logContent = props.lines
    .map(line => {
      const timestamp = line.timestamp || new Date().toLocaleTimeString('zh-CN', { hour12: false });
      return `[${timestamp}] [${line.level.toUpperCase()}] ${line.text}`;
    })
    .join('\n');
  
  const blob = new Blob([logContent], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `rename-log-${new Date().getTime()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
};

// 清空日志（通知父组件）
const clearLogs = () => {
  // 这里只是触发事件，实际清空由父组件处理
  // 如果需要可以在这里添加 emit
};

// 智能自动滚动
watch(
  () => props.lines.length,
  async () => {
    if (!autoScroll.value) return;
    
    await nextTick();
    if (logRef.value) {
      const { scrollTop, scrollHeight, clientHeight } = logRef.value;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      
      if (isNearBottom) {
        logRef.value.scrollTop = scrollHeight;
      }
    }
  }
);

const close = () => {
  emit('close');
};
</script>

<template>
  <div v-if="visible" class="event-log-modal" @click.self="close">
    <div class="event-log-dialog">
      <!-- 头部：标题 + 操作按钮 -->
      <div class="event-log-header">
        <h3 class="event-log-title">{{ title }}</h3>
        <div class="header-actions">
          <button class="header-btn" @click="copyLogs" :disabled="copying" title="复制日志">
            {{ copying ? '复制中...' : '📋 复制' }}
          </button>
          <button class="header-btn" @click="downloadLogs" title="下载日志">
            💾 下载
          </button>
          <button class="header-btn close-btn" @click="close">×</button>
        </div>
      </div>

      <!-- 进度区域 -->
      <div class="progress-section">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progress}%` }" />
        </div>
        <div class="progress-info">
          <span class="progress-counter">{{ counter }}</span>
          <span class="progress-percentage">{{ progress }}%</span>
        </div>
      </div>

      <!-- 日志过滤工具栏 -->
      <div class="log-toolbar">
        <div class="filter-group">
          <label class="filter-label">
            <input type="checkbox" v-model="filters.info" />
            <span class="level-dot level-info"></span>
            <span>INFO ({{ logStats.info }})</span>
          </label>
          <label class="filter-label">
            <input type="checkbox" v-model="filters.warning" />
            <span class="level-dot level-warning"></span>
            <span>WARNING ({{ logStats.warning }})</span>
          </label>
          <label class="filter-label">
            <input type="checkbox" v-model="filters.error" />
            <span class="level-dot level-error"></span>
            <span>ERROR ({{ logStats.error }})</span>
          </label>
        </div>
        <div class="toolbar-actions">
          <label class="auto-scroll-label">
            <input type="checkbox" v-model="autoScroll" />
            <span>自动滚动</span>
          </label>
        </div>
      </div>

      <!-- 日志内容区域（带阶段分组） -->
      <div ref="logRef" class="log-content">
        <div v-if="filteredLogs.length === 0" class="empty-logs">
          <span class="empty-icon">📄</span>
          <span>暂无日志</span>
        </div>
        <div v-else class="log-groups">
          <div 
            v-for="(group, index) in filteredLogs" 
            :key="index"
            class="log-group"
          >
            <div class="group-header">
              <span class="group-icon">{{ group.icon }}</span>
              <span class="group-title">{{ group.title }}</span>
              <span class="group-count">({{ group.logs.length }})</span>
            </div>
            <div class="log-lines">
              <div
                v-for="(line, idx) in group.logs"
                :key="idx"
                class="log-line"
                :class="['level-' + line.level]"
              >
                <span class="log-timestamp">{{ line.timestamp || new Date().toLocaleTimeString('zh-CN', { hour12: false }) }}</span>
                <span class="log-level" :class="'level-' + line.level">
                  [{{ line.level.toUpperCase() }}]
                </span>
                <span class="log-text">{{ line.text }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 汇总信息 -->
      <div class="log-summary" :class="{ done: !!summary, 'has-error': hasError }">
        <span class="summary-icon">{{ hasError ? '❌' : '✅' }}</span>
        <span class="summary-text">{{ summary }}</span>
      </div>

      <!-- 底部操作栏 -->
      <div class="log-actions">
        <button class="btn btn-secondary" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 模态框主体 */
.event-log-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

.event-log-dialog {
  width: min(1000px, 95%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: linear-gradient(160deg, rgba(24, 24, 24, 0.98) 0%, rgba(16, 16, 16, 0.98) 100%);
  border: 1px solid var(--color-border-default, rgba(255, 255, 255, 0.1));
  border-radius: 16px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
  padding: 20px;
  animation: slideUp 0.3s ease-out;
}

/* 头部 */
.event-log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  .event-log-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary, #fff);
    margin: 0;
  }

  .header-actions {
    display: flex;
    gap: 8px;

    .header-btn {
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.1));
      background: rgba(255, 255, 255, 0.05);
      color: var(--color-text-primary, #fff);
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
      white-space: nowrap;

      &:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: var(--color-border-hover, rgba(255, 255, 255, 0.2));
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      &.close-btn {
        width: 32px;
        height: 32px;
        padding: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
      }
    }
  }
}

/* 进度区域 */
.progress-section {
  .progress-bar {
    height: 8px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    overflow: hidden;

    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #3b82f6, #3ecf8e);
      transition: width 0.3s ease-out;
      box-shadow: 0 0 10px rgba(62, 207, 142, 0.4);
    }
  }

  .progress-info {
    display: flex;
    justify-content: space-between;
    margin-top: 8px;
    font-size: 13px;
    color: var(--color-text-secondary, rgba(255, 255, 255, 0.7));

    .progress-counter {
      font-weight: 500;
    }

    .progress-percentage {
      font-weight: 600;
      color: #3ecf8e;
    }
  }
}

/* 日志工具栏 */
.log-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;

  .filter-group {
    display: flex;
    gap: 16px;

    .filter-label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-size: 13px;
      color: var(--color-text-secondary, rgba(255, 255, 255, 0.7));
      user-select: none;

      input[type="checkbox"] {
        cursor: pointer;
      }

      .level-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;

        &.level-info { background: #3b82f6; }
        &.level-warning { background: #f59e0b; }
        &.level-error { background: #ef4444; }
      }
    }
  }

  .toolbar-actions {
    .auto-scroll-label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-size: 13px;
      color: var(--color-text-secondary, rgba(255, 255, 255, 0.7));
      user-select: none;

      input[type="checkbox"] {
        cursor: pointer;
      }
    }
  }
}

/* 日志内容区域 */
.log-content {
  flex: 1;
  min-height: 300px;
  max-height: 50vh;
  overflow-y: auto;
  border: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.4);
  padding: 12px;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;

    &:hover {
      background: rgba(255, 255, 255, 0.3);
    }
  }

  .empty-logs {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: var(--color-text-muted, rgba(255, 255, 255, 0.4));
    gap: 12px;

    .empty-icon {
      font-size: 48px;
      opacity: 0.5;
    }
  }

  .log-groups {
    .log-group {
      margin-bottom: 16px;

      .group-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: rgba(255, 255, 255, 0.05);
        border-radius: 6px;
        margin-bottom: 8px;

        .group-icon {
          font-size: 16px;
        }

        .group-title {
          font-weight: 600;
          color: var(--color-text-primary, #fff);
          font-size: 14px;
        }

        .group-count {
          font-size: 12px;
          color: var(--color-text-secondary, rgba(255, 255, 255, 0.6));
        }
      }

      .log-lines {
        .log-line {
          display: flex;
          gap: 8px;
          padding: 4px 0;
          font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
          font-size: 13px;
          line-height: 1.5;

          .log-timestamp {
            color: var(--color-text-muted, rgba(255, 255, 255, 0.4));
            font-size: 12px;
            min-width: 70px;
          }

          .log-level {
            min-width: 75px;
            font-weight: 700;
            font-size: 11px;

            &.level-info { color: #3b82f6; }
            &.level-warning { color: #f59e0b; }
            &.level-error { color: #ef4444; }
          }

          .log-text {
            color: var(--color-text-primary, #fff);
            white-space: pre-wrap;
            word-break: break-word;
            flex: 1;
          }
        }
      }
    }
  }
}

/* 汇总信息 */
.log-summary {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--color-text-secondary, rgba(255, 255, 255, 0.8));

  &.done {
    background: rgba(62, 207, 142, 0.1);
    border: 1px solid rgba(62, 207, 142, 0.3);
    color: #3ecf8e;
  }

  &.has-error {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }

  .summary-icon {
    font-size: 18px;
  }

  .summary-text {
    flex: 1;
  }
}

/* 底部操作栏 */
.log-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;

  .btn {
    padding: 8px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    border: none;

    &.btn-secondary {
      background: rgba(255, 255, 255, 0.1);
      color: var(--color-text-primary, #fff);

      &:hover {
        background: rgba(255, 255, 255, 0.15);
      }
    }
  }
}

/* 动画 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(100px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
