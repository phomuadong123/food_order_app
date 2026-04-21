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
        this.hasLoadedInitialMessages = false;

        this.defaultServices = ['vnEdu', 'iOffice', 'vnPortal', 'Kiosk'];
        this.serviceKeywords = [...this.defaultServices];

        this.acknowledgeText = 'Yêu cầu của bạn đã được tiếp nhận và đang được cán bộ xử lý.';

        this.initElements();
        this.loadParserConfig();

        if (this.loadGroupsBtn) {
            this.attachEventListeners();
        }
    }

    initElements() {
        this.loadGroupsBtn = document.getElementById('loadGroupsBtn');
        this.groupsContainer = document.getElementById('groupsContainer');
        this.loadingSpinner = document.getElementById('loadingSpinner');

        this.messagesSection = document.getElementById('messagesSection');
        this.messagesTitle = document.getElementById('messagesTitle');
        this.messagesContainer = document.getElementById('messagesContainer');
        this.statsContainer = document.getElementById('statsContainer');
        this.startFetchBtn = document.getElementById('startFetchBtn');
        this.stopFetchBtn = document.getElementById('stopFetchBtn');
        this.backBtn = document.getElementById('backBtn');

        this.statusValue = document.getElementById('statusValue');
        this.lastUpdateValue = document.getElementById('lastUpdateValue');
        this.newMessageCount = document.getElementById('newMessageCount');

        this.serviceKeywordsInput = document.getElementById('serviceKeywordsInput');
        this.saveParserConfigBtn = document.getElementById('saveParserConfigBtn');
        this.resetParserConfigBtn = document.getElementById('resetParserConfigBtn');
    }

    attachEventListeners() {
        if (this.loadGroupsBtn) this.loadGroupsBtn.addEventListener('click', () => this.loadGroups());
        if (this.startFetchBtn) this.startFetchBtn.addEventListener('click', () => this.startFetching());
        if (this.stopFetchBtn) this.stopFetchBtn.addEventListener('click', () => this.stopFetching());
        if (this.backBtn) this.backBtn.addEventListener('click', () => this.goBack());
        if (this.saveParserConfigBtn) this.saveParserConfigBtn.addEventListener('click', () => this.saveParserConfig());
        if (this.resetParserConfigBtn) this.resetParserConfigBtn.addEventListener('click', () => this.resetParserConfig());
    }

    // =========================
    // Parser Config
    // =========================
    loadParserConfig() {
        try {
            const savedServices = localStorage.getItem('works_service_keywords');
            if (savedServices) {
                this.serviceKeywords = JSON.parse(savedServices);
            }
        } catch (error) {
            console.error('Load parser config error:', error);
            this.serviceKeywords = [...this.defaultServices];
        }

        this.renderParserConfigInputs();
    }

    renderParserConfigInputs() {
        if (this.serviceKeywordsInput) {
            this.serviceKeywordsInput.value = this.serviceKeywords.join('\n');
        }
    }

    saveParserConfig() {
        try {
            const services = this.parseMultilineInput(this.serviceKeywordsInput?.value || '');
            this.serviceKeywords = services.length ? services : [...this.defaultServices];
            localStorage.setItem('works_service_keywords', JSON.stringify(this.serviceKeywords));
            this.renderParserConfigInputs();
            this.refreshHighlightedMessages();
            this.showNotification('✓ Đã lưu cấu hình dịch vụ', 'success');
        } catch (error) {
            console.error('Save parser config error:', error);
            this.showNotification('✗ Không lưu được cấu hình', 'error');
        }
    }

    resetParserConfig() {
        this.serviceKeywords = [...this.defaultServices];
        localStorage.setItem('works_service_keywords', JSON.stringify(this.serviceKeywords));
        this.renderParserConfigInputs();
        this.refreshHighlightedMessages();
        this.showNotification('✓ Đã khôi phục mặc định', 'info');
    }

    parseMultilineInput(text) {
        return text
            .split('\n')
            .map(item => item.trim())
            .filter(Boolean);
    }

    // =========================
    // Groups
    // =========================
    loadGroups() {
        try {
            if (!this.loadGroupsBtn) {
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
                    }
                },
                error: () => {
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
        this.hasLoadedInitialMessages = false;
        this.messagesContainer.innerHTML = '';

        this.messagesSection.style.display = 'block';
        this.messagesTitle.textContent = `📨 Tin nhắn - ${groupName}`;
        this.startFetchBtn.style.display = 'inline-flex';
        this.stopFetchBtn.style.display = 'none';
        this.statsContainer.style.display = 'grid';
        this.statusValue.textContent = 'Dừng';
        this.statusValue.style.color = '#ff4d4f';
        this.newMessageCount.textContent = '0';

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
        this.hasLoadedInitialMessages = false;
        this.messagesContainer.innerHTML = '';
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
    }

    fetchMessages() {
        try {
            frappe.call({
                method: 'food_order_app.api.get_zalo_group_messages',
                args: {
                    group_id: this.selectedGroupId,
                    offset: 0,
                    count: 50
                },
                callback: (response) => {
                    if (response.message && response.message.success) {
                        const messages = response.message.messages || [];
                        this.processMessages(messages);
                        this.updateLastUpdate();
                    } else {
                        console.error('Fetch messages failed:', response.message);
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
            if (!this.hasLoadedInitialMessages) {
                this.messagesContainer.innerHTML = `
                    <div class="empty-state">
                        <p>📭 Không có tin nhắn nào</p>
                    </div>
                `;
                this.hasLoadedInitialMessages = true;
            }
            return;
        }

        // giữ thứ tự cũ -> mới để khi prepend vẫn ra mới nhất trên cùng
        const normalizedMessages = [...messages].reverse();

        normalizedMessages.forEach(msg => {
            const msgId = msg.message_id || msg.msg_id || msg.id;
            if (!msgId) return;

            const existing = this.messagesContainer.querySelector(`[data-msg-id="${msgId}"]`);
            const isBrandNewRecord = !existing;

            if (isBrandNewRecord) {
                const messageCard = this.createMessageCard(msg, this.hasLoadedInitialMessages);
                this.messagesContainer.prepend(messageCard);

                // Chỉ đếm + phản hồi sau khi đã load xong đợt đầu tiên
                if (this.hasLoadedInitialMessages) {
                    this.newMessagesCount++;

                    const parsed = this.parseSupportMessage(msg.message || msg.text || '');
                    if (parsed.isSupport) {
                        this.autoReplySupportMessage(msg, parsed);
                    }
                }
            }
        });

        if (!this.hasLoadedInitialMessages) {
            this.hasLoadedInitialMessages = true;
        }

        this.newMessageCount.textContent = this.newMessagesCount;

        const emptyState = this.messagesContainer.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

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

        const parsed = this.parseSupportMessage(contentRaw);

        const card = document.createElement('div');
        card.className = `message-card ${isNew ? 'new' : ''} ${parsed.isSupport ? 'message-support-inline' : ''}`;
        card.setAttribute('data-msg-id', msgId);
        card.setAttribute('data-message-raw', contentRaw);

        card.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${sender}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">${this.highlightSupportContent(contentRaw, parsed)}</div>
        `;

        if (parsed.isSupport) {
            card.style.borderLeft = '6px solid #ff3b30';
            card.style.background = '#fff5f5';
            card.style.fontWeight = '700';
            card.style.padding = '12px 14px';
            card.style.borderRadius = '10px';
            card.style.marginBottom = '10px';
            card.style.boxShadow = '0 4px 14px rgba(255, 59, 48, 0.12)';
        }

        return card;
    }

    parseSupportMessage(messageText) {
        const text = (messageText || '').trim();
        if (!text) {
            return { isSupport: false, service: '', content: '' };
        }

        const normalizedText = text.replace(/\s+/g, ' ').trim();

        for (const service of this.serviceKeywords) {
            const serviceValue = (service || '').trim();
            if (!serviceValue) continue;

            const escapedService = this.escapeRegex(serviceValue);

            const regex = new RegExp(`^${escapedService}(?:\\s*[-:–—/]\\s*|\\s+)(.+)$`, 'i');
            const match = normalizedText.match(regex);

            if (match && match[1] && match[1].trim()) {
                return {
                    isSupport: true,
                    service: serviceValue,
                    content: match[1].trim()
                };
            }
        }

        return { isSupport: false, service: '', content: '' };
    }

    highlightSupportContent(messageText, parsed) {
        const safeText = this.escapeHtml(messageText || '');

        if (!parsed.isSupport) {
            return this.nl2br(safeText);
        }

        const escapedService = this.escapeRegex(parsed.service);
        const regex = new RegExp(`^(${escapedService})(\\s*[-:–—/]\\s*|\\s+)(.+)$`, 'i');
        const match = (messageText || '').match(regex);

        if (!match) {
            return this.nl2br(safeText);
        }

        const serviceHtml = `<span style="color:#d70015;font-weight:800;">${this.escapeHtml(match[1])}</span>`;
        const sepHtml = `<span style="color:#d70015;font-weight:800;">${this.escapeHtml(match[2])}</span>`;
        const contentHtml = `<span style="color:#b00000;font-weight:800;">${this.escapeHtml(match[3])}</span>`;

        return `${serviceHtml}${sepHtml}${this.nl2br(contentHtml)}`;
    }

    autoReplySupportMessage(msg, parsed) {
        const msgId = msg.message_id || msg.msg_id || msg.id;
        const groupId = msg.group_id || this.selectedGroupId;

        if (!msgId || !groupId) return;

        const ackKey = `works_ack_${groupId}_${msgId}`;
        if (localStorage.getItem(ackKey) === '1') {
            return;
        }

        frappe.call({
            method: 'food_order_app.api.send_zalo_group_message_works',
            args: {
                group_id: groupId,
                text: this.acknowledgeText
            },
            callback: (response) => {
                if (response.message && response.message.success) {
                    localStorage.setItem(ackKey, '1');
                    console.log(`Đã phản hồi tự động cho message ${msgId}`, parsed);
                } else {
                    console.error('Auto reply failed:', response.message);
                }
            },
            error: (error) => {
                console.error('Auto reply error:', error);
            }
        });
    }

    refreshHighlightedMessages() {
        const messageCards = this.messagesContainer.querySelectorAll('.message-card');
        if (!messageCards.length) return;

        messageCards.forEach(card => {
            const raw = card.getAttribute('data-message-raw') || '';
            const parsed = this.parseSupportMessage(raw);
            const contentNode = card.querySelector('.message-content');

            if (contentNode) {
                contentNode.innerHTML = this.highlightSupportContent(raw, parsed);
            }

            if (parsed.isSupport) {
                card.classList.add('message-support-inline');
                card.style.borderLeft = '6px solid #ff3b30';
                card.style.background = '#fff5f5';
                card.style.fontWeight = '700';
                card.style.padding = '12px 14px';
                card.style.borderRadius = '10px';
                card.style.marginBottom = '10px';
                card.style.boxShadow = '0 4px 14px rgba(255, 59, 48, 0.12)';
            } else {
                card.classList.remove('message-support-inline');
                card.style.borderLeft = '';
                card.style.background = '';
                card.style.fontWeight = '';
                card.style.padding = '';
                card.style.borderRadius = '';
                card.style.marginBottom = '';
                card.style.boxShadow = '';
            }
        });
    }

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

    escapeRegex(text) {
        return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
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

frappe.ready(function() {
    window.zaloManager = new ZaloGroupsManager();
});