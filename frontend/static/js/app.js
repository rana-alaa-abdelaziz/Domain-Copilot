document.addEventListener('DOMContentLoaded', () => {
    
    // --- 1. Ingest ---
    const ingestForm = document.getElementById('ingest-form');
    const ingestResult = document.getElementById('ingest-result');
    
    ingestForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('ingest-file');
        if (!fileInput.files.length) return;
        
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        
        ingestResult.textContent = "Uploading and ingesting...";
        try {
            const res = await fetch('/api/ingest/file', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (data.message === "Ingestion skipped (already exists)") {
                ingestResult.textContent = data.message;
            } else {
                ingestResult.innerHTML = `<strong>${data.message}</strong><br>
                Document ID: ${data.document_id}<br>
                Chunks Extracted: ${data.chunks_extracted}<br>
                Chunks Embedded: ${data.chunks_embedded}`;
            }
        } catch (err) {
            ingestResult.textContent = "Error: " + err.message;
        }
    });

    // --- 2. Ask with Citations ---
    const askForm = document.getElementById('ask-form');
    const askInput = document.getElementById('ask-input');
    const askChat = document.getElementById('ask-chat');
    
    // Restore chat history
    const savedChat = localStorage.getItem('ask_chat_history');
    if (savedChat) {
        askChat.innerHTML = savedChat;
    }

    askForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = askInput.value;
        if (!query) return;
        
        appendMessage('user', query);
        askInput.value = '';
        
        const botMsgDiv = appendMessage('bot', '...');
        
        const eventSource = new EventSource(`/api/stream/ask?query=${encodeURIComponent(query)}`);
        
        let markdownContent = "";
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'token') {
                markdownContent += data.text;
                botMsgDiv.innerHTML = marked.parse(markdownContent);
            }
            // We receive citations but no longer render them in the chat bubble
        };
        
        eventSource.addEventListener('done', () => {
            eventSource.close();
            localStorage.setItem('ask_chat_history', askChat.innerHTML);
        });
        
        eventSource.onerror = (err) => {
            console.error("SSE Error:", err);
            eventSource.close();
        };
    });
    
    function appendMessage(sender, text) {
        const div = document.createElement('div');
        div.className = `chat-message ${sender}`;
        div.textContent = text;
        askChat.appendChild(div);
        askChat.scrollTop = askChat.scrollHeight;
        return div;
    }

    // --- 3. Run Workflow ---
    const wfForm = document.getElementById('workflow-form');
    const wfLog = document.getElementById('wf-log');
    const wfCancel = document.getElementById('wf-cancel');
    let wfEventSource = null;

    wfForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const role = document.getElementById('wf-role').value;
        const subjectsStr = document.getElementById('wf-subjects').value;
        const subjects = subjectsStr ? subjectsStr.split(',').map(s => s.trim()) : [];
        
        wfLog.textContent = "Connecting to workflow stream...\n";
        
        let url = `/api/stream/workflow?target_role=${encodeURIComponent(role)}`;
        subjects.forEach(s => {
            url += `&user_reported_subjects=${encodeURIComponent(s)}`;
        });
        
        wfEventSource = new EventSource(url);
        wfCancel.disabled = false;
        
        wfEventSource.addEventListener('connected', (event) => {
            wfLog.textContent += `[Connected] ${event.data}\n`;
            wfLog.scrollTop = wfLog.scrollHeight;
        });
        
        wfEventSource.addEventListener('progress', (event) => {
            wfLog.textContent += `[Progress] ${event.data}\n`;
            wfLog.scrollTop = wfLog.scrollHeight;
        });

        wfEventSource.addEventListener('paused_for_review', (event) => {
            const data = JSON.parse(event.data);
            wfLog.textContent += `[Paused] ${data.message} (Thread ID: ${data.thread_id})\n`;
            wfLog.scrollTop = wfLog.scrollHeight;
            wfCancel.disabled = true;
            wfEventSource.close();
            fetchTasks(); // Auto-refresh the pending tasks table!
        });

        wfEventSource.addEventListener('error', (event) => {
            // Note: SSE triggers 'error' for network drops too
            if (event.data) {
                wfLog.textContent += `[Error] ${event.data}\n`;
            } else {
                wfLog.textContent += "Stream closed or errored.\n";
            }
            wfLog.scrollTop = wfLog.scrollHeight;
            wfEventSource.close();
            wfCancel.disabled = true;
        });
    });
    
    wfCancel.addEventListener('click', () => {
        if (wfEventSource) {
            wfEventSource.close();
            wfLog.textContent += "Workflow cancelled by user.\n";
            wfCancel.disabled = true;
        }
    });

    // --- 4. Approval Gate ---
    const btnRefresh = document.getElementById('refresh-tasks');
    const tableBody = document.querySelector('#tasks-table tbody');
    const completedTableBody = document.querySelector('#completed-tasks-table tbody');
    const reviewPanel = document.getElementById('review-panel');
    const reviewContent = document.getElementById('review-content');
    const reviewThreadId = document.getElementById('review-thread-id');
    const reviewComment = document.getElementById('review-comment');
    
    let currentReviewThreadId = null;
    
    btnRefresh.addEventListener('click', fetchTasks);
    
    async function fetchTasks() {
        await fetchPendingTasks();
        await fetchCompletedTasks();
    }
    
    async function fetchPendingTasks() {
        try {
            const res = await fetch('/api/reviews/pending');
            const data = await res.json();
            tableBody.innerHTML = '';
            
            data.tasks.forEach(task => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${task.thread_id}</td>
                    <td>${task.target_role}</td>
                    <td>${task.status}</td>
                    <td>
                        <button onclick="openReview('${task.thread_id}')">Review</button>
                    </td>
                `;
                tableBody.appendChild(tr);
            });
        } catch (e) {
            console.error(e);
        }
    }
    
    async function fetchCompletedTasks() {
        try {
            const res = await fetch('/api/reviews/completed');
            const data = await res.json();
            completedTableBody.innerHTML = '';
            
            data.tasks.forEach(task => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${task.thread_id}</td>
                    <td>${task.target_role}</td>
                    <td><span style="padding: 2px 6px; border-radius: 4px; background: ${task.status === 'approved' ? '#d4edda' : task.status === 'rejected' ? '#f8d7da' : '#fff3cd'};">${task.status}</span></td>
                    <td>${task.comment || ''}</td>
                `;
                completedTableBody.appendChild(tr);
            });
        } catch (e) {
            console.error(e);
        }
    }
    
    window.openReview = async function(thread_id) {
        try {
            const res = await fetch(`/api/reviews/${thread_id}/pending`);
            const data = await res.json();
            
            currentReviewThreadId = thread_id;
            reviewThreadId.textContent = thread_id;
            reviewComment.value = "";
            
            // Format the artifacts nicely as HTML
            let html = `<h4>Competency Gap Report</h4>`;
            if (data.competency_gap_report && data.competency_gap_report.unverified_competencies) {
                data.competency_gap_report.unverified_competencies.forEach(comp => {
                    html += `<div style="margin-bottom: 10px; padding: 10px; background: #f0f0f0; border-left: 4px solid #0066cc;">
                        <strong>${comp.name}</strong><br>
                        <em>${comp.description}</em><br>
                        <span style="font-size: 0.9em; color: #555;">Rationale: ${comp.rationale}</span>
                    </div>`;
                });
            } else {
                html += `<p>No gap report available.</p>`;
            }

            html += `<h4>Generated Assessment Questions</h4>`;
            if (data.assessment_report && data.assessment_report.items) {
                data.assessment_report.items.forEach((item, idx) => {
                    html += `<div style="margin-bottom: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">
                        <strong>Q${idx + 1}: ${item.question_text}</strong><br>`;
                    
                    if (item.question_type === 'multiple_choice' && item.options) {
                        html += `<ul>`;
                        item.options.forEach(opt => {
                            const isCorrect = opt === item.correct_answer;
                            html += `<li style="${isCorrect ? 'color: green; font-weight: bold;' : ''}">${opt}${isCorrect ? ' (Correct)' : ''}</li>`;
                        });
                        html += `</ul>`;
                    } else {
                        html += `<strong>Correct Answer:</strong> ${item.correct_answer}<br>`;
                    }
                    html += `<span style="font-size: 0.9em; color: #555;"><strong>Rationale:</strong> ${item.rationale}</span><br>`;
                    html += `<span style="font-size: 0.8em; color: #888;">Competency Tested: ${item.competency} (${item.difficulty})</span>`;
                    html += `</div>`;
                });
            } else {
                html += `<p>No assessment items available.</p>`;
            }
            
            reviewContent.innerHTML = html;
            reviewPanel.classList.remove('hidden');
        } catch (e) {
            console.error(e);
            alert("Failed to fetch pending review.");
        }
    };
    
    window.closeReview = function() {
        reviewPanel.classList.add('hidden');
        currentReviewThreadId = null;
    };
    
    window.submitReview = async function(action) {
        if (!currentReviewThreadId) return;
        
        const payload = {
            action: action,
            instructor_comment: reviewComment.value
        };
        
        try {
            const res = await fetch(`/api/reviews/${currentReviewThreadId}/decision`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                alert(`Successfully processed decision: ${action}`);
                closeReview();
                fetchTasks();
            } else {
                const err = await res.json();
                alert(`Error: ${JSON.stringify(err)}`);
            }
        } catch (e) {
            console.error(e);
            alert("Failed to submit decision");
        }
    };

    // --- 5. Trace ---
    const traceForm = document.getElementById('trace-form');
    const traceResult = document.getElementById('trace-result');
    
    traceForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const threadId = document.getElementById('trace-thread-id').value;
        try {
            const res = await fetch(`/api/trace/${encodeURIComponent(threadId)}`);
            const data = await res.json();
            traceResult.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
            traceResult.textContent = "Error: " + e.message;
        }
    });

});
