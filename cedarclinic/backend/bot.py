import os
from datetime import date

from google.genai.types import HttpOptions, HttpRetryOptions
from loguru import logger
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

import data
import events
from audio_serializer import RawAudioSerializer


def build_prompt():
    today = date.today()
    doctors = "\n".join(f"- {d['name']}, {d['specialty']}" for d in data.DOCTORS)
    return f"""You are Maya, the voice receptionist at Cedar Clinic.
Today is {today.strftime('%A')}, {today.isoformat()}. Appointments can be booked for the next {data.DAYS_AHEAD} days.

Doctors at the clinic:
{doctors}

You can check a doctor's availability, book an appointment and cancel an appointment.

How to talk:
- This is a phone call. Keep every reply to one or two short sentences.
- No lists, no markdown, no emojis. Speak like a friendly human receptionist.
- Say dates like "Thursday the 26th" and times like "10:30 AM".
- Offer at most three slots at a time.

Rules:
- The caller is identified only by the phone number they tell you. Never assume one.
- Before booking or cancelling, read the phone number back digit by digit and wait for the caller to say it is correct.
  Write the digits with spaces so they are spoken one by one, like "9 8 4 5 6, 1 2 3 4 5".
- To book you need the caller's name, the doctor, the date and the time. Always check availability before offering slots.
- Send dates to tools as YYYY-MM-DD and times as HH:MM in 24 hour format.
- If a tool returns an error, explain it simply and help the caller pick something else.
- After booking or cancelling, confirm the doctor, date and time in one sentence.

Start the call by greeting the caller and asking how you can help."""


tools = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            name="check_doctor_availability",
            description="Get free appointment slots for a doctor. Accepts a doctor name or a specialty.",
            properties={
                "doctor": {"type": "string", "description": "Doctor name or specialty, e.g. 'Dr. Rao' or 'dermatologist'"},
                "date": {"type": "string", "description": "Optional date in YYYY-MM-DD. Leave empty to get all upcoming days."},
            },
            required=["doctor"],
        ),
        FunctionSchema(
            name="book_appointment",
            description="Book a slot after the caller has confirmed their phone number.",
            properties={
                "doctor": {"type": "string", "description": "Doctor name"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD"},
                "time": {"type": "string", "description": "Time in HH:MM, 24 hour"},
                "phone": {"type": "string", "description": "Caller's 10 digit phone number, digits only"},
                "patient_name": {"type": "string", "description": "Caller's name"},
            },
            required=["doctor", "date", "time", "phone", "patient_name"],
        ),
        FunctionSchema(
            name="cancel_appointment",
            description="Cancel the caller's appointment, found by the phone number they confirmed.",
            properties={
                "phone": {"type": "string", "description": "Caller's 10 digit phone number, digits only"},
                "appointment_id": {"type": "string", "description": "Only needed when the caller has more than one appointment"},
            },
            required=["phone"],
        ),
    ]
)


async def check_doctor_availability(params: FunctionCallParams):
    args = params.arguments
    result = data.check_availability(args["doctor"], args.get("date") or None)
    await params.result_callback(result)


async def book_appointment(params: FunctionCallParams):
    args = params.arguments
    result = data.book(args["doctor"], args["date"], args["time"], args["phone"], args["patient_name"])
    if "booked" in result:
        events.publish({"type": "booked", "appointment": result["booked"]})
    await params.result_callback(result)


async def cancel_appointment(params: FunctionCallParams):
    args = params.arguments
    result = data.cancel(args["phone"], args.get("appointment_id"))
    if "cancelled" in result:
        events.publish({"type": "cancelled", "appointment": result["cancelled"]})
    await params.result_callback(result)


async def run_bot(websocket):
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=RawAudioSerializer(),
        ),
    )

    stt = ElevenLabsRealtimeSTTService(api_key=os.getenv("ELEVENLABS_API_KEY"))

    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(voice=os.getenv("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9")),
    )

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        http_options=HttpOptions(
            retry_options=HttpRetryOptions(attempts=4, initial_delay=0.5, http_status_codes=[429, 500, 503]),
        ),
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            system_instruction=build_prompt(),
        ),
    )
    llm.register_function("check_doctor_availability", check_doctor_availability)
    llm.register_function("book_appointment", book_appointment)
    llm.register_function("cancel_appointment", cancel_appointment)

    context = LLMContext(messages=[{"role": "user", "content": "Hello?"}], tools=tools)
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
    )

    @aggregators.user().event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message):
        if message.content:
            events.publish({"type": "transcript", "role": "user", "text": message.content})

    @aggregators.assistant().event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        if message.content:
            events.publish({"type": "transcript", "role": "agent", "text": message.content})

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Caller connected")
        events.publish({"type": "call", "state": "connected"})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Caller disconnected")
        events.publish({"type": "call", "state": "ended"})
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
