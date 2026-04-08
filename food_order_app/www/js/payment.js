// Get URL parameters
let params = new URLSearchParams(window.location.search);
let zalo_id = params.get('zalo_id');
let isAdmin = false;
let currentApprovalData = {};
let approvalDialog = null;

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
            console.log(r.message);
            if (r.message && r.message.is_admin) {
                document.getElementById("lock-modal-title").textContent = "Duyệt các yêu cầu nạp tiền, admin(" + (r.message.full_name) +")";
            } else {
                document.getElementById("lock-modal-title").textContent = "Thực hiện giao dịch thêm tiền vào ví của bạn: " + (r.message.full_name) +".";
            }
            loadPaymentRequests();
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
let currentPage = 0;
const pageSize = 10;

function loadPaymentRequests(page = 0) {
    currentPage = page;
    let fromDate = document.getElementById('trans-from-date').value;
    let toDate = document.getElementById('trans-to-date').value;

    // Logic xử lý ngày mặc định (giữ nguyên của bạn)
    if (!toDate) {
        toDate = new Date().toISOString().split('T')[0];
    }
    if (!fromDate) {
        const d = new Date(toDate);
        d.setDate(d.getDate() - 30);
        fromDate = d.toISOString().split('T')[0];
    }

    const offset = currentPage * pageSize;

    frappe.call({
        method: 'food_order_app.payment.get_payment_requests',
        args: {
            zalo_id: zalo_id,
            from_date: fromDate,
            to_date: toDate,
            limit: pageSize,
            offset: offset
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                renderTable(r.message.data, r.message.user_info);
                renderPagination(r.message.total_count);
            }
        }
    });
}

function renderTable(requests, userInfo) {
    const container = document.getElementById('payment-request-list');
    if (!requests || requests.length === 0) {
        container.innerHTML = '<div class="empty-message">Không có dữ liệu</div>';
        return;
    }

    const isAdmin = userInfo && userInfo.roles && userInfo.roles.includes("Admin");
    console.log(userInfo);

    let html = `
        <table class="payment-request-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>ID Người dùng</th>
                    <th>Tên Người dùng</th>
                    <th>Số tiền</th>
                    <th>Trạng thái</th>
                    <th>Ghi chú</th>
                    <th>Thời gian</th>
                    ${isAdmin ? '<th>Hành động</th>' : ''} 
                </tr>
            </thead>
            <tbody>
    `;

    requests.forEach(req => {
        const amount = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(req.amount);
        const createDate = frappe.datetime.str_to_user(req.creation);
        
        html += `
            <tr>
                <td><strong>${req.name}</strong></td>
                <td>${req.user}</td>
                <td>${req.full_name}</td>
                <td style="color: #28a745; font-weight:600">${amount}</td>
                <td style="color: #994d59; font-weight:600">${req.status}</td>
                <td>${req.notes || '-'}</td>
                <td>${createDate}</td>
                ${isAdmin ? `
                    <td>
                        <button class="btn-approve" onclick="openApprovalModal('${req.name}', '${amount}', '${req.user}')">
                            Duyệt
                        </button>
                    </td>
                ` : ''}
            </tr>
        `;
    });

    html += '</tbody></table><div id="pagination-controls" class="pagination"></div>';
    container.innerHTML = html;
}

function renderPagination(totalCount) {
    const totalPages = Math.ceil(totalCount / pageSize);
    let html = `<div class="pagination-info">Tổng: ${totalCount} bản ghi</div><div class="page-buttons">`;

    // Nút Previous
    html += `<button ${currentPage === 0 ? 'disabled' : ''} onclick="loadPaymentRequests(${currentPage - 1})">Trước</button>`;

    // Hiển thị số trang (VD: Trang 1 / 5)
    html += `<span> Trang ${currentPage + 1} / ${totalPages || 1} </span>`;

    // Nút Next
    html += `<button ${currentPage >= totalPages - 1 ? 'disabled' : ''} onclick="loadPaymentRequests(${currentPage + 1})">Sau</button>`;

    html += `</div>`;
    document.getElementById('pagination-controls').innerHTML = html;
}

function openApprovalModal(requestId, amount, user) {
    currentApprovalData = {
        requestId: requestId,
        amount: amount,
        user: user
    };

    if (!approvalDialog) {
        approvalDialog = new frappe.ui.Dialog({
            title: 'Duyệt Yêu Cầu Nạp Tiền',
            body: `
                <div style="padding: 15px;">
                    <p><strong>Yêu cầu ID:</strong> <span id="dialog-request-id"></span></p>
                    <p><strong>Số tiền:</strong> <span id="dialog-amount"></span></p>
                    <div style="margin-top: 15px;">
                        <label for="dialog-notes" style="display: block; margin-bottom: 5px;"><strong>Ghi chú:</strong></label>
                        <textarea id="dialog-notes" placeholder="Ghi chú thêm (không bắt buộc)" style="width: 100%; min-height: 60px; padding: 8px; border: 1px solid #ccc; border-radius: 4px;"></textarea>
                    </div>
                </div>
            `,
            primary_action_label: 'Phê Duyệt',
            primary_action: function() {
                const notes = document.getElementById('dialog-notes').value;
                submitApproval('Approved', notes);
            },
            secondary_action_label: 'Từ Chối',
            secondary_action: function() {
                const notes = document.getElementById('dialog-notes').value;
                submitApproval('Rejected', notes);
            }
        });
    }

    approvalDialog.show();
    document.getElementById('dialog-request-id').textContent = requestId;
    document.getElementById('dialog-amount').textContent = amount + ' - ' + user;
    document.getElementById('dialog-notes').value = '';
}

function closeApprovalModal() {
    if (approvalDialog) {
        approvalDialog.hide();
    }
    currentApprovalData = {};
}

function submitApproval(action, notes) {
    if (!currentApprovalData.requestId) {
        frappe.msgprint('Có lỗi xảy ra');
        return;
    }

    notes = notes || '';

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

