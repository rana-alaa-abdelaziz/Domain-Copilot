let currentToken = localStorage.getItem("token");
let currentUser = null;

function parseJwt(token) {
    try {
        return JSON.parse(atob(token.split('.')[1]));
    } catch (e) {
        return null;
    }
}

function escapeHTML(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function updateAuthUI() {
    if (currentToken) {
        const payload = parseJwt(currentToken);
        currentUser = payload;
        document.getElementById("login-overlay").style.display = "none";
        document.getElementById("main-container").style.display = "block";
        document.getElementById("current-user-info").innerText = `Logged in as: ${payload.sub} (${payload.role})`;
        
        // Hide review buttons if instructor
        const reviewPanel = document.getElementById("review-panel");
        if (payload.role === "instructor" && reviewPanel) {
            const buttons = reviewPanel.querySelectorAll("button");
            buttons.forEach(btn => {
                if (btn.innerText !== "Close") {
                    btn.style.display = "none";
                }
            });
        } else if (reviewPanel) {
            const buttons = reviewPanel.querySelectorAll("button");
            buttons.forEach(btn => btn.style.display = "inline-block");
        }
        
        // Fetch and render chat history
        fetchChatHistory();
    } else {
        document.getElementById("login-overlay").style.display = "flex";
        document.getElementById("main-container").style.display = "none";
        currentUser = null;
    }
}

async function fetchChatHistory() {
    const chatBox = document.getElementById('ask-chat');
    if (!chatBox) return;
    
    try {
        const res = await apiFetch('/api/stream/history');
        if (!res.ok) return;
        
        const data = await res.json();
        chatBox.innerHTML = '';
        
        data.messages.forEach(msg => {
            const msgDiv = document.createElement('div');
            msgDiv.style.marginBottom = '15px';
            
            if (msg.role === 'user') {
                msgDiv.innerHTML = `<strong>You:</strong> <span>${escapeHTML(msg.content)}</span>`;
            } else {
                msgDiv.innerHTML = `<strong>Assistant:</strong> <div style="margin-top:5px;">${marked.parse(msg.content)}</div>`;
                if (msg.citations && msg.citations.length > 0) {
                    const citDiv = document.createElement('div');
                    citDiv.className = 'citations';
                    citDiv.style.marginTop = '10px';
                    citDiv.style.fontSize = '0.85em';
                    citDiv.style.color = '#555';
                    citDiv.innerHTML = '<strong>Citations:</strong><ul>' + 
                        msg.citations.map(c => `<li>File: ${escapeHTML(c.document_id)} (Score: ${c.score.toFixed(2)})</li>`).join('') +
                        '</ul>';
                    msgDiv.appendChild(citDiv);
                }
            }
            chatBox.appendChild(msgDiv);
        });
        chatBox.scrollTop = chatBox.scrollHeight;
    } catch (err) {
        console.error("Failed to load chat history:", err);
    }
}

async function apiFetch(url, options = {}) {
    if (!options.headers) options.headers = {};
    if (currentToken) {
        options.headers["Authorization"] = `Bearer ${currentToken}`;
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
        logout();
        throw new Error("Unauthorized");
    }
    if (res.status === 403) {
        alert("Access Denied: You do not have permission for this action.");
        throw new Error("Forbidden");
    }
    return res;
}

function logout() {
    localStorage.removeItem("token");
    currentToken = null;
    
    // Clear DOM state to prevent data leakage between sessions
    const clearEl = (id) => { const el = document.getElementById(id); if (el) el.innerHTML = ""; };
    clearEl("ask-chat");
    clearEl("wf-log");
    clearEl("ingest-result");
    clearEl("trace-result");
    
    const tasksTbody = document.querySelector("#tasks-table tbody");
    if (tasksTbody) tasksTbody.innerHTML = "";
    
    const compTbody = document.querySelector("#completed-tasks-table tbody");
    if (compTbody) compTbody.innerHTML = "";
    
    const reviewPanel = document.getElementById("review-panel");
    if (reviewPanel) reviewPanel.classList.add("hidden");
    
    updateAuthUI();
}

document.addEventListener('DOMContentLoaded', () => {
    
    // Auth Logic
    updateAuthUI();
    const loginForm = document.getElementById("login-form");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = document.getElementById("login-email").value;
            const password = document.getElementById("login-password").value;
            const errorDiv = document.getElementById("login-error");
            
            const formData = new URLSearchParams();
            formData.append("username", email);
            formData.append("password", password);
            
            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: formData.toString()
                });
                
                if (res.ok) {
                    const data = await res.json();
                    localStorage.setItem("token", data.access_token);
                    currentToken = data.access_token;
                    errorDiv.innerText = "";
                    updateAuthUI();
                } else {
                    const data = await res.json();
                    errorDiv.innerText = data.detail || "Login failed";
                }
            } catch (err) {
                errorDiv.innerText = "Network error";
            }
        });
    }

    
    // --- 1. Ingest ---
    const ingestForm = document.getElementById('ingest-form');
    const ingestResult = document.getElementById('ingest-result');
    
    ingestForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('ingest-file');
        if (!fileInput.files.length) return;
        
        const categorySelect = document.getElementById('ingest-category');
        
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('doc_category', categorySelect.value);
        
        ingestResult.textContent = "Uploading and ingesting...";
        try {
            const res = await apiFetch('/api/ingest/file', {
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

    askForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = askInput.value;
        if (!query) return;
        
        appendMessage('user', query);
        askInput.value = '';
        
        const botMsgDiv = appendMessage('bot', '...');
        botMsgDiv.textContent = '';
        
        // Use apiFetch for streaming to pass the Authorization header
        const url = `/api/stream/ask?query=${encodeURIComponent(query)}`;
        try {
            const response = await apiFetch(url, { headers: { 'Accept': 'text/event-stream' } });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                let lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line

                for (let line of lines) {
                    if (line.startsWith('data:')) {
                        const dataStr = line.replace('data:', '').trim();
                        if (!dataStr) continue;
                        
                        const jsonData = JSON.parse(dataStr);
                        
                        if (jsonData.type === "message") {
                            botMsgDiv.innerHTML += `<em>${jsonData.text}</em><br><br>`;
                        } else if (jsonData.type === "citations") {
                            if (jsonData.citations && jsonData.citations.length > 0) {
                                const citHtml = jsonData.citations.map(c => `<li>File: ${c.document_id} (Score: ${c.score.toFixed(2)})</li>`).join('');
                                botMsgDiv.innerHTML += `<strong>Citations:</strong><ul>${citHtml}</ul><hr>`;
                            }
                        } else if (jsonData.type === "token") {
                            // parse markdown on the fly or just append text (app.js originally appended then parsed)
                            const currentText = botMsgDiv.getAttribute("data-raw") || "";
                            const newText = currentText + jsonData.text;
                            botMsgDiv.setAttribute("data-raw", newText);
                            botMsgDiv.innerHTML = marked.parse(escapeHTML(newText));
                        }
                    } else if (line.startsWith('event: done')) {
                        // done
                    } else if (line.startsWith('event: error')) {
                        // Error event might follow on the next data line, or just be here
                    }
                }
            }
            localStorage.setItem('ask_chat_history', askChat.innerHTML);
        } catch (err) {
            console.error("SSE Error:", err);
            botMsgDiv.innerHTML += "<br><span style='color:red'>Stream error occurred.</span>";
        }
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

    wfForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const role = document.getElementById('wf-role').value;
        const subjectsStr = document.getElementById('wf-subjects').value;
        const subjects = subjectsStr ? subjectsStr.split(',').map(s => s.trim()) : [];
        
        wfLog.textContent = "Connecting to workflow stream...\n";
        
        let url = `/api/stream/workflow?target_role=${encodeURIComponent(role)}`;
        subjects.forEach(s => {
            url += `&user_reported_subjects=${encodeURIComponent(s)}`;
        });
        
        wfCancel.disabled = false;
        
        // Use an AbortController so we can cancel the stream
        const abortController = new AbortController();
        wfCancel.onclick = () => {
            abortController.abort();
            wfLog.textContent += "Stream cancelled by user.\n";
            wfCancel.disabled = true;
        };

        try {
            const response = await apiFetch(url, { 
                headers: { 'Accept': 'text/event-stream' },
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
                buffer = lines.pop(); // keep incomplete line

                for (let line of lines) {
                    if (line.startsWith('event:')) {
                        currentEvent = line.replace('event:', '').trim();
                    } else if (line.startsWith('data:')) {
                        const dataStr = line.replace('data:', '').trim();
                        if (!dataStr) continue;
                        
                        if (currentEvent === 'connected') {
                            wfLog.textContent += `[Connected] ${dataStr}\n`;
                        } else if (currentEvent === 'progress') {
                            wfLog.textContent += `[Progress] ${dataStr}\n`;
                        } else if (currentEvent === 'paused_for_review') {
                            const jsonData = JSON.parse(dataStr);
                            wfLog.textContent += `[Paused] ${jsonData.message} (Thread ID: ${jsonData.thread_id})\n`;
                            wfCancel.disabled = true;
                            fetchTasks(); // Auto-refresh the pending tasks table!
                            abortController.abort(); // close stream locally
                        } else if (currentEvent === 'error') {
                            wfLog.textContent += `[Error] ${dataStr}\n`;
                            wfCancel.disabled = true;
                        } else if (currentEvent === 'ping') {
                            const jsonData = JSON.parse(dataStr);
                            wfLog.textContent += `[Working...] ${jsonData.message}\n`;
                        }
                        
                        wfLog.scrollTop = wfLog.scrollHeight;
                    }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                wfLog.textContent += "Stream closed or errored.\n";
                console.error("SSE Error:", err);
            }
            wfCancel.disabled = true;
        }
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
            const res = await apiFetch('/api/reviews/pending');
            const data = await res.json();
            tableBody.innerHTML = '';
            
            data.tasks.forEach(task => {
                const tr = document.createElement('tr');
                
                let actionHtml = '';
                if (!task.assigned_reviewer_id) {
                    actionHtml = `<button onclick="claimTask('${task.thread_id}')" style="background-color: #17a2b8;">Claim</button>`;
                } else if (task.assigned_reviewer_id === currentUser.sub || task.assigned_reviewer_id === currentUser.user_id) {
                    actionHtml = `<button onclick="openReview('${task.thread_id}')">Review</button>`;
                } else {
                    actionHtml = `<button onclick="claimTask('${task.thread_id}')" style="background-color: #17a2b8;">Claim</button>`;
                }
                
                tr.innerHTML = `
                    <td>${task.thread_id}</td>
                    <td>${task.target_role}</td>
                    <td>${task.status}</td>
                    <td>
                        ${actionHtml}
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
            const res = await apiFetch('/api/reviews/completed');
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
    
    window.claimTask = async function(thread_id) {
        if (!currentUser) return;
        try {
            const res = await apiFetch(`/api/reviews/${thread_id}/assign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reviewer_id: currentUser.user_id || currentUser.sub })
            });
            if (res.ok) {
                // Refresh the table
                fetchPendingTasks();
            } else {
                alert("Failed to claim task. You may not have permissions or it might already be assigned.");
            }
        } catch(e) {
            console.error("Error claiming task:", e);
        }
    }
    
    window.openReview = async function(thread_id) {
        try {
            const res = await apiFetch(`/api/reviews/${thread_id}/pending`);
            const data = await res.json();
            
            currentReviewThreadId = thread_id;
            reviewThreadId.textContent = thread_id;
            reviewComment.value = "";
            
            // Format the artifacts nicely as HTML
            
            // Build Task Metadata Ribbon
            let priorityColor = '#ccc';
            const priority = data.review_task?.priority?.toLowerCase() || 'medium';
            if (priority === 'critical') priorityColor = '#dc3545';
            else if (priority === 'high') priorityColor = '#fd7e14';
            else if (priority === 'medium') priorityColor = '#ffc107';
            else priorityColor = '#17a2b8';

            let slaText = 'No SLA';
            let slaColor = '#555';
            if (data.review_task?.sla_due_at) {
                const dueTime = new Date(data.review_task.sla_due_at);
                const now = new Date();
                const diffHours = (dueTime - now) / (1000 * 60 * 60);
                if (diffHours < 0) {
                    slaText = '⚠️ SLA Breached';
                    slaColor = '#dc3545';
                } else if (diffHours < 24) {
                    slaText = `Due in ${Math.round(diffHours)} hours`;
                    slaColor = '#fd7e14';
                } else {
                    slaText = `Due in ${Math.round(diffHours/24)} days`;
                    slaColor = '#28a745';
                }
            }

            const assignee = data.review_task?.assigned_reviewer_id || 'Unassigned';

            let html = `<div style="display: flex; gap: 10px; margin-bottom: 20px; padding: 10px; background: #f8f9fa; border-radius: 6px; border: 1px solid #ddd; align-items: center;">
                <span style="background: ${priorityColor}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">${escapeHTML(priority.toUpperCase())}</span>
                <span style="color: ${slaColor}; font-weight: bold; font-size: 0.9em;">⏱️ ${escapeHTML(slaText)}</span>
                <span style="margin-left: auto; font-size: 0.9em; color: #444;">👤 Assigned to: <strong>${escapeHTML(assignee)}</strong></span>
            </div>`;
            
            html += `<h4>Competency Gap Report</h4>`;
            if (data.competency_gap_report && data.competency_gap_report.gaps && data.competency_gap_report.gaps.length > 0) {
                data.competency_gap_report.gaps.forEach(gap => {
                    const statusColor = gap.coverage_source === 'unverified' ? '#cc0000' : '#0066cc';
                    html += `<div style="margin-bottom: 10px; padding: 10px; background: #f0f0f0; border-left: 4px solid ${statusColor};">
                        <strong>${escapeHTML(gap.competency)}</strong><br>
                        <em>Coverage: ${escapeHTML(gap.coverage_source)} | Severity: ${escapeHTML(gap.severity)}</em><br>
                        <span style="font-size: 0.9em; color: #555;">Matched Subject: ${escapeHTML(gap.matched_user_subject || 'None')}</span>
                    </div>`;
                });
            } else {
                html += `<p>No gap report available.</p>`;
            }

            html += `<h4>Generated Assessment Questions</h4>`;
            const assessmentItems = data.assessment_report?.items || [];
            if (assessmentItems.length > 0) {
                assessmentItems.forEach((item, idx) => {
                    html += `<div style="margin-bottom: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">
                        <strong>Q${idx + 1}: ${escapeHTML(item.question_text)}</strong><br>`;
                    
                    if (item.question_type === 'multiple_choice' && item.options) {
                        html += `<ul>`;
                        item.options.forEach(opt => {
                            const isCorrect = opt === item.correct_answer;
                            html += `<li style="${isCorrect ? 'color: green; font-weight: bold;' : ''}">${escapeHTML(opt)}${isCorrect ? ' (Correct)' : ''}</li>`;
                        });
                        html += `</ul>`;
                    } else {
                        html += `<strong>Correct Answer:</strong> ${escapeHTML(item.correct_answer)}<br>`;
                    }
                    html += `<span style="font-size: 0.9em; color: #555;"><strong>Rationale:</strong> ${escapeHTML(item.rationale)}</span><br>`;
                    
                    if (item.question_type === 'multiple_choice' && item.distractor_rationales && Object.keys(item.distractor_rationales).length > 0) {
                        html += `<div style="margin-top: 8px; margin-bottom: 8px; padding: 8px; background: #fafafa; border-left: 3px solid #f39c12;">`;
                        html += `<strong style="font-size: 0.9em; color: #555;">Distractor Breakdown:</strong><ul style="margin: 4px 0 0 0; padding-left: 20px; font-size: 0.85em; color: #666;">`;
                        for (const [optKey, distRationale] of Object.entries(item.distractor_rationales)) {
                            html += `<li><strong>${escapeHTML(optKey)}:</strong> ${escapeHTML(distRationale)}</li>`;
                        }
                        html += `</ul></div>`;
                    }
                    
                    html += `<span style="font-size: 0.8em; color: #888;">Competency Tested: ${escapeHTML(item.competency)} (${escapeHTML(item.difficulty)})</span>`;
                    html += `</div>`;
                });
            } else if (data.workflow_error) {
                html += `<p style="color: #b00020;">No questions were generated. ${escapeHTML(data.workflow_error)}</p>`;
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
            const res = await apiFetch(`/api/reviews/${currentReviewThreadId}/decision`, {
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
            const res = await apiFetch(`/api/trace/${encodeURIComponent(threadId)}`);
            const data = await res.json();
            traceResult.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
            traceResult.textContent = "Error: " + e.message;
        }
    });

});
