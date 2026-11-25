import json

from pipecat.frames.frames import InputAudioRawFrame, InterruptionFrame, OutputAudioRawFrame
from pipecat.serializers.base_serializer import FrameSerializer


class RawAudioSerializer(FrameSerializer):
    async def serialize(self, frame):
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": "clear"})
        return None

    async def deserialize(self, data):
        if isinstance(data, bytes):
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        return None
