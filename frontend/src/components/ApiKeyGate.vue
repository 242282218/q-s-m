<script setup lang="ts">
import { computed, ref, watch } from 'vue';

const props = defineProps<{
  hasStoredKey: boolean;
  message: string;
}>();

const emit = defineEmits<{
  clearStoredKey: [];
  dismiss: [];
  save: [apiKey: string];
}>();

const apiKey = ref('');
const canSave = computed(() => apiKey.value.trim().length > 0);

watch(
  () => [props.message, props.hasStoredKey],
  () => {
    apiKey.value = '';
  }
);

function submit() {
  if (!canSave.value) {
    return;
  }

  emit('save', apiKey.value.trim());
  apiKey.value = '';
}

function clearStoredKey() {
  apiKey.value = '';
  emit('clearStoredKey');
}
</script>

<template>
  <section class="auth-gate" role="dialog" aria-modal="false" aria-labelledby="auth-gate-title">
    <div class="auth-gate-card">
      <p class="auth-gate-kicker">访问受保护实例</p>
      <h2 id="auth-gate-title" class="auth-gate-title">输入 API Key 后继续</h2>
      <p class="auth-gate-message">{{ message }}</p>
      <p v-if="hasStoredKey" class="auth-gate-hint">
        检测到浏览器里已有本地 Key，但服务拒绝了它。你可以直接覆盖，或先清除再重输。
      </p>

      <form class="auth-gate-form" @submit.prevent="submit">
        <label class="auth-gate-label" for="api-key-gate-input">API 访问 Key</label>
        <input
          id="api-key-gate-input"
          v-model.trim="apiKey"
          class="auth-gate-input"
          type="password"
          autocomplete="off"
          placeholder="输入当前实例的 API Key"
        />

        <div class="auth-gate-actions">
          <button class="auth-gate-primary" type="submit" :disabled="!canSave">
            保存并重试
          </button>
          <button
            v-if="hasStoredKey"
            class="auth-gate-secondary"
            type="button"
            @click="clearStoredKey"
          >
            清除本地 Key
          </button>
          <button class="auth-gate-ghost" type="button" @click="$emit('dismiss')">稍后处理</button>
        </div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.auth-gate {
  position: fixed;
  top: calc(var(--site-header-top, 16px) + var(--site-header-height, 72px) + var(--spacing-4));
  left: 50%;
  width: min(calc(100% - 32px), 520px);
  transform: translateX(-50%);
  z-index: calc(var(--z-index-modal) - 1);
}

.auth-gate-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-2xl);
  background:
    radial-gradient(circle at top left, rgba(240, 90, 40, 0.22), transparent 42%),
    linear-gradient(145deg, rgba(10, 15, 27, 0.96), rgba(19, 28, 45, 0.92));
  box-shadow:
    0 20px 48px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.auth-gate-kicker {
  display: inline-flex;
  align-self: flex-start;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  background: rgba(240, 90, 40, 0.16);
  color: var(--color-brand-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  letter-spacing: var(--letter-spacing-wide);
  text-transform: uppercase;
}

.auth-gate-title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: clamp(1.5rem, 1.2rem + 1vw, 2rem);
  font-weight: var(--font-weight-extrabold);
  color: var(--color-text-primary);
}

.auth-gate-message,
.auth-gate-hint {
  margin: 0;
  line-height: var(--line-height-relaxed);
}

.auth-gate-message {
  color: var(--color-text-secondary);
}

.auth-gate-hint {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.auth-gate-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.auth-gate-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.auth-gate-input {
  width: 100%;
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-text-primary);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.auth-gate-input:focus {
  outline: none;
  border-color: rgba(240, 90, 40, 0.65);
  box-shadow:
    0 0 0 4px rgba(240, 90, 40, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.auth-gate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.auth-gate-primary,
.auth-gate-secondary,
.auth-gate-ghost {
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition:
    transform var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    opacity var(--transition-fast);
}

.auth-gate-primary {
  background: var(--color-brand-gradient);
  color: #fff;
  box-shadow: 0 12px 24px rgba(240, 90, 40, 0.24);
}

.auth-gate-primary:hover:not(:disabled),
.auth-gate-secondary:hover,
.auth-gate-ghost:hover {
  transform: translateY(-1px);
}

.auth-gate-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.auth-gate-secondary,
.auth-gate-ghost {
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.auth-gate-secondary {
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-primary);
}

.auth-gate-ghost {
  background: transparent;
  color: var(--color-text-tertiary);
}

@media (max-width: 640px) {
  .auth-gate {
    width: calc(100% - 24px);
    top: calc(var(--site-header-top, 16px) + var(--site-header-height, 64px) + var(--spacing-3));
  }

  .auth-gate-card {
    padding: var(--spacing-4);
  }

  .auth-gate-actions {
    flex-direction: column;
  }

  .auth-gate-primary,
  .auth-gate-secondary,
  .auth-gate-ghost {
    width: 100%;
    justify-content: center;
  }
}
</style>
