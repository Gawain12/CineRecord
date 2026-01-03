/**
 * Scheduled Tasks Management
 * Handles UI interactions and Socket.IO communication for scheduled sync tasks
 */

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
            this.tasks = data.tasks || [];
            this.renderTaskList();
        });

        socket.on('task_added', (data) => {
            if (data.success) {
                log('✅ 任务创建成功', 'success');
                this.loadTasks();
                this.hideTaskForm();
            } else {
                log(`❌ 创建失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_updated', (data) => {
            if (data.success) {
                log('✅ 任务更新成功', 'success');
                this.loadTasks();
                this.hideTaskForm();
            } else {
                log(`❌ 更新失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_deleted', (data) => {
            if (data.success) {
                log('✅ 任务已删除', 'success');
                this.loadTasks();
            } else {
                log(`❌ 删除失败: ${data.error}`, 'error');
            }
        });

        socket.on('task_status_changed', (data) => {
            if (data.success) {
                const action = data.paused ? '暂停' : '恢复';
                log(`✅ 任务已${action}`, 'success');
                this.loadTasks();
            }
        });
    },

    /**
     * Load tasks from server
     */
    loadTasks() {
        socket.emit('get_scheduled_tasks');
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

        formContainer.style.display = 'block';
        formContainer.scrollIntoView({ behavior: 'smooth' });
    },

    /**
     * Hide task form
     */
    hideTaskForm() {
        document.getElementById('task-form').style.display = 'none';
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
        if (confirm('确定要删除这个定时任务吗？')) {
            socket.emit('delete_scheduled_task', { task_id: taskId });
        }
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
        const emptyDiv = document.getElementById('tasks-empty');
        const tableDiv = document.getElementById('tasks-table');
        const tbody = document.getElementById('tasks-tbody');

        if (this.tasks.length === 0) {
            emptyDiv.style.display = 'block';
            tableDiv.style.display = 'none';
            return;
        }

        emptyDiv.style.display = 'none';
        tableDiv.style.display = 'block';

        // Build table rows
        tbody.innerHTML = this.tasks.map(task => {
            const platformEmoji = {
                'douban': '🎬',
                'imdb': '⭐',
                'trakt': '🎯',
                'tmdb': '🎬',
                'letterboxd': '🎞️'
            };

            const statusBadge = task.paused
                ? '<span style="background: #888; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;">⏸️ 已暂停</span>'
                : '<span style="background: var(--success); color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;">✅ 运行中</span>';

            const nextRun = task.next_run_time
                ? new Date(task.next_run_time).toLocaleString('zh-CN')
                : '--';

            return `
                <tr style="border-bottom: 1px solid var(--border);">
                    <td style="padding: 12px; font-weight: 600;">${task.name}</td>
                    <td style="padding: 12px;">
                        ${platformEmoji[task.source]} ${task.source.toUpperCase()} 
                        <span style="color: #888;">→</span> 
                        ${platformEmoji[task.target]} ${task.target.toUpperCase()}
                    </td>
                    <td style="padding: 12px; font-family: monospace; font-size: 0.85rem;">${task.schedule}</td>
                    <td style="padding: 12px;">${statusBadge}</td>
                    <td style="padding: 12px; color: #888; font-size: 0.85rem;">${nextRun}</td>
                    <td style="padding: 12px;">
                        <button class="btn btn-sm btn-outline" onclick="scheduledTasks.showTaskForm(${JSON.stringify(task).replace(/"/g, '&quot;')})" title="编辑">
                            ✏️
                        </button>
                        <button class="btn btn-sm btn-outline" onclick="scheduledTasks.toggleTaskStatus('${task.id}', ${task.paused})" title="${task.paused ? '恢复' : '暂停'}">
                            ${task.paused ? '▶️' : '⏸️'}
                        </button>
                        <button class="btn btn-sm btn-outline" onclick="scheduledTasks.deleteTask('${task.id}')" title="删除" style="color: var(--danger);">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
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
