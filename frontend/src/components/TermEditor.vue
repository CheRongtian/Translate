<script setup lang="ts">
import type { TermItem } from "../types";

const props = defineProps<{
  terms: TermItem[];
  disabled: boolean;
}>();

const emit = defineEmits<{
  "update:terms": [terms: TermItem[]];
}>();

function blankTerm(): TermItem {
  return {
    source: "",
    suggested: "",
    translation: "",
    preserve: false,
    count: 0,
    category: "手动添加",
    context: "",
  };
}

function updateRow(index: number, patch: Partial<TermItem>) {
  const next = props.terms.map((term, rowIndex) =>
    rowIndex === index ? { ...term, ...patch } : term,
  );
  emit("update:terms", next);
}

function removeRow(index: number) {
  emit("update:terms", props.terms.filter((_, rowIndex) => rowIndex !== index));
}

function addRow() {
  emit("update:terms", [...props.terms, blankTerm()]);
}

async function importGlossary(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;

  try {
    const parsed = JSON.parse(await file.text());
    const rows = Array.isArray(parsed) ? parsed : parsed.terms;
    if (!Array.isArray(rows)) throw new Error("术语表必须是数组或包含 terms 数组。");

    const imported: TermItem[] = rows
      .map((row: Record<string, unknown>) => ({
        source: String(row.source || row.term || row.original || "").trim(),
        suggested: String(row.suggested || "").trim(),
        translation: String(row.translation || row.target || row.final || "").trim(),
        preserve: Boolean(row.preserve),
        count: Number(row.count || 0),
        category: String(row.category || "导入"),
        context: String(row.context || ""),
      }))
      .filter((row: TermItem) => row.source);

    const merged = [...props.terms];
    for (const term of imported) {
      const index = merged.findIndex((current) => current.source === term.source);
      if (index >= 0) merged[index] = { ...merged[index], ...term };
      else merged.push(term);
    }
    emit("update:terms", merged);
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "术语表读取失败。");
  }
}
</script>

<template>
  <section class="term-editor">
    <div class="term-editor-toolbar">
      <p class="section-note">
        指定译法留空就跳过；填写后采用你的译法；勾选“保留原文”会忽略指定译法。
      </p>
      <label class="secondary-button file-button" :class="{ disabled }">
        导入 JSON
        <input type="file" accept=".json" :disabled="disabled" @change="importGlossary" />
      </label>
    </div>

    <div class="term-table-wrap">
      <table class="term-table">
        <thead>
          <tr>
            <th>原词</th>
            <th>类型 / 建议</th>
            <th>指定译法（可留空）</th>
            <th>保留原文</th>
            <th>次数</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="terms.length === 0" class="empty-row">
            <td colspan="6">分析后会在这里显示候选，也可以直接添加。</td>
          </tr>
          <tr v-for="(term, index) in terms" :key="`${term.source}-${index}`">
            <td>
              <input
                class="table-input source-term"
                :value="term.source"
                :disabled="disabled"
                placeholder="原词"
                @input="updateRow(index, { source: ($event.target as HTMLInputElement).value })"
              />
              <small v-if="term.context" :title="term.context">{{ term.context }}</small>
            </td>
            <td>
              <span class="category">{{ term.category || "候选" }}</span>
              <small>{{ term.suggested || "无建议" }}</small>
            </td>
            <td>
              <input
                class="table-input"
                :value="term.translation"
                :disabled="disabled || term.preserve"
                :placeholder="term.suggested || '留空则跳过'"
                @input="updateRow(index, { translation: ($event.target as HTMLInputElement).value })"
              />
            </td>
            <td class="center-cell">
              <input
                type="checkbox"
                :checked="term.preserve"
                :disabled="disabled"
                @change="updateRow(index, { preserve: ($event.target as HTMLInputElement).checked })"
              />
            </td>
            <td class="count-cell">{{ term.count }}</td>
            <td>
              <button class="icon-button" :disabled="disabled" title="删除" @click="removeRow(index)">×</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <button class="secondary-button add-term" :disabled="disabled" @click="addRow">＋ 添加词项</button>
  </section>
</template>
