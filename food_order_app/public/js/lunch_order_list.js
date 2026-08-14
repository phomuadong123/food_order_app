(() => {
    const method = (name) => `food_order_app.admin_lunch_order.${name}`;

    const escapeHtml = (value) => {
        const text = String(value ?? "");
        if (frappe.utils.escape_html) {
            return frappe.utils.escape_html(text);
        }
        return text.replace(/[&<>'"]/g, (character) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "'": "&#39;",
            '"': "&quot;",
        })[character]);
    };

    const formatAmount = (amount) => `${Number(amount || 0).toLocaleString("vi-VN")} VNĐ`;

    const errorMessage = (error, fallback) => {
        if (error?.message) return error.message;
        if (error?._server_messages) {
            try {
                const messages = JSON.parse(error._server_messages);
                const lastMessage = JSON.parse(messages[messages.length - 1]);
                return lastMessage.message || fallback;
            } catch (parseError) {
                return fallback;
            }
        }
        return fallback;
    };

    const call = async (name, args) => {
        const response = await frappe.call({ method: method(name), args });
        const payload = response.message;
        if (!payload?.success) {
            throw new Error(payload?.message || __("Không thể xử lý yêu cầu."));
        }
        return payload;
    };

    const setSelectOptions = (dialog, fieldname, labels) => {
        dialog.set_df_property(fieldname, "options", ["", ...labels].join("\n"));
        dialog.set_value(fieldname, "");
    };

    const setPrimaryButtonDisabled = (dialog, disabled) => {
        dialog.get_primary_btn().prop("disabled", disabled);
    };

    const openCreateDialog = (listview) => {
        let dialog;
        let sessionByLabel = new Map();
        let menuByLabel = new Map();
        let selectedUser = null;
        let userSearchTimer = null;

        const clearUserSelection = () => {
            selectedUser = null;
            dialog.get_field("selected_user_summary").$wrapper.html(
                `<div class="text-muted">${__("Chưa chọn người dùng.")}</div>`
            );
        };

        const renderUserResults = (users, emptyMessage = __("Không có người dùng phù hợp.")) => {
            const wrapper = dialog.get_field("user_results").$wrapper;
            if (!users.length) {
                wrapper.html(`<div class="text-muted">${escapeHtml(emptyMessage)}</div>`);
                return;
            }

            wrapper.html(`
                <div class="border rounded p-2" style="max-height: 240px; overflow-y: auto;">
                    ${users.map((user, index) => `
                        <button type="button" class="btn btn-default btn-sm text-left w-100 mb-2" data-user-index="${index}">
                            <strong>${escapeHtml(user.full_name || user.real_name || user.zalo_id)}</strong>
                            <div class="text-muted small">
                                ${escapeHtml(user.real_name || "-")} · ${escapeHtml(user.department || "-")} · Zalo ID: ${escapeHtml(user.zalo_id || "-")}
                            </div>
                            <div class="small">${__("Số dư ví")}: ${escapeHtml(formatAmount(user.wallet_balance))} · ${user.is_active ? __("Đang hoạt động") : __("Chưa kích hoạt")}</div>
                        </button>
                    `).join("")}
                </div>
            `);

            wrapper.find("[data-user-index]").on("click", function () {
                selectedUser = users[Number($(this).data("user-index"))];
                dialog.set_value("user_search", selectedUser.full_name || selectedUser.zalo_id);
                dialog.get_field("selected_user_summary").$wrapper.html(`
                    <div class="alert alert-info mb-0">
                        <strong>${escapeHtml(selectedUser.full_name || "-")}</strong><br>
                        ${__("Tên thật")}: ${escapeHtml(selectedUser.real_name || "-")}<br>
                        ${__("Phòng ban")}: ${escapeHtml(selectedUser.department || "-")}<br>
                        Zalo ID: ${escapeHtml(selectedUser.zalo_id || "-")}<br>
                        ${__("Số dư ví hiện tại")}: ${escapeHtml(formatAmount(selectedUser.wallet_balance))}
                    </div>
                `);
                wrapper.empty();
            });
        };

        const loadSessions = async () => {
            const orderDate = dialog.get_value("order_date");
            sessionByLabel = new Map();
            menuByLabel = new Map();
            setSelectOptions(dialog, "session", []);
            setSelectOptions(dialog, "menu_item", []);
            dialog.set_df_property("session", "read_only", 1);
            dialog.set_df_property("menu_item", "read_only", 1);
            if (!orderDate) return;

            try {
                const payload = await call("admin_get_sessions_by_date", { order_date: orderDate });
                const labels = payload.data.map((session) => {
                    const label = `${session.session_name || __("Buổi ăn")} (${session.status}) [${session.name}]`;
                    sessionByLabel.set(label, session);
                    return label;
                });
                setSelectOptions(dialog, "session", labels);
                dialog.set_df_property("session", "read_only", 0);
                if (!labels.length) {
                    frappe.show_alert({ message: __("Không có buổi ăn mở/đã đóng cho ngày đã chọn."), indicator: "orange" }, 5);
                }
            } catch (error) {
                frappe.msgprint({ title: __("Không tải được buổi ăn"), indicator: "red", message: errorMessage(error, __("Vui lòng thử lại.")) });
            }
        };

        const loadMenuItems = async () => {
            const session = sessionByLabel.get(dialog.get_value("session"));
            menuByLabel = new Map();
            setSelectOptions(dialog, "menu_item", []);
            dialog.set_df_property("menu_item", "read_only", 1);
            if (!session) return;

            try {
                const payload = await call("admin_get_session_menu_items", { session: session.name });
                const labels = payload.data.map((menuItem) => {
                    const label = `${menuItem.item_name || __("Món ăn")} — ${formatAmount(menuItem.price)} [${menuItem.name}]`;
                    menuByLabel.set(label, menuItem);
                    return label;
                });
                setSelectOptions(dialog, "menu_item", labels);
                dialog.set_df_property("menu_item", "read_only", 0);
            } catch (error) {
                frappe.msgprint({ title: __("Không tải được món ăn"), indicator: "red", message: errorMessage(error, __("Vui lòng thử lại.")) });
            }
        };

        const searchUsers = async () => {
            const searchText = (dialog.get_value("user_search") || "").trim();
            clearUserSelection();
            if (searchText.length < 2) {
                renderUserResults([], __("Nhập ít nhất 2 ký tự để tìm theo tên hoặc Zalo ID."));
                return;
            }

            try {
                const payload = await call("admin_search_lunch_users", { search_text: searchText });
                renderUserResults(payload.data);
            } catch (error) {
                renderUserResults([], errorMessage(error, __("Không thể tìm người dùng.")));
            }
        };

        dialog = new frappe.ui.Dialog({
            title: __("Thêm đặt mới"),
            fields: [
                {
                    fieldname: "order_date",
                    label: __("Ngày ăn"),
                    fieldtype: "Date",
                    reqd: 1,
                    default: frappe.datetime.get_today(),
                    onchange: loadSessions,
                },
                {
                    fieldname: "session",
                    label: __("Buổi ăn"),
                    fieldtype: "Select",
                    reqd: 1,
                    read_only: 1,
                    onchange: loadMenuItems,
                },
                {
                    fieldname: "menu_item",
                    label: __("Bữa ăn / Menu"),
                    fieldtype: "Select",
                    reqd: 1,
                    read_only: 1,
                },
                { fieldtype: "Section Break", label: __("Người dùng") },
                {
                    fieldname: "user_search",
                    label: __("Tìm người dùng"),
                    fieldtype: "Data",
                    description: __("Tìm theo tên Zalo, tên thật hoặc Zalo ID."),
                },
                { fieldname: "user_results", fieldtype: "HTML" },
                { fieldname: "selected_user_summary", fieldtype: "HTML" },
                { fieldtype: "Section Break", label: __("Thông tin tạo đơn") },
                {
                    fieldname: "active_summary",
                    fieldtype: "HTML",
                    options: `<div class="text-muted">${__("Thời gian tạo được lấy theo thời điểm xác nhận. Đơn mới sẽ ở trạng thái Hoạt động.")}</div>`,
                },
            ],
            primary_action_label: __("Xác nhận thêm đặt mới"),
            primary_action: async () => {
                const session = sessionByLabel.get(dialog.get_value("session"));
                const menuItem = menuByLabel.get(dialog.get_value("menu_item"));
                if (!session || !menuItem || !selectedUser) {
                    frappe.msgprint(__("Vui lòng chọn đầy đủ buổi ăn, món ăn và người dùng."));
                    return;
                }

                setPrimaryButtonDisabled(dialog, true);
                try {
                    const payload = await call("admin_create_lunch_order", {
                        session: session.name,
                        menu_item: menuItem.name,
                        zalo_user: selectedUser.name,
                    });
                    frappe.show_alert({
                        message: `${escapeHtml(payload.message)} ${__("Số tiền")}: ${formatAmount(payload.amount)}. ${__("Số dư còn lại")}: ${formatAmount(payload.wallet_balance)}.`,
                        indicator: "green",
                    }, 8);
                    dialog.hide();
                    listview.refresh();
                } catch (error) {
                    frappe.msgprint({ title: __("Không thể thêm đăng ký"), indicator: "red", message: errorMessage(error, __("Dữ liệu chưa được thay đổi.")) });
                } finally {
                    setPrimaryButtonDisabled(dialog, false);
                }
            },
        });

        dialog.show();
        clearUserSelection();
        renderUserResults([], __("Nhập ít nhất 2 ký tự để tìm người dùng."));
        dialog.get_field("user_search").$input.on("input", () => {
            window.clearTimeout(userSearchTimer);
            userSearchTimer = window.setTimeout(searchUsers, 300);
        });
        loadSessions();
    };

    const openCancelDialog = (listview) => {
        let dialog;
        let activeOrders = [];
        let selectedOrder = null;

        const renderSelectedOrder = () => {
            const wrapper = dialog.get_field("selected_order_summary").$wrapper;
            if (!selectedOrder) {
                wrapper.html(`<div class="text-muted">${__("Chưa chọn đăng ký cần hủy.")}</div>`);
                return;
            }

            const paidAmount = Number(selectedOrder.paid_amount || 0);
            const paymentText = selectedOrder.payment_is_resolvable
                ? formatAmount(paidAmount)
                : __("Không xác định — không thể tự động hoàn tiền");
            wrapper.html(`
                <div class="alert ${selectedOrder.payment_is_resolvable ? "alert-warning" : "alert-danger"} mb-0">
                    <strong>${escapeHtml(selectedOrder.full_name || "-")}</strong><br>
                    ${__("Ngày ăn")}: ${escapeHtml(selectedOrder.session_date || "-")}<br>
                    ${__("Buổi ăn")}: ${escapeHtml(selectedOrder.session_name || "-")}<br>
                    ${__("Bữa ăn / Menu")}: ${escapeHtml(selectedOrder.menu_item_name || "-")}<br>
                    ${__("Đã thanh toán")}: ${escapeHtml(paymentText)}<br>
                    ${__("Số dư hiện tại")}: ${escapeHtml(formatAmount(selectedOrder.wallet_balance))}<br>
                    Lunch Order ID: ${escapeHtml(selectedOrder.lunch_order)}
                </div>
            `);
        };

        const renderOrders = () => {
            const wrapper = dialog.get_field("order_results").$wrapper;
            if (!activeOrders.length) {
                wrapper.html(`<div class="text-muted">${__("Không có đăng ký đang hoạt động cho ngày đã chọn.")}</div>`);
                return;
            }

            wrapper.html(`
                <div class="border rounded p-2" style="max-height: 360px; overflow-y: auto;">
                    ${activeOrders.map((order, index) => {
                        const paidText = order.payment_is_resolvable
                            ? formatAmount(order.paid_amount)
                            : __("Không xác định");
                        return `
                            <button type="button" class="btn btn-default btn-sm text-left w-100 mb-2" data-order-index="${index}">
                                <strong>${escapeHtml(order.full_name || order.real_name || order.zalo_id)}</strong>
                                <div class="text-muted small">${escapeHtml(order.department || "-")} · Zalo ID: ${escapeHtml(order.zalo_id || "-")}</div>
                                <div class="small">${escapeHtml(order.session_name || "-")} · ${escapeHtml(order.menu_item_name || "-")} · ${__("Đã trừ")}: ${escapeHtml(paidText)}</div>
                                <div class="text-muted small">Lunch Order ID: ${escapeHtml(order.lunch_order)}</div>
                            </button>
                        `;
                    }).join("")}
                </div>
            `);
            wrapper.find("[data-order-index]").on("click", function () {
                selectedOrder = activeOrders[Number($(this).data("order-index"))];
                renderSelectedOrder();
            });
        };

        const loadOrders = async () => {
            const orderDate = dialog.get_value("order_date");
            activeOrders = [];
            selectedOrder = null;
            renderSelectedOrder();
            dialog.get_field("order_results").$wrapper.html(`<div class="text-muted">${__("Đang tải đăng ký...")}</div>`);
            if (!orderDate) return;

            try {
                const payload = await call("admin_get_active_orders_by_date", { order_date: orderDate });
                activeOrders = payload.data;
                renderOrders();
            } catch (error) {
                dialog.get_field("order_results").$wrapper.html(`<div class="text-danger">${escapeHtml(errorMessage(error, __("Không tải được đăng ký.")))}</div>`);
            }
        };

        dialog = new frappe.ui.Dialog({
            title: __("Hủy đăng ký"),
            fields: [
                {
                    fieldname: "order_date",
                    label: __("Ngày ăn"),
                    fieldtype: "Date",
                    reqd: 1,
                    default: frappe.datetime.get_today(),
                    onchange: loadOrders,
                },
                { fieldname: "order_results", fieldtype: "HTML" },
                { fieldtype: "Section Break", label: __("Xác nhận hủy") },
                { fieldname: "selected_order_summary", fieldtype: "HTML" },
            ],
            primary_action_label: __("Xác nhận hủy đăng ký"),
            primary_action: async () => {
                if (!selectedOrder) {
                    frappe.msgprint(__("Vui lòng chọn một đăng ký để hủy."));
                    return;
                }
                if (!selectedOrder.payment_is_resolvable) {
                    frappe.msgprint({
                        title: __("Không thể hoàn tiền tự động"),
                        indicator: "red",
                        message: __("Không tìm thấy chính xác một giao dịch thanh toán liên kết với Lunch Order này. Dữ liệu không bị thay đổi."),
                    });
                    return;
                }

                frappe.confirm(
                    `${__("Bạn có chắc muốn hủy đăng ký của")} ${escapeHtml(selectedOrder.full_name || selectedOrder.zalo_id)}? ${__("Hệ thống sẽ hoàn lại")} ${formatAmount(selectedOrder.paid_amount)}.`,
                    async () => {
                        setPrimaryButtonDisabled(dialog, true);
                        try {
                            const payload = await call("admin_cancel_lunch_order", { lunch_order: selectedOrder.lunch_order });
                            frappe.show_alert({
                                message: `${escapeHtml(payload.message)} ${__("Đã hoàn")}: ${formatAmount(payload.refund_amount)}. ${__("Số dư hiện tại")}: ${formatAmount(payload.wallet_balance)}.`,
                                indicator: "green",
                            }, 8);
                            dialog.hide();
                            listview.refresh();
                        } catch (error) {
                            frappe.msgprint({ title: __("Không thể hủy đăng ký"), indicator: "red", message: errorMessage(error, __("Dữ liệu chưa được thay đổi.")) });
                        } finally {
                            setPrimaryButtonDisabled(dialog, false);
                        }
                    }
                );
            },
        });

        dialog.show();
        renderSelectedOrder();
        loadOrders();
    };

    frappe.listview_settings["Lunch Order"] = {
        refresh(listview) {
            if (listview.page.__foodOrderAdminActionsBound) return;
            listview.page.__foodOrderAdminActionsBound = true;

            listview.page.add_inner_button(__("Thêm đặt mới"), () => openCreateDialog(listview));
            listview.page.add_inner_button(__("Hủy đăng ký"), () => openCancelDialog(listview));
        },
    };
})();
