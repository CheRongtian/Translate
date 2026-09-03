<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  disabled: boolean;
  hasTranslation: boolean;
}>();

const emit = defineEmits<{
  apply: [source: string, translation: string, preserve: boolean];
  retranslate: [source: string, translation: string, preserve: boolean];
  close: [];
}>();

const source = ref("");
const translation = ref("");
const preserve = ref(false);

function submit(mode: "apply" | "retranslate") {
  const original = source.value.trim();
  const target = translation.value.trim();
  if (!original || (!target && !preserve.value)) return;
  if (mode === "apply") emit("apply", original, target, preserve.value);
  else emit("retranslate", original, target, preserve.value);
}
</script>

<template>
  <section class="revision-panel">
    <div class="modal-heading">
      <div>
        <h2>修正术语</h2>
        <p>补充一个明确规则，可以直接应用到当前译文，也可以携带完整术语表重新翻译。</p>
      </div>
      <button class="modal-close" aria-label="关闭" @click="emit('close')">×</button>
    </div>
    <div class="revision-fields">
      <label>
        <span>原词</span>
        <input v-model="source" :disabled="disabled" placeholder="输入原词" />
      </label>
      <label>
        <span>指定译法</span>
        <input v-model="translation" :disabled="disabled || preserve" placeholder="输入指定译法" />
      </label>
      <label class="preserve-field">
        <input v-model="preserve" type="checkbox" :disabled="disabled" />
        保留原文
      </label>
    </div>
    <div class="revision-actions">
      <button class="secondary-button" :disabled="disabled || !hasTranslation" @click="submit('apply')">
        应用到当前译文
      </button>
      <button class="secondary-button" :disabled="disabled" @click="submit('retranslate')">
        加入术语表并重新翻译
      </button>
    </div>
  </section>
</template>
