document.getElementById("record-btn").addEventListener("click", function () {
    const statusElement = document.getElementById("status");
    const intervalsElement = document.getElementById("intervals");

    statusElement.innerText = "Recording... Please wait.";
    intervalsElement.innerText = "";

    fetch("/process-audio", {
        method: "POST"
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (data.tone_intervals.length > 0) {
                statusElement.innerText = "Processing completed!";
                intervalsElement.innerText = "Tone intervals: " + data.tone_intervals.join(", ");
            } else {
                statusElement.innerText = data.message || "No valid notes found.";
            }
        } else {
            statusElement.innerText = "Error: " + data.error;
        }
    })
    .catch(error => {
        statusElement.innerText = "Error: " + error.message;
    });
});