# Cedar Clinic – Voice Appointment Assistant

A voice agent that books and cancels doctor appointments over a browser call. The caller talks to "Maya", who can check a doctor's free slots, book one, or cancel an existing booking. The caller is identified only by the phone number they say during the call.

## Stack

| Part | Used |
| --- | --- |
| Voice pipeline | Pipecat (Python) |
| Speech to text | ElevenLabs Realtime STT (`scribe_v2_realtime`) |
| Text to speech | ElevenLabs TTS (`eleven_flash_v2_5`) |
| LLM | Google Gemini (`gemini-3.5-flash-lite` by default, set with `GEMINI_MODEL`) |
| VAD | Silero VAD |
| Transport | WebSocket (Pipecat `FastAPIWebsocketTransport`, raw PCM audio) |
| Backend | FastAPI |
| Frontend | Plain HTML, CSS and JavaScript |
| Data | In-memory mock data |

## Run it

You need Python 3.11+ and API keys for Google AI Studio (Gemini) and ElevenLabs.

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env           # then fill in the keys
cd backend
python server.py
```

Open http://localhost:7860 in Chrome, click **Try Call** and allow microphone access.

## Environment variables

| Name | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini API key from https://aistudio.google.com/apikey |
| `ELEVENLABS_API_KEY` | ElevenLabs key, used for both STT and TTS |
| `ELEVENLABS_VOICE_ID` | Voice for Maya |
| `GEMINI_MODEL` | Gemini model name |

## Pipeline

```
mic ─▶ WebSocket ─▶ Silero VAD ─▶ ElevenLabs STT ─▶ Gemini (+ tools) ─▶ ElevenLabs TTS ─▶ WebSocket ─▶ speaker
```

The browser records the microphone as 16 kHz PCM (an AudioWorklet) and streams it to the server over a WebSocket. Silero VAD detects when the caller starts and stops talking, ElevenLabs turns the speech into text, and the text is added to the conversation context. Gemini reads the context and either replies or calls one of three tools. Its reply is spoken with ElevenLabs TTS and streamed back as 24 kHz PCM, which the browser plays in order. If the caller talks over Maya, the server sends a `clear` message, the browser drops the queued audio and Maya listens.

Tools registered on the LLM:

| Tool | What it does |
| --- | --- |
| `check_doctor_availability` | Free slots for a doctor or specialty, for one date or all upcoming days |
| `book_appointment` | Books a slot using the caller's name and the phone number they spoke |
| `cancel_appointment` | Cancels the active booking for that phone number |

The system prompt tells Maya to read the phone number back digit by digit and wait for a yes before booking or cancelling.

When a turn ends, or a booking or cancellation happens, the server pushes an event to the dashboard over Server-Sent Events (`/api/events`). That is how the transcript and the tables update live.

## Project layout

```
backend/
  server.py   FastAPI app: call WebSocket, REST endpoints, event stream, serves the frontend
  bot.py      Pipecat pipeline, system prompt and the three tools
  audio_serializer.py  Turns WebSocket bytes into audio frames and back
  data.py     Doctors, slots and appointments (in memory)
  events.py   Small pub/sub used for the live dashboard events
frontend/
  index.html  Dashboard and phone call screen
  style.css
  app.js      Call over WebSocket, audio playback, live updates, waveform, ring sounds
  mic-worklet.js  Converts microphone audio to 16-bit PCM
```

## API

| Method | Path | |
| --- | --- | --- |
| WS | `/ws` | The call: PCM audio in both directions, starts a bot per connection |
| GET | `/api/doctors` | Doctors with all times and free slots for the next 4 days |
| GET | `/api/appointments` | All appointments, newest first |
| GET | `/api/events` | Live events: `transcript`, `booked`, `cancelled`, `call` |

## Mock data

Five doctors with fixed daily times. Slots are generated for the next 4 days from today, so the demo always has future dates. Two bookings are seeded so cancellation can be tried right away:

- `9876543210`: Rahul Sharma with Dr. Ananya Rao
- `9123456780`: Priya Nair with Dr. Sara Thomas

Data lives in memory and resets when the server restarts.

## Troubleshooting

- **Call ends right away**: check the server terminal for an API key error.
- **No audio from Maya**: check `ELEVENLABS_API_KEY` and that the voice ID exists in your ElevenLabs account.
- **Gemini quota or model errors**: change `GEMINI_MODEL` to a model your key can use on the free tier.
