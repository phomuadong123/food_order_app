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