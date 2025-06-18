import cv2
import mediapipe as mp
import pyttsx3
import time
import csv
from datetime import datetime
import numpy as np
import argparse
import os
import threading
import queue
import logging # Import the logging module
import sys

# Configure logging for model_live
logging.basicConfig(
    level=logging.DEBUG, # Set to DEBUG to capture all messages
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler("application.log", mode='a'), # Append to the same log file
        logging.StreamHandler(sys.stdout) # Also log to console
    ]
)
logger = logging.getLogger(__name__)

# Initialize text-to-speech engine for model_live
engine = None
speaker_queue = queue.Queue()

def speaker_thread_function():
    global engine
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        logger.info("Text-to-speech engine initialized in speaker thread.")
    except Exception as e:
        logger.error(f"Error initializing text-to-speech in speaker thread: {e}")
        engine = None

    while True:
        message = speaker_queue.get()
        if message is None:
            break
        if engine:
            try:
                engine.say(message)
                engine.runAndWait()
                time.sleep(0.1) # Add a small delay to ensure audio plays fully
            except Exception as e:
                logger.error(f"Voice feedback error in speaker thread: {e}")
        speaker_queue.task_done()

# Start the speaker thread once
speaker_thread = threading.Thread(target=speaker_thread_function)
speaker_thread.start()

def speak(text):
    speaker_queue.put(text)

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

# Initialize MediaPipe Pose outside main() for faster startup
pose_instance = mp_pose.Pose(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=1,
    static_image_mode=False
)

def calculate_angle(a, b, c):
    """Calculate the angle between three points"""
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
    angle = np.abs(radians*180.0/np.pi)
    
    if angle > 180.0:
        angle = 360-angle
    return angle

def calculate_calories(reps, duration):
    """Calculate calories burned based on reps only"""
    # Calories from reps (0.5 calories per rep)
    return reps * 0.5

class ExerciseState:
    def __init__(self):
        self.stage = None
        self.counter = 0
        self.last_rep_time = 0
        self.min_rep_duration = 0.2
        self.rep_angles = []
        self.is_valid_rep = False
        self.consecutive_valid_frames = 0
        self.required_valid_frames = 1
        self.last_valid_angle = None
        self.angle_threshold = 5
        self.down_threshold = 90
        self.up_threshold = 130
        self.rep_start_time = 0
        self.max_rep_duration = 15.0
        self.angle_history = []
        self.history_size = 3
        self.last_angle = None
        self.angle_direction = None
        self.start_time = time.time()
        self.last_spoken_time = 0
        self.speak_delay = 0.5

    def get_smoothed_angle(self, current_angle):
        self.angle_history.append(current_angle)
        if len(self.angle_history) > self.history_size:
            self.angle_history.pop(0)
        return sum(self.angle_history) / len(self.angle_history)

    def update_rep(self, angle, current_time):
        smoothed_angle = self.get_smoothed_angle(angle)
        
        if self.last_angle is not None:
            if smoothed_angle > self.last_angle + 2:
                self.angle_direction = "up"
            elif smoothed_angle < self.last_angle - 2:
                self.angle_direction = "down"
        self.last_angle = smoothed_angle

        self.rep_angles.append(smoothed_angle)
        if len(self.rep_angles) > 5:
            self.rep_angles.pop(0)

        if self.stage is None:
            if smoothed_angle < self.down_threshold and self.angle_direction == "down":
                self.stage = "down"
                self.is_valid_rep = True
                self.rep_start_time = current_time
        elif self.stage == "down":
            if smoothed_angle > self.up_threshold and self.angle_direction == "up":
                self.stage = "up"
        elif self.stage == "up":
            if smoothed_angle < self.down_threshold and self.angle_direction == "down":
                rep_duration = current_time - self.rep_start_time
                if (self.is_valid_rep and 
                    current_time - self.last_rep_time >= self.min_rep_duration and
                    rep_duration <= self.max_rep_duration):
                    self.counter += 1
                    self.last_rep_time = current_time
                    return self.stage, self.counter, True
                self.stage = "down"
                self.is_valid_rep = True
                self.rep_start_time = current_time

        return self.stage, self.counter, False

def process_frame(frame):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    return frame

# Global variables for workout summary
final_reps = 0
final_calories = 0.0
final_duration = 0.0

def main():
    global final_reps, final_calories, final_duration
    logger.debug("model_live.py main function started.")
    
    cap = None
    exercise_state = None
    video_writer = None

    try:
        # Create initial summary files with default values
        with open("summary.txt", "w") as f:
            f.write("Workout in progress...\n")
            f.write("Reps: 0\n")
            f.write("Calories: 0.0\n")
            f.write("Duration: 0.0s\n")
        with open("live_workout_stats.txt", "w") as f:
            f.write("Reps: 0\n")
            f.write("Calories: 0.0\n")
            f.write("Duration: 0.0s\n")

        # Initialize camera
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("Error: Could not open camera")
            # Update summary with error
            with open("summary.txt", "w") as f:
                f.write("Workout failed: Camera error\n")
                f.write("Reps: 0\n")
                f.write("Calories: 0.0\n")
                f.write("Duration: 0.0s\n")
            return # Exit if camera fails

        # Set camera properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        # Get video properties
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))

        # Create uploads directory if it doesn't exist
        os.makedirs("uploads", exist_ok=True)

        # Create video writer
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"live_workout_{timestamp}.mp4"
        video_path = os.path.join("uploads", video_filename)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(video_path, fourcc, fps, (frame_width, frame_height))

        logger.info("Camera started. Press 'q' to quit.")

        exercise_state = ExerciseState()
        last_summary_write_time = time.time()
        summary_write_interval = 1

        with pose_instance as pose:
            speak("Live workout started.")
            while True:
                ret, frame = cap.read()
                if not ret:
                    logger.error("Error: Could not read frame")
                    # Update summary with error
                    with open("summary.txt", "w") as f:
                        f.write("Workout failed: Frame read error\n")
                        f.write(f"Reps: {exercise_state.counter}\n")
                        f.write(f"Calories: {final_calories:.1f}\n")
                        f.write(f"Duration: {final_duration:.1f}s\n")
                    break

                # Write frame to video file
                if video_writer is not None:
                    video_writer.write(frame)

                # Recolor image to RGB
                image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image.flags.writeable = False

                # Make detection
                results = pose.process(image)

                # Recolor back to BGR
                image.flags.writeable = True
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                # Draw landmarks
                if results.pose_landmarks:
                    mp_drawing.draw_landmarks(image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                            mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                                            mp_drawing.DrawingSpec(color=(245, 66, 230), thickness=2, circle_radius=2))

                    # Extract landmarks for rep counting (example: bicep curls using left arm)
                    try:
                        hip = [results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_HIP.value].x,
                               results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_HIP.value].y]
                        knee = [results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_KNEE.value].x,
                                results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_KNEE.value].y]
                        ankle = [results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_ANKLE.value].x,
                                 results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_ANKLE.value].y]

                        angle = calculate_angle(hip, knee, ankle)
                        current_stage, current_counter, new_rep = exercise_state.update_rep(angle, time.time())

                        if new_rep and (time.time() - exercise_state.last_spoken_time > exercise_state.speak_delay):
                            speak(f"Rep {current_counter}")
                            exercise_state.last_spoken_time = time.time()

                    except Exception as e:
                        logger.error(f"Error processing landmarks: {e}")
                        pass

                current_duration = time.time() - exercise_state.start_time
                current_calories = calculate_calories(exercise_state.counter, current_duration)
                
                # Update global variables for final summary
                final_reps = exercise_state.counter
                final_calories = current_calories
                final_duration = current_duration

                # Display stats on frame
                cv2.putText(image, f'Reps: {exercise_state.counter}', (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(image, f'Calories: {current_calories:.1f}', (10, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(image, f'Duration: {current_duration:.1f}s', (10, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
                
                # Write live stats to file for app.py
                if time.time() - last_summary_write_time > summary_write_interval:
                    try:
                        with open("live_workout_stats.txt", "w") as f:
                            f.write(f"Reps: {exercise_state.counter}\n")
                            f.write(f"Calories: {current_calories:.1f}\n")
                            f.write(f"Duration: {current_duration:.1f}s\n")
                        # Also update summary.txt to keep it in sync
                        with open("summary.txt", "w") as f:
                            f.write("Workout in progress...\n")
                            f.write(f"Reps: {exercise_state.counter}\n")
                            f.write(f"Calories: {current_calories:.1f}\n")
                            f.write(f"Duration: {current_duration:.1f}s\n")
                        last_summary_write_time = time.time()
                    except Exception as e:
                        logger.error(f"Error writing stats files: {e}")

                cv2.imshow('Live Workout', image)

                if cv2.waitKey(10) & 0xFF == ord('q'):
                    logger.info("Quit key 'q' pressed. Exiting live workout.")
                    break
                
                # Check for stop signal from app.py
                if os.path.exists("stop_signal.txt"):
                    logger.info("Stop signal received. Exiting live workout gracefully.")
                    break

    except Exception as e:
        logger.critical(f"Unhandled exception in model_live.py main loop: {e}", exc_info=True)
        # Update summary with error
        try:
            with open("summary.txt", "w") as f:
                f.write("Workout failed: Unexpected error\n")
                f.write(f"Reps: {final_reps}\n")
                f.write(f"Calories: {final_calories:.1f}\n")
                f.write(f"Duration: {final_duration:.1f}s\n")
        except Exception as write_error:
            logger.error(f"Failed to write error summary: {write_error}")

    finally:
        logger.debug("Running final cleanup and summary writing.")
        if cap:
            cap.release()
        if video_writer:
            video_writer.release()
        cv2.destroyAllWindows()
        
        # Ensure final summary is written
        try:
            with open("summary.txt", "w") as f:
                f.write("Workout completed!\n")
                f.write(f"Reps: {final_reps}\n")
                f.write(f"Calories: {final_calories:.1f}\n")
                f.write(f"Duration: {final_duration:.1f}s\n")
            logger.info("Final summary.txt written.")

            # Also write to live_workout_stats.txt one last time to ensure consistency
            with open("live_workout_stats.txt", "w") as f:
                f.write(f"Reps: {final_reps}\n")
                f.write(f"Calories: {final_calories:.1f}\n")
                f.write(f"Duration: {final_duration:.1f}s\n")
            logger.info("Final live_workout_stats.txt written.")

        except Exception as e:
            logger.error(f"Error writing final summary files: {e}")
        
        speak(f"Workout finished. You did {final_reps} reps.")
        speaker_queue.join()  # Wait for the speaker queue to be empty
        speaker_queue.put(None) # Signal the speaker thread to exit
        speaker_thread.join() # Wait for the speaker thread to finish
        logger.info("Cleanup complete")

if __name__ == "__main__":
    main()
