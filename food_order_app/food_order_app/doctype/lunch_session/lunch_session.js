frappe.listview_settings['Lunch Session'] = {
    refresh: function(listview) {
        listview.page.add_inner_button(__("Xuất Báo Cáo Tháng"), function() {
            var today = new Date();
            frappe.prompt(
                [
                    {
                        fieldname: 'month',
                        label: __('Tháng'),
                        fieldtype: 'Select',
                        options: "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12",
                        reqd: 1,
                        default: (today.getMonth() + 1).toString()
                    },
                    {
                        fieldname: 'year',
                        label: __('Năm'),
                        fieldtype: 'Int',
                        reqd: 1,
                        default: today.getFullYear()
                    }
                ],
                function(values) {
                    var download_url = "/api/method/food_order_app.api.export_monthly_report?month=" + values.month + "&year=" + values.year;
                    window.open(download_url, '_blank');
                },
                __('Chọn Tháng & Năm Xuất Báo Cáo Excel'),
                __('Tải Về')
            );
        });
    }
};
