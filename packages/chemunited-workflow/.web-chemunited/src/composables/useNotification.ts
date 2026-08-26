import { ref } from 'vue'

type NotifType = 'success' | 'error' | 'info' | 'warning'

const message = ref('')
const type = ref<NotifType>('info')
let timer: ReturnType<typeof setTimeout> | null = null

export function useNotification() {
  function notify(msg: string, t: NotifType = 'info', duration = 60000) {
    if (timer) clearTimeout(timer)
    message.value = msg
    type.value = t
    timer = setTimeout(() => { message.value = '' }, duration)
  }

  function dismiss() {
    if (timer) clearTimeout(timer)
    message.value = ''
  }

  return { message, type, notify, dismiss }
}
