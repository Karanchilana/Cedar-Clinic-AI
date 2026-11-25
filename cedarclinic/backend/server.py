import json
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import data
import events
from bot import run_bot

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI()


@app.websocket("/ws")
async def call(websocket: WebSocket):
    await websocket.accept()
    await run_bot(websocket)


@app.get("/api/doctors")
def doctors():
    return data.doctors_with_slots()


@app.get("/api/appointments")
def appointments():
    return list(reversed(data.appointments))


@app.get("/api/events")
async def stream():
    async def generate():
        queue = events.subscribe()
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(generate(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
