# 🚀 Quick Start Guide - BudtBoy

## เริ่มใช้งานได้ใน 5 นาที!

### 1️⃣ ติดตั้ง Python

ดาวน์โหลดและติดตั้ง Python 3.11+ จาก [python.org](https://www.python.org/downloads/)

### 2️⃣ ติดตั้งโปรเจกต์

```bash
# เปิด Terminal/Command Prompt ใน folder โปรเจกต์

# สร้าง virtual environment
python -m venv venv

# เปิดใช้งาน virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# ติดตั้ง dependencies
pip install -r requirements.txt
```

### 3️⃣ ตั้งค่า Environment

```bash
# คัดลอกไฟล์ตัวอย่าง
# Windows:
copy .env.example .env
# macOS/Linux:
cp .env.example .env

# แก้ไขไฟล์ .env ด้วย text editor
# เปลี่ยน SECRET_KEY และ ADMIN_MASTER_PASSWORD
```

### 4️⃣ รันแอป

```bash
python run.py
```

### 5️⃣ เปิดเบราว์เซอร์

```
http://localhost:5000
```

## 🔐 Login ครั้งแรก

**Admin:**
- URL: `http://localhost:5000/admin/login`
- Username: `admin999`
- Password: ตามที่ตั้งใน `.env` (ADMIN_MASTER_PASSWORD)

**User:**
- สมัครสมาชิกใหม่ที่หน้า login

## 📝 ขั้นตอนถัดไป

1. อ่าน [README.md](README.md) สำหรับคู่มือฉบับเต็ม
2. อ่าน [SETUP_GUIDE.md](SETUP_GUIDE.md) สำหรับ troubleshooting
3. อ่าน [MIGRATION_STEPS.md](MIGRATION_STEPS.md) สำหรับ migration จาก Replit

## ❓ มีปัญหา?

ดูที่ [SETUP_GUIDE.md](SETUP_GUIDE.md) ส่วน Troubleshooting

---

**เท่านี้ก็พร้อมใช้งานแล้ว! 🎉**
