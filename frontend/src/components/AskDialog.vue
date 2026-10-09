<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  askSupervisor,
  createSession,
  enqueueSupervisorAsk,
  fetchExecutions,
  fetchQueueStatus,
  waitForTask,
} from '../api/agent'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '智能问答' },
  offsetIndex: { type: Number, default: 0 },
  zIndex: { type: Number, default: 60 },
})

const emit = defineEmits(['close', 'activate', 'update:title'])

const WELCOME =
  '可问运营数据、规则 SOP、异常归因或策略建议，系统自动路由。例如：「最近7天全站GMV是多少？」「什么情况下可以全额退款？」'

const input = ref('')
const asking = ref(false)
const messages = ref([{ role: 'assistant', text: WELCOME }])
const listEl = ref(null)
const sessionId = ref('')
const panelEl = ref(null)

const pos = ref({ x: 0, y: 0 })
const dragging = ref(false)
let dragOrigin = { mx: 0, my: 0, x: 0, y: 0 }

const panelStyle = computed(() => ({
  zIndex: props.zIndex,
  left: `${pos.value.x}px`,
  top: `${pos.value.y}px`,
}))

function placePanel() {
  const margin = 24
  const cascade = (props.offsetIndex % 6) * 28
  const width = Math.min(420, window.innerWidth - margin * 2)
  const height = Math.min(560, window.innerHeight - margin * 2)
  pos.value = {
    x: Math.max(margin, window.innerWidth - width - margin - cascade),
    y: Math.max(margin, 72 + cascade),
  }
  panelEl.value?.style.setProperty('--panel-h', `${height}px`)
}

onMounted(() => {
  if (props.open) placePanel()
})

watch(
  () => props.open,
  async (v) => {
    if (v) {
      placePanel()
      scrollBottom()
      if (!sessionId.value) {
        try {
          await ensureSession()
        } catch {
          /* shown on send */
        }
      }
    }
  },
)

async function ensureSession() {
  if (sessionId.value) return sessionId.value
  const data = await createSession(props.title || '运营问答')
  sessionId.value = data.id
  return sessionId.value
}

async function scrollBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function loadExecutions(msg) {
  if (!msg.taskId || msg.loadingSteps) return
  msg.loadingSteps = true
  try {
    msg.executions = await fetchExecutions(msg.taskId)
  } catch (e) {
    msg.executions = []
    msg.stepsError = e.message || String(e)
  } finally {
    msg.loadingSteps = false
  }
}

async function send(text) {
  const q = (text ?? input.value).trim()
  if (!q || asking.value) return
  input.value = ''

  const userCount = messages.value.filter((m) => m.role === 'user').length
  if (userCount === 0) {
    const short = q.length > 16 ? `${q.slice(0, 16)}…` : q
    emit('update:title', short)
  }

  messages.value.push({ role: 'user', text: q })
  const idx =
    messages.value.push({
      role: 'assistant',
      text: '',
      streaming: true,
      sql: '',
      rowCount: null,
      citations: [],
      route: [],
      taskId: '',
      executions: null,
    }) - 1
  asking.value = true
  await scrollBottom()

  const msg = () => messages.value[idx]
  const onEvent = (event, data) => {
    const m = msg()
    if (data.task_id) m.taskId = data.task_id
    if (event === 'token' && data.text) {
      m.text += data.text
      scrollBottom()
    } else if (event === 'meta') {
      if (data.sql) m.sql = data.sql
      if (data.row_count != null) m.rowCount = data.row_count
      if (data.citations) m.citations = data.citations
      if (data.route) m.route = data.route
      if (data.route_decision) m.routeDecision = data.route_decision
    } else if (event === 'phase') {
      m.phase = data.phase
    }
  }

  try {
    const sid = await ensureSession()
    let useQueue = false
    try {
      const qs = await fetchQueueStatus()
      useQueue = Boolean(qs?.enabled)
    } catch {
      useQueue = false
    }

    let data
    if (useQueue) {
      const queued = await enqueueSupervisorAsk(sid, q)
      if (queued.task_id) msg().taskId = queued.task_id
      const task = await waitForTask(queued.task_id)
      data = {
        answer: task.result_summary || '',
        task_id: task.id,
        error: task.error_message || '',
        route: [],
      }
      if (task.status === 'failed') {
        const err = new Error(task.error_message || '任务失败')
        err.payload = { data }
        throw err
      }
    } else {
      data = await askSupervisor(q, { sessionId: sid }, onEvent)
    }

    const m = msg()
    m.streaming = false
    m.text = data.answer || m.text || '未返回结论。'
    if (data.sql) m.sql = data.sql
    if (data.row_count != null) m.rowCount = data.row_count
    if (data.citations) m.citations = data.citations
    if (data.route) m.route = data.route
    if (data.route_decision) m.routeDecision = data.route_decision
    if (data.no_hit != null) m.noHit = data.no_hit
    if (data.task_id) m.taskId = data.task_id
    if (data.suggestions_only != null) m.suggestionsOnly = data.suggestions_only
    if (data.route?.includes('strategy_agent')) m.suggestionsOnly = true
  } catch (e) {
    const payload = e.payload?.data
    const detail = payload?.error || e.message || String(e)
    const m = msg()
    m.streaming = false
    m.error = true
    m.text = m.text ? `${m.text}\n\n失败：${detail}` : `失败：${detail}`
    if (payload?.sql) m.sql = payload.sql
    if (payload?.task_id) m.taskId = payload.task_id
  } finally {
    asking.value = false
    await scrollBottom()
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function onPointerDown(e) {
  if (e.button !== 0) return
  emit('activate')
  dragging.value = true
  dragOrigin = { mx: e.clientX, my: e.clientY, x: pos.value.x, y: pos.value.y }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

function onPointerMove(e) {
  if (!dragging.value) return
  pos.value = {
    x: Math.max(8, dragOrigin.x + e.clientX - dragOrigin.mx),
    y: Math.max(8, dragOrigin.y + e.clientY - dragOrigin.my),
  }
}

function onPointerUp() {
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
}
</script>

<template>
  <Teleport to="body">
    <aside
      v-if="open"
      ref="panelEl"
      class="panel"
      :class="{ dragging }"
      :style="panelStyle"
      role="dialog"
      :aria-label="title"
      @mousedown="emit('activate')"
    >
      <header class="dlg-head" @pointerdown="onPointerDown">
        <div class="titles">
          <p class="eyebrow">Supervisor · 统一问答</p>
          <h2>{{ title }}</h2>
        </div>
        <div class="head-actions">
          <button type="button" class="icon-btn" title="关闭" @click.stop="emit('close')">关闭</button>
        </div>
      </header>

      <p class="hint-bar">问数 / 问规则 / 异常 / 策略 · 同一窗口自动路由</p>

      <div ref="listEl" class="msgs">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="msg"
          :class="[m.role, { err: m.error }]"
        >
          <p class="bubble">{{ m.text }}</p>
          <p v-if="m.suggestionsOnly" class="route suggest-hint">仅输出建议，不会自动修改业务数据</p>
          <p v-if="m.route?.length" class="route">路由：{{ m.route.join(' → ') }}</p>
          <p v-if="m.taskId" class="route">任务：{{ m.taskId }}</p>
          <details
            v-if="m.taskId"
            class="meta"
            @toggle="(e) => e.target.open && loadExecutions(m)"
          >
            <summary>查看执行步骤</summary>
            <p v-if="m.loadingSteps" class="steps-hint">加载中…</p>
            <p v-else-if="m.stepsError" class="steps-hint">{{ m.stepsError }}</p>
            <ul v-else-if="m.executions?.length" class="steps">
              <li v-for="ex in m.executions" :key="ex.id">
                <strong>{{ ex.step_no }}. {{ ex.agent_name }}</strong>
                <span class="tag">{{ ex.status }}</span>
                <span v-if="ex.tool_name" class="tag">{{ ex.tool_name }}</span>
                <p>{{ ex.output_summary }}</p>
              </li>
            </ul>
            <p v-else class="steps-hint">暂无步骤</p>
          </details>
          <details v-if="m.sql" class="meta">
            <summary>查看 SQL{{ m.rowCount != null ? ` · ${m.rowCount} 行` : '' }}</summary>
            <pre>{{ m.sql }}</pre>
          </details>
          <details v-if="m.citations?.length" class="meta">
            <summary>查看来源 · {{ m.citations.length }} 条</summary>
            <ul class="cites">
              <li v-for="c in m.citations" :key="c.chunk_id || c.index">
                <strong>[{{ c.index }}] {{ c.title }}</strong>
                <span class="tag">{{ c.doc_type }}</span>
                <p>{{ c.snippet }}</p>
              </li>
            </ul>
          </details>
        </div>
        <p v-if="asking" class="typing">
          {{ messages.at(-1)?.text ? '生成中…' : '任务执行中…' }}
        </p>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="2"
          placeholder="输入问题：数据、规则、异常或策略…"
          :disabled="asking"
          @keydown="onKeydown"
          @focus="emit('activate')"
        />
        <button type="button" class="send" :disabled="asking || !input.trim()" @click="send()">
          发送
        </button>
      </footer>
    </aside>
  </Teleport>
</template>

<style scoped>
.panel {
  --panel-h: 560px;
  position: fixed;
  width: min(420px, calc(100vw - 32px));
  height: var(--panel-h);
  max-height: calc(100vh - 32px);
  background: #f7faf8;
  border: 1px solid #dbe4df;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
  overflow: hidden;
}

.panel.dragging {
  user-select: none;
  cursor: grabbing;
}

.dlg-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 14px 10px;
  border-bottom: 1px solid #dbe4df;
  background: #fff;
  cursor: grab;
  touch-action: none;
}

.titles {
  min-width: 0;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

h2 {
  margin: 2px 0 0;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

.icon-btn {
  border: 1px solid #dbe4df;
  background: #fff;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
}

.hint-bar {
  margin: 0;
  padding: 8px 14px;
  font-size: 12px;
  color: #64748b;
  background: #ecfdf5;
  border-bottom: 1px solid #ccfbf1;
}

.msgs {
  flex: 1;
  overflow: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 92%;
}

.msg.user {
  align-self: flex-end;
}

.msg.assistant {
  align-self: flex-start;
}

.bubble {
  margin: 0;
  padding: 10px 12px;
  border-radius: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.user .bubble {
  background: #0f766e;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.assistant .bubble {
  background: #fff;
  border: 1px solid #dbe4df;
  color: #0f172a;
  border-bottom-left-radius: 4px;
}

.route {
  margin: 4px 2px 0;
  font-size: 11px;
  color: #64748b;
}

.suggest-hint {
  color: #b45309;
}

.msg.err .bubble {
  border-color: #fecdca;
  background: #fef3f2;
  color: #b42318;
}

.meta {
  font-size: 12px;
  color: #64748b;
}

.meta pre {
  margin: 6px 0 0;
  padding: 8px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 11px;
}

.cites {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}

.cites li {
  background: #fff;
  border: 1px solid #dbe4df;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 6px;
}

.cites p {
  margin: 4px 0 0;
  color: #475569;
}

.steps {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  color: #334155;
}

.steps p {
  margin: 2px 0 8px;
  color: #64748b;
}

.steps-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}

.tag {
  margin-left: 6px;
  font-size: 11px;
  color: #0f766e;
}

.typing {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 12px 14px 14px;
  border-top: 1px solid #dbe4df;
  background: #fff;
}

textarea {
  resize: none;
  border: 1px solid #dbe4df;
  border-radius: 12px;
  padding: 10px 12px;
  font: inherit;
  outline: none;
}

textarea:focus {
  border-color: #0f766e;
}

.send {
  align-self: end;
  border: 0;
  background: #0f766e;
  color: #fff;
  border-radius: 12px;
  padding: 10px 16px;
  cursor: pointer;
  font-weight: 600;
}

.send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
