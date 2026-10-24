import { onBeforeUnmount, ref, shallowRef } from 'vue'

// The live state of the platform's devices and LCDs, from GET /platform/stream.
// The browser only listens: the work-server records the commands it sends and
// the monitoring readings, and the panel is live only while monitoring is on
// from the Monitoring page.

export type DeviceStatus = 'unknown' | 'running' | 'done' | 'failed'

export interface LiveCommand {
  name: string
  params: Record<string, unknown> | null
  at: string
  run: string | null
  node: string | null
}

export interface LiveDevice {
  kind: string | null
  status: DeviceStatus
  command: LiveCommand | null
  picture: Record<string, unknown> | null
  error: string | null
}

export interface LiveDisplay {
  value: string | null
  at: string | null
  error: string | null
  monitored: boolean
}

export type LiveConnection = 'connecting' | 'open' | 'reconnecting' | 'disconnected'

interface Snapshot {
  seq: number
  live: boolean
  pictures: boolean
  devices: Record<string, LiveDevice>
  displays: Record<string, LiveDisplay>
}

interface Update {
  seq: number
  devices?: Record<string, LiveDevice>
  displays?: Record<string, LiveDisplay>
}

const HEARTBEAT_MS = 5_000
// Without a frame for two heartbeats the stream counts as lost, and a fresh
// one is opened every RETRY_MS; after GIVE_UP_MS the picture shows as frozen.
const SILENCE_MS = 2 * HEARTBEAT_MS
const RETRY_MS = 10_000
const GIVE_UP_MS = 30_000
// A command that finishes faster than this gets a short flash instead of a
// running ring: its device doesn't report when it finishes.
const FLASH_BELOW_MS = 800
const FLASH_MS = 1_500

export function usePlatformLive() {
  const live = ref(false)
  const pictures = ref(false)
  const devices = shallowRef<Record<string, LiveDevice>>({})
  const displays = shallowRef<Record<string, LiveDisplay>>({})
  const connection = ref<LiveConnection>('connecting')
  const flashing = shallowRef<ReadonlySet<string>>(new Set())

  let source: EventSource | null = null
  let seq = 0
  let openedAt = 0
  let lastFrameAt = 0
  let lostSince = 0
  let watchdog: number | undefined
  const runningSince = new Map<string, number>()
  const flashTimers = new Map<string, number>()

  function frameArrived() {
    lastFrameAt = Date.now()
    lostSince = 0
    connection.value = 'open'
  }

  function parse<T>(event: MessageEvent): T | null {
    try {
      return JSON.parse(event.data as string) as T
    } catch {
      return null
    }
  }

  function flash(name: string) {
    window.clearTimeout(flashTimers.get(name))
    flashing.value = new Set([...flashing.value, name])
    flashTimers.set(name, window.setTimeout(() => {
      flashTimers.delete(name)
      const next = new Set(flashing.value)
      next.delete(name)
      flashing.value = next
    }, FLASH_MS))
  }

  function noteStatus(name: string, previous: LiveDevice | undefined, next: LiveDevice) {
    if (next.status === 'running') {
      if (previous?.status !== 'running') runningSince.set(name, Date.now())
      return
    }
    const since = runningSince.get(name)
    runningSince.delete(name)
    if (since !== undefined && Date.now() - since < FLASH_BELOW_MS) flash(name)
  }

  function onSnapshot(event: MessageEvent) {
    const data = parse<Snapshot>(event)
    if (!data) return
    frameArrived()
    seq = data.seq
    live.value = data.live
    pictures.value = data.pictures
    runningSince.clear()
    for (const [name, device] of Object.entries(data.devices)) {
      if (device.status === 'running') runningSince.set(name, Date.now())
    }
    devices.value = data.devices
    displays.value = data.displays
  }

  function onUpdate(event: MessageEvent) {
    const data = parse<Update>(event)
    if (!data) return
    frameArrived()
    if (data.seq <= seq) return
    seq = data.seq
    if (data.devices) {
      for (const [name, device] of Object.entries(data.devices)) {
        noteStatus(name, devices.value[name], device)
      }
      devices.value = { ...devices.value, ...data.devices }
    }
    if (data.displays) displays.value = { ...displays.value, ...data.displays }
  }

  function close() {
    source?.close()
    source = null
  }

  function open() {
    close()
    openedAt = Date.now()
    source = new EventSource('/platform/stream')
    source.addEventListener('snapshot', onSnapshot)
    source.addEventListener('update', onUpdate)
    source.addEventListener('heartbeat', frameArrived)
    source.onerror = () => {
      // Refused (no project loaded yet, a server error) closes the stream for
      // good; the watchdog opens a new one later. A network error leaves the
      // browser reconnecting, sending Last-Event-ID to replay what it missed.
      if (source?.readyState === EventSource.CLOSED) close()
      if (connection.value !== 'disconnected') connection.value = 'reconnecting'
    }
  }

  function check() {
    const now = Date.now()
    if (now - lastFrameAt <= SILENCE_MS) return
    if (!lostSince) lostSince = lastFrameAt
    connection.value = now - lostSince > GIVE_UP_MS ? 'disconnected' : 'reconnecting'
    // Silent but maybe not closed (a sleeping laptop, a proxy holding the
    // connection): start over with a fresh stream and a fresh snapshot.
    if (!source || now - openedAt > RETRY_MS) open()
  }

  function start() {
    if (watchdog !== undefined) return
    connection.value = 'connecting'
    lastFrameAt = Date.now()
    lostSince = 0
    open()
    watchdog = window.setInterval(check, 1_000)
  }

  function stop() {
    close()
    window.clearInterval(watchdog)
    watchdog = undefined
    for (const timer of flashTimers.values()) window.clearTimeout(timer)
    flashTimers.clear()
  }

  onBeforeUnmount(stop)

  return { live, pictures, devices, displays, connection, flashing, start, stop }
}
