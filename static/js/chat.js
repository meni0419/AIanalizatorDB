class DeepSeekChat {
    constructor() {
        this.attachedFiles = [];
        this.currentSessionId = null;
        this.sessions = [];
        this.initializeElements();
        this.bindEvents();
        this.loadStatus();
        this.loadSessions();
        this.loadHistory();
        this.initializeTheme();
        this.initializeSidebarState();
    }

    initializeSidebarState() {
        const savedState = localStorage.getItem('sidebarState');
        // По умолчанию сайдбар открыт
        if (savedState === 'closed') {
            this.elements.sidebar.classList.remove('open');
        } else {
            this.elements.sidebar.classList.add('open');
        }
    }

    initializeElements() {
        this.elements = {
            messageInput: document.getElementById('message-input'),
            sendBtn: document.getElementById('send-btn'),
            attachBtn: document.getElementById('attach-btn'),
            fileInput: document.getElementById('file-input'),
            attachedFilesContainer: document.getElementById('attached-files'),
            messages: document.getElementById('messages'),
            loading: document.getElementById('loading'),
            preloadBtn: document.getElementById('preload-btn'),
            statusBtn: document.getElementById('status-btn'),
            logoutBtn: document.getElementById('logout-btn'),
            modelStatus: document.getElementById('model-status'),
            statusModal: document.getElementById('status-modal'),
            statusInfo: document.getElementById('status-info'),

            // Элементы сайдбара
            sidebar: document.getElementById('sidebar'),
            sidebarToggle: document.getElementById('sidebar-toggle'),
            sidebarToggleMain: document.getElementById('sidebar-toggle-main'),
            newChatBtn: document.getElementById('new-chat-btn'),
            clearHistoryBtn: document.getElementById('clear-history-btn'),
            sessionsList: document.getElementById('sessions-list'),
            themeToggle: document.getElementById('theme-toggle')
        };
    }

    bindEvents() {
        // Основные события
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.elements.attachBtn.addEventListener('click', () => {
            this.elements.fileInput.click();
        });
        this.elements.fileInput.addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });

        this.elements.preloadBtn.addEventListener('click', () => this.preloadModel());
        this.elements.statusBtn.addEventListener('click', () => this.showStatus());
        this.elements.logoutBtn.addEventListener('click', () => {
            window.location.href = '/logout';
        });

        this.elements.statusModal.addEventListener('click', (e) => {
            if (e.target === this.elements.statusModal || e.target.classList.contains('close')) {
                this.elements.statusModal.classList.add('hidden');
            }
        });

        // События сайдбара
        this.elements.sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        this.elements.sidebarToggleMain.addEventListener('click', () => this.toggleSidebar());
        this.elements.newChatBtn.addEventListener('click', () => this.newChat());
        this.elements.clearHistoryBtn.addEventListener('click', () => this.clearHistory());
        this.elements.themeToggle.addEventListener('click', () => this.toggleTheme());

        this.setupDragAndDrop();
    }

    toggleSidebar() {
        this.elements.sidebar.classList.toggle('open');
        const isOpen = this.elements.sidebar.classList.contains('open');
        localStorage.setItem('sidebarState', isOpen ? 'open' : 'closed');

        // Обновляем иконку
        this.elements.sidebarToggle.textContent = isOpen ? '←' : '→';
    }

    async newChat() {
        try {
            const response = await fetch('/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();

            if (data.success) {
                this.currentSessionId = data.session_id;
                this.elements.messages.innerHTML = '';
                this.loadSessions();
                this.showMessage('Новый чат создан', 'success');
            } else {
                this.showMessage('Ошибка создания чата: ' + data.error, 'error');
            }
        } catch (error) {
            this.showMessage('Ошибка создания чата: ' + error.message, 'error');
        }
    }

    async loadSessions() {
        try {
            const response = await fetch('/get_sessions');
            const data = await response.json();

            if (data.success) {
                this.sessions = data.sessions;
                this.renderSessions();
            }
        } catch (error) {
            console.error('Ошибка загрузки сессий:', error);
        }
    }

    renderSessions() {
        this.elements.sessionsList.innerHTML = '';

        this.sessions.forEach(session => {
            const sessionElement = document.createElement('div');
            sessionElement.className = 'session-item';
            if (session.session_id === this.currentSessionId) {
                sessionElement.classList.add('active');
            }

            // Исправлено: убрано дублирование
            sessionElement.innerHTML = `
                <div class="session-header">
                    <div class="session-title">${session.title}</div>
                    <button class="session-delete">❌</button>
                </div>
                <div class="session-date">${new Date(session.updated_at).toLocaleDateString()}</div>
            `;

            // Добавляем обработчики событий
            const deleteBtn = sessionElement.querySelector('.session-delete');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteSession(session.session_id);
            });

            sessionElement.addEventListener('click', () => this.loadSession(session.session_id));
            this.elements.sessionsList.appendChild(sessionElement);
        });
    }

    async deleteSession(sessionId) {
    if (!confirm('Вы уверены, что хотите удалить этот диалог?')) return;

    try {
        const response = await fetch(`/delete_session/${sessionId}`, {
            method: 'DELETE'
        });

        // Проверяем статус ответа
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Проверяем, что ответ - JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            throw new Error('Сервер вернул не JSON ответ');
        }

        const data = await response.json();

        if (data.success) {
            // Если удалили текущий активный диалог, создаем новый
            if (sessionId === this.currentSessionId) {
                await this.newChat();
            }

            this.loadSessions();
            this.showMessage('Диалог удален', 'success');
        } else {
            this.showMessage('Ошибка удаления: ' + data.error, 'error');
        }

    } catch (error) {
        console.error('Delete session error:', error);
        this.showMessage('Ошибка удаления: ' + error.message, 'error');
    }
}

    async loadSession(sessionId) {
        try {
            const response = await fetch(`/load_session/${sessionId}`);
            const data = await response.json();

            if (data.success) {
                this.currentSessionId = sessionId;
                this.elements.messages.innerHTML = '';

                data.messages.forEach(msg => {
                    this.addMessage(msg.role, msg.content, msg.files || [], msg.thinking, msg.response_time);
                });

                this.renderSessions();
                this.scrollToBottom();
            }
        } catch (error) {
            this.showMessage('Ошибка загрузки сессии: ' + error.message, 'error');
        }
    }

    initializeTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-theme');
            this.elements.themeToggle.textContent = '☀️';
        }
    }

    toggleTheme() {
        document.body.classList.toggle('dark-theme');
        const isDark = document.body.classList.contains('dark-theme');
        this.elements.themeToggle.textContent = isDark ? '☀️' : '🌙';
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    }

    async sendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message && this.attachedFiles.length === 0) return;

        // ВАЖНО: Сохраняем файлы ПЕРЕД очисткой
        const attachedFiles = [...this.attachedFiles];

        // СРАЗУ добавляем сообщение пользователя в чат
        this.addMessage('user', message, attachedFiles.map(f => f.name));

        // Теперь очищаем поле ввода и файлы
        this.elements.messageInput.value = '';
        this.clearAttachedFiles();

        this.elements.loading.classList.remove('hidden');
        this.elements.sendBtn.disabled = true;

        try {
            const formData = new FormData();
            formData.append('message', message);
            formData.append('session_id', this.currentSessionId || '');

            // Добавляем сохраненные файлы
            attachedFiles.forEach(file => {
                formData.append('files', file);
            });

            // Отправляем асинхронный запрос
            const response = await fetch('/send_message_async', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                // Показываем индикатор ожидания AI
                const waitingMessageId = this.addWaitingMessage();

                // Начинаем polling статуса
                this.pollOperationStatus(data.operation_id, waitingMessageId);

            } else {
                this.showMessage('Ошибка: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Send message error:', error);
            this.showMessage('Ошибка отправки сообщения: ' + error.message, 'error');
        } finally {
            this.elements.loading.classList.add('hidden');
            this.elements.sendBtn.disabled = false;
        }
    }

    addWaitingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant waiting';

        messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-role">🤖 DeepSeek</span>
            <span class="message-time">${new Date().toLocaleTimeString()}</span>
        </div>
        <div class="message-content">
            <div class="ai-thinking">
                🧠 Думаю... <span class="dots"></span>
                <div class="progress-info">Время: <span class="elapsed-time">0с</span></div>
            </div>
        </div>
    `;

        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();

        return messageDiv;
    }


    async pollOperationStatus(operationId, waitingMessageElement) {
        const startTime = Date.now();

        const poll = async () => {
            try {
                const response = await fetch(`/operation_status/${operationId}`);
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Ошибка получения статуса');
                }

                // Обновляем время ожидания
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                const elapsedTimeElement = waitingMessageElement.querySelector('.elapsed-time');
                if (elapsedTimeElement) {
                    const minutes = Math.floor(elapsed / 60);
                    const seconds = elapsed % 60;
                    elapsedTimeElement.textContent = minutes > 0 ? `${minutes}м ${seconds}с` : `${seconds}с`;
                }

                if (data.status === 'completed') {
                    // Убираем сообщение ожидания
                    waitingMessageElement.remove();

                    // Добавляем ТОЛЬКО ответ ассистента (сообщение пользователя уже показано)
                    const result = data.result;
                    this.addMessage('assistant', result.response, [], result.thinking, result.response_time);
                    this.currentSessionId = result.session_id;
                    this.loadSessions();

                } else if (data.status === 'error') {
                    waitingMessageElement.remove();
                    this.showMessage('Ошибка AI: ' + data.error, 'error');

                } else {
                    // Продолжаем polling через 2 секунды
                    setTimeout(poll, 2000);
                }

            } catch (error) {
                console.error('Polling error:', error);
                waitingMessageElement.remove();
                this.showMessage('Ошибка получения ответа: ' + error.message, 'error');
            }
        };

        // Начинаем polling
        poll();
    }

    addMessage(role, content, files = [], thinking = '', responseTime = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        let filesHtml = '';
        if (files && files.length > 0) {
            filesHtml = `<div class="message-files">📎 Файлы: ${files.join(', ')}</div>`;
        }

        let thinkingHtml = '';
        if (thinking) {
            thinkingHtml = `<div class="thinking">${thinking}</div>`;
        }

        let timeHtml = '';
        if (responseTime) {
            timeHtml = `<div class="response-time">⏱️ ${responseTime.toFixed(2)}с</div>`;
        }

        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-role">${role === 'user' ? '👤 Вы' : '🤖 DeepSeek'}</span>
                <span class="message-time">${new Date().toLocaleTimeString()}</span>
            </div>
            ${filesHtml}
            ${thinkingHtml}
            <div class="message-content">${this.formatMessage(content)}</div>
            ${timeHtml}
        `;

        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    formatMessage(content) {
        return marked.parse(content);
    }

    clearAttachedFiles() {
        this.attachedFiles = [];
        this.elements.attachedFilesContainer.innerHTML = '';
    }

    scrollToBottom() {
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    showMessage(message, type = 'info') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `alert alert-${type}`;
        messageDiv.textContent = message;

        document.body.appendChild(messageDiv);

        setTimeout(() => {
            messageDiv.remove();
        }, 3000);
    }

    async preloadModel() {
        this.elements.preloadBtn.disabled = true;

        // Показываем прогресс загрузки
        let dots = 0;
        const progressInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            this.elements.preloadBtn.textContent = 'Загрузка модели' + '.'.repeat(dots);
        }, 1000);

        try {
            // Добавляем очень большой таймаут для загрузки модели - 2 часа
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 7200000); // 2 часа

            console.log('Начинаю загрузку модели с таймаутом 2 часа...');
            this.showMessage('Начата загрузка модели. Это может занять до 2 часов...', 'info');

            const response = await fetch('/preload_model', {
                method: 'POST',
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            clearInterval(progressInterval);

            if (!response.ok) {
                if (response.status === 504) {
                    throw new Error('Модель не успела загрузиться за 2 часа. Возможно, модель слишком большая для CPU.');
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                this.elements.modelStatus.textContent = '🟢 Загружена';
                this.elements.modelStatus.className = 'status loaded';
                this.showMessage('Модель успешно загружена!', 'success');
            } else {
                this.showMessage('Ошибка загрузки модели: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Preload model error:', error);
            clearInterval(progressInterval);

            if (error.name === 'AbortError') {
                this.showMessage('Загрузка модели прервана по таймауту (2 часа). Попробуйте загрузить модель меньшего размера или дождитесь завершения загрузки.', 'error');
            } else {
                this.showMessage('Ошибка загрузки модели: ' + error.message, 'error');
            }
        } finally {
            clearInterval(progressInterval);
            this.elements.preloadBtn.disabled = false;
            this.elements.preloadBtn.textContent = 'Загрузить модель';
        }
    }


    async showStatus() {
        try {
            const response = await fetch('/get_status');
            const data = await response.json();

            if (data.success) {
                this.elements.statusInfo.innerHTML = `
                    <div class="status-item">
                        <strong>Модель:</strong> ${data.model_name}
                    </div>
                    <div class="status-item">
                        <strong>Статус:</strong> ${data.model_loaded ? '🟢 Загружена' : '🔴 Не загружена'}
                    </div>
                    <div class="status-item">
                        <strong>Контекст:</strong> ${data.context_tokens} / ${data.max_tokens} токенов
                    </div>
                    <div class="status-item">
                        <strong>Использование:</strong> ${data.context_usage}%
                    </div>
                `;
                this.elements.statusModal.classList.remove('hidden');
            }
        } catch (error) {
            this.showMessage('Ошибка получения статуса: ' + error.message, 'error');
        }
    }

    async loadHistory() {
        try {
            const response = await fetch('/get_history');
            const data = await response.json();

            if (data.success && data.messages) {
                this.elements.messages.innerHTML = '';
                data.messages.forEach(msg => {
                    this.addMessage(msg.role, msg.content, msg.files || [], msg.thinking, msg.response_time);
                });
                this.scrollToBottom();
            }
        } catch (error) {
            console.error('Ошибка загрузки истории:', error);
        }
    }

    async loadStatus() {
        try {
            const response = await fetch('/get_status');
            const data = await response.json();

            if (data.success) {
                this.elements.modelStatus.textContent = data.model_loaded ? '🟢 Загружена' : '🔴 Не загружена';
                this.elements.modelStatus.className = `status ${data.model_loaded ? 'loaded' : 'not-loaded'}`;
                this.elements.preloadBtn.disabled = data.model_loaded;
            }
        } catch (error) {
            console.error('Ошибка загрузки статуса:', error);
        }
    }

    async clearHistory() {
        if (!confirm('Вы уверены, что хотите очистить историю чата?')) return;

        try {
            const response = await fetch('/clear_history', {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.elements.messages.innerHTML = '';
                this.showMessage('История очищена', 'success');
            }
        } catch (error) {
            this.showMessage('Ошибка очистки истории: ' + error.message, 'error');
        }
    }

    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        this.attachedFiles = [...this.attachedFiles, ...files];
        this.renderAttachedFiles();
    }

    renderAttachedFiles() {
        this.elements.attachedFilesContainer.innerHTML = '';
        this.attachedFiles.forEach((file, index) => {
            const fileDiv = document.createElement('div');
            fileDiv.className = 'attached-file';
            fileDiv.innerHTML = `
                <span>📄 ${file.name}</span>
                <span class="remove" onclick="chat.removeFile(${index})">×</span>
            `;
            this.elements.attachedFilesContainer.appendChild(fileDiv);
        });
    }

    removeFile(index) {
        this.attachedFiles.splice(index, 1);
        this.renderAttachedFiles();
    }

    setupDragAndDrop() {
        const container = this.elements.messages;

        container.addEventListener('dragover', (e) => {
            e.preventDefault();
            container.classList.add('drag-over');
        });

        container.addEventListener('dragleave', (e) => {
            if (!container.contains(e.relatedTarget)) {
                container.classList.remove('drag-over');
            }
        });

        container.addEventListener('drop', (e) => {
            e.preventDefault();
            container.classList.remove('drag-over');

            const files = Array.from(e.dataTransfer.files);
            this.attachedFiles = [...this.attachedFiles, ...files];
            this.renderAttachedFiles();
        });
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.chat = new DeepSeekChat();
});