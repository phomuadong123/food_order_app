function confirmCancel() {
    frappe.confirm(
        'Bạn có chắc chắn muốn hủy đăng ký này không? (thao tác này sẽ hủy tất cả các đăng ký của bạn trong ngày hôm nay)',
        () => {
            cancelOrder();
        },
        () => {
            console.log("Người dùng đã suy nghĩ lại.");
        }
    );
}

window.addEventListener('load', function() {
    console.log("Tất cả tài nguyên đã tải xong!");
    setTimeout(function() {
        const newUrl = '/api/method/food_order_app.api.start_vote';
        window.history.replaceState({ path: newUrl }, '', newUrl);
        
        console.log("URL đã được làm sạch thành: " + newUrl);
    }, 1000); 
});

document.addEventListener("DOMContentLoaded", function() {
    const fromInput = document.getElementById('my-history-from-date');
    const toInput = document.getElementById('my-history-to-date');
    
    const now = new Date();
    
    const todayStr = now.toISOString().split('T')[0];
    if(toInput) toInput.value = todayStr;
    
    const lastMonth = new Date();
    lastMonth.setMonth(now.getMonth() - 1);
    const lastMonthStr = lastMonth.toISOString().split('T')[0];
    if(fromInput) fromInput.value = lastMonthStr;
});

// =========================
// PAYMENT FUNCTIONS
// =========================

function openDepositModal() {
    document.getElementById('deposit-modal').style.display = 'flex';
    document.getElementById('deposit-modal').setAttribute('aria-hidden', 'false');
    document.getElementById('qr-container').style.display = 'none';
    document.getElementById('confirm-payment-btn').style.display = 'none';
    document.getElementById('generate-qr-btn').style.display = 'inline-block';
    document.getElementById('deposit-amount').value = '';
}

function closeDepositModal() {
    document.getElementById('deposit-modal').style.display = 'none';
    document.getElementById('deposit-modal').setAttribute('aria-hidden', 'true');
}

function generateQR() {
    const amount = document.getElementById('deposit-amount').value;
    if (!amount || amount < 10000) {
        frappe.msgprint('Vui lòng nhập số tiền tối thiểu 10,000 VNĐ');
        return;
    }

    frappe.call({
        method: 'food_order_app.payment.create_payment_request',
        args: { amount: amount },
        callback: function(r) {
            if (r.message && r.message.success) {
                document.getElementById('qr-code').src = r.message.qr_code;
                document.getElementById('bank-info').innerText = r.message.bank_info.replace(/\n/g, '\n');
                document.getElementById('qr-container').style.display = 'block';
                document.getElementById('generate-qr-btn').style.display = 'none';
                document.getElementById('confirm-payment-btn').style.display = 'inline-block';
                frappe.msgprint('Mã QR đã được tạo. Vui lòng quét và chuyển khoản.');
            } else {
                frappe.msgprint('Có lỗi xảy ra khi tạo yêu cầu thanh toán');
            }
        }
    });
}

function confirmPayment() {
    frappe.confirm('Bạn đã chuyển khoản thành công?', () => {
        frappe.msgprint('Yêu cầu duyệt thanh toán đã được gửi đến quản trị viên. Vui lòng chờ xác nhận.');
        closeDepositModal();
    });
}