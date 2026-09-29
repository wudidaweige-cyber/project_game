<script setup>
import { onMounted, ref } from 'vue'
import DashboardView from './views/DashboardView.vue'
import LoginView from './views/LoginView.vue'
import { clearAuth, fetchMe, getToken } from './api/auth'

const ready = ref(false)
const authed = ref(false)

async function checkAuth() {
  if (!getToken()) {
    authed.value = false
    ready.value = true
    return
  }
  try {
    await fetchMe()
    authed.value = true
  } catch {
    clearAuth()
    authed.value = false
  } finally {
    ready.value = true
  }
}

function onLoginSuccess() {
  authed.value = true
}

function onLogout() {
  authed.value = false
}

onMounted(checkAuth)
</script>

<template>
  <div v-if="!ready" class="boot">加载中…</div>
  <LoginView v-else-if="!authed" @success="onLoginSuccess" />
  <DashboardView v-else @logout="onLogout" />
</template>

<style scoped>
.boot {
  min-height: 100vh;
  display: grid;
  place-items: center;
  color: #64748b;
}
</style>
