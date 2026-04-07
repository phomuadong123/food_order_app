// Get URL parameters
const urlParams = new URLSearchParams(window.location.search);
const mode = urlParams.get('mode');
const zaloId = urlParams.get('zalo_id');
let isAdmin = false;
let currentApprovalData = {};

frappe.ready(function() {
    // Check if admin mode
    if (mode === 'admin' && zaloId) {
        isAdmin = true;
        document.getElementById('admin-header').style.display = 'block';
        document.getElementById('qr-section').style.display = 'none';
        document.getElementById('payment-request-section').style.display = 'block';
        loadPaymentRequests();
    } else {
        loadTransactions();
        loadQRCode();
    }
});

function loadQRCode() {
    // Load QR Code from bank/payment config
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Zalo Config',
            fields: ['bank_info', 'qr_code'],
            limit_page_length: 1
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                const config = r.message[0];
                let qrHtml = '<p style="color: #dc3545; font-size: 16px; margin-bottom: 20px;">Vui lòng chuyển khoản theo thông tin bên dưới:</p>';
                
                if (config.qr_code) {
                    qrHtml += `<img src="${config.qr_code}" alt="QR Code" style="max-width: 300px; border-radius: 8px;">`;
                }
                
                if (config.bank_info) {
                    qrHtml += `<div class="bank-info">${config.bank_info}</div>`;
                }
                
                document.getElementById('qr-code-container').innerHTML = qrHtml;
            }
        }
    });
}

function loadTransactions() {
    if (!zaloId) {
        // Show error message
        document.getElementById('transaction-list').innerHTML = '<p style="color: #dc3545; text-align: center;">Không tìm thấy zalo_id</p>';
        return;
    }

    const fromDate = document.getElementById('trans-from-date').value;
    const toDate = document.getElementById('trans-to-date').value;

    frappe.call({
        method: 'food_order_app.api.get_user_transactions',
        args: {
            zalo_id: zaloId,
            from_date: fromDate,
            to_date: toDate,
            limit: 100
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                const transactions = r.message.data;
                if (transactions.length === 0) {
                    document.getElementById('transaction-list').innerHTML = '<div class="empty-message">Không có giao dịch nào</div>';
                } else {
                    let table = '<table class="transaction-table"><thead><tr><th>Ngày</th><th>Loại</th><th>Số tiền</th><th>Mô tả</th></tr></thead><tbody>';
                    transactions.forEach(tx => {
                        const badgeClass = `badge badge-${tx.type.toLowerCase()}`;
                        const amount = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(tx.amount);
                        table += `<tr>
                            <td>${frappe.datetime.str_to_user(tx.date)}</td>
                            <td><span class="${badgeClass}">${getTransactionTypeLabel(tx.type)}</span></td>
                            <td style="font-weight: 600; color: ${tx.type === 'Pay' ? '#dc3545' : '#28a745'}">${amount}</td>
                            <td>${tx.description}</td>
                        </tr>`;
                    });
                    table += '</tbody></table>';
                    document.getElementById('transaction-list').innerHTML = table;
                }
            }
        }
    });
}

function loadPaymentRequests() {
    frappe.call({
        method: 'food_order_app.api.get_pending_payment_requests',
        args: {
            zalo_id: zaloId,
            limit: 50
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                const requests = r.message.data;
                if (requests.length === 0) {
                    document.getElementById('payment-request-list').innerHTML = '<div class="empty-message">Không có yêu cầu nạp tiền nào chờ duyệt</div>';
                } else {
                    let table = '<table class="payment-request-table"><thead><tr><th>ID</th><th>Người dùng</th><th>Số tiền</th><th>Ghi chú</th><th>Thời gian</th><th>Hành động</th></tr></thead><tbody>';
                    requests.forEach(req => {
                        const amount = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(req.amount);
                        const createDate = frappe.datetime.str_to_user(req.creation);
                        table += `<tr>
                            <td><strong>${req.name}</strong></td>
                            <td>${req.user}</td>
                            <td style="font-weight: 600; color: #28a745;">${amount}</td>
                            <td>${req.notes || '-'}</td>
                            <td>${createDate}</td>
                            <td>
                                <div class="action-buttons">
                                    <button class="btn-approve" onclick="openApprovalModal('${req.name}', '${amount}', '${req.user}')">Duyệt</button>
                                </div>
                            </td>
                        </tr>`;
                    });
                    table += '</tbody></table>';
                    document.getElementById('payment-request-list').innerHTML = table;
                }
            }
        }
    });
}

function openApprovalModal(requestId, amount, user) {
    currentApprovalData = {
        requestId: requestId,
        amount: amount,
        user: user
    };
    document.getElementById('approval-request-id').textContent = requestId;
    document.getElementById('approval-amount').textContent = amount + ' - ' + user;
    document.getElementById('approval-notes').value = '';
    document.getElementById('approval-modal').setAttribute('aria-hidden', 'false');
}

function closeApprovalModal() {
    document.getElementById('approval-modal').setAttribute('aria-hidden', 'true');
    currentApprovalData = {};
}

function submitApproval(action) {
    if (!currentApprovalData.requestId) {
        frappe.msgprint('Có lỗi xảy ra');
        return;
    }

    const notes = document.getElementById('approval-notes').value;

    frappe.call({
        method: 'food_order_app.api.approve_payment_request',
        args: {
            payment_request_id: currentApprovalData.requestId,
            zalo_id: zaloId,
            action: action,
            notes: notes
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.msgprint(r.message.message);
                closeApprovalModal();
                loadPaymentRequests();
            } else {
                frappe.msgprint('Có lỗi xảy ra: ' + (r.message ? r.message.message : 'Unknown error'));
            }
        },
        error: function(err) {
            frappe.msgprint('Lỗi: ' + err);
        }
    });
}

function getTransactionTypeLabel(type) {
    switch(type) {
        case 'Deposit':
            return 'Nạp tiền';
        case 'Pay':
            return 'Trừ tiền';
        case 'Refund':
            return 'Hoàn tiền';
        default:
            return type;
    }
}

function goBack() {
    window.history.back();
}