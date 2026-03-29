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