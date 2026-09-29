<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, default: () => ({}) },
  height: { type: String, default: '320px' },
})

const el = ref(null)
let chart

const style = computed(() => ({ height: props.height, width: '100%' }))

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(props.option, true)
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch(
  () => props.option,
  () => render(),
  { deep: true },
)

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="chart" :style="style" />
</template>

<style scoped>
.chart {
  min-height: 240px;
}
</style>
