import speech_recognition as sr
from gtts import gTTS
from translate import Translator
import os
import tempfile
import logging
import time

class VoiceLanguageHandler:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.translator = Translator(to_lang='en')
        self.supported_languages = {
            'english': 'en',
            'telugu': 'te'
        }
        
        # Initialize logging with custom format
        logging.basicConfig(
            level=logging.WARNING,
            format='%(levelname)s: %(message)s'
        )
        
        # Initialize audio as None first
        self.audio = None
        
        # Perform initial system checks with proper error handling
        try:
            import pyaudio
            # Add signal handler for graceful keyboard interrupt
            import signal
            def handle_interrupt(signum, frame):
                if self.audio:
                    self.audio.terminate()
                logging.info("Audio system shutdown gracefully")
                exit(0)
            signal.signal(signal.SIGINT, handle_interrupt)
            
            # Initialize PyAudio with timeout
            self.audio = pyaudio.PyAudio()
            if self._check_audio_system():
                logging.info("Audio system initialized successfully")
            else:
                logging.warning("Audio system initialization incomplete - some features may be limited")
        except ImportError:
            logging.error("PyAudio not installed. Voice features will be disabled.")
        except Exception as e:
            logging.error(f"Failed to initialize audio system: {e}")
            logging.warning("Voice features will be disabled")
        
    def _check_audio_system(self):
        """Verify audio system configuration"""
        try:
            # Check Windows audio service status if possible
            try:
                import win32serviceutil
                audio_service_status = win32serviceutil.QueryServiceStatus('Audiosrv')[1]
                if audio_service_status != 4:  # 4 means running
                    logging.error("Windows Audio service is not running. Please start the service.")
                    return False
            except ImportError:
                # Skip Windows service check if win32serviceutil is not available
                pass

            # Get system audio information
            device_count = self.audio.get_device_count()
            if device_count == 0:
                logging.error("No audio devices detected in the system. Please check device manager for audio devices.")
                return False
                
            # Check all available audio devices and find the best microphone
            microphone_found = False
            preferred_device = None
            for i in range(device_count):
                try:
                    device_info = self.audio.get_device_info_by_index(i)
                    if device_info.get('maxInputChannels', 0) > 0:
                        device_name = device_info.get('name', 'Unknown')
                        logging.info(f"Found input device: {device_name}")
                        # Check device driver status
                        if 'hostApi' in device_info:
                            logging.info(f"Audio driver: {self.audio.get_host_api_info_by_index(device_info['hostApi']).get('name', 'Unknown')}")
                        
                        microphone_found = True
                        # Prioritize actual microphone devices over Stereo Mix
                        if 'microphone' in device_name.lower() and not preferred_device:
                            preferred_device = device_info
                            self.audio.get_host_api_info_by_index(device_info['hostApi'])
                            logging.info(f"Selected preferred microphone device: {device_name}")
                except Exception as e:
                    logging.warning(f"Could not get info for device {i}: {e}")
                    
            if not microphone_found:
                logging.error("No working microphones found. Please check your audio settings and device manager.")
                return False
                
            # Set the preferred device as default if found
            if preferred_device:
                try:
                    self.audio._default_input_device_info = preferred_device
                    logging.info(f"Successfully set default input device to: {preferred_device.get('name', 'Unknown')}")
                except Exception as e:
                    logging.error(f"Failed to set preferred input device: {e}")
                    return False
                
            # Verify default input device
            try:
                default_input = self.audio.get_default_input_device_info()
                if default_input['maxInputChannels'] == 0:
                    logging.error("Default input device has no input channels. Please check Windows Sound settings > Recording devices.")
                    return False
                    
                if default_input.get('defaultSampleRate', 0) == 0:
                    logging.error("Default input device may be disabled. Please check Windows Sound settings > Recording devices.")
                    return False

                # Check if device is muted in Windows
                # Only check mute status if pycaw is available
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = cast(interface, POINTER(IAudioEndpointVolume))
                    if volume.GetMute():
                        logging.warning("Microphone is muted in Windows. Please unmute it in the system tray.")
                except ImportError:
                    # Skip mute check if pycaw is not available
                    pass
                    
                logging.info(f"Using default input device: {default_input.get('name', 'Unknown')}")
                return True
                
            except Exception as e:
                logging.error(f"Error accessing default input device: {e}. Please check Windows Sound settings.")
                return False
                
        except Exception as e:
            logging.error(f"Error during audio system check: {e}. Please verify audio drivers are installed correctly.")
            return False

    def speech_to_text(self, audio_data, source_language='en-IN'):
        """Convert speech to text with language support"""
        try:
            # System-level microphone checks
            try:
                import pyaudio
                audio = pyaudio.PyAudio()
                device_count = audio.get_device_count()
                
                # Find preferred microphone device
                preferred_device = None
                for i in range(device_count):
                    try:
                        device_info = audio.get_device_info_by_index(i)
                        if device_info.get('maxInputChannels', 0) > 0 and 'microphone' in device_info.get('name', '').lower():
                            preferred_device = device_info
                            break
                    except Exception:
                        continue
                
                if not preferred_device:
                    logging.error("No suitable microphone found. Please connect a microphone.")
                    return None
                
                # Set preferred device as default
                audio._default_input_device_info = preferred_device
                    
            except Exception as e:
                logging.error(f"Error checking audio system: {e}. Please verify microphone permissions and drivers.")
            
            # Optimize recognition parameters for better accuracy
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.energy_threshold = 1000  # Increased threshold for better noise filtering
            self.recognizer.pause_threshold = 0.8  # Reduced pause threshold for more continuous recognition
            
            # Enhanced noise reduction and audio quality settings
            self.recognizer.dynamic_energy_adjustment_damping = 0.15  # Balanced noise reduction
            self.recognizer.dynamic_energy_ratio = 1.5  # Adjusted for better signal-to-noise ratio
            self.recognizer.operation_timeout = 10  # Shorter timeout for faster feedback
            
            # Improved ambient noise adjustment
            if hasattr(audio_data, 'duration'):
                self.recognizer.adjust_for_ambient_noise(audio_data, duration=min(audio_data.duration, 3.0))  # Increased duration
            
            # Add additional error checking for audio data
            if not audio_data or not hasattr(audio_data, 'get_raw_data'):
                logging.error("Invalid audio data format - Please ensure your microphone is properly connected")
                return None
            
            # Enhanced sample rate handling
            if hasattr(audio_data, 'sample_rate'):
                if audio_data.sample_rate < 16000:
                    logging.warning("Low sample rate detected. For better recognition, use a microphone with at least 16kHz sample rate.")
                elif audio_data.sample_rate > 48000:
                    logging.warning("High sample rate detected, audio will be downsampled for optimal processing")
            
            # Improved recognition with adaptive retry mechanism
            max_retries = 3  # Reduced retries for faster response
            backoff_delay = 0.5  # Reduced initial delay
            
            for attempt in range(max_retries):
                try:
                    # Dynamic energy threshold adjustment
                    if attempt > 0:
                        self.recognizer.energy_threshold *= 0.8  # More aggressive threshold reduction
                        self.recognizer.dynamic_energy_ratio += 0.5  # Incrementally increase sensitivity
                    
                    text = self.recognizer.recognize_google(audio_data, language=source_language)
                    if text and len(text.strip()) > 0:
                        logging.info(f"Successfully recognized text on attempt {attempt + 1}: {text}")
                        return text.strip()
                        
                except sr.UnknownValueError:
                    if attempt < max_retries - 1:
                        logging.warning(f"Recognition attempt {attempt + 1} failed. Optimizing parameters for next attempt...")
                        time.sleep(backoff_delay)  # Shorter delay between retries
                        backoff_delay *= 1.2  # Gentler backoff increase
                        continue
                    logging.error("Speech recognition unsuccessful. Please speak clearly and ensure you're in a quiet environment.")
                    return None
                    
                except sr.RequestError as e:
                    if "recognition connection failed" in str(e).lower():
                        logging.error("Network connection error. Please check your internet connection and try again.")
                    else:
                        logging.error(f"Speech recognition service error: {e}. Please try again.")
                    return None
            
            logging.error("Speech recognition failed after multiple optimization attempts")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in speech recognition: {e}")
            return None

    def text_to_speech(self, text, language='en'):
        """Convert text to speech with language support"""
        try:
            tts = gTTS(text=text, lang=language)
            # Create a temporary file to store the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_filename = fp.name
                tts.save(temp_filename)
            return temp_filename
        except Exception as e:
            logging.error(f"Error in text to speech conversion: {e}")
            return None

    def translate_text(self, text, target_language='te'):
        """Translate text between languages"""
        try:
            translation = self.translator.translate(text, dest=target_language)
            return translation.text
        except Exception as e:
            logging.error(f"Translation error: {e}")
            return None

    def process_voice_input(self, audio_data, source_language='en-IN'):
        """Process voice input and return text"""
        text = self.speech_to_text(audio_data, source_language)
        if text:
            return text
        return None

    def process_voice_output(self, text, language='en'):
        """Process text to voice output"""
        audio_file = self.text_to_speech(text, language)
        return audio_file

    def read_summary(self, summary_text, language='en'):
        """Read out the summary in the specified language with enhanced error handling and language support"""
        try:
            if not summary_text:
                logging.error("Empty summary text provided")
                return None

            # Validate language code
            if language not in self.supported_languages.values():
                logging.error(f"Unsupported language code: {language}")
                return None

            # Translate if not in English
            if language != 'en':
                translated_text = self.translate_text(summary_text, language)
                if not translated_text:
                    logging.error(f"Failed to translate summary to {language}")
                    return None
                summary_text = translated_text

            # Convert to speech
            audio_file = self.text_to_speech(summary_text, language)
            if not audio_file:
                logging.error(f"Failed to convert summary to speech in {language}")
                return None

            logging.info(f"Successfully generated audio summary in {language}")
            return audio_file

        except Exception as e:
            logging.error(f"Error reading summary: {e}")
            return None

    def process_follow_up_question(self, question_text, language='en'):
        """Process and read out follow-up questions in the specified language"""
        try:
            # Translate if not in English
            if language != 'en':
                question_text = self.translate_text(question_text, language)
            
            # Convert to speech and play
            audio_file = self.text_to_speech(question_text, language)
            return audio_file
        except Exception as e:
            logging.error(f"Error processing follow-up question: {e}")
            return None

    def read_follow_up_question(self, question_text, language='en'):
        """Read out the follow-up question in the specified language with enhanced features"""
        try:
            if not question_text:
                logging.error("Empty question text provided")
                return None

            # Validate and normalize language code
            language = language.lower()
            if language not in self.supported_languages.values():
                logging.warning(f"Unsupported language {language}, falling back to English")
                language = 'en'

            # Translate if not in English
            if language != 'en':
                translated_text = self.translate_text(question_text, language)
                if not translated_text:
                    logging.error(f"Failed to translate question to {language}, falling back to English")
                    translated_text = question_text
                    language = 'en'
                question_text = translated_text

            # Enhanced speech parameters for questions
            tts = gTTS(text=question_text, lang=language, slow=False)
            
            # Create a temporary file with unique name
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{language}.mp3') as fp:
                temp_filename = fp.name
                try:
                    tts.save(temp_filename)
                    logging.info(f"Successfully generated audio question in {language}")
                    return temp_filename
                except Exception as e:
                    logging.error(f"Failed to save audio file: {e}")
                    if os.path.exists(temp_filename):
                        os.remove(temp_filename)
                    return None

        except Exception as e:
            logging.error(f"Error processing follow-up question: {e}")
            return None

    def cleanup_temp_file(self, file_path):
        """Clean up temporary audio files"""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logging.error(f"Error cleaning up temporary file: {e}")