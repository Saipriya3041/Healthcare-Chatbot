import os
from flask import Flask, request, jsonify, send_file, session, render_template, redirect, current_app
import logging
from dotenv import load_dotenv
from voice_language_handler import VoiceLanguageHandler
import speech_recognition as sr
import base64
import io
import sqlite3
from auth import auth_bp

# Load environment variables from .env file
load_dotenv()

# Initialize Flask App
app = Flask(__name__)
# Set a permanent secret key for session management
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
# Configure session parameters
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookies over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to session cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # Session lifetime of 30 minutes
app.register_blueprint(auth_bp, url_prefix='/auth')

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('index.html')

# Initialize voice and language handler
voice_handler = VoiceLanguageHandler()

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def generate_summary(symptoms, language="English", follow_up_answers=None, format_type="concise"):
    """
    Generates a medical summary based on user symptoms and follow-up answers using local processing.
    Always generates a concise single-paragraph summary optimized for quick medical review.
    """
    # Prepare context from common symptoms database
    common_symptoms = {
        "fever": {
            "causes": ["Viral infection", "Bacterial infection", "Inflammation", "COVID-19"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if temperature exceeds 103°F (39.4°C)"
        },
        "headache": {
            "causes": ["Tension", "Migraine", "Sinusitis", "Hypertension", "Dehydration"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if accompanied by confusion or stiff neck"
        },
        "cough": {
            "causes": ["Upper respiratory infection", "Bronchitis", "Asthma", "COVID-19", "Allergies"],
            "severity": "Mild to Severe",
            "urgency": "Urgent if difficulty breathing or coughing blood"
        },
        "fatigue": {
            "causes": ["Sleep deprivation", "Anemia", "Depression", "Thyroid dysfunction", "Post-viral syndrome"],
            "severity": "Varies",
            "urgency": "Evaluate if persistent > 2 weeks"
        },
        "nausea": {
            "causes": ["Gastroenteritis", "Food poisoning", "Migraine", "Pregnancy", "Medication side effect"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if severe dehydration signs present"
        },
        "chest pain": {
            "causes": ["Heart attack", "Angina", "Pulmonary embolism", "Anxiety", "Muscle strain"],
            "severity": "High",
            "urgency": "Seek immediate emergency care"
        },
        "shortness of breath": {
            "causes": ["Asthma", "Anxiety", "Heart failure", "Pneumonia", "COVID-19"],
            "severity": "High",
            "urgency": "Seek immediate care if severe or worsening"
        },
        "dizziness": {
            "causes": ["Low blood pressure", "Inner ear problems", "Dehydration", "Anemia", "Medication side effect"],
            "severity": "Moderate",
            "urgency": "Urgent if accompanied by fainting or severe headache"
        },
        "abdominal pain": {
            "causes": ["Gastritis", "Appendicitis", "Food poisoning", "Ulcer", "Gallstones"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if severe or accompanied by fever"
        },
        "rash": {
            "causes": ["Allergic reaction", "Infection", "Autoimmune condition", "Medication reaction", "Contact dermatitis"],
            "severity": "Mild to Moderate",
            "urgency": "Urgent if accompanied by difficulty breathing or severe swelling"
        },
        "joint pain": {
            "causes": ["Arthritis", "Injury", "Gout", "Lupus", "Fibromyalgia"],
            "severity": "Moderate",
            "urgency": "Seek care if severe or affecting mobility"
        },
        "sore throat": {
            "causes": ["Viral infection", "Strep throat", "Allergies", "Acid reflux", "Tonsillitis"],
            "severity": "Mild to Moderate",
            "urgency": "Seek care if difficulty swallowing or breathing"
        },
        "back pain": {
            "causes": ["Muscle strain", "Herniated disc", "Arthritis", "Osteoporosis", "Kidney problems"],
            "severity": "Moderate",
            "urgency": "Urgent if accompanied by numbness or weakness"
        },
        "ear pain": {
            "causes": ["Ear infection", "Sinus pressure", "Tooth infection", "Earwax buildup", "Swimmer's ear"],
            "severity": "Mild to Moderate",
            "urgency": "Seek care if severe pain or fever present"
        },
        "eye problems": {
            "causes": ["Conjunctivitis", "Allergies", "Foreign object", "Glaucoma", "Eye strain"],
            "severity": "Moderate",
            "urgency": "Urgent if sudden vision changes or severe pain"
        },
        "stomach pain": {
            "causes": ["Indigestion", "Food poisoning", "Ulcer", "Appendicitis", "IBS"],
            "severity": "Moderate to High",
            "urgency": "Seek immediate care if severe or persistent"
        },
        "muscle weakness": {
            "causes": ["Fatigue", "Nerve problems", "Stroke", "Multiple sclerosis", "Electrolyte imbalance"],
            "severity": "High",
            "urgency": "Urgent if sudden onset or affecting breathing"
        },
        "bleeding": {
            "causes": ["Injury", "Surgery", "Blood disorder", "Medication side effect", "Internal bleeding"],
            "severity": "High",
            "urgency": "Seek immediate care if heavy or uncontrolled"
        },
        "swelling": {
            "causes": ["Injury", "Infection", "Heart problems", "Kidney problems", "Allergic reaction"],
            "severity": "Moderate to High",
            "urgency": "Urgent if affecting breathing or circulation"
        },
        "anxiety": {
            "causes": ["Stress", "Panic disorder", "PTSD", "Depression", "Medical conditions"],
            "severity": "Moderate",
            "urgency": "Seek care if affecting daily life or worsening"
        }
    }
    
    symptoms_lower = symptoms.lower()
    identified_symptoms = {}
    
    # Identify and analyze reported symptoms
    for symptom, info in common_symptoms.items():
        if symptom in symptoms_lower:
            identified_symptoms[symptom] = info
    
    # Generate a comprehensive single-paragraph summary in simple language
    summary = f"Based on what you told us, you have {symptoms}. "
    
    if identified_symptoms:
        summary += "Here's what we found: "
        findings = []
        warnings = []
        
        for symptom, info in identified_symptoms.items():
            findings.append(f"{symptom}")
            if 'urgent' in info['urgency'].lower() or 'immediate' in info['urgency'].lower():
                warnings.append(info['urgency'])
        
        summary += f"You have {', '.join(findings)}. "
        if warnings:
            summary += f"Important health alerts: {'; '.join(warnings)}. "
    
    # Add possible causes in simple terms
    all_causes = set()
    for info in identified_symptoms.values():
        all_causes.update(info['causes'])
    if all_causes:
        primary_causes = list(all_causes)[:3]
        summary += f"This might be caused by {', '.join(primary_causes)}. "
    
    # Add simple, clear recommendations
    summary += "What you should do: "
    recommendations = [
        "See a doctor for proper medical care",
        "Keep track of how you're feeling",
        "Get plenty of rest and drink lots of water"
    ]
    summary += ", ".join(recommendations) + ". "
    
    # Analyze follow-up information and integrate insights
    if follow_up_answers:
        summary += "Based on your additional information: "
        insights = []
        
        for answer in follow_up_answers:
            question = answer['question'].lower()
            response = answer['answer'].lower()
            
            # Analyze duration-related responses
            if 'how long' in question or 'when' in question:
                if any(word in response for word in ['day', 'week', 'month']):
                    insights.append(f"Duration: {response}")
            
            # Analyze severity-related responses
            elif 'scale' in question or 'intensity' in question:
                if any(str(i) for i in range(1, 11) if str(i) in response):
                    insights.append(f"Severity level: {response}")
            
            # Analyze pattern-related responses
            elif 'pattern' in question or 'worse' in question:
                insights.append(f"Pattern observed: {response}")
            
            # Analyze treatment-related responses
            elif 'medication' in question or 'taken' in question:
                insights.append(f"Treatment history: {response}")
        
        if insights:
            summary += ", ".join(insights) + ". "
            
            # Add severity-based recommendations
            if any('severity' in insight.lower() for insight in insights):
                if any(str(i) for i in range(7, 11) for insight in insights if str(i) in insight.lower()):
                    summary += "Given the high severity, immediate medical attention is recommended. "
                elif any(str(i) for i in range(4, 7) for insight in insights if str(i) in insight.lower()):
                    summary += "Consider consulting a healthcare provider soon. "
            
            # Add duration-based recommendations
            if any('duration' in insight.lower() for insight in insights):
                if any(word in summary.lower() for word in ['week', 'month']):
                    summary += "The persistent nature of symptoms suggests the need for medical evaluation. "
    
    # Add severity-based insights
    severity_level = "Low"
    if identified_symptoms:
        severity_scores = []
        for symptom, info in identified_symptoms.items():
            if info['severity'].lower().startswith('high'):
                severity_scores.append(3)
            elif info['severity'].lower().startswith('moderate'):
                severity_scores.append(2)
            else:
                severity_scores.append(1)
        
        avg_severity = sum(severity_scores) / len(severity_scores)
        if avg_severity > 2.5:
            severity_level = "High"
            summary += "This combination of symptoms suggests a potentially serious condition that requires immediate medical attention. "
        elif avg_severity > 1.5:
            severity_level = "Moderate"
            summary += "These symptoms warrant medical evaluation within the next 24-48 hours. "
        else:
            summary += "While these symptoms appear mild, monitor for any worsening. "
    
    # Add lifestyle and self-care recommendations
    general_recommendations = [
        "Stay hydrated by drinking plenty of water",
        "Get adequate rest",
        "Monitor your symptoms for any changes",
        "Keep a symptom diary to share with your healthcare provider"
    ]
    
    summary += "General recommendations: " + ", ".join(general_recommendations) + ". "
    
    # Add emergency warning signs based on severity
    if severity_level == "High":
        summary += "SEEK IMMEDIATE MEDICAL CARE if you experience: difficulty breathing, severe chest pain, confusion, or high fever with severe headache. "
    
    return summary.strip()

def ask_follow_up(symptoms, language="English"):
    """
    Asks follow-up questions based on reported symptoms using local processing.
    Returns a list of at least 3-4 relevant follow-up questions.
    """
    symptoms_lower = symptoms.lower()
    follow_up_questions = []
    
    # Start with a general timing question for all symptoms
    follow_up_questions.append({
        "question": "When did these symptoms first appear?",
        "image": "/static/images/medical-bot.svg",
        "animation": "fadeIn"
    })
    
    # Symptom-specific questions with severity assessment
    if "fever" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "What is your current temperature?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideIn"
            },
            {
                "question": "Have you taken any medication to reduce the fever?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceIn"
            },
            {
                "question": "Are you experiencing chills or sweating?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeIn"
            }
        ])
    if "pain" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "On a scale of 1-10, how severe is your pain?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideIn"
            },
            {
                "question": "Is the pain constant or does it come and go?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceIn"
            },
            {
                "question": "What makes the pain better or worse?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeIn"
            }
        ])
    if "cough" in symptoms_lower:
        follow_up_questions.extend([
            {
                "question": "Is your cough dry or producing mucus?",
                "image": "/static/images/medical-bot.svg",
                "animation": "slideIn"
            },
            {
                "question": "How frequently are you coughing?",
                "image": "/static/images/medical-bot.svg",
                "animation": "bounceIn"
            },
            {
                "question": "Does anything trigger or worsen your cough?",
                "image": "/static/images/medical-bot.svg",
                "animation": "fadeIn"
            }
        ])
    
    # Add general follow-up questions if we need more
    general_questions = [
        {
            "question": "Have you taken any medications for these symptoms?",
            "image": "/static/images/medical-bot.svg",
            "animation": "slideIn"
        },
        {
            "question": "Have you experienced any other related symptoms?",
            "image": "/static/images/medical-bot.svg",
            "animation": "bounceIn"
        },
        {
            "question": "Do your symptoms affect your daily activities?",
            "image": "/static/images/medical-bot.svg",
            "animation": "fadeIn"
        }
    ]
    
    while len(follow_up_questions) < 4:
        if not general_questions:
            break
        follow_up_questions.append(general_questions.pop(0))
    
    return follow_up_questions

@app.route("/chatbot", methods=["POST"])
def chatbot():
    from flask import request
    # Check authentication first
    if 'user_id' not in session:
        return jsonify({'error': 'Your session has expired. Please log in again to continue.'}), 401
        
    # Continue with chatbot logic
    request_data = request.json
    input_type = request_data.get("input_type", "text")  # 'text' or 'voice'
    language = request_data.get("language", "english").lower()
    
    # Handle initial symptoms or follow-up answers
    is_follow_up = request_data.get("is_follow_up", False)
    follow_up_answers = request_data.get("follow_up_answers", [])
    
    # Handle voice input for initial symptoms
    if input_type == "voice" and not is_follow_up:
        try:
            # Validate audio data presence
            if "audio" not in request_data:
                return jsonify({"error": "No audio data provided"}), 400
                
            audio_data = base64.b64decode(request_data.get("audio", ""))
            audio_file = io.BytesIO(audio_data)
            # Ensure the audio data is not empty and valid
            audio_content = audio_file.read()
            if not audio_content:
                return jsonify({"error": "Empty audio data. Please try recording again."}), 400
            
            # Reset buffer position for reading
            audio_file = io.BytesIO(audio_content)
            
            # Convert to AudioData object with appropriate parameters for better quality
            audio = sr.AudioData(audio_content, sample_rate=44100, sample_width=2)
            source_lang = "te-IN" if language == "telugu" else "en-IN"
            
            # Process voice input with improved error handling
            symptoms = voice_handler.process_voice_input(audio, source_lang)
            if not symptoms:
                return jsonify({"error": "Could not understand the audio. Please ensure you are in a quiet environment, speak clearly and at a normal pace. If the issue persists, try adjusting your microphone settings or using text input."}), 400
        except Exception as e:
            logging.error(f"Error processing voice input: {str(e)}")
            return jsonify({"error": "There was an issue processing your voice input. Please try again or use text input."}), 400
    else:
        symptoms = request_data.get("symptoms", "")
        if not symptoms and not is_follow_up:
            return jsonify({"error": "Please provide symptoms"}), 400
    
    # Get format type preference
    format_type = request_data.get("format_type", "detailed")
    
    # Generate initial response or process follow-up
    if not is_follow_up:
        # Generate follow-up questions
        follow_up = ask_follow_up(symptoms, language)
        
        # Translate follow-up questions if language is Telugu
        if language == "telugu":
            follow_up = voice_handler.translate_text(follow_up, "te")
        
        response = {
            "is_follow_up": True,
            "follow_up_questions": follow_up,
            "original_symptoms": symptoms,
            "format_type": format_type
        }
    else:
        # Generate final summary including follow-up answers
        original_symptoms = request_data.get("original_symptoms", "")
        format_type = request_data.get("format_type", "detailed")
        summary = generate_summary(original_symptoms, language, follow_up_answers, format_type)
        
        # Add follow-up answers to the summary
        if follow_up_answers:
            summary += "\n\nFollow-up Information:\n"
            for answer in follow_up_answers:
                summary += f"Q: {answer['question']}\nA: {answer['answer']}\n"
        
        # Translate if language is Telugu
        if language == "telugu":
            summary = voice_handler.translate_text(summary, "te")
        
        # Save the summary sheet to database
        try:
            if 'user_id' not in session:
                logging.error("No user_id in session when trying to save summary")
                return jsonify({'error': 'Failed to save consultation summary'}), 500
            
            db_path = os.path.join(os.path.dirname(__file__), 'users.db')
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            c.execute('INSERT INTO summary_sheets (user_id, symptoms, summary) VALUES (?, ?, ?)',
                      (session['user_id'], original_symptoms, summary))
            conn.commit()
            conn.close()
            
        except Exception as e:
            logging.error(f"Error saving summary: {e}")
            return jsonify({'error': 'Failed to save consultation summary'}), 500
        
        response = {
            "is_follow_up": False,
            "summary_sheet": summary
        }
    
    # Convert response to voice if requested
    if request_data.get("voice_response", False):
        try:
            lang_code = "te" if language == "telugu" else "en"
            response_text = response.get("follow_up_questions", "") if not is_follow_up else response.get("summary_sheet", "")
            audio_file = voice_handler.process_voice_output(response_text, lang_code)
            if audio_file:
                return send_file(audio_file, mimetype="audio/mp3")
        except Exception as e:
            logging.error(f"Error generating voice response: {e}")
    
    return jsonify(response)

@app.route('/set_language', methods=['POST'])
def set_language():
    language = request.form.get('language', 'english')
    session['language'] = language
    return jsonify({'status': 'success'})

@app.route('/get_greeting')
def get_greeting():
    language = session.get('language', 'english')
    greetings = {
        'english': 'Hello! I am your healthcare assistant. How can I help you today?',
        'telugu': 'నమస్కారం! నేను మీ ఆరోగ్య సహాయకుడిని. నేను మీకు ఎలా సహాయం చేయగలను?'
    }
    greeting = greetings.get(language, greetings['english'])
    
    # Convert greeting to speech if voice_handler is available
    try:
        if voice_handler:
            audio_file = voice_handler.text_to_speech(greeting, language)
            return jsonify({
                'text': greeting,
                'audio': audio_file
            })
    except Exception as e:
        logging.error(f"Error in text-to-speech conversion: {e}")
    
    return jsonify({
        'text': greeting,
        'audio': None
    })

if __name__ == '__main__':
    # Configure logging to suppress werkzeug development server warning
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    # Get debug mode from environment variable, default to True for development
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() not in ('0', 'false', 'no')
    app.debug = debug_mode
    
    # Use Flask's development server with explicit host and port
    host = '127.0.0.1'
    port = 5000
    
    # Display clear server startup message
    print(f"\nStarting Flask server in {'debug' if debug_mode else 'production'} mode")
    print(f"Server URL: http://{host}:{port}")
    print("Press CTRL+C to quit")
    
    try:
        app.run(host=host, port=port, debug=debug_mode)
    except Exception as e:
        print(f"\nError starting server: {str(e)}")
