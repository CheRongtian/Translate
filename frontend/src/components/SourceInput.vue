<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  modelValue: string;
  disabled: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  upload: [file: File];
  clear: [];
}>();

const dragging = ref(false);

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) emit("upload", file);
  input.value = "";
}

function dropFile(event: DragEvent) {
  dragging.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) emit("upload", file);
}
</script>

<template>
  <section
    class="translator-pane source-pane"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="dropFile"
  >
    <header class="pane-header">
      <strong>源文本</strong>
      <div class="pane-tools">
        <span class="character-count">{{ modelValue.length.toLocaleString() }} 字符</span>
        <label class="tool-button file-button" :class="{ disabled }">
          上传文件
          <input
            type="file"
            accept=".txt,.pdf,.docx,.png,.jpg,.jpeg"
            :disabled="disabled"
            @change="chooseFile"
          />
        </label>
        <button class="tool-button" :disabled="disabled || !modelValue" @click="emit('clear')">清空</button>
      </div>
    </header>

    <textarea
      class="translation-area"
      :value="modelValue"
      :disabled="disabled"
      placeholder="粘贴或上传需要翻译的文本"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />

    <div v-if="dragging" class="drop-overlay">松开即可读取文件</div>
  </section>
</template>
