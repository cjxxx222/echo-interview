import { ref } from 'vue'

export function useSSE() {
  const isStreaming = ref(false)
  const currentText = ref('')
  const controller = ref<AbortController | null>(null)

  async function startStream(
    url: string,
    body: object,
    onToken: (token: string) => void,
    onStatus?: (status: object) => void,
    onDone?: () => void
  ) {
    controller.value = new AbortController()
    isStreaming.value = true
    currentText.value = ''

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.value.signal,
      })

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue
          try {
            const data = JSON.parse(part.slice(6))
            if (data.type === 'token') {
              currentText.value += data.data
              onToken(data.data)
            } else if (data.type === 'status') {
              onStatus?.(data.data)
            } else if (data.type === 'done') {
              onDone?.()
            }
          } catch (_e) { /* skip */ }
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') console.error(e)
    } finally {
      isStreaming.value = false
    }
  }

  function stopStream() {
    controller.value?.abort()
  }

  return { isStreaming, currentText, startStream, stopStream }
}
