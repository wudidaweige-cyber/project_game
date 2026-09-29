<script setup>
import { ref } from 'vue'
import { login } from '../api/auth'

const emit = defineEmits(['success'])

const username = ref('operator')
const password = ref('Operator@123')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value.trim(), password.value)
    emit('success')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="panel">
      <p class="eyebrow">GAME OPS</p>
      <h1>账号租赁智能运营分析</h1>
      <p class="sub">登录后使用运营看板与智能问答</p>

      <form class="form" @submit.prevent="onSubmit">
        <label>
          用户名
          <input v-model="username" autocomplete="username" required />
        </label>
        <label>
          密码
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </label>
        <p v-if="error" class="err">{{ error }}</p>
        <button type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>

      <p class="hint">
        演示账号：operator / Operator@123（运营）· admin / Admin@123（管理员）
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(ellipse 80% 60% at 20% 10%, rgba(15, 118, 110, 0.18), transparent),
    radial-gradient(ellipse 70% 50% at 90% 80%, rgba(15, 23, 42, 0.08), transparent),
    linear-gradient(160deg, #f0f7f4 0%, #e8eef2 45%, #f7faf8 100%);
}

.panel {
  width: min(420px, 100%);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #dbe4df;
  border-radius: 16px;
  padding: 28px 28px 22px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
}

.eyebrow {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.16em;
  color: #0f766e;
  font-weight: 700;
}

h1 {
  margin: 8px 0 6px;
  font-size: 22px;
  color: #0f172a;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.sub {
  margin: 0 0 20px;
  color: #64748b;
  font-size: 14px;
}

.form {
  display: grid;
  gap: 12px;
}

label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: #334155;
}

input {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
}

button {
  margin-top: 4px;
  border: 0;
  border-radius: 10px;
  padding: 11px 14px;
  background: #0f766e;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.err {
  margin: 0;
  color: #b42318;
  font-size: 13px;
}

.hint {
  margin: 16px 0 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
}
</style>
