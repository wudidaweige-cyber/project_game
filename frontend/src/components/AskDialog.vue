<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import {
  askKnowledge,
  askNl2sql,
  askSupervisor,
  createSession,
  fetchExecutions,
} from '../api/agent'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const mode = ref('auto') // auto | data | knowledge
const input = ref('')
const asking = ref(false)
const messages = ref([])
const listEl = ref(null)
const sessionId = ref('')
const sessionError = ref('')

const modeMeta = computed(() => {
  if (mode.value === 'data') {
    return {
      eyebrow: 'NL2SQL',
      title: '智能问数',
      hint: '可以问运营数据，例如：「最近7天全站GMV是多少？」',
      placeholder: '输入数据问题…',
      typing: '正在生成 SQL 并查询…',
    }
  }
  if (mode.value === 'knowledge') {
    return {
      eyebrow: 'RAG',
      title: '知识问答',
      hint: '可以问运营规则，例如：「什么情况下可以全额退款？」',
      placeholder: '输入规则/SOP 问题…',
      typing: '正在检索知识库并作答…',
    }
  }
  return {
    eyebrow: 'Supervisor',
    title: '智能运营助手',
    hint: '自动路由问数、异常、策略建议或问规则。例如：「根据最近指标给出运营策略建议」',
    placeholder: '输入问题，自动判断走数据、异常、策略或规则…',
    typing: 'Supervisor 路由并汇总中…',
  }
})

function resetWelcome() {
  messages.value = [{ role: 'assistant', text: modeMeta.value.hint }]
}

resetWelcome()

async function ensureSession() {
  if (sessionId.value) return sessionId.value
  try {
    const data = await createSession('运营问答')
    sessionId.value = data.id
    sessionError.value = ''
    return sessionId.value
  } catch (e) {
    sessionError.value = e.message || String(e)
    throw e
  }
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
      if (data.phase === 'routed' && data.route) m.route = data.route
    } else if (event === 'phase') {
      m.phase = data.phase
    }
  }

  try {
    let data
    if (mode.value === 'data') {
      data = await askNl2sql(q, 100, onEvent)
    } else if (mode.value === 'knowledge') {
      data = await askKnowledge(q, 5, undefined, onEvent)
    } else {
      const sid = await ensureSession()
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

function switchMode(next) {
  if (mode.value === next) return
  mode.value = next
  resetWelcome()
}

watch(
  () => props.open,
  async (v) => {
    if (v) {
      scrollBottom()
      if (mode.value === 'auto' && !sessionId.value) {
        try {
          await ensureSession()
        } catch {
          /* shown via sessionError when sending */
        }
      }
    }
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="mask" @click.self="emit('close')">
      <aside class="dialog" role="dialog" :aria-label="modeMeta.title">
        <header class="dlg-head">
          <div>
            <p class="eyebrow">{{ modeMeta.eyebrow }}</p>
            <h2>{{ modeMeta.title }}</h2>
          </div>
          <button type="button" class="icon-btn" @click="emit('close')">关闭</button>
        </header>

        <div class="modes">
          <button type="button" :class="{ active: mode === 'auto' }" @click="switchMode('auto')">
            智能
          </button>
          <button type="button" :class="{ active: mode === 'data' }" @click="switchMode('data')">
            问数
          </button>
          <button
            type="button"
            :class="{ active: mode === 'knowledge' }"
            @click="switchMode('knowledge')"
          >
            问规则
          </button>
        </div>

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
            {{
              messages.at(-1)?.text
                ? '生成中…'
                : modeMeta.typing
            }}
          </p>
        </div>

        <footer class="composer">
          <textarea
            v-model="input"
            rows="2"
            :placeholder="modeMeta.placeholder"
            :disabled="asking"
            @keydown="onKeydown"
          />
          <button type="button" class="send" :disabled="asking || !input.trim()" @click="send()">
            发送
          </button>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 50;
}

.dialog {
  width: min(440px, 100%);
  height: 100%;
  background: #f7faf8;
  border-left: 1px solid #dbe4df;
  display: flex;
  flex-direction: column;
  box-shadow: -12px 0 40px rgba(15, 23, 42, 0.12);
}

.dlg-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 18px 12px;
  border-bottom: 1px solid #dbe4df;
  background: #fff;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

h2 {
  margin: 2px 0 0;
  font-size: 18px;
}

.icon-btn {
  border: 1px solid #dbe4df;
  background: #fff;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
}

.modes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #dbe4df;
}

.modes button {
  border: 1px solid #dbe4df;
  background: #f8fafc;
  border-radius: 999px;
  padding: 8px 10px;
  cursor: pointer;
  color: #64748b;
}

.modes button.active {
  background: #ccfbf1;
  border-color: #99f6e4;
  color: #0f766e;
  font-weight: 600;
}

.msgs {
  flex: 1;
  overflow: auto;
  padding: 16px;
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
  padding: 12px 16px 16px;
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
