<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean;
  disabled?: boolean;
  label?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue);
  }
}
</script>

<template>
  <button
    type="button"
    class="toggle-switch"
    :class="{ active: modelValue, disabled }"
    :disabled="disabled"
    :aria-label="label || '切换开关'"
    :aria-pressed="modelValue"
    @click="toggle"
  >
    <span class="toggle-track">
      <span class="toggle-thumb" />
    </span>
  </button>
</template>

<style scoped>
.toggle-switch {
  position: relative;
  width: 52px;
  height: 28px;
  border-radius: var(--radius-full);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-default);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
  padding: 3px;
}

.toggle-switch:focus-visible {
  outline: 2px solid var(--color-accent-cyan);
  outline-offset: 2px;
}

.toggle-switch.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-track {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-full);
  transition: background var(--transition-fast);
}

.toggle-thumb {
  position: absolute;
  top: 0;
  left: 0;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--color-text-tertiary);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all var(--transition-fast);
}

.toggle-switch.active .toggle-track {
  background: var(--color-brand-primary);
}

.toggle-switch.active .toggle-thumb {
  transform: translateX(24px);
  background: var(--color-text-primary);
}

.toggle-switch:hover:not(:disabled) .toggle-thumb {
  transform: scale(1.05);
}

.toggle-switch.active:hover:not(:disabled) .toggle-thumb {
  transform: translateX(24px) scale(1.05);
}
</style>
