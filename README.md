# 💪 Neuroflex - Fitness Tracker

Welcome to the **AI-Based Fitness Tracker** by Team **NeuroFlex**!  
This project uses **Computer Vision** and **AI** to analyze workouts from live camera or uploaded videos, estimate key fitness metrics, and provide real-time feedback — all accessible from a user-friendly web interface.

---

## 📌 Features

- 🎥 **Video Input**: Supports both **live camera feed** and **uploaded videos** for workout analysis.
- 🧠 **AI-Based Pose Detection**: Uses machine learning to analyze exercise form and repetitions.
- 🔊 **Voice Feedback**: Real-time audio guidance during workouts (live/video).
- 📊 **Workout Summary & History**: Logs workout data (e.g., reps, duration, type) and stores it in CSV.
- 🌐 **Frontend UI**: Clean, responsive interface built to show live feedback and past workout history.

---

## 🚀 Tech Stack

| Layer     | Tools Used                            |
|-----------|----------------------------------------|
| Backend   | Python, Flask                          |
| Frontend  | HTML, CSS, JavaScript                  |
| AI/ML     | OpenCV, MediaPipe (Pose Estimation)    |
| Storage   | CSV for workout history, TXT for summary |

---


## 🛠️ Setup Instructions

1. Clone the Repository
git clone https://github.com/Lakshyabhatt/Fitness-tracker.git
cd Fitness-tracker

2. Create a virtual environment
python -m venv venv
source venv/bin/activate

3. Install Dependencies
pip install -r requirements.txt

4. Run the Flask App
python main.py

6. Open the App
Go to your browser and open:
http://localhost:5000


📂 Project Structure

├── main.py                 # Flask backend
├── templates/
│   └── index.html          # Frontend UI
├── static/
│   ├── style.css
│   └── script.js
├── uploads/                # Uploaded videos
├── summary.txt             # Latest workout summary
├── history.csv             # Workout history logs
├── requirements.txt
└── README.md


👨‍💻 Team NeuroFlex

Lakshya Bhatt(Lead) – Backend Developer (Flask, AI integration)
Prateek Panwar – Frontend Developer (UI design & responsiveness)
Sarthak Krishali – Integrator & Tester (feature linking & QA)



