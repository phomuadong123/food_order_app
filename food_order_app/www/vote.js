function confirmCancel() {
    frappe.confirm(
        'Bạn có chắc chắn muốn hủy đăng ký này không?',
        () => {
            cancelOrder();
        },
        () => {
            console.log("Người dùng đã suy nghĩ lại.");
        }
    );
}