<script setup lang="ts">
import type { TranslationFailure } from "../types";

const props = defineProps<{
  translation: string;
  busy: boolean;
  current: number;
  total: number;
  failures: TranslationFailure[];
}>();

const emit = defineEmits<{
  revise: [];
}>();

async function copyResult() {
  if (props.translation) await navigator.clipboard.writeText(props.translation);
}

function downloadResult() {
  if (!props.translation) return;
  const url = URL.createObjectURL(new Blob([props.translation], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "translation.txt";
  anchor.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <section class="translator-pane result-pane">
    <header class="pane-header">
      <div class="result-title">
        <strong>译文</strong>
        <span v-if="busy || total" class="inline-progress">
          {{ busy ? `${current}/${total || "…"}` : "已完成" }}
        </span>
      </div>
      <div class="pane-tools">
        <button class="tool-button" :disabled="!translation" @click="emit('revise')">修正术语</button>
        <button class="tool-button" :disabled="!translation" @click="copyResult">复制</button>
        <button class="tool-button" :disabled="!translation" @click="downloadResult">下载</button>
      </div>
    </header>

    <div v-if="busy || total" class="progress-track">
      <span :style="{ width: `${total ? (current / total) * 100 : 0}%` }"></span>
    </div>

    <div v-if="failures.length" class="failure-box compact-failure">
      <strong>{{ failures.length }} 个段落翻译失败</strong>
      <span v-for="failure in failures" :key="failure.index">
        第 {{ failure.index }} 段：{{ failure.message }}
      </span>
    </div>

    <textarea
      class="translation-area"
      :value="translation"
      readonly
      placeholder="译文将在这里显示"
    />
  </section>
</template>
