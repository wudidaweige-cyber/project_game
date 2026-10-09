<script setup>
import { computed, nextTick, ref, watch } from 'vue'
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
})

const emit = defineEmits(['close'])

const WELCOME =
  '可问运营数据、规则 SOP、异常归因或策略建议，系统自动路由。例如：「最近7天全站GMV是多少？」「什么情况下可以全额退款？」'

let seq = 0

function blankThread(title) {
  seq += 1
  return {
    id: `t-${Date.now()}-${seq}`,
    title: title || `对话 ${seq}`,
    preview: '暂无消息',
    updatedAt: Date.now(),
    sessionId: '',
    messages: [{ role: 'assistant', text: WELCOME }],
    asking: false,
    input: '',
  }
}

const threads = ref([])
const activeId = ref('')
const listEl = ref(null)

const active = computed(() => threads.value.find((t) => t.id === activeId.value) || null)
const sortedThreads = computed(() =>
  [...threads.value].sort((a, b) => b.updatedAt - a.updatedAt),
)

function ensureInitial() {
  if (!threads.value.length) {
    const t = blankThread()
    threads.value.push(t)
    activeId.value = t.id
  } else if (!activeId.value) {
    activeId.value = sortedThreads.value[0]?.id || ''
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      ensureInitial()
      nextTick(scrollBottom)
    }
  },
)

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  if (d.toDateString() === now.toDateString()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function selectThread(id) {
  activeId.value = id
  nextTick(scrollBottom)
}

function createThread() {
  const t = blankThread()
  threads.value.unshift(t)
  activeId.value = t.id
  nextTick(scrollBottom)
}

function removeThread(id, e) {
  e?.stopPropagation?.()
  const idx = threads.value.findIndex((t) => t.id === id)
  if (idx < 0) return
  const wasActive = activeId.value === id
  threads.value.splice(idx, 1)
  if (!threads.value.length) {
    createThread()
    return
  }
  if (wasActive) {
    activeId.value = sortedThreads.value[0].id
  }
}

async function scrollBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function ensureSession(thread) {
  if (thread.sessionId) return thread.sessionId
  const data = await createSession(thread.title || '运营问答')
  thread.sessionId = data.id
  return thread.sessionId
}

async function loadExecutions(msg) {
  if (!msg.taskId || msg.loadingSteps) return
  msg.loadingSteps = true
  try {
    msg.executions = await fetchExecutions(msg.taskId)
  } catch (err) {
    msg.executions = []
    msg.stepsError = err.message || String(err)
  } finally {
    msg.loadingSteps = false
  }
}

async function send() {
  const thread = active.value
  if (!thread) return
  const q = (thread.input || '').trim()
  if (!q || thread.asking) return

  thread.input = ''
  const userCount = thread.messages.filter((m) => m.role === 'user').length
  if (userCount === 0) {
    thread.title = q.length > 18 ? `${q.slice(0, 18)}…` : q
  }
  thread.preview = q.length > 28 ? `${q.slice(0, 28)}…` : q
  thread.updatedAt = Date.now()

  thread.messages.push({ role: 'user', text: q })
  const idx =
    thread.messages.push({
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
  thread.asking = true
  await scrollBottom()

  const msg = () => thread.messages[idx]
  const onEvent = (event, data) => {
    const m = msg()
    if (data.task_id) m.taskId = data.task_id
    if (event === 'token' && data.text) {
      m.text += data.text
      if (activeId.value === thread.id) scrollBottom()
    } else if (event === 'meta') {
      if (data.sql) m.sql = data.sql
      if (data.row_count != null) m.rowCount = data.row_count
      if (data.citations) m.citations = data.citations
      if (data.route) m.route = data.route
      if (data.route_decision) m.routeDecision = data.route_decision
    }
  }

  try {
    const sid = await ensureSession(thread)
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
    if (data.task_id) m.taskId = data.task_id
    if (data.suggestions_only != null) m.suggestionsOnly = data.suggestions_only
    if (data.route?.includes('strategy_agent')) m.suggestionsOnly = true

    const previewText = (m.text || '').replace(/\s+/g, ' ').trim()
    thread.preview = previewText.length > 28 ? `${previewText.slice(0, 28)}…` : previewText || '已回复'
    thread.updatedAt = Date.now()
  } catch (e) {
    const payload = e.payload?.data
    const detail = payload?.error || e.message || String(e)
    const m = msg()
    m.streaming = false
    m.error = true
    m.text = m.text ? `${m.text}\n\n失败：${detail}` : `失败：${detail}`
    if (payload?.sql) m.sql = payload.sql
    if (payload?.task_id) m.taskId = payload.task_id
    thread.preview = '发送失败'
    thread.updatedAt = Date.now()
  } finally {
    thread.asking = false
    if (activeId.value === thread.id) await scrollBottom()
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <div class="workspace" role="dialog" aria-label="智能问答">
        <aside class="sidebar">
          <header class="side-head">
            <div>
              <p class="eyebrow">GameOps</p>
              <h2>消息</h2>
            </div>
            <button type="button" class="new-btn" title="新建对话" @click="createThread">＋</button>
          </header>

          <ul class="thread-list">
            <li
              v-for="t in sortedThreads"
              :key="t.id"
              :class="{ active: t.id === activeId, busy: t.asking }"
              @click="selectThread(t.id)"
            >
              <div class="avatar">助</div>
              <div class="meta">
                <div class="row1">
                  <strong>{{ t.title }}</strong>
                  <span class="time">{{ formatTime(t.updatedAt) }}</span>
                </div>
                <div class="row2">
                  <span class="preview">{{ t.asking ? '正在回复…' : t.preview }}</span>
                  <button
                    type="button"
                    class="del"
                    title="删除"
                    @click="removeThread(t.id, $event)"
                  >
                    ×
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </aside>

        <section class="chat">
          <header class="chat-head">
            <div>
              <h3>{{ active?.title || '智能问答' }}</h3>
              <p class="sub">问数 / 问规则 / 异常 / 策略 · 自动路由</p>
            </div>
            <button type="button" class="ghost" @click="emit('close')">关闭</button>
          </header>

          <div v-if="active" ref="listEl" class="msgs">
            <div
              v-for="(m, i) in active.messages"
              :key="i"
              class="msg"
              :class="[m.role, { err: m.error }]"
            >
              <div class="bubble-wrap">
                <p class="bubble">{{ m.text }}</p>
                <p v-if="m.suggestionsOnly" class="route suggest-hint">
                  仅输出建议，不会自动修改业务数据
                </p>
                <p v-if="m.route?.length" class="route">路由：{{ m.route.join(' → ') }}</p>
                <details
                  v-if="m.taskId"
                  class="detail"
                  @toggle="(e) => e.target.open && loadExecutions(m)"
                >
                  <summary>执行步骤</summary>
                  <p v-if="m.loadingSteps" class="steps-hint">加载中…</p>
                  <p v-else-if="m.stepsError" class="steps-hint">{{ m.stepsError }}</p>
                  <ul v-else-if="m.executions?.length" class="steps">
                    <li v-for="ex in m.executions" :key="ex.id">
                      <strong>{{ ex.step_no }}. {{ ex.agent_name }}</strong>
                      <span class="tag">{{ ex.status }}</span>
                      <p>{{ ex.output_summary }}</p>
                    </li>
                  </ul>
                </details>
                <details v-if="m.sql" class="detail">
                  <summary>SQL{{ m.rowCount != null ? ` · ${m.rowCount} 行` : '' }}</summary>
                  <pre>{{ m.sql }}</pre>
                </details>
                <details v-if="m.citations?.length" class="detail">
                  <summary>来源 · {{ m.citations.length }}</summary>
                  <ul class="cites">
                    <li v-for="c in m.citations" :key="c.chunk_id || c.index">
                      <strong>[{{ c.index }}] {{ c.title }}</strong>
                      <p>{{ c.snippet }}</p>
                    </li>
                  </ul>
                </details>
              </div>
            </div>
            <p v-if="active.asking" class="typing">
              {{ active.messages.at(-1)?.text ? '生成中…' : '正在思考…' }}
            </p>
          </div>
          <div v-else class="empty-chat">请选择或新建一个对话</div>

          <footer v-if="active" class="composer">
            <textarea
              v-model="active.input"
              rows="2"
              placeholder="输入消息…"
              :disabled="active.asking"
              @keydown="onKeydown"
            />
            <button
              type="button"
              class="send"
              :disabled="active.asking || !active.input.trim()"
              @click="send"
            >
              发送
            </button>
          </footer>
        </section>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  display: grid;
  place-items: center;
  z-index: 55;
  padding: 20px;
}

.workspace {
  width: min(960px, 100%);
  height: min(720px, calc(100vh - 40px));
  background: #ededed;
  border-radius: 14px;
  overflow: hidden;
  display: grid;
  grid-template-columns: 280px 1fr;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
}

.sidebar {
  background: #f7f7f7;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.side-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 14px 12px;
  background: #f0f0f0;
  border-bottom: 1px solid #e5e5e5;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.12em;
  color: #0f766e;
  font-weight: 700;
}

.side-head h2 {
  margin: 2px 0 0;
  font-size: 18px;
  color: #111;
}

.new-btn {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 50%;
  background: #07c160;
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}

.thread-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  flex: 1;
}

.thread-list li {
  display: flex;
  gap: 10px;
  padding: 12px 12px;
  cursor: pointer;
  border-bottom: 1px solid #ececec;
}

.thread-list li:hover {
  background: #f0f0f0;
}

.thread-list li.active {
  background: #dedede;
}

.thread-list li.busy .preview {
  color: #07c160;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 6px;
  background: #0f766e;
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  flex-shrink: 0;
}

.meta {
  min-width: 0;
  flex: 1;
}

.row1,
.row2 {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.row1 strong {
  font-size: 14px;
  color: #111;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
}

.preview {
  font-size: 12px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 4px;
}

.del {
  border: 0;
  background: transparent;
  color: #bbb;
  font-size: 16px;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}

.del:hover {
  color: #e11;
}

.chat {
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
  min-width: 0;
}

.chat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #f0f0f0;
  border-bottom: 1px solid #e0e0e0;
}

.chat-head h3 {
  margin: 0;
  font-size: 16px;
  color: #111;
}

.sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: #888;
}

.ghost {
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
}

.msgs {
  flex: 1;
  overflow: auto;
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.empty-chat {
  flex: 1;
  display: grid;
  place-items: center;
  color: #999;
}

.msg {
  display: flex;
  max-width: 78%;
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
  border-radius: 6px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
}

.user .bubble {
  background: #95ec69;
  color: #111;
}

.assistant .bubble {
  background: #fff;
  color: #111;
  border: 1px solid #e8e8e8;
}

.msg.err .bubble {
  background: #fff1f0;
  border-color: #ffccc7;
  color: #cf1322;
}

.route {
  margin: 6px 2px 0;
  font-size: 11px;
  color: #888;
}

.suggest-hint {
  color: #b45309;
}

.detail {
  margin-top: 6px;
  font-size: 12px;
  color: #666;
}

.detail pre {
  margin: 6px 0 0;
  padding: 8px;
  background: #1f2937;
  color: #e5e7eb;
  border-radius: 6px;
  white-space: pre-wrap;
  font-size: 11px;
}

.steps {
  margin: 6px 0 0;
  padding-left: 16px;
}

.steps p {
  margin: 2px 0 8px;
  color: #888;
}

.steps-hint {
  margin: 6px 0 0;
  color: #aaa;
}

.tag {
  margin-left: 6px;
  color: #0f766e;
  font-size: 11px;
}

.cites {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
}

.cites li {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 6px;
}

.cites p {
  margin: 4px 0 0;
  color: #666;
}

.typing {
  margin: 0;
  color: #888;
  font-size: 13px;
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 12px 14px 14px;
  background: #f7f7f7;
  border-top: 1px solid #e0e0e0;
}

textarea {
  resize: none;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 10px 12px;
  font: inherit;
  outline: none;
  background: #fff;
}

textarea:focus {
  border-color: #07c160;
}

.send {
  align-self: end;
  border: 0;
  background: #07c160;
  color: #fff;
  border-radius: 8px;
  padding: 10px 18px;
  font-weight: 600;
  cursor: pointer;
}

.send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .workspace {
    grid-template-columns: 1fr;
    height: calc(100vh - 24px);
  }

  .sidebar {
    max-height: 38%;
  }
}
</style>
