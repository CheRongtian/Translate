<script setup lang="ts">
import { computed, ref } from "vue";

import { analyzeTerms, applyTerms, extractDocument, translate } from "./api/client";
import RevisionPanel from "./components/RevisionPanel.vue";
import SourceInput from "./components/SourceInput.vue";
import TermEditor from "./components/TermEditor.vue";
import TranslationResult from "./components/TranslationResult.vue";
import type { TermItem, TranslationEvent, TranslationFailure } from "./types";


const sourceText = ref("");
const terms = ref<TermItem[]>([]);
const translation = ref("");
const busy = ref(false);
const action = ref("");
const error = ref("");
const currentBlock = ref(0);
const totalBlocks = ref(0);
const failures = ref<TranslationFailure[]>([]);
const streamedBlocks = ref<string[]>([]);
const termDrawerOpen = ref(false);
const revisionOpen = ref(false);

const canAnalyze = computed(() => sourceText.value.trim().length > 0 && !busy.value);
const canTranslate = computed(() => sourceText.value.trim().length > 0 && !busy.value);

function messageFrom(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : String(errorValue);
}

function setStreamedBlock(index: number, value: string) {
  const next = [...streamedBlocks.value];
  while (next.length < index) next.push("");
  next[index - 1] = value;
  streamedBlocks.value = next;
  translation.value = next.filter(Boolean).join("\n\n");
}

function mergeAnalyzedTerms(analyzed: TermItem[]): TermItem[] {
  const previous = new Map(terms.value.map((term) => [term.source, term]));
  const merged = analyzed.map((term) => {
    const existing = previous.get(term.source);
    previous.delete(term.source);
    return existing
      ? { ...term, translation: existing.translation, preserve: existing.preserve }
      : term;
  });
  for (const remaining of previous.values()) {
    if (remaining.translation || remaining.preserve || remaining.category === "手动添加") {
      merged.push(remaining);
    }
  }
  return merged;
}

async function uploadFile(file: File) {
  busy.value = true;
  action.value = "正在读取文件";
  error.value = "";
  try {
    sourceText.value = await extractDocument(file);
    terms.value = [];
    translation.value = "";
    failures.value = [];
    currentBlock.value = 0;
    totalBlocks.value = 0;
    streamedBlocks.value = [];
  } catch (requestError) {
    error.value = messageFrom(requestError);
  } finally {
    busy.value = false;
    action.value = "";
  }
}

async function runTermAnalysis() {
  if (!canAnalyze.value) return;
  busy.value = true;
  action.value = "正在分析术语";
  error.value = "";
  try {
    terms.value = mergeAnalyzedTerms(await analyzeTerms(sourceText.value));
    termDrawerOpen.value = true;
  } catch (requestError) {
    error.value = messageFrom(requestError);
  } finally {
    busy.value = false;
    action.value = "";
  }
}

function handleTranslationEvent(event: TranslationEvent) {
  if (event.type === "start") {
    totalBlocks.value = event.total;
    currentBlock.value = 0;
    streamedBlocks.value = [];
    return;
  }
  if (event.type === "block_start") {
    totalBlocks.value = event.total;
    setStreamedBlock(event.index, "");
    return;
  }
  if (event.type === "delta") {
    const current = streamedBlocks.value[event.index - 1] || "";
    setStreamedBlock(event.index, current + event.text);
    return;
  }
  if (event.type === "block_reset") {
    setStreamedBlock(event.index, "");
    return;
  }
  if (event.type === "block") {
    currentBlock.value = event.index;
    setStreamedBlock(event.index, event.translation);
    return;
  }
  if (event.type === "block_error") {
    currentBlock.value = event.index;
    setStreamedBlock(event.index, "");
    failures.value.push({ index: event.index, message: event.message });
    return;
  }
  if (event.type === "complete") {
    translation.value = event.translation;
    failures.value = event.errors;
    currentBlock.value = totalBlocks.value;
    return;
  }
  if (event.type === "fatal_error") error.value = event.message;
}

async function runTranslation() {
  if (!canTranslate.value) return;
  busy.value = true;
  action.value = "正在翻译";
  error.value = "";
  failures.value = [];
  translation.value = "";
  streamedBlocks.value = [];
  currentBlock.value = 0;
  totalBlocks.value = 0;
  try {
    await translate(sourceText.value, terms.value, handleTranslationEvent);
  } catch (requestError) {
    error.value = messageFrom(requestError);
  } finally {
    busy.value = false;
    action.value = "";
  }
}

function upsertTerm(source: string, target: string, preserve: boolean): TermItem[] {
  const next = terms.value.map((term) => ({ ...term }));
  const index = next.findIndex((term) => term.source === source);
  const patch = { source, translation: preserve ? "" : target, preserve };
  if (index >= 0) next[index] = { ...next[index], ...patch };
  else {
    next.push({
      ...patch,
      suggested: "",
      count: 0,
      category: "手动添加",
      context: "",
    });
  }
  return next;
}

async function applyRevision(source: string, target: string, preserve: boolean) {
  terms.value = upsertTerm(source, target, preserve);
  busy.value = true;
  action.value = "正在应用术语规则";
  error.value = "";
  try {
    translation.value = await applyTerms(translation.value, terms.value);
    revisionOpen.value = false;
  } catch (requestError) {
    error.value = messageFrom(requestError);
  } finally {
    busy.value = false;
    action.value = "";
  }
}

async function retranslateWithRevision(source: string, target: string, preserve: boolean) {
  terms.value = upsertTerm(source, target, preserve);
  revisionOpen.value = false;
  await runTranslation();
}

function clearAll() {
  sourceText.value = "";
  terms.value = [];
  translation.value = "";
  error.value = "";
  failures.value = [];
  currentBlock.value = 0;
  totalBlocks.value = 0;
  streamedBlocks.value = [];
  termDrawerOpen.value = false;
  revisionOpen.value = false;
}
</script>

<template>
  <main class="page-shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">译</span>
        <div>
          <h1>本地翻译</h1>
          <p>数据留在本机</p>
        </div>
      </div>
      <div class="model-badge">qwen2.5:14b</div>
    </header>

    <section class="translator-shell">
      <div class="translator-grid">
        <SourceInput v-model="sourceText" :disabled="busy" @upload="uploadFile" @clear="clearAll" />
        <TranslationResult
          :translation="translation"
          :busy="busy && action === '正在翻译'"
          :current="currentBlock"
          :total="totalBlocks"
          :failures="failures"
          @revise="revisionOpen = true"
        />
      </div>

      <div class="actionbar">
        <div class="action-status" :class="{ failed: error }">
          <span v-if="action" class="spinner"></span>
          <span>{{ error || action || "准备就绪" }}</span>
        </div>
        <div class="action-buttons">
          <button class="secondary-button" :disabled="!canAnalyze" @click="runTermAnalysis">分析术语</button>
          <button class="primary-button" :disabled="!canTranslate" @click="runTranslation">开始翻译</button>
        </div>
      </div>
    </section>

    <section class="term-drawer" :class="{ open: termDrawerOpen }">
      <button class="drawer-toggle" @click="termDrawerOpen = !termDrawerOpen">
        <span>
          <strong>术语表</strong>
          <small>{{ terms.length ? `${terms.length} 个候选` : "可选" }}</small>
        </span>
        <span class="drawer-arrow">{{ termDrawerOpen ? "⌄" : "⌃" }}</span>
      </button>
      <div v-if="termDrawerOpen" class="drawer-body">
        <TermEditor v-model:terms="terms" :disabled="busy" />
      </div>
    </section>

    <div v-if="revisionOpen" class="modal-backdrop" @click.self="revisionOpen = false">
      <RevisionPanel
        :disabled="busy || !sourceText.trim()"
        :has-translation="Boolean(translation)"
        @close="revisionOpen = false"
        @apply="applyRevision"
        @retranslate="retranslateWithRevision"
      />
    </div>
  </main>
</template>
