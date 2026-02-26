<script setup lang="ts">
import type { Pagination } from "@/types/api";

const props = defineProps<{
  pagination: Pagination;
  loading?: boolean;
}>();

const emit = defineEmits<{
  change: [page: number];
}>();

const prev = () => {
  if (props.pagination.page > 1) {
    emit("change", props.pagination.page - 1);
  }
};

const next = () => {
  if (props.pagination.page < props.pagination.total_pages) {
    emit("change", props.pagination.page + 1);
  }
};
</script>

<template>
  <div class="pager pagination" v-if="pagination.total_pages > 1">
    <button class="btn-page" :disabled="loading || pagination.page <= 1" @click="prev">
      上一页
    </button>
    <div class="pager-text page-info">
      第 {{ pagination.page }} / {{ pagination.total_pages }} 页 · 共 {{ pagination.total }} 项
    </div>
    <button class="btn-page" :disabled="loading || pagination.page >= pagination.total_pages" @click="next">
      下一页
    </button>
  </div>
</template>
