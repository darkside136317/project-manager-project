<script setup>
import { computed, ref, watch } from "vue";
import { formatDate } from "../../lib/format.js";
import Drawer from "../Drawer.vue";
import Icon from "../Icon.vue";

// Before dates change: what would move, what happens to the end of the project, why (a reason is required once work
// has been given). Nothing is written until the person confirms.
const props = defineProps({
  plan: { type: Object, default: null },
  title: { type: String, default: "Dời lịch" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["confirm", "cancel"]);
const reason = ref("");
const missing = ref(false);
const SHOWN = 40;

const shown = computed(() => (props.plan?.changes || []).slice(0, SHOWN));
const rest = computed(() => Math.max(0, (props.plan?.total || 0) - SHOWN));
const pushed = computed(() => (props.plan?.changes || []).filter((change) => !change.direct).length);
const endMoves = computed(() => props.plan && props.plan.plan_end_before !== props.plan.plan_end_after);

watch(() => props.plan, () => {
  reason.value = "";
  missing.value = false;
});

function confirm() {
  if (props.plan?.reason_required && !reason.value.trim()) {
    missing.value = true;
    return;
  }
  emit("confirm", reason.value.trim());
}
</script>

<template>
  <Drawer :open="Boolean(plan)" :title="title" width="600px" @close="emit('cancel')">
    <div v-if="plan" class="space-y-4 text-sm">
      <p v-if="!plan.total" class="m-0 rounded-md bg-surface-muted px-3 py-2">Không có gì thay đổi: {{ plan.clamped ? "việc này không thể sớm hơn khi các việc trước chưa xong." : "ngày mới trùng với kế hoạch hiện tại." }}</p>
      <template v-else>
        <p class="m-0">
          <strong>{{ plan.total }}</strong> việc đổi ngày<template v-if="pushed">, trong đó <strong>{{ pushed }}</strong> việc bị đẩy theo phụ thuộc</template>.
        </p>
        <p v-if="plan.clamped" class="m-0 rounded-md bg-warning-soft px-3 py-2">Ngày đã chọn sớm hơn phụ thuộc cho phép nên được đẩy tới ngày sớm nhất có thể.</p>
        <dl class="m-0 grid grid-cols-2 gap-2 rounded-lg border border-line p-3">
          <div><dt class="text-xs text-ink-muted">Dự án kết thúc</dt><dd class="m-0 font-medium">{{ formatDate(plan.plan_end_before) }}<template v-if="endMoves"> → <span class="text-danger">{{ formatDate(plan.plan_end_after) }}</span></template></dd></div>
          <div v-if="plan.contract_end"><dt class="text-xs text-ink-muted">Hạn của dự án</dt><dd class="m-0 font-medium">{{ formatDate(plan.contract_end) }}</dd></div>
        </dl>
        <p v-if="plan.over_contract" class="m-0 flex items-center gap-2 rounded-md bg-danger-soft px-3 py-2 text-danger"><Icon name="alert-triangle" :size="16" /> Kế hoạch mới vượt hạn của dự án.</p>
        <table class="w-full text-left">
          <thead class="text-xs text-ink-muted"><tr class="border-b border-line"><th class="py-1 pr-2 font-medium">Công việc</th><th class="py-1 pr-2 font-medium">Từ</th><th class="py-1 font-medium">Thành</th></tr></thead>
          <tbody>
            <tr v-for="change in shown" :key="change.name" class="border-b border-line align-top last:border-0">
              <td class="py-1.5 pr-2"><span :class="{ 'font-medium': change.direct }">{{ change.label }}</span></td>
              <td class="whitespace-nowrap py-1.5 pr-2 text-xs text-ink-muted">{{ formatDate(change.from_start) }}<br />{{ formatDate(change.from_end) }}</td>
              <td class="whitespace-nowrap py-1.5 text-xs">{{ formatDate(change.to_start) }}<br />{{ formatDate(change.to_end) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="rest" class="m-0 text-xs text-ink-muted">và {{ rest }} việc khác.</p>
        <div>
          <label class="label" for="move-reason">Lý do đổi ngày<span v-if="plan.reason_required" class="text-danger"> *</span></label>
          <textarea id="move-reason" v-model="reason" class="input" :class="{ 'is-invalid': missing }" rows="2"></textarea>
          <p v-if="missing" class="m-0 mt-1 text-xs text-danger" role="alert">Có việc đã giao cho người thực hiện: cần ghi lý do. Họ sẽ nhận được thông báo.</p>
        </div>
      </template>
      <p v-if="error" class="m-0 whitespace-pre-line rounded-md bg-danger-soft px-3 py-2 text-danger" role="alert">{{ error }}</p>
    </div>
    <template #footer>
      <button class="btn" type="button" @click="emit('cancel')">{{ plan?.total ? "Hủy" : "Đóng" }}</button>
      <button v-if="plan?.total" class="btn btn-primary" type="button" :disabled="busy" @click="confirm"><Icon :name="busy ? 'loader' : 'check'" :size="16" :spin="busy" /> Dời lịch</button>
    </template>
  </Drawer>
</template>
