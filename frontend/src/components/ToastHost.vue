<script setup lang="ts">
import { useToast } from "@/composables/useToast";

const { toasts } = useToast();
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <div
      v-for="item in toasts"
      :key="item.id"
      class="toast-item"
      :class="`toast-${item.type}`"
    >
      {{ item.text }}
    </div>
  </div>
</template>

