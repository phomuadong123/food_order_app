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
                isAdmin = true;
                document.getElementById("lock-modal-title").textContent = "Duyệt các yêu cầu nạp tiền, Quản trị viên: (" + (r.message.full_name) +")";
            } else {
                document.getElementById("lock-modal-title").textContent = "Thực hiện giao dịch thêm tiền vào ví của bạn: " + (r.message.full_name) +".";
            }
            console.log("isAdmin",isAdmin);
            
            loadPaymentRequests(0, r.message.is_admin);
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
                
                qrImg.src = "/image/qr.jpg";
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

function loadPaymentRequests(page = 0, is_admin = false) {
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
            offset: offset,
            isAdmin:  is_admin ? is_admin : isAdmin
        },
        callback: function(r) {
            console.log('Payment requests response:', r);
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
        const statusInfo = formatStatus(req.status);
        
        html += `
            <tr>
                <td>${req.user}</td>
                <td>${req.full_name}</td>
                <td style="color: #28a745; font-weight:600">${amount}</td>
                <td><button style="background-color: ${statusInfo.color}; color: white; border: none; padding: 5px 10px; border-radius: 3px;">${statusInfo.text}</button></td>
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

function formatStatus(status) {
    const s = status ? status.toLowerCase() : "";
    
    let config = {
        text: status,
        color: "#994d59"   
    };

    if (s === "pending") {
        config = { text: "Chờ duyệt", color: "#ffc107" }; // Vàng
    } else if (s === "approved") {
        config = { text: "Đã duyệt", color: "#02c076" };  // Xanh lá
    } else if (s === "rejected") {
        config = { text: "Từ chối", color: "#cf304a" };   // Đỏ
    }

    return config;
}

function renderPagination(totalCount) {
    const totalPages = Math.ceil(totalCount / pageSize);
    let html = `<div class="pagination-info">Tổng: ${totalCount} bản ghi</div><div class="page-buttons">`;

    // Nút Previous
    html += `<button ${currentPage === 0 ? 'disabled' : ''} onclick="loadPaymentRequests(${currentPage - 1}, ${isAdmin})">Trước</button>`;

    // Hiển thị số trang (VD: Trang 1 / 5)
    html += `<span> Trang ${currentPage + 1} / ${totalPages || 1} </span>`;

    // Nút Next
    html += `<button ${currentPage >= totalPages - 1 ? 'disabled' : ''} onclick="loadPaymentRequests(${currentPage + 1}, ${isAdmin})">Sau</button>`;
    html += `</div>`;
    document.getElementById('pagination-controls').innerHTML = html;
}


function openApprovalModal(requestId, amount, user) {
    // Lưu thông tin
    currentApprovalData = { requestId: requestId, amount: amount, user: user };
    console.log(currentApprovalData);
    
    // Đổ dữ liệu vào HTML bằng JS thuần
    document.getElementById('m-id').innerText = requestId;
    document.getElementById('m-amount').innerText = amount;
    document.getElementById('m-user').innerText = user;
    document.getElementById('pure-notes').value = '';

    // Hiển thị modal (dùng flex để căn giữa)
    document.getElementById('myCustomModal').style.display = 'flex';
}

function closeMyModal() {
    document.getElementById('myCustomModal').style.display = 'none';
}

function handleAction(status) {
    const notes = document.getElementById('pure-notes').value;
    
    // Gọi hàm submitApproval của bạn
    if (typeof submitApproval === "function") {
        submitApproval(status, notes);
    } else {
        console.log("Status:", status, "Notes:", notes, "Data:", currentData);
    }

    // Đóng modal sau khi thực hiện
    closeMyModal();
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
                closeMyModal();
                loadPaymentRequests(0, isAdmin); // Tải lại trang sau khi duyệt
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

