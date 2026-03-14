import whisper
import logging

logger = logging.getLogger(__name__)

class AudioTranscriber:
    def __init__(self, model_size="base"):
        """
        model_size options: tiny, base, small, medium, large
        base = good balance of speed/accuracy
        """
        logger.info(f"Loading Whisper {model_size} model...")
        self.model = whisper.load_model(model_size)
        logger.info("Whisper model ready")
    
    def transcribe_audio(self, audio_file_path: str) -> dict:
        """
        Transcribe audio file to text
        
        Returns:
        {
            'text': full transcript,
            'segments': [{text, start, end}...],
            'language': detected language
        }
        """
        logger.info(f"Transcribing {audio_file_path}...")
        result = self.model.transcribe(
            audio_file_path,
            language="en",  # Force English or set to None for auto-detect
            verbose=False
        )
        logger.info(f"✓ Transcription complete: {len(result['text'])} chars")
        return result