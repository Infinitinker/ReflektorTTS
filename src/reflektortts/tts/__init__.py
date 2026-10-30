"""The TTS service: speech engines, playback and voices, running in their own process.

The core imports only engine.py, to list voices through the engine plugins without loading
the engines; its side of the service is in reflektortts.sinks.tts.
"""
