let isRecording = false;
let startTime;
let pollingInterval;

// DOM Elements
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const uploadForm = document.getElementById('uploadForm');
const uploadProgress = document.getElementById('uploadProgress');
const uploadProgressBar = document.getElementById('uploadProgressBar');
const uploadProgressText = document.getElementById('uploadProgressText');
const uploadResult = document.getElementById('uploadResult');
const liveMessage = document.getElementById('liveMessage');
const liveWorkoutStats = document.getElementById('liveWorkoutStats');
const repCountElement = document.getElementById('repCount');
const calorieCountElement = document.getElementById('calorieCount');
const durationCountElement = document.getElementById('durationCount');
const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

// Event Listeners
uploadForm.addEventListener('submit', handleVideoUpload);
document.getElementById('videoFile').addEventListener('change', handleFileSelect);

// File Selection Handler
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        const label = document.querySelector('.file-input-label span');
        label.textContent = file.name;
    }
}

// Video Upload Handler
async function handleVideoUpload(event) {
    event.preventDefault();
    
    const videoFile = document.getElementById('videoFile').files[0];
    if (!videoFile) {
        showMessage(uploadResult, 'Please select a video file.', 'error');
        return;
    }

    // Check file size (100MB limit)
    if (videoFile.size > 100 * 1024 * 1024) {
        showMessage(uploadResult, 'File size too large. Maximum size is 100MB.', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('video', videoFile);

    try {
        uploadProgress.style.display = 'block';
        uploadProgressBar.style.width = '0%';
        uploadProgressText.textContent = '0%';

        const response = await fetch('/analyze', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to analyze video');
        }

        if (result.success) {
            uploadProgressBar.style.width = '100%';
            uploadProgressText.textContent = '100%';
            showMessage(uploadResult, result.message, 'success');
            loadHistory();
        } else {
            throw new Error(result.error || 'Analysis failed');
        }
        
        setTimeout(() => {
            uploadProgress.style.display = 'none';
        }, 1000);

    } catch (error) {
        console.error('Upload error:', error);
        showMessage(uploadResult, error.message || 'Error analyzing video. Please try again.', 'error');
        uploadProgress.style.display = 'none';
    }
}

// Start Live Workout
async function startCamera() {
    if (isRecording) {
        return;
    }

    try {
        // Show progress container immediately upon clicking start
        progressContainer.style.display = 'block';
        progressBar.style.width = '0%';
        progressText.textContent = '0%';

        const response = await fetch('/start-camera');
        if (!response.ok) {
            throw new Error('Failed to start camera');
        }

        const result = await response.json();
        if (result.success) {
            isRecording = true;
            startTime = Date.now();
            
            // Update UI
            startButton.style.display = 'none';
            stopButton.style.display = 'block';
            liveWorkoutStats.style.display = 'flex'; // Show live stats
            
            // Start polling for live stats
            startPollingLiveStats();
            
            showMessage(liveMessage, 'Workout started! Look for the camera window.', 'success');
        } else {
            throw new Error(result.error || 'Failed to start workout');
        }
    } catch (error) {
        console.error('Start error:', error);
        showMessage(liveMessage, error.message || 'Error starting workout. Please try again.', 'error');
        resetWorkout();
    }
}

// Stop Live Workout
async function stopWorkout() {
    if (!isRecording) {
        return;
    }

    try {
        // Stop polling for live stats
        stopPollingLiveStats();

        const response = await fetch('/stop-workout');
        if (!response.ok) {
            throw new Error('Failed to stop workout');
        }

        const result = await response.json();
        if (result.success) {
            // Explicitly set progress bar to 100% on success
            progressBar.style.width = '100%';
            progressText.textContent = '100%';

            showMessage(liveMessage, result.message || 'Workout completed!', 'success');
            loadHistory(); // Load history to show final results
        } else {
            throw new Error(result.error || 'Failed to stop workout');
        }
    } catch (error) {
        console.error('Stop error:', error);
        showMessage(liveMessage, error.message || 'Error stopping workout. Please try again.', 'error');
    } finally {
        // Reset UI elements after a short delay to allow 100% to be seen
        setTimeout(() => {
            resetWorkout();
        }, 1000); // Wait 1 second before resetting
    }
}

// Reset workout state
function resetWorkout() {
    isRecording = false;
    stopPollingLiveStats(); // Ensure polling stops

    startButton.style.display = 'block';
    stopButton.style.display = 'none';
    progressContainer.style.display = 'none';
    liveWorkoutStats.style.display = 'none'; // Hide live stats
    repCountElement.textContent = '0'; // Reset stats display
    calorieCountElement.textContent = '0.0';
    durationCountElement.textContent = '0.0';
}

// Polling for live stats
function startPollingLiveStats() {
    // Clear any existing polling interval
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }

    pollingInterval = setInterval(async () => {
        if (!isRecording) {
            stopPollingLiveStats();
            return;
        }
        try {
            const response = await fetch('/live-stats');
            if (!response.ok) {
                throw new Error('Failed to fetch live stats');
            }
            const stats = await response.json();

            repCountElement.textContent = stats.reps;
            calorieCountElement.textContent = stats.calories.toFixed(1);
            durationCountElement.textContent = stats.duration.toFixed(1);

            // Update progress bar based on duration
            let progressPercentage = Math.min(100, Math.floor(stats.duration)); 
            progressBar.style.width = progressPercentage + '%';
            progressText.textContent = `${progressPercentage}%`;

        } catch (error) {
            console.error('Live stats polling error:', error);
            // Optionally show a temporary error message, but keep polling if workout is active
        }
    }, 1000); // Poll every 1 second
}

function stopPollingLiveStats() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// History Update
function updateHistory(result) {
    const tbody = document.getElementById('historyBody');
    const row = document.createElement('tr');
    
    const timestamp = new Date(result.timestamp).toLocaleString(); // Use timestamp from backend result
    row.innerHTML = `
        <td>${timestamp}</td>
        <td>${result.reps || 0}</td>
        <td>${(result.calories || 0).toFixed(1)}</td>
        <td>${(result.duration || 0).toFixed(1)}s</td>
    `;
    
    tbody.insertBefore(row, tbody.firstChild);
}

// Load History
async function loadHistory() {
    try {
        const response = await fetch('/history');
        if (!response.ok) {
            throw new Error('Failed to load history');
        }

        const data = await response.json();
        const tbody = document.getElementById('historyBody');
        tbody.innerHTML = '';
        
        data.forEach(workout => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(workout.timestamp).toLocaleString()}</td>
                <td>${workout.reps}</td>
                <td>${workout.calories.toFixed(1)}</td>
                <td>${workout.duration.toFixed(1)}s</td>
            `;
            tbody.appendChild(row);
        });

    } catch (error) {
        console.error('History loading error:', error);
        showMessage(liveMessage, 'Error loading workout history.', 'error');
    }
}

// Message Display
function showMessage(element, message, type) {
    element.textContent = message;
    element.className = `result-message ${type}`;
    element.style.display = 'block';
    
    setTimeout(() => {
        element.style.display = 'none';
    }, 5000);
}

// Initialize
window.onload = loadHistory;
  