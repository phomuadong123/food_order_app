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
// PAYMENT FUNCTION FLOW
// =========================

window.openDepositModal = function() {
    const modal = document.getElementById('deposit-modal');
    if (modal) {
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        document.getElementById('qr-container').style.display = 'none';
        document.getElementById('confirm-payment-btn').style.display = 'none';
        document.getElementById('generate-qr-btn').style.display = 'inline-block';
        document.getElementById('deposit-amount').value = '';
    }
};

window.closeDepositModal = function() {
    const modal = document.getElementById('deposit-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }
};

window.generateQR = function() {
    const amountInput = document.getElementById('deposit-amount');
    const amount = amountInput.value;
    
    if (!amount || parseFloat(amount) < 10000) {
        frappe.msgprint('Vui lòng nhập số tiền tối thiểu 10,000 VNĐ');
        return;
    }
    
    frappe.call({
        method: 'food_order_app.payment.create_payment_request',
        args: { amount: amount },
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

window.confirmPayment = function() {
    frappe.confirm('Bạn đã chuyển khoản thành công?', () => {
        frappe.msgprint({
            title: 'Thành công',
            message: 'Yêu cầu nạp tiền đã được gửi đến quản trị viên. Vui lòng chờ xác nhận (thường trong vòng 1-2 giờ).',
            indicator: 'green'
        });
        window.closeDepositModal();
    });
};

// Close modal when clicking outside
document.addEventListener('DOMContentLoaded', function() {
    const depositModal = document.getElementById('deposit-modal');
    if (depositModal) {
        depositModal.addEventListener('click', function(e) {
            if (e.target === depositModal) {
                window.closeDepositModal();
            }
        });
    }
});

