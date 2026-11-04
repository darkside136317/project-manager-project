<script setup>
import { computed } from "vue";
import { F, tableRows } from "../../lib/forms.js";
import Icon from "../Icon.vue";

// A table inside a form. One markup for both sizes: rows are stacked cards on a phone (each cell shows its column
// name) and a grid on a wide screen. A checklist's rows are fixed by the template: first column read-only, no add/remove.
const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);

const preset = computed(() => Boolean(props.field.preset_rows?.length));
const editable = computed(() => !preset.value && !props.readonly);
const rows = computed(() => {
  const list = tableRows(props.field, props.modelValue);
  return list.length || !editable.value ? list : [{}];
});
const grid = computed(() => ({
  gridTemplateColumns: `repeat(${props.field.columns.length}, minmax(0, 1fr))${editable.value ? " 32px" : ""}`,
}));

function setCell(index, key, value) {
  const next = rows.value.map((row) => ({ ...row }));
  next[index][key] = value;
  emit("update:modelValue", next);
}
const addRow = () => emit("update:modelValue", [...rows.value, {}]);
const removeRow = (index) => emit("update:modelValue", rows.value.filter((_row, i) => i !== index));
const display = (column, value) => (column.type === F.CHECK ? (value ? "Có" : "") : value ?? "");
</script>

<template>
  <div class="rounded-lg border border-line">
    <div class="form-row hidden gap-2 border-b border-line bg-surface-muted px-2 py-1.5 text-xs font-semibold text-ink-muted sm:grid" :style="grid">
      <span v-for="column in field.columns" :key="column.key">{{ column.label }}</span>
    </div>
    <div v-for="(row, index) in rows" :key="index" class="form-row grid items-start gap-2 border-b border-line p-2 last:border-b-0" :style="grid">
      <div v-for="(column, position) in field.columns" :key="column.key" class="min-w-0">
        <span class="mb-0.5 block text-xs text-ink-muted sm:hidden">{{ column.label }}</span>
        <span v-if="readonly || (preset && position === 0)" class="block whitespace-pre-wrap text-sm" :class="{ 'font-medium': preset && position === 0 }">{{ display(column, row[column.key]) }}</span>
        <select v-else-if="column.type === F.SELECT" class="input" :value="row[column.key] ?? ''" :aria-label="column.label" @change="setCell(index, column.key, $event.target.value)">
          <option value="">—</option>
          <option v-for="choice in column.choices" :key="choice" :value="choice">{{ choice }}</option>
        </select>
        <input v-else-if="column.type === F.CHECK" type="checkbox" class="h-5 w-5" :checked="Boolean(row[column.key])" :aria-label="column.label" @change="setCell(index, column.key, $event.target.checked ? 1 : 0)" />
        <input v-else class="input" :type="column.type === F.DATE ? 'date' : column.type === F.NUMBER ? 'number' : 'text'" :step="column.type === F.NUMBER ? 'any' : undefined"
          :value="row[column.key] ?? ''" :aria-label="column.label" @input="setCell(index, column.key, $event.target.value)" />
      </div>
      <button v-if="editable" class="btn btn-ghost btn-icon !min-h-0 justify-self-end !p-1" type="button" aria-label="Xóa hàng" @click="removeRow(index)"><Icon name="x" :size="15" /></button>
    </div>
    <p v-if="readonly && !rows.length" class="m-0 p-2 text-sm text-ink-muted">Chưa có hàng nào.</p>
    <div v-if="editable" class="p-2"><button class="btn btn-ghost" type="button" @click="addRow"><Icon name="plus" :size="16" /> Thêm hàng</button></div>
  </div>
</template>

<style scoped>
/* A phone stacks the cells of a row; a wide screen lines them up under the column names. */
@media (max-width: 639px) {
  .form-row { grid-template-columns: minmax(0, 1fr) !important; }
}
</style>
