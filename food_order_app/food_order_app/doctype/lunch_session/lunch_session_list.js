frappe.listview_settings['Lunch Session'] = {
    refresh: function(listview) {        listview.page.add_inner_button(__('Import Báo Cáo'), function() {
            frappe.prompt(
                [
                    {
                        fieldname: 'file_url',
                        label: __('URL file Excel (năm)'),
                        fieldtype: 'Data',
                        reqd: 1
                    }
                ],
                function(values) {
                    frappe.call({
                        method: 'food_order_app.excel.import.import_yearly_report',
                        args: { file_url: values.file_url },
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint(r.message);
                            } else {
                                frappe.msgprint(__('Import thành công'));
                            }
                            listview.refresh();
                        },
                        error: function(err) {
                            frappe.msgprint(__('Import lỗi: ') + (err?.message || ''));
                        }
                    });
                },
                __('Import báo cáo theo file Excel năm'),
                __('Import')
            );
        });
        listview.page.add_inner_button(__("Xuất Báo Cáo"), function() {
            frappe.prompt(
                [
                    {
                        fieldname: 'report_type',
                        label: __('Chọn loại báo cáo'),
                        fieldtype: 'Select',
                        options: 'Ngày\nTháng\nNăm',
                        reqd: 1
                    }
                ],
                function(values) {
                    var today = new Date();
                    if (values.report_type === 'Ngày') {
                        frappe.prompt(
                            [
                                {
                                    fieldname: 'date',
                                    label: __('Ngày'),
                                    fieldtype: 'Date',
                                    reqd: 1,
                                    default: frappe.datetime.get_today()
                                }
                            ],
                            function(values2) {
                                var download_url = "/api/method/food_order_app.excel.export.export_daily_report?date=" + values2.date;
                                window.open(download_url, '_blank');
                            },
                            __('Chọn ngày xuất báo cáo'),
                            __('Tải về')
                        );
                    } else if (values.report_type === 'Tháng') {
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
                            function(values2) {
                                var download_url = "/api/method/food_order_app.excel.export.export_monthly_report?month=" + values2.month + "&year=" + values2.year;
                                window.open(download_url, '_blank');
                            },
                            __('Chọn tháng và năm xuất báo cáo'),
                            __('Tải về')
                        );
                    } else if (values.report_type === 'Năm') {
                        frappe.prompt(
                            [
                                {
                                    fieldname: 'year',
                                    label: __('Năm'),
                                    fieldtype: 'Int',
                                    reqd: 1,
                                    default: today.getFullYear()
                                }
                            ],
                            function(values2) {
                                var download_url = "/api/method/food_order_app.excel.export.export_yearly_report?year=" + values2.year;
                                window.open(download_url, '_blank');
                            },
                            __('Chọn năm xuất báo cáo'),
                            __('Tải về')
                        );
                    }
                },
                __('Có các lựa chọn để xuất báo cáo'),
                __('Tiếp tục')
            );
        });
    }
};
