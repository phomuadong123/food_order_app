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

        this.initElements();
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
    }

    attachEventListeners() {
        if (this.loadGroupsBtn) this.loadGroupsBtn.addEventListener('click', () => this.loadGroups());
        if (this.startFetchBtn) this.startFetchBtn.addEventListener('click', () => this.startFetching());
        if (this.stopFetchBtn) this.stopFetchBtn.addEventListener('click', () => this.stopFetching());
        if (this.backBtn) this.backBtn.addEventListener('click', () => this.goBack());
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

            console.log('Calling API: food_order_app.api.get_zalo_groups');

            frappe.call({
                method: 'food_order_app.api.get_zalo_groups',
                args: {},
                callback: (response) => {
                    console.log('API Response:', response);
                    
                    if (response.message && response.message.success) {
                        this.displayGroups(response.message.groups);
                        this.showNotification('✓ Tải danh sách nhóm thành công!', 'success');
                    } else {
                        const error = response.message?.error || 'Lỗi không xác định';
                        this.showNotification(`✗ Lỗi: ${error}`, 'error');
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
            <div class="group-card" data-group-id="${group.group_id}" data-group-name="${group.group_name}">
                <div class="group-info">
                    <div class="group-name">👥 ${this.escapeHtml(group.group_name)}</div>
                    <div class="group-id">ID: ${group.group_id}</div>
                </div>
                <div class="group-icon">→</div>
            </div>
        `).join('');

        // Attach click listeners
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

        // Show messages section
        this.messagesSection.style.display = 'block';
        this.messagesTitle.textContent = `📨 Tin nhắn - ${this.escapeHtml(groupName)}`;
        this.startFetchBtn.style.display = 'inline-flex';
        this.stopFetchBtn.style.display = 'none';
        this.statsContainer.style.display = 'grid';
        this.statusValue.textContent = 'Dừng';

        // Scroll to messages section
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

        // Load messages immediately
        this.fetchMessages();

        // Then load every 5 seconds
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

    async fetchMessages() {
        try {
            const offset = this.lastMessageId ? 0 : 0;
            const count = 50;

            console.log(`Fetching messages from group ${this.selectedGroupId}`);

            frappe.call({
                method: 'food_order_app.api.get_zalo_group_messages',
                args: {
                    group_id: this.selectedGroupId,
                    offset: offset,
                    count: count
                },
                callback: (response) => {
                    console.log('Messages Response:', response);
                    
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

        // Reverse to show latest first
        messages.reverse();

        messages.forEach(msg => {
            const msgId = msg.msg_id || msg.id;
            const isNew = !this.lastMessageId || (msgId > this.lastMessageId);

            // Check if message already exists in DOM
            if (!document.querySelector(`[data-msg-id="${msgId}"]`)) {
                const messageCard = this.createMessageCard(msg, isNew);
                this.messagesContainer.prepend(messageCard);

                if (isNew) {
                    this.newMessagesCount++;
                }
            }

            // Update last message ID
            if (!this.lastMessageId || msgId > this.lastMessageId) {
                this.lastMessageId = msgId;
            }
        });

        // Update counter
        this.newMessageCount.textContent = this.newMessagesCount;

        // Remove empty state
        const emptyState = this.messagesContainer.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        // Limit messages to 100 to avoid performance issues
        const allMessages = this.messagesContainer.querySelectorAll('.message-card');
        if (allMessages.length > 100) {
            for (let i = 100; i < allMessages.length; i++) {
                allMessages[i].remove();
            }
        }
    }

    createMessageCard(msg, isNew = false) {
        const msgId = msg.msg_id || msg.id;
        const sender = this.escapeHtml(msg.sender_name || 'Người dùng');
        const time = this.formatTime(msg.timestamp || msg.created_time);
        const content = this.escapeHtml(msg.message || msg.text || '');

        const card = document.createElement('div');
        card.className = `message-card ${isNew ? 'new' : ''}`;
        card.setAttribute('data-msg-id', msgId);
        card.innerHTML = `
            <div class="message-header">
                <span class="message-sender">${sender}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">${this.nl2br(content)}</div>
        `;

        return card;
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
            date = new Date(timestamp * 1000); // Convert from Unix timestamp if needed
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
