# Works Page - Quản lý tin nhắn Zalo

## Tổng quan
Trang **Works** được tạo để quản lý tin nhắn từ các nhóm Zalo của tài khoản OA. Trang này cho phép:

1. **Lấy danh sách nhóm Zalo**: Hiển thị tất cả các nhóm OA có sẵn
2. **Chọn nhóm**: Người dùng chọn một nhóm để xem tin nhắn
3. **Lấy tin nhắn tự động**: Mỗi 5 giây, hệ thống tự động lấy tin nhắn mới
4. **Lưu ID tin nhắn**: Chỉ lấy tin nhắn từ ID cuối cùng trở về sau
5. **Hiển thị tin nhắn**: Hiển thị danh sách tin nhắn realtime với thông tin người gửi, giờ gửi và nội dung

## Cấu trúc tệp

### 1. API Endpoints (`food_order_app/api.py`)
Thêm 2 hàm mới:

#### `get_zalo_groups()` (GET)
- **Mục đích**: Lấy danh sách tất cả các nhóm Zalo của tài khoản OA
- **Endpoint**: `https://openapi.zalo.me/v3.0/oa/group/getgroupsofoa`
- **Response**:
```json
{
  "success": true,
  "groups": [
    {
      "group_id": "abc123",
      "group_name": "Nhóm công ty"
    }
  ]
}
```

#### `get_zalo_group_messages(group_id, offset=0, count=50)` (POST)
- **Mục đích**: Lấy tin nhắn từ một nhóm cụ thể
- **Endpoint**: `https://openapi.zalo.me/v3.0/oa/group/conversation`
- **Parameters**:
  - `group_id`: ID của nhóm
  - `offset`: Vị trí bắt đầu (mặc định 0)
  - `count`: Số lượng tin nhắn (mặc định 50)
- **Response**:
```json
{
  "success": true,
  "messages": [
    {
      "msg_id": "msg123",
      "sender_name": "Người dùng",
      "timestamp": "2024-01-01T10:30:00",
      "message": "Nội dung tin nhắn"
    }
  ]
}
```

### 2. Frontend Files

#### `www/works.html`
- Trang giao diện chính
- Sử dụng Frappe template system (`{% extends "templates/web.html" %}`)
- Bố cục hai cột:
  - **Bên trái**: Danh sách nhóm Zalo
  - **Bên phải**: Tin nhắn của nhóm được chọn

#### `public/css/works.css`
- Stylesheet cho trang Works
- Responsive design với mobile support
- Animations và effects
- Color scheme: Purple gradient (#667eea, #764ba2)

#### `public/js/works.js`
- Xử lý logic phía client
- Class `ZaloGroupsManager`:
  - Quản lý danh sách nhóm
  - Quản lý việc lấy tin nhắn
  - Lưu ID tin nhắn cuối cùng để không lấy lặp
  - Tự động cập nhật mỗi 5 giây
  - Đếm tin nhắn mới
  - Thời gian cập nhật lần cuối

## Luồng hoạt động

```
1. Trang load → Hiển thị button "Tải danh sách nhóm"
   ↓
2. Người dùng nhấn "Tải danh sách nhóm"
   ↓
3. Call API `get_zalo_groups()` → Hiển thị danh sách nhóm
   ↓
4. Người dùng chọn một nhóm
   ↓
5. Hiển thị phần "Tin nhắn nhóm" với button "Bắt đầu lấy tin nhắn"
   ↓
6. Người dùng nhấn "Bắt đầu lấy tin nhắn"
   ↓
7. Gọi API `get_zalo_group_messages()` ngay lập tức
   ↓
8. Mỗi 5 giây, gọi API lại để kiểm tra tin nhắn mới
   ↓
9. Tin nhắn mới được thêm vào đầu danh sách
   ↓
10. Hiển thị thống kê: trạng thái, giờ cập nhật, số tin nhắn mới
    ↓
11. Người dùng nhấn "Dừng lấy tin nhắn" để dừng
```

## Cách sử dụng

### Truy cập trang
```
http://localhost:8000/works
```

### Các bước:
1. Nhấn button **"Tải danh sách nhóm"**
2. Chọn một nhóm từ danh sách
3. Nhấn **"Bắt đầu lấy tin nhắn"** để bắt đầu lấy tin nhắn mỗi 5 giây
4. Xem tin nhắn được hiển thị realtime
5. Nhấn **"Dừng lấy tin nhắn"** để dừng
6. Nhấn **"Quay lại"** để quay lại danh sách nhóm

## Tính năng

✅ Lấy danh sách nhóm Zalo OA  
✅ Chọn nhóm để xem tin nhắn  
✅ Lấy tin nhắn tự động mỗi 5 giây  
✅ Lưu ID tin nhắn mới nhất để tránh lấy lặp  
✅ Hiển thị tin nhắn với thông tin người gửi, giờ gửi  
✅ Đếm số tin nhắn mới  
✅ Thống kê thời gian cập nhật  
✅ Responsive design (mobile + desktop)  
✅ Animations mượt mà  
✅ Error handling  

## Lưu ý

- Token Zalo OA được lấy từ bảng `tabZalo Config` trong cơ sở dữ liệu
- Token tự động được refresh nếu hết hạn (error -216)
- Giới hạn 100 tin nhắn trên giao diện để tránh lag
- Tin nhắn được sắp xếp từ mới nhất đến cũ nhất

## Troubleshooting

### Không thấy nhóm?
- Kiểm tra xem token OA có hợp lệ không
- Kiểm tra permission của OA account

### Tin nhắn không cập nhật?
- Kiểm tra console (F12) có error không
- Kiểm tra network tab xem API có được gọi không
- Kiểm tra log trong Frappe

### Giao diện không load CSS/JS?
- Kiểm tra xem file `works.css` và `works.js` có tồn tại không
- Hard refresh (Ctrl+F5) để clear cache
