from flask import Flask, request, jsonify, send_from_directory
import os
import subprocess
import csv
import uuid
import glob
from datetime import datetime
import pyttsx3
import threading
import time
import sys
import logging # Import the logging module
from utils import save_live_workout_data

app = Flask(__name__, static_folder='frontend', static_url_path='')
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to INFO
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('application.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize text-to-speech engine
try:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
    engine.setProperty('volume', 1.0)
except Exception as e:
    logger.error(f"Error initializing text-to-speech: {e}")
    engine = None

def speak_async(text):
    if engine:
        def run_speak():
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                logger.error(f"Voice feedback error in thread: {e}")
        threading.Thread(target=run_speak).start()

# Global variables for live workout
live_workout_process = None
live_workout_start_time = None

# Serve the homepage
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# API: Analyze uploaded video
@app.route('/analyze', methods=['POST'])
def analyze_video():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        video = request.files['video']
        if video.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}.mp4"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Clean up old files
        old_files = glob.glob(os.path.join(app.config['UPLOAD_FOLDER'], '*.mp4'))
        for old_file in old_files:
            try:
                os.remove(old_file)
            except Exception as e:
                logger.error(f"Error removing old file {old_file}: {e}")
        
        # Save the video
        video.save(save_path)

        # Run analysis model
        result = subprocess.run(['python', 'model.py', '--video_path', save_path], 
                              capture_output=True, text=True)
        
        logger.debug(f"model.py stdout:\n{result.stdout}")
        logger.debug(f"model.py stderr:\n{result.stderr}")

        if result.returncode != 0:
            return jsonify({'error': f'Analysis failed: {result.stderr}'}), 500

        # Read summary if generated
        if os.path.exists("summary.txt"):
            with open("summary.txt", "r") as f:
                lines = f.readlines()
                summary = "".join(lines)

                # Parse details from summary.txt for video analysis
                reps = 0
                calories = 0.0
                duration = 0.0
                for line in lines:
                    if "Reps:" in line:
                        try:
                            reps = int(line.split(":")[1].strip())
                        except ValueError:
                            pass # Handle cases where rep count might be missing or invalid
                    elif "Calories:" in line:
                        try:
                            calories = float(line.split(":")[1].replace('s', '').strip())
                        except ValueError:
                            pass # Handle cases where calorie count might be missing or invalid
                    elif "Duration:" in line:
                        try:
                            duration = float(line.split(":")[1].replace('s', '').strip())
                        except ValueError:
                            pass # Handle cases where duration might be missing or invalid

            # Voice feedback for uploaded video
            speak_async(summary)
            
            # Update history with parsed details
            update_history_with_details(reps, calories, duration, summary)
            
            return jsonify({
                'success': True,
                'message': summary,
                'timestamp': datetime.now().isoformat(),
                'reps': reps,
                'calories': calories,
                'duration': duration
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No analysis results found'
            }), 500

    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        return jsonify({'error': str(e)}), 500

# API: Start real-time camera workout
@app.route('/start-camera', methods=['GET'])
def start_camera():
    # Clear summary and live stats files at startup, and stop signal file
    if os.path.exists("summary.txt"):
        os.remove("summary.txt")
    if os.path.exists("live_workout_stats.txt"):
        os.remove("live_workout_stats.txt")
    if os.path.exists("stop_signal.txt"):
        os.remove("stop_signal.txt")

    global live_workout_process, live_workout_start_time
    logger.debug("start_camera endpoint hit")

    try:
        if live_workout_process is not None and live_workout_process.poll() is None: # Check if process is still running
            return jsonify({
                'success': False,
                'error': 'A workout is already in progress'
            }), 400

        # Start the live workout process in a non-blocking way
        logger.debug("Starting model_live.py subprocess...")
        live_workout_process = subprocess.Popen(['python', 'model_live.py'],
                                              stdout=sys.stdout, # Redirect to parent's stdout
                                              stderr=sys.stderr) # Redirect to parent's stderr
        
        live_workout_start_time = datetime.now()
        logger.info("Live workout started successfully.")
        
        return jsonify({
            'success': True,
            'message': 'Live workout started'
        })

    except Exception as e:
        logger.error(f"Error starting camera: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: Stop real-time camera workout
@app.route('/stop-workout', methods=['GET'])
def stop_workout():
    global live_workout_process, live_workout_start_time
    
    logger.debug("stop_workout endpoint hit")

    try:
        if live_workout_process is None or live_workout_process.poll() is not None:
            logger.warning("No workout in progress or workout already stopped.")
            return jsonify({
                'success': False,
                'error': 'No workout in progress or workout already stopped'
            }), 400

        logger.debug("Stopping workout process...")
        
        # Signal model_live.py to stop by creating a file
        with open("stop_signal.txt", "w") as f:
            f.write("STOP")
        logger.info("Sent stop signal to model_live.py")

        # Wait for process to finish with a longer timeout
        try:
            live_workout_process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            logger.warning("Process didn't terminate gracefully after signal, forcing kill...")
            live_workout_process.kill()
            live_workout_process.wait()
        
        # Clean up the stop signal file
        if os.path.exists("stop_signal.txt"):
            os.remove("stop_signal.txt")
            logger.info("Cleaned up stop_signal.txt")
        
        logger.debug("Process terminated, waiting for summary file...")
        
        # Wait for the summary file to be written, with a timeout
        summary_file_path = "summary.txt"
        wait_attempts = 6 # Total wait time 6 * 0.5 = 3 seconds
        file_found = False
        for i in range(wait_attempts):
            if os.path.exists(summary_file_path):
                logger.debug(f"Summary file found after {i*0.5} seconds.")
                file_found = True
                break
            time.sleep(0.5)
        
        summary = ""
        reps = 0
        calories = 0.0
        duration = 0.0
        status = "unknown"
        
        if file_found:
            logger.debug("Found summary.txt, reading contents...")
            with open("summary.txt", "r") as f:
                lines = f.readlines()
                summary = "".join(lines)
                logger.debug(f"Summary content: {summary}")
                
                # Check first line for status
                if lines and "Workout" in lines[0]:
                    status = lines[0].strip()
                
                for line in lines:
                    if "Reps:" in line:
                        reps = int(line.split(":")[1].strip())
                    elif "Calories:" in line:
                        calories = float(line.split(":")[1].replace('s', '').strip())
                    elif "Duration:" in line:
                        duration = float(line.split(":")[1].replace('s', '').strip())
            
            logger.debug(f"Parsed values - Status: {status}, Reps: {reps}, Calories: {calories}, Duration: {duration}")
            
            # Only update history if workout completed successfully
            if "completed" in status.lower():
                try:
                    update_history_with_details(reps, calories, duration, summary)
                    logger.info("History updated successfully")
                except Exception as e:
                    logger.error(f"Failed to update history: {str(e)}")
                    # Continue even if history update fails
            else:
                logger.warning(f"Not updating history due to workout status: {status}")
            
            return jsonify({
                'success': True,
                'message': summary,
                'status': status,
                'reps': reps,
                'calories': calories,
                'duration': duration
            })
        else:
            logger.error("Summary file not found after waiting")
            return jsonify({
                'success': False,
                'error': 'Failed to get workout summary'
            }), 500

    except Exception as e:
        logger.error(f"Error stopping workout: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        live_workout_process = None
        live_workout_start_time = None

# API: Get real-time live workout stats
@app.route('/live-stats', methods=['GET'])
def get_live_stats():
    stats = {'reps': 0, 'calories': 0.0, 'duration': 0.0}
    try:
        if os.path.exists("live_workout_stats.txt"):
            with open("live_workout_stats.txt", "r") as f:
                lines = f.readlines()
                for line in lines:
                    if "Reps:" in line:
                        stats['reps'] = int(line.split(":")[1].strip())
                    elif "Calories:" in line:
                        stats['calories'] = float(line.split(":")[1].strip())
                    elif "Duration:" in line:
                        stats['duration'] = float(line.split(":")[1].strip().replace('s',''))
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error reading live stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

def update_history(summary):
    # This function is now deprecated, use update_history_with_details instead
    pass

def update_history_with_details(reps, calories, duration, summary_text):
    try:
        timestamp = datetime.now().isoformat()
        logger.debug(f"update_history_with_details - Timestamp: {timestamp}, Reps: {reps}, Calories: {calories}, Duration: {duration}, Summary: {summary_text[:50]}...")
        # Add to history.csv
        with open("history.csv", "a", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                timestamp,
                reps,
                calories,
                duration,
                summary_text.strip() # Store the full summary text
            ])
        logger.info("Successfully wrote to history.csv")
    except Exception as e:
        logger.error(f"Error updating history: {str(e)}")

# API: Return workout history
@app.route('/history')
def get_history():
    try:
        history = []
        if os.path.exists("history.csv"):
            with open("history.csv", "r") as csvfile:
                reader = csv.reader(csvfile)
                # Attempt to skip header only if file is not empty
                try:
                    first_line = next(csvfile)
                    if not first_line.strip().startswith("timestamp"): # Adjust if your header is different
                        csvfile.seek(0) # Go back to beginning if it's not a header
                except StopIteration:
                    csvfile.seek(0) # Empty file, seek to beginning

                # Reset reader after potential seek
                csvfile.seek(0) # Ensure we read from the beginning after header check
                reader = csv.reader(csvfile)
                
                # Skip header if it exists (assuming the first row is header)
                header_skipped = False
                for row in reader:
                    if not header_skipped and row and row[0] == 'timestamp': # Simple check for header
                        header_skipped = True
                        continue

                    if len(row) >= 5: # Changed from 4 to 5 to include summary text
                        history.append({
                            'timestamp': row[0],
                            'reps': int(row[1]),
                            'calories': float(row[2]),
                            'duration': float(row[3]),
                            'summary': row[4] # Add summary text
                        })
        logger.debug(f"get_history - Returning {len(history)} entries: {history}")
        return jsonify(history)
    except Exception as e:
        logger.error(f"Error reading history: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Serve static frontend files
@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    # Ensure the UPLOAD_FOLDER exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    # Run the Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

