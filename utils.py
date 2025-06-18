import pyttsx3
import logging
from typing import Dict, Any
import csv
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize text-to-speech engine
try:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
except Exception as e:
    logger.error(f"Failed to initialize text-to-speech: {e}")
    engine = None

def speak(text: str) -> None:
    """Shared text-to-speech function"""
    if engine:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"Text-to-speech error: {e}")

def save_workout_summary(
    exercise_type: str,
    duration: float,
    calories: float,
    source: str,
    summary: Dict[str, Any]
) -> None:
    """Save workout summary to history file"""
    try:
        with open("history.csv", "a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                datetime.now().isoformat(),
                source,
                exercise_type,
                duration,
                calories,
                str(summary)
            ])
    except Exception as e:
        logger.error(f"Error saving workout summary: {e}")

# Shared exercise configuration
EXERCISE_CONFIG = {
    'squats': {
        'met_value': 5.0,
        'rep_threshold': 0.3,
        'min_rep_interval': 1.0
    },
    'pushups': {
        'met_value': 3.5,
        'rep_threshold': 0.25,
        'min_rep_interval': 1.0
    },
    'jumping_jacks': {
        'met_value': 8.0,
        'rep_threshold': 0.4,
        'min_rep_interval': 0.5
    }
}

def calculate_calories(duration_minutes: float, exercise_type: str = "squats") -> float:
    """Calculate calories burned based on duration and exercise type"""
    # MET values for different exercises (Metabolic Equivalent of Task)
    met_values = {
        "squats": 5.0,
        "pushups": 3.8,
        "lunges": 4.0,
        "plank": 2.5
    }
    
    # Default to squats if exercise type not found
    met = met_values.get(exercise_type.lower(), 5.0)
    
    # Average weight in kg (can be made configurable)
    weight_kg = 70
    
    # Calculate calories: MET * weight * duration * 1.5 (intensity factor)
    calories = (met * weight_kg * (duration_minutes / 60)) * 1.5
    return round(calories, 1)

def save_live_workout_data(reps: int, calories: float, duration: float, summary: str) -> str:
    """Save live workout data to a file in the uploads folder"""
    try:
        # Create a unique filename using timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"live_workout_{timestamp}.txt"
        filepath = os.path.join("uploads", filename)
        
        # Ensure uploads directory exists
        os.makedirs("uploads", exist_ok=True)
        
        # Write workout data to file
        with open(filepath, "w") as f:
            f.write(f"Workout Summary\n")
            f.write(f"==============\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Reps: {reps}\n")
            f.write(f"Calories: {calories:.1f}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"\nDetailed Summary:\n{summary}\n")
        
        logger.info(f"Live workout data saved to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error saving live workout data: {e}")
        return None 