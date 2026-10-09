<script setup>
import { computed, ref, watch } from 'vue'
import {
  deleteKnowledgeDoc,
  getKnowledgeDoc,
  listKnowledgeDocs,
  uploadKnowledgeDoc,
} from '../api/knowledge'

const props = defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close'])

const DOC_TYPES = [
  { value: '', label: '全部类型' },
  { value: 'sop', label: 'SOP' },
  { value: 'refund', label: '退款' },
  { value: 'account', label: '账号' },
  { value: 'pricing', label: '定价' },
  { value: 'risk', label: '风控' },
  { value: 'other', label: '其他' },
]

const filterType = ref('')
const uploadType = ref('sop')
const items = ref([])
const loading = ref(false)
const uploading = ref(false)
const error = ref('')
const message = ref('')
const fileInput = ref(null)
const selected = ref(null)
const detailChunks = ref([])
const detailLoading = ref(false)

const hasItems = computed(() => items.value.length > 0)

async function loadList() {
  loading.value = true
  error.value = ''
  try {
    const data = await listKnowledgeDocs(filterType.value || undefined)
    items.value = data.items || []
  } catch (e) {
    error.value = e.message || String(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

async function onUpload() {
  const input = fileInput.value
  const file = input?.files?.[0]
  if (!file) {
    error.value = '请先选择 .md 文件'
    return
  }
  if (!file.name.toLowerCase().endsWith('.md')) {
    error.value = '仅支持 Markdown（.md）'
    return
  }
  uploading.value = true
  error.value = ''
  message.value = ''
  try {
    const data = await uploadKnowledgeDoc(file, uploadType.value || undefined)
    message.value = `已入库「${data.document?.title || file.name}」，切片 ${data.chunk_count || 0} 条`
    if (input) input.value = ''
    await loadList()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    uploading.value = false
  }
}

async function onSelect(item) {
  selected.value = item
  detailChunks.value = []
  detailLoading.value = true
  error.value = ''
  try {
    const data = await getKnowledgeDoc(item.id)
    selected.value = data.document
    detailChunks.value = data.chunks || []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    detailLoading.value = false
  }
}

async function onDelete(item) {
  if (!confirm(`确认删除「${item.title}」？将同步移除向量切片。`)) return
  error.value = ''
  message.value = ''
  try {
    await deleteKnowledgeDoc(item.id)
    message.value = `已删除「${item.title}」`
    if (selected.value?.id === item.id) {
      selected.value = null
      detailChunks.value = []
    }
    await loadList()
  } catch (e) {
    error.value = e.message || String(e)
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      message.value = ''
      error.value = ''
      selected.value = null
      detailChunks.value = []
      loadList()
    }
  },
)

watch(filterType, () => {
  if (props.open) loadList()
})
</script>

<template>
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <div class="panel" role="dialog" aria-label="知识库管理">
      <header class="head">
        <div>
          <p class="eyebrow">ADMIN · RAG</p>
          <h2>知识库管理</h2>
          <p class="hint">上传 Markdown，切分并向量化后即可被「问规则」检索。</p>
        </div>
        <button type="button" class="ghost" @click="emit('close')">关闭</button>
      </header>

      <section class="upload">
        <label class="field">
          <span>文档类型</span>
          <select v-model="uploadType">
            <option v-for="t in DOC_TYPES.filter((x) => x.value)" :key="t.value" :value="t.value">
              {{ t.label }}
            </option>
          </select>
        </label>
        <label class="field file">
          <span>选择 .md 文件</span>
          <input ref="fileInput" type="file" accept=".md,text/markdown" />
        </label>
        <button type="button" class="primary" :disabled="uploading" @click="onUpload">
          {{ uploading ? '入库中…' : '上传并入库' }}
        </button>
      </section>

      <p v-if="message" class="ok-msg">{{ message }}</p>
      <p v-if="error" class="err-msg">{{ error }}</p>

      <div class="toolbar">
        <label>
          筛选
          <select v-model="filterType">
            <option v-for="t in DOC_TYPES" :key="t.label" :value="t.value">{{ t.label }}</option>
          </select>
        </label>
        <button type="button" class="ghost" :disabled="loading" @click="loadList">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <div class="body">
        <ul class="list">
          <li v-if="!loading && !hasItems" class="empty">暂无文档，请上传 .md</li>
          <li
            v-for="item in items"
            :key="item.id"
            :class="{ active: selected?.id === item.id }"
            @click="onSelect(item)"
          >
            <div class="row">
              <strong>{{ item.title }}</strong>
              <span class="tag">{{ item.doc_type }}</span>
            </div>
            <div class="meta">
              <span>{{ item.chunk_count ?? 0 }} 切片</span>
              <span>{{ item.embed_status }}</span>
            </div>
            <button type="button" class="danger" @click.stop="onDelete(item)">删除</button>
          </li>
        </ul>

        <aside class="detail">
          <p v-if="!selected" class="empty">选择左侧文档查看切片</p>
          <template v-else>
            <h3>{{ selected.title }}</h3>
            <p class="meta">
              {{ selected.doc_type }} · {{ selected.embed_status }} ·
              {{ detailChunks.length }} 切片
            </p>
            <p v-if="detailLoading" class="empty">加载中…</p>
            <ol v-else class="chunks">
              <li v-for="c in detailChunks" :key="c.id">
                <span class="idx">#{{ c.chunk_index }}</span>
                <pre>{{ c.content }}</pre>
              </li>
            </ol>
          </template>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: grid;
  place-items: center;
  z-index: 60;
  padding: 24px;
}

.panel {
  width: min(960px, 100%);
  max-height: min(88vh, 820px);
  overflow: auto;
  background: #fff;
  border-radius: 16px;
  padding: 22px 24px 28px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.2);
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.14em;
  color: #0f766e;
  font-weight: 700;
}

h2 {
  margin: 4px 0;
  font-size: 22px;
  color: #0f172a;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.upload {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  padding: 14px;
  background: #f0fdfa;
  border: 1px solid #ccfbf1;
  border-radius: 12px;
  margin-bottom: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #475569;
}

.field.file {
  min-width: 220px;
  flex: 1;
}

select,
input[type='file'] {
  font: inherit;
}

.primary,
.ghost,
.danger {
  border: 0;
  border-radius: 999px;
  padding: 8px 14px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}

.primary {
  background: #0f766e;
  color: #fff;
}

.primary:disabled {
  opacity: 0.6;
  cursor: wait;
}

.ghost {
  background: #e2e8f0;
  color: #334155;
}

.danger {
  background: #fee2e2;
  color: #b91c1c;
  margin-top: 8px;
}

.ok-msg {
  color: #0f766e;
  font-size: 13px;
}

.err-msg {
  color: #b91c1c;
  font-size: 13px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 8px 0 12px;
  font-size: 13px;
  color: #475569;
}

.body {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 14px;
  min-height: 280px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: auto;
  max-height: 420px;
}

.list li {
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
  cursor: pointer;
}

.list li:last-child {
  border-bottom: 0;
}

.list li.active,
.list li:hover {
  background: #f8fafc;
}

.row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.tag {
  font-size: 11px;
  background: #ccfbf1;
  color: #0f766e;
  padding: 2px 8px;
  border-radius: 999px;
}

.meta {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
  display: flex;
  gap: 10px;
}

.detail {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  overflow: auto;
  max-height: 420px;
}

.detail h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

.empty {
  color: #94a3b8;
  font-size: 13px;
  padding: 12px;
}

.chunks {
  margin: 12px 0 0;
  padding: 0 0 0 18px;
}

.chunks li {
  margin-bottom: 12px;
}

.chunks .idx {
  font-size: 11px;
  color: #0f766e;
  font-weight: 700;
}

.chunks pre {
  margin: 4px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
  background: #f8fafc;
  padding: 8px 10px;
  border-radius: 8px;
}

@media (max-width: 720px) {
  .body {
    grid-template-columns: 1fr;
  }
}
</style>
