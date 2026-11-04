<script setup>
import { F } from "../../lib/forms.js";
import { formatDate } from "../../lib/format.js";
import FormPictures from "./FormPictures.vue";
import FormTable from "./FormTable.vue";
import SignaturePad from "./SignaturePad.vue";

// The form itself, from a template's definition: to fill in, or read-only for a form already submitted.
// `uploader(content, filename)` keeps a picture with the form; without it (a designer's preview) nothing is sent.
const props = defineProps({
  spec: { type: Object, required: true },
  modelValue: { type: Object, default: () => ({}) },
  readonly: { type: Boolean, default: false },
  missing: { type: Array, default: () => [] },
  uploader: { type: Function, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const set = (key, value) => emit("update:modelValue", { ...props.modelValue, [key]: value });
const id = (field) => `f-${field.fieldname}`;
const isMissing = (field) => props.missing.includes(field.fieldname);

function shown(field) {
  const value = props.modelValue[field.fieldname];
  if (value === undefined || value === null || value === "") return "—";
  if (field.fieldtype === F.DATE) return formatDate(value);
  if (field.fieldtype === F.NUMBER && field.unit) return `${value} ${field.unit}`;
  return value;
}
</script>

<template>
  <div class="space-y-4">
    <template v-for="field in spec.fields" :key="field.fieldname">
      <h3 v-if="field.fieldtype === F.SECTION" class="m-0 border-b border-line pb-1 pt-2 text-sm font-semibold">{{ field.label }}</h3>

      <div v-else-if="field.fieldtype === F.CHECK">
        <label class="flex items-center gap-2 text-sm" :class="{ 'text-danger': isMissing(field) }">
          <input type="checkbox" class="h-5 w-5" :checked="Boolean(modelValue[field.fieldname])" :disabled="readonly" @change="set(field.fieldname, $event.target.checked ? 1 : 0)" />
          <span>{{ field.label }}<span v-if="field.reqd" class="text-danger"> *</span></span>
        </label>
        <p v-if="field.description" class="m-0 mt-1 text-xs text-ink-muted">{{ field.description }}</p>
      </div>

      <div v-else>
        <label class="label" :for="id(field)">{{ field.label }}<span v-if="field.reqd && !readonly" class="text-danger"> *</span></label>
        <p v-if="field.description && !readonly" class="m-0 mb-1 text-xs text-ink-muted">{{ field.description }}</p>

        <FormTable v-if="field.fieldtype === F.TABLE" :field="field" :model-value="modelValue[field.fieldname]" :readonly="readonly"
          :class="{ 'border-danger': isMissing(field) }" @update:model-value="set(field.fieldname, $event)" />
        <FormPictures v-else-if="field.fieldtype === F.IMAGE" :model-value="modelValue[field.fieldname]" :readonly="readonly" :uploader="uploader" :label="field.label"
          @update:model-value="set(field.fieldname, $event)" />
        <SignaturePad v-else-if="field.fieldtype === F.SIGNATURE" :model-value="modelValue[field.fieldname]" :readonly="readonly" :uploader="uploader" :label="field.label"
          @update:model-value="set(field.fieldname, $event)" />

        <p v-else-if="readonly" class="m-0 whitespace-pre-wrap text-sm">{{ shown(field) }}</p>
        <textarea v-else-if="field.fieldtype === F.LONG" :id="id(field)" class="input" :class="{ 'is-invalid': isMissing(field) }" rows="3" :value="modelValue[field.fieldname] ?? ''"
          @input="set(field.fieldname, $event.target.value)"></textarea>
        <div v-else-if="field.fieldtype === F.SELECT && field.choices.length <= 4" :id="id(field)" class="flex flex-wrap gap-2" role="radiogroup" :aria-label="field.label">
          <button v-for="choice in field.choices" :key="choice" type="button" class="btn" role="radio" :aria-checked="modelValue[field.fieldname] === choice"
            :class="modelValue[field.fieldname] === choice ? 'btn-primary' : isMissing(field) ? 'border-danger' : ''" @click="set(field.fieldname, choice)">{{ choice }}</button>
        </div>
        <select v-else-if="field.fieldtype === F.SELECT" :id="id(field)" class="input" :class="{ 'is-invalid': isMissing(field) }" :value="modelValue[field.fieldname] ?? ''" @change="set(field.fieldname, $event.target.value)">
          <option value="">Chọn...</option>
          <option v-for="choice in field.choices" :key="choice" :value="choice">{{ choice }}</option>
        </select>
        <div v-else-if="field.fieldtype === F.NUMBER" class="flex items-center gap-2">
          <input :id="id(field)" class="input max-w-[12rem]" :class="{ 'is-invalid': isMissing(field) }" type="number" step="any" inputmode="decimal" :min="field.min_value || undefined" :max="field.max_value || undefined"
            :value="modelValue[field.fieldname] ?? ''" @input="set(field.fieldname, $event.target.value)" />
          <span v-if="field.unit" class="text-sm text-ink-muted">{{ field.unit }}</span>
        </div>
        <input v-else :id="id(field)" class="input" :class="{ 'is-invalid': isMissing(field) }" :type="field.fieldtype === F.DATE ? 'date' : 'text'" :value="modelValue[field.fieldname] ?? ''"
          @input="set(field.fieldname, $event.target.value)" />
        <p v-if="isMissing(field)" class="m-0 mt-1 text-xs text-danger" role="alert">Cần điền mục này.</p>
      </div>
    </template>
  </div>
</template>
