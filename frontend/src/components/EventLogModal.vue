<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

const props = defineProps<{
  visible: boolean;
  title: string;
  progress: number;
  counter: string;
  summary: string;
  lines: Array<{ level: string; text: string }>;
  busy: boolean;
}>();

const emit = defineEmits<{ close: [] }>();
const logRef = ref<HTMLElement | null>(null);

const hasError = computed(() => props.summary.includes("失败"));

watch(
  () => props.lines.length,
  async () => {
    await nextTick();
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight;
    }
  },
);

const close = () => {
  emit("close");
};
</script>

<template>
  <div v-if="visible" class="rename-log-modal" @click.self="close">
    <div class="rename-log-dialog">
      <div class="rename-log-header">
        <h3 class="rename-log-title">{{ title }}</h3>
        <button class="rename-log-close" @click="close">×</button>
      </div>

      <div class="rename-progress-wrapper">
        <div class="rename-progress-track">
          <div class="rename-progress-fill" :style="{ width: `${progress}%` }" />
        </div>
        <div class="rename-progress-text">{{ progress }}% ({{ counter }})</div>
      </div>

      <div ref="logRef" class="rename-log-lines">
        <div v-for="(line, idx) in lines" :key="idx" class="rename-log-line" :class="`level-${line.level}`">
          [{{ line.level.toUpperCase() }}] {{ line.text }}
        </div>
      </div>

      <div class="rename-log-summary" :class="{ done: !!summary, 'has-error': hasError }">
        {{ summary }}
      </div>

      <div class="rename-log-actions">
        <button class="btn btn-primary" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>
