import { ref, computed, onUnmounted } from 'vue'

export function useTimer() {
  const seconds = ref(0)
  const isRunning = ref(false)
  let intervalId: ReturnType<typeof setInterval> | null = null

  function start() {
    if (isRunning.value) return
    isRunning.value = true
    intervalId = setInterval(() => { seconds.value++ }, 1000)
  }

  function stop() {
    isRunning.value = false
    if (intervalId) { clearInterval(intervalId); intervalId = null }
  }

  function reset() {
    stop()
    seconds.value = 0
  }

  const formatted = computed(() => {
    const m = Math.floor(seconds.value / 60).toString().padStart(2, '0')
    const s = (seconds.value % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  })

  onUnmounted(stop)

  return { seconds, isRunning, start, stop, reset, formatted }
}
