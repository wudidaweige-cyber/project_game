import { authHeaders, clearAuth } from './auth'

async function postJson(path, body) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  const payload = await resp.json().catch(() => ({}))
  if (resp.status === 401 || payload.code === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('auth:logout'))
    const err = new Error(payload.message || '未登录')
    err.payload = payload
    throw err
  }
  if (!resp.ok || payload.code !== 200) {
    const err = new Error(payload.message || payload.detail || `请求失败 ${resp.status}`)
    err.payload = payload
    throw err
  }
  return payload.data
}

async function getJson(path) {
  const resp = await fetch(path, { headers: authHeaders() })
  const payload = await resp.json().catch(() => ({}))
  if (resp.status === 401 || payload.code === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('auth:logout'))
    const err = new Error(payload.message || '未登录')
    err.payload = payload
    throw err
  }
  if (!resp.ok || payload.code !== 200) {
    const err = new Error(payload.message || payload.detail || `请求失败 ${resp.status}`)
    err.payload = payload
    throw err
  }
  return payload.data
}

/**
 * Consume POST SSE (event: ... / data: ...).
 * onEvent(eventName, data) for each event; resolves with final `done` payload.
 */
export async function postSse(path, body, onEvent) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: authHeaders({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }),
    body: JSON.stringify(body),
  })
  if (resp.status === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('auth:logout'))
    throw new Error('未登录')
  }
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `请求失败 ${resp.status}`)
  }
  if (!resp.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let donePayload = null

  const flushBlock = (block) => {
    const lines = block.split(/\r?\n/)
    let eventName = 'message'
    const dataLines = []
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }
    if (!dataLines.length) return
    let data
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch {
      data = { raw: dataLines.join('\n') }
    }
    if (typeof onEvent === 'function') onEvent(eventName, data)
    if (eventName === 'done') donePayload = data
    if (eventName === 'error') {
      const err = new Error(data.error || '流式问答失败')
      err.payload = { data }
      throw err
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (block.trim()) flushBlock(block)
    }
  }
  if (buffer.trim()) flushBlock(buffer)

  if (!donePayload) {
    throw new Error('流式响应未正常结束')
  }
  return donePayload
}

export function createSession(title = '') {
  return postJson('/api/v1/agent/sessions', { title })
}

export function fetchTask(taskId) {
  return getJson(`/api/v1/agent/tasks/${taskId}`)
}

export function fetchExecutions(taskId) {
  return getJson(`/api/v1/agent/tasks/${taskId}/executions`)
}

export function askNl2sql(question, maxRows = 100, onEvent) {
  return postSse(
    '/api/v1/agent/nl2sql/stream',
    { question, max_rows: maxRows },
    onEvent,
  )
}

export function askKnowledge(question, topK = 5, docType, onEvent) {
  const body = { question, top_k: topK }
  if (docType) body.doc_type = docType
  return postSse('/api/v1/agent/knowledge/stream', body, onEvent)
}

export function askSupervisor(question, { maxRows = 100, topK = 5, sessionId } = {}, onEvent) {
  if (!sessionId) {
    return postSse(
      '/api/v1/agent/ask/stream',
      { question, max_rows: maxRows, top_k: topK },
      onEvent,
    )
  }
  return postSse(
    `/api/v1/agent/sessions/${sessionId}/ask/stream`,
    { question, max_rows: maxRows, top_k: topK },
    onEvent,
  )
}

/** Non-stream helpers retained for scripts/tests. */
export function askNl2sqlJson(question, maxRows = 100) {
  return postJson('/api/v1/agent/nl2sql', { question, max_rows: maxRows })
}
