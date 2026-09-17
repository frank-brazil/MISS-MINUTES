"""Manual verification for the real OpenAI voice providers.

Requires a valid OPENAI_API_KEY in the environment (or a local .env loaded
by python-dotenv). This script is NOT used by automated tests; it lets you
verify real transcription and synthesis with your own audio/text.

Examples:
    python scripts/voice_demo.py --audio path/to/speech.mp3
    python scripts/voice_demo.py --text "Hello from MISSMINUTES" --output out.mp3
    python scripts/voice_demo.py --audio speech.wav --text "Reply text" --output reply.mp3

Prompts the user for confirmation before any network call is made.
"""

import argparse
import asyncio
import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.providers.openai_speech_to_text import OpenAISpeechToText  # noqa: E402
from app.providers.openai_text_to_speech import OpenAITextToSpeech  # noqa: E402
from app.voice.base import SpeechInput, TextToSpeechRequest  # noqa: E402


async def transcribe(audio_path: Path) -> None:
    stt = OpenAISpeechToText()
    data = audio_path.read_bytes()
    audio_format = audio_path.suffix.lstrip(".") or "wav"
    print(f"Transcribing {audio_path} ({len(data)} bytes, format={audio_format})...")
    result = await stt.transcribe(SpeechInput(audio=data, format=audio_format))
    if result.success:
        print(f"  success: {result.success}")
        print(f"  text: {result.text}")
        print(f"  language: {result.language}")
        print(f"  confidence: {result.confidence}")
    else:
        print(f"  transcription failed: {result.error}")


async def synthesize(text: str, output: Path) -> None:
    tts = OpenAITextToSpeech()
    print(f"Synthesizing ({len(text)} characters)...")
    result = await tts.synthesize(TextToSpeechRequest(text=text))
    if result.success and result.audio is not None:
        output.write_bytes(result.audio.content)
        print(f"  saved {len(result.audio.content)} bytes ({result.audio.format}) to {output}")
    else:
        print(f"  synthesis failed: {result.error}")


async def main(audio: Path | None, text: str | None, output: Path) -> None:
    if audio is not None:
        await transcribe(audio)
    if text is not None:
        await synthesize(text, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual voice provider demo.")
    parser.add_argument("--audio", type=Path, default=None, help="Audio file to transcribe.")
    parser.add_argument("--text", default=None, help="Text to synthesize into speech.")
    parser.add_argument("--output", type=Path, default=Path("output.mp3"), help="TTS output file.")
    args = parser.parse_args()
    if args.audio is None and args.text is None:
        parser.error("provide at least one of --audio or --text")
    if args.audio is not None and not args.audio.is_file():
        parser.error(f"--audio is not a file: {args.audio}")

    answer = input("This makes real network calls to OpenAI. Continue? [y/N] ").strip()
    if answer.lower() not in ("y", "yes"):
        print("Aborted.")
        raise SystemExit(0)

    asyncio.run(main(audio=args.audio, text=args.text, output=args.output))
