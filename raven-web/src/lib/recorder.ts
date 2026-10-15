const STT_RATE = 16000

export type Recorded = {
  /** What the browser recorded, for playing back in the chat. */
  original: Blob
  /** 16 kHz mono 16-bit WAV, what the server's Whisper expects. */
  wav: Blob
  duration: number
}

export type Recording = {
  /** Microphone loudness right now, 0..1, for the live bars. */
  level: () => number
  stop: () => Promise<Recorded>
  cancel: () => void
}

function encodeWav(samples: Float32Array, rate: number): Blob {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2))
  const text = (at: number, s: string) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)))
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  text(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true))
  return new Blob([view], { type: 'audio/wav' })
}

/** Decoding through a 16 kHz offline context resamples on the way; channels are averaged to mono. */
async function toWav16k(blob: Blob): Promise<{ wav: Blob; duration: number }> {
  const decoded = await new OfflineAudioContext(1, 1, STT_RATE).decodeAudioData(await blob.arrayBuffer())
  const mono = new Float32Array(decoded.length)
  for (let c = 0; c < decoded.numberOfChannels; c++) {
    decoded.getChannelData(c).forEach((v, i) => { mono[i] = (mono[i] ?? 0) + v / decoded.numberOfChannels })
  }
  return { wav: encodeWav(mono, STT_RATE), duration: decoded.duration }
}

export async function startRecording(): Promise<Recording> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Bu tarayıcı mikrofon kaydını desteklemiyor.')
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  })
  const recorder = new MediaRecorder(stream)
  const chunks: Blob[] = []
  recorder.ondataavailable = e => {
    if (e.data.size) chunks.push(e.data)
  }
  const meter = new AudioContext()
  const analyser = meter.createAnalyser()
  analyser.fftSize = 512
  meter.createMediaStreamSource(stream).connect(analyser)
  const frame = new Float32Array(analyser.fftSize)
  recorder.start()

  const release = () => {
    stream.getTracks().forEach(t => t.stop())
    void meter.close()
  }
  return {
    level() {
      analyser.getFloatTimeDomainData(frame)
      let sum = 0
      for (const v of frame) sum += v * v
      return Math.min(1, Math.sqrt(sum / frame.length) * 6)
    },
    stop: () =>
      new Promise<Recorded>((resolve, reject) => {
        recorder.onstop = () => {
          release()
          const original = new Blob(chunks, { type: recorder.mimeType })
          toWav16k(original).then(({ wav, duration }) => resolve({ original, wav, duration }), reject)
        }
        recorder.stop()
      }),
    cancel() {
      recorder.onstop = null
      if (recorder.state !== 'inactive') recorder.stop()
      release()
    },
  }
}
