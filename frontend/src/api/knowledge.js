import { authHeaders, clearAuth } from './auth'

async function parseJson(resp) {
  const body = await resp.json().catch(() => ({}))
  if (resp.status === 401 || body.code === 401) {
    clearAuth()
    window.dispatchEvent(new CustomEvent('auth:logout'))
    throw new Error(body.message || '未登录')
  }
  if (!resp.ok || body.code !== 200) {
    throw new Error(body.message || body.detail || `请求失败 ${resp.status}`)
  }
  return body.data
}

export function listKnowledgeDocs(docType) {
  const url = new URL('/api/v1/knowledge/docs', window.location.origin)
  if (docType) url.searchParams.set('doc_type', docType)
  return fetch(url.pathname + url.search, { headers: authHeaders() }).then(parseJson)
}

export function getKnowledgeDoc(docId) {
  return fetch(`/api/v1/knowledge/docs/${docId}`, { headers: authHeaders() }).then(parseJson)
}

export function deleteKnowledgeDoc(docId) {
  return fetch(`/api/v1/knowledge/docs/${docId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  }).then(parseJson)
}

export function uploadKnowledgeDoc(file, docType) {
  const form = new FormData()
  form.append('file', file)
  if (docType) form.append('doc_type', docType)
  return fetch('/api/v1/knowledge/docs', {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  }).then(parseJson)
}

export function searchKnowledge(query, { topK = 5, docType, mode } = {}) {
  return fetch('/api/v1/knowledge/search', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      query,
      top_k: topK,
      doc_type: docType || null,
      mode: mode || null,
    }),
  }).then(parseJson)
}
