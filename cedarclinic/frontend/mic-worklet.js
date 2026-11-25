class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
  }

  process(inputs) {
    const channel = inputs[0][0];
    if (channel) {
      for (const sample of channel) this.samples.push(sample);
    }

    if (this.samples.length >= 640) {
      const pcm = new Int16Array(this.samples.length);
      this.samples.forEach((sample, i) => {
        pcm[i] = Math.max(-1, Math.min(1, sample)) * 0x7fff;
      });
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this.samples = [];
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
