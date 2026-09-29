<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import BaseChart from '../components/BaseChart.vue'
import AskDialog from '../components/AskDialog.vue'
import {
  fetchGameDetail,
  fetchGameRank,
  fetchHealth,
  fetchOverview,
  fetchTrends,
} from '../api/dashboard'
import { getUser, logout } from '../api/auth'
import { formatMoney, formatNumber, formatPercent, rangeDays } from '../utils/format'

const emit = defineEmits(['logout'])

const rangeKey = ref('30')
const trendMetric = ref('gmv')
const rankMetric = ref('gmv')
const loading = ref(false)
const error = ref('')
const health = ref(null)
const overview = ref(null)
const trendPoints = ref([])
const rankItems = ref([])
const selectedGame = ref(null)
const detail = ref(null)
const askOpen = ref(false)
const currentUser = ref(getUser())

const ranges = [
  { key: '7', label: '近 7 天' },
  { key: '14', label: '近 14 天' },
  { key: '30', label: '近 30 天' },
]

const metricOptions = [
  { value: 'gmv', label: 'GMV' },
  { value: 'order_count', label: '订单量' },
  { value: 'rent_rate', label: '出租率' },
  { value: 'refund_rate', label: '退款率' },
]

const dateRange = computed(() => rangeDays(Number(rangeKey.value)))

const cards = computed(() => {
  const o = overview.value
  if (!o) return []
  return [
    { key: 'gmv', label: 'GMV', value: formatMoney(o.gmv), hint: '成交总额' },
    { key: 'orders', label: '订单量', value: formatNumber(o.order_count), hint: '区间合计' },
    { key: 'rent', label: '出租率', value: formatPercent(o.rent_rate), hint: '区间均值' },
    { key: 'refund', label: '退款率', value: formatPercent(o.refund_rate), hint: '区间均值' },
    {
      key: 'stock',
      label: '可出租账号',
      value: formatNumber(o.available_account_count),
      hint: '均值库存',
    },
    {
      key: 'games',
      label: '活跃游戏',
      value: formatNumber(o.active_game_count),
      hint: '有成交游戏数',
    },
  ]
})

const trendOption = computed(() => {
  const isRate = trendMetric.value.includes('rate')
  return {
    color: ['#0f766e'],
    grid: { left: 48, right: 24, top: 32, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (isRate ? formatPercent(v) : formatNumber(v, isRate ? 4 : 2)),
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trendPoints.value.map((p) => p.date),
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b' },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#64748b',
        formatter: (v) => (isRate ? `${(v * 100).toFixed(0)}%` : formatNumber(v)),
      },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(15,118,110,0.28)' },
              { offset: 1, color: 'rgba(15,118,110,0.02)' },
            ],
          },
        },
        data: trendPoints.value.map((p) => p.value),
      },
    ],
  }
})

const rankOption = computed(() => {
  const items = [...rankItems.value].reverse()
  const isRate = rankMetric.value.includes('rate')
  return {
    color: ['#0f766e'],
    grid: { left: 96, right: 36, top: 16, bottom: 24 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v) => (isRate ? formatPercent(v) : formatNumber(v, 2)),
    },
    xAxis: {
      type: 'value',
      axisLabel: {
        color: '#64748b',
        formatter: (v) => (isRate ? `${(v * 100).toFixed(0)}%` : formatNumber(v)),
      },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.game_name),
      axisLabel: { color: '#334155' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        data: items.map((i) => i.value),
        itemStyle: { borderRadius: [0, 6, 6, 0] },
      },
    ],
  }
})

async function loadAll() {
  loading.value = true
  error.value = ''
  const { startDate, endDate } = dateRange.value
  try {
    const [h, o, t, r] = await Promise.all([
      fetchHealth(),
      fetchOverview(startDate, endDate),
      fetchTrends(trendMetric.value, startDate, endDate),
      fetchGameRank(rankMetric.value, startDate, endDate, 8),
    ])
    health.value = h
    overview.value = o
    trendPoints.value = t.points || []
    rankItems.value = r.items || []
    if (selectedGame.value) {
      detail.value = await fetchGameDetail(selectedGame.value, startDate, endDate)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function onSelectGame(item) {
  selectedGame.value = item.game_id
  const { startDate, endDate } = dateRange.value
  try {
    detail.value = await fetchGameDetail(item.game_id, startDate, endDate)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onLogout() {
  await logout()
  emit('logout')
}

function onAuthLogout() {
  emit('logout')
}

onMounted(() => {
  window.addEventListener('auth:logout', onAuthLogout)
})
onUnmounted(() => {
  window.removeEventListener('auth:logout', onAuthLogout)
})

watch([rangeKey, trendMetric, rankMetric], loadAll, { immediate: true })
</script>

<template>
  <div class="cockpit">
    <header class="top">
      <div>
        <p class="brand">GameOps</p>
        <h1>运营驾驶舱</h1>
        <p class="sub">账号租赁 · 核心指标 / 趋势 / 游戏排行</p>
      </div>
      <div class="top-right">
        <button type="button" class="ask-btn" @click="askOpen = true">智能问数</button>
        <div class="ranges">
          <button
            v-for="r in ranges"
            :key="r.key"
            type="button"
            :class="{ active: rangeKey === r.key }"
            @click="rangeKey = r.key"
          >
            {{ r.label }}
          </button>
        </div>
        <div class="user-box">
          <span>{{ currentUser?.display_name || currentUser?.username || '用户' }}</span>
          <span class="role">{{ currentUser?.role || '' }}</span>
          <button type="button" class="logout-btn" @click="onLogout">退出</button>
        </div>
        <p class="health" :class="health?.database?.ok ? 'ok' : 'bad'">
          {{
            health?.database?.ok
              ? `服务正常 · ${dateRange.startDate} ~ ${dateRange.endDate}`
              : error || '后端未连接（请启动 :8888）'
          }}
        </p>
      </div>
    </header>

    <p v-if="error" class="banner-err">{{ error }}</p>
    <p v-else-if="loading" class="banner-load">数据加载中…</p>

    <section class="metrics">
      <article v-for="c in cards" :key="c.key" class="metric">
        <p class="m-label">{{ c.label }}</p>
        <p class="m-value">{{ c.value }}</p>
        <p class="m-hint">{{ c.hint }}</p>
      </article>
    </section>

    <section class="grid-2">
      <div class="panel">
        <div class="panel-head">
          <h2>指标趋势</h2>
          <select v-model="trendMetric">
            <option v-for="m in metricOptions" :key="m.value" :value="m.value">
              {{ m.label }}
            </option>
          </select>
        </div>
        <BaseChart :option="trendOption" height="340px" />
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>游戏排行</h2>
          <select v-model="rankMetric">
            <option v-for="m in metricOptions" :key="m.value" :value="m.value">
              {{ m.label }}
            </option>
          </select>
        </div>
        <BaseChart :option="rankOption" height="340px" />
        <ul class="rank-list">
          <li
            v-for="(item, idx) in rankItems"
            :key="item.game_id"
            :class="{ selected: selectedGame === item.game_id }"
            @click="onSelectGame(item)"
          >
            <span class="idx">{{ idx + 1 }}</span>
            <span class="name">{{ item.game_name }}</span>
            <span class="val">
              {{
                rankMetric.includes('rate')
                  ? formatPercent(item.value)
                  : rankMetric === 'gmv'
                    ? formatMoney(item.value)
                    : formatNumber(item.value)
              }}
            </span>
          </li>
        </ul>
      </div>
    </section>

    <section v-if="detail" class="panel detail">
      <div class="panel-head">
        <h2>游戏详情 · {{ detail.game.name }}</h2>
        <button type="button" class="ghost" @click="detail = null; selectedGame = null">关闭</button>
      </div>
      <div class="detail-meta">
        <span>分类 {{ detail.game.category }}</span>
        <span>平台 {{ detail.game.platform }}</span>
        <span>GMV {{ formatMoney(detail.overview.gmv) }}</span>
        <span>订单 {{ formatNumber(detail.overview.order_count) }}</span>
        <span>出租率 {{ formatPercent(detail.overview.rent_rate) }}</span>
        <span>退款率 {{ formatPercent(detail.overview.refund_rate) }}</span>
      </div>
      <BaseChart
        :option="{
          color: ['#b45309'],
          grid: { left: 48, right: 24, top: 24, bottom: 40 },
          tooltip: { trigger: 'axis' },
          xAxis: {
            type: 'category',
            data: detail.gmv_trends.map((p) => p.date),
            axisLabel: { color: '#64748b' },
          },
          yAxis: {
            type: 'value',
            axisLabel: { color: '#64748b', formatter: (v) => formatNumber(v) },
            splitLine: { lineStyle: { color: '#e2e8f0' } },
          },
          series: [
            {
              type: 'line',
              smooth: true,
              showSymbol: false,
              data: detail.gmv_trends.map((p) => p.value),
              areaStyle: { color: 'rgba(180,83,9,0.12)' },
            },
          ],
        }"
        height="280px"
      />
    </section>

    <AskDialog :open="askOpen" @close="askOpen = false" />

    <button type="button" class="fab" title="智能问数" @click="askOpen = true">问</button>
  </div>
</template>

<style scoped>
.cockpit {
  --bg: #eef3f1;
  --panel: #ffffff;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #dbe4df;
  --accent: #0f766e;
  --accent-soft: #ccfbf1;
  max-width: 1180px;
  margin: 0 auto;
  padding: 36px 24px 64px;
}

.top {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  margin-bottom: 28px;
}

.brand {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
}

h1 {
  margin: 6px 0 4px;
  font-size: clamp(28px, 4vw, 40px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ink);
}

.sub {
  margin: 0;
  color: var(--muted);
}

.top-right {
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.ask-btn {
  border: 0;
  background: #0f766e;
  color: #fff;
  font-weight: 600;
  border-radius: 999px;
  padding: 8px 16px;
  cursor: pointer;
}

.user-box {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #334155;
}

.user-box .role {
  color: #0f766e;
  font-size: 12px;
}

.logout-btn {
  border: 1px solid #dbe4df;
  background: #fff;
  border-radius: 999px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
}

.fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 52px;
  height: 52px;
  border: 0;
  border-radius: 50%;
  background: #0f766e;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(15, 118, 110, 0.35);
  z-index: 40;
}

.ranges {
  display: inline-flex;
  gap: 6px;
  padding: 4px;
  background: #e2ebe7;
  border-radius: 999px;
}

.ranges button {
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 8px 14px;
  border-radius: 999px;
  cursor: pointer;
  font: inherit;
}

.ranges button.active {
  background: var(--panel);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.health {
  margin: 10px 0 0;
  font-size: 13px;
}

.health.ok {
  color: #0f766e;
}

.health.bad,
.banner-err {
  color: #b42318;
}

.banner-load {
  color: var(--muted);
}

.metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0 20px;
}

.metric {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px;
}

.m-label {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.m-value {
  margin: 8px 0 4px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ink);
}

.m-hint {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
}

.grid-2 {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 16px 18px 12px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.panel-head h2 {
  margin: 0;
  font-size: 16px;
}

select,
.ghost {
  font: inherit;
  border: 1px solid var(--line);
  background: #f8fafc;
  border-radius: 8px;
  padding: 6px 10px;
  color: var(--ink);
}

.ghost {
  cursor: pointer;
}

.rank-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  border-top: 1px solid var(--line);
}

.rank-list li {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 10px 4px;
  cursor: pointer;
  border-bottom: 1px solid #f1f5f9;
}

.rank-list li:hover,
.rank-list li.selected {
  background: var(--accent-soft);
}

.idx {
  color: var(--muted);
  font-size: 12px;
}

.name {
  font-weight: 600;
}

.val {
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}

.detail {
  margin-top: 16px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 960px) {
  .metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .grid-2,
  .top {
    grid-template-columns: 1fr;
    display: grid;
  }
  .top-right {
    text-align: left;
  }
}

@media (max-width: 640px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
