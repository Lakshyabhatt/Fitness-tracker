import cv2
import mediapipe as mp
import time
import csv
from datetime import datetime
import argparse
import numpy as np
import pyttsx3
import threading
import queue

# Initialize text-to-speech engine for model.py
engine = None
speaker_queue = queue.Queue()

def speaker_thread_function():
    global engine
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        print("Text-to-speech engine initialized in model.py speaker thread.")
    except Exception as e:
        print(f"Error initializing text-to-speech in model.py speaker thread: {e}")
        engine = None

    while True:
        message = speaker_queue.get()
        if message is None: 
            break
        if engine:
            try:
                engine.say(message)
                engine.runAndWait()
            except Exception as e:
                print(f"Voice feedback error in model.py speaker thread: {e}")
        speaker_queue.task_done()

speaker_thread = threading.Thread(target=speaker_thread_function, daemon=True)
speaker_thread.start()

def speak(text):
    speaker_queue.put(text)

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

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

def calculate_calories(reps, duration_seconds):
    # This is a very rough estimation. Real calorie calculation is complex.
    calories_per_rep = 0.3 # Example: 0.3 calories per rep
    base_metabolic_rate_per_sec = 0.005 # Very small value for continuous burn
    total_calories = (reps * calories_per_rep) + (duration_seconds * base_metabolic_rate_per_sec)
    return total_calories

# Corrected ExerciseState class (from model_live.py)
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

def main(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception(f"Error opening video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        exercise_state = ExerciseState()
        frame_count = 0
        processed_frames = 0
        
        speak("Analyzing video. Please wait.")

        with mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=1,
            static_image_mode=False
        ) as pose:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                processed_frames += 1

                # Resize frame for better display
                frame = cv2.resize(frame, (640, 480))
                
                image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image.flags.writeable = False
                results = pose.process(image)
                image.flags.writeable = True
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                if results.pose_landmarks:
                    mp_drawing.draw_landmarks(image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                            mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                                            mp_drawing.DrawingSpec(color=(245, 66, 230), thickness=2, circle_radius=2))

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

                        # Display rep count and stage
                        cv2.putText(image, f'Reps: {current_counter}', (10, 30),
                                  cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.putText(image, f'Stage: {current_stage}', (10, 70),
                                  cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                    except Exception as e:
                        pass

                # Show the frame
                cv2.imshow('Workout Analysis', image)
                
                # Calculate frame delay based on video FPS
                frame_delay = int(1000/fps)
                if cv2.waitKey(frame_delay) & 0xFF == ord('q'):
                    break

        cap.release()
        cv2.destroyAllWindows()

        final_calories = calculate_calories(exercise_state.counter, duration)

        with open("summary.txt", "w") as f:
            f.write(f"Workout completed!\n")
            f.write(f"Reps: {exercise_state.counter}\n")
            f.write(f"Calories: {final_calories:.1f}\n")
            f.write(f"Duration: {duration:.1f}s\n")

        # Give detailed voice feedback
        speak(f"Workout analysis complete. You did {exercise_state.counter} reps.")
        time.sleep(1)  # Small pause between messages
        speak(f"Estimated calories burned: {final_calories:.1f}")
        time.sleep(1)  # Small pause between messages
        speak(f"Workout duration: {duration:.1f} seconds")

    except Exception as e:
        print(f"Error in main: {e}")
        speak("An error occurred during video analysis.")
        with open("summary.txt", "w") as f:
            f.write("Workout completed!\n")
            f.write("Reps: 0\n")
            f.write("Calories: 0.0\n")
            f.write("Duration: 0.0s\n")
    finally:
        # Ensure cap and windows are released even if an error occurs mid-process
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run workout analysis on a video file.')
    parser.add_argument('--video_path', type=str, help='Path to the video file.')
    args = parser.parse_args()
    main(args.video_path)

    
        
