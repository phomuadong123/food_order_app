// Get URL parameters
let params = new URLSearchParams(window.location.search);
let zalo_id = params.get('zalo_id');
let isAdmin = false;
let currentApprovalData = {};

frappe.ready(function() {
    

    if (!zalo_id) {
        console.error("Không tìm thấy Zalo ID");
        return;
    }

    frappe.call({
        method: "food_order_app.payment.check_zalo_admin",
        args: {
            "zalo_id": zalo_id
        },
        callback: function(r) {
            if (r.message && r.message.is_admin) {
                document.getElementById('admin-header').style.display = 'block';
                document.querySelector('.lock-modal-card').style.display = 'none';
                document.querySelector('.payment-section').style.display = 'none';
                loadPaymentRequests();
            } else {
                // LOGIC CHO USER THƯỜNG
                document.getElementById('admin-header').style.display = 'none';
                document.getElementById("lock-modal-title").textContent = "Thêm tiền vào ví của bạn: " + (r.message.full_name) +".";
                loadTransactions();
            }
        }
    });
});

function confirmPayment() {
    frappe.confirm('Bạn đã chuyển khoản thành công?', () => {
        frappe.msgprint({
            title: 'Thành công',
            message: 'Yêu cầu nạp tiền đã được gửi đến quản trị viên. Vui lòng chờ xác nhận (thường trong vòng 1-2 giờ).',
            indicator: 'green'
        });
        window.closeDepositModal();
    });
};

function generateQR() {
    const amountInput = document.getElementById('deposit-amount');
    const amount = amountInput.value;
    
    if (!amount || parseFloat(amount) < 10000) {
        frappe.msgprint('Vui lòng nhập số tiền tối thiểu 10,000 VNĐ');
        return;
    }
    
    frappe.call({
        method: 'food_order_app.payment.create_payment_request',
        args: { amount: amount, zalo_id: zalo_id },
        callback: function(r) {
            if (r.message && r.message.success) {
                const qrImg = document.getElementById('qr-code');
                const bankInfo = document.getElementById('bank-info');
                const qrContainer = document.getElementById('qr-container');
                const generateBtn = document.getElementById('generate-qr-btn');
                const confirmBtn = document.getElementById('confirm-payment-btn');
                
                qrImg.src = r.message.qr_code;
                bankInfo.innerHTML = r.message.bank_info.replace(/\n/g, '<br>');
                qrContainer.style.display = 'block';
                generateBtn.style.display = 'none';
                confirmBtn.style.display = 'inline-block';
                
                frappe.msgprint('Mã QR đã được tạo. Vui lòng quét mã và chuyển khoản.');
            } else {
                frappe.msgprint({
                    title: 'Lỗi',
                    message: 'Không tạo được mã QR. Vui lòng thử lại.',
                    indicator: 'red'
                });
            }
        },
        error: function(err) {
            console.error('generateQR error:', err);
            frappe.msgprint({
                title: 'Lỗi',
                message: 'Có lỗi xảy ra khi tạo mã QR.',
                indicator: 'red'
            });
        }
    });
};

function loadTransactions() {
    if (!zalo_id) {
        // Show error message
        document.getElementById('transaction-list').innerHTML = '<p style="color: #dc3545; text-align: center;">Không tìm thấy zalo_id</p>';
        return;
    }

    const fromDate = document.getElementById('trans-from-date').value;
    const toDate = document.getElementById('trans-to-date').value;

    frappe.call({
        method: 'food_order_app.api.get_user_transactions',
        args: {
            zalo_id: zalo_id,
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
        method: 'food_order_app.payment.get_payment_requests',
        args: {
            zalo_id: zalo_id,
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
        method: 'food_order_app.payment.approve_payment_request',
        args: {
            payment_request_id: currentApprovalData.requestId,
            zalo_id: zalo_id,
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

