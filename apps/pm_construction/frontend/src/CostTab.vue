<script setup>
import { computed, inject, onMounted, ref } from "vue";
import { moneyText, qtyText, site } from "./construction.js";

// Chi phí: per section and work item, the estimate (BOQ), the value of the work done, what it actually cost (materials,
// machines, labour) and the gap. Only for who may see the project's costs.
const { name: project } = inject("project");
const data = ref(null);
const error = ref("");
const total = computed(() => data.value?.total || {});
const tiles = computed(() => [
  { label: "Giá trị dự toán", value: total.value.estimate },
  { label: "Giá trị đã thi công", value: total.value.earned },
  { label: "Chi phí thực tế", value: total.value.actual },
  { label: "Chênh lệch (đã thi công − thực tế)", value: total.value.variance, tone: total.value.variance < 0 ? "text-danger" : "text-success" },
]);

onMounted(async () => {
  try {
    data.value = await site.costs(project.value);
  } catch (e) {
    error.value = e.message;
  }
});
</script>

<template>
  <p v-if="error" class="rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-muted" role="status">{{ error }}</p>
  <div v-else-if="data" class="space-y-4" data-costs>
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <div v-for="tile in tiles" :key="tile.label" class="card px-4 py-3">
        <span class="block text-xs text-ink-muted">{{ tile.label }}</span>
        <span class="text-lg font-semibold" :class="tile.tone">{{ moneyText(tile.value, { short: true }) }}</span>
      </div>
    </div>
    <p class="m-0 text-xs text-ink-muted">Vật tư {{ moneyText(total.material, { short: true }) }} · Máy {{ moneyText(total.machine, { short: true }) }}
      · Nhân công {{ moneyText(total.labour, { short: true }) }}. Vật tư tính theo giá xuất kho; máy theo ca × đơn giá ca; nhân công theo công đã xác nhận.</p>
    <div class="card overflow-x-auto">
      <table class="w-full min-w-[820px] text-sm">
        <thead><tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="px-4 py-2">Hạng mục, công tác</th><th class="px-2 text-right">Dự toán</th><th class="px-2 text-right">Đã thi công</th>
          <th class="px-2 text-right">Vật tư</th><th class="px-2 text-right">Máy</th><th class="px-2 text-right">Nhân công</th>
          <th class="px-2 text-right">Thực tế</th><th class="px-4 text-right">Chênh lệch</th></tr></thead>
        <tbody>
          <tr v-for="row in data.rows" :key="row.name" class="border-b border-line last:border-0" :class="{ 'font-semibold bg-surface-muted': row.is_group }" data-cost-row>
            <td class="py-1.5 pr-2" :style="{ paddingLeft: `${1 + (row.level - 1) * 0.9}rem` }">{{ row.label }}
              <span v-if="!row.is_group && row.planned_qty" class="block text-xs font-normal text-ink-muted">{{ qtyText(row.done_qty) }} / {{ qtyText(row.planned_qty, row.uom) }}</span></td>
            <td class="px-2 text-right">{{ moneyText(row.estimate, { short: true }) }}</td>
            <td class="px-2 text-right">{{ moneyText(row.earned, { short: true }) }}</td>
            <td class="px-2 text-right">{{ moneyText(row.material, { short: true }) }}</td>
            <td class="px-2 text-right">{{ moneyText(row.machine, { short: true }) }}</td>
            <td class="px-2 text-right">{{ moneyText(row.labour, { short: true }) }}</td>
            <td class="px-2 text-right">{{ moneyText(row.actual, { short: true }) }}</td>
            <td class="px-4 text-right" :class="row.variance < 0 ? 'text-danger' : ''">{{ moneyText(row.variance, { short: true }) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
