// =========================
// WORKS PAGE - JAVASCRIPT
// =========================

class ZaloGroupsManager {
    constructor() {
        this.selectedGroupId = null;
        this.selectedGroupName = null;
        this.fetchInterval = null;
        this.lastMessageId = null;
        this.isFetching = false;
        this.newMessagesCount = 0;

        this.defaultPrefixes = ['Cần hỗ trợ', 'Hỗ trợ'];
        this.defaultServices = ['vnEdu', 'iOffice', 'vnPortal', 'Kiosk'];

        this.prefixKeywords = [...this.defaultPrefixes];
        this.serviceKeywords = [...this.defaultServices];

        this.initElements();
        this.loadParserConfig();

        if (this.loadGroupsBtn) {
            this.attachEventListeners();
        }
    }

    initElements() {
        // Groups
        this.loadGroupsBtn = document.getElementById('loadGroupsBtn');
        this.groupsContainer = document.getElementById('groupsContainer');
        this.loadingSpinner = document.getElementById('loadingSpinner');

        // Messages
        this.messagesSection = document.getElementById('messagesSection');
        this.messagesTitle = document.getElementById('messagesTitle');
        this.messagesContainer = document.getElementById('messagesContainer');
        this.statsContainer = document.getElementById('statsContainer');
        this.startFetchBtn = document.getElementById('startFetchBtn');
        this.stopFetchBtn = document.getElementById('stopFetchBtn');
        this.backBtn = document.getElementById('backBtn');

        // Stats
        this.statusValue = document.getElementById('statusValue');
        this.lastUpdateValue = document.getElementById('lastUpdateValue');
        this.newMessageCount = document.getElementById('newMessageCount');

        // Parser config
        this.prefixKeywordsInput = document.getElementById('prefixKeywordsInput');
        this.serviceKeywordsInput = document.getElementById('serviceKeywordsInput');
        this.saveParserConfigBtn = document.getElementById('saveParserConfigBtn');
        this.resetParserConfigBtn = document.getElementById('resetParserConfigBtn');
    }

    attachEventListeners() {
        if (this.loadGroupsBtn) this.loadGroupsBtn.addEventListener('click', () => this.loadGroups());
        if (this.startFetchBtn) this.startFetchBtn.addEventListener('click', () => this.startFetching());
        if (this.stopFetchBtn) this.stopFetchBtn.addEventListener('click', () => this.stopFetching());
        if (this.backBtn) this.backBtn.addEventListener('click', () => this.goBack());

        if (this.saveParserConfigBtn) {
            this.saveParserConfigBtn.addEventListener('click', () => this.saveParserConfig());
        }

        if (this.resetParserConfigBtn) {
            this.resetParserConfigBtn.addEventListener('click', () => this.resetParserConfig());
        }
    }

    // =========================
    // Parser Config
    // =========================
    loadParserConfig() {
        try {
            const savedPrefixes = localStorage.getItem('works_prefix_keywords');
            const savedServices = localStorage.getItem('works_service_keywords');

            if (savedPrefixes) {
                this.prefixKeywords = JSON.parse(savedPrefixes);
            }

            if (savedServices) {
                this.serviceKeywords = JSON.parse(savedServices);
            }
        } catch (error) {
            console.error('Load parser config error:', error);
            this.prefixKeywords = [...this.defaultPrefixes];
            this.serviceKeywords = [...this.defaultServices];
        }

        this.renderParserConfigInputs();
    }

    renderParserConfigInputs() {
        if (this.prefixKeywordsInput) {
            this.prefixKeywordsInput.value = this.prefixKeywords.join('\n');
        }

        if (this.serviceKeywordsInput) {
            this.serviceKeywordsInput.value = this.serviceKeywords.join('\n');
        }
    }

    saveParserConfig() {
        try {
            const prefixes = this.parseMultilineInput(this.prefixKeywordsInput?.value || '');
            const services = this.parseMultilineInput(this.serviceKeywordsInput?.value || '');

            this.prefixKeywords = prefixes.length ? prefixes : [...this.defaultPrefixes];
            this.serviceKeywords = services.length ? services : [...this.defaultServices];

            localStorage.setItem('works_prefix_keywords', JSON.stringify(this.prefixKeywords));
            localStorage.setItem('works_service_keywords', JSON.stringify(this.serviceKeywords));

            this.renderParserConfigInputs();
            this.refreshHighlightedMessages();
            this.showNotification('✓ Đã lưu cấu hình nhận diện', 'success');
        } catch (error) {
            console.error('Save parser config error:', error);
            this.showNotification('✗ Không lưu được cấu hình', 'error');
        }
    }

    resetParserConfig() {
        this.prefixKeywords = [...this.defaultPrefixes];
        this.serviceKeywords = [...this.defaultServices];

        localStorage.setItem('works_prefix_keywords', JSON.stringify(this.prefixKeywords));
        localStorage.setItem('works_service_keywords', JSON.stringify(this.serviceKeywords));

        this.renderParserConfigInputs();
        this.refreshHighlightedMessages();
        this.showNotification('✓ Đã khôi phục cấu hình mặc định', 'info');
    }

    parseMultilineInput(text) {
        return text
            .split('\n')
            .map(item => item.trim())
            .filter(Boolean);
    }

    // =========================
    // Load Groups
    // =========================
    loadGroups() {
        console.log('loadGroups called');
        try {
            if (!this.loadGroupsBtn) {
                console.error('loadGroupsBtn not found');
                this.showNotification('❌ Lỗi: Button không tồn tại', 'error');
                return;
            }

            this.loadGroupsBtn.disabled = true;
            if (this.loadingSpinner) this.loadingSpinner.style.display = 'inline-block';

            frappe.call({
                method: 'food_order_app.api.get_zalo_groups',
                args: {},
                callback: (response) => {
                    if (response.message && response.message.success) {
                        this.displayGroups(response.message.groups);
                        this.showNotification('✓ Tải danh sách nhóm thành công!', 'success');
                    } else {
                        const error = response.message?.error || 'Lỗi không xác định';
                        this.showNotification(`✗ Lỗi: ${typeof error === 'string' ? error : JSON.stringify(error)}`, 'error');
                        console.error('Error:', response.message);
                    }
                },
                error: (error) => {
                    console.error('API Error:', error);
                    this.showNotification('✗ Lỗi kết nối API', 'error');
                }
            });
        } catch (error) {
            console.error('Exception:', error);
            this.showNotification('✗ Lỗi hệ thống', 'error');
        } finally {
            if (this.loadGroupsBtn) this.loadGroupsBtn.disabled = false;
            if (this.loadingSpinner) this.loadingSpinner.style.display = 'none';
        }
    }

    displayGroups(groups) {
        if (!groups || groups.length === 0) {
            this.groupsContainer.innerHTML = `
                <div class="empty-state">
                    <p>😔 Không tìm thấy nhóm Zalo nào</p>
                </div>
            `;
            return;
        }

        this.groupsContainer.innerHTML = groups.map(group => `
            <div class="group-card" data-group-id="${group.group_id}" data-group-name="${this.escapeHtml(group.group_name)}">
                <div class="group-info">
                    <div class="group-name">👥 ${this.escapeHtml(group.group_name)}</div>
                    <div class="group-id">ID: ${group.group_id}</div>
                </div>
                <div class="group-icon">→</div>
            </div>
        `).join('');

        document.querySelectorAll('.group-card').forEach(card => {
            card.addEventListener('click', () => {
                const groupId = card.getAttribute('data-group-id');
                const groupName = card.getAttribute('data-group-name');
                this.selectGroup(groupId, groupName);
            });
        });
    }

    selectGroup(groupId, groupName) {
        this.selectedGroupId = groupId;
        this.selectedGroupName = groupName;
        this.lastMessageId = null;
        this.newMessagesCount = 0;
        this.messagesContainer.innerHTML = '';

        this.messagesSection.style.display = 'block';
        this.messagesTitle.textContent = `📨 Tin nhắn - ${groupName}`;
        this.startFetchBtn.style.display = 'inline-flex';
        this.stopFetchBtn.style.display = 'none';
        this.statsContainer.style.display = 'grid';
        this.statusValue.textContent = 'Dừng';
        this.statusValue.style.color = '#ff4d4f';

        setTimeout(() => {
            this.messagesSection.scrollIntoView({ behavior: 'smooth' });
        }, 100);
    }

    goBack() {
        this.stopFetching();
        this.messagesSection.style.display = 'none';
        this.selectedGroupId = null;
        this.selectedGroupName = null;
        this.lastMessageId = null;
        this.newMessagesCount = 0;
    }

    // =========================
    // Fetch Messages
    // =========================
    startFetching() {
        if (this.isFetching) return;

        this.isFetching = true;
        this.newMessagesCount = 0;
        this.startFetchBtn.style.display = 'none';
        this.stopFetchBtn.style.display = 'inline-flex';
        this.statusValue.textContent = '▶ Đang lấy tin nhắn...';
        this.statusValue.style.color = '#52c41a';

        this.fetchMessages();

        this.fetchInterval = setInterval(() => {
            this.fetchMessages();
        }, 5000);

        this.showNotification('▶ Bắt đầu lấy tin nhắn mỗi 5 giây', 'info');
    }

    stopFetching() {
        if (this.fetchInterval) {
            clearInterval(this.fetchInterval);
            this.fetchInterval = null;
        }

        this.isFetching = false;
        this.startFetchBtn.style.display = 'inline-flex';
        this.stopFetchBtn.style.display = 'none';
        this.statusValue.textContent = 'Dừng';
        this.statusValue.style.color = '#ff4d4f';

        this.showNotification('⏹ Dừng lấy tin nhắn', 'info');
    }

    fetchMessages() {
        try {
            const offset = 0;
            const count = 50;

            frappe.call({
                method: 'food_order_app.api.get_zalo_group_messages',
                args: {
                    group_id: this.selectedGroupId,
                    offset: offset,
                    count: count
                },
                callback: (response) => {
                    if (response.message && response.message.success) {
                        const messages = response.message.messages || [];
                        this.processMessages(messages);
                        this.updateLastUpdate();
                    } else {
                        const error = response.message?.error || 'Lỗi không xác định';
                        console.error('Error:', error);
                    }
                },
                error: (error) => {
                    console.error('Fetch Messages Error:', error);
                }
            });
        } catch (error) {
            console.error('Exception in fetchMessages:', error);
        }
    }

    processMessages(messages) {
        if (!messages || messages.length === 0) {
            if (!this.lastMessageId) {
                this.messagesContainer.innerHTML = `
                    <div class="empty-state">
                        <p>📭 Không có tin nhắn nào</p>
                    </div>
                `;
            }
            return;
        }

        messages.reverse();

        messages.forEach(msg => {
            const msgId = msg.message_id || msg.msg_id || msg.id;
            const isNew = !this.lastMessageId || (String(msgId) > String(this.lastMessageId));

            if (!document.querySelector(`[data-msg-id="${msgId}"]`)) {
                const messageCard = this.createMessageCard(msg, isNew);
                this.messagesContainer.prepend(messageCard);

                if (isNew) {
                    this.newMessagesCount++;
                }
            }

            if (!this.lastMessageId || String(msgId) > String(this.lastMessageId)) {
                this.lastMessageId = msgId;
            }
        });

        this.newMessageCount.textContent = this.newMessagesCount;

        const emptyState = this.messagesContainer.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        const allMessages = this.messagesContainer.querySelectorAll('.message-card');
        if (allMessages.length > 100) {
            for (let i = 100; i < allMessages.length; i++) {
                allMessages[i].remove();
            }
        }
    }

    createMessageCard(msg, isNew = false) {
        const msgId = msg.message_id || msg.msg_id || msg.id;
        const sender = this.escapeHtml(msg.from_display_name || msg.sender_name || 'Người dùng');
        const time = this.escapeHtml(msg.sent_time || this.formatTime(msg.time || msg.timestamp || msg.created_time));
        const contentRaw = msg.message || msg.text || '';
        const content = this.escapeHtml(contentRaw);

        const parsedSupport = this.parseSupportMessage(contentRaw);

        const card = document.createElement('div');
        card.className = `message-card ${isNew ? 'new' : ''} ${parsedSupport.isSupport ? 'message-support' : ''}`;
        card.setAttribute('data-msg-id', msgId);
        card.setAttribute('data-message-raw', contentRaw);

        card.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${sender}</span>
                <span class="message-time">${time}</span>
            </div>
            ${
                parsedSupport.isSupport
                    ? `
                    <div class="support-badge">🚨 Tin nhắn hỗ trợ</div>
                    <div class="support-meta">
                        <div><strong>Tiền tố:</strong> ${this.escapeHtml(parsedSupport.prefix)}</div>
                        <div><strong>Dịch vụ:</strong> ${this.escapeHtml(parsedSupport.service)}</div>
                    </div>
                    `
                    : ''
            }
            <div class="message-content">${this.nl2br(content)}</div>
            ${
                parsedSupport.isSupport
                    ? `<div class="support-detail"><strong>Nội dung cần hỗ trợ:</strong> ${this.escapeHtml(parsedSupport.content)}</div>`
                    : ''
            }
        `;

        if (parsedSupport.isSupport) {
            card.style.border = '2px solid #ff4d4f';
            card.style.background = '#fff1f0';
            card.style.fontWeight = '700';
            card.style.boxShadow = '0 8px 24px rgba(255, 77, 79, 0.18)';
        }

        return card;
    }

    parseSupportMessage(messageText) {
        const text = (messageText || '').trim();

        if (!text) {
            return {
                isSupport: false,
                prefix: '',
                service: '',
                content: ''
            };
        }

        for (const prefix of this.prefixKeywords) {
            const normalizedPrefix = prefix.trim();
            if (!normalizedPrefix) continue;

            const lowerText = text.toLowerCase();
            const lowerPrefix = normalizedPrefix.toLowerCase();

            if (!lowerText.startsWith(lowerPrefix)) {
                continue;
            }

            const remainingText = text.slice(normalizedPrefix.length).trim();
            if (!remainingText) {
                continue;
            }

            for (const service of this.serviceKeywords) {
                const normalizedService = service.trim();
                if (!normalizedService) continue;

                const lowerRemaining = remainingText.toLowerCase();
                const lowerService = normalizedService.toLowerCase();

                if (!lowerRemaining.startsWith(lowerService)) {
                    continue;
                }

                const content = remainingText.slice(normalizedService.length).trim();

                return {
                    isSupport: true,
                    prefix: normalizedPrefix,
                    service: normalizedService,
                    content: content
                };
            }
        }

        return {
            isSupport: false,
            prefix: '',
            service: '',
            content: ''
        };
    }

    refreshHighlightedMessages() {
        const messageCards = this.messagesContainer.querySelectorAll('.message-card');
        if (!messageCards.length) return;

        messageCards.forEach(card => {
            const raw = card.getAttribute('data-message-raw') || '';
            const msgId = card.getAttribute('data-msg-id');
            const headerHtml = card.querySelector('.message-header')?.outerHTML || '';
            const contentNode = card.querySelector('.message-content');
            const contentHtml = contentNode ? contentNode.innerHTML : this.escapeHtml(raw);

            const parsedSupport = this.parseSupportMessage(raw);

            card.className = card.className.replace(' message-support', '');

            card.innerHTML = `
                ${headerHtml}
                ${
                    parsedSupport.isSupport
                        ? `
                        <div class="support-badge">🚨 Tin nhắn hỗ trợ</div>
                        <div class="support-meta">
                            <div><strong>Tiền tố:</strong> ${this.escapeHtml(parsedSupport.prefix)}</div>
                            <div><strong>Dịch vụ:</strong> ${this.escapeHtml(parsedSupport.service)}</div>
                        </div>
                        `
                        : ''
                }
                <div class="message-content">${contentHtml}</div>
                ${
                    parsedSupport.isSupport
                        ? `<div class="support-detail"><strong>Nội dung cần hỗ trợ:</strong> ${this.escapeHtml(parsedSupport.content)}</div>`
                        : ''
                }
            `;

            if (parsedSupport.isSupport) {
                card.classList.add('message-support');
                card.style.border = '2px solid #ff4d4f';
                card.style.background = '#fff1f0';
                card.style.fontWeight = '700';
                card.style.boxShadow = '0 8px 24px rgba(255, 77, 79, 0.18)';
            } else {
                card.style.border = '';
                card.style.background = '';
                card.style.fontWeight = '';
                card.style.boxShadow = '';
            }

            card.setAttribute('data-msg-id', msgId);
            card.setAttribute('data-message-raw', raw);
        });
    }

    // =========================
    // Utilities
    // =========================
    updateLastUpdate() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        this.lastUpdateValue.textContent = `${hours}:${minutes}:${seconds}`;
    }

    formatTime(timestamp) {
        if (!timestamp) return '--:--:--';

        let date;
        if (typeof timestamp === 'string') {
            date = new Date(timestamp);
        } else {
            date = new Date(timestamp);
        }

        if (Number.isNaN(date.getTime())) {
            return String(timestamp);
        }

        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    nl2br(text) {
        if (!text) return '';
        return text.replace(/\n/g, '<br>');
    }

    showNotification(message, type = 'info') {
        if (frappe && frappe.show_alert) {
            frappe.show_alert({
                message: message,
                indicator: type
            });
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
}

// Initialize on Frappe ready
frappe.ready(function() {
    console.log('Frappe ready - Initializing ZaloGroupsManager');
    window.zaloManager = new ZaloGroupsManager();
    console.log('ZaloGroupsManager initialized:', window.zaloManager);
});