/**
 * Scheduled Tasks Management
 * Handles UI interactions and Socket.IO communication for scheduled sync tasks
 */

// Use global log if available, otherwise console fallback
const log = window.log || function (msg, type) {
    console.log(`[${type}] ${msg}`);
};

// Dedicated task log function - writes to the task log panel
function taskLog(msg, type = 'info') {
    const logContent = document.getElementById('task-log-content');
    const logEmpty = document.getElementById('task-log-empty');
    if (!logContent) {
        console.log(`[TaskLog] ${msg}`);
        return;
    }

    // Hide empty placeholder
    if (logEmpty) logEmpty.style.display = 'none';

    // Create log entry
    const entry = document.createElement('div');
    const now = new Date();
    const time = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    // Color based on type
    const colors = {
        'success': '#4CAF50',
        'error': '#f44336',
        'warning': '#ff9800',
        'info': '#888'
    };

    entry.style.cssText = `padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); color: ${colors[type] || colors.info};`;
    entry.innerHTML = `<span style="color: #555;">[${time}]</span> ${msg}`;

    // Insert at top (newest first)
    logContent.insertBefore(entry, logContent.firstChild);

    // Keep max 200 entries
    while (logContent.children.length > 200) {
        logContent.removeChild(logContent.lastChild);
    }
}

// Task management state
const scheduledTasks = {
    tasks: [],
    editingTaskId: null,

    /**
     * Initialize scheduled tasks UI
     */
    init() {
        this.attachEventListeners();
        this.loadTasks();
    },

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        console.log('🔗 Attaching event listeners...');

        // Tabs: task list vs logs
        document.querySelectorAll('.scheduled-tab-button').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                if (!tab) return;
                document.querySelectorAll('.scheduled-tab-button').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.scheduled-tab-panel').forEach(el => el.classList.remove('active'));
                btn.classList.add('active');
                const panel = document.getElementById(`scheduled-tab-${tab}`);
                if (panel) panel.classList.add('active');
            });
        });

        // Use event delegation for better robustness
        document.body.addEventListener('click', (e) => {
            // Add task button
            if (e.target.id === 'add-task-btn' || e.target.closest('#add-task-btn')) {
                console.log('🖱️ "New Task" button clicked');
                this.showTaskForm();
            }

            // Cancel task button
            if (e.target.id === 'cancel-task-btn' || e.target.closest('#cancel-task-btn')) {
                console.log('🖱️ "Cancel" button clicked');
                this.hideTaskForm();
            }
        });


        // Save task button
        document.getElementById('save-task-btn')?.addEventListener('click', () => {
            this.saveTask();
        });

        // Schedule preset buttons
        document.querySelectorAll('.schedule-preset').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const cron = e.target.dataset.cron;
                document.getElementById('task-cron-input').value = cron;
            });
        });

        // Platform selection validation - prevent same source/target
        const sourceSelect = document.getElementById('task-source-platform');
        const targetSelect = document.getElementById('task-target-platform');

        if (sourceSelect && targetSelect) {
            const updateTargetOptions = () => {
                const sourceValue = sourceSelect.value;
                Array.from(targetSelect.options).forEach(opt => {
                    if (opt.value === sourceValue) {
                        opt.disabled = true;
                        opt.style.color = '#666';
                    } else {
                        opt.disabled = false;
                        opt.style.color = '';
                    }
                });
                // If current target is same as source, auto-select first different option
                if (targetSelect.value === sourceValue) {
                    const firstDifferent = Array.from(targetSelect.options).find(opt => opt.value !== sourceValue);
                    if (firstDifferent) targetSelect.value = firstDifferent.value;
                }
            };

            const updateSourceOptions = () => {
                const targetValue = targetSelect.value;
                Array.from(sourceSelect.options).forEach(opt => {
                    if (opt.value === targetValue) {
                        opt.disabled = true;
                        opt.style.color = '#666';
                    } else {
                        opt.disabled = false;
                        opt.style.color = '';
                    }
                });
            };

            sourceSelect.addEventListener('change', updateTargetOptions);
            targetSelect.addEventListener('change', updateSourceOptions);

            // Initial validation
            updateTargetOptions();
            updateSourceOptions();
        }

        // Socket.IO events
        socket.on('scheduled_tasks_list', (data) => {
            scheduledTasks.tasks = data.tasks || [];
            scheduledTasks.renderTaskList();
        });

        socket.on('task_added', (data) => {
            if (data.success) {
                taskLog('✅ 任务创建成功', 'success');
                scheduledTasks.loadTasks();
                scheduledTasks.hideTaskForm();
            } else {
                taskLog(`❌ 创建失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_updated', (data) => {
            if (data.success) {
                taskLog('✅ 任务更新成功', 'success');
                scheduledTasks.loadTasks();
                scheduledTasks.hideTaskForm();
            } else {
                taskLog(`❌ 更新失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_deleted', (data) => {
            if (data.success) {
                taskLog('✅ 任务已删除', 'success');
                scheduledTasks.loadTasks();
            } else {
                taskLog(`❌ 删除失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_status_changed', (data) => {
            if (data.success) {
                const action = data.paused ? '暂停' : '恢复';
                taskLog(`✅ 任务已${action}`, 'success');
                scheduledTasks.loadTasks();
            }
        });

        // Listen for scheduled task execution logs
        socket.on('scheduled_task_log', (data) => {
            const typeMap = {
                'start': 'info',
                'success': 'success',
                'error': 'error',
                'progress': 'info'
            };
            const logType = typeMap[data.type] || 'info';
            taskLog(`[${data.task_name || 'Task'}] ${data.message}`, logType);
        });

        // Listen for persisted logs loaded from server
        socket.on('task_logs_loaded', (data) => {
            if (data.success && data.logs && data.logs.length > 0) {
                const logContent = document.getElementById('task-log-content');
                const logEmpty = document.getElementById('task-log-empty');
                if (logContent) {
                    logContent.innerHTML = ''; // Clear existing
                    data.logs.forEach(log => {
                        const entry = document.createElement('div');
                        const colors = {
                            'success': '#4CAF50',
                            'error': '#f44336',
                            'warning': '#ff9800',
                            'info': '#888',
                            'start': '#2196F3',
                            'progress': '#9C27B0'
                        };
                        entry.style.cssText = `padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); color: ${colors[log.type] || colors.info};`;
                        entry.innerHTML = `<span style="color: #555;">[${log.time_str}]</span> [${log.task_name}] ${log.message}`;
                        logContent.appendChild(entry);
                    });
                    if (logEmpty) logEmpty.style.display = 'none';
                }
            }
        });
    },

    /**
     * Load persisted task logs from server
     */
    loadTaskLogs() {
        socket.emit('get_task_logs', { limit: 200 });
    },

    /**
     * Load tasks from server
     */
    loadTasks() {
        socket.emit('get_scheduled_tasks');
        // Also load persisted logs
        this.loadTaskLogs();
    },

    /**
     * Show task form
     */
    showTaskForm(task = null) {
        const formContainer = document.getElementById('task-form');
        const nameInput = document.getElementById('task-name-input');
        const sourceSelect = document.getElementById('task-source-platform');
        const targetSelect = document.getElementById('task-target-platform');
        const cronInput = document.getElementById('task-cron-input');
        const enabledCheckbox = document.getElementById('task-enabled-checkbox');

        if (task) {
            // Edit mode
            this.editingTaskId = task.id;
            nameInput.value = task.name;
            sourceSelect.value = task.source;
            targetSelect.value = task.target;
            cronInput.value = task.schedule;
            enabledCheckbox.checked = !task.paused;
        } else {
            // Add mode
            this.editingTaskId = null;
            nameInput.value = '';
            sourceSelect.value = 'douban';
            targetSelect.value = 'imdb';
            cronInput.value = '0 2 * * *';
            enabledCheckbox.checked = true;
        }

        formContainer.style.display = 'flex';
        // Hide placeholder when form is visible
        const placeholder = document.getElementById('task-form-placeholder');
        if (placeholder) placeholder.style.display = 'none';
        formContainer.scrollIntoView({ behavior: 'smooth' });
    },

    /**
     * Hide task form
     */
    hideTaskForm() {
        document.getElementById('task-form').style.display = 'none';
        // Show placeholder when form is hidden
        const placeholder = document.getElementById('task-form-placeholder');
        if (placeholder) placeholder.style.display = 'flex';
        this.editingTaskId = null;
    },

    /**
     * Save task (add or update)
     */
    saveTask() {
        const name = document.getElementById('task-name-input').value.trim();
        const source = document.getElementById('task-source-platform').value;
        const target = document.getElementById('task-target-platform').value;
        const schedule = document.getElementById('task-cron-input').value.trim();
        const paused = !document.getElementById('task-enabled-checkbox').checked;

        // Validation
        if (!name) {
            log('❌ 请输入任务名称', 'error');
            return;
        }

        if (!schedule) {
            log('❌ 请输入Cron表达式', 'error');
            return;
        }

        if (source === target) {
            log('❌ 源平台和目标平台不能相同', 'error');
            return;
        }

        const taskData = {
            name,
            source,
            target,
            schedule,
            paused
        };

        if (this.editingTaskId) {
            // Update existing task
            socket.emit('update_scheduled_task', {
                task_id: this.editingTaskId,
                ...taskData
            });
        } else {
            // Add new task
            socket.emit('add_scheduled_task', taskData);
        }
    },

    /**
     * Delete task
     */
    deleteTask(taskId) {
        // Confirmation is handled by the UI button state
        socket.emit('delete_scheduled_task', { task_id: taskId });
    },

    /**
     * Toggle task status (pause/resume)
     */
    toggleTaskStatus(taskId, currentlyPaused) {
        socket.emit('toggle_scheduled_task', {
            task_id: taskId,
            paused: !currentlyPaused
        });
    },

    /**
     * Render task list
     */
    renderTaskList() {
        const container = document.getElementById('scheduled-tasks-list');
        const emptyDiv = document.getElementById('no-tasks-placeholder');

        if (!container) {
            console.error('Task list container not found');
            return;
        }

        // Clear existing task items (keep placeholder)
        container.querySelectorAll('.task-item').forEach(el => el.remove());

        if (this.tasks.length === 0) {
            if (emptyDiv) emptyDiv.style.display = 'block';
            return;
        }

        if (emptyDiv) emptyDiv.style.display = 'none';

        // Platform icons - prefer SVG, fallback to emoji
        const platformIcons = window.platformIcons || {};
        const platformEmoji = window.platformEmoji || {
            'douban': '🎬',
            'imdb': '⭐',
            'trakt': '🎯',
            'tmdb': '🎬',
            'letterboxd': '🎞️'
        };

        // Build task items
        this.tasks.forEach(task => {
            const item = document.createElement('div');
            item.className = 'task-item';
            item.style.cssText = 'padding: 12px 14px; border-radius: 8px; margin-bottom: 8px; background: rgba(255,255,255,0.03); cursor: pointer; display: flex; flex-direction: column; gap: 8px; transition: all 0.2s ease;';

            const statusColor = task.paused ? '#666' : '#4CAF50';
            const nextRun = task.paused
                ? '已暂停'
                : (task.next_run ? new Date(task.next_run).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' }) : 'N/A');

            // Platform icons - use SVG if available, else emoji
            let sourceIcon = platformIcons[task.source] || platformEmoji[task.source] || '📁';
            let targetIcon = platformIcons[task.target] || platformEmoji[task.target] || '📁';

            // Force larger size for images (override default 20px)
            if (sourceIcon.includes('<img')) {
                sourceIcon = sourceIcon.replace(/width:20px;height:20px;/g, 'width:36px;height:36px;');
            }
            if (targetIcon.includes('<img')) {
                targetIcon = targetIcon.replace(/width:20px;height:20px;/g, 'width:36px;height:36px;');
            }

            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 0.9rem; font-weight: 600; color: var(--text-primary); white-space: normal; overflow: visible; text-overflow: unset; line-height: 1.3; flex: 1;">
                        ${task.name || task.id}
                    </div>
                    <div style="display: flex; gap: 4px; flex-shrink: 0;">
                        <button class="btn btn-ghost btn-sm edit-task-btn" style="padding: 2px 6px; opacity: 0.6; font-size: 0.75rem;" title="编辑">✏️</button>
                        <button class="btn btn-ghost btn-sm delete-task-btn" style="padding: 2px 6px; opacity: 0.6; font-size: 0.75rem;" title="删除">🗑️</button>
                    </div>
                </div>
                <div style="display: flex; justify-content: center; align-items: center; gap: 12px; font-size: 0.78rem; color: #888;">
                    <span style="font-size: 1.8rem; line-height: 1;">${sourceIcon}</span>
                    <span style="color: #555;">→</span>
                    <span style="font-size: 1.8rem; line-height: 1;">${targetIcon}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; color: #888;">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: ${statusColor};"></span>
                        <span>${nextRun}</span>
                    </div>
                </div>
            `;

            // Hover effect
            item.addEventListener('mouseenter', () => { item.style.background = 'rgba(255,255,255,0.06)'; });
            item.addEventListener('mouseleave', () => { item.style.background = 'rgba(255,255,255,0.03)'; });

            // Edit click
            item.querySelector('.edit-task-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                scheduledTasks.showTaskForm(task);
            });

            // Delete click
            // Delete click with "Click twice to confirm" logic
            const deleteBtn = item.querySelector('.delete-task-btn');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                e.preventDefault();

                if (deleteBtn.classList.contains('confirming')) {
                    // Second click: Do delete
                    scheduledTasks.deleteTask(task.id);
                } else {
                    // First click: Show confirm state
                    deleteBtn.classList.add('confirming');
                    deleteBtn.innerHTML = '确定?';
                    deleteBtn.style.color = '#ff4d4f';
                    deleteBtn.style.background = 'rgba(255, 77, 79, 0.1)';
                    deleteBtn.style.fontWeight = 'bold';
                    deleteBtn.style.opacity = '1';
                    deleteBtn.style.width = 'auto';

                    // Reset after 3 seconds
                    setTimeout(() => {
                        if (deleteBtn.isConnected) {
                            deleteBtn.classList.remove('confirming');
                            deleteBtn.innerHTML = '🗑️';
                            deleteBtn.style.color = '';
                            deleteBtn.style.background = '';
                            deleteBtn.style.fontWeight = '';
                            deleteBtn.style.opacity = '0.6';
                            deleteBtn.style.width = '';
                        }
                    }, 3000);
                }
            });

            // Click entire item to toggle pause/resume
            item.addEventListener('click', () => {
                scheduledTasks.toggleTaskStatus(task.id, task.paused);
            });

            container.appendChild(item);
        });
    },

    /**
     * Format next run time
     */
    formatNextRun(timestamp) {
        if (!timestamp) return '--';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = date - now;

        if (diff < 0) return '准备执行';
        if (diff < 60000) return '1分钟内';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟后`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时后`;
        return `${Math.floor(diff / 86400000)}天后`;
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Wait for socket to be connected
    setTimeout(() => {
        scheduledTasks.init();
    }, 500);
});

// Expose to global scope for debugging and access from other scripts
window.scheduledTasks = scheduledTasks;
