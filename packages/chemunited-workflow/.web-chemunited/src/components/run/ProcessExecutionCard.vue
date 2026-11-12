<script setup lang="ts">
import type { NodeCard, ProcessCard } from '../../stores/runStatus'
import { operatorInputKey } from '../../lib/runPresentation'
const props = defineProps<{ card: ProcessCard; nowSeconds: number; drafts: Record<string, string>; notExecuted?: boolean }>()
const emit = defineEmits<{ reply: [card: ProcessCard, node: NodeCard]; draft: [key: string, value: string] }>()
function updateDraft(node: NodeCard, event: Event) { emit('draft', operatorInputKey(props.card.stepKey, node.nodeId), (event.target as HTMLInputElement).value) }
function remaining(node: NodeCard): number {
  return node.waitSeconds === null || node.waitStartedAt === null ? 0 : Math.max(0, node.waitSeconds - (props.nowSeconds - node.waitStartedAt))
}
function waitFraction(node: NodeCard): number { return !node.waitSeconds ? 0 : remaining(node) / node.waitSeconds }
function formatWait(seconds: number): string {
  const whole = Math.ceil(seconds)
  return whole < 60 ? `${whole}s` : `${Math.floor(whole / 60)}:${(whole % 60).toString().padStart(2, '0')}`
}
</script>

<template>
        <div
          :class="['process-card', card.status]"
        >
          <div class="process-card-header">
            <span :class="['process-status-dot', card.status]" aria-hidden="true" />
            <span class="process-name">{{ card.displayName }}</span>
            <span :class="['process-badge', card.status]">{{ notExecuted && card.status === 'waiting' ? 'Not executed' : card.status }}</span>
          </div>
          <p v-if="card.description" class="process-description">{{ card.description }}</p>
          <p v-if="card.hasFailed && card.errorMessage" class="process-error">
            {{ card.errorMessage }}
          </p>
          <div v-if="card.nodes.length" class="node-list">
            <div
              v-for="node in card.nodes"
              :key="node.nodeId"
              :class="['node-row', node.state.toLowerCase()]"
            >
              <div class="node-row-header">
                <span class="node-name">
                  {{ node.method || node.nodeId }}
                  <span v-if="node.iteration > 0" class="node-iteration-badge">
                    iteration {{ node.iteration }}
                  </span>
                </span>
                <span class="node-percentage">{{ node.percentage }}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: node.percentage + '%' }" />
              </div>
              <div v-if="node.message || remaining(node) > 0" class="node-status-row">
                <p v-if="node.message" class="node-message">{{ node.message }}</p>
                <span v-if="remaining(node) > 0" class="node-wait">
                  <span
                    class="node-wait-clock"
                    :style="{ '--wait-frac': waitFraction(node) }"
                    aria-hidden="true"
                  />
                  <span class="node-wait-time">{{ formatWait(remaining(node)) }}</span>
                </span>
              </div>
              <form
                v-if="node.awaitingInput"
                class="node-input-row"
                @submit.prevent="emit('reply', card, node)"
              >
                <label class="node-input-prompt" :for="`input-${encodeURIComponent(operatorInputKey(card.stepKey, node.nodeId))}`">
                  {{ node.inputPrompt || 'Operator input requested.' }}
                </label>
                <div class="node-input-controls">
                  <input
                    :id="`input-${encodeURIComponent(operatorInputKey(card.stepKey, node.nodeId))}`"
                    :value="drafts[operatorInputKey(card.stepKey, node.nodeId)] ?? ''"
                    type="text"
                    class="node-input-field"
                    placeholder="Type a reply…"
                    @input="updateDraft(node, $event)"
                  >
                  <button type="submit" class="primary-action node-input-submit">Reply</button>
                </div>
              </form>
            </div>
          </div>
        </div>
</template>

<style scoped>
/* ── Process grid ───────────────────────────────────── */
.process-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.process-card {
  padding: 1rem 1.1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background-mute);
  transition: border-color 200ms;
}

.process-card.running {
  border-color: color-mix(in srgb, var(--color-primary) 32%, var(--color-border));
  background: color-mix(in srgb, var(--color-primary-soft) 55%, var(--color-background-soft));
}

.process-card.completed {
  border-color: color-mix(in srgb, var(--color-success) 30%, var(--color-border));
}

.process-card.failed {
  border-color: color-mix(in srgb, var(--color-danger) 30%, var(--color-border));
}

.process-card-header {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.5rem;
}

.process-status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.process-status-dot.waiting   { background: var(--color-text-muted); opacity: 0.45; }
.process-status-dot.running   { background: var(--color-primary); animation: orb-pulse 1.5s ease-in-out infinite; }
.process-status-dot.completed { background: var(--color-success); }
.process-status-dot.failed    { background: var(--color-danger); }

.process-name {
  flex: 1;
  font-size: 0.87rem;
  font-weight: 680;
  color: var(--color-heading);
}

.process-badge {
  padding: 0.15rem 0.5rem;
  font-size: 0.68rem;
  font-weight: 720;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-radius: 999px;
}

.process-badge.waiting   { color: var(--color-text-muted);  background: var(--color-background-soft); }
.process-badge.running   { color: var(--color-primary);     background: var(--color-primary-soft); }
.process-badge.completed { color: var(--color-success);     background: var(--color-success-soft); }
.process-badge.failed    { color: var(--color-danger);      background: var(--color-danger-soft); }

.process-description {
  margin: 0;
  font-size: 0.79rem;
  line-height: 1.4;
  color: var(--color-text-muted);
}

.process-error {
  margin: 0.4rem 0 0;
  padding: 0.4rem 0.55rem;
  font-size: 0.77rem;
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border-left: 2px solid var(--color-danger);
  border-radius: var(--radius-sm);
}

/* ── Node ("script block") list ────────────────────────── */
.node-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.6rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--color-border);
}

.node-row {
  padding: 0.4rem 0.55rem;
  border-radius: var(--radius-sm);
  background: var(--color-background-soft);
}

.node-row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
}

.node-name {
  font-size: 0.76rem;
  font-weight: 620;
  color: var(--color-heading);
}

.node-iteration-badge {
  margin-left: 0.4rem;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.node-percentage {
  font-size: 0.72rem;
  font-weight: 620;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.progress-track {
  width: 100%;
  height: 5px;
  border-radius: 999px;
  background: var(--color-border);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.node-row.completed .progress-fill { background: var(--color-success); }
.node-row.failed .progress-fill    { background: var(--color-danger); }
.node-row.waiting .progress-fill,
.node-row.inactive .progress-fill  { background: var(--color-text-muted); }

.node-row.completed .node-percentage { color: var(--color-success); }
.node-row.failed .node-percentage    { color: var(--color-danger); }

.node-status-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.3rem;
}

.node-message {
  margin: 0;
  font-size: 0.73rem;
  line-height: 1.35;
  color: var(--color-text-muted);
}

.node-row.failed .node-message {
  color: var(--color-danger);
}

/* ── Wait countdown ─────────────────────────────────── */
.node-wait {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
}

.node-wait-clock {
  --wait-frac: 1;
  width: 11px;
  height: 11px;
  flex-shrink: 0;
  border-radius: 50%;
  background: conic-gradient(
    var(--color-primary) calc(var(--wait-frac) * 360deg),
    var(--color-border) 0
  );
  transition: background 0.2s linear;
}

.node-wait-time {
  font-size: 0.72rem;
  font-weight: 620;
  font-variant-numeric: tabular-nums;
  color: var(--color-primary);
  white-space: nowrap;
}

/* ── Operator input prompt ──────────────────────────── */
.node-input-row {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.5rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
}

.node-input-prompt {
  font-size: 0.75rem;
  font-weight: 620;
  color: var(--color-heading);
}

.node-input-controls {
  display: flex;
  gap: 0.4rem;
}

.node-input-field {
  flex: 1;
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-background);
  color: var(--color-text);
}

.node-input-field:focus {
  outline: none;
  border-color: var(--color-primary);
}

.node-input-submit {
  flex-shrink: 0;
  padding: 0.4rem 0.9rem;
  font-size: 0.78rem;
}

/* ── Animations ─────────────────────────────────────── */
@keyframes orb-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.35; }
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 840px) {
  .control-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .process-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-orb.running,
  .process-status-dot.running {
    animation: none;
  }
}

.process-card { min-width: 0; }
.process-name, .node-name, .node-message, .process-error { min-width: 0; overflow-wrap: anywhere; }
.node-input-field { min-width: 0; }
.primary-action { color: white; background: var(--color-primary); border: 0; border-radius: var(--radius-sm); cursor: pointer; }

</style>
