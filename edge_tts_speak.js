const { MsEdgeTTS, OUTPUT_FORMAT } = require("msedge-tts");

const VOICE = process.argv[3] || "en-IE-EmilyNeural";
const FORMAT = OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3;

function streamToBuffer(stream) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on("data", chunk => chunks.push(Buffer.from(chunk)));
    stream.on("close", () => resolve(Buffer.concat(chunks)));
    stream.on("error", reject);
  });
}

(async () => {
  const text = (process.argv[2] || "").trim();
  if (!text) {
    throw new Error("No text to speak");
  }

  const tts = new MsEdgeTTS();
  await tts.setMetadata(VOICE, FORMAT);
  const result = await tts.toStream(text.slice(0, 5000));
  const audio = await streamToBuffer(result.audioStream);
  if (!audio.length) {
    throw new Error("No audio returned from Edge TTS");
  }
  process.stdout.write(audio);
  process.exit(0);
})().catch(error => {
  process.stderr.write(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
