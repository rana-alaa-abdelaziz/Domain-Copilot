let abortController = null;

async function startStreamingWorkflow(targetRole, subjects = []) {
    abortController = new AbortController();

    try {
        let url = `/api/stream/workflow?target_role=${encodeURIComponent(targetRole)}`;
        for (const subject of subjects) {
            url += `&user_reported_subjects=${encodeURIComponent(subject)}`;
        }

        const response = await fetch(url, {
            signal: abortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = 'message';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n');

            // Keep the last partial line in the buffer
            buffer = lines.pop();

            for (let line of lines) {
                if (line.startsWith('event:')) {
                    currentEvent = line.replace('event:', '').trim();
                } else if (line.startsWith('data:')) {
                    const dataStr = line.replace('data:', '').trim();
                    if (!dataStr) continue;
                    
                    const jsonData = JSON.parse(dataStr);
                    console.log(`[${currentEvent}]`, jsonData);

                    // Update UI or emit custom events based on the event type
                    if (currentEvent === 'connected') {
                        console.log(`Workflow started for thread ${jsonData.thread_id}`);
                    } else if (currentEvent === 'progress') {
                        console.log(`Agent ${jsonData.agent} completed!`);
                        // document.getElementById('status-log').innerText += `\nAgent ${jsonData.agent} completed!`;
                    } else if (currentEvent === 'error') {
                        console.error(`Error in ${jsonData.agent}:`, jsonData.error);
                    } else if (currentEvent === 'complete') {
                        console.log("Workflow finished successfully.");
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log("Stream successfully cancelled by client. Server-side work halted.");
        } else {
            console.error("Stream error:", error);
        }
    }
}

function cancelWorkflow() {
    if (abortController) {
        abortController.abort(); // Triggers request.is_disconnected() on FastAPI instantly
    }
}