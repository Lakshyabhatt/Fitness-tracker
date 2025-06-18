import pyttsx3

def speak_text(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # Speed of speech
    engine.setProperty('volume', 1)  # Volume (0.0 to 1.0)
    engine.say(text)
    engine.runAndWait()

if __name__ == "__main__":
    try:
        with open("summary.txt", "r") as f:
            summary = f.read()
        print("Speaking summary:", summary)
        speak_text(summary)
    except FileNotFoundError:
        print("summary.txt not found. Please run the video analysis first.")
