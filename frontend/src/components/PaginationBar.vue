<script setup lang="ts">
import type { Pagination, CursorPagination } from '@/types/api';

const props = defineProps<{
  pagination?: Pagination;
  cursorPagination?: CursorPagination;
  loading?: boolean;
  mode?: 'page' | 'cursor';
}>();

const emit = defineEmits<{
  change: [page: number];
  cursorChange: [direction: 'next' | 'prev'];
}>();

// 页码分页方法
const prevPage = () => {
  if (props.pagination && props.pagination.page > 1) {
    emit('change', props.pagination.page - 1);
  }
};

const nextPage = () => {
  if (props.pagination && props.pagination.page < props.pagination.total_pages) {
    emit('change', props.pagination.page + 1);
  }
};

// 游标分页方法
const prevCursor = () => {
  if (props.cursorPagination?.prev_cursor) {
    emit('cursorChange', 'prev');
  }
};

const nextCursor = () => {
  if (props.cursorPagination?.has_more) {
    emit('cursorChange', 'next');
  }
};
</script>

<template>
  <!-- 传统页码分页 -->
  <div class="pager pagination" v-if="mode !== 'cursor' && pagination && pagination.total_pages > 1">
    <button class="btn-page" :disabled="loading || pagination.page <= 1" @click="prevPage">
      上一页
    </button>
    <div class="pager-text page-info">
      第 {{ pagination.page }} / {{ pagination.total_pages }} 页 · 共 {{ pagination.total }} 项
    </div>
    <button
      class="btn-page"
      :disabled="loading || pagination.page >= pagination.total_pages"
      @click="nextPage"
    >
      下一页
    </button>
  </div>

  <!-- 游标分页 -->
  <div class="pager pagination cursor-mode" v-if="mode === 'cursor' && cursorPagination">
    <button
      class="btn-page"
      :disabled="loading || !cursorPagination.prev_cursor"
      @click="prevCursor"
    >
      上一页
    </button>
    <div class="pager-text page-info">
      <span v-if="cursorPagination.total !== null">共 {{ cursorPagination.total }} 项 · </span>
      <span>每页 {{ cursorPagination.limit }} 项</span>
      <span v-if="cursorPagination.has_more" class="has-more">（还有更多）</span>
    </div>
    <button
      class="btn-page"
      :disabled="loading || !cursorPagination.has_more"
      @click="nextCursor"
    >
      下一页
    </button>
  </div>
</template>

<style scoped>
.cursor-mode .has-more {
  color: #888;
  font-size: 0.9em;
}
</style>
