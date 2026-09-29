function pad(n) {
  return String(n).padStart(2, '0')
}

export function formatDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function rangeDays(days) {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - (days - 1))
  return { startDate: formatDate(start), endDate: formatDate(end) }
}

export function formatNumber(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-'
  return Number(n).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatPercent(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '-'
  return `${(Number(n) * 100).toFixed(2)}%`
}

export function formatMoney(n) {
  return `¥${formatNumber(n, 2)}`
}
