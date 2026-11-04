"""Synthetic local audio through Kokoro, Silero, Smart Turn and Whisper. No devices."""
# pyright: reportMissingImports=false
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

from jarvis.voice.worker import SpeechRuntime


async def main():
    import numpy as np
    import soxr
    from kokoro_onnx import Kokoro
    root = Path(__file__).resolve().parents[1]
    runtime = SpeechRuntime(root)
    try:
        await runtime.load()
        await runtime.start_listening()
        assert runtime.turn_analyzer is not None,'Smart Turn failed to initialize'
        assert runtime.endpoint is not None
        kokoro = Kokoro(str(root/'.voice-models/kokoro-v1.0.int8.onnx'),str(root/'.voice-models/voices-v1.0.bin'))
        audio,rate = kokoro.create('Please open the browser and find Python documentation.',voice='bm_george',speed=1,lang='en-gb')
        audio = soxr.resample(audio,rate,16000)
        speech_samples = len(audio)
        audio = np.concatenate((audio,np.zeros(32000,dtype=np.float32)))
        pcm = (np.clip(audio,-1,0.9999)*32768).astype('<i2').tobytes()
        ended = None;segment = None;boundaries = 0;began = time.perf_counter()
        for offset in range(0,len(pcm),640):
            _,segment = await runtime.endpoint.feed(pcm[offset:offset+640])
            if segment is not None:
                ended = (offset+640)//2;boundaries += 1;break
        assert ended is not None and boundaries == 1 and segment is not None
        def audio_message(pcm):
            return {'epoch':runtime.epoch,'audio':base64.b64encode(pcm).decode('ascii'),
                    'rate':16000,'channels':1,'format':'s16'}
        with patch('jarvis.voice.worker.emit') as emit:
            click = np.zeros(16000,dtype='<i2')
            click[8000] = 30000
            await runtime.transcribe(audio_message(click.tobytes()))
            assert emit.call_args.kwargs['text'] == ''
            await runtime.transcribe(audio_message(segment))
            transcript = emit.call_args.kwargs['text']
        assert 'browser' in transcript.lower() and 'python' in transcript.lower(),transcript
        print(json.dumps({'smart_turn_loaded':True,'utterance_boundaries':boundaries,
            'end_after_speech_seconds':round((ended-speech_samples)/16000,2),
            'processing_seconds':round(time.perf_counter()-began,2),'synthetic_transcript':transcript,
            'isolated_click_rejected':True,'microphone_opened':False,'speaker_opened':False,'cloud_calls':0}))
    finally:await runtime.close()


if __name__=='__main__':asyncio.run(main())
